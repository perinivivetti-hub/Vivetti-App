"""Stile grafico condiviso di Vivetti App (allineato a Vivetti Mobile).

Si applica una volta sola da app.py con `applica_stile()`; l'accesso usa in più
`stile_login()`. I colori sono gli stessi dell'app mobile.
"""
import streamlit as st

VERDE = "#00A650"
VERDE_SCURO = "#008A43"
SFONDO = "#F3F6F4"
BORDO = "#E2E9E5"
INCHIOSTRO = "#1B2B22"
GRIGIO = "#66756D"

_CSS_BASE = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

/* Carattere: solo sui testi, per non rompere le icone di Streamlit */
.stApp, .stApp p, .stApp label, .stApp li, .stApp input, .stApp textarea,
.stApp button, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
.stApp [data-baseweb="select"] div, .stApp [data-testid="stMetricValue"],
.stApp [data-testid="stMetricLabel"], .stApp .stMarkdown {{
    font-family: 'Plus Jakarta Sans', sans-serif;
}}
.stApp {{ background: {SFONDO}; color: {INCHIOSTRO}; }}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 2.2rem; max-width: 1250px; }}
footer {{ visibility: hidden; }}

h1, h2, h3 {{ color: {INCHIOSTRO}; font-weight: 800; letter-spacing: -0.01em; }}
h1 {{ font-size: 1.9rem; }}

/* Pulsanti */
[data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-secondaryFormSubmit"], [data-testid="stBaseButton-primaryFormSubmit"],
.stDownloadButton button, .stLinkButton a {{
    border-radius: 14px !important;
    font-weight: 700 !important;
    min-height: 2.6rem;
    border: 1px solid {BORDO};
    transition: box-shadow .15s ease, transform .05s ease;
}}
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primaryFormSubmit"] {{
    background: {VERDE}; border-color: {VERDE}; color: #fff;
}}
[data-testid="stBaseButton-primary"]:hover, [data-testid="stBaseButton-primaryFormSubmit"]:hover {{
    background: {VERDE_SCURO}; border-color: {VERDE_SCURO};
}}
[data-testid="stBaseButton-secondary"]:hover, .stDownloadButton button:hover {{
    border-color: {VERDE}; color: {VERDE_SCURO};
    box-shadow: 0 2px 10px rgba(0,166,80,.15);
}}

/* Campi di testo, liste a tendina, aree di testo */
[data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="textarea"],
[data-baseweb="select"] > div, [data-testid="stNumberInput"] [data-baseweb="input"],
[data-testid="stDateInput"] [data-baseweb="input"] {{
    border-radius: 14px !important;
    background: #fff !important;
    border-color: {BORDO} !important;
}}
[data-baseweb="input"]:focus-within, [data-baseweb="textarea"]:focus-within,
[data-baseweb="select"] > div:focus-within {{
    border-color: {VERDE} !important;
    box-shadow: 0 0 0 1px {VERDE} !important;
}}

/* Schede: expander, contenitori con bordo, metriche, moduli */
[data-testid="stExpander"], [data-testid="stForm"] {{
    border-radius: 18px;
}}
/* contenitori "scheda" delle pagine (st.container con chiave scheda_...) */
[class*="st-key-scheda"] {{
    background: #fff; border: 1px solid {BORDO} !important; border-radius: 18px !important;
    padding: 1rem 1.1rem;
}}
[data-testid="stExpander"] {{ background: #fff; border: 1px solid {BORDO} !important; overflow: hidden; }}
[data-testid="stExpander"] summary {{ font-weight: 700; }}
[data-testid="stForm"] {{ background: #fff; border: 1px solid {BORDO}; padding: 1.2rem; }}
[data-testid="stMetric"] {{
    background: #fff; border: 1px solid {BORDO}; border-radius: 18px; padding: 14px 18px;
}}
[data-testid="stMetricValue"] {{ font-weight: 800; color: {INCHIOSTRO}; }}
[data-testid="stMetricLabel"] {{ color: {GRIGIO}; }}
[data-testid="stAlert"] {{ border-radius: 14px; }}
[data-testid="stDataFrame"], [data-testid="stTable"] {{ border-radius: 14px; overflow: hidden; }}
[data-testid="stTabs"] [data-baseweb="tab"] {{ font-weight: 700; }}
[data-testid="stTabs"] [aria-selected="true"] {{ color: {VERDE_SCURO}; }}
[data-testid="stTabs"] [data-baseweb="tab-highlight"] {{ background-color: {VERDE}; }}
hr {{ border-color: {BORDO}; }}

/* Menu laterale */
[data-testid="stSidebar"] {{ border-right: 1px solid {BORDO}; }}
[data-testid="stSidebarNavSeparator"] {{ display: none; }}
[data-testid="stNavSectionHeader"], [data-testid="stSidebarNav"] header {{
    text-transform: uppercase; letter-spacing: .12em; font-size: .72rem;
    font-weight: 800; color: {GRIGIO};
}}
[data-testid="stSidebarNav"] a, [data-testid="stSidebarNavLink"] {{
    border-radius: 12px; font-weight: 600; margin: 1px 0;
}}
[data-testid="stSidebarNavLink"][aria-current="page"], [data-testid="stSidebarNav"] a[aria-current="page"] {{
    background: rgba(0,166,80,.12); color: {VERDE_SCURO}; font-weight: 800;
}}
.menu-sezione {{
    text-transform: uppercase; letter-spacing: .12em; font-size: .72rem; font-weight: 800;
    color: {GRIGIO}; margin: 1rem 0 .2rem .4rem;
}}
[data-testid="stPageLink-NavLink"] {{
    border-radius: 12px; font-weight: 600; margin: 1px 0;
}}
[data-testid="stPageLink-NavLink"][aria-current="page"] {{
    background: rgba(0,166,80,.12); color: {VERDE_SCURO}; font-weight: 800;
}}
[data-testid="stPageLink-NavLink"][aria-current="page"] * {{ color: {VERDE_SCURO}; font-weight: 800; }}
.utente-card {{
    background: linear-gradient(135deg, {VERDE}, {VERDE_SCURO});
    border-radius: 18px; padding: 14px 16px; color: #fff; margin-bottom: 10px;
}}
.utente-card .nome {{ font-size: 1.05rem; font-weight: 800; }}
.utente-card .ruolo {{
    display: inline-block; margin-top: 6px; padding: 2px 10px; border-radius: 20px;
    background: rgba(255,255,255,.22); font-size: .72rem; font-weight: 700; letter-spacing: .04em;
}}
</style>
"""

_CSS_LOGIN = f"""
<style>
.stApp {{ background: linear-gradient(180deg, {VERDE} 0%, {VERDE_SCURO} 60%, #006B35 100%); }}
[data-testid="stHeader"], [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {{ display: none; }}
.block-container {{ padding-top: 4rem; }}
[data-testid="stForm"] {{
    background: #fff; border: none; border-radius: 24px; padding: 1.6rem 1.6rem 1.2rem;
    box-shadow: 0 12px 30px rgba(0,0,0,.18);
}}
[data-testid="stForm"] label, [data-testid="stForm"] p {{ color: {INCHIOSTRO}; }}
[data-testid="stForm"] [data-testid="stBaseButton-primaryFormSubmit"] p {{ color: #fff; font-weight: 700; }}
.login-titolo {{ font-size: 1.5rem; font-weight: 800; margin: 0; color: {INCHIOSTRO}; }}
.login-sotto {{ color: {GRIGIO}; margin: 0 0 .8rem 0; }}
</style>
"""


def applica_stile():
    """Stile generale dell'app (da chiamare dopo set_page_config)."""
    st.markdown(_CSS_BASE, unsafe_allow_html=True)


def stile_login():
    """Sfondo verde e scheda bianca per la pagina di accesso."""
    st.markdown(_CSS_BASE + _CSS_LOGIN, unsafe_allow_html=True)


def scheda_utente(nome: str, ruolo: str):
    """Riquadro verde con nome e ruolo, in cima al menu laterale."""
    st.markdown(
        f'<div class="utente-card"><div class="nome">{nome}</div>'
        f'<span class="ruolo">{ruolo.upper()}</span></div>',
        unsafe_allow_html=True,
    )
