import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime
from fpdf import FPDF
import io
import os
import time

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Nuovo Preventivo", layout="centered")

st.markdown("""
    <style>
    .main h1 { font-size: 1.8rem !important; margin-bottom: 0.5rem !important; }
    .stMetric { background-color: #f8f9fa; padding: 10px; border-radius: 10px; border: 1px solid #ddd; }
    @media (max-width: 640px) {
        .main h1 { font-size: 1.5rem !important; }
        .stButton button { width: 100%; height: 3.5rem; font-weight: bold; }
    }
    .preview-card {
        background-color: #f0f2f6; padding: 12px; border-radius: 8px; 
        border-left: 5px solid #ff4b4b; margin-bottom: 15px; font-size: 0.9rem;
    }
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
        if start >= 35000: break
            
    df_l = pd.DataFrame(all_listino_rows)
    df_c = pd.DataFrame(clienti_res.data)
    if not df_l.empty:
        for col in ["CODICE", "DESCRIZIONE"]:
            df_l[col] = df_l[col].astype(str).fillna("").str.strip()
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
    return float(listino) * (1 - float(s1)/100) * (1 - float(s2)/100) * (1 - float(s3)/100)

# --- 3. GENERAZIONE PDF ---
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
    pdf.cell(0, 6, f"DATA: {datetime.now().strftime('%d/%m/%Y')}", ln=True, align='R')
    pdf.ln(8)
    
    pdf.set_font("Arial", 'B', 8); pdf.set_fill_color(230, 230, 230)
    pdf.cell(25, 8, "CODICE", 1, 0, 'C', True)
    pdf.cell(65, 8, "DESCRIZIONE", 1, 0, 'L', True)
    pdf.cell(10, 8, "Q.TA", 1, 0, 'C', True)
    pdf.cell(20, 8, "LISTINO U.", 1, 0, 'R', True)
    pdf.cell(18, 8, "SCONTI", 1, 0, 'C', True)
    pdf.cell(22, 8, "NETTO U.", 1, 0, 'R', True)
    pdf.cell(30, 8, "TOTALE", 1, 1, 'R', True)
    
    pdf.set_font("Arial", '', 8)
    for r in righe:
        p_l = float(r['PREZZO_LORDO'])
        p_u = 0.0 if r['SCONTO_MERCE'] else float(r['PREZZO_NETTO'])
        s_str = "OMAGGIO" if r['SCONTO_MERCE'] else format_sconti_string(r['S1'], r['S2'], r['S3'])
        y_before = pdf.get_y()
        pdf.set_xy(35, y_before)
        desc_testo = r['DESCRIZIONE']
        if r.get('NOTA'): desc_testo += f"\nNote: {r['NOTA']}"
        pdf.multi_cell(65, 5, desc_testo, border=1, align='L')
        h = max(pdf.get_y() - y_before, 8)
        pdf.set_xy(10, y_before)
        pdf.cell(25, h, r['CODICE'], border=1, align='C')
        pdf.set_xy(100, y_before)
        pdf.cell(10, h, str(r['QTA']), border=1, align='C')
        pdf.cell(20, h, f"{p_l:,.2f}", border=1, align='R')
        pdf.cell(18, h, s_str, border=1, align='C')
        pdf.cell(22, h, f"{p_u:,.2f}", border=1, align='R')
        pdf.cell(30, h, f"{(p_u * r['QTA']):,.2f}", border=1, ln=1, align='R')

    pdf.ln(5)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(160, 10, "TOTALE NETTO (IVA ESCLUSA)", 0, 0, 'R')
    pdf.cell(30, 10, f"EUR {testata['totale_netto']:,.2f}", 0, 1, 'R')
    return pdf.output(dest='S').encode('latin-1', errors='replace')

# --- 4. SALVATAGGIO DATABASE ---
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
    st.subheader("📝 Nuovo Preventivo")
    if 'search_counter' not in st.session_state: st.session_state.search_counter = 0
    if 'righe_preventivo' not in st.session_state: st.session_state.righe_preventivo = []
    
    df_clienti, df_listino = get_data_for_form()
    user_data = st.session_state.get('user_info', {})
    
    with st.expander("👤 Anagrafica e Consegna", expanded=not bool(st.session_state.righe_preventivo)):
        clienti_filtrati = df_clienti
        if user_data.get("ruolo") == "agente":
            ag_id = str(user_data.get("agente_corrispondente"))
            clienti_filtrati = df_clienti[df_clienti["id_agente"].astype(str) == ag_id]

        cliente_sel = st.selectbox("Seleziona il cliente", options=clienti_filtrati.to_dict('records'), 
                                   format_func=lambda x: f"{x['ragione_sociale']} ({x.get('citta', '')})", index=None)
        c1, c2 = st.columns(2)
        data_cons = c1.date_input("Data consegna", value=None, format="DD/MM/YYYY")
        rif_ordine = c2.text_input("Riferimento", placeholder="es. Cantiere Rossi")

    st.divider()
    
    st.subheader("📦 Articoli nel Preventivo")
    tot_netto, tot_lordo = 0.0, 0.0
    
    for idx, riga in enumerate(st.session_state.righe_preventivo):
        with st.container(border=True):
            col_a, col_b = st.columns([3, 1])
            col_a.markdown(f"**{riga['CODICE']}**")
            n_r = 0 if riga['SCONTO_MERCE'] else (riga['PREZZO_NETTO'] * riga['QTA'])
            tot_netto += n_r
            tot_lordo += (riga['PREZZO_LORDO'] * riga['QTA'])
            col_b.markdown(f"**€ {n_r:,.2f}**")
            st.write(f"{riga['DESCRIZIONE']}")
            if riga['NOTA']: st.caption(f"📝 {riga['NOTA']}")
            
            s_str = format_sconti_string(riga['S1'], riga['S2'], riga['S3'])
            st.caption(f"Qta: {riga['QTA']} | Netto U: €{riga['PREZZO_NETTO']:,.2f} | Sconti: {s_str}")

            b1, b2 = st.columns(2)
            with b1.popover("✏️ Modifica", use_container_width=True):
                e_qta = st.number_input("Q.tà", min_value=1, value=int(riga['QTA']), key=f"e_q_{idx}")
                modo_e = st.radio("Metodo", ["Sconti %", "Netto Fisso €"], key=f"md_e_{idx}", horizontal=True)
                
                if modo_e == "Sconti %":
                    sc1 = st.number_input("S1 %", value=float(riga['S1']), key=f"s1_e_{idx}")
                    sc2 = st.number_input("S2 %", value=float(riga['S2']), key=f"s2_e_{idx}")
                    sc3 = st.number_input("S3 %", value=float(riga['S3']), key=f"s3_e_{idx}")
                    e_netto = calcola_netto(riga['PREZZO_LORDO'], sc1, sc2, sc3)
                else:
                    e_netto = st.number_input("Prezzo Netto Unitario", value=float(riga['PREZZO_NETTO']), key=f"pn_e_{idx}")
                    sc1, sc2, sc3 = 0, 0, 0
                
                e_nota = st.text_input("Nota riga", value=riga['NOTA'], key=f"nt_e_{idx}")
                if st.button("Aggiorna", key=f"upd_{idx}", type="primary", use_container_width=True):
                    st.session_state.righe_preventivo[idx].update({
                        "QTA": e_qta, "S1": sc1, "S2": sc2, "S3": sc3, "PREZZO_NETTO": e_netto, "NOTA": e_nota
                    })
                    st.rerun()
            if b2.button("🗑️ Rimuovi", key=f"del_{idx}", use_container_width=True):
                st.session_state.righe_preventivo.pop(idx); st.rerun()

    # --- AGGIUNGI ARTICOLO CON DOPPIA MODALITA PREZZO ---
    with st.expander("➕ Aggiungi Articolo dal Listino", expanded=not bool(st.session_state.righe_preventivo)):
        search_term = st.text_input("Cerca per Codice o Descrizione (min. 4 caratteri):", 
                                   key=f"live_search_{st.session_state.search_counter}")
        
        if len(search_term) >= 4:
            mask = df_listino['DESCRIZIONE'].str.contains(search_term, case=False) | \
                   df_listino['CODICE'].str.contains(search_term, case=False)
            res = df_listino[mask].head(25)
            
            if not res.empty:
                sel_item = st.selectbox(f"Risultati ({len(res)}):", options=res.to_dict('records'),
                                        format_func=lambda x: f"[{x['CODICE']}] {x['DESCRIZIONE'][:60]}...",
                                        index=None, key=f"sel_{st.session_state.search_counter}")
                if sel_item:
                    st.markdown(f"""<div class="preview-card">
                        <b>{sel_item['CODICE']}</b> - {sel_item['DESCRIZIONE']}<br>
                        <b>LISTINO:</b> € {float(sel_item['PREZZO']):,.2f}
                    </div>""", unsafe_allow_html=True)
                    
                    p_l = float(sel_item['PREZZO'])
                    q_add = st.number_input("Quantità", min_value=1, value=1, key=f"q_{st.session_state.search_counter}")
                    
                    # SELETTORE MODALITA PREZZO
                    modo = st.radio("Metodo inserimento prezzo", ["Sconti %", "Netto € Manuale"], horizontal=True, key=f"modo_{st.session_state.search_counter}")
                    
                    if modo == "Sconti %":
                        c_s1, c_s2, c_s3 = st.columns(3)
                        s1 = c_s1.number_input("S1 %", value=float(sel_item.get('SCONTO1') or 0), key=f"s1_n_{st.session_state.search_counter}")
                        s2 = c_s2.number_input("S2 %", value=float(sel_item.get('SCONTO2') or 0), key=f"s2_n_{st.session_state.search_counter}")
                        s3 = c_s3.number_input("S3 %", value=float(sel_item.get('SCONTO3') or 0), key=f"s3_n_{st.session_state.search_counter}")
                        p_n = calcola_netto(p_l, s1, s2, s3)
                        st.info(f"💰 Netto calcolato: € {p_n:.2f}")
                    else:
                        p_n = st.number_input("Prezzo Netto Unitario", value=p_l, key=f"pn_n_{st.session_state.search_counter}")
                        s1, s2, s3 = 0, 0, 0

                    nota_art = st.text_input("Nota articolo", key=f"nt_n_{st.session_state.search_counter}")
                    is_omaggio = st.checkbox("Omaggio", key=f"om_{st.session_state.search_counter}")
                    if is_omaggio: p_n = 0
                    
                    if st.button("🚀 AGGIUNGI", type="primary", use_container_width=True):
                        st.session_state.righe_preventivo.append({
                            "CODICE": sel_item["CODICE"], "DESCRIZIONE": sel_item["DESCRIZIONE"], 
                            "PREZZO_LORDO": p_l, "PREZZO_NETTO": p_n, "QTA": q_add, 
                            "SCONTO_MERCE": is_omaggio, "S1": s1, "S2": s2, "S3": s3, "NOTA": nota_art
                        })
                        st.session_state.search_counter += 1; st.rerun()
            else: st.warning("Nessun articolo trovato.")

    # --- SEZIONE FINALE: TOTALI E AZIONI ---
    if st.session_state.righe_preventivo:
        st.divider()
        
        # Layout Totale e Note
        col_note, col_metrica = st.columns([2, 1])
        with col_note:
            note_gen = st.text_area("Note finali per il cliente", placeholder="Esempio: Consegna inclusa, Validità 30gg...")
        with col_metrica:
            st.metric("TOTALE NETTO", f"€ {tot_netto:,.2f}")
        
        num_prev = f"PREV-{datetime.now().strftime('%y%m%d-%H%M')}"
        
        testata = {
            "id_cliente": cliente_sel['id'] if cliente_sel else None,
            "ragione_sociale_cliente": cliente_sel['ragione_sociale'] if cliente_sel else "",
            "id_agente": str(user_data.get("agente_corrispondente")),
            "totale_lordo": tot_lordo, 
            "totale_netto": tot_netto, 
            "note_generali": note_gen,
            "data_consegna": str(data_cons) if data_cons else None, 
            "riferimento": rif_ordine,
            "numero_preventivo": num_prev
        }

        # --- TASTI AZIONE PROFESSIONALI (Allineati a destra) ---
        # Usiamo 5 colonne: le prime 2 sono vuote per spingere i tasti a destra
        # Le altre 3 ospitano i pulsanti (uno per il PDF, uno per il Database)
        c_spacer1, c_spacer2, c_spacer3, c_pdf, c_db = st.columns([1, 1, 1, 1.2, 1.5])

        with c_pdf:
            if cliente_sel:
                try:
                    pdf_b = genera_pdf_ordine(cliente_sel, testata, st.session_state.righe_preventivo)
                    st.download_button(
                        label="📄 PDF", 
                        data=pdf_b, 
                        file_name=f"{num_prev}.pdf", 
                        mime="application/pdf", 
                        use_container_width=True
                    )
                except Exception as e:
                    st.error("Errore PDF")

        with c_db:
            if c_db.button("💾 SALVA ORDINE", type="primary", use_container_width=True):
                if not cliente_sel:
                    st.error("Seleziona un cliente!")
                else:
                    ok, res_id = salva_preventivo_db(testata, st.session_state.righe_preventivo)
                    if ok:
                        st.toast(f"✅ Preventivo {num_prev} salvato!", icon='🎉')
                        time.sleep(1.5)
                        st.session_state.righe_preventivo = []
                        st.rerun()
                    else:
                        st.error(f"Errore: {res_id}")

# Fine del file
if __name__ == "__main__":
    show_preventivi()