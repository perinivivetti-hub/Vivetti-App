import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime
from fpdf import FPDF
from streamlit_searchbox import st_searchbox
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
    try:
        clienti_res = supabase.table("rubrica_clienti").select("*").execute()
        return pd.DataFrame(clienti_res.data)
    except:
        return pd.DataFrame()

def carica_dettagli_ordine(id_ordine):
    supabase = get_supabase_client()
    testata = supabase.table("preventivi_testata").select("*").eq("id", id_ordine).single().execute()
    righe = supabase.table("preventivi_righe").select("*").eq("id_preventivo", id_ordine).order("id").execute()
    return testata.data, righe.data

# --- 2. UTILITY PDF ---
def format_sconti_string(s1, s2, s3):
    parts = []
    for s in [s1, s2, s3]:
        try:
            val = float(s)
            if val > 0: parts.append(f"{val:g}")
        except: continue
    return "+".join(parts) if parts else "-"

def genera_pdf_conferma(cliente_ragione_sociale, testata, righe):
    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.add_page()
    logo_path = 'LogoVivetti.png'
    if os.path.exists(logo_path):
        pdf.image(logo_path, x=10, y=8, w=45) 
    
    pdf.set_font("Arial", 'B', 15); pdf.set_y(12)
    pdf.cell(0, 10, f"CONFERMA ORDINE: {testata['numero_preventivo']}", ln=True, align='R')
    pdf.ln(18); pdf.set_font("Arial", '', 10)
    
    pdf.cell(0, 6, f"SPETT.LE CLIENTE: {cliente_ragione_sociale}", ln=True)
    pdf.cell(100, 6, f"RIFERIMENTO: {testata['riferimento'] if testata['riferimento'] else '-'}", ln=False)
    pdf.cell(0, 6, f"DATA ORDINE: {datetime.now().strftime('%d/%m/%Y')}", ln=True, align='R')
    
    cons_str = "-"
    if testata.get('data_consegna'):
        try:
            cons_str = datetime.strptime(testata['data_consegna'], '%Y-%m-%d').strftime('%d/%m/%Y')
        except:
            cons_str = testata['data_consegna']
    
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 6, f"CONSEGNA PREVISTA: {cons_str}", ln=True)
    pdf.set_font("Arial", '', 10)
    
    pdf.ln(8); pdf.set_font("Arial", 'B', 8); pdf.set_fill_color(230, 230, 230)
    cols = [("CODICE", 35), ("DESCRIZIONE", 55), ("Q.TA", 10), ("PREZZO U.", 20), ("SCONTI", 20), ("NETTO U.", 20), ("TOTALE", 20)]
    for txt, w in cols: pdf.cell(w, 8, txt, 1, 0, 'C', True)
    pdf.ln(); pdf.set_font("Arial", '', 8)

    for r in righe:
        if r.get('nota_riga') == 'NOTA_TESTO':
            pdf.set_font("Arial", 'B', 9); pdf.set_fill_color(245, 245, 245)
            pdf.multi_cell(180, 8, r['descrizione'].upper(), border=1, align='L', fill=True)
            pdf.set_font("Arial", '', 8)
        else:
            p_l = float(r.get('prezzo_lordo_unitario', 0))
            p_n = float(r.get('prezzo_netto_unitario', 0))
            s_str = format_sconti_string(r.get('sconto_1'), r.get('sconto_2'), r.get('sconto_3'))
            y_before = pdf.get_y()
            pdf.set_xy(45, y_before); pdf.multi_cell(55, 5, r['descrizione'], border=0, align='L')
            h = max(pdf.get_y() - y_before, 8)
            pdf.set_xy(10, y_before); pdf.cell(35, h, str(r['codice_articolo']), border=1, align='C')
            pdf.set_xy(45, y_before); pdf.multi_cell(55, 5, r['descrizione'], border=1, align='L')
            pdf.set_xy(100, y_before); pdf.cell(10, h, str(r['quantita']), border=1, align='C')
            pdf.cell(20, h, f"{p_l:,.2f}", border=1, align='R')
            pdf.cell(20, h, s_str, border=1, align='C')
            pdf.cell(20, h, f"{p_n:,.2f}", border=1, align='R')
            pdf.cell(20, h, f"{(p_n * r['quantita']):,.2f}", border=1, ln=1, align='R')

    pdf.ln(5); pdf.set_font("Arial", 'B', 12)
    pdf.cell(160, 10, "TOTALE ORDINE (IVA ESCLUSA)", 0, 0, 'R')
    pdf.cell(30, 10, f"EUR {testata['totale_netto']:,.2f}", 0, 1, 'R')
    return pdf.output(dest='S').encode('latin-1', errors='replace')

# --- 3. FUNZIONE PRINCIPALE ---
def show_ordinato():
    st.subheader("📦 Archivio Ordini")
    
    df_clienti = get_base_data()
    user_data = st.session_state.get('user_info', {})
    supabase = get_supabase_client()

    anno_corrente = datetime.now().year
    anno_sel = st.selectbox("Seleziona Anno di Analisi", options=range(anno_corrente, anno_corrente - 5, -1), index=0)

    # --- 4. LOGICA GRAFICO ---
    start_y = f"{anno_sel}-01-01"
    end_y = f"{anno_sel}-12-31"
    
    query_stats = supabase.table("preventivi_testata").select("totale_netto, data_consegna, created_at")\
        .eq("stato", "Ordine")\
        .gte("created_at", start_y).lte("created_at", end_y)
    
    if user_data.get("ruolo") == "agente":
        query_stats = query_stats.eq("id_agente", str(user_data.get("agente_corrispondente")))
    
    stats_res = query_stats.execute()

    if stats_res.data:
        df_stats = pd.DataFrame(stats_res.data)
        ordine_mesi = ['Gen', 'Feb', 'Mar', 'Apr', 'Mag', 'Giu', 'Lug', 'Ago', 'Set', 'Ott', 'Nov', 'Dic', 'Senza Data']
        mesi_nomi = {1:'Gen', 2:'Feb', 3:'Mar', 4:'Apr', 5:'Mag', 6:'Giu', 7:'Lug', 8:'Ago', 9:'Set', 10:'Ott', 11:'Nov', 12:'Dic'}
        
        totali = {m: 0.0 for m in ordine_mesi}
        for _, row in df_stats.iterrows():
            if row.get('data_consegna'):
                try:
                    m_idx = datetime.strptime(row['data_consegna'], '%Y-%m-%d').month
                    totali[mesi_nomi[m_idx]] += float(row['totale_netto'])
                except:
                    totali["Senza Data"] += float(row['totale_netto'])
            else:
                totali["Senza Data"] += float(row['totale_netto'])

        df_chart = pd.DataFrame(list(totali.items()), columns=['Mese', 'Totale'])
        df_chart['Mese'] = pd.Categorical(df_chart['Mese'], categories=ordine_mesi, ordered=True)
        df_chart = df_chart.sort_values('Mese')

        st.markdown(f"**Andamento Consegne {anno_sel}**")
        st.bar_chart(df_chart, x='Mese', y='Totale', color="#22c55e")
    else:
        st.info(f"Nessun dato disponibile per il {anno_sel}")

    st.divider()

    # --- 5. FILTRO CLIENTE E LISTA ---
    def search_clienti_ord(search_term: str):
        if not search_term or len(search_term) < 2: return []
        if df_clienti.empty: return []
        mask = df_clienti['ragione_sociale'].str.contains(search_term, case=False, na=False)
        if user_data.get("ruolo") == "agente":
            mask = mask & (df_clienti["id_agente"].astype(str) == str(user_data.get("agente_corrispondente")))
        return [(r['ragione_sociale'], r['id']) for _, r in df_clienti[mask].iterrows()]

    filtro_cliente_id = st_searchbox(search_clienti_ord, key="search_ord_final", placeholder="🔍 Filtra per cliente...")

    query_list = supabase.table("preventivi_testata").select("*").eq("stato", "Ordine").gte("created_at", start_y).lte("created_at", end_y)
    if filtro_cliente_id: 
        query_list = query_list.eq("id_cliente", filtro_cliente_id)
    if user_data.get("ruolo") == "agente": 
        query_list = query_list.eq("id_agente", str(user_data.get("agente_corrispondente")))
    
    res_list = query_list.order("data_consegna", desc=False).execute()

    if not res_list.data:
        st.warning("Nessun ordine trovato.")
    else:
        st.write(f"Trovati **{len(res_list.data)}** ordini")
        for row in res_list.data:
            dt_c = row['data_consegna'] if row['data_consegna'] else "NON SETTATA"
            label = f"📦 {row['numero_preventivo']} | {row['ragione_sociale_cliente']} | Consegna: {dt_c} | € {row['totale_netto']:,.2f}"
            
            with st.expander(label):
                c1, c2, c3 = st.columns(3)
                
                # Generazione PDF e Download
                try:
                    _, r_dettagli = carica_dettagli_ordine(row['id'])
                    pdf_data = genera_pdf_conferma(row['ragione_sociale_cliente'], row, r_dettagli)
                    c1.download_button("📄 SCARICA PDF", data=pdf_data, file_name=f"Ordine_{row['numero_preventivo']}.pdf", mime="application/pdf", key=f"dl_{row['id']}")
                except Exception as e:
                    c1.error("Errore PDF")

                if c2.button("🔄 RIPRISTINA", key=f"rip_{row['id']}", use_container_width=True):
                    supabase.table("preventivi_testata").update({"stato": "Preventivo"}).eq("id", row['id']).execute()
                    st.rerun()

                if c3.button("🗑️ ELIMINA", key=f"del_{row['id']}", use_container_width=True, type="secondary"):
                    supabase.table("preventivi_testata").delete().eq("id", row['id']).execute()
                    st.rerun()

if __name__ == "__main__":
    show_ordinato()