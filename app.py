import streamlit as st
import pandas as pd
import os
from streamlit_cookies_manager import EncryptedCookieManager

# 1. CONFIGURAZIONE (Deve essere assolutamente il primo comando)
st.set_page_config(page_title="Vivetti App", page_icon="LogoVivetti.png", layout="wide")

# 2. INIZIALIZZAZIONE GESTORE COOKIE
cookies = EncryptedCookieManager(
    prefix="vivetti_app_",
    password=st.secrets.get("cookie_password", "chiave_segreta_obbligatoria_32_caratteri_min") 
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
    col_sinistra, col_centrale, col_destra = st.columns([0.3, 0.4, 0.3])
    
    with col_centrale:
        placeholder = st.empty()
        with placeholder.container():
            with st.form("login_form"):
                st.image("LogoVivetti.png", use_container_width=True)
                user = st.text_input("Username")
                password = st.text_input("Password", type="password")
                
                if st.form_submit_button("Accedi", use_container_width=True):
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
user_data = st.session_state['user_info']
ruolo = str(user_data.get("ruolo", "")).lower().strip()

# 4. DEFINIZIONE DINAMICA DEL MENU IN BASE AL RUOLO
# Lista standard completa per agenti e admin
pagine_disponibili = ["📊 Nuovo Preventivo", "📊 Archivio Preventivi", "📦 Archivio Ordini", "📊 Performance", "🏬 Clienti", "📦 Magazzino", "🗓️ Eventi Aziendali", "📈 Nota Spese", "🗺️ Mappa"]

if ruolo == "autista":
    # L'autista vede SOLO ed esclusivamente la nota spese
    pagine_disponibili = ["📈 Nota Spese"]
elif ruolo == "amministrazione":
    # L'amministrazione vede tutto tranne la creazione di nuovi preventivi
    pagine_disponibili = [p for p in pagine_disponibili if p != "📊 Nuovo Preventivo"]

# 5. SIDEBAR E NAVIGAZIONE
with st.sidebar:
    st.image("LogoVivetti.png", use_container_width=True)
    st.divider()

    st.markdown(f"### 👤 {user_data['username']}")
    st.caption(f"Ruolo: {user_data['ruolo'].upper()}")
    
    # PULSANTE LOGOUT
    if st.button("Logout", use_container_width=True):
        del cookies["auth_user"]
        cookies.save()
        st.session_state['autenticato'] = False
        st.session_state['user_info'] = None
        st.rerun()
    
    st.divider()
    
    # Mostra la lista filtrata dinamicamente
    scelta = st.radio(
        "NAVIGAZIONE",
        options=pagine_disponibili,
        index=0,
        key="menu_nav"
    )

# 6. CARICAMENTO DELLE PAGINE (VIEWS)
if scelta == "📊 Nuovo Preventivo":
    try:
        from views.preventivi import show_preventivi
        show_preventivi()
    except Exception as e:
        st.error(f"Errore nel caricamento della pagina Preventivi: {e}")

elif scelta == "📊 Archivio Preventivi":
    try:
        from views.archivio import show_archivio
        show_archivio()
    except Exception as e:
        st.info("La pagina 'Archivio' è in fase di sviluppo o il file non è presente.")

elif scelta == "📦 Archivio Ordini":
    try:
        from views.ordinato import show_ordinato
        show_ordinato()
    except Exception as e:
        st.info("La pagina 'Ordinato' è in fase di sviluppo o il file non è presente.")

elif scelta == "📊 Performance":
    try:
        from views.dashboard import show_dashboard
        show_dashboard()
    except Exception as e:
        st.info("La pagina 'Performance' è in fase di sviluppo o il file non è presente.")
        st.error(f"Errore tecnico: {e}")
    
elif scelta == "🏬 Clienti":
    try:
        from views.clienti import show_clienti
        show_clienti()
    except Exception as e:
        st.info("La pagina 'Clienti' è in fase di sviluppo o il file non è presente.")

elif scelta == "📦 Magazzino":
    st.info("La pagina **Magazzino** è attualmente in fase di sviluppo (WIP).")

elif scelta == "🗓️ Eventi Aziendali":
    try:
        from views.eventi import show_eventi
        show_eventi()
    except Exception as e:
        st.info("La pagina 'Eventi' è in fase di sviluppo o il file non è presente.")
        st.error(f"Errore reale: {e}")

elif scelta == "📈 Nota Spese":
    try:
        from views.note_spese import show_note_spese
        show_note_spese()
    except Exception as e:
        st.info("La pagina 'Nota Spese' è in fase di sviluppo o il file non è presente.")
        st.error(f"Errore reale: {e}")

elif scelta == "🗺️ Mappa":
    try:
        from views.mappa import show_mappa
        show_mappa()
    except Exception as e:
        st.info("La pagina 'Mappa' è in fase di sviluppo o il file non è presente.")