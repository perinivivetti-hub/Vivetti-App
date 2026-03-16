import streamlit as st
import pandas as pd
import plotly.express as px

# --- FUNZIONE CARICAMENTO CON CACHE SU DISCO ---
@st.cache_data(persist="disk", ttl=3600)
def load_all_data(url, key):
    from supabase import create_client
    supabase = create_client(url, key)
    
    placeholder = st.empty()
    with placeholder.container():
        st.markdown("### 🔄 Sincronizzazione Database...")
        progress_bar = st.progress(0)
        status_text = st.empty()
    
    all_data = []
    chunk_size = 1000
    start = 0
    total_estimated = 80000 

    while True:
        # La query include ora esplicitamente CodArt e Famiglia
        response = supabase.table("fatturati").select(
            "AnnoRif,MeseRif,AgenteDoc,Cliente,ImportoNettoRiga,Merceologica,CodArt,IdAgenteDoc,Famiglia"
        ).range(start, start + chunk_size - 1).execute()
        
        data = response.data
        if not data: break
        all_data.extend(data)
        if len(data) < chunk_size: break
        start += chunk_size
        progress_bar.progress(min(start / total_estimated, 1.0))
        status_text.markdown(f"Record recuperati: **{len(all_data):,}**")

    placeholder.empty()
    return pd.DataFrame(all_data)

def show_dashboard():
    if 'user_info' not in st.session_state:
        st.error("Errore: Utente non loggato.")
        return
    
    user_data = st.session_state['user_info']
    my_agente_id = str(user_data.get("agente_corrispondente"))
    
    if 'df_vendite' not in st.session_state:
        df_raw = load_all_data(st.secrets["connections"]["supabase"]["url"], st.secrets["connections"]["supabase"]["key"])
        st.session_state['df_vendite'] = df_raw
    else:
        df_raw = st.session_state['df_vendite']

    if df_raw.empty:
        st.warning("⚠️ Nessun dato trovato.")
        return

    # --- 1. PULIZIA E NORMALIZZAZIONE ---
    df_base = df_raw.copy()
    
    # Fix per errore 'CodArt': controlliamo se esiste prima del filtro RAEE
    if "CodArt" in df_base.columns:
        df_base = df_base[~df_base["CodArt"].astype(str).str.upper().str.contains('RAEE', na=False)].copy()
    
    df_base["ImportoNettoRiga"] = pd.to_numeric(df_base["ImportoNettoRiga"], errors='coerce').fillna(0)
    df_base["IdAgenteDoc"] = df_base["IdAgenteDoc"].astype(str)
    df_base["AgenteDoc"] = df_base["AgenteDoc"].astype(str).str.upper().str.strip()
    
    # Gestione colonna Famiglia (Marchio)
    if "Famiglia" in df_base.columns:
        df_base["Famiglia"] = df_base["Famiglia"].astype(str).str.upper().str.strip()
        df_base["Famiglia"] = df_base["Famiglia"].replace(["0", "NAN", "NONE", ""], "NON SPECIFICATO")
    else:
        df_base["Famiglia"] = "NON SPECIFICATO"

    st.subheader("📊 Performance & Analisi Comparativa")
    
    # --- 2. SEZIONE FILTRI ---
    with st.container(border=True):
        if user_data["ruolo"] != "agente":
            f1, f2, f3 = st.columns([1.5, 1.5, 1.5])
        else:
            f1, f2 = st.columns(2)
            f3 = None

        with f1:
            anni_disp = sorted(df_base["AnnoRif"].unique().tolist(), reverse=True)
            anni_sel = st.multiselect("📅 Anni da confrontare", options=anni_disp, default=[anni_disp[0]])
        
        with f2:
            mesi_disp = sorted(df_base["MeseRif"].unique().tolist())
            mesi_sel = st.multiselect("📅 Mesi da includere", options=mesi_disp, default=mesi_disp)
        
        agente_nome_sel = "Tutti"
        if f3 is not None:
            with f3:
                mappa_agenti = df_base.groupby("AgenteDoc")["IdAgenteDoc"].first().reset_index()
                opzioni_agenti = ["Tutti"] + mappa_agenti["AgenteDoc"].tolist()
                agente_nome_sel = st.selectbox("👤 Filtra per Agente", opzioni_agenti)

    # --- 3. LOGICA DI FILTRAGGIO ---
    df_final = df_base[df_base["AnnoRif"].isin(anni_sel)]
    if mesi_sel:
        df_final = df_final[df_final["MeseRif"].isin(mesi_sel)]
    
    if user_data["ruolo"] == "agente":
        df_final = df_final[df_final["IdAgenteDoc"] == my_agente_id]
    elif agente_nome_sel != "Tutti":
        id_scelto = mappa_agenti[mappa_agenti["AgenteDoc"] == agente_nome_sel]["IdAgenteDoc"].values[0]
        df_final = df_final[df_final["IdAgenteDoc"] == id_scelto]

    # --- 4. VISUALIZZAZIONE DATI ---
    if not df_final.empty:
        # Metriche Totali per Anno
        cols_metric = st.columns(len(anni_sel) if anni_sel else 1)
        for i, anno in enumerate(sorted(anni_sel, reverse=True)):
            val = df_final[df_final["AnnoRif"] == anno]["ImportoNettoRiga"].sum()
            cols_metric[i].metric(f"Totale {anno}", f"€ {val:,.2f}")

        # --- GRAFICO 1: ANDAMENTO MENSILE YoY ---
        st.divider()
        st.subheader("📈 Andamento Mensile Year-over-Year")
        res_mensile = df_final.groupby(["AnnoRif", "MeseRif"])["ImportoNettoRiga"].sum().reset_index()
        res_mensile["AnnoRif"] = res_mensile["AnnoRif"].astype(str)
        nomi_mesi = {1: "Gen", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Mag", 6: "Giu", 7: "Lug", 8: "Ago", 9: "Set", 10: "Ott", 11: "Nov", 12: "Dic"}
        res_mensile["Mese"] = res_mensile["MeseRif"].map(nomi_mesi)
        res_mensile = res_mensile.sort_values("MeseRif")

        fig_linea = px.line(
            res_mensile, x="Mese", y="ImportoNettoRiga", color="AnnoRif",
            markers=True, template="plotly_white",
            color_discrete_sequence=px.colors.qualitative.Bold,
            labels={"ImportoNettoRiga": "Fatturato (€)", "AnnoRif": "Anno"}
        )
        fig_linea.update_layout(height=400, xaxis_title=None, legend=dict(orientation="h", y=1.1, x=1, title=None))
        st.plotly_chart(fig_linea, use_container_width=True)

        # --- GRAFICO 2: PERFORMANCE AGENTI COMPARATIVA (Solo Admin) ---
        if user_data["ruolo"] != "agente":
            st.divider()
            st.subheader("👤 Performance Agenti: Confronto Anni")
            res_agenti = df_final.groupby(["AgenteDoc", "AnnoRif"])["ImportoNettoRiga"].sum().reset_index()
            res_agenti["AnnoRif"] = res_agenti["AnnoRif"].astype(str)
            ordine_agenti = res_agenti.groupby("AgenteDoc")["ImportoNettoRiga"].sum().sort_values(ascending=False).index
            
            fig_agenti = px.bar(
                res_agenti, x="AgenteDoc", y="ImportoNettoRiga", color="AnnoRif",
                barmode="group", text_auto='.2s',
                category_orders={"AgenteDoc": ordine_agenti},
                template="plotly_white",
                color_discrete_sequence=px.colors.qualitative.Bold
            )
            fig_agenti.update_layout(height=500, xaxis_tickangle=-45, legend=dict(orientation="h", y=1.1, x=1, title=None))
            st.plotly_chart(fig_agenti, use_container_width=True)

        # --- GRAFICO 3: DISTRIBUZIONE PER MARCHIO (FAMIGLIA) ---
        st.divider()
        st.subheader("🏆 Distribuzione per Marchio")
        res_famiglia = df_final.groupby(["Famiglia", "AnnoRif"])["ImportoNettoRiga"].sum().reset_index()
        res_famiglia["AnnoRif"] = res_famiglia["AnnoRif"].astype(str)
        ordine_famiglia = res_famiglia.groupby("Famiglia")["ImportoNettoRiga"].sum().sort_values(ascending=True).index

        fig_famiglia = px.bar(
            res_famiglia, x="ImportoNettoRiga", y="Famiglia", color="AnnoRif",
            barmode="group", orientation='h',
            category_orders={"Famiglia": ordine_famiglia},
            template="plotly_white",
            color_discrete_sequence=px.colors.qualitative.Bold, text_auto='.2s'
        )
        fig_famiglia.update_layout(height=max(400, len(res_famiglia.Famiglia.unique())*35), yaxis_title=None)
        st.plotly_chart(fig_famiglia, use_container_width=True)

        # --- GRAFICO 4: CATEGORIE MERCEOLOGICHE ---
        st.divider()
        st.subheader("📦 Distribuzione per Categoria")
        res_merce = df_final.groupby(["Merceologica", "AnnoRif"])["ImportoNettoRiga"].sum().reset_index()
        res_merce["AnnoRif"] = res_merce["AnnoRif"].astype(str)
        res_merce = res_merce.sort_values("ImportoNettoRiga", ascending=True)

        fig_merce = px.bar(
            res_merce, x="ImportoNettoRiga", y="Merceologica", color="AnnoRif",
            barmode="group", orientation='h', 
            color_discrete_sequence=px.colors.qualitative.Bold, text_auto='.2s'
        )
        fig_merce.update_layout(height=max(400, len(res_merce.Merceologica.unique())*40), yaxis_title=None)
        st.plotly_chart(fig_merce, use_container_width=True)

        # --- GRAFICO 5: TOP 30 CLIENTI ---
        st.divider()
        st.subheader("🏙️ Top 30 Clienti per Fatturato")
        res_clienti = df_final.groupby("Cliente")["ImportoNettoRiga"].sum().sort_values(ascending=False).head(30).reset_index()
        res_clienti = res_clienti.sort_values("ImportoNettoRiga", ascending=True)

        fig_clienti = px.bar(
            res_clienti, x="ImportoNettoRiga", y="Cliente", orientation='h',
            text_auto='.3s', color="ImportoNettoRiga", color_continuous_scale="Viridis",
            template="plotly_white"
        )
        fig_clienti.update_layout(height=800, showlegend=False, coloraxis_showscale=False, yaxis_title=None)
        st.plotly_chart(fig_clienti, use_container_width=True)
    
    else:
        st.info("Nessun dato trovato per i filtri selezionati.")

if __name__ == "__main__":
    show_dashboard()