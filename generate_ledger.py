"""Command-line interface for generating an Excel invoice ledger."""

import sys

from gst_engine import generate_ledger


def main() -> int:
    if len(sys.argv) < 3:
        print(
            "Usage: python generate_ledger.py <input_file> <output_file> [seller_state]",
            file=sys.stderr,
        )
        return 2

    input_path = sys.argv[1]
    output_path = sys.argv[2]
    seller_state = sys.argv[3] if len(sys.argv) > 3 else "Maharashtra"

    try:
        processed, summary = generate_ledger(input_path, output_path, seller_state)
    except (OSError, ValueError, ImportError) as exc:
        print(f"Could not generate the ledger: {exc}", file=sys.stderr)
        return 1

    print("\n=== SUMMARY ===")
    for _, row in summary.iterrows():
        print(f"{row['Metric']}: {row['Value']}")

    mismatch_count = int((processed["status"] == "MISMATCH").sum())
    print(f"\nLedger written to: {output_path}")
    print(f"{mismatch_count} invoice(s) flagged for review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
