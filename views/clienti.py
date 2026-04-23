import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from streamlit_searchbox import st_searchbox
from st_supabase_connection import SupabaseConnection
from datetime import date

def show_clienti():
    # --- 1. ACCESSO E CONNESSIONE ---
    if 'user_info' not in st.session_state:
        st.error("Effettua il login per accedere.")
        return
    
    user_data = st.session_state['user_info']
    my_agente_id = str(user_data.get("agente_corrispondente", "")).strip()
    ruolo = user_data.get("ruolo")

    conn = st.connection(
        "supabase",
        type=SupabaseConnection,
        url=st.secrets["connections"]["supabase"]["url"],
        key=st.secrets["connections"]["supabase"]["key"]
    )

    # --- 2. FUNZIONI DI RECUPERO DATI ---
    def search_clienti(search_term: str):
        if not search_term or len(search_term) < 2: return []
        query = conn.table("rubrica_clienti").select("ragione_sociale, id_cliente")
        if ruolo == "agente": 
            query = query.eq("id_agente", my_agente_id)
        res = query.ilike("ragione_sociale", f"%{search_term}%").limit(15).execute()
        return [(d["ragione_sociale"], d["id_cliente"]) for d in res.data] if res.data else []

    @st.cache_data(ttl=600)
    def get_cliente_years(codice_cliente):
        res = conn.table("fatturati").select("AnnoRif").eq("IdAnagrafica", codice_cliente).execute()
        res_2026 = conn.table("fatturati").select("AnnoRif").eq("IdAnagrafica", codice_cliente).eq("AnnoRif", 2026).limit(1).execute()
        anni = [d['AnnoRif'] for d in res.data] if res.data else []
        if res_2026.data: anni.append(2026)
        return sorted(list(set([int(a) for a in anni])), reverse=True)

    @st.cache_data(ttl=600)
    def get_data_for_single_year(codice_cliente, anno):
        res = conn.table("fatturati").select("*").eq("IdAnagrafica", codice_cliente).eq("AnnoRif", int(anno)).limit(3000).execute()
        df = pd.DataFrame(res.data)
        if not df.empty:
            df = df[~df["CodArt"].astype(str).str.upper().str.contains('RAEE', na=False)].copy()
            df["ImportoNettoRiga"] = pd.to_numeric(df["ImportoNettoRiga"], errors='coerce').fillna(0)
            df["MeseRif"] = df["MeseRif"].astype(int)
            df["AnnoRif"] = str(anno)
        return df

    # --- 3. FILTRI DI INTERFACCIA ---
    st.subheader("👥 Analisi Clienti")
    
    with st.container(border=True):
        cliente_id_sel = st_searchbox(search_clienti, key="sb_final_v4", placeholder="🔍 Cerca cliente...", label="🏢 Seleziona Cliente")
        
        if not cliente_id_sel:
            st.info("💡 Digita il nome di un cliente per iniziare."); return

        anni_disp = get_cliente_years(cliente_id_sel)
        if cliente_id_sel:
            st.sidebar.write(f"🔍 DEBUG Cliente Selezionato ID: `{cliente_id_sel}`")
            
            # Test rapido: conta quanti record ci sono in fatturati per questo ID senza filtri di anno
            test_res = conn.table("fatturati").select("count", count="exact").eq("IdAnagrafica", cliente_id_sel).execute()
            st.sidebar.write(f"📊 Record totali in fatturati: {test_res.count}")
        c1, c2 = st.columns(2)
        with c1:
            anni_scelti = st.multiselect("📅 Confronta Anni", anni_disp, default=[anni_disp[0]] if anni_disp else [])
        with c2:
            mesi_nomi = {1:'Gen', 2:'Feb', 3:'Mar', 4:'Apr', 5:'Mag', 6:'Giu', 7:'Lug', 8:'Ago', 9:'Set', 10:'Ott', 11:'Nov', 12:'Dic'}
            mesi_scelti = st.multiselect("🗓️ Filtra Mesi", options=list(mesi_nomi.keys()), format_func=lambda x: mesi_nomi[x], default=list(range(1, 13)))

    # --- 4. RAGIONE SOCIALE ---
    res_info = conn.table("rubrica_clienti").select("ragione_sociale").eq("id_cliente", cliente_id_sel).single().execute()
    #st.header(f"🏢 {res_info.data['ragione_sociale'] if res_info.data else 'Scheda Cliente'}")

    # --- 5. CARICAMENTO DATI ---
    df_list = []
    for anno in anni_scelti:
        df_anno = get_data_for_single_year(cliente_id_sel, anno)
        if not df_anno.empty:
            df_list.append(df_anno)
    
    if df_list:
        df_totale = pd.concat(df_list)
        df = df_totale[df_totale["MeseRif"].isin(mesi_scelti)].copy()
        
        # --- METRICHE (CON CONTEGGIO ORDINI UNIVOCI) ---
        cols = st.columns(len(anni_scelti))
        for i, anno in enumerate(sorted(anni_scelti, reverse=True)):
            df_a = df[df["AnnoRif"] == str(anno)]
            somma_fatturato = df_a['ImportoNettoRiga'].sum()
            
            # Contiamo gli ordini univoci usando IdTestata (o NumeroDocumento)
            # Se la colonna ha un nome diverso nel tuo DB, cambiala qui sotto
            campo_ordine = "IdTestata" if "IdTestata" in df_a.columns else df_a.columns[0]
            num_ordini_univoci = df_a[campo_ordine].nunique()
            
            with cols[i]:
                st.metric(
                    label=f"Fatturato {anno}", 
                    value=f"€ {somma_fatturato:,.2f}", 
                    delta=f"{num_ordini_univoci} ordini totali",
                    delta_color="normal"
                )
    
        st.divider()

        # --- 6. GRAFICI ---
        st.subheader("📈 Andamento Mensile")
        mensile_res = df.groupby(["AnnoRif", "MeseRif"])["ImportoNettoRiga"].sum().reset_index()
        fig_evol = px.line(mensile_res, x="MeseRif", y="ImportoNettoRiga", color="AnnoRif", markers=True, template="plotly_white")
        fig_evol.update_layout(xaxis=dict(tickmode='array', tickvals=list(mesi_nomi.keys()), ticktext=list(mesi_nomi.values())), height=400)
        st.plotly_chart(fig_evol, use_container_width=True)

        st.subheader("🏆 Marchi")
        res_fam = df.groupby(["Famiglia", "AnnoRif"])["ImportoNettoRiga"].sum().reset_index()
        top_fam_list = res_fam.groupby("Famiglia")["ImportoNettoRiga"].sum().nlargest(15).index
        df_fam_plot = res_fam[res_fam["Famiglia"].isin(top_fam_list)]

        fig_fam = px.bar(df_fam_plot, x="ImportoNettoRiga", y="Famiglia", color="AnnoRif", barmode="group", orientation='h', template="plotly_white")
        fig_fam.update_layout(yaxis={'categoryorder':'total ascending'}, height=600)
        st.plotly_chart(fig_fam, use_container_width=True)

        st.subheader("📊 Cat Merceologica")
        res_mer = df.groupby(["Merceologica", "AnnoRif"])["ImportoNettoRiga"].sum().reset_index()
        fig_mer = px.bar(res_mer, x="ImportoNettoRiga", y="Merceologica", color="AnnoRif", barmode="group", orientation='h', template="plotly_white")
        fig_mer.update_layout(yaxis={'categoryorder':'total ascending'}, height=600)
        st.plotly_chart(fig_mer, use_container_width=True)

    else:
        st.warning("Nessun dato di fatturato trovato.")

    st.divider()

    # --- ANALISI CIAMBELLA CATEGORIE PER IL CLIENTE (VERSIONE CLEAN) ---
        
    st.subheader(f"🎯 Mix Merceologico Cliente")

    # Raggruppamento dati per il grafico a torta
    res_focus_client = df.groupby("Merceologica")["ImportoNettoRiga"].sum().reset_index()
    totale_periodo_cliente = res_focus_client["ImportoNettoRiga"].sum()

    # Metrica del totale per il periodo selezionato
    st.metric(label="Fatturato Totale nel Periodo", value=f"€ {totale_periodo_cliente:,.2f}")

    # Creazione del grafico a ciambella
    fig_pie_client = px.pie(
        res_focus_client, 
        values='ImportoNettoRiga', 
        names='Merceologica',
        hole=0.5,
        template="plotly_white",
        color_discrete_sequence=px.colors.qualitative.Safe
    )
        
    # Pulizia etichette (solo hover) per coerenza con la dashboard
    fig_pie_client.update_traces(
        textinfo='none', 
        hovertemplate="<b>%{label}</b><br>Fatturato: € %{value:,.2f}<br>Incidenza: %{percent}"
    )
        
    fig_pie_client.update_layout(
        height=500,
        showlegend=True,
        legend=dict(orientation="v", y=0.5, x=1, title="Categorie"),
        margin=dict(t=20, b=20, l=20, r=20)
    )

    st.plotly_chart(fig_pie_client, use_container_width=True)

    # --- 7. DIARIO VISITE (DEMO IN FONDO) ---
    with st.container(border=True):
        st.subheader("📒 Diario Visite")
        c_v1, c_v2 = st.columns([1, 2])
        with c_v1:
            st.date_input("Data Visita", value=date.today(), key="v_date_final_v4")
            if st.button("💾 Salva Nota", use_container_width=True):
                st.success("Nota salvata nel diario (Simulazione)!")
        with c_v2:
            st.text_area("Note incontro", placeholder="Inserisci qui i dettagli della visita...", key="v_notes_final_v4", height=100)

        st.markdown("**🕒 Ultime note salvate:**")
        st.info("📌 **15/01/2026**: Cliente interessato a pacchetti promozionali. Richiesto catalogo aggiornato.")
        st.info("📌 **04/12/2025**: Sollecitato pagamento bonifico scaduto.")

if __name__ == "__main__":
    show_clienti()