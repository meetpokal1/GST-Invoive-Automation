"""Streamlit interface for the GST Invoice & Ledger Automation Tool."""

import io
from pathlib import Path
import pandas as pd
import streamlit as st

from gst_engine import build_review_queue, build_summary, process_invoices

st.set_page_config(page_title="GST Invoice & Ledger Automation", layout="wide")
st.title("GST Invoice & Ledger Automation Tool")
st.caption(
    "Automated reconciliation workbench: compare entered tax amounts with state-based "
    "expected tax rules, identify discrepancies within tolerance, and export prioritized audit ledgers."
)
st.info(
    "Demonstration only: this application uses simplified state-comparison rules and synthetic data. "
    "Flagged records assist human review and do not constitute a legal tax determination."
)

with st.sidebar:
    st.header("Settings")
    seller_state = st.text_input("Seller state", value="Maharashtra")
    st.markdown("---")
    st.markdown(
        "**Required columns**\n\n"
        "invoice_no, date, customer_name, customer_state, "
        "taxable_amount, gst_rate, cgst_amt, sgst_amt, igst_amt, invoice_total"
    )
    st.markdown("---")
    st.markdown(
        "**Synthetic Sample Data:**\n"
        "Includes 10 multi-state invoices with ₹0.50 rounding tolerance checks and 2 intentional mismatches for review."
    )

sample_csv_path = Path(__file__).resolve().parent / "sample_data" / "invoices_sample.csv"

c_upload, c_sample = st.columns([3, 1])
with c_upload:
    uploaded_file = st.file_uploader(
        "Upload invoice file (CSV or Excel)",
        type=["csv", "xlsx"],
        help="Use the required column names listed in the sidebar.",
    )

with c_sample:
    st.write("")
    st.write("")
    if st.button("📊 Reset to Sample Data"):
        st.session_state["use_sample"] = True

if uploaded_file is not None:
    st.session_state["use_sample"] = False

raw_df = None
source_label = ""

if uploaded_file is not None:
    source_label = f"Uploaded file: {uploaded_file.name}"
    try:
        if uploaded_file.name.lower().endswith(".csv"):
            raw_df = pd.read_csv(uploaded_file)
        else:
            raw_df = pd.read_excel(uploaded_file)
    except Exception as exc:
        st.error(f"Could not read uploaded file: {exc}")
elif st.session_state.get("use_sample", True) and sample_csv_path.exists():
    source_label = "Synthetic Sample Invoices (10 multi-state records with 2 intentional review mismatches)"
    try:
        raw_df = pd.read_csv(sample_csv_path)
    except Exception as exc:
        st.error(f"Could not load sample data: {exc}")

if raw_df is None:
    st.info("Upload an invoice file or click 'Reset to Sample Data' to explore the reconciliation workbench.")
else:
    try:
        st.caption(f"📁 **Active Dataset:** {source_label}")
        processed = process_invoices(raw_df, seller_state)
        summary = build_summary(processed)
        review_queue = build_review_queue(processed)
        summary_values = dict(zip(summary["Metric"], summary["Value"]))
        mismatch_count = int(summary_values["Invoices Flagged as Mismatch"])
        high_priority_count = int(summary_values["High-Priority Review Items"])

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Invoices", int(summary_values["Total Invoices"]))
        col2.metric(
            "Total Invoice Value",
            f"₹{summary_values['Total Invoice Value']:,.2f}",
        )
        col3.metric("Flagged Mismatches", mismatch_count)
        col4.metric("High-Priority Review", high_priority_count)

        st.subheader("Summary")
        st.dataframe(summary, use_container_width=True, hide_index=True)

        st.subheader("All Processed Invoices")

        def highlight_mismatch(row):
            colour = (
                "background-color: #ffe6e6"
                if row["status"] == "MISMATCH"
                else ""
            )
            return [colour] * len(row)

        st.dataframe(
            processed.style.apply(highlight_mismatch, axis=1),
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("Actionable Exception Review Queue")
        st.caption(
            "Priority is a workflow hint based on discrepancy patterns in this demo; "
            "it is not a legal determination. Review source documents before acting."
        )
        if mismatch_count:
            st.dataframe(review_queue, use_container_width=True, hide_index=True)
        else:
            st.success("No mismatches were detected using the configured tolerance.")

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            summary.to_excel(writer, sheet_name="Summary", index=False)
            processed.to_excel(writer, sheet_name="All Invoices", index=False)
            processed.loc[processed["status"] == "MISMATCH"].to_excel(
                writer, sheet_name="Mismatches Only", index=False
            )
            review_queue.to_excel(writer, sheet_name="Review Queue", index=False)

        st.download_button(
            label="Download Excel Ledger",
            data=output.getvalue(),
            file_name="gst_ledger_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    except Exception as exc:
        st.error(
            "The file could not be processed. Check that it is a valid CSV/Excel "
            "file and that the required columns, dates, amounts and invoice IDs "
            f"are valid. Details: {exc}"
        )
