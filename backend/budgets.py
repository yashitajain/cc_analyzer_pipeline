"""
Budget persistence.

The Budget Tracker tab lets you set a monthly salary, fixed costs, and
category spending targets. Before this module existed, those were plain
Streamlit widgets with hardcoded defaults -- nothing was ever saved, so
every new session (a new login, a different day) reset back to the
hardcoded $5,000 salary / $2,000 mortgage / etc. regardless of what you'd
actually entered before. A "budget tracker" that forgets your budget every
time isn't really tracking anything.

Budgets are stored per (user_email, month) so history is kept -- but a
month you haven't touched yet should still show something sensible rather
than snapping back to the hardcoded defaults. get_budget_for_month() falls
back to the most recent prior month's budget when the requested month has
no row of its own: "if not changed, keep the fixed costs as they were."
"""

from datetime import date
from psycopg2.extras import Json

# Hardcoded fallback, used only when a user has never saved a budget at
# all (brand new user, no prior month to carry forward from).
DEFAULT_FIXED_COSTS = {
    "monthly_salary": 5000,
    "mortgage": 2000,
    "utilities": 150,
    "insurance": 200,
    "daycare": 1500,
    "subscriptions_fixed": 100,
    "other_fixed": 0,
}

DEFAULT_CATEGORY_BUDGETS = {
    "shopping": 700,
    "travel": 400,
    "entertainment": 200,
    "subscription": 202,
    "dining": 150,
    "transportation": 15,
    "misc": 100,
}


def setup_budgets_table(conn):
    """Create the budgets table if it doesn't exist (idempotent)."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            user_email          VARCHAR NOT NULL,
            month               DATE NOT NULL,
            monthly_salary      DECIMAL(10,2) NOT NULL,
            mortgage            DECIMAL(10,2) NOT NULL,
            utilities           DECIMAL(10,2) NOT NULL,
            insurance           DECIMAL(10,2) NOT NULL,
            daycare             DECIMAL(10,2) NOT NULL,
            subscriptions_fixed DECIMAL(10,2) NOT NULL,
            other_fixed         DECIMAL(10,2) NOT NULL,
            category_budgets    JSONB NOT NULL,
            savings             DECIMAL(10,2),
            savings_rate        DECIMAL(6,2),
            updated_at          TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (user_email, month)
        )
    """)
    conn.commit()


def _month_start(month) -> date:
    """Normalize a date/Timestamp/str to the first of its month, since a
    budget always covers a whole calendar month regardless of which day
    within it the caller passes in."""
    if isinstance(month, str):
        month = date.fromisoformat(month[:10])
    elif hasattr(month, "date") and not isinstance(month, date):
        month = month.date()
    return month.replace(day=1)


def get_budget_for_month(conn, user_email, month):
    """Return {"fixed_costs": {...}, "category_budgets": {...},
    "is_carried_forward": bool, "source_month": date} for this month, or
    None if this user has never saved a budget at all.

    "Carried forward" means this exact month has no saved row, so the most
    recent earlier month's numbers are being shown instead -- the caller
    can use that to tell the user "this is last month's budget, save to
    lock in this month's."
    """
    month = _month_start(month)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT monthly_salary, mortgage, utilities, insurance, daycare,
               subscriptions_fixed, other_fixed, category_budgets, month
        FROM budgets
        WHERE user_email = %s AND month <= %s
        ORDER BY month DESC
        LIMIT 1
        """,
        (user_email, month)
    )
    row = cur.fetchone()
    if row is None:
        return None

    (monthly_salary, mortgage, utilities, insurance, daycare,
     subscriptions_fixed, other_fixed, category_budgets, found_month) = row

    return {
        "fixed_costs": {
            "monthly_salary": float(monthly_salary),
            "mortgage": float(mortgage),
            "utilities": float(utilities),
            "insurance": float(insurance),
            "daycare": float(daycare),
            "subscriptions_fixed": float(subscriptions_fixed),
            "other_fixed": float(other_fixed),
        },
        "category_budgets": {k: float(v) for k, v in (category_budgets or {}).items()},
        "is_carried_forward": found_month != month,
        "source_month": found_month,
    }


def save_budget(conn, user_email, month, fixed_costs, category_budgets, savings, savings_rate):
    """Save (upsert) this month's budget, plus the savings/savings_rate it
    produced so a savings trend can be read back later without
    recomputing it from scratch."""
    month = _month_start(month)

    # psycopg2's float adapter uses repr() for precision, and numpy>=2.0
    # changed repr(np.float64(x)) to the string "np.float64(x)" -- which
    # then gets embedded literally in the SQL instead of just the number,
    # breaking the query (InvalidSchemaName: schema "np" does not exist).
    # Any value here that traces back to a pandas/numpy computation (e.g.
    # a DataFrame column .sum()) needs to be a plain Python float before
    # it reaches psycopg2, so cast everything defensively at the boundary
    # rather than relying on every caller to remember to do it upstream.
    fixed_costs = {k: float(v) for k, v in fixed_costs.items()}
    category_budgets = {k: float(v) for k, v in category_budgets.items()}
    savings = float(savings)
    savings_rate = float(savings_rate)

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO budgets (
            user_email, month, monthly_salary, mortgage, utilities,
            insurance, daycare, subscriptions_fixed, other_fixed,
            category_budgets, savings, savings_rate, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (user_email, month) DO UPDATE SET
            monthly_salary      = EXCLUDED.monthly_salary,
            mortgage            = EXCLUDED.mortgage,
            utilities           = EXCLUDED.utilities,
            insurance           = EXCLUDED.insurance,
            daycare             = EXCLUDED.daycare,
            subscriptions_fixed = EXCLUDED.subscriptions_fixed,
            other_fixed         = EXCLUDED.other_fixed,
            category_budgets    = EXCLUDED.category_budgets,
            savings             = EXCLUDED.savings,
            savings_rate        = EXCLUDED.savings_rate,
            updated_at          = NOW()
        """,
        (
            user_email, month,
            fixed_costs["monthly_salary"], fixed_costs["mortgage"], fixed_costs["utilities"],
            fixed_costs["insurance"], fixed_costs["daycare"], fixed_costs["subscriptions_fixed"],
            fixed_costs["other_fixed"],
            Json(category_budgets), savings, savings_rate
        )
    )
    conn.commit()


def get_savings_history(conn, user_email):
    """All saved months' savings, oldest first -- groundwork for a savings
    trend chart; not wired into the UI yet."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT month, savings, savings_rate
        FROM budgets
        WHERE user_email = %s
        ORDER BY month
        """,
        (user_email,)
    )
    return cur.fetchall()
