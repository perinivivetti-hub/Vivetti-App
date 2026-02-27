import streamlit as st
import pandas as pd
import os

# 1. CONFIGURAZIONE (Deve essere il primo comando)
st.set_page_config(page_title="Vivetti App", layout="wide")

col_sinistra, col_centrale, col_destra = st.columns([0.3, 0.4, 0.3])

with col_centrale:
    # --- GESTIONE SESSIONE LOGIN ---
    if 'autenticato' not in st.session_state:
        st.session_state['autenticato'] = False
        st.session_state['user_info'] = None

    # Creiamo un contenitore che può essere "svuotato"
    placeholder = st.empty()

    if not st.session_state['autenticato']:
        with placeholder.container(): # Tutto il login sta qui dentro
            with st.form("login_form"):
                st.image("LogoVivetti.png", use_container_width=True)
                user = st.text_input("Username")
                password = st.text_input("Password", type="password")
                if st.form_submit_button("Accedi"):
                    # Accediamo ai secrets invece del dizionario locale
                    if user in st.secrets["passwords"] and st.secrets["passwords"][user] == password:
                        st.session_state['autenticato'] = True
                        # Creiamo l'info utente recuperando i dati dalle altre sezioni dei secrets
                        st.session_state['user_info'] = {
                            "username": user,
                            "agente_corrispondente": st.secrets["agenti"][user],
                            "ruolo": st.secrets["ruoli"][user]
                        }
                        placeholder.empty() # <--- CANCELLA IL LOGIN ISTANTANEAMENTE
                        st.rerun()
                    else:
                        st.error("Credenziali errate")
            st.stop() # Blocca l'app qui finché non avviene il login

# --- SE SIAMO QUI, L'UTENTE È LOGGATO ---
user_data = st.session_state['user_info']

# 3. SIDEBAR: USA IL CONTAINER PER "SPOSTARE" IL CONTENUTO SOPRA IL MENU
# In Streamlit, inserire elementi in st.sidebar prima di pg.run() 
# a volte richiede l'uso esplicito del container per mantenere l'ordine.
with st.sidebar:
    # 1. Logo Vivetti in alto nella Sidebar
    st.image("LogoVivetti.png", use_container_width=True)
        
    st.divider() # Una linea sottile per separare il logo dal resto

    st.markdown(f"### 👤 {user_data['username']}")
    st.caption(f"Ruolo: {user_data['ruolo'].capitalize()}")
    
    if st.button("Logout", use_container_width=True):
        st.session_state['autenticato'] = False
        st.rerun()
    
    st.divider()
    
    # Parte centrale: Il Menu manuale
    # Usiamo un radio button che sembra un menu
    scelta = st.radio(
        "NAVIGAZIONE",
        ["📊 Nuovo Preventivo", "📊 Archivio Preventivi", "📊 Performance", "🏬 Clienti", "📦 Magazzino", "🗓️ Eventi Aziendali", "📈 Nota Spese"],
        index=0,
        key="menu_nav"
    )

# 2. LOGICA DI CARICAMENTO PAGINE
# Invece di pg.run(), importiamo i file in base alla scelta
if scelta == "📊 Nuovo Preventivo":
    # Eseguiamo il codice della dashboard
    # Se il file è views/dashboard.py:
    from views.preventivi import show_preventivi
    show_preventivi()  # Chiamiamo la funzione

elif scelta == "📊 Archivio Preventivi":
    # Eseguiamo il codice dell'altra pagina
    try:
        from views.archivio import show_archivio
        show_archivio()
    except FileNotFoundError:
        st.info("La pagina 'Archivio' è in fase di sviluppo.")

elif scelta == "📊 Performance":
    # Eseguiamo il codice dell'altra pagina
    try:
        from views.dashboard import show_dashboard
        show_dashboard()
    except FileNotFoundError:
        st.info("La pagina 'Clienti' è in fase di sviluppo.")
    
elif scelta == "🏬 Clienti":
    # Eseguiamo il codice dell'altra pagina
    try:
        from views.clienti import show_clienti
        show_clienti()
    except FileNotFoundError:
        st.info("La pagina 'Clienti' è in fase di sviluppo.")

elif scelta == "📦 Magazzino":
    # Eseguiamo il codice dell'altra pagina
    try:
        st.info("La pagina Magazzino è wip")
    except FileNotFoundError:
        st.info("La pagina 'Magazzino' è in fase di sviluppo.")

elif scelta == "🗓️ Eventi Aziendali":
    # Eseguiamo il codice dell'altra pagina
    try:
        st.info("La pagina Eventi Aziendali è wip")
    except FileNotFoundError:
        st.info("La pagina 'Eventi Aziendali' è in fase di sviluppo.")

elif scelta == "📈 Nota Spese":
    # Eseguiamo il codice dell'altra pagina
    try:
        st.info("La pagina Nota Spese è wip")
    except FileNotFoundError:
        st.info("La pagina 'Nota Spese' è in fase di sviluppo.")

