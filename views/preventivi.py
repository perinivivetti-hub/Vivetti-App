import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime
from fpdf import FPDF
from streamlit_searchbox import st_searchbox
import io
import os
import time
import base64

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
    
    /* Bottone PDF Universale per fix iOS */
    .pdf-button {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        background-color: #ff4b4b;
        color: white !important;
        padding: 0.5rem 1rem;
        border-radius: 8px;
        width: 100%;
        font-weight: bold;
        cursor: pointer;
        border: none;
        text-align: center;
        text-decoration: none !important;
        transition: background-color 0.3s ease;
    }
    .pdf-button:hover {
        background-color: #e64141;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 1. CONNESSIONE ---
def get_supabase_client():
    url = st.secrets["connections"]["supabase"]["url"]
    key = st.secrets["connections"]["supabase"]["key"]
    return create_client(url, key)

supabase = get_supabase_client()

# --- 2. FUNZIONI DI RICERCA ---
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

def search_articles(search_term: str):
    if not search_term or len(search_term) < 3:
        return []
    res = supabase.table("listino_import")\
        .select("CODICE, DESCRIZIONE, PREZZO, SCONTO1, SCONTO2, SCONTO3")\
        .or_(f"CODICE.ilike.%{search_term}%,DESCRIZIONE.ilike.%{search_term}%")\
        .limit(20)\
        .execute()
    if not res.data: return []
    return [(f"{row['CODICE']} | {row['DESCRIZIONE'][:70]}...", row) for row in res.data]

# --- 3. UTILITY CALCOLI E PDF ---
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

def genera_pdf_ordine(cliente, testata, righe):
    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.add_page()
    logo_path = 'LogoVivetti.png'
    if os.path.exists(logo_path):
        pdf.image(logo_path, x=10, y=8, w=45) 
    
    pdf.set_font("Arial", 'B', 15)
    pdf.set_y(12)
    pdf.cell(0, 10, f"OFFERTA / ORDINE: {testata['numero_preventivo']}", ln=True, align='R')
    
    pdf.ln(18)
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 6, f"SPETT.LE CLIENTE: {cliente['ragione_sociale']}", ln=True)
    pdf.cell(100, 6, f"RIFERIMENTO: {testata['riferimento'] if testata['riferimento'] else '-'}", ln=False)
    pdf.cell(0, 6, f"DATA EMISSIONE: {datetime.now().strftime('%d/%m/%Y')}", ln=True, align='R')
    
    consegna_str = "-"
    if testata.get('data_consegna'):
        try: consegna_str = datetime.strptime(testata['data_consegna'], '%Y-%m-%d').strftime('%d/%m/%Y')
        except: consegna_str = testata['data_consegna']
            
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(100, 6, f"CONSEGNA PREVISTA: {consegna_str}", ln=True)
    pdf.ln(8)
    pdf.set_font("Arial", 'B', 8)
    pdf.set_fill_color(230, 230, 230)
    
    cols = [("CODICE", 35), ("DESCRIZIONE", 55), ("Q.TA", 10), ("PREZZO U.", 20), ("SCONTI", 20), ("NETTO U.", 20), ("TOTALE", 20)]
    for txt, w in cols: pdf.cell(w, 8, txt, 1, 0, 'C', True)
    pdf.ln()
    pdf.set_font("Arial", '', 8)

    for r in righe:
        if r.get('tipo') == 'NOTA_TESTO':
            pdf.set_font("Arial", 'B', 9)
            pdf.set_fill_color(245, 245, 245)
            pdf.multi_cell(180, 8, r['DESCRIZIONE'].upper(), border=1, align='L', fill=True)
            pdf.set_font("Arial", '', 8)
        else:
            p_l = float(r['PREZZO_LORDO'])
            p_u = 0.0 if r['SCONTO_MERCE'] else float(r['PREZZO_NETTO'])
            s_str = "OMAGGIO" if r['SCONTO_MERCE'] else format_sconti_string(r['S1'], r['S2'], r['S3'])
            y_before = pdf.get_y()
            desc_testo = r['DESCRIZIONE']
            if r.get('NOTA'): desc_testo += f"\nNote: {r['NOTA']}"
            pdf.set_xy(45, y_before)
            pdf.multi_cell(55, 5, desc_testo, border=0, align='L')
            h = max(pdf.get_y() - y_before, 8)
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
            
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(160, 10, "TOTALE NETTO (IVA ESCLUSA)", 0, 0, 'R')
    pdf.cell(30, 10, f"EUR {testata['totale_netto']:,.2f}", 0, 1, 'R')
    
    return pdf.output(dest='S').encode('latin-1', errors='replace')

# --- 4. SALVATAGGIO DB ---
def salva_preventivo_db(info_testata, righe):
    try:
        res_t = supabase.table("preventivi_testata").insert(info_testata).execute()
        id_prev = res_t.data[0]['id']
        righe_db = [{
            "id_preventivo": id_prev, 
            "codice_articolo": r.get('CODICE', 'NOTA'), 
            "descrizione": r['DESCRIZIONE'],
            "quantita": r.get('QTA', 0), 
            "prezzo_lordo_unitario": r.get('PREZZO_LORDO', 0),
            "sconto_1": r.get('S1', 0), "sconto_2": r.get('S2', 0), "sconto_3": r.get('S3', 0),
            "is_sconto_merce": r.get('SCONTO_MERCE', False), 
            "prezzo_netto_unitario": r.get('PREZZO_NETTO', 0), 
            "nota_riga": r.get('tipo', '') 
        } for r in righe]
        supabase.table("preventivi_righe").insert(righe_db).execute()
        return True, id_prev
    except Exception as e: return False, str(e)

# --- 5. INTERFACCIA PRINCIPALE ---
def show_preventivi():
    if 'righe_preventivo' not in st.session_state: st.session_state.righe_preventivo = []
    if 'temp_item' not in st.session_state: st.session_state.temp_item = None
    if 'search_key' not in st.session_state: st.session_state.search_key = 0
    if 'cliente_selezionato_obj' not in st.session_state: st.session_state.cliente_selezionato_obj = None

    user_data = st.session_state.get('user_info', {})
    st.subheader("📝 Nuovo Preventivo")

    # --- RICERCA CLIENTI ---
    with st.expander("👤 Anagrafica", expanded=not bool(st.session_state.righe_preventivo)):
        cliente_sel = st_searchbox(search_clients, placeholder="🔍 Cerca cliente in rubrica...", key="search_cliente_prev")
        if cliente_sel: st.session_state.cliente_selezionato_obj = cliente_sel
            
        c1, c2 = st.columns(2)
        data_cons = c1.date_input("Data consegna", value=None, format="DD/MM/YYYY")
        rif_ordine = c2.text_input("Riferimento", placeholder="Esempio: Cantiere Rossi, Cucina...")
        
        if st.session_state.cliente_selezionato_obj:
            cli = st.session_state.cliente_selezionato_obj
            st.success(f"Cliente Selezionato: **{cli['ragione_sociale']}**")

    st.divider()

    # --- RICERCA ARTICOLI ---
    st.subheader("🔍 Ricerca Articoli")
    col_search, col_m, col_n = st.columns([0.7, 0.15, 0.15], gap="small", vertical_alignment="bottom")
    with col_search:
        selected_article = st_searchbox(search_articles, placeholder="Scrivi almeno 3 caratteri...", key=f"search_art_{st.session_state.search_key}", clear_on_submit=True)
    with col_m:
        if st.button("➕ Manuale", use_container_width=True):
            st.session_state.temp_item = {"CODICE": "EXTRA", "DESCRIZIONE": "", "PREZZO": 0.0, "is_manual": True}
            st.rerun()
    with col_n:
        if st.button("🗒️ Nota", use_container_width=True):
            st.session_state.temp_item = {"tipo": "NOTA_TESTO", "DESCRIZIONE": ""}
            st.rerun()

    if selected_article: st.session_state.temp_item = selected_article

    # --- SCHEDA CONFIGURAZIONE RIGA ---
    if st.session_state.temp_item:
        item = st.session_state.temp_item
        with st.container():
            st.markdown('<div class="config-card">', unsafe_allow_html=True)
            if item.get("tipo") == "NOTA_TESTO":
                st.markdown("#### 🗒️ Inserisci Nota Descrittiva")
                testo_nota = st.text_area("Testo della nota (apparirà in grassetto)", value=item["DESCRIZIONE"])
                c1, c2 = st.columns(2)
                if c1.button("💾 AGGIUNGI NOTA", type="primary", use_container_width=True):
                    st.session_state.righe_preventivo.append({"tipo": "NOTA_TESTO", "DESCRIZIONE": testo_nota})
                    st.session_state.temp_item = None; st.session_state.search_key += 1; st.rerun()
                if c2.button("Annulla", use_container_width=True): st.session_state.temp_item = None; st.rerun()
            else:
                st.markdown(f"#### ⚙️ Configura Articolo")
                is_manual = item.get("is_manual", False)
                if is_manual:
                    c_m1, c_m2 = st.columns([1, 2])
                    item["CODICE"] = c_m1.text_input("Codice", value=item["CODICE"])
                    item["DESCRIZIONE"] = c_m2.text_input("Descrizione", value=item["DESCRIZIONE"])
                else: st.write(f"**Codice:** `{item['CODICE']}` | **Descrizione:** {item['DESCRIZIONE']}")
                
                col_p1, col_p2 = st.columns(2)
                pl = col_p1.number_input("Prezzo Unitario", value=float(item.get('PREZZO', item.get('PREZZO_LORDO', 0.0))), format="%.2f")
                qta_val = col_p2.number_input("Quantità", min_value=1, value=int(item.get('QTA', 1)))
                
                metodo = st.radio("Metodo Calcolo Prezzo:", ["Sconti %", "Netto Fisso"], horizontal=True)
                if metodo == "Sconti %":
                    cs1, cs2, cs3 = st.columns(3)
                    s1 = cs1.number_input("S1 %", value=float(item.get('SCONTO1', item.get('S1', 0))))
                    s2 = cs2.number_input("S2 %", value=float(item.get('SCONTO2', item.get('S1', 0)))) # Corretto S1->S2
                    s3 = cs3.number_input("S3 %", value=float(item.get('SCONTO3', item.get('S1', 0)))) # Corretto S1->S3
                    pn = calcola_netto(pl, s1, s2, s3)
                else:
                    pn = st.number_input("Netto Unitario (€)", value=float(item.get('PREZZO_NETTO', pl)), format="%.2f")
                    s1, s2, s3 = 0, 0, 0
                
                nota_r = st.text_input("Nota interna per questa riga", value=item.get('NOTA', ""))
                omaggio = st.checkbox("Articolo in Omaggio", value=item.get('SCONTO_MERCE', False))
                if omaggio: pn = 0
                st.info(f"💰 Totale Netto Riga: € {pn * qta_val:,.2f}")
                
                cadd, cann = st.columns(2)
                if cadd.button("🚀 AGGIUNGI AL PREVENTIVO", type="primary", use_container_width=True):
                    st.session_state.righe_preventivo.append({
                        "CODICE": item["CODICE"], "DESCRIZIONE": item["DESCRIZIONE"], 
                        "PREZZO_LORDO": pl, "PREZZO_NETTO": pn, "QTA": qta_val, 
                        "SCONTO_MERCE": omaggio, "S1": s1, "S2": s2, "S3": s3, "NOTA": nota_r
                    })
                    st.session_state.temp_item = None; st.session_state.search_key += 1; st.rerun()
                if cann.button("Annulla", use_container_width=True): st.session_state.temp_item = None; st.rerun()
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
                        st.session_state.temp_item = st.session_state.righe_preventivo.pop(idx); st.rerun()
                    if b2.button("🗑️", key=f"del_{idx}"):
                        st.session_state.righe_preventivo.pop(idx); st.rerun()

        st.divider()
        cn, cm = st.columns([2, 1])
        note_finali = cn.text_area("Note finali (condizioni...)")
        cm.metric("TOTALE NETTO", f"€ {tot_n:,.2f}")
        
        num_prev = f"PREV-{datetime.now().strftime('%y%m%d-%H%M')}"
        cli_obj = st.session_state.cliente_selezionato_obj
        testata = {
            "id_cliente": cli_obj['id'] if cli_obj else None, 
            "ragione_sociale_cliente": cli_obj['ragione_sociale'] if cli_obj else "", 
            "id_agente": str(user_data.get("agente_corrispondente", "")), 
            "totale_netto": tot_n, "note_generali": note_finali, 
            "data_consegna": str(data_cons) if data_cons else None, 
            "riferimento": rif_ordine, "numero_preventivo": num_prev
        }

        # --- SEZIONE PDF E SALVATAGGIO ---
        cp, cs = st.columns(2)
        if cli_obj:
            try:
                # Generazione dei dati PDF
                pdf_b = genera_pdf_ordine(cli_obj, testata, st.session_state.righe_preventivo)
                filename = f"{num_prev}_{cli_obj['ragione_sociale'][:15]}.pdf"
                b64 = base64.b64encode(pdf_b).decode()
                
                # HTML per il link "Safe" con icona e testo richiesto
                pdf_link_html = f"""
                    <div style="padding-top: 10px;">
                        <a href="data:application/pdf;base64,{b64}" 
                           target="_blank" 
                           download="{filename}" 
                           class="pdf-link" 
                           style="color: #ff4b4b; text-decoration: none; font-weight: bold; display: flex; align-items: center; gap: 10px;">
                            <span style="font-size: 24px;">📄</span> 
                            <span style="font-size: 18px;">GENERA PDF</span>
                        </a>
                    </div>
                """
                cp.markdown(pdf_link_html, unsafe_allow_html=True)
                
            except Exception as e: 
                cp.error(f"Errore PDF: {e}")

        if cs.button("💾 SALVA E CHIUDI", type="primary", use_container_width=True):
            if not cli_obj: st.error("Seleziona un cliente!")
            else:
                ok, res = salva_preventivo_db(testata, st.session_state.righe_preventivo)
                if ok:
                    st.success("✅ Salvato!"); time.sleep(1.5); st.session_state.righe_preventivo = []; st.session_state.cliente_selezionato_obj = None; st.rerun()
                else: st.error(f"Errore: {res}")

if __name__ == "__main__":
    show_preventivi()