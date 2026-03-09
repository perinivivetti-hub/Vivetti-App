import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime
from fpdf import FPDF
from streamlit_searchbox import st_searchbox
import io
import os
import time

# --- 1. CONNESSIONE E CARICAMENTO DATI ---
def get_supabase_client():
    url = st.secrets["connections"]["supabase"]["url"]
    key = st.secrets["connections"]["supabase"]["key"]
    return create_client(url, key)

@st.cache_data(ttl=600)
def get_base_data():
    supabase = get_supabase_client()
    clienti_res = supabase.table("rubrica_clienti").select("*").execute()
    
    all_listino_rows = []
    step, start = 1000, 0
    while True:
        res = supabase.table("listino_import")\
            .select("CODICE, DESCRIZIONE, PREZZO, SCONTO1, SCONTO2, SCONTO3")\
            .range(start, start + step - 1)\
            .execute()
        if not res.data: break
        all_listino_rows.extend(res.data)
        start += step
        if start >= 40000: break 
            
    df_l = pd.DataFrame(all_listino_rows)
    df_c = pd.DataFrame(clienti_res.data)
    
    if not df_l.empty:
        for col in ["CODICE", "DESCRIZIONE"]:
            df_l[col] = df_l[col].astype(str).fillna("").str.strip()
        df_l['PREZZO'] = pd.to_numeric(df_l['PREZZO'], errors='coerce').fillna(0.0)
        
    return df_c, df_l

def carica_preventivo(id_preventivo):
    supabase = get_supabase_client()
    testata = supabase.table("preventivi_testata").select("*").eq("id", id_preventivo).single().execute()
    righe = supabase.table("preventivi_righe").select("*").eq("id_preventivo", id_preventivo).order("id").execute()
    
    session_righe = []
    for r in righe.data:
        if r['nota_riga'] == 'NOTA_TESTO':
            session_righe.append({"tipo": "NOTA_TESTO", "DESCRIZIONE": r['descrizione']})
        else:
            session_righe.append({
                "CODICE": r['codice_articolo'], "DESCRIZIONE": r['descrizione'],
                "PREZZO_LORDO": float(r['prezzo_lordo_unitario']), "PREZZO_NETTO": float(r['prezzo_netto_unitario']),
                "QTA": int(r['quantita']), "SCONTO_MERCE": bool(r['is_sconto_merce']),
                "S1": float(r['sconto_1']), "S2": float(r['sconto_2']), "S3": float(r['sconto_3']),
                "NOTA": r['nota_riga'] if r['nota_riga'] != 'NOTA_TESTO' else ""
            })
    return testata.data, session_righe

# --- 2. UTILITY PDF ---
def format_sconti_string(s1, s2, s3):
    parts = []
    for s in [s1, s2, s3]:
        try:
            val = float(s)
            if val > 0: parts.append(f"{val:g}")
        except: continue
    return "+".join(parts) if parts else "-"

def calcola_netto(listino, s1, s2, s3):
    return float(listino) * (1 - float(s1 or 0)/100) * (1 - float(s2 or 0)/100) * (1 - float(s3 or 0)/100)

def genera_pdf_ordine(cliente_ragione_sociale, testata, righe):
    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.add_page()
    logo_path = 'LogoVivetti.png'
    if os.path.exists(logo_path): pdf.image(logo_path, x=10, y=8, w=45) 
    pdf.set_font("Arial", 'B', 15); pdf.set_y(12)
    pdf.cell(0, 10, f"OFFERTA / ORDINE: {testata['numero_preventivo']}", ln=True, align='R')
    pdf.ln(18); pdf.set_font("Arial", '', 10)
    pdf.cell(0, 6, f"SPETT.LE CLIENTE: {cliente_ragione_sociale}", ln=True)
    pdf.cell(100, 6, f"RIFERIMENTO: {testata['riferimento'] if testata['riferimento'] else '-'}", ln=False)
    pdf.cell(0, 6, f"DATA: {datetime.now().strftime('%d/%m/%Y')}", ln=True, align='R')
    pdf.ln(8); pdf.set_font("Arial", 'B', 8); pdf.set_fill_color(230, 230, 230)
    cols = [("CODICE", 35), ("DESCRIZIONE", 55), ("Q.TA", 10), ("PREZZO U.", 20), ("SCONTI", 20), ("NETTO U.", 20), ("TOTALE", 20)]
    for txt, w in cols: pdf.cell(w, 8, txt, 1, 0, 'C', True)
    pdf.ln(); pdf.set_font("Arial", '', 8)
    for r in righe:
        if r.get('tipo') == 'NOTA_TESTO':
            pdf.set_font("Arial", 'B', 9); pdf.set_fill_color(245, 245, 245)
            pdf.multi_cell(180, 8, r['DESCRIZIONE'].upper(), border=1, align='L', fill=True)
            pdf.set_font("Arial", '', 8)
        else:
            p_l, p_u = float(r['PREZZO_LORDO']), (0.0 if r['SCONTO_MERCE'] else float(r['PREZZO_NETTO']))
            s_str = "OMAGGIO" if r['SCONTO_MERCE'] else format_sconti_string(r['S1'], r['S2'], r['S3'])
            y_before = pdf.get_y(); desc_testo = r['DESCRIZIONE']
            if r.get('NOTA'): desc_testo += f"\nNote: {r['NOTA']}"
            pdf.set_xy(45, y_before); pdf.multi_cell(55, 5, desc_testo, border=0, align='L')
            h = max(pdf.get_y() - y_before, 8); pdf.set_xy(10, y_before)
            pdf.cell(35, h, str(r['CODICE']), border=1, align='C')
            pdf.set_xy(45, y_before); pdf.multi_cell(55, 5, desc_testo, border=1, align='L')
            pdf.set_xy(100, y_before); pdf.cell(10, h, str(r['QTA']), border=1, align='C')
            pdf.cell(20, h, f"{p_l:,.2f}", border=1, align='R'); pdf.cell(20, h, s_str, border=1, align='C')
            pdf.cell(20, h, f"{p_u:,.2f}", border=1, align='R'); pdf.cell(20, h, f"{(p_u * r['QTA']):,.2f}", border=1, ln=1, align='R')
    pdf.ln(5); pdf.set_font("Arial", 'B', 12)
    pdf.cell(160, 10, "TOTALE NETTO (IVA ESCLUSA)", 0, 0, 'R')
    pdf.cell(30, 10, f"EUR {testata['totale_netto']:,.2f}", 0, 1, 'R')
    return pdf.output(dest='S').encode('latin-1', errors='replace')

# --- 3. AGGIORNAMENTO DB ---
def aggiorna_preventivo_db(id_preventivo, info_testata, righe):
    supabase = get_supabase_client()
    try:
        supabase.table("preventivi_testata").update(info_testata).eq("id", id_preventivo).execute()
        supabase.table("preventivi_righe").delete().eq("id_preventivo", id_preventivo).execute()
        righe_db = [{
            "id_preventivo": id_preventivo, "codice_articolo": r.get('CODICE', 'NOTA'), "descrizione": r['DESCRIZIONE'],
            "quantita": r.get('QTA', 0), "prezzo_lordo_unitario": r.get('PREZZO_LORDO', 0),
            "sconto_1": r.get('S1', 0), "sconto_2": r.get('S2', 0), "sconto_3": r.get('S3', 0),
            "is_sconto_merce": r.get('SCONTO_MERCE', False), "prezzo_netto_unitario": r.get('PREZZO_NETTO', 0), 
            "nota_riga": r.get('tipo', r.get('NOTA', ''))
        } for r in righe]
        supabase.table("preventivi_righe").insert(righe_db).execute()
        return True
    except Exception as e: return str(e)

# --- 4. FUNZIONE PRINCIPALE ---
def show_archivio():
    st.markdown("""
        <style>
        .config-card { background-color: #f1f3f6; padding: 20px; border-radius: 12px; border-left: 6px solid #ff4b4b; margin: 15px 0; }
        .stButton button { border-radius: 8px; font-weight: bold; }
        </style>
        """, unsafe_allow_html=True)
        
    st.subheader("📁 Archivio Preventivi")
    
    if 'edit_id' not in st.session_state: st.session_state.edit_id = None
    if 'righe_archivio' not in st.session_state: st.session_state.righe_archivio = []
    if 'temp_item_arc' not in st.session_state: st.session_state.temp_item_arc = None
    if 'search_key_arc' not in st.session_state: st.session_state.search_key_arc = 500

    df_clienti, df_listino = get_base_data()
    user_data = st.session_state.get('user_info', {})
    supabase = get_supabase_client()

    # --- VISTA LISTA ---
    if st.session_state.edit_id is None:
        def search_clienti_arc(search_term: str):
            if not search_term: return []
            mask = df_clienti['ragione_sociale'].str.contains(search_term, case=False, na=False)
            return [(r['ragione_sociale'], r['id']) for _, r in df_clienti[mask].iterrows()]

        st.write("🔍 Filtra per cliente:")
        filtro_cliente_id = st_searchbox(search_clienti_arc, key="filtro_cliente_archivio")

        query = supabase.table("preventivi_testata").select("*, rubrica_clienti(ragione_sociale)")
        if user_data.get("ruolo") == "agente":
            query = query.eq("id_agente", str(user_data.get("agente_corrispondente")))
        if filtro_cliente_id:
            query = query.eq("id_cliente", filtro_cliente_id)
        
        prev_data = query.order("created_at", desc=True).execute()
        
        if not prev_data.data:
            st.info("Nessun preventivo trovato.")
        else:
            for row in prev_data.data:
                with st.expander(f"📄 {row['numero_preventivo']} - {row['ragione_sociale_cliente']} (€ {row['totale_netto']:,.2f})"):
                    col1, col2, col3, col4 = st.columns([1.5, 1, 1, 1])
                    col1.caption(f"Rif: {row['riferimento'] or '-'} | Data: {row['created_at'][:10]}")
                    
                    if col2.button("✏️ MODIFICA", key=f"ed_{row['id']}", use_container_width=True):
                        testata, righe = carica_preventivo(row['id'])
                        st.session_state.edit_id = row['id']
                        st.session_state.edit_testata = testata
                        st.session_state.righe_archivio = righe
                        st.rerun()
                    
                    try:
                        _, r_pdf = carica_preventivo(row['id'])
                        pdf_rapido = genera_pdf_ordine(row['ragione_sociale_cliente'], row, r_pdf)
                        col3.download_button("📄 PDF", data=pdf_rapido, file_name=f"{row['numero_preventivo']}.pdf", use_container_width=True, key=f"pdf_q_{row['id']}")
                    except: col3.error("Errore PDF")

                    if col4.button("🗑️ ELIMINA", key=f"del_{row['id']}", use_container_width=True):
                        supabase.table("preventivi_testata").delete().eq("id", row['id']).execute()
                        st.rerun()

    # --- VISTA MODIFICA ---
    else:
        st.info(f"Modifica: **{st.session_state.edit_testata['numero_preventivo']}**")
        if st.button("⬅️ Chiudi senza salvare"):
            st.session_state.edit_id = None
            st.rerun()
        
        st.divider()
        
        with st.expander("👤 Dati Preventivo", expanded=False):
            cliente_attuale = next((c for c in df_clienti.to_dict('records') if c['id'] == st.session_state.edit_testata['id_cliente']), None)
            cliente_sel = st.selectbox("Cliente", options=df_clienti.to_dict('records'), format_func=lambda x: f"{x['ragione_sociale']}", index=df_clienti.to_dict('records').index(cliente_attuale) if cliente_attuale else None)
            c_test1, c_test2 = st.columns(2)
            try: d_init = datetime.strptime(st.session_state.edit_testata['data_consegna'], '%Y-%m-%d').date() if st.session_state.edit_testata['data_consegna'] else None
            except: d_init = None
            data_cons = c_test1.date_input("Consegna", value=d_init)
            rif_ordine = c_test2.text_input("Riferimento", value=st.session_state.edit_testata.get('riferimento', ''))

        def search_articles(search_term: str):
            if not search_term or len(search_term) < 3: return []
            mask = (df_listino['DESCRIZIONE'].str.contains(search_term, case=False, na=False)) | (df_listino['CODICE'].str.contains(search_term, case=False, na=False))
            return [(f"{row['CODICE']} | {row['DESCRIZIONE'][:70]}...", row.to_dict()) for _, row in df_listino[mask].head(15).iterrows()]

        cs, cm, cn = st.columns([0.7, 0.15, 0.15], vertical_alignment="bottom")
        with cs: sel_art = st_searchbox(search_articles, placeholder="Aggiungi riga...", key=f"search_arc_{st.session_state.search_key_arc}")
        if cm.button("➕ Manuale", use_container_width=True): st.session_state.temp_item_arc = {"CODICE": "EXTRA", "DESCRIZIONE": "", "PREZZO": 0.0, "is_manual": True}; st.rerun()
        if cn.button("🗒️ Nota", use_container_width=True): st.session_state.temp_item_arc = {"tipo": "NOTA_TESTO", "DESCRIZIONE": ""}; st.rerun()

        if sel_art: st.session_state.temp_item_arc = sel_art

        if st.session_state.temp_item_arc:
            item = st.session_state.temp_item_arc
            with st.container():
                st.markdown('<div class="config-card">', unsafe_allow_html=True)
                if item.get("tipo") == "NOTA_TESTO":
                    st.markdown("#### 🗒️ Inserisci Nota")
                    t_n = st.text_area("Testo Nota", value=item["DESCRIZIONE"])
                    if st.button("💾 AGGIUNGI NOTA"):
                        st.session_state.righe_archivio.append({"tipo": "NOTA_TESTO", "DESCRIZIONE": t_n})
                        st.session_state.temp_item_arc = None; st.session_state.search_key_arc += 1; st.rerun()
                else:
                    st.markdown("#### ⚙️ Configura Riga")
                    if item.get("is_manual"):
                        item["CODICE"] = st.text_input("Codice", value=item["CODICE"])
                        item["DESCRIZIONE"] = st.text_input("Descrizione", value=item["DESCRIZIONE"])
                    else: st.write(f"**{item['CODICE']}** - {item['DESCRIZIONE']}")
                    cp1, cp2 = st.columns(2)
                    pl = cp1.number_input("Prezzo Lordo", value=float(item.get('PREZZO', item.get('PREZZO_LORDO', 0.0))))
                    qta = cp2.number_input("Q.tà", min_value=1, value=int(item.get('QTA', 1)))
                    cs1, cs2, cs3 = st.columns(3)
                    s1, s2, s3 = cs1.number_input("S1", value=float(item.get('S1', 0))), cs2.number_input("S2", value=float(item.get('S2', 0))), cs3.number_input("S3", value=float(item.get('S3', 0)))
                    pn = calcola_netto(pl, s1, s2, s3)
                    if st.button("🚀 SALVA"):
                        st.session_state.righe_archivio.append({"CODICE": item["CODICE"], "DESCRIZIONE": item["DESCRIZIONE"], "PREZZO_LORDO": pl, "PREZZO_NETTO": pn, "QTA": qta, "SCONTO_MERCE": False, "S1": s1, "S2": s2, "S3": s3, "NOTA": ""})
                        st.session_state.temp_item_arc = None; st.session_state.search_key_arc += 1; st.rerun()
                if st.button("Annulla"): st.session_state.temp_item_arc = None; st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

        tot_n = 0.0
        for idx, r in enumerate(st.session_state.righe_archivio):
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 1, 0.8])
                if r.get('tipo') == 'NOTA_TESTO':
                    c1.markdown(f"**🗒️ NOTA:** {r['DESCRIZIONE']}")
                    c2.write("-")
                else:
                    val = r['PREZZO_NETTO'] * r['QTA']
                    tot_n += val
                    c1.markdown(f"**{r['CODICE']}** - {r['DESCRIZIONE']}")
                    c1.caption(f"Qta: {r['QTA']} | Netto: € {r['PREZZO_NETTO']:,.2f}")
                    c2.markdown(f"**€ {val:,.2f}**")
                
                b1, b2 = c3.columns(2)
                if b1.button("✏️", key=f"e_{idx}"): st.session_state.temp_item_arc = st.session_state.righe_archivio.pop(idx); st.rerun()
                if b2.button("🗑️", key=f"d_{idx}"): st.session_state.righe_archivio.pop(idx); st.rerun()

        st.divider()
        st.metric("TOTALE NETTO", f"€ {tot_n:,.2f}")
        
        if st.button("💾 SALVA MODIFICHE DEFINITIVE", type="primary", use_container_width=True):
            data_db = str(data_cons) if data_cons else None
            upd = {
                "id_cliente": cliente_sel['id'], 
                "ragione_sociale_cliente": cliente_sel['ragione_sociale'], 
                "totale_netto": tot_n, 
                "note_generali": st.session_state.edit_testata.get('note_generali', ''), 
                "data_consegna": data_db, 
                "riferimento": rif_ordine
            }
            res = aggiorna_preventivo_db(st.session_state.edit_id, upd, st.session_state.righe_archivio)
            if res is True:
                st.success("✅ Preventivo modificato con successo!")
                time.sleep(2)
                st.session_state.edit_id = None
                st.rerun()
            else: st.error(f"Errore: {res}")