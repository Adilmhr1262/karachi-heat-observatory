"""Editorial theme for the observatory dashboard.

Warm paper background, deep ink type, restrained teal, one heat accent.
Serif display face for titles, plain sans-serif for controls and data.
No gradients, no shadows, no decorative effects.
"""

import streamlit as st

PAPER = "#FAF7F0"
PAPER_DEEP = "#F2ECDD"
INK = "#22303A"
MUTED = "#5F6D76"
TEAL = "#2E7D6B"
TEAL_DEEP = "#1E5A4D"
HEAT = "#C0562F"
RULE = "#E2D9C3"

CSS = f"""
<style>
.stApp {{
    background: {PAPER};
    color: {INK};
}}
section[data-testid="stSidebar"] {{
    background: {PAPER_DEEP};
}}
section[data-testid="stSidebar"] .stRadio label {{
    font-size: 0.95rem;
}}
h1, h2, h3 {{
    font-family: Georgia, 'Times New Roman', serif;
    color: {INK};
    font-weight: normal;
}}
.obs-kicker {{
    font-size: 0.78rem;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: {MUTED};
    margin-bottom: 0.1rem;
}}
.obs-title {{
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 2.1rem;
    line-height: 1.15;
    margin: 0 0 0.3rem 0;
}}
.obs-subtitle {{
    font-size: 1.0rem;
    color: {MUTED};
    margin-bottom: 0.6rem;
}}
.obs-rule {{
    border: none;
    border-top: 1px solid {RULE};
    margin: 1.1rem 0;
}}
.obs-finding {{
    font-family: Georgia, 'Times New Roman', serif;
    font-style: italic;
    font-size: 1.18rem;
    line-height: 1.5;
    border-left: 3px solid {HEAT};
    padding: 0.2rem 0 0.2rem 1rem;
    margin: 1rem 0;
}}
.obs-caption {{
    font-size: 0.8rem;
    color: {MUTED};
    line-height: 1.45;
    margin-top: 0.5rem;
}}
.obs-fact {{
    font-size: 0.92rem;
    margin: 0.15rem 0;
}}
.obs-fact b {{
    font-weight: 600;
}}
.stDownloadButton button {{
    border: 1px solid {TEAL};
    color: {TEAL_DEEP};
    background: transparent;
    border-radius: 2px;
}}
.stDownloadButton button:hover {{
    background: {TEAL};
    color: {PAPER};
    border: 1px solid {TEAL};
}}
a {{
    color: {TEAL_DEEP};
}}
.map-legend {{
    background: rgba(250, 247, 240, 0.94);
    border: 1px solid {RULE};
    padding: 8px 10px;
    font-size: 12px;
    color: {INK};
    line-height: 1.4;
}}
.map-legend .legend-title {{
    font-weight: 600;
    margin-bottom: 4px;
}}
.map-legend .legend-unit {{
    color: {MUTED};
}}
table.obs-table {{
    border-collapse: collapse;
    font-size: 0.88rem;
}}
table.obs-table th, table.obs-table td {{
    border-bottom: 1px solid {RULE};
    padding: 0.35rem 0.7rem 0.35rem 0;
    text-align: left;
}}
</style>
"""


def inject_styles():
    st.markdown(CSS, unsafe_allow_html=True)


def caption(text):
    st.markdown(f'<p class="obs-caption">{text}</p>', unsafe_allow_html=True)


def rule():
    st.markdown('<hr class="obs-rule">', unsafe_allow_html=True)
