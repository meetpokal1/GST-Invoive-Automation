from pathlib import Path

import pandas as pd
import pytest

from gst_engine import (
    TOLERANCE,
    calculate_gst,
    generate_ledger,
    process_invoices,
    build_review_queue,
)

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_FILE = ROOT / "sample_data" / "invoices_sample.csv"


def sample_data():
    return pd.read_csv(SAMPLE_FILE)


def test_calculate_gst_for_intra_state_supply():
    result = calculate_gst(10000, 18, "Maharashtra", " maharashtra ")
    assert result == {
        "expected_cgst": 900.0,
        "expected_sgst": 900.0,
        "expected_igst": 0.0,
        "expected_total_tax": 1800.0,
        "expected_invoice_total": 11800.0,
    }


def test_calculate_gst_for_inter_state_supply():
    result = calculate_gst(25000, 18, "Maharashtra", "Gujarat")
    assert result["expected_cgst"] == 0.0
    assert result["expected_sgst"] == 0.0
    assert result["expected_igst"] == 4500.0
    assert result["expected_invoice_total"] == 29500.0


def test_included_sample_has_ten_invoices_and_two_mismatches():
    processed = process_invoices(sample_data(), "Maharashtra")
    assert len(processed) == 10
    assert (processed["status"] == "MISMATCH").sum() == 2
    assert set(processed.loc[processed["status"] == "MISMATCH", "invoice_no"]) == {
        "INV-1005",
        "INV-1009",
    }
    by_invoice = processed.set_index("invoice_no")
    assert by_invoice.loc["INV-1005", "exception_category"] == "TAX_HEAD_AND_TOTAL"
    assert by_invoice.loc["INV-1009", "exception_category"] == "TAX_HEAD_ALLOCATION"
    assert by_invoice.loc["INV-1009", "review_priority"] == "High"


def test_small_paise_difference_within_tolerance_is_not_flagged():
    df = sample_data().iloc[[0]].copy()
    df["cgst_amt"] = df["cgst_amt"].astype(float)
    df.loc[df.index[0], "cgst_amt"] = 900.01
    processed = process_invoices(df, "Maharashtra")
    assert TOLERANCE == 0.02
    assert processed.iloc[0]["status"] == "OK"


def test_missing_required_column_is_rejected():
    df = sample_data().drop(columns=["invoice_total"])
    with pytest.raises(ValueError, match="invoice_total"):
        process_invoices(df, "Maharashtra")


@pytest.mark.parametrize("value", [None, "not-a-number", float("inf")])
def test_invalid_numeric_values_are_rejected(value):
    df = sample_data().iloc[[0]].copy()
    df["taxable_amount"] = df["taxable_amount"].astype(object)
    df.loc[df.index[0], "taxable_amount"] = value
    with pytest.raises(ValueError, match="taxable_amount"):
        process_invoices(df, "Maharashtra")


def test_invalid_date_is_rejected():
    df = sample_data().iloc[[0]].copy()
    df.loc[df.index[0], "date"] = "not-a-date"
    with pytest.raises(ValueError, match="Invalid date"):
        process_invoices(df, "Maharashtra")


def test_duplicate_invoice_numbers_are_rejected():
    df = sample_data().iloc[:2].copy()
    df.loc[df.index[1], "invoice_no"] = df.loc[df.index[0], "invoice_no"]
    with pytest.raises(ValueError, match="Duplicate invoice"):
        process_invoices(df, "Maharashtra")


def test_blank_buyer_state_is_rejected():
    df = sample_data().iloc[[0]].copy()
    df.loc[df.index[0], "customer_state"] = "  "
    with pytest.raises(ValueError, match="customer_state"):
        process_invoices(df, "Maharashtra")


def test_negative_taxable_amount_is_rejected():
    df = sample_data().iloc[[0]].copy()
    df.loc[df.index[0], "taxable_amount"] = -1
    with pytest.raises(ValueError, match="negative values"):
        process_invoices(df, "Maharashtra")


def test_empty_input_is_rejected():
    df = sample_data().iloc[0:0]
    with pytest.raises(ValueError, match="no invoice rows"):
        process_invoices(df, "Maharashtra")


def test_generate_ledger_creates_expected_sheets(tmp_path):
    output_file = tmp_path / "ledger.xlsx"
    processed, summary = generate_ledger(str(SAMPLE_FILE), str(output_file))

    assert output_file.exists()
    assert len(processed) == 10
    assert int(
        summary.loc[
            summary["Metric"] == "Invoices Flagged as Mismatch", "Value"
        ].iloc[0]
    ) == 2

    with pd.ExcelFile(output_file) as workbook:
        assert workbook.sheet_names == [
            "Summary",
            "All Invoices",
            "Mismatches Only",
            "Review Queue",
        ]
        mismatch_sheet = pd.read_excel(workbook, sheet_name="Mismatches Only")
        review_queue = pd.read_excel(workbook, sheet_name="Review Queue")
    assert set(mismatch_sheet["invoice_no"]) == {"INV-1005", "INV-1009"}
    assert list(review_queue["invoice_no"]) == ["INV-1009", "INV-1005"]
    assert "recommended_review_action" in review_queue.columns


def test_unsupported_input_extension_is_rejected():
    with pytest.raises(ValueError, match=".csv, .xlsx, or .xls"):
        generate_ledger("invoices.json", "out.xlsx")



def test_review_queue_is_exception_only_and_priority_ordered():
    processed = process_invoices(sample_data(), "Maharashtra")
    queue = build_review_queue(processed)

    assert len(queue) == 2
    assert list(queue["invoice_no"]) == ["INV-1009", "INV-1005"]
    assert queue.iloc[0]["review_priority"] == "High"
    assert queue.iloc[0]["exception_category"] == "TAX_HEAD_ALLOCATION"
    assert queue.iloc[0]["recommended_review_action"]
