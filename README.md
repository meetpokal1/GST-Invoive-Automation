# GST Invoice & Ledger Automation Tool

A Python tool that automates GST (Goods & Services Tax) validation and ledger
generation for a batch of invoices — turning a manual, error-prone accounting
task into a one-click check.

## Problem Statement

During an accounting internship, invoice-level GST validation (checking whether
CGST/SGST/IGST was calculated correctly, and whether it matches intra-state vs.
inter-state supply rules) was done manually in Excel — slow, and easy to get
wrong when volumes are high. This tool automates that entire check:

1. Reads a batch of invoices (CSV/Excel)
2. Applies India's GST rule automatically:
   - **Same state (seller = buyer)** → CGST + SGST (split equally)
   - **Different state** → IGST (full rate)
3. Compares the *expected* tax values against what's actually on the invoice
4. Flags any mismatches with the exact reason (e.g. "IGST off by ₹2,000")
5. Generates a clean, multi-sheet Excel ledger (Summary / All Invoices / Mismatches Only)

## Tech Stack

- **Python 3** — core logic
- **pandas** — data processing
- **openpyxl** — Excel report generation
- **Streamlit** — interactive web UI

## Project Structure

```
gst-invoice-automation/
├── app.py                     # Streamlit web app (upload → validate → download)
├── gst_engine.py               # Core GST calculation + validation logic
├── generate_ledger.py          # CLI entry point (no UI needed)
├── sample_data/
│   └── invoices_sample.csv     # 10 sample invoices (2 with intentional errors)
├── requirements.txt
└── README.md
```

## How to Run

**Option 1 — Web app**
```bash
pip install -r requirements.txt
streamlit run app.py
```
Then upload `sample_data/invoices_sample.csv` (or your own file) in the browser.

**Option 2 — Command line**
```bash
pip install -r requirements.txt
python generate_ledger.py sample_data/invoices_sample.csv output_ledger.xlsx
```

## Sample Output

Running the CLI on the sample data:

```
Total Invoices: 10
Total Taxable Amount: 720000
Total CGST Collected: 20250
Total SGST Collected: 20250
Total IGST Collected: 84400
Total Invoice Value: 844150
Invoices Flagged as Mismatch: 2
2 invoice(s) flagged for review.
```

## What I'd Improve Next

- Add support for reading invoices directly from a GST portal export (JSON) format
- Add a "correct the invoice" auto-fix suggestion, not just a flag
- Add unit tests (currently validated manually against known-correct sample data)
- Deploy a live demo on Streamlit Community Cloud

## Why I Built This

I wanted a project that connects my accounting/GST work experience with the
Python and automation skills I'm developing for an ERP/cloud role — this is
the exact kind of manual reconciliation task ERP systems are meant to remove.
