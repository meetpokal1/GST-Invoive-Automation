from pathlib import Path

import pandas as pd
import pytest

from gst_engine import (
    TOLERANCE,
    build_summary,
    calculate_gst,
    generate_ledger,
    process_invoices,
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


def test_small_paise_difference_within_tolerance_is_not_flagged():
    df = sample_data().iloc[[0]].copy()
    df [cgst_amt