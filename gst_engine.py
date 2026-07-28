"""
gst_engine.py
Core logic for GST calculation, invoice validation, and ledger generation.

Business rule:
- If buyer's state == seller's state  -> Intra-state supply -> CGST + SGST (split equally)
- If buyer's state != seller's state  -> Inter-state supply -> IGST (full rate)

This mirrors how GST actually works in India for CA/accounts teams doing
manual invoice checking - which is the real-world process this tool automates.
"""

import pandas as pd
from datetime import datetime

# Rounding tolerance (in Rs.) before we flag something as a mismatch.
# Real invoices often have paisa-level rounding differences that are NOT errors.
TOLERANCE = 0.5


def calculate_gst(taxable_amount: float, gst_rate: float, seller_state: str, buyer_state: str) -> dict:
    """
    Given a taxable amount and GST rate, return the CORRECT expected
    CGST / SGST / IGST split based on seller and buyer state.
    """
    total_tax = round(taxable_amount * (gst_rate / 100), 2)

    if seller_state.strip().lower() == buyer_state.strip().lower():
        # Intra-state: split equally between Central and State GST
        cgst = round(total_tax / 2, 2)
        sgst = round(total_tax / 2, 2)
        igst = 0.0
    else:
        # Inter-state: full amount goes as Integrated GST
        cgst = 0.0
        sgst = 0.0
        igst = total_tax

    return {
        "expected_cgst": cgst,
        "expected_sgst": sgst,
        "expected_igst": igst,
        "expected_total_tax": total_tax,
        "expected_invoice_total": round(taxable_amount + total_tax, 2),
    }


def process_invoices(df: pd.DataFrame, seller_state: str) -> pd.DataFrame:
    """
    Takes a raw invoice dataframe (as uploaded by the user) and returns
    an enriched dataframe with expected tax values and a mismatch flag.

    Expected input columns:
        invoice_no, date, customer_name, customer_state,
        taxable_amount, gst_rate, cgst_amt, sgst_amt, igst_amt, invoice_total
    """
    required_cols = [
        "invoice_no", "date", "customer_name", "customer_state",
        "taxable_amount", "gst_rate", "cgst_amt", "sgst_amt", "igst_amt", "invoice_total"
    ]
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required column(s) in uploaded file: {missing}")

    results = []
    for _, row in df.iterrows():
        expected = calculate_gst(
            taxable_amount=float(row["taxable_amount"]),
            gst_rate=float(row["gst_rate"]),
            seller_state=seller_state,
            buyer_state=str(row["customer_state"]),
        )

        cgst_diff = abs(expected["expected_cgst"] - float(row["cgst_amt"]))
        sgst_diff = abs(expected["expected_sgst"] - float(row["sgst_amt"]))
        igst_diff = abs(expected["expected_igst"] - float(row["igst_amt"]))
        total_diff = abs(expected["expected_invoice_total"] - float(row["invoice_total"]))

        is_mismatch = (
            cgst_diff > TOLERANCE
            or sgst_diff > TOLERANCE
            or igst_diff > TOLERANCE
            or total_diff > TOLERANCE
        )

        reasons = []
        if cgst_diff > TOLERANCE:
            reasons.append(f"CGST off by Rs.{cgst_diff:.2f}")
        if sgst_diff > TOLERANCE:
            reasons.append(f"SGST off by Rs.{sgst_diff:.2f}")
        if igst_diff > TOLERANCE:
            reasons.append(f"IGST off by Rs.{igst_diff:.2f}")
        if total_diff > TOLERANCE:
            reasons.append(f"Invoice total off by Rs.{total_diff:.2f}")

        results.append({
            **row.to_dict(),
            **expected,
            "status": "MISMATCH" if is_mismatch else "OK",
            "mismatch_reason": "; ".join(reasons) if reasons else "",
        })

    return pd.DataFrame(results)


def build_summary(processed_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate totals for a quick ledger-style summary sheet."""
    summary = {
        "Total Invoices": len(processed_df),
        "Total Taxable Amount": round(processed_df["taxable_amount"].sum(), 2),
        "Total CGST Collected": round(processed_df["cgst_amt"].sum(), 2),
        "Total SGST Collected": round(processed_df["sgst_amt"].sum(), 2),
        "Total IGST Collected": round(processed_df["igst_amt"].sum(), 2),
        "Total Invoice Value": round(processed_df["invoice_total"].sum(), 2),
        "Invoices Flagged as Mismatch": int((processed_df["status"] == "MISMATCH").sum()),
        "Report Generated On": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    return pd.DataFrame(list(summary.items()), columns=["Metric", "Value"])


def generate_ledger(input_path: str, output_path: str, seller_state: str = "Maharashtra"):
    """CLI-friendly entry point: reads a CSV/Excel invoice file and writes
    a formatted Excel ledger with a Summary sheet, full processed data,
    and a Mismatches-only sheet."""
    if input_path.endswith(".csv"):
        df = pd.read_csv(input_path)
    else:
        df = pd.read_excel(input_path)

    processed = process_invoices(df, seller_state)
    summary = build_summary(processed)
    mismatches = processed[processed["status"] == "MISMATCH"]

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Summary", index=False)
        processed.to_excel(writer, sheet_name="All Invoices", index=False)
        mismatches.to_excel(writer, sheet_name="Mismatches Only", index=False)

    return processed, summary
