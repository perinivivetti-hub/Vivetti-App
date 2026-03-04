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
    my_agente_id = str(user_data.get("agente_corrispondente", "")).strip()

    conn = st.connection(
        "supabase",
        type=SupabaseConnection,
        url=st.secrets["connections"]["supabase"]["url"],
        key=st.secrets["connections"]["supabase"]["key"]
    )

    # --- 2. FUNZIONI DI CARICAMENTO DATI ---
    
    @st.cache_data(persist="disk", ttl=600)
    def get_clienti_full_data(id_agente=None):
        """Recupera i clienti dai fatturati e incrocia con rubrica_clienti per ID"""
        # 1. Prendiamo i nomi clienti dai fatturati
        query_f = conn.table("fatturati").select("Cliente")
        if id_agente and id_agente != "Tutti":
            query_f = query_f.eq("IdAgenteDoc", id_agente)
        
        res_f = query_f.execute()
        nomi_unici = sorted(list(set([d['Cliente'] for d in res_f.data])))

        if not nomi_unici:
            return pd.DataFrame(columns=["ragione_sociale", "id_cliente"])

        # 2. Recuperiamo ID dalla rubrica per questi nomi
        # Assicurati che i nomi delle colonne 'id_cliente' e 'ragione_sociale' siano corretti su Supabase
        res_r = conn.table("rubrica_clienti").select("id_cliente, ragione_sociale").in_("ragione_sociale", nomi_unici).execute()
        
        df_rubrica = pd.DataFrame(res_r.data)
        return df_rubrica

    @st.cache_data(persist="disk", ttl=600)
    def get_cliente_years(nome_cliente):
        res = conn.table("fatturati").select("AnnoRif").eq("Cliente", nome_cliente).execute()
        df_y = pd.DataFrame(res.data)
        if df_y.empty: return []
        return sorted(df_y["AnnoRif"].unique().tolist(), reverse=True)

    @st.cache_data(persist="disk", ttl=600)
    def get_cliente_detail_filtered(nome_cliente, anno):
        res = conn.table("fatturati").select("*").eq("Cliente", nome_cliente).eq("AnnoRif", anno).execute()
        return pd.DataFrame(res.data)

    # --- 3. INTERFACCIA FILTRI ---
    st.subheader("👥 Analisi Clienti")
    
    with st.container(border=True):
        c1, c2, c3 = st.columns([1.2, 1.8, 1])
        
        with c1:
            if user_data["ruolo"] == "agente":
                id_agente_per_query = my_agente_id
                st.info(f"👤 **Agente:** {user_data.get('agente_nome', 'Mio Profilo')}")
            else:
                res_agenti = conn.table("fatturati").select("IdAgenteDoc, AgenteDoc").execute()
                df_mappa = pd.DataFrame(res_agenti.data).drop_duplicates()
                mappa_nomi = {"Tutti": "Tutti"}
                for _, row in df_mappa.iterrows():
                    mappa_nomi[str(row["AgenteDoc"]).strip()] = str(row["IdAgenteDoc"]).strip()
                
                agente_nome_sel = st.selectbox("👤 Seleziona Agente", list(mappa_nomi.keys()))
                id_agente_per_query = mappa_nomi[agente_nome_sel]

        with c2:
            with st.spinner("Sincronizzazione clienti..."):
                df_clienti_anagrafica = get_clienti_full_data(id_agente_per_query)
                lista_nomi = sorted(df_clienti_anagrafica["ragione_sociale"].tolist()) if not df_clienti_anagrafica.empty else []
                cliente_sel = st.selectbox("🏢 Seleziona Cliente", ["-"] + lista_nomi)
                
                # Recupero ID Cliente per uso interno
                id_cliente_corrente = None
                if cliente_sel != "-" and not df_clienti_anagrafica.empty:
                    id_cliente_corrente = df_clienti_anagrafica[df_clienti_anagrafica["ragione_sociale"] == cliente_sel]["id_cliente"].values[0]

        with c3:
            if cliente_sel != "-":
                anni_disponibili = get_cliente_years(cliente_sel)
                anno_sel = st.selectbox("📅 Anno", anni_disponibili)
            else:
                st.selectbox("📅 Anno", ["-"], disabled=True)
                anno_sel = None

    if cliente_sel == "-" or not anno_sel:
        st.info("💡 Seleziona un cliente e l'anno di riferimento per visualizzare l'analisi.")
        return

    # --- 4. ELABORAZIONE DATI ---
    with st.spinner("Recupero dati..."):
        df_cliente = get_cliente_detail_filtered(cliente_sel, anno_sel)
    
    if df_cliente.empty:
        st.warning(f"Nessun dato trovato per {cliente_sel} nell'anno {anno_sel}.")
        return

    df_cliente = df_cliente[~df_cliente["CodArt"].astype(str).str.upper().str.contains('RAEE', na=False)].copy()
    df_cliente["ImportoNettoRiga"] = pd.to_numeric(df_cliente["ImportoNettoRiga"], errors='coerce').fillna(0)

    # --- 5. VISUALIZZAZIONE PERFORMANCE ---
    fatturato_totale = df_cliente["ImportoNettoRiga"].sum()
    target_fittizio = 80000.0 
    percentuale = min(1.0, fatturato_totale / target_fittizio)

    st.markdown(f"""
        <div style="border-left: 5px solid #1f77b4; padding-left: 15px; margin: 25px 0;">
            <h2 style="margin:0; font-weight: 600; color: #1f77b4;">{cliente_sel}</h2>
            <p style="margin:0; color: #666; font-size: 15px;">ID CLIENTE: <b>{id_cliente_corrente}</b> | PERFORMANCE ANNO <b>{anno_sel}</b></p>
        </div>
    """, unsafe_allow_html=True)
    
    m1, m2, m3 = st.columns(3)
    m1.metric(f"💰 Fatturato {anno_sel}", f"€ {fatturato_totale:,.2f}")
    m2.metric("🎯 Obiettivo Annuale", f"€ {target_fittizio:,.0f}")
    
    mancante = target_fittizio - fatturato_totale
    if mancante > 0:
        m3.metric("📉 Gap al Target", f"€ {mancante:,.2f}", delta=f"-{mancante:,.2f}", delta_color="inverse")
    else:
        m3.metric("🎉 Target", "RAGGIUNTO", delta="COMPLETATO")

    st.progress(percentuale)

    # --- 6. GRAFICO MERCEOLOGICO ---
    st.divider()
    st.subheader(f"📦 Mix Prodotti Acquistati ({anno_sel})")
    res_merce = df_cliente.groupby("Merceologica")["ImportoNettoRiga"].sum().reset_index().sort_values("ImportoNettoRiga", ascending=True)
    
    fig_merce = px.bar(
        res_merce, x="ImportoNettoRiga", y="Merceologica", orientation='h',
        color_discrete_sequence=['#1f77b4'], text_auto='.2s'
    )
    fig_merce.update_layout(height=max(300, len(res_merce)*35), margin=dict(l=0, r=10, t=10, b=10))
    st.plotly_chart(fig_merce, use_container_width=True)

    # --- 7. DIARIO VISITE ---
    st.divider()
    st.subheader("📝 Diario Visite")
    
    with st.container(border=True):
        st.write(f"Registra un nuovo feedback per il cliente **{cliente_sel}**")
        
        c_v1, c_v2 = st.columns([1, 2])
        with c_v1:
            data_visita = st.date_input("📅 Data Visita", value=pd.Timestamp.now())
        
        nuova_nota = st.text_area(
            "Note della visita", 
            height=100, 
            placeholder="Esempio: Il cliente ha richiesto informazioni sui nuovi listini..."
        )
        
        if st.button("Salva nel Diario", type="primary", use_container_width=True):
            if nuova_nota:
                data_str = data_visita.strftime("%d/%m/%Y")
                # Qui simulo il salvataggio. In futuro:
                # conn.table("note").insert({"id_cliente": id_cliente_corrente, "nota": nuova_nota, "data": data_visita.isoformat()}).execute()
                st.success(f"Nota del {data_str} registrata con successo!")
                st.balloons()
            else:
                st.warning("Inserisci un testo per la nota prima di salvare.")

if __name__ == "__main__":
    show_clienti()