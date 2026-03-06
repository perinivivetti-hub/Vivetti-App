import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime
import io
import os
import time

# Importiamo le funzioni necessarie dal file preventivi.py
from views.preventivi import genera_pdf_ordine, format_sconti_string, calcola_netto, get_data_for_form

# --- 1. CONNESSIONE ---
def get_supabase_client():
    if "supabase" not in st.session_state:
        url = st.secrets["connections"]["supabase"]["url"]
        key = st.secrets["connections"]["supabase"]["key"]
        st.session_state.supabase = create_client(url, key)
    return st.session_state.supabase

# --- 2. DIALOG DI MODIFICA REATTIVO ---
@st.dialog("Gestione Preventivo", width="large")
def modal_gestione(id_p, testata):
    supabase = get_supabase_client()
    session_key = f"edit_righe_{id_p}"
    
    # Inizializzazione: carica le righe dal DB solo la prima volta
    if session_key not in st.session_state:
        with st.spinner("Sincronizzazione articoli..."):
            res = supabase.table("preventivi_righe").select("*").eq("id_preventivo", id_p).execute()
            st.session_state[session_key] = res.data if res.data else []

    righe_temporanee = st.session_state[session_key]
    st.markdown(f"🔍 **Modifica Preventivo: {testata['ragione_sociale_cliente']}**")
    st.caption(f"Numero: {testata.get('numero_preventivo')} | Rif: {testata.get('riferimento', '-')}")
    st.divider()

    nuovo_totale_netto = 0.0
    da_rimuovere = None

    # --- A. ELENCO ARTICOLI ESISTENTI ---
    st.markdown("### 📦 Articoli in lista")
    if not righe_temporanee:
        st.info("Il preventivo è vuoto. Aggiungi un articolo sotto.")
    
    for idx, r in enumerate(righe_temporanee):
        prezzo_l = float(r.get('prezzo_lordo_unitario', 0))
        desc_preview = r['descrizione'][:45] + "..." if len(r['descrizione']) > 45 else r['descrizione']
        
        with st.expander(f"{r['codice_articolo']} - {desc_preview}"):
            c1, c2 = st.columns([2, 1])
            qta = c1.number_input("Quantità", min_value=1, value=int(r.get('quantita', 1)), key=f"q_{idx}_{id_p}")
            omaggio = c2.toggle("Omaggio", value=r.get('is_sconto_merce', False), key=f"sm_{idx}_{id_p}")

            # Logica Metodo Prezzo (Sconti o Netto Diretto)
            # Controllo se ha sconti per impostare il default del radio
            ha_sconti = any([float(r.get('sconto_1', 0)) > 0, float(r.get('sconto_2', 0)) > 0, float(r.get('sconto_3', 0)) > 0])
            metodo_init = "Sconti %" if ha_sconti else "Netto Fisso €"
            
            modo = st.radio("Metodo Prezzo", ["Sconti %", "Netto Fisso €"], 
                            index=0 if metodo_init=="Sconti %" else 1, 
                            key=f"modo_{idx}_{id_p}", horizontal=True)

            if modo == "Sconti %":
                sc1_c, sc2_c, sc3_c = st.columns(3)
                s1 = sc1_c.number_input("S1 %", value=float(r.get('sconto_1', 0)), key=f"s1_{idx}_{id_p}")
                s2 = sc2_c.number_input("S2 %", value=float(r.get('sconto_2', 0)), key=f"s2_{idx}_{id_p}")
                s3 = sc3_c.number_input("S3 %", value=float(r.get('sconto_3', 0)), key=f"s3_{idx}_{id_p}")
                prezzo_n_unitario = calcola_netto(prezzo_l, s1, s2, s3)
                st.caption(f"Netto calcolato: € {prezzo_n_unitario:,.2f}")
            else:
                prezzo_n_unitario = st.number_input("Prezzo Netto Unitario (€)", 
                                                   value=float(r.get('prezzo_netto_unitario', prezzo_l)), 
                                                   key=f"pn_{idx}_{id_p}")
                s1, s2, s3 = 0.0, 0.0, 0.0

            r['nota_riga'] = st.text_input("Note articolo", value=r.get('nota_riga', ""), key=f"n_{idx}_{id_p}")
            
            # Aggiornamento dati in memoria
            r.update({
                "quantita": qta, "is_sconto_merce": omaggio, "sconto_1": s1, "sconto_2": s2, "sconto_3": s3,
                "prezzo_netto_unitario": prezzo_n_unitario
            })

            if st.button("🗑️ Rimuovi riga", key=f"del_{idx}_{id_p}", use_container_width=True):
                da_rimuovere = idx

        # Somma al totale (se non è omaggio)
        nuovo_totale_netto += 0.0 if omaggio else (prezzo_n_unitario * qta)

    if da_rimuovere is not None:
        st.session_state[session_key].pop(da_rimuovere)
        st.rerun()

    # --- B. AGGIUNTA NUOVO ARTICOLO ---
    st.markdown("---")
    st.markdown("### ➕ Aggiungi Articolo")
    _, df_listino = get_data_for_form()
    
    search_edit = st.text_input("Cerca nel listino (min. 4 car.):", key=f"search_edit_{id_p}")
    if len(search_edit) >= 4:
        mask = df_listino['DESCRIZIONE'].str.contains(search_edit, case=False) | \
               df_listino['CODICE'].str.contains(search_edit, case=False)
        res_list = df_listino[mask].head(10)
        
        if not res_list.empty:
            sel_new = st.selectbox("Seleziona prodotto:", options=res_list.to_dict('records'),
                                   format_func=lambda x: f"[{x['CODICE']}] {x['DESCRIZIONE'][:50]}...", 
                                   index=None, key=f"sel_new_{id_p}")
            if sel_new:
                if st.button("✅ Inserisci in lista", type="secondary", use_container_width=True):
                    p_lordo = float(sel_new["PREZZO"])
                    # Creiamo la riga col formato del DB
                    nuova_riga = {
                        "id_preventivo": id_p,
                        "codice_articolo": sel_new["CODICE"],
                        "descrizione": sel_new["DESCRIZIONE"],
                        "quantita": 1,
                        "prezzo_lordo_unitario": p_lordo,
                        "sconto_1": float(sel_new.get("SCONTO1", 0)),
                        "sconto_2": float(sel_new.get("SCONTO2", 0)),
                        "sconto_3": float(sel_new.get("SCONTO3", 0)),
                        "prezzo_netto_unitario": calcola_netto(p_lordo, sel_new.get("SCONTO1", 0), sel_new.get("SCONTO2", 0), sel_new.get("SCONTO3", 0)),
                        "is_sconto_merce": False,
                        "nota_riga": ""
                    }
                    st.session_state[session_key].append(nuova_riga)
                    st.rerun()
        else:
            st.warning("Nessun articolo trovato.")

    # --- C. FOOTER E SALVATAGGIO ---
    st.divider()
    st.markdown(f"#### Totale Documento: € {nuovo_totale_netto:,.2f}")

    col_save, col_close = st.columns(2)
    if col_save.button("💾 SALVA MODIFICHE", type="primary", use_container_width=True):
        with st.spinner("Aggiornamento in corso..."):
            # 1. Aggiorna totale in testata
            supabase.table("preventivi_testata").update({"totale_netto": nuovo_totale_netto}).eq("id", id_p).execute()
            # 2. Sostituzione integrale righe
            supabase.table("preventivi_righe").delete().eq("id_preventivo", id_p).execute()
            
            per_db = []
            for item in st.session_state[session_key]:
                # Pulizia per evitare errori di vincoli DB (rimuoviamo ID vecchi)
                item_clean = {k: v for k, v in item.items() if k not in ['id', 'created_at']}
                item_clean['id_preventivo'] = id_p
                per_db.append(item_clean)
            
            if per_db:
                supabase.table("preventivi_righe").insert(per_db).execute()
            
            st.toast("✅ Preventivo aggiornato!", icon='💾')
            del st.session_state[session_key]
            time.sleep(1)
            st.rerun()

    if col_close.button("Annulla", use_container_width=True):
        if session_key in st.session_state:
            del st.session_state[session_key]
        st.rerun()

# --- 3. VISTA ARCHIVIO PRINCIPALE ---
def show_archivio():
    st.subheader("📂 Archivio Preventivi")
    supabase = get_supabase_client()
    user_data = st.session_state.get('user_info', {})
    agente_id = str(user_data.get("agente_corrispondente"))

    c1, c2 = st.columns([2, 1])
    cerca = c1.text_input("🔍 Cerca cliente o riferimento...", placeholder="es. Rossi...")
    ordine = c2.selectbox("Ordine", ["Più recenti", "Meno recenti"])

    with st.spinner("Lettura archivio..."):
        is_desc = True if ordine == "Più recenti" else False
        res = supabase.table("preventivi_testata")\
            .select("*, preventivi_righe(*)")\
            .eq("id_agente", agente_id)\
            .order("created_at", desc=is_desc)\
            .execute()
    
    if not res.data:
        st.info("Nessun preventivo presente in archivio.")
        return

    # Filtro locale per ricerca
    preventivi = [p for p in res.data if 
                  cerca.lower() in p['ragione_sociale_cliente'].lower() or 
                  cerca.lower() in (p.get('riferimento') or "").lower()]

    for prev in preventivi:
        data_f = datetime.fromisoformat(prev['created_at']).strftime("%d/%m/%Y")
        righe_db = prev.get('preventivi_righe', [])
        
        # FIX ERRORE: Gestione NoneType per totale_netto
        valore_totale = prev.get('totale_netto') if prev.get('totale_netto') is not None else 0.0
        
        with st.container(border=True):
            col_info, col_prezzo = st.columns([3, 1])
            col_info.markdown(f"**{prev['ragione_sociale_cliente']}**")
            col_info.caption(f"📅 {data_f} | Rif: {prev.get('riferimento') or '-'}")
            
            # Formattazione sicura
            col_prezzo.markdown(f"<h3 style='margin:0; text-align:right; color:#1f77b4;'>€ {valore_totale:,.2f}</h3>", unsafe_allow_html=True)
            
            # Sintesi articoli
            art_list = ", ".join([f"{r['quantita']}x {r['codice_articolo']}" for r in righe_db[:2]])
            if len(righe_db) > 2: art_list += "..."
            st.markdown(f"<small style='color: gray;'>{art_list}</small>", unsafe_allow_html=True)

            st.write("")
            btn_edit, btn_pdf = st.columns(2)
            
            if btn_edit.button("✏️ Gestisci", key=f"main_edit_{prev['id']}", use_container_width=True):
                modal_gestione(prev['id'], prev)

            # Generazione PDF
            try:
                righe_pdf = [{
                    "CODICE": r['codice_articolo'], "DESCRIZIONE": r['descrizione'], "QTA": r['quantita'],
                    "PREZZO_LORDO": r['prezzo_lordo_unitario'], "PREZZO_NETTO": r['prezzo_netto_unitario'],
                    "S1": r['sconto_1'], "S2": r['sconto_2'], "S3": r['sconto_3'],
                    "SCONTO_MERCE": r['is_sconto_merce'], "NOTA": r.get('nota_riga', "")
                } for r in righe_db]

                pdf_file = genera_pdf_ordine({"ragione_sociale": prev['ragione_sociale_cliente']}, prev, righe_pdf)
                
                btn_pdf.download_button(
                    label="📄 PDF", data=pdf_file,
                    file_name=f"Prev_{prev['numero_preventivo']}.pdf",
                    mime="application/pdf", key=f"pdf_down_{prev['id']}", use_container_width=True
                )
            except Exception as e:
                btn_pdf.error("Errore PDF")

if __name__ == "__main__":
    show_archivio()