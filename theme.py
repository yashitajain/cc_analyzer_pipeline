"""
Custom styling on top of Streamlit's theme engine.

Streamlit's .streamlit/config.toml sets the base palette (background,
accent, text colors). This module layers on the things config.toml can't
do -- custom fonts, card-style metrics, pill-shaped buttons/tabs/toggle --
via one injected CSS block. Purely visual: nothing here touches app logic.
"""

import streamlit as st

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&family=DM+Sans:wght@400;500;600;700&display=swap');

:root {
    --warm-bg: #FBF4EC;
    --warm-card: #FFFDF9;
    --warm-secondary: #F3E5D8;
    --warm-accent: #D97757;
    --warm-accent-dark: #B85C3E;
    --warm-accent-light: #F2CBB5;
    --warm-text: #362B22;
    --warm-text-soft: #7A6B5D;
    --warm-border: #E8D9C8;
}

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
}

h1, h2, h3, h4 {
    font-family: 'Fraunces', serif !important;
    color: var(--warm-text) !important;
    font-weight: 600 !important;
}

/* roomier top, capped width so it doesn't stretch too wide on big screens */
.block-container {
    padding-top: 2.2rem;
    padding-bottom: 3rem;
    max-width: 1100px;
}

/* caption / muted text */
[data-testid="stCaptionContainer"], .stCaption {
    color: var(--warm-text-soft) !important;
}

/* metric cards */
[data-testid="stMetric"] {
    background: var(--warm-card);
    border: 1px solid var(--warm-border);
    border-radius: 14px;
    padding: 1rem 1.2rem;
    box-shadow: 0 2px 10px rgba(180, 110, 70, 0.08);
}
[data-testid="stMetricLabel"] {
    color: var(--warm-text-soft);
    font-weight: 500;
}
[data-testid="stMetricValue"] {
    color: var(--warm-accent-dark);
    font-family: 'Fraunces', serif;
}

/* buttons */
.stButton > button, .stDownloadButton > button {
    border-radius: 999px;
    border: 1px solid var(--warm-accent);
    background: var(--warm-accent);
    color: white;
    font-weight: 600;
    padding: 0.5rem 1.4rem;
    transition: all 0.15s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover {
    background: var(--warm-accent-dark);
    border-color: var(--warm-accent-dark);
    color: white;
}
.stButton > button:disabled {
    background: var(--warm-secondary);
    border-color: var(--warm-border);
    color: var(--warm-text-soft);
}

/* tabs */
[data-baseweb="tab-list"] {
    gap: 4px;
    border-bottom: 1px solid var(--warm-border);
}
[data-baseweb="tab"] {
    border-radius: 10px 10px 0 0;
    padding: 0.5rem 1rem;
    color: var(--warm-text-soft);
    font-weight: 500;
}
[aria-selected="true"][data-baseweb="tab"] {
    background: var(--warm-secondary);
    color: var(--warm-accent-dark) !important;
    font-weight: 600;
}

/* expander (Household box) */
[data-testid="stExpander"] {
    border: 1px solid var(--warm-border);
    border-radius: 14px;
    background: var(--warm-card);
}

/* the My Spend / Household Spend toggle, styled as a pill segmented control */
[data-testid="stRadio"] > div {
    background: var(--warm-secondary);
    border-radius: 999px;
    padding: 4px;
    display: inline-flex;
    gap: 2px;
}
[data-testid="stRadio"] label {
    border-radius: 999px !important;
    padding: 0.3rem 1rem !important;
    margin: 0 !important;
}

/* dividers */
hr {
    border-color: var(--warm-border) !important;
}

/* text inputs / selects */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input {
    border-radius: 10px;
    border: 1px solid var(--warm-border);
}
[data-baseweb="select"] > div {
    border-radius: 10px !important;
    border-color: var(--warm-border) !important;
}

/* progress bars (budget tracker) */
[data-testid="stProgress"] > div > div {
    background-color: var(--warm-accent);
}

/* toggle switch (Anomalies "show flagged only") */
[data-testid="stToggle"] [role="switch"][aria-checked="true"] {
    background-color: var(--warm-accent) !important;
}

/* vertical section nav in the sidebar -- the stRadio rule above makes a
   pill-shaped horizontal row, right for the 2-option My Spend/Household
   Spend switch but wrong for a 6-item nav list, so override it scoped to
   the sidebar only (main-area radios, like that toggle, are untouched) */
[data-testid="stSidebar"] [data-testid="stRadio"] > div {
    display: flex;
    flex-direction: column;
    background: transparent;
    border-radius: 0;
    padding: 0;
    gap: 4px;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label {
    border-radius: 10px !important;
    padding: 0.55rem 0.9rem !important;
    width: 100%;
    margin: 0 !important;
}
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
    background: var(--warm-secondary);
    font-weight: 600;
}
</style>
"""


def inject_custom_theme():
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
