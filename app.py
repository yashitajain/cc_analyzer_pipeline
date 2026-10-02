import streamlit as st
from dotenv import load_dotenv
import os
import tempfile
from pathlib import Path
from datetime import date
import sys
import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))
from extract import process_single_pdf, setup_database, get_connection
from analytics import load_raw_transactions, clean_transactions, monthly_summary, category_spend, detect_anomalies, member_spend
from household import setup_household_tables, ensure_household, invite_member, list_household_members
from notifications import send_household_invite_email
from budgets import (
    setup_budgets_table, get_budget_for_month, save_budget,
    DEFAULT_FIXED_COSTS, DEFAULT_CATEGORY_BUDGETS,
)
from theme import inject_custom_theme

load_dotenv()

# make sure the local database file and its tables exist before anything
# tries to query them (first run on a fresh checkout has neither yet)
setup_database()


def _ensure_household_schema():
    conn = get_connection()
    try:
        setup_household_tables(conn)
    finally:
        conn.close()


def _ensure_budgets_schema():
    conn = get_connection()
    try:
        setup_budgets_table(conn)
    finally:
        conn.close()


_ensure_household_schema()
_ensure_budgets_schema()

# --- Page Config ---
st.set_page_config(
    page_title="CC Statement Analyzer",
    page_icon="💳",
    layout="wide"
)
inject_custom_theme()

# --- Auth gate ---
# Streamlit's built-in Google login (configured in .streamlit/secrets.toml).
# Nothing below this point ever runs for a signed-out visitor, and every
# query below is scoped to st.user.email so one person's statements can
# never show up for another (except where a household member has
# explicitly invited someone else in, see below).
if not st.user.is_logged_in:
    st.title("💳 Credit Card Statement Analyzer")
    st.markdown("Upload your credit card statements and get instant spending insights.")
    st.caption("Sign in to get started — your data is private to your account.")
    st.divider()
    st.button("Log in with Google", on_click=st.login, type="primary")
    st.stop()

user_email = st.user.email
user_name = getattr(st.user, "name", None) or user_email

# --- Household ---
# Every signed-in user belongs to exactly one household (a household-of-one
# until they invite someone). This is what lets a partner's uploads show up
# alongside your own in a combined "Household Spend" view, while your own
# uploads always stay tied to your own email underneath.
_household_conn = get_connection()
try:
    household_id = ensure_household(_household_conn, user_email)
    household_members = list_household_members(_household_conn, household_id)
finally:
    _household_conn.close()

active_emails = [m["email"] for m in household_members if m["joined"]]
has_household = len(active_emails) > 1

# --- Header ---
header_col1, header_col2 = st.columns([5, 1])
with header_col1:
    st.title("💳 Credit Card Statement Analyzer")
    st.markdown("Upload your credit card statements and get instant spending insights.")
with header_col2:
    st.caption(f"Signed in as **{user_name}**")
    st.button("Log out", on_click=st.logout)
st.divider()

# --- Household management ---
with st.expander("👪 Household", expanded=False):
    st.caption("Invite your partner so you can see your individual spending and your combined household spending side by side.")
    for m in household_members:
        label = "You" if m["email"] == user_email else m["email"]
        status = "✅ Active" if m["joined"] else "⏳ Invited — will join once they sign in with Google"
        st.write(f"- **{label}** — {status}")

    st.divider()
    invite_col1, invite_col2 = st.columns([4, 1])
    with invite_col1:
        invite_email = st.text_input(
            "Partner's Google email",
            key="invite_email",
            label_visibility="collapsed",
            placeholder="partner@gmail.com"
        )
    with invite_col2:
        if st.button("Invite", use_container_width=True):
            invitee_email = (invite_email or "").strip().lower()
            conn = get_connection()
            try:
                ok, msg = invite_member(conn, household_id, user_email, invitee_email)
            finally:
                conn.close()
            if ok:
                st.success(msg)
                sent, email_msg = send_household_invite_email(user_name, user_email, invitee_email)
                if sent:
                    st.caption(f"📧 {email_msg}")
                else:
                    st.warning(email_msg)
                st.rerun()
            else:
                st.error(msg)

# --- View toggle: individual vs household ---
if has_household:
    view_mode = st.radio(
        "View",
        ["My Spend", "Household Spend"],
        horizontal=True,
        key="view_mode"
    )
else:
    view_mode = "My Spend"

selected_emails = tuple(sorted(active_emails)) if view_mode == "Household Spend" else (user_email,)

st.divider()


# --- Data loaders ---
# Everything here reads from the database, scoped to whichever emails the
# view toggle selects. Cached for a few minutes so dragging a slider or
# switching tabs doesn't requery and recompute aggregates on every rerun.
# selected_emails is always passed as an argument (not read from st.user
# or session state inside the function) because Streamlit's cache key is
# derived from the arguments -- leaving it out would let one view's cached
# results leak into another's.

@st.cache_data(ttl=300, show_spinner=False)
def load_data(user_emails):
    """Load raw transactions for the given emails into a pandas dataframe"""
    try:
        conn = get_connection()
        df = load_raw_transactions(conn, user_emails)
        conn.close()
        return df
    except Exception as e:
        st.error(f"Database error: {e}")
        return None


@st.cache_data(ttl=300, show_spinner=False)
def load_clean_transactions(user_emails):
    """These transactions run through the same cleaning rules as the old dbt models."""
    conn = get_connection()
    raw = load_raw_transactions(conn, user_emails)
    conn.close()
    return clean_transactions(raw)


def render_processing_results(results_list):
    """Render the per-file outcome of an upload batch: extraction counts,
    the control-total check, and model latency/cost/validation index.

    Pulled out into its own function so it can be called from the "last
    upload" banner in the tabs view (see below) instead of only inline in
    the Process Statements button handler -- st.rerun() right after
    processing replaces the whole script output immediately, so anything
    drawn only in that handler never actually reaches the screen.
    """
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

                col4, col5, col6 = st.columns(3)
                latency_ms = s.get("latency_ms")
                col4.metric("Model Latency", f"{latency_ms / 1000:.1f}s" if latency_ms is not None else "—")
                cost = s.get("estimated_cost_usd")
                col5.metric("Est. Cost", f"${cost:.4f}" if cost is not None else "—")
                validation_index = s.get("validation_index")
                col6.metric("Validation Index", f"{validation_index:.2f}" if validation_index is not None else "—")

                diff = s.get("difference", 0)
                if s.get("control_ok", True):
                    st.success(f"✅ Control total matches (difference: ${diff:.2f})")
                else:
                    st.warning(f"⚠️ Difference of ${diff:.2f} — review recommended")


df = load_data(selected_emails)
if "analyzed" not in st.session_state:
    # Returning users who already have data land straight on the
    # tabs instead of the upload screen. Without this, a fresh
    # browser session always starts with analyzed = False (session
    # state is per-session, not per-account), so previously
    # uploaded statements looked "missing" even though df already
    # has them -- the summary tiles showed real numbers, but the
    # tabs never appeared. "Upload more" still flips this back to
    # False so uploading again works the same as before.
    st.session_state.analyzed = df is not None and not df.empty

if not st.session_state.analyzed:
    st.subheader("📄 Step 1 — Upload PDF Statements")

    uploaded_files = st.file_uploader(
        "Drag and drop statements here",
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

    ready = bool(uploaded_files)

    if st.button("Process Statements", disabled=not ready, type="primary"):

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

            # one shared connection for the whole batch instead of reopening
            # the database per setup/dedup-check/save per file
            batch_conn = get_connection()
            setup_database(batch_conn)
            try:
                for i, pdf_path in enumerate(pdf_paths):
                    file_name = Path(pdf_path).name
                    status_container.info(f"⏳ Processing {i+1} of {len(pdf_paths)}: **{file_name}**")

                    # always tied to the actual signed-in user, regardless of
                    # which view (My Spend / Household Spend) is selected --
                    # you can only ever upload statements as yourself
                    result = process_single_pdf(pdf_path, user_email=user_email, conn=batch_conn)
                    results_list.append(result)
                    progress_bar.progress((i + 1) / len(pdf_paths))
            finally:
                batch_conn.close()

            status_container.empty()

            total_success = sum(1 for r in results_list if r.get("success") and not r.get("already_processed"))
            if total_success:
                st.cache_data.clear()  # new rows exist now -- drop cached query results

            # Stash results instead of rendering them here: st.rerun() below
            # fires immediately and replaces this whole run's output with
            # the tabs view before anything drawn in this handler ever
            # reaches the browser -- that's why the Processing Results
            # section (and everyone's latency/cost/validation index) never
            # actually showed up. The tabs view renders this from
            # session_state instead, where it sticks around until dismissed.
            st.session_state.last_upload_results = {
                "results_list": results_list,
                "total_success": total_success,
                "total_files": len(pdf_paths),
            }
            st.session_state.analyzed = True
            st.rerun()
    st.divider()

    # --- Step 3: View Data ---
    st.subheader("📂 Step 3 — View Your Data")

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
else:
    col1, col2 = st.columns([6, 1])
    with col2:
        if st.button("Upload more"):
            st.session_state.analyzed = False
            st.session_state.pop("last_upload_results", None)
            st.rerun()

    last_upload = st.session_state.get("last_upload_results")
    if last_upload:
        st.subheader("📊 Processing Results")
        render_processing_results(last_upload["results_list"])
        st.success(
            f"✅ Done! {last_upload['total_success']} of {last_upload['total_files']} "
            "file(s) processed successfully."
        )
        if st.button("Dismiss"):
            st.session_state.pop("last_upload_results", None)
            st.rerun()
        st.divider()

    # Vertical section nav in the sidebar instead of horizontal tabs --
    # easier to scan with six sections, and leaves more horizontal room
    # for tables/charts in the main area. active_section persists across
    # reruns via its widget key, so switching My Spend/Household Spend or
    # saving a budget doesn't reset which section you're looking at.
    SECTIONS = ["Overview", "Category", "Anomalies", "Budget Tracker", "Transactions", "Ask AI"]
    with st.sidebar:
        st.markdown("#### Sections")
        section = st.radio("Go to", SECTIONS, key="active_section", label_visibility="collapsed")

    # Shared across sections (Category's own view, and Budget Tracker's
    # month selector + variable-cost comparison) -- computed once here so
    # it exists no matter which single section below actually runs.
    category_df = category_spend(load_clean_transactions(selected_emails))

    if section == "Overview":
        # monthly summary, computed locally from the cleaned transactions
        summary_df = monthly_summary(load_clean_transactions(selected_emails))

        if summary_df.empty:
            st.info("No data yet — upload a statement first.")
        else:
            # --- top metrics from most recent month ---
            latest = summary_df.iloc[-1]

            st.markdown("#### Most Recent Month")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("💰 Total Spend",    f"${latest['total_spend']:,.2f}")
            col2.metric("🧾 Transactions",   int(latest['total_transactions']))
            col3.metric("📈 vs Last Month",  f"${latest['mom_spend_change']:,.2f}" if pd.notna(latest['mom_spend_change']) else "N/A")
            col4.metric("💳 Largest Charge", f"${latest['largest_transactions']:,.2f}")

            st.divider()

            # --- monthly spend trend line chart ---
            st.markdown("#### Monthly Spend Trend")
            st.line_chart(
                summary_df.set_index("transaction_month")["total_spend"],
                use_container_width=True
            )

            # --- per-member breakdown, only meaningful in Household Spend view ---
            if view_mode == "Household Spend" and has_household:
                member_df = member_spend(load_clean_transactions(selected_emails))
                if not member_df.empty:
                    st.divider()
                    st.markdown("#### Who Spent What (Most Recent Month)")
                    latest_month = member_df["transaction_month"].max()
                    month_breakdown = member_df[member_df["transaction_month"] == latest_month]

                    member_cols = st.columns(len(month_breakdown) + 1)
                    for i, (_, row) in enumerate(month_breakdown.iterrows()):
                        label = "You" if row["user_email"] == user_email else row["user_email"]
                        member_cols[i].metric(label, f"${row['total_spend']:,.2f}")
                    member_cols[-1].metric("Household Total", f"${month_breakdown['total_spend'].sum():,.2f}")
    elif section == "Category":
        # --- spending by category ---
        st.markdown("#### Spending by Category")

        if category_df.empty:
            st.info("No data yet — upload a statement first.")
        else:
            # month filter
            months = sorted(category_df["transaction_month"].unique(), reverse=True)
            selected_month = st.selectbox(
                "Select month",
                months,
                format_func=lambda x: str(x)[:7]
            )

            month_df = category_df[category_df["transaction_month"] == selected_month]

            col1, col2 = st.columns(2)

            with col1:
                # bar chart
                st.bar_chart(
                    month_df.set_index("category_name")["total_spend"],
                    use_container_width=True
                )

            with col2:
                # category breakdown table
                st.dataframe(
                    month_df[["category_name", "total_spend", "transaction_count", "pct_monthly_spend"]],
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "category_name": "Category",
                        "total_spend": st.column_config.NumberColumn("Total Spend", format="$%.2f"),
                        "transaction_count": "# Transactions",
                        "pct_monthly_spend": st.column_config.NumberColumn("% of Month", format="%.1f%%")
                    }
                )
    elif section == "Anomalies":
        anomaly_df = detect_anomalies(load_clean_transactions(selected_emails))
        if not anomaly_df.empty:
            anomaly_df = anomaly_df[[
                "transaction_date", "merchant_name", "category_name",
                "amount", "z_score", "anomaly_flag", "anomaly_reason"
            ]]

        if anomaly_df.empty:
            st.info("No data yet — upload a statement first.")
        else:
            # summary metrics
            total_flagged = anomaly_df["anomaly_flag"].sum()
            total_transactions = len(anomaly_df)

            col1, col2 = st.columns(2)
            col1.metric("🚨 Flagged Transactions", int(total_flagged))
            col2.metric("✅ Normal Transactions", int(total_transactions - total_flagged))

            st.divider()

            # flagged only toggle
            show_flagged = st.toggle("Show flagged only", value=True)

            if show_flagged:
                display_df = anomaly_df[anomaly_df["anomaly_flag"] == True]
            else:
                display_df = anomaly_df

            st.markdown(f"**{len(display_df)} transactions**")

            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "transaction_date": st.column_config.DateColumn("Date"),
                    "merchant_name": "Merchant",
                    "category_name": "Category",
                    "amount": st.column_config.NumberColumn("Amount", format="$%.2f"),
                    "z_score": st.column_config.NumberColumn("Z-Score", format="%.2f"),
                    "anomaly_flag": st.column_config.CheckboxColumn("Flagged?"),
                    "anomaly_reason": "Reason"
                }
            )
    elif section == "Budget Tracker":
        st.markdown("#### 💼 Financial Planner")

        # --- month selector ---
        # Always includes the current calendar month even if no statements
        # have landed for it yet, so a budget can be set up in advance
        # instead of only being plannable retroactively once transactions
        # exist.
        current_month = pd.Timestamp(date.today().replace(day=1))
        available_months = category_df["transaction_month"].unique().tolist() if not category_df.empty else []
        if current_month not in available_months:
            available_months.append(current_month)
        months = sorted(available_months, reverse=True)

        selected_plan_month = st.selectbox(
            "Select month to plan",
            months,
            format_func=lambda x: str(x)[:7],
            key="plan_month"
        )
        plan_month_df = (
            category_df[category_df["transaction_month"] == selected_plan_month]
            if not category_df.empty
            else pd.DataFrame(columns=["category_name", "total_spend", "transaction_count"])
        )
        month_key = selected_plan_month.strftime("%Y-%m")

        # --- Load this month's saved budget (or the most recent prior
        # month's, if this one hasn't been saved yet) ---
        # Before this, every field below was a plain widget with a
        # hardcoded default -- a budget tracker that forgets your budget
        # every session isn't really tracking anything. Keys are scoped to
        # month_key so switching months actually refreshes every field to
        # that month's numbers instead of Streamlit keeping whatever value
        # was last typed into a same-named widget.
        _budget_conn = get_connection()
        try:
            saved_budget = get_budget_for_month(_budget_conn, user_email, selected_plan_month)
        finally:
            _budget_conn.close()

        if saved_budget:
            fixed_defaults = saved_budget["fixed_costs"]
            category_defaults = saved_budget["category_budgets"] or DEFAULT_CATEGORY_BUDGETS
            if saved_budget["is_carried_forward"]:
                st.caption(
                    f"📎 No budget saved yet for {month_key} — showing your numbers from "
                    f"{saved_budget['source_month'].strftime('%Y-%m')}. Adjust below and save "
                    "to lock in this month's own budget."
                )
            else:
                st.caption(f"✅ Showing your saved budget for {month_key}.")
        else:
            fixed_defaults = DEFAULT_FIXED_COSTS
            category_defaults = DEFAULT_CATEGORY_BUDGETS
            st.caption("No budget saved yet — starting from defaults below. Adjust and save to make them yours.")

        st.divider()

        # Seed widget state from the loaded budget, exactly once per month
        # per browser session. Without this, `value=` below is silently
        # ignored on every rerun after the first time this month's widgets
        # were created, so switching away and back (or just another rerun)
        # would keep showing whatever was on screen the first time this
        # month was opened -- hardcoded defaults if nothing was saved yet
        # at that moment -- instead of what get_budget_for_month() loads.
        budget_init_flag = f"_budget_loaded_{month_key}"
        if budget_init_flag not in st.session_state:
            st.session_state[f"salary_{month_key}"] = int(fixed_defaults["monthly_salary"])
            st.session_state[f"mortgage_{month_key}"] = int(fixed_defaults["mortgage"])
            st.session_state[f"utilities_{month_key}"] = int(fixed_defaults["utilities"])
            st.session_state[f"insurance_{month_key}"] = int(fixed_defaults["insurance"])
            st.session_state[f"daycare_{month_key}"] = int(fixed_defaults["daycare"])
            st.session_state[f"subs_fixed_{month_key}"] = int(fixed_defaults["subscriptions_fixed"])
            st.session_state[f"other_fixed_{month_key}"] = int(fixed_defaults["other_fixed"])
            for category, default in DEFAULT_CATEGORY_BUDGETS.items():
                st.session_state[f"budget_{category}_{month_key}"] = int(category_defaults.get(category, default))
            st.session_state[budget_init_flag] = True

        # --- Income, Fixed Costs & Budget Targets (one form) ---
        # Everything you type/drag here is wrapped in a single st.form, so
        # Streamlit does NOT rerun the script (and therefore does not
        # recompute Monthly Summary / Budget vs Actual below) on every
        # keystroke or slider drag -- only once "Save this month's budget"
        # is pressed. The button sits right after these inputs, before the
        # Variable Costs section, so saving doesn't require scrolling past
        # your own actual spending first.
        with st.form(key=f"budget_form_{month_key}"):
            st.markdown("#### 💰 Income & Fixed Costs")
            col1, col2 = st.columns(2)

            with col1:
                monthly_salary = st.number_input(
                    "Monthly Salary (after tax)",
                    min_value=0,
                    step=100,
                    format="%d",
                    key=f"salary_{month_key}"
                )

            st.markdown("**Fixed Monthly Costs:**")
            col1, col2 = st.columns(2)

            with col1:
                mortgage = st.number_input("🏠 Mortgage / Rent", min_value=0, step=50, key=f"mortgage_{month_key}")
                utilities = st.number_input("💡 Utilities", min_value=0, step=10, key=f"utilities_{month_key}")
                insurance = st.number_input("🛡️ Insurance", min_value=0, step=10, key=f"insurance_{month_key}")

            with col2:
                daycare = st.number_input("👶 Daycare", min_value=0, step=50, key=f"daycare_{month_key}")
                subscriptions_fixed = st.number_input("📱 Phone / Internet", min_value=0, step=10, key=f"subs_fixed_{month_key}")
                other_fixed = st.number_input("📦 Other Fixed", min_value=0, step=50, key=f"other_fixed_{month_key}")

            # Save button sits right here, directly under the fixed-cost
            # inputs -- a form_submit_button can be placed anywhere inside
            # the form and still submits everything in it (including the
            # sliders below), so moving it up doesn't change what gets saved.
            budget_submitted = st.form_submit_button("💾 Save this month's budget", type="primary")

            st.divider()

            st.markdown("#### 🎯 Variable Cost Budget Targets")
            st.caption("Set targets for your variable spending and track progress.")

            budgets = {}
            for category, default in DEFAULT_CATEGORY_BUDGETS.items():
                saved_value = category_defaults.get(category, default)
                # keep the slider usable even if a saved value exceeds the
                # hardcoded default's usual 2x range
                slider_max = max(int(default * 2), int(saved_value * 2) + 10)
                budgets[category] = st.slider(
                    category.title(),
                    min_value=0,
                    max_value=slider_max,
                    step=10,
                    key=f"budget_{category}_{month_key}"
                )

            st.markdown("**Budget vs Actual:**")
            for category, budget in budgets.items():
                if not category_df.empty:
                    actual = plan_month_df[
                        plan_month_df["category_name"] == category
                    ]["total_spend"].sum()
                else:
                    actual = 0

                pct_used = (actual / budget * 100) if budget > 0 else 0
                col1, col2, col3 = st.columns([2, 3, 1])
                with col1:
                    st.markdown(f"**{category.title()}**")
                    st.caption(f"${actual:,.2f} of ${budget:,.2f}")
                with col2:
                    st.progress(min(pct_used / 100, 1.0))
                with col3:
                    if actual > budget:
                        st.markdown("🔴 Over")
                    elif pct_used >= 80:
                        st.markdown(f"🟡 {pct_used:.0f}%")
                    else:
                        st.markdown(f"🟢 {pct_used:.0f}%")

        total_fixed = mortgage + utilities + insurance + daycare + subscriptions_fixed + other_fixed

        st.divider()

        # --- Variable Costs from transactions (your actual spending) ---
        st.markdown("#### 🛒 Variable Costs (from your transactions)")

        if category_df.empty:
            st.info("No transaction data yet — upload a statement first.")
            total_variable = 0
            variable_df = pd.DataFrame(columns=["category_name", "total_spend", "transaction_count"])
        else:
            # exclude transfer/credit categories from variable costs
            variable_df = plan_month_df[
                ~plan_month_df["category_name"].isin(["transfer", "credit"])
            ]
            total_variable = variable_df["total_spend"].sum()

            st.dataframe(
                variable_df[["category_name", "total_spend", "transaction_count"]],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "category_name": "Category",
                    "total_spend": st.column_config.NumberColumn("Spent", format="$%.2f"),
                    "transaction_count": "# Transactions"
                }
            )

        st.divider()

        # --- Monthly Summary ---
        st.markdown("#### 📊 Monthly Summary")

        total_expenses = total_fixed + total_variable
        savings = monthly_salary - total_expenses
        savings_rate = (savings / monthly_salary * 100) if monthly_salary > 0 else 0

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("💰 Income", f"${monthly_salary:,.0f}")
        col2.metric("🏠 Fixed Costs", f"${total_fixed:,.0f}")
        col3.metric("🛒 Variable Costs", f"${total_variable:,.2f}")
        col4.metric(
            "💵 Savings",
            f"${savings:,.2f}",
            delta=f"{savings_rate:.1f}% savings rate",
            delta_color="normal" if savings >= 0 else "inverse"
        )

        # savings health indicator
        if savings < 0:
            st.error(f"⚠️ You're overspending by ${abs(savings):,.2f} this month.")
        elif savings_rate < 10:
            st.warning(f"💡 Savings rate is {savings_rate:.1f}% — financial advisors recommend at least 20%.")
        elif savings_rate < 20:
            st.info(f"👍 Savings rate is {savings_rate:.1f}% — good, but room to improve.")
        else:
            st.success(f"🎉 Great job! Savings rate is {savings_rate:.1f}%.")

        # Persist on submit, now that total_fixed/total_variable/savings
        # are all known -- a toast instead of an inline st.success() since
        # the button lives well above this point in the layout now.
        if budget_submitted:
            fixed_costs_to_save = {
                "monthly_salary": monthly_salary,
                "mortgage": mortgage,
                "utilities": utilities,
                "insurance": insurance,
                "daycare": daycare,
                "subscriptions_fixed": subscriptions_fixed,
                "other_fixed": other_fixed,
            }
            _budget_conn = get_connection()
            try:
                save_budget(
                    _budget_conn, user_email, selected_plan_month,
                    fixed_costs_to_save, budgets, savings, savings_rate
                )
            finally:
                _budget_conn.close()
            st.toast(f"💾 Saved your budget for {month_key}.", icon="✅")

        st.divider()

        # --- Section 5: AI Investment Suggestion ---
        st.markdown("#### 🤖 AI Investment Advisor")

        if st.button("Get Investment Suggestion", type="primary"):
            if savings <= 0:
                st.warning("Focus on reducing expenses before investing — you're currently overspending.")
            else:
                with st.spinner("Analyzing your finances..."):
                    import anthropic
                    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

                    top_categories = (
                        variable_df[["category_name", "total_spend"]].to_string(index=False)
                        if not category_df.empty else "No data"
                    )

                    prompt = f"""
    You are a personal finance advisor. Based on this person's monthly finances, give a concise, actionable 2-3 sentence investment suggestion.

    Monthly salary (after tax): ${monthly_salary:,.0f}
    Total fixed costs: ${total_fixed:,.0f}
    Total variable costs: ${total_variable:,.2f}
    Monthly savings available: ${savings:,.2f}
    Savings rate: {savings_rate:.1f}%

    Top spending categories this month:
    {top_categories}

    Give specific, actionable advice. Mention exact amounts. Be direct and practical.
    Do not give generic advice. Tailor it to their savings amount and spending pattern.
    """
                    message = client.messages.create(
                        model="claude-sonnet-4-5",
                        max_tokens=300,
                        messages=[{"role": "user", "content": prompt}]
                    )

                    st.info(message.content[0].text)
    elif section == "Transactions":
        st.markdown("**Filter transactions:**")

        show_member_filter = view_mode == "Household Spend" and has_household
        filter_cols = st.columns(4 if show_member_filter else 3)

        with filter_cols[0]:
            categories = ["All"] + sorted(df["category"].dropna().unique().tolist())
            selected_category = st.selectbox("Category", categories)

        with filter_cols[1]:
            txn_type = st.selectbox("Type", ["All", "Debits only", "Credits only"])

        with filter_cols[2]:
            files = ["All"] + sorted(df["source_file"].dropna().unique().tolist())
            selected_file = st.selectbox("Statement", files)

        selected_member = "All"
        if show_member_filter:
            with filter_cols[3]:
                member_options = ["All"] + sorted(df["user_email"].dropna().unique().tolist())
                selected_member = st.selectbox(
                    "Member",
                    member_options,
                    format_func=lambda x: "You" if x == user_email else x
                )

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
        if selected_member != "All":
            filtered_df = filtered_df[filtered_df["user_email"] == selected_member]

        st.markdown(f"**{len(filtered_df)} transactions**")

        # --- Transactions Table ---
        display_column_config = {
            "date": st.column_config.DateColumn("Date"),
            "merchant": "Merchant",
            "category": "Category",
            "amount": st.column_config.NumberColumn("Amount", format="$%.2f"),
            "is_credit": st.column_config.CheckboxColumn("Credit?"),
            "source_file": "Statement"
        }
        if show_member_filter:
            display_column_config["user_email"] = "Member"
        else:
            filtered_df = filtered_df.drop(columns=["user_email"], errors="ignore")

        st.dataframe(
            filtered_df,
            use_container_width=True,
            hide_index=True,
            column_config=display_column_config
        )

        # --- Download ---
        csv = filtered_df.to_csv(index=False)
        st.download_button(
            label="⬇️ Download as CSV",
            data=csv,
            file_name="transactions.csv",
            mime="text/csv"
        )
    elif section == "Ask AI":
        st.info(
            "🚧 Ask AI isn't built yet — this will let you ask natural-language "
            "questions about your spending. For now, the Budget Tracker section "
            "has a one-shot AI investment suggestion at the bottom."
        )
