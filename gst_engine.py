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

        component_fields = ("cgst_amt", "sgst_amt", "igst_amt")
        component_errors = [field for field in component_fields if differences[field] > TOLERANCE]
        expected_components = {
            "cgst_amt": expected["expected_cgst"],
            "sgst_amt": expected["expected_sgst"],
            "igst_amt": expected["expected_igst"],
        }
        reported_components = {
            "cgst_amt": float(row["cgst_amt"]),
            "sgst_amt": float(row["sgst_amt"]),
            "igst_amt": float(row["igst_amt"]),
        }
        # This pattern is a review hint only; it is not a legal place-of-supply determination.
        tax_head_issue = any(
            expected_components[field] <= TOLERANCE and reported_components[field] > TOLERANCE
            for field in component_fields
        )
        total_issue = differences["invoice_total"] > TOLERANCE

        if not reasons:
            category = "NO_EXCEPTION"
            priority = "None"
            action = "No discrepancy detected under this tool's simplified rules."
        elif tax_head_issue and total_issue:
            category = "TAX_HEAD_AND_TOTAL"
            priority = "High"
            action = (
                "Compare the original invoice, place-of-supply facts, tax-head allocation, taxable value, "
                "additional charges and rounding. Do not auto-correct."
            )
        elif tax_head_issue:
            category = "TAX_HEAD_ALLOCATION"
            priority = "High"
            action = (
                "Verify the applicable place-of-supply/tax-head treatment against the source invoice "
                "and transaction facts before posting."
            )
        elif total_issue and component_errors:
            category = "TAX_COMPONENT_AND_TOTAL"
            priority = "High"
            action = (
                "Recheck each reported tax component and the invoice total against the source invoice; "
                "this demo assumes no extra charges or discounts."
            )
        elif component_errors:
            category = "TAX_COMPONENT_AMOUNT"
            priority = "Medium"
            action = "Recalculate the affected tax component(s) and compare with the source invoice."
        else:
            category = "INVOICE_TOTAL"
            priority = "Medium"
            action = (
                "Check taxable value, rate, additional charges/discounts and rounding; "
                "this demo assumes invoice total = taxable value + GST."
            )

        results.append(
            {
                **row.to_dict(),
                **expected,
                "status": "MISMATCH" if reasons else "OK",
                "mismatch_reason": "; ".join(reasons),
                "exception_category": category,
                "review_priority": priority,
                "recommended_review_action": action,
            }
        )

    return pd.DataFrame(results)



def build_review_queue(processed_df: pd.DataFrame) -> pd.DataFrame:
    """Return a compact, priority-ordered list of invoice exceptions for human review."""
    if processed_df.empty:
        raise ValueError("Cannot build a review queue from an empty invoice table.")
    if "exception_category" not in processed_df.columns:
        raise ValueError("Processed invoice data is missing exception triage fields.")

    queue = processed_df.loc[processed_df["status"] == "MISMATCH"].copy()
    priority_order = {"High": 0, "Medium": 1, "Low": 2, "None": 3}
    queue["_priority_sort"] = queue["review_priority"].map(priority_order).fillna(9)
    queue = queue.sort_values(["_priority_sort", "date", "invoice_no"], kind="stable")
    queue = queue.drop(columns=["_priority_sort"])
    preferred_columns = [
        "invoice_no", "date", "customer_name", "customer_state", "taxable_amount", "gst_rate",
        "expected_cgst", "expected_sgst", "expected_igst", "expected_invoice_total",
        "cgst_amt", "sgst_amt", "igst_amt", "invoice_total", "exception_category",
        "review_priority", "mismatch_reason", "recommended_review_action",
    ]
    return queue[[column for column in preferred_columns if column in queue.columns]].reset_index(drop=True)

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
        "High-Priority Review Items": int((processed_df["review_priority"] == "High").sum()),
        "Tax-Head Allocation Exceptions": int(processed_df["exception_category"].isin(["TAX_HEAD_ALLOCATION", "TAX_HEAD_AND_TOTAL"]).sum()),
        "Invoice-Total Exceptions": int(processed_df["exception_category"].isin(["INVOICE_TOTAL", "TAX_HEAD_AND_TOTAL", "TAX_COMPONENT_AND_TOTAL"]).sum()),
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
    review_queue = build_review_queue(processed)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Summary", index=False)
        processed.to_excel(writer, sheet_name="All Invoices", index=False)
        mismatches.to_excel(writer, sheet_name="Mismatches Only", index=False)
        review_queue.to_excel(writer, sheet_name="Review Queue", index=False)

    return processed, summary
