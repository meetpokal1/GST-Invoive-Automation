# GST Invoice & Ledger Automation Tool

A small Python application that checks invoice-level GST calculations and generates a review-ready Excel ledger. It demonstrates business-rule automation, tabular data validation, exception reporting, and Excel report generation.

> **Scope note:** This is a learning and demonstration project, not a complete GST-compliance product or a substitute for professional tax advice. It uses a simplified state-comparison rule for CGST/SGST versus IGST and assumes invoice value equals taxable value plus GST. It does not cover every place-of-supply rule, exempt supply, cess, discounts, freight, reverse charge, credit/debit notes, or other special cases.

## What it does

- Reads invoice batches from CSV or Excel files.
- Checks required columns, blank fields, dates, numeric values, GST-rate bounds, and duplicate invoice numbers.
- Calculates expected CGST/SGST for same-state transactions and IGST for different-state transactions under the simplified rules described above.
- Flags tax-component or invoice-total differences above a configurable paise-level tolerance.
- Creates an Excel workbook with Summary, All Invoices, and Mismatches Only sheets.
- Offers a Streamlit interface and a command-line workflow.

## Tech stack

- Python
- pandas
- openpyxl
- Streamlit
- pytest

## Project structure

- app.py — Streamlit interface
- gst_engine.py — tax calculations, validation and reporting
- generate_ledger.py — command-line entry point
- requirements.txt — dependencies
- sample_data/invoices_sample.csv — synthetic demo data
- tests/test_gst_engine.py — automated tests
- .github/workflows/tests.yml — GitHub Actions test workflow

## Run locally

Use Python 3.10 or later. From the repository root, create a virtual environment:

    python -m venv .venv

Activate it, then install dependencies:

    # Windows PowerShell
    .\.venv\Scripts\Activate.ps1

    # macOS / Linux
    source .venv/bin/activate

    python -m pip install -r requirements.txt

### Option 1: Streamlit app

    streamlit run app.py

Upload sample_data/invoices_sample.csv, or upload a CSV/Excel file with the required columns. Set the seller state in the sidebar. The included sample is synthetic and contains two intentional tax mismatches.

### Option 2: Generate an Excel ledger from the terminal

    python generate_ledger.py sample_data/invoices_sample.csv output_ledger.xlsx Maharashtra

The generated workbook contains:

- **Summary** — invoice count, amounts, tax totals, flagged count and report timestamp.
- **All Invoices** — source data, calculated expected values, validation status and mismatch reasons.
- **Mismatches Only** — only records requiring review.

## Run tests

    python -m pytest -q

Tests cover intra-state and inter-state calculations, the sample data, paise-level tolerance, missing columns, invalid numbers and dates, duplicate invoice IDs, blank states, negative amounts, empty files, output workbook sheets and unsupported file extensions. GitHub Actions runs the same test suite on pushes and pull requests.

## Input data format

The input must include these columns (column-name case and surrounding whitespace are normalised):

invoice_no, date, customer_name, customer_state, taxable_amount, gst_rate, cgst_amt, sgst_amt, igst_amt, invoice_total

Invoice numbers must be unique within the uploaded batch. This first version expects non-negative taxable amounts and tax values; credit notes and negative-value invoices are outside scope. Rates are expressed as percentages, for example 18 for 18%.

## Business rules and limitations

- A buyer state matching the seller state after whitespace and case normalisation is treated as intra-state; otherwise it is treated as inter-state.
- CGST and SGST are rounded independently to two decimal places. IGST is rounded to two decimal places.
- Tax components and invoice totals are compared with a tolerance of ₹0.02 to avoid flagging tiny paise-level differences. Change TOLERANCE in gst_engine.py if a different review policy is needed.
- The app flags discrepancies for human review; it does not automatically alter original invoice values or certify that an invoice is legally compliant.

## Example use case

An accounts or operations team exports a batch of invoices from its billing system. The tool identifies records whose entered tax split or total differs from the simplified expected calculation and creates a separate review sheet so the team can investigate exceptions rather than checking every row manually.

## Future improvements

- Add configurable seller GSTIN and appropriate place-of-supply rules.
- Add richer audit trails and configurable business policies.
- Support credit notes, exempt items, cess, discounts and other invoice components.
- Add CSV schema templates, broader integration tests and a deployed demo using synthetic data only.

## Responsible use

Use synthetic or properly authorised data in demos. Do not upload confidential customer, financial or tax records to a public deployment. This project is intended for learning and demonstration, not for filing tax returns or replacing review by a qualified professional.
