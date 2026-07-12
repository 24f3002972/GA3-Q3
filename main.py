from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dateutil import parser
from datetime import datetime
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
    value = (
        value.replace("Rs.", "")
        .replace("Rs", "")
        .replace("₹", "")
        .replace("$", "")
        .replace("€", "")
        .replace(",", "")
        .strip()
    )
    try:
        return float(value)
    except:
        return None

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
        if re.match(r'^\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2}$', value):
            return parser.parse(value, yearfirst=True).date().isoformat()
        return parser.parse(value, dayfirst=True).date().isoformat()
    except:
        return None

def extract_invoice_no(text):
    patterns = [
        r'(?im)^\s*(?:Invoice\s*No\.?|Invoice\s*Number|Invoice\s*#|Inv\s*No\.?|Receipt\s*No\.?|Ref(?:erence)?\s*No\.?|Ref)\s*[:#-]?\s*([A-Z0-9][A-Z0-9\/-]*)\s*$',
        r'(?i)\b(?:Invoice\s*No\.?|Invoice\s*Number|Invoice\s*#|Inv\s*No\.?|Receipt\s*No\.?|Ref(?:erence)?\s*No\.?|Ref)\b[^\n]{0,25}?([A-Z0-9][A-Z0-9\/-]*)',
        r'(?i)\b([A-Z]{1,5}-\d{2,10}[A-Z0-9\/-]*)\b'
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return m.group(1).strip(" .:#")
    return None

def extract_vendor(text):
    patterns = [
        r'(?im)^\s*(?:Vendor|Supplier|From|Bill From|Sold By|Issued By|Provider|Company|Seller)\s*[:\-]?\s*(.+?)\s*$'
    ]

    ignore = [
        "invoice", "tax invoice", "bill to", "ship to", "subtotal", "sub total", "total",
        "gst", "igst", "cgst", "sgst", "date", "invoice no", "invoice number",
        "amount", "currency", "description", "qty", "quantity"
    ]

    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            candidate = m.group(1).strip(" .:-")
            if candidate and candidate.lower() not in ignore:
                return candidate

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines[:8]:
        low = line.lower()
        if any(word in low for word in ignore):
            continue
        if re.search(r'^[A-Za-z][A-Za-z0-9&.,()\/ -]{2,}$', line):
            return line.strip(" .:-")

    return None

def extract_amount(text):
    patterns = [
        r'(?i)Subtotal\s*[:\-]?\s*(?:Rs\.?|₹|\$|€)?\s*([\d,]+\.\d{2})',
        r'(?i)Sub\s*Total\s*[:\-]?\s*(?:Rs\.?|₹|\$|€)?\s*([\d,]+\.\d{2})',
        r'(?i)Amount\s*Before\s*Tax\s*[:\-]?\s*(?:Rs\.?|₹|\$|€)?\s*([\d,]+\.\d{2})',
        r'(?i)Net\s*Amount\s*[:\-]?\s*(?:Rs\.?|₹|\$|€)?\s*([\d,]+\.\d{2})',
        r'(?i)Taxable\s*Amount\s*[:\-]?\s*(?:Rs\.?|₹|\$|€)?\s*([\d,]+\.\d{2})',
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return parse_money(m.group(1))
    return None

def extract_tax(text):
    total_tax_patterns = [
        r'(?im)^(?:GST|Total GST|Tax|Total Tax|VAT)[^\n:]*[:\-]?\s*(?:Rs\.?|₹|\$|€)?\s*([\d,]+\.\d{2})\s*$'
    ]

    for pattern in total_tax_patterns:
        m = re.search(pattern, text)
        if m:
            return parse_money(m.group(1))

    m = re.search(
        r'(?im)^(?:IGST|Integrated GST)[^\n:]*[:\-]?\s*(?:Rs\.?|₹|\$|€)?\s*([\d,]+\.\d{2})\s*$',
        text
    )
    if m:
        return parse_money(m.group(1))

    component_patterns = [
        r'(?im)^(?:CGST|Central GST)[^\n:]*[:\-]?\s*(?:Rs\.?|₹|\$|€)?\s*([\d,]+\.\d{2})\s*$',
        r'(?im)^(?:SGST|State GST)[^\n:]*[:\-]?\s*(?:Rs\.?|₹|\$|€)?\s*([\d,]+\.\d{2})\s*$'
    ]

    values = []
    for pattern in component_patterns:
        matches = re.findall(pattern, text)
        for x in matches:
            val = parse_money(x)
            if val is not None:
                values.append(val)

    if values:
        return round(sum(values), 2)

    return None

def extract_currency(text):
    if re.search(r'(?i)\bINR\b|₹|Rs\.?', text):
        return "INR"
    if re.search(r'(?i)\bUSD\b|\$', text):
        return "USD"
    if re.search(r'(?i)\bEUR\b|€', text):
        return "EUR"
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

    vendor = extract_vendor(text)
    amount = extract_amount(text)
    tax = extract_tax(text)
    currency = extract_currency(text)

    return {
        "invoice_no": invoice_no,
        "date": date,
        "vendor": vendor,
        "amount": amount,
        "tax": tax,
        "currency": currency
    }
