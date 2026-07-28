"""
generate_ledger.py
Command-line entry point (useful for demos, cron jobs, or when you don't
want to spin up the Streamlit UI).

Usage:
    python generate_ledger.py sample_data/invoices_sample.csv output_ledger.xlsx
"""

import sys
from gst_engine import generate_ledger


def main():
    if len(sys.argv) < 3:
        print("Usage: python generate_ledger.py <input_file> <output_file> [seller_state]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]
    seller_state = sys.argv[3] if len(sys.argv) > 3 else "Maharashtra"

    processed, summary = generate_ledger(input_path, output_path, seller_state)

    print("\n=== SUMMARY ===")
    for _, row in summary.iterrows():
        print(f"{row['Metric']}: {row['Value']}")

    mismatch_count = (processed["status"] == "MISMATCH").sum()
    print(f"\nLedger written to: {output_path}")
    print(f"{mismatch_count} invoice(s) flagged for review.")


if __name__ == "__main__":
    main()
