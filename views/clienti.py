import streamlit as st
import pandas as pd
import plotly.express as px
from st_supabase_connection import SupabaseConnection

def show_clienti():
    # --- 1. CONFIGURAZIONE E CONNESSIONE ---
    if 'user_info' not in st.session_state:
        st.error("Errore: Utente non loggato.")
        return
    
    user_data = st.session_state['user_info']
    my_agente_id = str(user_data.get("agente_corrispondente"))

    conn = st.connection(
        "supabase",
        type=SupabaseConnection,
        url=st.secrets["connections"]["supabase"]["url"],
        key=st.secrets["connections"]["supabase"]["key"]
    )

    # --- 2. FUNZIONI DI CARICAMENTO OTTIMIZZATE ---
    
    @st.cache_data(persist="disk", ttl=600)
    def get_clienti_list(id_agente=None):
        """Recupera la lista clienti filtrata per ID AGENTE"""
        all_clients = []
        start = 0
        chunk_size = 1000
        
        while True:
            # Query basata su IdAgenteDoc per precisione massima
            query = conn.table("fatturati").select("Cliente").range(start, start + chunk_size - 1)
            
            if id_agente and id_agente != "Tutti":
                query = query.eq("IdAgenteDoc", id_agente)
            
            response = query.execute()
            data = response.data
            
            if not data:
                break
            
            all_clients.extend([d['Cliente'] for d in data])
            
            if len(data) < chunk_size:
                break
            start += chunk_size
        
        return sorted(list(set(all_clients)))

    @st.cache_data(persist="disk", ttl=600)
    def get_cliente_detail(nome_cliente):
        """Recupera tutto lo storico vendite del cliente"""
        res = conn.table("fatturati").select("*").eq("Cliente", nome_cliente).execute()
        return pd.DataFrame(res.data)

    # --- 3. FILTRI DI SELEZIONE ---
    st.title("👥 Analisi Clienti")
    
    with st.container(border=True):
        c1, c2 = st.columns(2)
        
        with c1:
            if user_data["ruolo"] == "agente":
                # L'agente usa il suo ID fisso
                id_agente_per_query = my_agente_id
                st.markdown(f"**👤 Agente:** {user_data.get('agente_nome', 'Mio Profilo')}")
            else:
                # L'admin può scegliere tra gli agenti (mappando Nome -> ID)
                # Recupero rapido per il menu a tendina
                res_agenti = conn.table("fatturati").select("IdAgenteDoc, AgenteDoc").execute()
                df_mappa = pd.DataFrame(res_agenti.data).drop_duplicates()
                
                mappa_nomi = {"Tutti": "Tutti"}
                mappa_nomi.update(dict(zip(df_mappa["AgenteDoc"], df_mappa["IdAgenteDoc"])))
                
                agente_nome_sel = st.selectbox("👤 Seleziona Agente (Admin)", list(mappa_nomi.keys()))
                id_agente_per_query = mappa_nomi[agente_nome_sel]

        with c2:
            with st.spinner("Caricamento clienti..."):
                lista_clienti = get_clienti_list(id_agente_per_query)
            cliente_sel = st.selectbox("🏢 Seleziona Cliente", ["-"] + lista_clienti)

    if cliente_sel == "-":
        st.info("💡 Seleziona un cliente per visualizzare il tracking target e i dati.")
        return

    # --- 4. ANALISI DATI ---
    with st.spinner("Elaborazione dati..."):
        df_cliente = get_cliente_detail(cliente_sel)
    
    if df_cliente.empty:
        st.warning("Nessun dato trovato.")
        return

    # Pulizia
    df_cliente = df_cliente[~df_cliente["CodArt"].astype(str).str.upper().str.contains('RAEE', na=False)].copy()
    df_cliente["ImportoNettoRiga"] = pd.to_numeric(df_cliente["ImportoNettoRiga"], errors='coerce').fillna(0)

    # --- 5. VISUALIZZAZIONE "FINE" (HEADER & TARGET) ---
    fatturato_totale = df_cliente["ImportoNettoRiga"].sum()
    target = 80000.0  # Esempio target
    percentuale = min(1.0, fatturato_totale / target)

    st.markdown(f"""
        <div style="border-left: 4px solid #1f77b4; padding-left: 15px; margin: 20px 0;">
            <h2 style="margin:0; font-weight: 500;">{cliente_sel}</h2>
            <span style="color: #888; font-size: 14px; text-transform: uppercase;">Tracking Obiettivi 2026</span>
        </div>
    """, unsafe_allow_html=True)
    
    m1, m2, m3 = st.columns(3)
    m1.metric("💰 Fatturato", f"€ {fatturato_totale:,.2f}")
    m2.metric("🎯 Target", f"€ {target:,.0f}")
    
    mancante = target - fatturato_totale
    if mancante > 0:
        m3.metric("📉 Al Traguardo", f"€ {mancante:,.2f}", delta=f"-{mancante:,.2f}", delta_color="inverse")
    else:
        m3.metric("📉 Al Traguardo", "RAGGIUNTO", delta="COMPLETATO")

    st.progress(percentuale)
    st.caption(f"Avanzamento: **{percentuale*100:.1f}%**")

    # --- 6. GRAFICO MERCEOLOGICO ---
    st.divider()
    st.subheader("📦 Suddivisione per Categoria")
    res_merce = df_cliente.groupby("Merceologica")["ImportoNettoRiga"].sum().reset_index().sort_values("ImportoNettoRiga", ascending=True)
    
    fig_merce = px.bar(
        res_merce, x="ImportoNettoRiga", y="Merceologica", orientation='h',
        color_discrete_sequence=['#1f77b4'], text_auto='.2s'
    )
    fig_merce.update_layout(height=max(300, len(res_merce)*35), yaxis_title=None, margin=dict(l=0, r=0, t=10, b=10))
    st.plotly_chart(fig_merce, use_container_width=True)

    # --- 7. PREVENTIVI E NOTE (Come nel tuo codice originale) ---
    st.divider()
    t1, t2 = st.tabs(["🚀 Preventivi Caldi", "📝 Diario Visite"])
    
    with t1:
        if 'preventivi_list' not in st.session_state:
            st.session_state.preventivi_list = []
        
        df_prev = pd.DataFrame(st.session_state.preventivi_list) if st.session_state.preventivi_list else pd.DataFrame(columns=["Data", "Oggetto", "Valore", "Stato"])
        st.dataframe(df_prev, use_container_width=True, hide_index=True)
        
        with st.expander("➕ Aggiungi preventivo"):
            c_p1, c_p2 = st.columns([2, 1])
            nuovo_ogg = c_p1.text_input("Descrizione cantiere/oggetto")
            nuovo_val = c_p2.number_input("Valore stimato (€)", min_value=0.0)
            if st.button("Salva", use_container_width=True):
                st.session_state.preventivi_list.append({
                    "Data": pd.Timestamp.now().strftime("%d/%m/%Y"),
                    "Oggetto": nuovo_ogg, "Valore": nuovo_val, "Stato": "Caldo"
                })
                st.rerun()

    with t2:
        st.caption("Ultime note registrate per questo cliente:")
        st.info("Visita 19/02: Interessato a promo elettrodomestici da incasso.")
        
        with st.expander("➕ Registra nuova visita"):
            nota = st.text_area("Cosa vi siete detti?")
            if st.button("Salva Nota", type="primary"):
                st.toast("Nota salvata correttamente")

if __name__ == "__main__":
    show_clienti()