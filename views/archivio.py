import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime
import io
import os

# Importiamo le funzioni necessarie dal file preventivi.py
# Assicurati che il percorso dell'import sia corretto in base alla tua struttura
from views.preventivi import genera_pdf_ordine, format_sconti_string

# --- 1. CONNESSIONE ---
def get_supabase_client():
    if "supabase" not in st.session_state:
        url = st.secrets["connections"]["supabase"]["url"]
        key = st.secrets["connections"]["supabase"]["key"]
        st.session_state.supabase = create_client(url, key)
    return st.session_state.supabase

# --- 2. DIALOG DI MODIFICA REATTIVO (Tutto il tuo codice originale) ---
@st.dialog("Gestione Preventivo", width="large")
def modal_gestione(id_p, testata):
    supabase = get_supabase_client()
    session_key = f"edit_righe_{id_p}"
    
    if session_key not in st.session_state:
        with st.spinner("Sincronizzazione articoli..."):
            res = supabase.table("preventivi_righe").select("*").eq("id_preventivo", id_p).execute()
            st.session_state[session_key] = res.data if res.data else []

    righe_temporanee = st.session_state[session_key]
    st.markdown(f"**Modifica per: {testata['ragione_sociale_cliente']}**")
    st.divider()

    nuovo_totale_netto = 0.0
    da_rimuovere = None

    for idx, r in enumerate(righe_temporanee):
        # Recupero valori reattivi per ricalcolo istantaneo
        prezzo_l = float(r.get('prezzo_lordo_unitario', 0))
        qta = st.session_state.get(f"q_{idx}_{id_p}", int(r.get('quantita', 1)))
        s1 = st.session_state.get(f"s1_{idx}_{id_p}", float(r.get('sconto_1', 0)))
        s2 = st.session_state.get(f"s2_{idx}_{id_p}", float(r.get('sconto_2', 0)))
        s3 = st.session_state.get(f"s3_{idx}_{id_p}", float(r.get('sconto_3', 0)))
        omaggio = st.session_state.get(f"sm_{idx}_{id_p}", r.get('is_sconto_merce', False))

        # Calcolo Netto Unitario e Totale Riga
        prezzo_n_unitario = prezzo_l * (1 - s1/100) * (1 - s2/100) * (1 - s3/100)
        riga_tot = 0.0 if omaggio else (prezzo_n_unitario * qta)
        nuovo_totale_netto += riga_tot

        # TRONCAMENTO DESCRIZIONE per il titolo dell'expander (max 30 caratteri)
        desc_preview = r['descrizione'][:30] + "..." if len(r['descrizione']) > 30 else r['descrizione']
        
        label_riga = f"📦 {r['codice_articolo']} | {desc_preview} | € {prezzo_n_unitario:.2f}"
        if omaggio: label_riga = f"🎁 {r['codice_articolo']} | {desc_preview} | OMAGGIO"

        with st.expander(label_riga):
            c1, c2 = st.columns([2, 1])
            r['quantita'] = c1.number_input("Quantità", min_value=1, value=int(r.get('quantita', 1)), key=f"q_{idx}_{id_p}")
            r['is_sconto_merce'] = c2.toggle("Omaggio", value=r.get('is_sconto_merce', False), key=f"sm_{idx}_{id_p}")
            
            sc1, sc2, sc3 = st.columns(3)
            r['sconto_1'] = sc1.number_input("Sconto 1 %", value=float(r.get('sconto_1', 0)), key=f"s1_{idx}_{id_p}")
            r['sconto_2'] = sc2.number_input("Sconto 2 %", value=float(r.get('sconto_2', 0)), key=f"s2_{idx}_{id_p}")
            r['sconto_3'] = sc3.number_input("Sconto 3 %", value=float(r.get('sconto_3', 0)), key=f"s3_{idx}_{id_p}")
            
            # Mostriamo la descrizione completa qui dentro
            st.caption(f"**Descrizione completa:** {r['descrizione']}")
            r['nota_riga'] = st.text_input("Note articolo", value=r.get('nota_riga', ""), key=f"n_{idx}_{id_p}")
            r['prezzo_netto_unitario'] = prezzo_n_unitario

            if st.button("🗑️ Rimuovi", key=f"del_{idx}_{id_p}", use_container_width=True):
                da_rimuovere = idx

    if da_rimuovere is not None:
        st.session_state[session_key].pop(da_rimuovere)
        st.rerun()

    st.divider()

    st.markdown(f"""
        <div style='text-align: right; padding-top: 10px; border-top: 1px solid #eee; margin-top: 20px;'>
            <span style='font-size: 13px; color: #888; text-transform: uppercase; letter-spacing: 0.5px;'>Totale Documento</span><br>
            <span style='font-size: 22px; font-weight: 500; color: #31333F;'>€ {nuovo_totale_netto:,.2f}</span>
        </div>
    """, unsafe_allow_html=True)

    col_save, col_close = st.columns(2)
    if col_save.button("💾 SALVA MODIFICHE", type="primary", use_container_width=True):
        with st.spinner("Salvataggio..."):
            supabase.table("preventivi_testata").update({"totale_netto": nuovo_totale_netto}).eq("id", id_p).execute()
            supabase.table("preventivi_righe").delete().eq("id_preventivo", id_p).execute()
            per_db = []
            for item in righe_temporanee:
                item_copy = item.copy()
                item_copy.pop('id', None)
                item_copy['id_preventivo'] = id_p
                per_db.append(item_copy)
            if per_db:
                supabase.table("preventivi_righe").insert(per_db).execute()
            st.success("Archivio aggiornato!")
            if session_key in st.session_state: del st.session_state[session_key]
            st.rerun()

    if col_close.button("Annulla", use_container_width=True):
        if session_key in st.session_state: del st.session_state[session_key]
        st.rerun()

# --- 3. VISTA ARCHIVIO ---
def show_archivio():
    st.title("📂 Archivio Preventivi")
    supabase = get_supabase_client()
    user_data = st.session_state.get('user_info', {})
    agente_id = str(user_data.get("agente_corrispondente"))

    cerca = st.text_input("🔍 Cerca cliente...", placeholder="es. Rossi")

    with st.spinner("Caricamento..."):
        # Selezioniamo tutti i dati delle righe per poter stampare il PDF completo
        res = supabase.table("preventivi_testata")\
            .select("*, preventivi_righe(*)")\
            .eq("id_agente", agente_id)\
            .order("created_at", desc=True)\
            .execute()
    
    if not res.data:
        st.info("Nessun preventivo salvato.")
        return

    preventivi = [p for p in res.data if cerca.lower() in p['ragione_sociale_cliente'].lower()]

    for prev in preventivi:
        data_f = datetime.fromisoformat(prev['created_at']).strftime("%d/%m/%y")
        
        # Righe collegate a questo preventivo
        righe_db = prev.get('preventivi_righe', [])
        
        # Anteprima per la card
        nomi_articoli = ", ".join([r['descrizione'][:20] for r in righe_db[:2]])
        if len(righe_db) > 2: nomi_articoli += "..."

        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            c1.markdown(f"**{prev['ragione_sociale_cliente']}**")
            c2.markdown(f"<div style='text-align: right; font-size: 11px; color: gray;'>{data_f}</div>", unsafe_allow_html=True)
            
            st.markdown(f"<div style='font-size: 12px; color: #888; font-style: italic;'>{nomi_articoli}</div>", unsafe_allow_html=True)
            st.markdown(f"<div style='margin-top: 5px; color: #1f77b4; font-weight: bold;'>Tot: € {prev['totale_netto']:,.2f}</div>", unsafe_allow_html=True)
            
            # --- TASTI AZIONE ---
            btn_col1, btn_col2 = st.columns(2)
            
            if btn_col1.button("Gestisci", key=f"main_btn_{prev['id']}", use_container_width=True):
                modal_gestione(prev['id'], prev)

            # --- LOGICA DI STAMPA PDF ---
            try:
                # Trasformiamo i dati del DB nel formato che la funzione genera_pdf_ordine accetta
                righe_formattate = []
                for r in righe_db:
                    righe_formattate.append({
                        "CODICE": r['codice_articolo'],
                        "DESCRIZIONE": r['descrizione'],
                        "QTA": r['quantita'],
                        "PREZZO_LORDO": r['prezzo_lordo_unitario'],
                        "PREZZO_NETTO": r['prezzo_netto_unitario'],
                        "S1": r['sconto_1'],
                        "S2": r['sconto_2'],
                        "S3": r['sconto_3'],
                        "SCONTO_MERCE": r['is_sconto_merce'],
                        "NOTA": r['nota_riga']
                    })

                # Mock del dizionario cliente per la funzione PDF
                cliente_mock = {"ragione_sociale": prev['ragione_sociale_cliente']}
                
                # Generiamo il PDF usando la funzione centralizzata
                pdf_data = genera_pdf_ordine(cliente_mock, prev, righe_formattate)
                
                btn_col2.download_button(
                    label="📄 Stampa PDF",
                    data=pdf_data,
                    file_name=f"Preventivo_{prev['numero_preventivo']}.pdf",
                    mime="application/pdf",
                    key=f"print_btn_{prev['id']}",
                    use_container_width=True
                )
            except Exception as e:
                btn_col2.error("Errore PDF")