"""
app.py
Streamlit front-end for the GST Invoice & Ledger Automation Tool.

Run with:
    streamlit run app.py
"""

import io
import streamlit as st
import pandas as pd
from gst_engine import process_invoices, build_summary

st.set_page_config(page_title="GST Invoice & Ledger Automation", layout="wide")

st.title("📊 GST Invoice & Ledger Automation Tool")
st.caption(
    "Upload a batch of invoices, auto-calculate CGST/SGST/IGST, "
    "and instantly flag entries that don't match GST rules."
)

with st.sidebar:
    st.header("Settings")
    seller_state = st.text_input("Your (seller) state", value="Maharashtra")
    st.markdown("---")
    st.markdown(
        "**Expected columns:**\n\n"
        "`invoice_no, date, customer_name, customer_state, "
        "taxable_amount, gst_rate, cgst_amt, sgst_amt, igst_amt, invoice_total`"
    )
    st.markdown("Don't have a file handy? Use `sample_data/invoices_sample.csv`.")

uploaded_file = st.file_uploader("Upload invoice file (CSV or Excel)", type=["csv", "xlsx"])

if uploaded_file:
    try:
        if uploaded_file.name.endswith(".csv"):
            raw_df = pd.read_csv(uploaded_file)
        else:
            raw_df = pd.read_excel(uploaded_file)

        processed = process_invoices(raw_df, seller_state)
        summary = build_summary(processed)

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Invoices", int(summary.loc[summary.Metric == "Total Invoices", "Value"].values[0]))
        col2.metric("Total Invoice Value", f"₹{summary.loc[summary.Metric == 'Total Invoice Value', 'Value'].values[0]:,}")
        mismatch_count = int(summary.loc[summary.Metric == "Invoices Flagged as Mismatch", "Value"].values[0])
        col3.metric("Flagged Mismatches", mismatch_count, delta=None, delta_color="inverse")

        st.subheader("Summary")
        st.dataframe(summary, use_container_width=True, hide_index=True)

        st.subheader("All Processed Invoices")
        def highlight_mismatch(row):
            color = "background-color: #ffe6e6" if row["status"] == "MISMATCH" else ""
            return [color] * len(row)

        st.dataframe(processed.style.apply(highlight_mismatch, axis=1), use_container_width=True)

        if mismatch_count > 0:
            st.subheader("⚠️ Mismatches Only")
            st.dataframe(processed[processed["status"] == "MISMATCH"], use_container_width=True)

        # Download button
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            summary.to_excel(writer, sheet_name="Summary", index=False)
            processed.to_excel(writer, sheet_name="All Invoices", index=False)
            processed[processed["status"] == "MISMATCH"].to_excel(writer, sheet_name="Mismatches Only", index=False)

        st.download_button(
            label="⬇️ Download Full Ledger (Excel)",
            data=output.getvalue(),
            file_name="gst_ledger_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    except ValueError as e:
        st.error(str(e))
else:
    st.info("Upload an invoice file to get started, or try the sample data in `sample_data/`.")
