import streamlit as st
import pandas as pd
import plotly.express as px

# --- 1. FUNZIONE CARICAMENTO DATI CON FILTRO LATO SERVER ---
@st.cache_data(persist="disk", ttl=3600)
def load_all_data(url, key, agente_id=None):
    from supabase import create_client
    supabase = create_client(url, key)
    
    placeholder = st.empty()
    with placeholder.container():
        testo_caricamento = f"Sincronizzazione Agente: {agente_id}" if agente_id else "Sincronizzazione Database Completo (Admin)"
        st.markdown(f"### 🔄 {testo_caricamento}...")
        progress_bar = st.progress(0)
        status_text = st.empty()
    
    all_data = []
    chunk_size = 1000
    start = 0
    total_estimated = 80000 

    while True:
        # Query con selezione esplicita di tutte le colonne necessarie
        query = supabase.table("fatturati").select(
            "AnnoRif,MeseRif,AgenteDoc,Cliente,ImportoNettoRiga,Merceologica,CodArt,IdAgenteDoc,Famiglia"
        )
        
        # Filtro lato Database (Supabase) per efficienza
        if agente_id:
            query = query.eq("IdAgenteDoc", agente_id)
        
        response = query.range(start, start + chunk_size - 1).execute()
        
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
    ruolo = user_data.get("ruolo")
    
    # Identificativo univoco per la gestione della cache utente
    id_per_download = my_agente_id if ruolo == "agente" else None
    current_cache_key = id_per_download if id_per_download else "ADMIN_FULL"

    # Controllo cambio utente per svuotare la session_state
    if 'last_loaded_key' not in st.session_state or st.session_state['last_loaded_key'] != current_cache_key:
        if 'df_vendite' in st.session_state:
            del st.session_state['df_vendite']
        st.session_state['last_loaded_key'] = current_cache_key

    # Caricamento effettivo
    if 'df_vendite' not in st.session_state:
        df_raw = load_all_data(
            st.secrets["connections"]["supabase"]["url"], 
            st.secrets["connections"]["supabase"]["key"],
            agente_id=id_per_download
        )
        st.session_state['df_vendite'] = df_raw
    else:
        df_raw = st.session_state['df_vendite']

    if df_raw.empty:
        st.warning("⚠️ Nessun dato trovato per l'utente corrente.")
        return

    # --- 2. PULIZIA E NORMALIZZAZIONE INTEGRALE ---
    df_base = df_raw.copy()
    
    # Rimozione articoli RAEE
    if "CodArt" in df_base.columns:
        df_base = df_base[~df_base["CodArt"].astype(str).str.upper().str.contains('RAEE', na=False)].copy()
    
    df_base["ImportoNettoRiga"] = pd.to_numeric(df_base["ImportoNettoRiga"], errors='coerce').fillna(0)
    df_base["AnnoRif"] = pd.to_numeric(df_base["AnnoRif"], errors='coerce')
    df_base["MeseRif"] = df_base["MeseRif"].astype(str).str.zfill(2)
    df_base["IdAgenteDoc"] = df_base["IdAgenteDoc"].astype(str)
    df_base["AgenteDoc"] = df_base["AgenteDoc"].astype(str).str.upper().str.strip()
    
    if "Famiglia" in df_base.columns:
        df_base["Famiglia"] = df_base["Famiglia"].astype(str).str.upper().str.strip()
        df_base["Famiglia"] = df_base["Famiglia"].replace(["0", "NAN", "NONE", ""], "NON SPECIFICATO")
    else:
        df_base["Famiglia"] = "NON SPECIFICATO"

    st.subheader(f"📊 Performance & Analisi")
    
    # --- 3. SEZIONE FILTRI ---
    with st.container(border=True):
        if ruolo != "agente":
            f1, f2, f3 = st.columns([1.5, 1.5, 1.5])
        else:
            f1, f2 = st.columns(2)
            f3 = None

        with f1:
            anni_disp = sorted(df_base["AnnoRif"].dropna().unique().astype(int).tolist(), reverse=True)
            default_anno = [2026] if 2026 in anni_disp else [anni_disp[0]]
            anni_sel = st.multiselect("📅 Anni da confrontare", options=anni_disp, default=default_anno)
        
        with f2:
            mesi_disp = sorted(df_base["MeseRif"].unique().tolist())
            mesi_default = [m for m in ['01', '02', '03'] if m in mesi_disp]
            mesi_sel = st.multiselect("📅 Mesi da includere", options=mesi_disp, default=mesi_default if mesi_default else mesi_disp)
        
        agente_nome_sel = "Tutti"
        if f3 is not None:
            with f3:
                mappa_agenti = df_base.groupby("AgenteDoc")["IdAgenteDoc"].first().reset_index()
                opzioni_agenti = ["Tutti"] + mappa_agenti["AgenteDoc"].tolist()
                agente_nome_sel = st.selectbox("👤 Filtra per Agente", opzioni_agenti)

    # --- 4. LOGICA DI FILTRAGGIO FINALE ---
    df_final = df_base[df_base["AnnoRif"].isin(anni_sel)]
    if mesi_sel:
        df_final = df_final[df_final["MeseRif"].isin(mesi_sel)]
    
    if ruolo != "agente" and agente_nome_sel != "Tutti":
        id_scelto = mappa_agenti[mappa_agenti["AgenteDoc"] == agente_nome_sel]["IdAgenteDoc"].values[0]
        df_final = df_final[df_final["IdAgenteDoc"] == id_scelto]

    # --- 5. VISUALIZZAZIONE DATI ---
    if not df_final.empty:
        # Metriche Totali con calcolo variazione percentuale (Delta)
        st.divider()
        anni_ordinati = sorted(anni_sel)
        cols_metric = st.columns(len(anni_ordinati))

        for i, anno in enumerate(anni_ordinati):
            val_attuale = df_final[df_final["AnnoRif"] == anno]["ImportoNettoRiga"].sum()
            delta_val = None
            if i > 0:
                val_prec = df_final[df_final["AnnoRif"] == anni_ordinati[i-1]]["ImportoNettoRiga"].sum()
                if val_prec > 0:
                    variazione = ((val_attuale - val_prec) / val_prec) * 100
                    delta_val = f"{variazione:+.1f}% vs {anni_ordinati[i-1]}"
                else:
                    delta_val = "N/A"
            
            cols_metric[i].metric(label=f"Totale {anno}", value=f"€ {val_attuale:,.2f}", delta=delta_val)

        # GRAFICO 1: ANDAMENTO MENSILE YoY (Linee)
        st.divider()
        st.subheader("📈 Andamento Mensile Year-over-Year")
        res_mensile = df_final.groupby(["AnnoRif", "MeseRif"])["ImportoNettoRiga"].sum().reset_index()
        res_mensile["AnnoRif"] = res_mensile["AnnoRif"].astype(str)
        nomi_mesi = {"01":"Gen","02":"Feb","03":"Mar","04":"Apr","05":"Mag","06":"Giu","07":"Lug","08":"Ago","09":"Set","10":"Ott","11":"Nov","12":"Dic"}
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

        # GRAFICO 2: PERFORMANCE AGENTI (Solo Admin)
        if ruolo != "agente":
            st.divider()
            st.subheader("👤 Performance Agenti")
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

        # GRAFICO 3: DISTRIBUZIONE PER MARCHIO (FAMIGLIA) - ORDINATO CON IL PIÙ GRANDE IN ALTO
        st.divider()
        st.subheader("🏆 Distribuzione per Marchio")
        res_famiglia = df_final.groupby(["Famiglia", "AnnoRif"])["ImportoNettoRiga"].sum().reset_index()
        res_famiglia["AnnoRif"] = res_famiglia["AnnoRif"].astype(str)
        
        fig_famiglia = px.bar(
            res_famiglia, x="ImportoNettoRiga", y="Famiglia", color="AnnoRif",
            barmode="group", orientation='h', text_auto='.2s',
            template="plotly_white",
            color_discrete_sequence=px.colors.qualitative.Bold
        )
        # Il trucco per mettere il più grande in alto è l'asse Y con total ascending
        fig_famiglia.update_layout(
            height=max(400, len(res_famiglia.Famiglia.unique())*35), 
            yaxis={'categoryorder':'total ascending', 'title': None},
            legend=dict(orientation="h", y=1.02, x=1, title=None)
        )
        st.plotly_chart(fig_famiglia, use_container_width=True)

        # GRAFICO 4: CATEGORIE MERCEOLOGICHE - ORDINATO CON IL PIÙ GRANDE IN ALTO
        st.divider()
        st.subheader("📦 Distribuzione per Categoria")
        res_merce = df_final.groupby(["Merceologica", "AnnoRif"])["ImportoNettoRiga"].sum().reset_index()
        res_merce["AnnoRif"] = res_merce["AnnoRif"].astype(str)

        fig_merce = px.bar(
            res_merce, x="ImportoNettoRiga", y="Merceologica", color="AnnoRif",
            barmode="group", orientation='h', text_auto='.2s',
            template="plotly_white",
            color_discrete_sequence=px.colors.qualitative.Bold
        )
        fig_merce.update_layout(
            height=max(400, len(res_merce.Merceologica.unique())*40),
            yaxis={'categoryorder':'total ascending', 'title': None},
            legend=dict(orientation="h", y=1.02, x=1, title=None)
        )
        st.plotly_chart(fig_merce, use_container_width=True)

        # --- ANALISI DETTAGLIATA SINGOLO MARCHIO (VERSIONE CLEAN) ---
        st.divider()
        st.subheader("🔍 Focus Dettagliato sul Marchio")

        # 1. Selettore marchio
        marchi_disp = sorted(df_final["Famiglia"].unique().tolist())
        marchio_focus = st.selectbox("Seleziona un Marchio per l'analisi merceologica", marchi_disp)

        # 2. Filtraggio dati
        df_focus = df_final[df_final["Famiglia"] == marchio_focus]
        res_focus = df_focus.groupby("Merceologica")["ImportoNettoRiga"].sum().reset_index()
        totale_marchio = res_focus["ImportoNettoRiga"].sum()

        # 3. Layout: Totale in alto e Grafico sotto
        st.metric(label=f"Fatturato Totale {marchio_focus}", value=f"€ {totale_marchio:,.2f}")

        fig_pie = px.pie(
            res_focus, 
            values='ImportoNettoRiga', 
            names='Merceologica',
            hole=0.5, # Effetto ciambella leggermente più pronunciato
            template="plotly_white",
            color_discrete_sequence=px.colors.qualitative.Safe
        )
        
        # Rimuoviamo le etichette interne (textinfo='none')
        fig_pie.update_traces(
            textinfo='none', 
            hovertemplate="<b>%{label}</b><br>Fatturato: € %{value:,.2f}<br>Incidenza: %{percent}"
        )
        
        fig_pie.update_layout(
            height=500,
            showlegend=True,
            legend=dict(orientation="v", y=0.5, x=1, title="Categorie"),
            margin=dict(t=20, b=20, l=20, r=20)
        )

        st.plotly_chart(fig_pie, use_container_width=True)

        # GRAFICO 5: TOP 30 CLIENTI - ORDINATO CON IL PIÙ GRANDE IN ALTO
        st.divider()
        st.subheader("🏙️ Top 30 Clienti per Fatturato")
        res_clienti = df_final.groupby("Cliente")["ImportoNettoRiga"].sum().sort_values(ascending=False).head(30).reset_index()

        fig_clienti = px.bar(
            res_clienti, x="ImportoNettoRiga", y="Cliente", orientation='h',
            text_auto='.3s', color="ImportoNettoRiga", color_continuous_scale="Viridis",
            template="plotly_white"
        )
        fig_clienti.update_layout(
            height=800, showlegend=False, coloraxis_showscale=False, 
            yaxis={'categoryorder':'total ascending', 'title': None}
        )
        st.plotly_chart(fig_clienti, use_container_width=True)
    
    else:
        st.info("Nessun dato trovato per i filtri selezionati.")

if __name__ == "__main__":
    show_dashboard()