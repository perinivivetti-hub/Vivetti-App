import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime
from fpdf import FPDF
from streamlit_searchbox import st_searchbox
import io
import os
import time

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Vivetti - Nuovo Preventivo", layout="wide")

st.markdown("""
    <style>
    .main h1 { font-size: 1.8rem !important; margin-bottom: 0.5rem !important; }
    .stMetric { background-color: #f8f9fa; padding: 10px; border-radius: 10px; border: 1px solid #ddd; }
    .config-card {
        background-color: #f1f3f6; padding: 20px; border-radius: 12px; 
        border-left: 6px solid #ff4b4b; margin: 15px 0;
    }
    .note-card {
        background-color: #fff9db; padding: 15px; border-radius: 8px;
        border-left: 5px solid #fcc419; margin: 5px 0;
    }
    .stButton button { font-weight: bold; border-radius: 8px; }
    </style>
    """, unsafe_allow_html=True)

# --- 1. CONNESSIONE E CARICAMENTO DATI ---
def get_supabase_client():
    url = st.secrets["connections"]["supabase"]["url"]
    key = st.secrets["connections"]["supabase"]["key"]
    return create_client(url, key)

@st.cache_data(ttl=600)
def get_data_for_form():
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

# --- 2. UTILITY ---
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

# --- 3. GENERAZIONE PDF (CORRETTA PER LE NOTE) ---
def genera_pdf_ordine(cliente, testata, righe):
    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.add_page()
    logo_path = 'LogoVivetti.png'
    if os.path.exists(logo_path):
        pdf.image(logo_path, x=10, y=8, w=45) 
    pdf.set_font("Arial", 'B', 15); pdf.set_y(12)
    pdf.cell(0, 10, f"OFFERTA / ORDINE: {testata['numero_preventivo']}", ln=True, align='R')
    pdf.ln(18); pdf.set_font("Arial", '', 10)
    pdf.cell(0, 6, f"SPETT.LE CLIENTE: {cliente['ragione_sociale']}", ln=True)
    pdf.cell(100, 6, f"RIFERIMENTO: {testata['riferimento'] if testata['riferimento'] else '-'}", ln=False)
    pdf.cell(0, 6, f"DATA: {datetime.now().strftime('%d/%m/%Y')}", ln=True, align='R')
    pdf.ln(8); pdf.set_font("Arial", 'B', 8); pdf.set_fill_color(230, 230, 230)
    
    cols = [("CODICE", 35), ("DESCRIZIONE", 55), ("Q.TA", 10), ("PREZZO U.", 20), ("SCONTI", 20), ("NETTO U.", 20), ("TOTALE", 20)]
    for txt, w in cols: pdf.cell(w, 8, txt, 1, 0, 'C', True)
    pdf.ln(); pdf.set_font("Arial", '', 8)

    for r in righe:
        if r.get('tipo') == 'NOTA_TESTO':
            # Riga Nota: pulita, senza codice, a tutta larghezza
            pdf.set_font("Arial", 'B', 9)
            pdf.set_fill_color(245, 245, 245)
            # Stampiamo solo il testo digitato, occupando l'intera riga della tabella (180mm)
            pdf.multi_cell(180, 8, r['DESCRIZIONE'].upper(), border=1, align='L', fill=True)
            pdf.set_font("Arial", '', 8)
        else:
            # Riga Articolo standard
            p_l = float(r['PREZZO_LORDO']); p_u = 0.0 if r['SCONTO_MERCE'] else float(r['PREZZO_NETTO'])
            s_str = "OMAGGIO" if r['SCONTO_MERCE'] else format_sconti_string(r['S1'], r['S2'], r['S3'])
            
            y_before = pdf.get_y()
            desc_testo = r['DESCRIZIONE']
            if r.get('NOTA'): desc_testo += f"\nNote: {r['NOTA']}"
            
            # Calcolo altezza dinamica per la descrizione
            pdf.set_xy(45, y_before)
            pdf.multi_cell(55, 5, desc_testo, border=0, align='L')
            h = max(pdf.get_y() - y_before, 8)
            
            # Disegno celle
            pdf.set_xy(10, y_before)
            pdf.cell(35, h, str(r['CODICE']), border=1, align='C')
            pdf.set_xy(45, y_before)
            pdf.multi_cell(55, 5, desc_testo, border=1, align='L')
            pdf.set_xy(100, y_before)
            pdf.cell(10, h, str(r['QTA']), border=1, align='C')
            pdf.cell(20, h, f"{p_l:,.2f}", border=1, align='R')
            pdf.cell(20, h, s_str, border=1, align='C')
            pdf.cell(20, h, f"{p_u:,.2f}", border=1, align='R')
            pdf.cell(20, h, f"{(p_u * r['QTA']):,.2f}", border=1, ln=1, align='R')
            
    pdf.ln(5); pdf.set_font("Arial", 'B', 12)
    pdf.cell(160, 10, "TOTALE NETTO (IVA ESCLUSA)", 0, 0, 'R')
    pdf.cell(30, 10, f"EUR {testata['totale_netto']:,.2f}", 0, 1, 'R')
    return pdf.output(dest='S').encode('latin-1', errors='replace')

# --- 4. SALVATAGGIO DB ---
def salva_preventivo_db(info_testata, righe):
    supabase = get_supabase_client()
    try:
        res_t = supabase.table("preventivi_testata").insert(info_testata).execute()
        id_prev = res_t.data[0]['id']
        righe_db = [{
            "id_preventivo": id_prev, 
            "codice_articolo": r.get('CODICE', 'NOTA'), 
            "descrizione": r['DESCRIZIONE'],
            "quantita": r.get('QTA', 0), "prezzo_lordo_unitario": r.get('PREZZO_LORDO', 0),
            "sconto_1": r.get('S1', 0), "sconto_2": r.get('S2', 0), "sconto_3": r.get('S3', 0),
            "is_sconto_merce": r.get('SCONTO_MERCE', False), 
            "prezzo_netto_unitario": r.get('PREZZO_NETTO', 0), 
            "nota_riga": r.get('tipo', '') 
        } for r in righe]
        supabase.table("preventivi_righe").insert(righe_db).execute()
        return True, id_prev
    except Exception as e: return False, str(e)

# --- 5. INTERFACCIA ---
def show_preventivi():
    if 'righe_preventivo' not in st.session_state: st.session_state.righe_preventivo = []
    if 'temp_item' not in st.session_state: st.session_state.temp_item = None
    if 'search_key' not in st.session_state: st.session_state.search_key = 0

    df_clienti, df_listino = get_data_for_form()
    user_data = st.session_state.get('user_info', {})

    st.subheader("📝 Nuovo Preventivo")

    with st.expander("👤 Anagrafica", expanded=not bool(st.session_state.righe_preventivo)):
        clienti_filtrati = df_clienti
        if user_data.get("ruolo") == "agente":
            ag_id = str(user_data.get("agente_corrispondente"))
            clienti_filtrati = df_clienti[df_clienti["id_agente"].astype(str) == ag_id]
        cliente_sel = st.selectbox("Cliente", options=clienti_filtrati.to_dict('records'), 
                                    format_func=lambda x: f"{x['ragione_sociale']} ({x.get('citta', '')})", index=None)
        c1, c2 = st.columns(2)
        data_cons = c1.date_input("Data consegna", value=None, format="DD/MM/YYYY")
        rif_ordine = c2.text_input("Riferimento", placeholder="Cantiere...")

    st.divider()

    # --- RICERCA E AZIONI ---
    st.subheader("🔍 Ricerca Articoli")
    
    def search_articles(search_term: str):
        if not search_term or len(search_term) < 3: return []
        mask = (df_listino['DESCRIZIONE'].str.contains(search_term, case=False, na=False)) | \
               (df_listino['CODICE'].str.contains(search_term, case=False, na=False))
        results = df_listino[mask].head(15)
        return [(f"{row['CODICE']} | {row['DESCRIZIONE'][:70]}...", row.to_dict()) for _, row in results.iterrows()]

    col_search, col_m, col_n = st.columns([0.7, 0.15, 0.15], gap="small", vertical_alignment="bottom")
    
    with col_search:
        selected_article = st_searchbox(search_articles, placeholder="Cerca codice o descrizione...", 
                                        key=f"search_widget_{st.session_state.search_key}", clear_on_submit=True)

    with col_m:
        if st.button("➕ Manuale", use_container_width=True):
            st.session_state.temp_item = {"CODICE": "EXTRA", "DESCRIZIONE": "", "PREZZO": 0.0, "is_manual": True}
            st.rerun()
            
    with col_n:
        if st.button("🗒️ Nota", use_container_width=True):
            st.session_state.temp_item = {"tipo": "NOTA_TESTO", "DESCRIZIONE": ""}
            st.rerun()

    if selected_article:
        st.session_state.temp_item = selected_article

    # --- SCHEDA CONFIGURAZIONE ---
    if st.session_state.temp_item:
        item = st.session_state.temp_item
        with st.container():
            st.markdown('<div class="config-card">', unsafe_allow_html=True)
            
            if item.get("tipo") == "NOTA_TESTO":
                st.markdown("#### 🗒️ Inserisci Nota Descrittiva")
                testo_nota = st.text_area("Testo della nota (apparirà a tutta larghezza)", value=item["DESCRIZIONE"])
                c1, c2 = st.columns(2)
                if c1.button("💾 AGGIUNGI NOTA", type="primary", use_container_width=True):
                    st.session_state.righe_preventivo.append({"tipo": "NOTA_TESTO", "DESCRIZIONE": testo_nota})
                    st.session_state.temp_item = None; st.session_state.search_key += 1; st.rerun()
                if c2.button("Annulla", use_container_width=True):
                    st.session_state.temp_item = None; st.rerun()
            
            else:
                st.markdown(f"#### ⚙️ Configura Articolo")
                is_manual = item.get("is_manual", False)
                if is_manual:
                    c_m1, c_m2 = st.columns([1, 2])
                    item["CODICE"] = c_m1.text_input("Codice", value=item["CODICE"])
                    item["DESCRIZIONE"] = c_m2.text_input("Descrizione", value=item["DESCRIZIONE"])
                else:
                    st.write(f"**Codice:** `{item['CODICE']}`")
                    st.write(f"**Descrizione:** {item['DESCRIZIONE']}")
                
                col_p1, col_p2 = st.columns(2)
                pl = col_p1.number_input("Prezzo Unitario (€)", value=float(item.get('PREZZO', item.get('PREZZO_LORDO', 0.0))), step=0.01, format="%.2f")
                qta_val = col_p2.number_input("Q.tà", min_value=1, value=int(item.get('QTA', 1)))
                
                metodo = st.radio("Metodo Prezzo:", ["Sconti %", "Netto Fisso"], horizontal=True)
                if metodo == "Sconti %":
                    cs1, cs2, cs3 = st.columns(3)
                    s1 = cs1.number_input("S1 %", value=float(item.get('SCONTO1', item.get('S1', 0))))
                    s2 = cs2.number_input("S2 %", value=float(item.get('SCONTO2', item.get('S2', 0))))
                    s3 = cs3.number_input("S3 %", value=float(item.get('SCONTO3', item.get('S3', 0))))
                    pn = calcola_netto(pl, s1, s2, s3)
                else:
                    pn = st.number_input("Netto Unitario (€)", value=float(item.get('PREZZO_NETTO', pl)), step=0.01, format="%.2f")
                    s1, s2, s3 = 0, 0, 0
                
                nota_r = st.text_input("Nota riga", value=item.get('NOTA', ""))
                omaggio = st.checkbox("Omaggio", value=item.get('SCONTO_MERCE', False))
                if omaggio: pn = 0
                
                st.info(f"💰 Totale Netto Riga: € {pn * qta_val:,.2f}")
                cadd, cann = st.columns(2)
                if cadd.button("🚀 AGGIUNGI AL PREVENTIVO", type="primary", use_container_width=True):
                    st.session_state.righe_preventivo.append({
                        "CODICE": item["CODICE"], "DESCRIZIONE": item["DESCRIZIONE"], "PREZZO_LORDO": pl, 
                        "PREZZO_NETTO": pn, "QTA": qta_val, "SCONTO_MERCE": omaggio, "S1": s1, "S2": s2, "S3": s3, "NOTA": nota_r
                    })
                    st.session_state.temp_item = None; st.session_state.search_key += 1; st.rerun()
                if cann.button("Annulla", use_container_width=True):
                    st.session_state.temp_item = None; st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    # --- RIEPILOGO ---
    if st.session_state.righe_preventivo:
        st.subheader("📊 Riepilogo Preventivo")
        tot_n = 0.0
        for idx, riga in enumerate(st.session_state.righe_preventivo):
            if riga.get('tipo') == 'NOTA_TESTO':
                with st.container():
                    st.markdown(f'<div class="note-card"><b>🗒️ NOTA:</b> {riga["DESCRIZIONE"]}</div>', unsafe_allow_html=True)
                    col_b = st.columns([9, 0.5, 0.5])
                    if col_b[1].button("✏️", key=f"edit_n_{idx}"):
                        st.session_state.temp_item = st.session_state.righe_preventivo.pop(idx); st.rerun()
                    if col_b[2].button("🗑️", key=f"del_n_{idx}"):
                        st.session_state.righe_preventivo.pop(idx); st.rerun()
            else:
                with st.container(border=True):
                    ci, cv, c_btns = st.columns([3, 1, 0.8])
                    val_r = 0 if riga['SCONTO_MERCE'] else (riga['PREZZO_NETTO'] * riga['QTA'])
                    tot_n += val_r
                    ci.markdown(f"**{riga['CODICE']}** - {riga['DESCRIZIONE']}")
                    ci.caption(f"Qta: {riga['QTA']} | Sconti: {format_sconti_string(riga['S1'], riga['S2'], riga['S3'])}")
                    cv.markdown(f"**€ {val_r:,.2f}**")
                    b1, b2 = c_btns.columns(2)
                    if b1.button("✏️", key=f"edit_{idx}"):
                        edit_item = st.session_state.righe_preventivo.pop(idx); st.session_state.temp_item = edit_item; st.rerun()
                    if b2.button("🗑️", key=f"del_{idx}"):
                        st.session_state.righe_preventivo.pop(idx); st.rerun()

        st.divider()
        cn, cm = st.columns([2, 1])
        note_finali = cn.text_area("Note finali (piè di pagina)")
        cm.metric("TOTALE NETTO", f"€ {tot_n:,.2f}")
        
        num_prev = f"PREV-{datetime.now().strftime('%y%m%d-%H%M')}"
        testata = {"id_cliente": cliente_sel['id'] if cliente_sel else None, "ragione_sociale_cliente": cliente_sel['ragione_sociale'] if cliente_sel else "", "id_agente": str(user_data.get("agente_corrispondente")), "totale_netto": tot_n, "note_generali": note_finali, "data_consegna": str(data_cons) if data_cons else None, "riferimento": rif_ordine, "numero_preventivo": num_prev}

        cp, cs = st.columns(2)
        if cliente_sel:
            try:
                pdf_b = genera_pdf_ordine(cliente_sel, testata, st.session_state.righe_preventivo)
                cp.download_button("📄 SCARICA PDF", data=pdf_b, file_name=f"{num_prev}.pdf", mime="application/pdf", use_container_width=True)
            except: cp.error("Errore PDF")
        if cs.button("💾 SALVA E CHIUDI", type="primary", use_container_width=True):
            if not cliente_sel: st.error("Seleziona un cliente!")
            else:
                ok, res = salva_preventivo_db(testata, st.session_state.righe_preventivo)
                if ok:
                    st.success("Preventivo Salvato!"); time.sleep(1.5); st.session_state.righe_preventivo = []; st.rerun()
                else: st.error(f"Errore: {res}")

if __name__ == "__main__":
    show_preventivi()