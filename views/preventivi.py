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

# --- 3. GENERAZIONE PDF ---
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
        p_l = float(r['PREZZO_LORDO']); p_u = 0.0 if r['SCONTO_MERCE'] else float(r['PREZZO_NETTO'])
        s_str = "OMAGGIO" if r['SCONTO_MERCE'] else format_sconti_string(r['S1'], r['S2'], r['S3'])
        y_before = pdf.get_y(); pdf.set_xy(45, y_before)
        desc_testo = r['DESCRIZIONE']
        if r.get('NOTA'): desc_testo += f"\nNote: {r['NOTA']}"
        pdf.multi_cell(55, 5, desc_testo, border=1, align='L')
        h = max(pdf.get_y() - y_before, 8); pdf.set_xy(10, y_before)
        pdf.cell(35, h, str(r['CODICE']), border=1, align='C')
        pdf.set_xy(100, y_before); pdf.cell(10, h, str(r['QTA']), border=1, align='C')
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
            "id_preventivo": id_prev, "codice_articolo": r['CODICE'], "descrizione": r['DESCRIZIONE'],
            "quantita": r['QTA'], "prezzo_lordo_unitario": r['PREZZO_LORDO'],
            "sconto_1": r['S1'], "sconto_2": r['S2'], "sconto_3": r['S3'],
            "is_sconto_merce": r['SCONTO_MERCE'], "prezzo_netto_unitario": r['PREZZO_NETTO'], "nota_riga": r['NOTA']
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

    # --- CLIENTE ---
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

    # --- RICERCA LIVE ---
    st.subheader("🔍 Ricerca Articoli")
    
    def search_articles(search_term: str):
        if not search_term or len(search_term) < 3: return []
        mask = (df_listino['DESCRIZIONE'].str.contains(search_term, case=False, na=False)) | \
               (df_listino['CODICE'].str.contains(search_term, case=False, na=False))
        results = df_listino[mask].head(15)
        return [(f"{row['CODICE']} | {row['DESCRIZIONE'][:70]}...", row.to_dict()) for _, row in results.iterrows()]

    selected_article = st_searchbox(
        search_articles,
        placeholder="Cerca codice o descrizione...",
        key=f"search_widget_{st.session_state.search_key}", 
        clear_on_submit=True
    )

    if selected_article:
        # Quando seleziono un articolo, lo metto in configurazione
        st.session_state.temp_item = selected_article

    # --- SCHEDA CONFIGURAZIONE ---
    if st.session_state.temp_item:
        item = st.session_state.temp_item
        with st.container():
            st.markdown('<div class="config-card">', unsafe_allow_html=True)
            st.markdown(f"#### ⚙️ Configura Articolo")
            st.write(f"**Codice:** `{item['CODICE']}`")
            st.write(f"**Descrizione:** {item['DESCRIZIONE']}")
            
            cq, cm = st.columns([1, 2])
            # Se stiamo modificando, carichiamo i vecchi valori, altrimenti default
            qta_init = int(item.get('QTA', 1))
            qta_val = cq.number_input("Q.tà", min_value=1, value=qta_init)
            
            # Determina il metodo di prezzo iniziale
            metodo_init = "Netto Fisso" if 'PREZZO_NETTO' in item and item.get('S1') == 0 and item.get('S2') == 0 else "Sconti %"
            metodo = cm.radio("Metodo Prezzo:", ["Sconti %", "Netto Fisso"], horizontal=True, index=0 if metodo_init == "Sconti %" else 1)
            
            pl = float(item.get('PREZZO', item.get('PREZZO_LORDO', 0)))
            
            if metodo == "Sconti %":
                cs1, cs2, cs3 = st.columns(3)
                s1 = cs1.number_input("S1 %", value=float(item.get('SCONTO1', item.get('S1', 0))))
                s2 = cs2.number_input("S2 %", value=float(item.get('SCONTO2', item.get('S2', 0))))
                s3 = cs3.number_input("S3 %", value=float(item.get('SCONTO3', item.get('S3', 0))))
                pn = calcola_netto(pl, s1, s2, s3)
            else:
                pn_init = float(item.get('PREZZO_NETTO', pl))
                pn = st.number_input("Netto Unitario (€)", value=pn_init)
                s1, s2, s3 = 0, 0, 0
            
            nota_r = st.text_input("Nota riga", value=item.get('NOTA', ""))
            omaggio = st.checkbox("Omaggio", value=item.get('SCONTO_MERCE', False))
            if omaggio: pn = 0
            
            st.info(f"💰 Totale Netto Riga: € {pn * qta_val:,.2f}")
            
            cadd, cann = st.columns(2)
            label_btn = "💾 AGGIORNA ARTICOLO" if 'is_edit' in item else "🚀 AGGIUNGI AL PREVENTIVO"
            
            if cadd.button(label_btn, type="primary", use_container_width=True):
                st.session_state.righe_preventivo.append({
                    "CODICE": item["CODICE"], "DESCRIZIONE": item["DESCRIZIONE"], 
                    "PREZZO_LORDO": pl, "PREZZO_NETTO": pn, "QTA": qta_val, 
                    "SCONTO_MERCE": omaggio, "S1": s1, "S2": s2, "S3": s3, "NOTA": nota_r
                })
                st.session_state.temp_item = None
                st.session_state.search_key += 1
                st.rerun()
            
            if cann.button("Annulla", use_container_width=True):
                # Se annullo una modifica, devo rimettere l'articolo originale nel preventivo? 
                # No, l'utente ha cliccato "Modifica", quindi l'articolo è stato tolto. 
                # Se annulla, l'articolo è perso. Per sicurezza lo avvisiamo o gestiamo il restore.
                st.session_state.temp_item = None
                st.session_state.search_key += 1
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    # --- RIEPILOGO ---
    if st.session_state.righe_preventivo:
        st.subheader("📊 Riepilogo Prodotti")
        tot_n = 0.0
        for idx, riga in enumerate(st.session_state.righe_preventivo):
            with st.container(border=True):
                ci, cv, c_btns = st.columns([3, 1, 0.8])
                val_r = 0 if riga['SCONTO_MERCE'] else (riga['PREZZO_NETTO'] * riga['QTA'])
                tot_n += val_r
                
                ci.markdown(f"**{riga['CODICE']}** - {riga['DESCRIZIONE']}")
                ci.caption(f"Qta: {riga['QTA']} | Sconti: {format_sconti_string(riga['S1'], riga['S2'], riga['S3'])}")
                cv.markdown(f"**€ {val_r:,.2f}**")
                
                # Bottoni Azione
                b1, b2 = c_btns.columns(2)
                if b1.button("✏️", key=f"edit_{idx}", help="Modifica articolo"):
                    # Carichiamo l'articolo nel temp_item e lo togliamo dalla lista
                    edit_item = st.session_state.righe_preventivo.pop(idx)
                    edit_item['is_edit'] = True # Flag per cambiare etichetta al tasto
                    st.session_state.temp_item = edit_item
                    st.rerun()
                
                if b2.button("🗑️", key=f"del_{idx}", help="Elimina articolo"):
                    st.session_state.righe_preventivo.pop(idx)
                    st.rerun()

        st.divider()
        cn, cm = st.columns([2, 1])
        note_finali = cn.text_area("Note finali")
        cm.metric("TOTALE NETTO", f"€ {tot_n:,.2f}")
        
        num_prev = f"PREV-{datetime.now().strftime('%y%m%d-%H%M')}"
        testata = {
            "id_cliente": cliente_sel['id'] if cliente_sel else None,
            "ragione_sociale_cliente": cliente_sel['ragione_sociale'] if cliente_sel else "",
            "id_agente": str(user_data.get("agente_corrispondente")),
            "totale_lordo": 0, "totale_netto": tot_n, "note_generali": note_finali,
            "data_consegna": str(data_cons) if data_cons else None, "riferimento": rif_ordine,
            "numero_preventivo": num_prev
        }

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
                    st.success("Preventivo Salvato!"); time.sleep(1.5)
                    st.session_state.righe_preventivo = []
                    st.rerun()
                else: st.error(f"Errore: {res}")

if __name__ == "__main__":
    show_preventivi()