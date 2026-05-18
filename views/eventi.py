import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime
from streamlit_searchbox import st_searchbox
import time

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Vivetti - Gestione Eventi", layout="wide")

st.markdown("""
    <style>
    .main h1 { font-size: 1.8rem !important; margin-bottom: 0.5rem !important; }
    .config-card {
        background-color: #f1f3f6; padding: 20px; border-radius: 12px; 
        border-left: 6px solid #ff4b4b; margin: 15px 0;
    }
    .stButton button { font-weight: bold; border-radius: 8px; }
    </style>
    """, unsafe_allow_html=True)

# --- CONNESSIONE ---
def get_supabase_client():
    url = st.secrets["connections"]["supabase"]["url"]
    key = st.secrets["connections"]["supabase"]["key"]
    return create_client(url, key)

supabase = get_supabase_client()

# --- RICERCA CLIENTI ---
def search_clients(search_term: str):
    if not search_term or len(search_term) < 2:
        return []
    user_data = st.session_state.get('user_info', {})
    query = supabase.table("rubrica_clienti").select("*")
    if user_data.get("ruolo") == "agente":
        ag_id = str(user_data.get("agente_corrispondente", "")).strip()
        query = query.eq("id_agente", ag_id)
    res = query.ilike("ragione_sociale", f"%{search_term}%").limit(15).execute()
    if not res.data: return []
    return [(f"{row['ragione_sociale']} ({row.get('citta', '')})", row) for row in res.data]


# --- FUNZIONI CARICAMENTO DATI ---
def get_eventi_disponibili():
    res = supabase.table("eventi").select("*").order("data_evento").execute()
    return res.data or []

def get_conteggio_iscritti(id_evento):
    res = supabase.table("eventi_iscrizioni").select("id", count="exact").eq("id_evento", id_evento).execute()
    return res.count if res.count is not None else 0

def get_iscritti_evento(id_evento):
    """Recupera tutti i partecipanti iscritti a un determinato evento"""
    res = supabase.table("eventi_iscrizioni")\
        .select("id_agente, ragione_sociale_cliente, nominativo_partecipante, note, created_at")\
        .eq("id_evento", id_evento)\
        .order("created_at")\
        .execute()
    return res.data or []

def get_mappa_agenti():
    """Recupera la corrispondenza ID -> Nome dalla tabella 'agenti'"""
    try:
        res = supabase.table("agenti").select("id_agente, nome_agente").execute()
        if res.data:
            return {str(row['id_agente']).strip(): str(row['nome_agente']).upper() for row in res.data}
    except Exception as e:
        st.sidebar.error(f"Errore caricamento mappa agenti: {e}")
    return {}

def upload_locandina(file):
    """Carica il file nello storage di Supabase e restituisce l'URL pubblico"""
    try:
        # Pulizia del nome file
        clean_name = file.name.replace(' ', '_').replace('(', '').replace(')', '')
        file_name = f"flyer_{int(time.time())}_{clean_name}"
        
        # Esegui l'upload effettivo
        supabase.storage.from_("eventi_locandine").upload(
            path=file_name,
            file=file.getvalue(),
            file_options={"content-type": file.type}
        )
        
        # Recupera l'URL generato
        url_data = supabase.storage.from_("eventi_locandine").get_public_url(file_name)
        
        if isinstance(url_data, str):
            return url_data
        elif hasattr(url_data, "public_url"):
            return url_data.public_url
        elif isinstance(url_data, dict) and "publicUrl" in url_data:
            return url_data["publicUrl"]
        return str(url_data)
        
    except Exception as e:
        st.error(f"❌ Errore durante l'upload del file sullo Storage Supabase. Verifica le policy RLS del bucket. Dettaglio: {e}")
        return None


def show_eventi():
    st.subheader("📅 Gestione Eventi e Formazione")
    
    user_data = st.session_state.get('user_info', {})
    ruolo = user_data.get("ruolo", "").lower()
    agente_id = str(user_data.get("agente_corrispondente", "")).strip()
    
    if "inscrizione_cliente_obj" not in st.session_state:
        st.session_state.inscrizione_cliente_obj = None

    # ==========================================
    # VISTA ADMIN: CREAZIONE NUOVO EVENTO
    # ==========================================
    if ruolo == "admin":
        with st.expander("🛠️ Area Amministratore - Crea Nuovo Evento", expanded=False):
            with st.form("form_nuovo_evento", clear_on_submit=True):
                c1, c2 = st.columns([2, 1])
                titolo = c1.text_input("Titolo Evento", placeholder="Es. Corso formazione Miele")
                data_ev = c2.date_input("Data Evento", min_value=datetime.today())
                
                descrizione = st.text_area("Descrizione / Dettagli Evento")
                locandina_file = st.file_uploader("Allega Locandina o Invito (PDF, JPG, PNG)", type=["jpg", "png", "jpeg", "pdf"])
                max_part = st.number_input("Numero Massimo Partecipanti", min_value=1, value=20)
                
                submit_evento = st.form_submit_button("🚀 CREA EVENTO", use_container_width=True)
                
                if submit_evento:
                    if not titolo:
                        st.error("Il titolo dell'evento è obbligatorio!")
                    else:
                        url_locandina = None
                        upload_valido = True
                        
                        if locandina_file:
                            with st.spinner("Caricamento allegato in corso sullo storage..."):
                                url_locandina = upload_locandina(locandina_file)
                                if not url_locandina:
                                    upload_valido = False
                        
                        if upload_valido:
                            nuovo_evento = {
                                "titolo": titolo,
                                "data_evento": str(data_ev),
                                "descrizione": descrizione,
                                "max_partecipanti": int(max_part),
                                "locandina_url": url_locandina
                            }
                            try:
                                supabase.table("eventi").insert(nuovo_evento).execute()
                                st.success(f"✅ Evento '{titolo}' creato con successo!")
                                time.sleep(1)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Errore durante la scrittura nel database: {e}")
                        else:
                            st.error("⚠️ Creazione evento annullata a causa del fallimento del caricamento file.")
        st.divider()

    # ==========================================
    # SELEZIONE EVENTO
    # ==========================================
    eventi = get_eventi_disponibili()
    
    if not eventi:
        st.info("Al momento non ci sono eventi disponibili in catalogo.")
        return
        
    opzioni_eventi = {}
    for ev in eventi:
        iscritti = get_conteggio_iscritti(ev['id'])
        data_f = datetime.strptime(ev['data_evento'], "%Y-%m-%d").strftime("%d/%m/%Y")
        testo_mostrato = f"{ev['titolo']} ({data_f}) - Posti occupati: {iscritti}/{ev['max_partecipanti']}"
        opzioni_eventi[testo_mostrato] = (ev, iscritti)
        
    evento_selezionato_testo = st.selectbox(
        "Seleziona l'evento:", 
        options=list(opzioni_eventi.keys()),
        index=None,
        placeholder="🔍 Scegli un evento dal menu a tendina..."
    )
    
    if evento_selezionato_testo is None:
        st.info("💡 Seleziona un evento dal menu a tendina per visualizzare i dettagli e gli iscritti.")
        return
        
    evento_selezionato, posti_occupati = opzioni_eventi[evento_selezionato_testo]
    posti_rimanenti = evento_selezionato['max_partecipanti'] - posti_occupati
    
    # Visualizzazione Dettagli e Allegato
    c_desc, c_img = st.columns([2, 1])
    
    with c_desc:
        if evento_selezionato['descrizione']:
            st.markdown(f"{evento_selezionato['descrizione']}")
        else:
            st.caption("Nessuna descrizione fornita per questo evento.")
        st.markdown(f"**Posti ancora disponibili:** `{posti_rimanenti}`")
        
    with c_img:
        url_file = evento_selezionato.get('locandina_url')
        if url_file:
            if ".pdf" in url_file.lower():
                st.markdown("##### 📄 Invito PDF")
                st.link_button("📥 Apri / Scarica PDF", url_file, use_container_width=True)
            else:
                st.image(url_file, caption="Locandina Invito", use_container_width=True)
    
    # --- SEZIONE: ELENCO PARTECIPANTI ---
    st.subheader("👥 Partecipanti Iscritti")
    iscritti_totali = get_iscritti_evento(evento_selezionato['id'])
    
    if iscritti_totali:
        df_iscritti = pd.DataFrame(iscritti_totali)
        mappa_agenti = get_mappa_agenti()
        df_iscritti["id_agente"] = df_iscritti["id_agente"].astype(str).str.strip().apply(
            lambda x: mappa_agenti.get(x, "ADMIN" if x == "ADMIN" else f"Agente ({x})")
        )
        
        df_iscritti = df_iscritti.rename(columns={
            "id_agente": "Agente",
            "ragione_sociale_cliente": "Cliente",
            "nominativo_partecipante": "Nominativo Partecipante",
            "note": "Note"
        })
        colonne_da_mostrare = ["Nominativo Partecipante", "Cliente", "Agente", "Note"]
        
        st.dataframe(df_iscritti[colonne_da_mostrare], use_container_width=True, hide_index=True)
    else:
        st.info("Nessun partecipante ancora iscritto a questo evento.")
        
    st.divider()
    
    # --- SEZIONE: FORM DI ISCRIZIONE (SOLO PER AGENTI) ---
    if ruolo == "agente":
        if posti_rimanenti <= 0:
            st.error("❌ Questo evento ha raggiunto il limite massimo di partecipanti.")
        else:
            with st.container(border=True):
                st.markdown("##### Inserisci i dati per la prenotazione")
                cliente_sel = st_searchbox(search_clients, placeholder="🔍 Cerca cliente in rubrica...", key="search_cliente_evento")
                if cliente_sel:
                    st.session_state.inscrizione_cliente_obj = cliente_sel
                
                if st.session_state.inscrizione_cliente_obj:
                    st.success(f"Cliente Selezionato: **{st.session_state.inscrizione_cliente_obj['ragione_sociale']}**")
                
                c_nom, c_note = st.columns([1, 2])
                nominativo = c_nom.text_input("Nominativo Partecipante", placeholder="Nome e Cognome della persona")
                note_iscrizione = c_note.text_input("Note aggiuntive", placeholder="Es. richieste particolari...")
                
                if st.button("➕ CONFERMA ISCRIZIONE", type="primary", use_container_width=True):
                    if not st.session_state.inscrizione_cliente_obj:
                        st.error("Per favore, seleziona un cliente.")
                    elif not nominativo:
                        st.error("Il nominativo del partecipante è obbligatorio.")
                    else:
                        cli = st.session_state.inscrizione_cliente_obj
                        nuova_prenotazione = {
                            "id_evento": evento_selezionato['id'],
                            "id_agente": agente_id,
                            "ragione_sociale_cliente": cli['ragione_sociale'],
                            "nominativo_partecipante": nominativo.upper(),
                            "note": note_iscrizione
                        }
                        try:
                            supabase.table("eventi_iscrizioni").insert(nuova_prenotazione).execute()
                            st.success(f"🎉 Iscrizione di **{nominativo.upper()}** confermata!")
                            st.session_state.inscrizione_cliente_obj = None 
                            time.sleep(1.2)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Errore durante l'iscrizione: {e}")
    else:
        st.caption("ℹ️ Il modulo di inserimento partecipanti è riservato esclusivamente agli Agenti.")

if __name__ == "__main__":
    show_eventi()