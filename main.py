from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dateutil import parser
import re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ExtractRequest(BaseModel):
    invoice_text: str

def parse_money(value):
    if not value:
        return None
    value = value.replace("Rs.", "").replace("Rs", "").replace("₹", "").replace(",", "").strip()
    try:
        return float(value)
    except:
        return None

from datetime import datetime

def parse_date(value):
    if not value:
        return None

    value = value.strip()

    known_formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%d %B %Y",
        "%d %b %Y",
    ]

    for fmt in known_formats:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except:
            pass

    try:
        if re.match(r'^\d{1,2}[-/\.]\d{1,2}[-/\.]\d{4}$', value):
            return parser.parse(value, dayfirst=True).date().isoformat()
        return parser.parse(value, dayfirst=True).date().isoformat()
    except:
        return None

def extract_invoice_no(text):
    patterns = [
        r'(?im)^\s*(?:Invoice\s*No\.?|Invoice\s*Number|Invoice\s*#|Inv\s*No\.?|Receipt\s*No\.?|Ref(?:erence)?\s*No\.?|Ref)\s*[:#-]?\s*([A-Z0-9][A-Z0-9\/-]*)\s*$',
        r'(?i)\b(?:Invoice\s*No\.?|Invoice\s*Number|Invoice\s*#|Inv\s*No\.?|Receipt\s*No\.?|Ref(?:erence)?\s*No\.?|Ref)\b[^\n]{0,25}?([A-Z]{1,5}-\d{2,10}[A-Z0-9\/-]*)',
        r'(?i)\b([A-Z]{1,5}-\d{2,10}[A-Z0-9\/-]*)\b'
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return m.group(1).strip(" .:#")
    return None

@app.post("/extract")
def extract_invoice(data: ExtractRequest):
    text = data.invoice_text

    invoice_no = extract_invoice_no(text)

    date = None
    for label in [r"Date", r"Issued", r"Invoice Date", r"Bill Date"]:
        m = re.search(rf"(?i){label}\s*[:\-]?\s*([^\n]+)", text)
        if m:
            date = parse_date(m.group(1).strip())
            if date:
                break

    vendor = None
    for label in [r"Vendor", r"Supplier", r"From"]:
        m = re.search(rf"(?i){label}\s*[:\-]?\s*([^\n]+)", text)
        if m:
            vendor = m.group(1).strip()
            break

    amount = None
    for pattern in [
        r'(?i)Subtotal\s*[:\-]?\s*(?:Rs\.?|₹)?\s*([\d,]+\.\d{2})',
        r'(?i)Amount\s*Before\s*Tax\s*[:\-]?\s*(?:Rs\.?|₹)?\s*([\d,]+\.\d{2})',
        r'(?i)Net\s*Amount\s*[:\-]?\s*(?:Rs\.?|₹)?\s*([\d,]+\.\d{2})'
    ]:
        m = re.search(pattern, text)
        if m:
            amount = parse_money(m.group(1))
            break

    tax = None
    for pattern in [
        r'(?i)(?:GST|IGST|CGST|SGST|VAT|Tax)[^\n:]*[:\-]?\s*(?:Rs\.?|₹)?\s*([\d,]+\.\d{2})'
    ]:
        m = re.search(pattern, text)
        if m:
            tax = parse_money(m.group(1))
            break

    currency = None
    if re.search(r'(?i)\bINR\b|Rs\.?|₹', text):
        currency = "INR"
    elif re.search(r'(?i)\bUSD\b|\$', text):
        currency = "USD"
    elif re.search(r'(?i)\bEUR\b|€', text):
        currency = "EUR"

    return {
        "invoice_no": invoice_no,
        "date": date,
        "vendor": vendor,
        "amount": amount,
        "tax": tax,
        "currency": currency
    }
