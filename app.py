import streamlit as st
from dotenv import load_dotenv
import os
import tempfile
from pathlib import Path
import sys
import psycopg2
import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))
from extract import process_single_pdf, setup_database

load_dotenv()

SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")

# --- Page Config ---
st.set_page_config(
    page_title="CC Statement Analyzer",
    page_icon="💳",
    layout="wide"
)

# --- Header ---
st.title("💳 Credit Card Statement Analyzer")
st.markdown("Upload your credit card statements and get instant spending insights.")
st.divider()

# --- File Uploader ---
st.subheader("📄 Step 1 — Upload PDF Statements")
uploaded_files = st.file_uploader(
    "Drag and drop your statements here",
    type=["pdf"],
    accept_multiple_files=True,
    help="You can upload multiple months at once"
)

if uploaded_files:
    st.write(f"**{len(uploaded_files)} file(s) ready to process:**")
    for f in uploaded_files:
        st.write(f"- {f.name}")

st.divider()

# --- Process Button ---
st.subheader("🚀 Step 2 — Analyze")

if st.button("Process Statements", disabled=not uploaded_files, type="primary"):

    with tempfile.TemporaryDirectory() as tmp_dir:

        pdf_paths = []
        for uploaded_file in uploaded_files:
            tmp_path = os.path.join(tmp_dir, uploaded_file.name)
            with open(tmp_path, "wb") as f:
                f.write(uploaded_file.read())
            pdf_paths.append(tmp_path)

        st.write(f"**Processing {len(pdf_paths)} file(s)...**")
        progress_bar = st.progress(0)
        status_container = st.empty()
        results_list = []

        for i, pdf_path in enumerate(pdf_paths):
            file_name = Path(pdf_path).name
            status_container.info(f"⏳ Processing {i+1} of {len(pdf_paths)}: **{file_name}**")

            result = process_single_pdf(pdf_path)
            results_list.append(result)
            progress_bar.progress((i + 1) / len(pdf_paths))

        status_container.empty()
        st.divider()

        st.subheader("📊 Processing Results")

        for result in results_list:
            if result.get("already_processed"):
                st.warning(f"⏭️ **{result['file']}** — already processed, skipped")
            elif not result.get("success"):
                st.error(f"❌ **{result['file']}** — {result.get('error', 'Unknown error')}")
            else:
                s = result.get("summary") or {}
                with st.expander(f"✅ {result['file']} — {s.get('valid', 0)} transactions extracted", expanded=True):
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Transactions", s.get("valid", 0))
                    col2.metric("Extracted Total", f"${s.get('extracted_total', 0):,.2f}")
                    col3.metric("Statement Total", f"${s.get('statement_total', 0):,.2f}")
                    diff = s.get("difference", 0)
                    if s.get("control_ok", True):
                        st.success(f"✅ Control total matches (difference: ${diff:.2f})")
                    else:
                        st.warning(f"⚠️ Difference of ${diff:.2f} — review recommended")

        total_success = sum(1 for r in results_list if r.get("success") and not r.get("already_processed"))
        st.success(f"✅ Done! {total_success} of {len(pdf_paths)} file(s) processed successfully.")

st.divider()

# --- Step 3: View Data ---
st.subheader("📂 Step 3 — View Your Data")


def load_data():
    """Load transactions from Supabase into pandas dataframe"""
    try:
        conn = psycopg2.connect(SUPABASE_DB_URL)
        df = pd.read_sql("""
            SELECT
                date,
                merchant,
                category,
                amount,
                is_credit,
                source_file
            FROM raw_transactions
            ORDER BY date DESC
        """, conn)
        conn.close()
        return df
    except Exception as e:
        st.error(f"Database connection error: {e}")
        return None


df = load_data()

if df is None or df.empty:
    st.info("No data yet — upload and process a statement above to get started.")
else:
    # --- Summary Metrics ---
    total_spend = df[df["is_credit"] == False]["amount"].sum()
    total_transactions = len(df)
    months_loaded = pd.to_datetime(df["date"]).dt.to_period("M").nunique()
    files_loaded = df["source_file"].nunique()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("💰 Total Spend", f"${total_spend:,.2f}")
    col2.metric("🧾 Transactions", total_transactions)
    col3.metric("📅 Months", months_loaded)
    col4.metric("📄 Statements", files_loaded)

    st.divider()

    # --- Filters ---
    st.markdown("**Filter transactions:**")
    col1, col2, col3 = st.columns(3)

    with col1:
        categories = ["All"] + sorted(df["category"].dropna().unique().tolist())
        selected_category = st.selectbox("Category", categories)

    with col2:
        txn_type = st.selectbox("Type", ["All", "Debits only", "Credits only"])

    with col3:
        files = ["All"] + sorted(df["source_file"].dropna().unique().tolist())
        selected_file = st.selectbox("Statement", files)

    # apply filters
    filtered_df = df.copy()
    if selected_category != "All":
        filtered_df = filtered_df[filtered_df["category"] == selected_category]
    if txn_type == "Debits only":
        filtered_df = filtered_df[filtered_df["is_credit"] == False]
    elif txn_type == "Credits only":
        filtered_df = filtered_df[filtered_df["is_credit"] == True]
    if selected_file != "All":
        filtered_df = filtered_df[filtered_df["source_file"] == selected_file]

    st.markdown(f"**{len(filtered_df)} transactions**")

    # --- Transactions Table ---
    st.dataframe(
        filtered_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "date": st.column_config.DateColumn("Date"),
            "merchant": "Merchant",
            "category": "Category",
            "amount": st.column_config.NumberColumn("Amount", format="$%.2f"),
            "is_credit": st.column_config.CheckboxColumn("Credit?"),
            "source_file": "Statement"
        }
    )

    # --- Download ---
    csv = filtered_df.to_csv(index=False)
    st.download_button(
        label="⬇️ Download as CSV",
        data=csv,
        file_name="transactions.csv",
        mime="text/csv"
    )
tab1, tab2, tab3 = st.tabs(["Overview","Transactions","Anomalies"]) 
with tab1:
    st.write("Overview")   
with tab2:
    st.write("Overview")   
with tab3:
    st.write("Overview")   