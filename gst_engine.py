"""Core GST calculation, invoice validation, and ledger generation.

This project is a small demonstration tool, not a complete GST-compliance
system. It implements a simplified state-based CGST/SGST vs IGST rule and
expects invoice totals to equal taxable value plus the calculated GST.
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

import pandas as pd

# Allow small paise-level differences while still flagging meaningful errors.
TOLERANCE = 0.02

REQUIRED_COLUMNS = [
    "invoice_no",
    "date",
    "customer_name",
    "customer_state",
    "taxable_amount",
    "gst_rate",
    "cgst_amt",
    "sgst_amt",
    "igst_amt",
    "invoice_total",
]
NUMERIC_COLUMNS = [
    "taxable_amount",
    "gst_rate",
    "cgst_amt",
    "sgst_amt",
    "igst_amt",
    "invoice_total",
]


def _money(value) -> float:
    """Round a numeric value to two decimal places using half-up rounding."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Expected a valid numeric amount; received {value!r}.") from exc
    if not amount.is_finite():
        raise ValueError("Amounts and tax rates must be finite numbers.")
    return float(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _normalise_state(state: str, field_name: str) -> str:
    if state is None or pd.isna(state) or not str(state).strip():
        raise ValueError(f"{field_name} must not be blank.")
    return " ".join(str(state).split()).casefold()


def calculate_gst(
    taxable_amount: float,
    gst_rate: float,
    seller_state: str,
    buyer_state: str,
) -> dict:
    """Return expected tax values under this project's simplified state rule.

    Same-state transactions are treated as CGST + SGST; different-state
    transactions are treated as IGST. This is not a complete implementation
    of all GST place-of-supply or tax-treatment rules.
    """
    taxable = _money(taxable_amount)
    rate = _money(gst_rate)
    seller = _normalise_state(seller_state, "Seller state")
    buyer = _normalise_state(buyer_state, "Buyer state")

    if taxable < 0:
        raise ValueError("Taxable amount cannot be negative in this demo.")
    if not 0 <= rate <= 100:
        raise ValueError("GST rate must be between 0 and 100.")

    if seller == buyer:
        # Round each tax component independently to paise.
        cgst = _money(Decimal(str(taxable)) * Decimal(str(rate)) / Decimal("200"))
        sgst = _money(Decimal(str(taxable)) * Decimal(str(rate)) / Decimal("200"))
        igst = 0.0
    else:
        cgst = 0.0
        sgst = 0.0
        igst = _money(Decimal(str(taxable)) * Decimal(str(rate)) / Decimal("100"))

    total_tax = _money(cgst + sgst + igst)
    invoice_total = _money(taxable + total_tax)

    return {
        "expected_cgst": cgst,
        "expected_sgst": sgst,
        "expected_igst": igst,
        "expected_total_tax": total_tax,
        "expected_invoice_total": invoice_total,
    }


def _prepare_invoice_data(df: pd.DataFrame, seller_state: str) -> pd.DataFrame:
    """Normalise columns and reject rows that cannot be safely validated."""
    if not isinstance(df, pd.DataFrame):
        raise ValueError("Input must be a CSV or Excel table.")
    if df.empty:
        raise ValueError("The uploaded file contains no invoice rows.")

    clean = df.copy()
    clean.columns = [str(column).strip().lower() for column in clean.columns]
    if len(set(clean.columns)) != len(clean.columns):
        raise ValueError("Column names must be unique after trimming spaces and case.")

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in clean.columns]
    if missing_columns:
        raise ValueError(f"Missing required column(s): {', '.join(missing_columns)}")

    # Report human-readable spreadsheet row numbers (header is row 1).
    for column in ("invoice_no", "customer_name", "customer_state", "date"):
        values = clean[column]
        blank = values.isna() | values.astype(str).str.strip().eq("")
        if blank.any():
            rows = [str(index + 2) for index in clean.index[blank].tolist()]
            raise ValueError(
                f"Column '{column}' contains blank values on spreadsheet row(s): {', '.join(rows)}."
            )

    # Invoice numbers should be unique in a single batch to avoid double-counting.
    invoice_numbers = clean["invoice_no"].astype(str).str.strip()
    duplicates = invoice_numbers.duplicated(keep=False)
    if duplicates.any():
        values = sorted(invoice_numbers[duplicates].unique().tolist())
        raise ValueError(f"Duplicate invoice number(s) found: {', '.join(values)}")
    clean["invoice_no"] = invoice_numbers

    # Validate dates explicitly, then store parsed dates for reliable output.
    parsed_dates = pd.to_datetime(clean["date"], errors="coerce")
    if parsed_dates.isna().any():
        rows = [str(index + 2) for index in clean.index[parsed_dates.isna()].tolist()]
        raise ValueError(f"Invalid date value(s) on spreadsheet row(s): {', '.join(rows)}.")
    clean["date"] = parsed_dates

    for column in NUMERIC_COLUMNS:
        converted = pd.to_numeric(clean[column], errors="coerce")
        invalid = converted.isna()
        if invalid.any():
            rows = [str(index + 2) for index in clean.index[invalid].tolist()]
            raise ValueError(
                f"Column '{column}' contains missing or non-numeric values on spreadsheet row(s): {', '.join(rows)}."
            )
        if not converted.map(lambda value: Decimal(str(value)).is_finite()).all():
            raise ValueError(f"Column '{column}' contains non-finite values.")
        clean[column] = converted.astype(float)

    for column in ("taxable_amount", "cgst_amt", "sgst_amt", "igst_amt", "invoice_total"):
        negative = clean[column] < 0
        if negative.any():
            rows = [str(index + 2) for index in clean.index[negative].tolist()]
            raise ValueError(
                f"Column '{column}' contains negative values on spreadsheet row(s): {', '.join(rows)}. "
                "Credit notes and negative-value invoices are outside this demo's scope."
            )

    invalid_rates = (clean["gst_rate"] < 0) | (clean["gst_rate"] > 100)
    if invalid_rates.any():
        rows = [str(index + 2) for index in clean.index[invalid_rates].tolist()]
        raise ValueError(f"GST rate must be between 0 and 100 on spreadsheet row(s): {', '.join(rows)}.")

    _normalise_state(seller_state, "Seller state")
    for index, state in clean["customer_state"].items():
        _normalise_state(state, f"Buyer state on spreadsheet row {index + 2}")

    return clean


def process_invoices(df: pd.DataFrame, seller_state: str) -> pd.DataFrame:
    """Validate invoices and append expected tax calculations and mismatch flags."""
    clean = _prepare_invoice_data(df, seller_state)
    results = []

    for _, row in clean.iterrows():
        expected = calculate_gst(
            taxable_amount=row["taxable_amount"],
            gst_rate=row["gst_rate"],
            seller_state=seller_state,
            buyer_state=row["customer_state"],
        )

        differences = {
            "cgst_amt": abs(expected["expected_cgst"] - float(row["cgst_amt"])),
            "sgst_amt": abs(expected["expected_sgst"] - float(row["sgst_amt"])),
            "igst_amt": abs(expected["expected_igst"] - float(row["igst_amt"])),
            "invoice_total": abs(expected["expected_invoice_total"] - float(row["invoice_total"])),
        }
        reasons = []
        for field, difference in differences.items():
            if difference > TOLERANCE:
                display_name = {
                    "cgst_amt": "CGST",
                    "sgst_amt": "SGST",
                    "igst_amt": "IGST",
                    "invoice_total": "Invoice total",
                }[field]
                reasons.append(f"{display_name} off by Rs.{difference:.2f}")

        results.append(
            {
                **row.to_dict(),
                **expected,
                "status": "MISMATCH" if reasons else "OK",
                "mismatch_reason": "; ".join(reasons),
            }
        )

    return pd.DataFrame(results)


def build_summary(processed_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate useful totals from the validated and processed invoice table."""
    if processed_df.empty:
        raise ValueError("Cannot build a summary from an empty invoice table.")

    summary = {
        "Total Invoices": len(processed_df),
        "Total Taxable Amount": round(float(processed_df["taxable_amount"].sum()), 2),
        "Total CGST Collected": round(float(processed_df["cgst_amt"].sum()), 2),
        "Total SGST Collected": round(float(processed_df["sgst_amt"].sum()), 2),
        "Total IGST Collected": round(float(processed_df["igst_amt"].sum()), 2),
        "Total Invoice Value": round(float(processed_df["invoice_total"].sum()), 2),
        "Invoices Flagged as Mismatch": int((processed_df["status"] == "MISMATCH").sum()),
        "Report Generated On": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    return pd.DataFrame(list(summary.items()), columns=["Metric", "Value"])


def generate_ledger(input_path: str, output_path: str, seller_state: str = "Maharashtra"):
    """Read a CSV/Excel invoice file and write a three-sheet Excel ledger."""
    input_file = Path(input_path)
    suffix = input_file.suffix.lower()
    if suffix == ".csv":
        df = pd.read_csv(input_file)
    elif suffix in {".xlsx", ".xls"}:
        df = pd.read_excel(input_file)
    else:
        raise ValueError("Input file must use the .csv, .xlsx, or .xls extension.")

    processed = process_invoices(df, seller_state)
    summary = build_summary(processed)
    mismatches = processed[processed["status"] == "MISMATCH"]

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Summary", index=False)
        processed.to_excel(writer, sheet_name="All Invoices", index=False)
        mismatches.to_excel(writer, sheet_name="Mismatches Only", index=False)

    return processed, summary
