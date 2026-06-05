import pdfplumber
import json
import anthropic
import duckdb
import psycopg2
from dotenv import load_dotenv
from datetime import datetime
from pathlib import Path
import os
import traceback

load_dotenv()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")


# ─────────────────────────────────────────
# PDF EXTRACTION
# ─────────────────────────────────────────

def extract_text(pdf_path):
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text


# ─────────────────────────────────────────
# AI PARSING
# ─────────────────────────────────────────

def parse_with_ai(raw_text):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": f"""
You are a financial data extractor.
Extract all transactions from this credit card statement and return only a JSON array.
Return ONLY raw JSON. No markdown. No backticks. No ```json. No explanation.
Your response must start with {{ and end with }}

Return STRICT JSON:
{{
    "statement_total": 0.00,
    "transactions": [
        {{
            "date": "YYYY-MM-DD",
            "merchant": "cleaned merchant name",
            "category": "category",
            "amount": 0.00,
            "is_credit": false
        }}
    ]
}}
Rules:
- date format: YYYY-MM-DD
- merchant: cleaned name, remove codes/numbers/symbols
- category: Travel, Dining, Shopping, Subscription, Transportation, Healthcare, Entertainment, Transfer
- amount: positive number, USD only
- If foreign currency, use USD amount
- Remove duplicates
- Ignore headers, footers, summaries, interest sections
- statement_total is total new charges from summary section

Statement text:
{raw_text}
"""
        }]
    )
    return message.content[0].text


# ─────────────────────────────────────────
# VALIDATION
# ─────────────────────────────────────────

def validate_transactions(transactions, statement_total):
    errors = []
    valid = []

    for i, t in enumerate(transactions):
        row_errors = {}

        if not t.get("date"):
            row_errors["date"] = {"issue": "missing", "value": None}
        if not t.get("merchant"):
            row_errors["merchant"] = {"issue": "missing", "value": None}
        if not t.get("amount"):
            row_errors["amount"] = {"issue": "missing", "value": None}

        if t.get("amount"):
            try:
                float(t["amount"])
            except (ValueError, TypeError):
                row_errors["amount"] = {"issue": "not a number", "value": t.get("amount")}

        if t.get("date"):
            try:
                datetime.strptime(t["date"], "%Y-%m-%d")
            except:
                row_errors["date"] = {"issue": "wrong format", "value": t.get("date")}

        if row_errors:
            errors.append({"transaction_index": i, "transaction": t, "field_errors": row_errors})
        else:
            valid.append(t)

    extracted_total = sum(float(t["amount"]) for t in valid if not t.get("is_credit"))
    difference = abs(extracted_total - statement_total)

    return valid, {
        "total": len(transactions),
        "valid": len(valid),
        "errors": len(errors),
        "extracted_total": round(extracted_total, 2),
        "statement_total": round(statement_total, 2),
        "difference": round(difference, 2),
        "control_ok": difference <= 5
    }


# ─────────────────────────────────────────
# SUPABASE DATABASE
# ─────────────────────────────────────────

def get_connection():
    """Get a Supabase PostgreSQL connection"""
    return psycopg2.connect(SUPABASE_DB_URL)


def setup_database():
    """Create tables in Supabase if they don't exist"""
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS raw_transactions (
            id          SERIAL PRIMARY KEY,
            date        DATE,
            merchant    VARCHAR,
            category    VARCHAR,
            amount      DECIMAL(10,2),
            is_credit   BOOLEAN,
            source_file VARCHAR,
            created_at  TIMESTAMP DEFAULT NOW()
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS processed_files (
            file_name         VARCHAR PRIMARY KEY,
            processed_at      TIMESTAMP,
            transaction_count INTEGER
        )
    """)

    conn.commit()
    cur.close()
    conn.close()


def is_already_processed(file_name):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM processed_files WHERE file_name = %s", (file_name,))
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    return count > 0


def save_to_database(transactions, file_name):
    """Save transactions to Supabase"""
    conn = get_connection()
    cur = conn.cursor()

    for t in transactions:
        cur.execute(
            """
            INSERT INTO raw_transactions (date, merchant, category, amount, is_credit, source_file)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            [t["date"], t["merchant"], t["category"],
             t["amount"], t.get("is_credit", False), file_name]
        )

    cur.execute(
        """
        INSERT INTO processed_files (file_name, processed_at, transaction_count)
        VALUES (%s, %s, %s)
        ON CONFLICT (file_name) DO NOTHING
        """,
        [file_name, datetime.now(), len(transactions)]
    )

    conn.commit()
    cur.close()
    conn.close()
    return True, "saved"


# ─────────────────────────────────────────
# MAIN PROCESSING FUNCTION
# ─────────────────────────────────────────

def process_single_pdf(pdf_path, db_path=None):
    """
    Process one PDF — extract, parse, validate, save to Supabase.
    db_path kept as optional arg for backwards compatibility.
    """
    file_name = Path(pdf_path).name

    try:
        # check before API call to save cost
        setup_database()
        if is_already_processed(file_name):
            return {
                "file": file_name,
                "success": True,
                "already_processed": True,
                "summary": None
            }

        raw = extract_text(pdf_path)
        parsed_data = parse_with_ai(raw)
        results = json.loads(parsed_data)

        statement_total = results["statement_total"]
        transactions = results["transactions"]

        validated, summary = validate_transactions(transactions, statement_total)
        save_to_database(validated, file_name)

        return {
            "file": file_name,
            "success": True,
            "already_processed": False,
            "summary": summary
        }

    except json.JSONDecodeError as e:
        return {"file": file_name, "success": False, "error": f"JSON parsing failed: {e}"}
    except Exception as e:
        traceback.print_exc()
        return {"file": file_name, "success": False, "error": str(e)}


# only runs when called directly
if __name__ == "__main__":
    setup_database()
    print("Database setup complete")