import pdfplumber
import json
import time
import anthropic
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv
from datetime import datetime
from pathlib import Path
import os
import traceback

load_dotenv()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")

# Claude Sonnet 4.5 per-million-token pricing (Anthropic API, checked
# 2026-09-30 against https://platform.claude.com/docs/en/about-claude/pricing).
# Update these two numbers if pricing changes -- estimated_cost_usd below is
# only ever as accurate as they are.
INPUT_TOKEN_PRICE_PER_MTOK = 3.0
OUTPUT_TOKEN_PRICE_PER_MTOK = 15.0


# ─────────────────────────────────────────
# PDF EXTRACTION
# ─────────────────────────────────────────

def extract_text(pdf_path):
    """Extract text from a statement PDF, one page at a time.

    Statements almost always repeat the same header/footer on every page
    (bank name, account number, "Page X of Y", a customer-service line,
    sometimes a paragraph of legal boilerplate). pdfplumber pulls that out
    fresh on every page, so a 6-page statement pays for that same text 6
    times over once it's sent to the API. Below, a line that shows up
    identically on most pages is kept only the first time it appears --
    nothing about the actual transaction data is touched, since real
    transaction lines are unique to their page.
    """
    with pdfplumber.open(pdf_path) as pdf:
        pages_text = [page.extract_text() or "" for page in pdf.pages]

    if len(pages_text) > 2:
        line_counts = {}
        for page_text in pages_text:
            for line in set(page_text.splitlines()):
                stripped = line.strip()
                if stripped:
                    line_counts[stripped] = line_counts.get(stripped, 0) + 1
        repeated_threshold = max(2, int(len(pages_text) * 0.6))
        repeated_lines = {line for line, count in line_counts.items() if count >= repeated_threshold}
    else:
        repeated_lines = set()

    seen_once = set()
    output_lines = []
    for page_text in pages_text:
        for line in page_text.splitlines():
            stripped = line.strip()
            if stripped in repeated_lines:
                if stripped in seen_once:
                    continue
                seen_once.add(stripped)
            output_lines.append(line)
        output_lines.append("")

    return "\n".join(output_lines)


# ─────────────────────────────────────────
# AI PARSING
# ─────────────────────────────────────────

def parse_with_ai(raw_text):
    """Ask Claude to extract transactions as compact rows instead of a
    verbose JSON object per transaction. Repeating "date"/"merchant"/
    "category"/"amount"/"is_credit" as keys on every single transaction
    adds up fast on a statement with 50+ line items -- a plain
    [date, merchant, category, amount, is_credit] row carries the same
    information for a fraction of the output tokens (and therefore time).
    process_single_pdf() converts these rows back into the dict shape the
    rest of the pipeline already expects, so nothing downstream changes.

    Also times the API call and reads token usage off the response, so
    process_single_pdf() can record latency and estimated cost per file
    alongside the existing validation numbers. Returns (text, metrics)
    instead of just text.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    start = time.perf_counter()
    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": f"""
You are a financial data extractor.
Extract all transactions from this credit card statement and return only JSON.
Return ONLY raw JSON. No markdown. No backticks. No ```json. No explanation.
Your response must start with {{ and end with }}

Return STRICT JSON in this compact row format -- each transaction is a
4-element array, NOT an object, in exactly this order:
[date, merchant, category, amount, is_credit]

{{
    "statement_total": 0.00,
    "transactions": [
        ["YYYY-MM-DD", "cleaned merchant name", "category", 0.00, false]
    ]
}}
Rules:
- date format: YYYY-MM-DD
- merchant: cleaned name, remove codes/numbers/symbols
- category: Travel, Dining, Shopping, Grocery, Subscription, Transportation, Entertainment, Transfer, Misc
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
    latency_ms = round((time.perf_counter() - start) * 1000)

    input_tokens = message.usage.input_tokens
    output_tokens = message.usage.output_tokens
    estimated_cost_usd = round(
        (input_tokens / 1_000_000) * INPUT_TOKEN_PRICE_PER_MTOK
        + (output_tokens / 1_000_000) * OUTPUT_TOKEN_PRICE_PER_MTOK,
        6
    )

    metrics = {
        "latency_ms": latency_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": estimated_cost_usd,
    }
    return message.content[0].text, metrics


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

    # Validation index: a single 0-1 score combining row-level validity
    # (fraction of rows with no field errors) with control-total closeness
    # (how near extracted_total lands to the statement's own total). 1.0
    # means every row was well-formed and the control total matched
    # exactly. Unlike control_ok, this degrades smoothly instead of
    # flipping from "fine" to "not fine" at the $5 threshold, so it can
    # be tracked over time (e.g. average validation_index per week) to
    # notice extraction quality drifting before control_ok starts failing.
    row_validity = (len(valid) / len(transactions)) if transactions else 1.0
    if statement_total:
        total_closeness = max(0.0, 1 - (difference / abs(statement_total)))
    else:
        total_closeness = 1.0 if difference == 0 else 0.0
    validation_index = round(row_validity * total_closeness, 3)

    return valid, {
        "total": len(transactions),
        "valid": len(valid),
        "errors": len(errors),
        "extracted_total": round(extracted_total, 2),
        "statement_total": round(statement_total, 2),
        "difference": round(difference, 2),
        "control_ok": difference <= 5,
        "validation_index": validation_index
    }


# ─────────────────────────────────────────
# POSTGRES (SUPABASE) DATABASE
#
# Every function below accepts an optional `conn`. Pass a connection you
# already opened (e.g. once per upload batch) to avoid reopening the
# database per setup/dedup-check/save per file.
# ─────────────────────────────────────────

def get_connection():
    """Open a connection to the Postgres (Supabase) database."""
    if not SUPABASE_DB_URL:
        raise RuntimeError(
            "SUPABASE_DB_URL is not set. Add your Supabase connection string "
            "to .env before running the app."
        )
    return psycopg2.connect(SUPABASE_DB_URL)


def setup_database(conn=None):
    """Create tables in the database if they don't exist (idempotent)."""
    owns_conn = conn is None
    if owns_conn:
        conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS raw_transactions (
                id                SERIAL PRIMARY KEY,
                date              DATE,
                merchant          VARCHAR,
                category          VARCHAR,
                amount            DECIMAL(10,2),
                is_credit         BOOLEAN,
                source_file       VARCHAR,
                user_email        VARCHAR,
                created_at        TIMESTAMP DEFAULT NOW()
            )
        """)
        # self-heal a raw_transactions table that pre-dates multi-user
        # support (e.g. this project reused an older Supabase project
        # that still has the old household_member-only schema).
        # Added as nullable, never NOT NULL: ALTER TABLE ADD COLUMN
        # NOT NULL fails outright on a table that already has rows,
        # and save_to_database() already enforces user_email at the
        # application layer.
        cur.execute("""
            ALTER TABLE raw_transactions ADD COLUMN IF NOT EXISTS user_email VARCHAR
        """)

        # processed_files is just dedup bookkeeping, not real financial
        # data. If it predates multi-user support, its primary key needs
        # to move from file_name alone to (user_email, file_name), which
        # is simplest to do by recreating it -- worst case a couple of
        # already-processed files get reprocessed once.
        cur.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'processed_files' AND column_name = 'user_email'
        """)
        if cur.fetchone() is None:
            cur.execute("DROP TABLE IF EXISTS processed_files")

        # dedup is scoped per-user: two different people uploading a file
        # with the same name (e.g. "statement.pdf") must not collide
        cur.execute("""
            CREATE TABLE IF NOT EXISTS processed_files (
                user_email        VARCHAR NOT NULL,
                file_name         VARCHAR NOT NULL,
                processed_at      TIMESTAMP,
                transaction_count INTEGER,
                PRIMARY KEY (user_email, file_name)
            )
        """)
        # per-file processing metrics (latency/cost/validation_index),
        # added after the fact -- nullable and self-heal like user_email
        # above, so older rows just show NULL instead of breaking anything.
        # Lets "is extraction getting slower / costlier / less accurate
        # over time" be answered by querying processed_files directly.
        cur.execute("""
            ALTER TABLE processed_files ADD COLUMN IF NOT EXISTS latency_ms INTEGER
        """)
        cur.execute("""
            ALTER TABLE processed_files ADD COLUMN IF NOT EXISTS input_tokens INTEGER
        """)
        cur.execute("""
            ALTER TABLE processed_files ADD COLUMN IF NOT EXISTS output_tokens INTEGER
        """)
        cur.execute("""
            ALTER TABLE processed_files ADD COLUMN IF NOT EXISTS estimated_cost_usd DECIMAL(10,6)
        """)
        cur.execute("""
            ALTER TABLE processed_files ADD COLUMN IF NOT EXISTS validation_index DECIMAL(4,3)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_raw_transactions_user_date
            ON raw_transactions (user_email, date)
        """)
        conn.commit()
    finally:
        if owns_conn:
            conn.close()


def is_already_processed(file_name, user_email, conn=None):
    owns_conn = conn is None
    if owns_conn:
        conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM processed_files WHERE file_name = %s AND user_email = %s",
            (file_name, user_email),
        )
        count = cur.fetchone()[0]
        return count > 0
    finally:
        if owns_conn:
            conn.close()


def save_to_database(transactions, file_name, user_email, conn=None, metrics=None, validation_index=None):
    """Save transactions to the database in a single bulk INSERT.

    `metrics` (latency_ms/input_tokens/output_tokens/estimated_cost_usd,
    from parse_with_ai) and `validation_index` (from validate_transactions)
    are optional so a file that never reached the API (e.g. dedup-skipped)
    doesn't need to fake them.
    """
    if not user_email:
        raise ValueError("user_email is required -- transactions must be tied to a signed-in user")
    metrics = metrics or {}

    owns_conn = conn is None
    if owns_conn:
        conn = get_connection()
    try:
        cur = conn.cursor()

        rows = [
            (
                t["date"], t["merchant"], t["category"], float(t["amount"]),
                bool(t.get("is_credit", False)), file_name, user_email
            )
            for t in transactions
        ]

        if rows:
            execute_values(
                cur,
                """
                INSERT INTO raw_transactions
                    (date, merchant, category, amount, is_credit, source_file, user_email)
                VALUES %s
                """,
                rows
            )

        cur.execute(
            """
            INSERT INTO processed_files
                (user_email, file_name, processed_at, transaction_count,
                 latency_ms, input_tokens, output_tokens, estimated_cost_usd, validation_index)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_email, file_name) DO NOTHING
            """,
            (
                user_email, file_name, datetime.now(), len(transactions),
                metrics.get("latency_ms"), metrics.get("input_tokens"),
                metrics.get("output_tokens"), metrics.get("estimated_cost_usd"),
                validation_index
            )
        )

        conn.commit()
        return True, "saved"
    finally:
        if owns_conn:
            conn.close()


# ─────────────────────────────────────────
# MAIN PROCESSING FUNCTION
# ─────────────────────────────────────────

def _rows_to_transactions(rows):
    """Convert parse_with_ai()'s compact [date, merchant, category, amount,
    is_credit] rows back into the dict shape validate_transactions() and
    save_to_database() expect. Isolated here so the compact-wire-format
    optimization doesn't leak into the rest of the pipeline. Tolerates a
    short row (missing is_credit) or a stray dict (in case the model
    reverts to the old shape) rather than crashing the whole batch.
    """
    transactions = []
    for row in rows:
        if isinstance(row, dict):
            transactions.append(row)
            continue
        date, merchant, category, amount = (list(row) + [None] * 4)[:4]
        is_credit = row[4] if len(row) > 4 else False
        transactions.append({
            "date": date,
            "merchant": merchant,
            "category": category,
            "amount": amount,
            "is_credit": is_credit,
        })
    return transactions


def process_single_pdf(pdf_path, user_email, conn=None):
    """
    Process one PDF — extract, parse, validate, save.

    `user_email` (the signed-in user's Google account) scopes both the
    dedup check and the saved rows, so different users' files never
    collide or leak into each other's data. Pass `conn` (an open
    connection) when processing a batch of files so setup/dedup-check/save
    all reuse one connection instead of reopening the database per file.
    """
    file_name = Path(pdf_path).name
    owns_conn = conn is None

    try:
        if owns_conn:
            conn = get_connection()
            setup_database(conn)

        # check before API call to save cost
        if is_already_processed(file_name, user_email, conn):
            return {
                "file": file_name,
                "success": True,
                "already_processed": True,
                "summary": None
            }

        raw = extract_text(pdf_path)
        parsed_data, api_metrics = parse_with_ai(raw)
        results = json.loads(parsed_data)

        statement_total = results["statement_total"]
        transactions = _rows_to_transactions(results["transactions"])

        validated, summary = validate_transactions(transactions, statement_total)
        summary.update(api_metrics)  # latency_ms, input_tokens, output_tokens, estimated_cost_usd
        save_to_database(
            validated, file_name, user_email, conn,
            metrics=api_metrics, validation_index=summary["validation_index"]
        )

        return {
            "file": file_name,
            "success": True,
            "already_processed": False,
            "summary": summary
        }

    except json.JSONDecodeError as e:
        if conn is not None:
            conn.rollback()
        return {"file": file_name, "success": False, "error": f"JSON parsing failed: {e}"}
    except Exception as e:
        traceback.print_exc()
        if conn is not None:
            conn.rollback()
        return {"file": file_name, "success": False, "error": str(e)}
    finally:
        if owns_conn and conn is not None:
            conn.close()


# only runs when called directly
if __name__ == "__main__":
    setup_database()
    print("Database ready (Supabase/Postgres).")
