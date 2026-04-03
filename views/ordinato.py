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
    except Exception as e:
        return pd.DataFrame()

def carica_dettagli_ordine(id_ordine):
    """Carica testata e righe solo al momento del bisogno"""
    supabase = get_supabase_client()
    testata = supabase.table("preventivi_testata").select("*").eq("id", id_ordine).single().execute()
    righe = supabase.table("preventivi_righe").select("*").eq("id_preventivo", id_ordine).order("id").execute()
    return testata.data, righe.data

def duplica_ordine(id_originale, supabase):
    """Copia testata e righe di un ordine esistente creandone uno nuovo come Preventivo"""
    res_t = supabase.table("preventivi_testata").select("*").eq("id", id_originale).single().execute()
    old_t = res_t.data
    
    new_t = old_t.copy()
    campi_da_rimuovere = ['id', 'created_at']
    for campo in campi_da_rimuovere:
        if campo in new_t:
            del new_t[campo]
    
    new_t['numero_preventivo'] = f"{old_t['numero_preventivo']}_COPY"
    new_t['stato'] = "Preventivo" 
    new_t['inviato'] = False 
    
    ins_t = supabase.table("preventivi_testata").insert(new_t).execute()
    if not ins_t.data:
        return None
    new_id = ins_t.data[0]['id']
    
    res_r = supabase.table("preventivi_righe").select("*").eq("id_preventivo", id_originale).execute()
    old_righe = res_r.data
    
    if old_righe:
        for r in old_righe:
            new_r = r.copy()
            if 'id' in new_r: 
                del new_r['id']
            new_r['id_preventivo'] = new_id
            supabase.table("preventivi_righe").insert(new_r).execute()
            
    return new_id

# --- 2. UTILITY PDF ---
def format_sconti_string(s1, s2, s3):
    parts = []
    for s in [s1, s2, s3]:
        try:
            val = float(s)
            if val > 0: 
                parts.append(f"{val:g}")
        except: 
            continue
    return "+".join(parts) if parts else "-"

def genera_pdf_conferma(cliente_ragione_sociale, testata, righe, priorita=""):
    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.add_page()
    logo_path = 'LogoVivetti.png'
    if os.path.exists(logo_path):
        pdf.image(logo_path, x=10, y=8, w=45) 
    
    pdf.set_font("Arial", 'B', 15)
    pdf.set_y(12)
    pdf.cell(0, 10, f"CONFERMA ORDINE: {testata['numero_preventivo']}", ln=True, align='R')
    
    if priorita and priorita != "STANDARD":
        pdf.set_font("Arial", 'B', 11)
        if priorita == "URGENTE":
            pdf.set_text_color(255, 0, 0)
        else:
            pdf.set_text_color(0, 0, 255)
        pdf.cell(0, 8, f"PRIORITA': {priorita}", ln=True, align='R')
        pdf.set_text_color(0, 0, 0)
    
    pdf.ln(10)
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 6, f"SPETT.LE CLIENTE: {cliente_ragione_sociale}", ln=True)
    pdf.cell(100, 6, f"RIFERIMENTO: {testata['riferimento'] if testata['riferimento'] else '-'}", ln=False)
    pdf.cell(0, 6, f"DATA ORDINE: {datetime.now().strftime('%d/%m/%Y')}", ln=True, align='R')
    
    cons_str = "-"
    if testata.get('data_consegna'):
        try:
            cons_str = datetime.strptime(str(testata['data_consegna']), '%Y-%m-%d').strftime('%d/%m/%Y')
        except:
            cons_str = str(testata['data_consegna'])
    
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 6, f"CONSEGNA PREVISTA: {cons_str}", ln=True)
    
    pdf.ln(8)
    pdf.set_font("Arial", 'B', 8)
    pdf.set_fill_color(230, 230, 230)
    cols = [("CODICE", 35), ("DESCRIZIONE", 55), ("Q.TA", 10), ("PREZZO U.", 20), ("SCONTI", 20), ("NETTO U.", 20), ("TOTALE", 20)]
    for txt, w in cols:
        pdf.cell(w, 8, txt, 1, 0, 'C', True)
    pdf.ln()
    pdf.set_font("Arial", '', 8)

    for r in righe:
        if pdf.get_y() > 250:
            pdf.add_page()
            pdf.set_font("Arial", 'B', 8)
            pdf.set_fill_color(230, 230, 230)
            for txt, w in cols:
                pdf.cell(w, 8, txt, 1, 0, 'C', True)
            pdf.ln()
            pdf.set_font("Arial", '', 8)

        if r.get('nota_riga') == 'NOTA_TESTO':
            pdf.set_font("Arial", 'B', 9)
            pdf.set_fill_color(245, 245, 245)
            pdf.multi_cell(180, 8, r['descrizione'].upper(), border=1, align='L', fill=True)
            pdf.set_font("Arial", '', 8)
        else:
            p_l = float(r.get('prezzo_lordo_unitario', 0))
            p_n = float(r.get('prezzo_netto_unitario', 0))
            s_str = format_sconti_string(r.get('sconto_1'), r.get('sconto_2'), r.get('sconto_3'))
            
            desc_testo = str(r['descrizione'])
            if len(desc_testo) > 250:
                desc_testo = desc_testo[:247] + "..."
            
            y_before = pdf.get_y()
            pdf.set_xy(45, y_before)
            pdf.multi_cell(55, 5, desc_testo, border=0, align='L')
            h = max(pdf.get_y() - y_before, 8)
            
            pdf.set_xy(10, y_before)
            pdf.cell(35, h, str(r['codice_articolo']), border=1, align='C')
            pdf.set_xy(45, y_before)
            pdf.multi_cell(55, 5, desc_testo, border=1, align='L')
            pdf.set_xy(100, y_before)
            pdf.cell(10, h, str(r['quantita']), border=1, align='C')
            pdf.cell(20, h, f"{p_l:,.2f}", border=1, align='R')
            pdf.cell(20, h, s_str, border=1, align='C')
            pdf.cell(20, h, f"{p_n:,.2f}", border=1, align='R')
            pdf.cell(20, h, f"{(p_n * r['quantita']):,.2f}", border=1, ln=1, align='R')

    pdf.ln(5)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(160, 10, "TOTALE ORDINE (IVA ESCLUSA)", 0, 0, 'R')
    pdf.cell(30, 10, f"EUR {testata['totale_netto']:,.2f}", 0, 1, 'R')
    return pdf.output(dest='S').encode('latin-1', errors='replace')

def genera_pdf_riepilogo_giornaliero(anno, df_stats):
    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, f"RIEPILOGO ORDINI PER MESE - ANNO {anno}", ln=True, align='C')
    pdf.ln(5)
    
    df_stats['data_dt'] = pd.to_datetime(df_stats['created_at'])
    df_stats['mese_num'] = df_stats['data_dt'].dt.month
    df_stats['giorno'] = df_stats['data_dt'].dt.date
    
    mesi_nomi = {
        1:'Gennaio', 2:'Febbraio', 3:'Marzo', 4:'Aprile', 5:'Maggio', 6:'Giugno',
        7:'Luglio', 8:'Agosto', 9:'Settembre', 10:'Ottobre', 11:'Novembre', 12:'Dicembre'
    }

    totale_annuo = 0
    for mese_idx in sorted(df_stats['mese_num'].unique()):
        df_mese = df_stats[df_stats['mese_num'] == mese_idx]
        
        if pdf.get_y() > 240:
            pdf.add_page()

        pdf.set_font("Arial", 'B', 12)
        pdf.set_fill_color(200, 220, 255) 
        pdf.cell(0, 10, f"MESE: {mesi_nomi[mese_idx].upper()}", 1, 1, 'L', True)
        
        pdf.set_font("Arial", 'B', 9)
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(60, 7, "DATA", 1, 0, 'C', True)
        pdf.cell(60, 7, "NUM. ORDINI", 1, 0, 'C', True)
        pdf.cell(60, 7, "TOTALE GIORNO (EUR)", 1, 1, 'C', True)
        
        pdf.set_font("Arial", '', 9)
        riepilogo_giorni = df_mese.groupby('giorno').agg(
            num_ordini=('totale_netto', 'count'),
            totale_giorno=('totale_netto', 'sum')
        ).sort_index()
        
        totale_mese = 0
        for data, row in riepilogo_giorni.iterrows():
            if pdf.get_y() > 275:
                pdf.add_page()
                pdf.set_font("Arial", 'B', 8)
                pdf.cell(60, 7, "DATA (cont.)", 1, 0, 'C', True)
                pdf.cell(60, 7, "NUM. ORDINI", 1, 0, 'C', True)
                pdf.cell(60, 7, "TOTALE GIORNO", 1, 1, 'C', True)
                pdf.set_font("Arial", '', 9)

            pdf.cell(60, 7, data.strftime('%d/%m/%Y'), 1, 0, 'C')
            pdf.cell(60, 7, str(int(row['num_ordini'])), 1, 0, 'C')
            pdf.cell(60, 7, f"{row['totale_giorno']:,.2f}", 1, 1, 'R')
            totale_mese += row['totale_giorno']
        
        if pdf.get_y() > 270:
            pdf.add_page()

        pdf.set_font("Arial", 'B', 10)
        pdf.set_fill_color(245, 245, 245)
        pdf.cell(120, 8, f"TOTALE {mesi_nomi[mese_idx].upper()}", 1, 0, 'R', True)
        pdf.cell(60, 8, f"{totale_mese:,.2f}", 1, 1, 'R', True)
        pdf.ln(5)
        totale_annuo += totale_mese

    if pdf.get_y() > 250:
        pdf.add_page()

    pdf.ln(5)
    pdf.set_font("Arial", 'B', 13)
    pdf.set_fill_color(34, 197, 94)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(120, 12, "TOTALE COMPLESSIVO ANNUALE", 1, 0, 'R', True)
    pdf.cell(60, 12, f"EUR {totale_annuo:,.2f}", 1, 1, 'R', True)
    
    return pdf.output(dest='S').encode('latin-1', errors='replace')

# --- 3. FUNZIONE PRINCIPALE ---
def show_ordinato():
    st.subheader("📦 Archivio Ordini")
    
    if 'opened_expander_id' not in st.session_state:
        st.session_state.opened_expander_id = None
    
    df_clienti = get_base_data()
    user_data = st.session_state.get('user_info', {})
    supabase = get_supabase_client()

    anno_corrente = datetime.now().year
    anno_sel = st.selectbox("Seleziona Anno di Analisi", options=range(anno_corrente, anno_corrente - 5, -1), index=0)

    # --- 4. LOGICA DATI E GRAFICO ---
    start_y = f"{anno_sel}-01-01"
    end_y = f"{anno_sel}-12-31"
    
    query_stats = supabase.table("preventivi_testata").select("totale_netto, data_consegna, created_at")\
        .eq("stato", "Ordine").gte("created_at", start_y).lte("created_at", end_y)
    
    if user_data.get("ruolo") == "agente":
        query_stats = query_stats.eq("id_agente", str(user_data.get("agente_corrispondente")))
    
    stats_res = query_stats.execute()
    df_stats = pd.DataFrame(stats_res.data) if stats_res.data else pd.DataFrame()

    if not df_stats.empty:
        ordine_mesi = ['Gen', 'Feb', 'Mar', 'Apr', 'Mag', 'Giu', 'Lug', 'Ago', 'Set', 'Ott', 'Nov', 'Dic', 'Senza Data']
        mesi_nomi_short = {1:'Gen', 2:'Feb', 3:'Mar', 4:'Apr', 5:'Mag', 6:'Giu', 7:'Lug', 8:'Ago', 9:'Set', 10:'Ott', 11:'Nov', 12:'Dic'}
        
        totali = {m: 0.0 for m in ordine_mesi}
        for _, row in df_stats.iterrows():
            try:
                if row.get('data_consegna'):
                    m_idx = datetime.strptime(str(row['data_consegna']), '%Y-%m-%d').month
                    totali[mesi_nomi_short[m_idx]] += float(row['totale_netto'])
                else:
                    totali["Senza Data"] += float(row['totale_netto'])
            except:
                totali["Senza Data"] += float(row['totale_netto'])

        df_chart = pd.DataFrame(list(totali.items()), columns=['Mese', 'Totale'])
        df_chart['Mese'] = pd.Categorical(df_chart['Mese'], categories=ordine_mesi, ordered=True)
        
        st.markdown(f"**Andamento Consegne {anno_sel}**")
        st.bar_chart(df_chart, x='Mese', y='Totale', color="#22c55e")

        st.write("---")
        c_rep1, _ = st.columns([1.2, 2])
        with c_rep1:
            rep_key = f"rep_ready_{anno_sel}"
            if st.button("📊 GENERA REPORT ACQUISIZIONE", use_container_width=True):
                with st.spinner("Generazione..."):
                    pdf_rep = genera_pdf_riepilogo_giornaliero(anno_sel, df_stats)
                    st.session_state[rep_key] = base64.b64encode(pdf_rep).decode()
            
            if st.session_state.get(rep_key):
                b64_rep = st.session_state[rep_key]
                st.markdown(f'<a href="data:application/pdf;base64,{b64_rep}" download="Report_{anno_sel}.pdf" style="color:#ff4b4b;text-decoration:none;font-weight:bold;">⬇️ SCARICA REPORT</a>', unsafe_allow_html=True)
    else:
        st.info(f"Nessun dato disponibile per il {anno_sel}")
    
    st.divider()

    # --- 5. FILTRO CLIENTE E LISTA ---
    def search_clienti_ord(search_term: str):
        if not search_term or len(search_term) < 2:
            return []
        if df_clienti.empty:
            return []
        mask = df_clienti['ragione_sociale'].str.contains(search_term, case=False, na=False)
        if user_data.get("ruolo") == "agente":
            mask = mask & (df_clienti["id_agente"].astype(str) == str(user_data.get("agente_corrispondente")))
        return [(r['ragione_sociale'], r['id']) for _, r in df_clienti[mask].iterrows()]

    filtro_cliente_id = st_searchbox(search_clienti_ord, key="search_ord_final", placeholder="🔍 Filtra per cliente...")

    query_list = supabase.table("preventivi_testata").select("*").eq("stato", "Ordine")\
        .gte("created_at", start_y).lte("created_at", end_y).order("created_at", desc=True)
        
    if filtro_cliente_id: 
        query_list = query_list.eq("id_cliente", filtro_cliente_id)
    if user_data.get("ruolo") == "agente": 
        query_list = query_list.eq("id_agente", str(user_data.get("agente_corrispondente")))
    
    res_list = query_list.execute()

    if not res_list.data:
        st.warning("Nessun ordine trovato.")
    else:
        st.write(f"Trovati **{len(res_list.data)}** ordini")
        for row in res_list.data:
            dt_c = row['data_consegna'] if row['data_consegna'] else "NON SETTATA"
            
            # --- STATO INVIATO ---
            is_inviato = row.get('inviato', False)
            status_icon = "✅" if is_inviato else "⏳"
            
            label = f"{status_icon} {row['numero_preventivo']} | {row['ragione_sociale_cliente']} | Consegna: {dt_c} | € {row['totale_netto']:,.2f}"
            is_open = st.session_state.opened_expander_id == row['id']
            
            with st.expander(label, expanded=is_open):
                # Usiamo le colonne per compattare priorità e checkbox inviato
                col_prio, col_inv = st.columns([3, 1])
                
                with col_prio:
                    priorita_sel = st.radio(
                        "Priorità documento:", 
                        ["STANDARD", "URGENTE", "APPENA DISPONIBILE"], 
                        index=0, horizontal=True, key=f"prio_{row['id']}"
                    )
                
                with col_inv:
                    st.write("") # Allineamento verticale approssimativo
                    check_inv = st.checkbox("Segna come Inviato", value=is_inviato, key=f"inv_{row['id']}")
                    if check_inv != is_inviato:
                        supabase.table("preventivi_testata").update({"inviato": check_inv}).eq("id", row['id']).execute()
                        st.toast(f"Stato ordine {row['numero_preventivo']} aggiornato!")
                        time.sleep(0.5)
                        st.rerun()

                st.divider()
                c1, c2, c3, c4 = st.columns(4)
                
                pdf_key = f"pdf_ord_ready_{row['id']}"
                if c1.button("📄 PDF", key=f"btn_pdf_{row['id']}", use_container_width=True):
                    with st.spinner("Generazione..."):
                        st.session_state.opened_expander_id = row['id']
                        t_d, r_d = carica_dettagli_ordine(row['id'])
                        pdf_bytes = genera_pdf_conferma(row['ragione_sociale_cliente'], t_d, r_d, priorita=priorita_sel)
                        st.session_state[pdf_key] = base64.b64encode(pdf_bytes).decode()
                        st.rerun()

                if st.session_state.get(pdf_key):
                    b64_data = st.session_state[pdf_key]
                    file_n = f"Ordine_{row['numero_preventivo']}.pdf"
                    st.markdown(f'<div style="text-align:center;"><a href="data:application/pdf;base64,{b64_data}" target="_blank" download="{file_n}" style="color:#ff4b4b;text-decoration:none;font-weight:bold;">⬇️ SCARICA PDF</a></div>', unsafe_allow_html=True)

                if c2.button("👯 COPIA", key=f"btn_dup_{row['id']}", use_container_width=True):
                    st.session_state.opened_expander_id = None
                    if duplica_ordine(row['id'], supabase):
                        st.success("Copiato in Preventivi!")
                        time.sleep(1)
                        st.rerun()

                if c3.button("🔄 RIPRISTINA", key=f"rip_{row['id']}", use_container_width=True):
                    st.session_state.opened_expander_id = None
                    supabase.table("preventivi_testata").update({"stato": "Preventivo"}).eq("id", row['id']).execute()
                    st.rerun()

                if c4.button("🗑️ ELIMINA", key=f"del_{row['id']}", use_container_width=True, type="secondary"):
                    st.session_state.opened_expander_id = None
                    supabase.table("preventivi_testata").delete().eq("id", row['id']).execute()
                    st.rerun()

if __name__ == "__main__":
    show_ordinato()