import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client
import time

# --- CONNESSIONE ---
def get_supabase_client():
    url = st.secrets["connections"]["supabase"]["url"]
    key = st.secrets["connections"]["supabase"]["key"]
    return create_client(url, key)

try:
    supabase = get_supabase_client()
except Exception:
    pass

# --- FUNZIONI CARICAMENTO DATI & STORAGE (SUPABASE) ---

def get_mappa_agenti():
    """Recupera la corrispondenza ID -> Nome dalla tabella 'agenti'"""
    try:
        res = supabase.table("agenti").select("id_agente, nome_agente").execute()
        if res.data:
            return {str(row['id_agente']).strip(): str(row['nome_agente']).upper() for row in res.data}
    except Exception as e:
        st.error(f"Errore caricamento mappa agenti: {e}")
    return {}

def get_note_spese(mese, anno, id_agente=None):
    """Recupera le note spese in base a mese, anno ed eventuale agente specifico"""
    try:
        query = supabase.table("nota_spese").select("*").eq("mese", mese).eq("anno", anno)
        if id_agente:
            query = query.eq("id_agente", str(id_agente).strip())
        
        res = query.order("data_scontrino").execute()
        return res.data or []
    except Exception as e:
        st.error(f"Errore nel caricamento delle note spese: {e}")
        return []

def upload_scontrino(file, id_agente):
    """Carica la foto dello scontrino nello storage di Supabase e restituisce l'URL pubblico"""
    try:
        clean_name = file.name.replace(' ', '_').replace('(', '').replace(')', '')
        file_name = f"spesa_{id_agente}_{int(time.time())}_{clean_name}"
        
        supabase.storage.from_("ricevute_spese").upload(
            path=file_name,
            file=file.getvalue(),
            file_options={"content-type": file.type}
        )
        
        url_data = supabase.storage.from_("ricevute_spese").get_public_url(file_name)
        
        if isinstance(url_data, str): return url_data
        if hasattr(url_data, "public_url"): return url_data.public_url
        if isinstance(url_data, dict) and "publicUrl" in url_data: return url_data["publicUrl"]
        return str(url_data)
        
    except Exception as e:
        st.error(f"❌ Errore durante l'upload dello scontrino nello Storage: {e}")
        return None

def inserisci_nota_spesa(nuova_nota):
    """Inserisce una nuova riga nota spese sul database"""
    try:
        res = supabase.table("nota_spese").insert(nuova_nota).execute()
        return bool(res.data)
    except Exception as e:
        st.error(f"Errore durante l'inserimento: {e}")
        return False

def elimina_nota_spesa(id_nota):
    """Elimina una riga specifica di nota spesa"""
    try:
        res = supabase.table("nota_spese").delete().eq("id", id_nota).execute()
        return bool(res.data)
    except Exception as e:
        st.error(f"Errore durante l'eliminazione: {e}")
        return False

# NUOVA FUNZIONE AGGIUNTA
def aggiorna_stato_verifica(id_nota, stato):
    """Aggiorna lo stato verificato nel database"""
    try:
        supabase.table("nota_spese").update({"verificato": stato}).eq("id", id_nota).execute()
        return True
    except Exception as e:
        st.error(f"Errore aggiornamento verifica: {e}")
        return False


# --- INTERFACCIA UTENTE PRINCIPALE ---

def show_note_spese():
    st.subheader("💰 Gestione Note Spese ")
    
    user_data = st.session_state.get('user_info', {})
    ruolo = str(user_data.get("ruolo", "")).lower().strip()
    agente_id_loggato = str(user_data.get("agente_corrispondente", "")).strip()
    
    mesi_nomi = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", 
                 "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
    oggi = datetime.today()
    
    with st.container(border=True):
        st.markdown("##### 🔍 Filtri di Ricerca")
        col_m, col_a, col_ag = st.columns([1, 1, 2])
        
        with col_m:
            mese_sel_nome = st.selectbox("Mese di riferimento", options=mesi_nomi, index=oggi.month - 1)
            mese_sel_num = mesi_nomi.index(mese_sel_nome) + 1
            
        with col_a:
            anni_disponibili = list(range(oggi.year - 2, oggi.year + 3))
            anno_sel = st.selectbox("Anno di riferimento", options=anni_disponibili, index=anni_disponibili.index(oggi.year))
            
        mappa_agenti = get_mappa_agenti()
        agente_filtro_id = None
        
        with col_ag:
            if ruolo == "amministrazione":
                opzioni_agenti = {"TUTTI GLI UTENTI / AGENTI": None}
                for id_ag, nome_ag in mappa_agenti.items():
                    opzioni_agenti[f"{nome_ag} ({id_ag})"] = id_ag
                
                for user_secret, id_secret in st.secrets.get("agenti", {}).items():
                    if id_secret not in opzioni_agenti.values():
                        opzioni_agenti[f"{user_secret.upper()} ({id_secret})"] = str(id_secret).strip()
                
                agente_scelto_testo = st.selectbox("Seleziona Utente/Agente", options=list(opzioni_agenti.keys()))
                agente_filtro_id = opzioni_agenti[agente_scelto_testo]
            else:
                nome_loggato_visibile = mappa_agenti.get(agente_id_loggato, None)
                if not nome_loggato_visibile:
                    for u_sec, id_sec in st.secrets.get("agenti", {}).items():
                        if str(id_sec).strip() == agente_id_loggato:
                            nome_loggato_visibile = u_sec.upper()
                            break
                if not nome_loggato_visibile:
                    nome_loggato_visibile = agente_id_loggato
                    
                st.text_input("Utente Connesso", value=str(nome_loggato_visibile).upper(), disabled=True)
                agente_filtro_id = agente_id_loggato

    st.divider()

    if ruolo in ["agente", "admin", "autista", "amministrazione"]:
        with st.expander("➕ Inserisci Nuova Riga Nota Spese", expanded=False):
            with st.form("form_nuova_spesa", clear_on_submit=True):
                c1, c2, c3 = st.columns([1, 1, 1])
                data_scon = c1.date_input("Data Scontrino/Ricevuta", max_value=oggi)
                causali_predefinite = ["Pranzo/Cena con cliente", "Carburante", "Pedaggio / Parcheggio", "Hotel / Alloggio", "Trasferta / Consegna", "Altro"]
                causale_sel = c2.selectbox("Causale Spesa", options=causali_predefinite)
                importo_val = c3.number_input("Prezzo Pagato (€)", min_value=0.00, value=0.00, format="%.2f")
                note_spesa = st.text_input("Note / Dettagli aggiuntivi")
                foto_file = st.file_uploader("📸 Carica o Scatta Foto dello Scontrino", type=["jpg", "jpeg", "png", "pdf"])
                
                submit_spesa = st.form_submit_button("💾 SALVA RIGA", use_container_width=True)
                
                if submit_spesa:
                    # ... [tua logica di salvataggio invariata]
                    url_foto_salvata = None
                    upload_valido = True
                    if foto_file:
                        with st.spinner("Caricamento allegato..."):
                            url_foto_salvata = upload_scontrino(foto_file, agente_id_loggato)
                            if not url_foto_salvata: upload_valido = False
                    
                    if upload_valido:
                        nuovo_record = {
                            "id_agente": agente_id_loggato, "mese": int(mese_sel_num), "anno": int(anno_sel),
                            "data_scontrino": str(data_scon), "causale": causale_sel, "importo": float(importo_val),
                            "note": note_spesa.strip() if note_spesa else None, "url_scontrino": url_foto_salvata
                        }
                        if inserisci_nota_spesa(nuovo_record):
                            st.success("✅ Salvato!"); st.rerun()

    st.markdown(f"#### 📄 Elenco Spese - {mese_sel_nome} {anno_sel}")
    record_spese = get_note_spese(mese_sel_num, anno_sel, id_agente=agente_filtro_id)
    
    if record_spese:
        df_spese = pd.DataFrame(record_spese)
        df_spese["id_sicuro"] = df_spese["id"]
        df_spese["id_agente_raw"] = df_spese["id_agente"].astype(str).str.strip()
        
        # NUOVO CAMPO VERIFICATO
        df_spese["Verificato"] = df_spese.get("verificato", False)

        def mappa_nome_tabella(x):
            nome = mappa_agenti.get(x, None)
            if not nome:
                for u_sec, id_sec in st.secrets.get("agenti", {}).items():
                    if str(id_sec).strip() == x: return u_sec.upper()
                return f"ID: {x}"
            return nome

        df_spese["Utente/Agente"] = df_spese["id_agente_raw"].apply(mappa_nome_tabella)
        df_spese["Data"] = pd.to_datetime(df_spese["data_scontrino"]).dt.strftime('%d/%m/%Y')
        df_spese["Allegato"] = df_spese["url_scontrino"]
        
        df_spese = df_spese.rename(columns={"causale": "Causale", "importo": "Importo (€)", "note": "Note"})
        
        # LOGICA MODIFICHE
        if ruolo == "amministrazione": righe_eliminabili = [True] * len(df_spese)
        else: righe_eliminabili = [row["id_agente_raw"] == agente_id_loggato for _, row in df_spese.iterrows()]
            
        df_spese["_is_editable"] = righe_eliminabili
        df_spese.insert(0, "Elimina", [False if ok else None for ok in righe_eliminabili])
        
        # CONFIG COLONNE AGGIORNATA
        colonne_vista = ["Elimina", "Verificato", "Data", "Causale", "Importo (€)", "Note", "Allegato"]
        if ruolo == "amministrazione": colonne_vista.insert(2, "Utente/Agente")
            
        col_config = {
            "Elimina": st.column_config.CheckboxColumn("🗑️", help="Spunta per eliminare", default=False),
            "Verificato": st.column_config.CheckboxColumn("✅ Verificato", disabled=(ruolo != "amministrazione")),
            "Data": st.column_config.TextColumn("Data Scontrino", disabled=True),
            "Utente/Agente": st.column_config.TextColumn("Inserito Da", disabled=True),
            "Causale": st.column_config.TextColumn("Causale Spesa", disabled=True),
            "Importo (€)": st.column_config.NumberColumn("Importo", format="€ %.2f", disabled=True),
            "Note": st.column_config.TextColumn("Note / Dettagli", disabled=True),
            "Allegato": st.column_config.LinkColumn("📄 Vedi Ricevuta", display_text="Apri Scontrino")
        }
        
        editor_key = f"editor_spese_{mese_sel_num}_{anno_sel}_{agente_filtro_id}"
        edited_df = st.data_editor(df_spese, column_config=col_config, column_order=colonne_vista, use_container_width=True, hide_index=True, key=editor_key)
        
        stato_modifiche = st.session_state.get(editor_key, {})
        righe_modificate = stato_modifiche.get("edited_rows", {})
        
        if righe_modificate:
            for string_index, variazioni in righe_modificate.items():
                index = int(string_index)
                id_da_processare = df_spese.at[index, "id_sicuro"]
                
                if variazioni.get("Elimina") is True and df_spese.at[index, "_is_editable"]:
                    if elimina_nota_spesa(id_da_processare): st.rerun()
                elif "Verificato" in variazioni:
                    if aggiorna_stato_verifica(id_da_processare, variazioni["Verificato"]): st.rerun()
    else:
        st.info("ℹ️ Nessuna nota spesa presente.")

if __name__ == "__main__":
    show_note_spese()