"""
Household / family sharing.

Lets two (or more) signed-in users pool their spending into one "family"
view while still keeping each person's own uploads and individual view
separate. Deliberately lightweight for a small household, not a general
multi-tenant invite system:

- Every user belongs to exactly one household (household_members.user_email
  is the primary key -- one row per person, ever).
- Inviting someone just writes a row for their email with joined_at = NULL
  ("pending"). There's no email sent and no token to accept -- the moment
  that email signs in with Google, ensure_household() sees the pending row
  and activates it. This trades invite-flow security for simplicity, which
  is fine for a household of people who already trust each other.
- A household starts out as a household-of-one the first time anyone logs
  in, so every user always has a household_id even before inviting anyone.
"""

from datetime import datetime


def setup_household_tables(conn):
    """Create household tables if they don't exist (idempotent)."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS households (
            id           SERIAL PRIMARY KEY,
            created_by   VARCHAR NOT NULL,
            created_at   TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS household_members (
            user_email   VARCHAR PRIMARY KEY,
            household_id INTEGER NOT NULL REFERENCES households(id),
            invited_by   VARCHAR,
            joined_at    TIMESTAMP
        )
    """)
    conn.commit()


def ensure_household(conn, user_email):
    """Make sure `user_email` belongs to a household, and return its id.

    - Already an active member somewhere -> return that household_id.
    - Has a pending invite (joined_at IS NULL) -> activate it, return that
      household_id.
    - Neither -> create a brand-new household-of-one for them.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT household_id, joined_at FROM household_members WHERE user_email = %s",
        (user_email,)
    )
    row = cur.fetchone()

    if row is not None:
        household_id, joined_at = row
        if joined_at is None:
            cur.execute(
                "UPDATE household_members SET joined_at = %s WHERE user_email = %s",
                (datetime.now(), user_email)
            )
            conn.commit()
        return household_id

    cur.execute(
        "INSERT INTO households (created_by) VALUES (%s) RETURNING id",
        (user_email,)
    )
    household_id = cur.fetchone()[0]
    cur.execute(
        "INSERT INTO household_members (user_email, household_id, invited_by, joined_at) "
        "VALUES (%s, %s, %s, %s)",
        (user_email, household_id, None, datetime.now())
    )
    conn.commit()
    return household_id


def invite_member(conn, household_id, inviter_email, invitee_email):
    """Invite `invitee_email` into `household_id`. Returns (ok, message)."""
    invitee_email = (invitee_email or "").strip().lower()
    if not invitee_email or "@" not in invitee_email:
        return False, "Enter a valid email address."
    if invitee_email == inviter_email.strip().lower():
        return False, "That's your own email."

    cur = conn.cursor()
    cur.execute(
        "SELECT household_id, joined_at FROM household_members WHERE user_email = %s",
        (invitee_email,)
    )
    row = cur.fetchone()

    if row is not None:
        existing_household_id, joined_at = row
        if existing_household_id == household_id:
            if joined_at is not None:
                return False, f"{invitee_email} is already in your household."
            # already invited but hasn't joined yet -- treat clicking Invite
            # again as "resend the email" rather than blocking it. This
            # matters in practice: an earlier attempt may have saved the
            # pending row but failed to actually deliver the email (e.g. a
            # misconfigured mail provider), and the person needs a way to
            # retry without that first failure permanently locking them out.
            return True, f"Invite re-sent to {invitee_email} — they'll join once they sign in with Google."
        if joined_at is not None:
            return False, f"{invitee_email} already belongs to another household."
        # pending invite to a different household -- redirect it to this one
        cur.execute(
            "UPDATE household_members SET household_id = %s, invited_by = %s "
            "WHERE user_email = %s",
            (household_id, inviter_email, invitee_email)
        )
        conn.commit()
        return True, f"Invited {invitee_email} — they'll join once they sign in with Google."

    cur.execute(
        "INSERT INTO household_members (user_email, household_id, invited_by, joined_at) "
        "VALUES (%s, %s, %s, NULL)",
        (invitee_email, household_id, inviter_email)
    )
    conn.commit()
    return True, f"Invited {invitee_email} — they'll join once they sign in with Google."


def list_household_members(conn, household_id):
    """Return every member of a household, active and pending, active first."""
    cur = conn.cursor()
    cur.execute(
        "SELECT user_email, joined_at, invited_by FROM household_members "
        "WHERE household_id = %s ORDER BY joined_at IS NULL, joined_at",
        (household_id,)
    )
    return [
        {"email": r[0], "joined": r[1] is not None, "invited_by": r[2]}
        for r in cur.fetchall()
    ]
