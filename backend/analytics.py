"""
Local analytics layer.

This replaces the old dbt project (staging -> intermediate -> marts) now
that the pipeline runs against pandas instead of a dbt-managed warehouse.
Each function below mirrors one of the old dbt models exactly (same
filters, same math), just written as pandas instead of SQL:

    stg_transactional + int_transactions_cleaned  -> clean_transactions()
    mart_monthly_summary                          -> monthly_summary()
    mart_spending_by_category                     -> category_spend()
    mart_anomalies                                -> detect_anomalies()
"""

import pandas as pd


def load_raw_transactions(conn, user_emails):
    """Load rows for one or more signed-in users into a DataFrame.

    `user_emails` is always a list -- a single-item list for "my spend
    only", or every active member of a household for the combined "family
    spend" view. This is the multi-tenancy boundary: a query never reads
    rows outside the emails explicitly passed in.
    """
    user_emails = list(user_emails)
    if not user_emails:
        return pd.DataFrame(columns=[
            "date", "merchant", "category", "amount", "is_credit", "source_file", "user_email"
        ])

    placeholders = ", ".join(["%s"] * len(user_emails))
    df = pd.read_sql(
        f"""
        SELECT date, merchant, category, amount, is_credit, source_file, user_email
        FROM raw_transactions
        WHERE user_email IN ({placeholders})
        ORDER BY date DESC
        """,
        conn,
        params=tuple(user_emails),
    )
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["is_credit"] = df["is_credit"].astype(bool)
    return df


def clean_transactions(df):
    """Mirrors stg_transactional (amount > 0) + int_transactions_cleaned."""
    if df.empty:
        return df.assign(
            transaction_date=[], transaction_month=[], merchant_name=[],
            category_name=[], transaction_type=[], is_potential_duplicate=[],
            user_email=[],
        )

    clean = df[(df["amount"] > 0) & df["merchant"].notna() & df["date"].notna()].copy()

    clean["transaction_date"] = clean["date"].dt.normalize()
    clean["transaction_month"] = clean["date"].dt.to_period("M").dt.to_timestamp()
    clean["merchant_name"] = clean["merchant"].astype(str).str.strip().str.lower()
    clean["category_name"] = clean["category"].astype(str).str.strip().str.lower()
    clean["amount"] = clean["amount"].abs()
    clean["transaction_type"] = clean["is_credit"].map({True: "credit", False: "debit"})

    # duplicate_count: same (date, merchant, amount) seen more than once
    clean["duplicate_count"] = clean.groupby(
        [clean["date"], clean["merchant"], clean["amount"]]
    )["amount"].transform("size")
    clean["is_potential_duplicate"] = (clean["duplicate_count"] > 1).astype(int)

    return clean


def monthly_summary(clean_df):
    """Mirrors mart_monthly_summary.sql."""
    cols = ["transaction_month", "total_transactions", "total_spend", "avg_transactions",
            "largest_transactions", "potential_duplicates", "mom_spend_change", "mom_spend_pct_change"]
    if clean_df.empty:
        return pd.DataFrame(columns=cols)

    debit = clean_df[clean_df["transaction_type"] == "debit"]
    g = (
        debit.groupby("transaction_month")
        .agg(
            total_transactions=("amount", "size"),
            total_spend=("amount", "sum"),
            avg_transactions=("amount", "mean"),
            largest_transactions=("amount", "max"),
            potential_duplicates=("is_potential_duplicate", "sum"),
        )
        .reset_index()
        .sort_values("transaction_month")
    )

    g["total_spend"] = g["total_spend"].round(2)
    g["avg_transactions"] = g["avg_transactions"].round(2)
    g["largest_transactions"] = g["largest_transactions"].round(2)

    prior = g["total_spend"].shift(1)
    g["mom_spend_change"] = (g["total_spend"] - prior).round(2)
    g["mom_spend_pct_change"] = ((g["total_spend"] - prior) / prior.replace(0, pd.NA) * 100).round(2)

    return g[cols].reset_index(drop=True)


def category_spend(clean_df):
    """Mirrors mart_spending_by_category.sql."""
    cols = ["transaction_month", "category_name", "transaction_count", "total_spend",
            "avg_spending", "min_transaction", "max_transaction", "pct_monthly_spend"]
    if clean_df.empty:
        return pd.DataFrame(columns=cols)

    debit = clean_df[clean_df["transaction_type"] == "debit"]
    g = (
        debit.groupby(["transaction_month", "category_name"])
        .agg(
            transaction_count=("amount", "size"),
            total_spend=("amount", "sum"),
            avg_spending=("amount", "mean"),
            min_transaction=("amount", "min"),
            max_transaction=("amount", "max"),
        )
        .reset_index()
    )

    month_totals = g.groupby("transaction_month")["total_spend"].transform("sum")
    g["pct_monthly_spend"] = (g["total_spend"] / month_totals * 100).round(2)
    g["total_spend"] = g["total_spend"].round(2)
    g["avg_spending"] = g["avg_spending"].round(2)
    g["min_transaction"] = g["min_transaction"].round(2)
    g["max_transaction"] = g["max_transaction"].round(2)

    g = g.sort_values(["transaction_month", "total_spend"], ascending=[False, False])
    return g[cols].reset_index(drop=True)


def detect_anomalies(clean_df):
    """Mirrors mart_anomalies.sql."""
    cols = ["transaction_date", "merchant_name", "category_name", "amount",
            "category_mean", "category_sd", "z_score", "anomaly_flag", "anomaly_reason"]
    if clean_df.empty:
        return pd.DataFrame(columns=cols)

    tx = clean_df[clean_df["transaction_type"] == "debit"].copy()

    stats = tx.groupby("category_name")["amount"].agg(
        category_mean="mean", category_sd="std", category_count="size"
    )
    tx = tx.merge(stats, on="category_name", how="left")

    raw_z = (tx["amount"] - tx["category_mean"]) / tx["category_sd"]
    tx["z_score"] = raw_z.round(2)

    valid_sd = tx["category_sd"].notna() & (tx["category_sd"] > 0)
    high_zscore = valid_sd & (raw_z.abs() > 2)
    single_large = (tx["category_count"] == 1) & (tx["amount"] > 500)

    tx["anomaly_flag"] = high_zscore | single_large
    tx["anomaly_reason"] = "Normal"
    tx.loc[high_zscore, "anomaly_reason"] = "High zscore: significantly above category average"
    tx.loc[single_large, "anomaly_reason"] = "Single large transaction in category"

    tx["amount"] = tx["amount"].round(2)
    tx["category_mean"] = tx["category_mean"].round(2)
    tx["category_sd"] = tx["category_sd"].round(2)

    tx = tx.sort_values(["anomaly_flag", "z_score"], ascending=[False, False], na_position="last")
    return tx[cols].reset_index(drop=True)


def member_spend(clean_df):
    """Per-member totals for the household view: same idea as
    category_spend(), grouped by who made the purchase instead of what it
    was spent on."""
    cols = ["transaction_month", "user_email", "total_spend", "transaction_count"]
    if clean_df.empty:
        return pd.DataFrame(columns=cols)

    debit = clean_df[clean_df["transaction_type"] == "debit"]
    g = (
        debit.groupby(["transaction_month", "user_email"])
        .agg(
            total_spend=("amount", "sum"),
            transaction_count=("amount", "size"),
        )
        .reset_index()
    )
    g["total_spend"] = g["total_spend"].round(2)
    g = g.sort_values(["transaction_month", "total_spend"], ascending=[False, False])
    return g[cols].reset_index(drop=True)
