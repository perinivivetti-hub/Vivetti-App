import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime
from fpdf import FPDF
import io
import os

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
        if start >= 30000: break 
            
    df_l = pd.DataFrame(all_listino_rows)
    df_c = pd.DataFrame(clienti_res.data)
    if not df_l.empty:
        for col in ["CODICE", "DESCRIZIONE"]:
            df_l[col] = df_l[col].astype(str).fillna("").str.strip()
    return df_c, df_l

# --- 2. UTILITY: FORMATTAZIONE SCONTI ---
def format_sconti_string(s1, s2, s3):
    parts = []
    for s in [s1, s2, s3]:
        if s is not None and float(s) > 0:
            parts.append(f"{float(s):g}")
    return "+".join(parts) if parts else "-"

# --- 3. LOGICA GENERAZIONE PDF ---
def genera_pdf_ordine(cliente, testata, righe):
    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.add_page()
    
    # Logo
    logo_path = 'LogoVivetti.png'
    if os.path.exists(logo_path):
        pdf.image(logo_path, x=10, y=8, w=45) 
    
    pdf.set_font("Arial", 'B', 15)
    pdf.set_y(12)
    pdf.cell(0, 10, f"OFFERTA / ORDINE: {testata['numero_preventivo']}", ln=True, align='R')
    pdf.ln(18)
    
    # Dati Cliente
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 6, f"SPETT.LE CLIENTE: {cliente['ragione_sociale']}", ln=True)
    pdf.cell(100, 6, f"RIFERIMENTO: {testata['riferimento'] if testata['riferimento'] else '-'}", ln=False)
    pdf.cell(0, 6, f"DATA: {datetime.now().strftime('%d/%m/%Y')}", ln=True, align='R')
    data_c = testata['data_consegna'] if testata['data_consegna'] else "Da definire"
    pdf.cell(0, 6, f"CONSEGNA PREVISTA: {data_c}", ln=True)
    pdf.ln(8)
    
    # Intestazione Tabella
    pdf.set_font("Arial", 'B', 8)
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(25, 8, "CODICE", 1, 0, 'C', True)
    pdf.cell(65, 8, "DESCRIZIONE", 1, 0, 'L', True)
    pdf.cell(10, 8, "Q.TA", 1, 0, 'C', True)
    pdf.cell(20, 8, "LISTINO U.", 1, 0, 'R', True)
    pdf.cell(18, 8, "SCONTI", 1, 0, 'C', True)
    pdf.cell(22, 8, "NETTO U.", 1, 0, 'R', True)
    pdf.cell(30, 8, "TOTALE", 1, 1, 'R', True)
    
    # Righe con Descrizione Multi-riga (Corretto per VS Code)
    pdf.set_font("Arial", '', 8)
    for r in righe:
        p_l = float(r['PREZZO_LORDO'])
        p_u = 0.0 if r['SCONTO_MERCE'] else float(r['PREZZO_NETTO'])
        p_t = p_u * r['QTA']
        s_str = "OMAGGIO" if r['SCONTO_MERCE'] else format_sconti_string(r['S1'], r['S2'], r['S3'])
        
        # Salviamo la coordinata Y iniziale
        x_start = pdf.get_x()
        y_start = pdf.get_y()
        
        # 1. Scriviamo la descrizione a destra del codice (spazio 25mm)
        pdf.set_xy(x_start + 25, y_start)
        pdf.multi_cell(65, 5, r['DESCRIZIONE'], border=1, align='L')
        
        # 2. Calcoliamo l'altezza raggiunta
        y_end = pdf.get_y()
        h_riga = y_end - y_start
        if h_riga < 8: h_riga = 8 # Altezza minima per estetica
        
        # 3. Torniamo su e disegniamo il Codice e le altre celle con l'altezza corretta
        pdf.set_xy(x_start, y_start)
        pdf.cell(25, h_riga, r['CODICE'], border=1, align='C')
        
        # Spostiamo il cursore dopo la descrizione (25 + 65 = 90)
        pdf.set_xy(x_start + 90, y_start)
        pdf.cell(10, h_riga, str(r['QTA']), border=1, align='C')
        pdf.cell(20, h_riga, f"{p_l:,.2f}", border=1, align='R')
        pdf.cell(18, h_riga, s_str, border=1, align='C')
        pdf.cell(22, h_riga, f"{p_u:,.2f}", border=1, align='R')
        pdf.cell(30, h_riga, f"{p_t:,.2f}", border=1, ln=1, align='R')
        
        if r['NOTA']:
            pdf.set_font("Arial", 'I', 7)
            pdf.cell(0, 5, f"   Nota: {r['NOTA']}", border='LRB', ln=1)
            pdf.set_font("Arial", '', 8)

    # Totali
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(160, 8, "TOTALE LORDO LISTINO", 0, 0, 'R')
    pdf.cell(30, 8, f"EUR {testata['totale_lordo']:,.2f}", 0, 1, 'R')
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(160, 10, "TOTALE NETTO (IVA ESCLUSA)", 0, 0, 'R')
    pdf.cell(30, 10, f"EUR {testata['totale_netto']:,.2f}", 0, 1, 'R')
    
    if testata['note_generali']:
        pdf.ln(4)
        pdf.set_font("Arial", 'I', 9)
        pdf.multi_cell(0, 5, f"NOTE: {testata['note_generali']}")

    return pdf.output(dest='S').encode('latin-1', errors='replace')

# --- 4. FUNZIONE SALVATAGGIO DB ---
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
        return True, f"Preventivo #{id_prev} salvato!"
    except Exception as e: return False, str(e)

# --- 5. INTERFACCIA PRINCIPALE ---
def show_preventivi():
    df_clienti, df_listino = get_data_for_form()
    user_data = st.session_state.get('user_info', {})
    
    st.subheader("📝 Nuovo Preventivo")

    with st.expander("👤 Anagrafica e Dati Consegna", expanded=True):
        clienti_filtrati = df_clienti
        if user_data.get("ruolo") == "agente":
            agente_id = str(user_data.get("agente_corrispondente"))
            clienti_filtrati = df_clienti[df_clienti["id_agente"].astype(str) == agente_id]

        cliente_selezionato = st.selectbox("Seleziona il cliente", options=clienti_filtrati.to_dict('records'), 
                                           format_func=lambda x: f"{x['ragione_sociale']} ({x.get('citta', '')})", index=None)
        c1, c2 = st.columns(2)
        data_cons = c1.date_input("Data consegna prevista", value=None, format="DD/MM/YYYY")
        rif_ordine = c2.text_input("Riferimento / Oggetto", placeholder="es. Rif. Cantiere Rossi")

    if 'righe_preventivo' not in st.session_state:
        st.session_state.righe_preventivo = []

    st.divider()
    
    st.subheader("📦 Articoli Selezionati")
    tot_netto, tot_lordo = 0.0, 0.0
    
    if st.session_state.righe_preventivo:
        for idx, riga in enumerate(st.session_state.righe_preventivo):
            with st.container(border=True):
                col1, col2, col3, col4 = st.columns([1.5, 3.0, 2.5, 0.7])
                col1.write(f"**{riga['CODICE']}**")
                col2.write(f"{riga['DESCRIZIONE']}")
                
                n_r = 0 if riga['SCONTO_MERCE'] else (riga['PREZZO_NETTO'] * riga['QTA'])
                tot_netto += n_r
                tot_lordo += (riga['PREZZO_LORDO'] * riga['QTA'])

                with col3:
                    st.write(f"Netto: **€ {n_r:,.2f}**")
                    st.caption(f"Listino: ~~€ {riga['PREZZO_LORDO']:,.2f}~~")
                    s_str = format_sconti_string(riga['S1'], riga['S2'], riga['S3'])
                    st.caption(f"Qta: {riga['QTA']} | Sconti: **{s_str}**")

                b_edit, b_del = col4.columns(2)
                with b_edit.popover("✏️"):
                    e_qta = st.number_input("Q.tà", min_value=1, value=riga['QTA'], key=f"e_q_{idx}")
                    mode = st.radio("Metodo", ["Sconti %", "Netto €"], key=f"m_{idx}", horizontal=True)
                    if mode == "Sconti %":
                        es1 = st.number_input("S1 %", value=float(riga['S1']), key=f"s1_{idx}")
                        es2 = st.number_input("S2 %", value=float(riga['S2']), key=f"s2_{idx}")
                        es3 = st.number_input("S3 %", value=float(riga['S3']), key=f"s3_{idx}")
                        e_netto = riga['PREZZO_LORDO'] * (1-es1/100) * (1-es2/100) * (1-es3/100)
                    else:
                        e_netto = st.number_input("Netto Unitario", value=float(riga['PREZZO_NETTO']), key=f"pn_{idx}")
                        es1, es2, es3 = 0, 0, 0
                    if st.button("Aggiorna", key=f"btn_{idx}", type="primary"):
                        st.session_state.righe_preventivo[idx].update({"QTA": e_qta, "S1": es1, "S2": es2, "S3": es3, "PREZZO_NETTO": e_netto})
                        st.rerun()
                if b_del.button("🗑️", key=f"del_{idx}"):
                    st.session_state.righe_preventivo.pop(idx); st.rerun()

    with st.popover("➕ Aggiungi Articolo", use_container_width=True):
        in_search = st.text_input("Cerca Codice o Descrizione:")
        if in_search:
            res = df_listino[df_listino['DESCRIZIONE'].str.contains(in_search, case=False) | df_listino['CODICE'].str.contains(in_search, case=False)].head(40)
            sel = st.selectbox("Risultati:", options=("[" + res["CODICE"] + "] " + res["DESCRIZIONE"]).tolist(), index=None)
            if sel:
                cod_sel = sel.split("[")[1].split("]")[0]
                d = df_listino[df_listino["CODICE"] == cod_sel].iloc[0]
                p_l = float(d['PREZZO'])
                q_add = st.number_input("Q.tà", min_value=1, value=1)
                t1, t2 = st.tabs(["Sconti %", "Netto Diretto"])
                with t1:
                    s1 = st.number_input("S1 %", value=float(d.get('SCONTO1', 0) or 0))
                    s2 = st.number_input("S2 %", value=float(d.get('SCONTO2', 0) or 0))
                    s3 = st.number_input("S3 %", value=float(d.get('SCONTO3', 0) or 0))
                    p_n = p_l * (1-s1/100) * (1-s2/100) * (1-s3/100)
                with t2:
                    p_m = st.number_input("Prezzo Netto", value=p_n)
                    if p_m != p_n: p_n, s1, s2, s3 = p_m, 0, 0, 0
                if st.button("✅ Aggiungi", type="primary", use_container_width=True):
                    st.session_state.righe_preventivo.append({"CODICE": d["CODICE"], "DESCRIZIONE": d["DESCRIZIONE"], "PREZZO_LORDO": p_l, "PREZZO_NETTO": p_n, "QTA": q_add, "SCONTO_MERCE": False, "S1": s1, "S2": s2, "S3": s3, "NOTA": ""})
                    st.rerun()

    if st.session_state.righe_preventivo:
        st.divider()
        c_tot1, c_tot2 = st.columns(2)
        c_tot1.metric("TOTALE NETTO", f"€ {tot_netto:,.2f}")
        risparmio = tot_lordo - tot_netto
        if risparmio > 0: c_tot2.metric("RISPARMIO", f"€ {risparmio:,.2f}", delta=f"-{(risparmio/tot_lordo)*100:.1f}%")
        
        note_gen = st.text_area("Note finali")
        num_prev = f"PREV-{datetime.now().strftime('%y%m%d-%H%M')}"
        testata = {
            "id_cliente": cliente_selezionato['id'] if cliente_selezionato else None,
            "ragione_sociale_cliente": cliente_selezionato['ragione_sociale'] if cliente_selezionato else "",
            "id_agente": str(user_data.get("agente_corrispondente")),
            "totale_lordo": tot_lordo, "totale_netto": tot_netto, "note_generali": note_gen,
            "data_consegna": str(data_cons) if data_cons else None, "riferimento": rif_ordine,
            "numero_preventivo": num_prev
        }
        
        col_s, col_p = st.columns(2)
        if col_s.button("💾 SALVA DB", type="primary", use_container_width=True):
            if not cliente_selezionato: st.error("Seleziona cliente")
            else:
                ok, msg = salva_preventivo_db(testata, st.session_state.righe_preventivo)
                if ok: st.success(msg); st.session_state.righe_preventivo = []; st.rerun()
        
        if cliente_selezionato:
            pdf_bytes = genera_pdf_ordine(cliente_selezionato, testata, st.session_state.righe_preventivo)
            st.download_button(f"📄 SCARICA {num_prev}.pdf", data=pdf_bytes, file_name=f"{num_prev}.pdf", mime="application/pdf", use_container_width=True)