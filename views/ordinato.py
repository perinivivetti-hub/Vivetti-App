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
    clienti_res = supabase.table("rubrica_clienti").select("*").execute()
    return pd.DataFrame(clienti_res.data)

def carica_dettagli_ordine(id_ordine):
    supabase = get_supabase_client()
    testata = supabase.table("preventivi_testata").select("*").eq("id", id_ordine).single().execute()
    righe = supabase.table("preventivi_righe").select("*").eq("id_preventivo", id_ordine).order("id").execute()
    return testata.data, righe.data

# --- 2. UTILITY PDF (Mantenuta per coerenza) ---
def format_sconti_string(s1, s2, s3):
    parts = [f"{float(s):g}" for s in [s1, s2, s3] if s and float(s) > 0]
    return "+".join(parts) if parts else "-"

def genera_pdf_conferma(cliente_ragione_sociale, testata, righe):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, f"CONFERMA ORDINE: {testata['numero_preventivo']}", ln=True, align='R')
    pdf.set_font("Arial", '', 10)
    pdf.ln(10)
    pdf.cell(0, 6, f"CLIENTE: {cliente_ragione_sociale}", ln=True)
    pdf.cell(0, 6, f"TOTALE: EUR {testata['totale_netto']:,.2f}", ln=True)
    return pdf.output(dest='S').encode('latin-1', errors='replace')

# --- 3. FUNZIONE PRINCIPALE ---
def show_ordinato():
    st.subheader("📦 Archivio Ordini")
    
    df_clienti = get_base_data()
    user_data = st.session_state.get('user_info', {})
    supabase = get_supabase_client()

    # --- FILTRO ANNO (Spostato in alto per il grafico) ---
    anno_corrente = datetime.now().year
    anno_sel = st.selectbox("Seleziona Anno di Analisi", options=range(anno_corrente, anno_corrente - 5, -1), index=0)

    # --- 4. LOGICA GRAFICO (Tutti gli ordini dell'anno) ---
    start_year = f"{anno_sel}-01-01"
    end_year = f"{anno_sel}-12-31"
    
    query_stats = supabase.table("preventivi_testata").select("totale_netto, created_at").eq("stato", "Ordine").gte("created_at", start_year).lte("created_at", end_year)
    if user_data.get("ruolo") == "agente":
        query_stats = query_stats.eq("id_agente", str(user_data.get("agente_corrispondente")))
    
    stats_res = query_stats.execute()

    if stats_res.data:
        df_stats = pd.DataFrame(stats_res.data)
        df_stats['created_at'] = pd.to_datetime(df_stats['created_at'])
        df_stats['Mese'] = df_stats['created_at'].dt.month
        
        # Raggruppamento per mese (1-12)
        mesi_nomi = {1:'Gen', 2:'Feb', 3:'Mar', 4:'Apr', 5:'Mag', 6:'Giu', 7:'Lug', 8:'Ago', 9:'Set', 10:'Ott', 11:'Nov', 12:'Dic'}
        vendite_mese = df_stats.groupby('Mese')['totale_netto'].sum().reindex(range(1, 13), fill_value=0)
        vendite_mese.index = vendite_mese.index.map(mesi_nomi)

        st.markdown(f"**Andamento Vendite {anno_sel}**")
        st.bar_chart(vendite_mese, color="#22c55e")
    else:
        st.info(f"Nessun dato disponibile per il grafico nel {anno_sel}")

    st.divider()

    # --- 5. FILTRO CLIENTE E LISTA ORDINI ---
    def search_clienti_ord(search_term: str):
        if not search_term or len(search_term) < 2: return []
        mask = df_clienti['ragione_sociale'].str.contains(search_term, case=False, na=False)
        if user_data.get("ruolo") == "agente":
            mask = mask & (df_clienti["id_agente"].astype(str) == str(user_data.get("agente_corrispondente")))
        return [(r['ragione_sociale'], r['id']) for _, r in df_clienti[mask].iterrows()]

    filtro_cliente_id = st_searchbox(search_clienti_ord, key="search_ord_final", placeholder="🔍 Filtra la lista per cliente...")

    # Query per la lista (filtrata per anno e opzionalmente per cliente)
    query_list = supabase.table("preventivi_testata").select("*").eq("stato", "Ordine").gte("created_at", start_year).lte("created_at", end_year)
    
    if filtro_cliente_id:
        query_list = query_list.eq("id_cliente", filtro_cliente_id)
    if user_data.get("ruolo") == "agente":
        query_list = query_list.eq("id_agente", str(user_data.get("agente_corrispondente")))
    
    res_list = query_list.order("created_at", desc=True).execute()

    # --- DISPLAY LISTA ---
    if not res_list.data:
        st.warning("Nessun ordine trovato per i filtri selezionati.")
    else:
        st.write(f"Trovati **{len(res_list.data)}** ordini")
        for row in res_list.data:
            dt = datetime.fromisoformat(row['created_at'].replace('Z', '+00:00')).strftime('%d/%m/%Y')
            label = f"📦 {row['numero_preventivo']} | {row['ragione_sociale_cliente']} | {dt} | € {row['totale_netto']:,.2f}"
            
            with st.expander(label):
                c1, c2, c3 = st.columns(3)
                
                # Azioni
                if c1.button("📄 RIGENERA PDF", key=f"pdf_{row['id']}", use_container_width=True):
                    st.info("Funzione di download attivata (usa download_button per produzione)")
                
                if c2.button("🔄 RIPRISTINA", key=f"rip_{row['id']}", use_container_width=True):
                    supabase.table("preventivi_testata").update({"stato": "Preventivo"}).eq("id", row['id']).execute()
                    st.rerun()

                if c3.button("🗑️ ELIMINA", key=f"del_{row['id']}", use_container_width=True, type="secondary"):
                    supabase.table("preventivi_testata").delete().eq("id", row['id']).execute()
                    st.rerun()

if __name__ == "__main__":
    show_ordinato()