import importlib
import os
import pandas as pd
import streamlit as st

# --- MONKEY PATCH PER COMPATIBILITÀ CON STREAMLIT NUOVO ---
# Ripristina st.cache prima di importare streamlit_cookies_manager
if not hasattr(st, "cache"):
    st.cache = st.cache_data
# ---------------------------------------------------------

from streamlit_cookies_manager import EncryptedCookieManager
from stile import applica_stile, stile_login, scheda_utente

# 1. CONFIGURAZIONE (Prima chiamata Streamlit)
st.set_page_config(
    page_title="Vivetti App", page_icon="LogoVivetti.png", layout="wide"
)

# 2. INIZIALIZZAZIONE GESTORE COOKIE
cookies = EncryptedCookieManager(
    prefix="vivetti_app_",
    password=st.secrets.get(
        "cookie_password", "chiave_segreta_obbligatoria_32_caratteri_min"
    ),
)

if not cookies.ready():
    st.stop()  # Attende che il browser invii i cookie

# 3. GESTIONE LOGICA DI AUTENTICAZIONE (Cookie + Session State)
if 'autenticato' not in st.session_state:
    cookie_user = cookies.get("auth_user")

    if cookie_user and "passwords" in st.secrets and cookie_user in st.secrets["passwords"]:
        st.session_state['autenticato'] = True
        st.session_state['user_info'] = {
            "username": cookie_user,
            "agente_corrispondente": st.secrets["agenti"][cookie_user],
            "ruolo": st.secrets["ruoli"][cookie_user]
        }
    else:
        st.session_state['autenticato'] = False
        st.session_state['user_info'] = None

# --- INTERFACCIA DI LOGIN ---
if not st.session_state['autenticato']:
    stile_login()
    col_sinistra, col_centrale, col_destra = st.columns([1, 1.3, 1])

    with col_centrale:
        placeholder = st.empty()
        with placeholder.container():
            st.image("LogoVivetti_bianco.png", use_container_width=True)
            st.write("")
            with st.form("login_form"):
                st.markdown(
                    '<p class="login-titolo">Accedi</p>'
                    '<p class="login-sotto">Entra con le tue credenziali aziendali</p>',
                    unsafe_allow_html=True,
                )
                user = st.text_input("Username")
                password = st.text_input("Password", type="password")

                if st.form_submit_button("Accedi", use_container_width=True, type="primary"):
                    if user in st.secrets["passwords"] and st.secrets["passwords"][user] == password:
                        cookies["auth_user"] = user
                        cookies.save()

                        st.session_state['autenticato'] = True
                        st.session_state['user_info'] = {
                            "username": user,
                            "agente_corrispondente": st.secrets["agenti"][user],
                            "ruolo": st.secrets["ruoli"][user]
                        }
                        st.rerun()
                    else:
                        st.error("Credenziali errate")
        st.stop()

# --- SE SIAMO QUI, L'UTENTE È LOGGATO ---
applica_stile()
user_data = st.session_state['user_info']
ruolo = str(user_data.get("ruolo", "")).lower().strip()


# 4. PAGINE DELL'APP, RAGGRUPPATE COME IN VIVETTI MOBILE
def _pagina(modulo, funzione, nome):
    """Crea la funzione che mostra una pagina, con lo stesso trattamento degli errori di prima."""
    def mostra():
        try:
            getattr(importlib.import_module(modulo), funzione)()
        except Exception as e:
            st.info(f"La pagina '{nome}' è in fase di sviluppo o il file non è presente.")
            st.error(f"Errore tecnico: {e}")
    mostra.__name__ = f"pagina_{funzione}"
    return mostra


# (sezione, titolo, icona, modulo, funzione, percorso)
PAGINE = [
    ("Vendite", "Nuovo Preventivo", ":material/note_add:", "views.preventivi", "show_preventivi", "nuovo-preventivo"),
    ("Vendite", "Archivio Preventivi", ":material/folder_open:", "views.archivio", "show_archivio", "archivio-preventivi"),
    ("Vendite", "Archivio Ordini", ":material/local_shipping:", "views.ordinato", "show_ordinato", "archivio-ordini"),
    ("Vendite", "Fatturato", ":material/bar_chart:", "views.dashboard", "show_dashboard", "fatturato"),
    ("Clienti", "Clienti", ":material/groups:", "views.clienti", "show_clienti", "clienti"),
    ("Clienti", "Mappa Clienti", ":material/map:", "views.mappa", "show_mappa", "mappa-clienti"),
    ("Azienda", "Comunicazioni", ":material/campaign:", "views.comunicazioni", "show_comunicazioni", "comunicazioni"),
    ("Azienda", "Richieste Commerciali", ":material/assignment:", "views.richieste", "show_richieste", "richieste-commerciali"),
    ("Azienda", "Nota Spese", ":material/receipt_long:", "views.note_spese", "show_note_spese", "nota-spese"),
    ("Azienda", "Eventi Aziendali", ":material/event:", "views.eventi", "show_eventi", "eventi-aziendali"),
    ("Azienda", "Magazzino Occasioni", ":material/inventory_2:", "views.magazzino", "show_magazzino", "magazzino-occasioni"),
    ("Azienda", "Drive Promozioni", ":material/cloud:", "views.drive_promozioni", "show_drive_promozioni", "drive-promozioni"),
]

# Visibilità per ruolo (come prima)
if ruolo == "autista":
    # L'autista vede SOLO ed esclusivamente la nota spese
    visibili = {"Nota Spese"}
elif ruolo == "magazzino":
    # Il ruolo magazzino vede SOLO ed esclusivamente il Magazzino Occasioni
    visibili = {"Magazzino Occasioni"}
elif ruolo == "amministrazione":
    # L'amministrazione vede tutto tranne la creazione di nuovi preventivi, il Magazzino Occasioni
    # e le Richieste Commerciali (riservate ad agenti e admin)
    visibili = {p[1] for p in PAGINE} - {"Nuovo Preventivo", "Magazzino Occasioni", "Richieste Commerciali"}
else:
    visibili = {p[1] for p in PAGINE}

sezioni = {}
for sezione, titolo, icona, modulo, funzione, percorso in PAGINE:
    if titolo in visibili:
        sezioni.setdefault(sezione, []).append(
            st.Page(_pagina(modulo, funzione, titolo), title=titolo, icon=icona, url_path=percorso)
        )

# 5. MENU LATERALE: logo, utente, sezioni e uscita
pagina = st.navigation(sezioni, position="hidden")

with st.sidebar:
    st.image("LogoVivetti.png", use_container_width=True)
    scheda_utente(user_data['username'], user_data['ruolo'])
    # PULSANTE LOGOUT (sotto le informazioni dell'utente)
    if st.button("Esci", use_container_width=True, icon=":material/logout:"):
        del cookies["auth_user"]
        cookies.save()
        st.session_state['autenticato'] = False
        st.session_state['user_info'] = None
        st.rerun()
    for sezione, pagine_sezione in sezioni.items():
        st.markdown(f'<p class="menu-sezione">{sezione}</p>', unsafe_allow_html=True)
        for pg in pagine_sezione:
            st.page_link(pg)

# 6. CARICAMENTO DELLA PAGINA SCELTA
pagina.run()
