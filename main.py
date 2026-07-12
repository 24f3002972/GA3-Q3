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
    value = value.replace("Rs.", "").replace("Rs", "").replace(",", "").strip()
    try:
        return float(value)
    except:
        return None

def parse_date(value):
    if not value:
        return None
    try:
        return parser.parse(value, dayfirst=True).date().isoformat()
    except:
        return None
    
@app.post("/extract")
def extract_invoice(data: ExtractRequest):
    text = data.invoice_text

    invoice_no = None
    date = None
    vendor = None
    amount = None
    tax = None
    currency = "INR"

    m = re.search(r"(Invoice\s*No|Invoice\s*Number|Inv\s*No)[:\-]?\s*(.+)", text, re.IGNORECASE)
    if m:
        invoice_no = m.group(2).split("\n")[0].strip()

    m = re.search(r"Date[:\-]?\s*(.+)", text, re.IGNORECASE)
    if m:
        date = parse_date(m.group(1).split("\n")[0].strip())

    m = re.search(r"Vendor[:\-]?\s*(.+)", text, re.IGNORECASE)
    if m:
        vendor = m.group(1).split("\n")[0].strip()

    m = re.search(r"Subtotal[:\-]?\s*Rs\.?\s*([\d,]+\.\d{2})", text, re.IGNORECASE)
    if m:
        amount = parse_money(m.group(1))

    m = re.search(r"(GST|Tax|VAT).*?Rs\.?\s*([\d,]+\.\d{2})", text, re.IGNORECASE)
    if m:
        tax = parse_money(m.group(2))

    if "INR" in text or "Rs" in text or "₹" in text:
        currency = "INR"
    else:
        currency = None

    return {
        "invoice_no": invoice_no,
        "date": date,
        "vendor": vendor,
        "amount": amount,
        "tax": tax,
        "currency": currency
    }