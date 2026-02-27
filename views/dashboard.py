import streamlit as st
import pandas as pd
import plotly.express as px

# --- FUNZIONE CARICAMENTO CON CACHE SU DISCO ---
@st.cache_data(persist="disk", ttl=3600)
def load_all_data(url, key):
    # Connessione interna alla funzione per la cache
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
        # Recupero esplicito delle colonne necessarie, incluso IdAgenteDoc
        response = supabase.table("fatturati").select(
            "AnnoRif,MeseRif,AgenteDoc,Cliente,ImportoNettoRiga,Merceologica,CodArt,IdAgenteDoc"
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
    # Recuperiamo l'ID dell'agente dalla sessione (assicuriamoci che sia stringa per il confronto)
    my_agente_id = str(user_data.get("agente_corrispondente"))
    
    # --- GESTIONE MEMORIA SESSIONE ---
    if 'df_vendite' not in st.session_state:
        df_raw = load_all_data(st.secrets["connections"]["supabase"]["url"], st.secrets["connections"]["supabase"]["key"])
        st.session_state['df_vendite'] = df_raw
    else:
        df_raw = st.session_state['df_vendite']

    if df_raw.empty:
        st.warning("⚠️ Nessun dato trovato.")
        return

    # --- PULIZIA E CONVERSIONE DATI ---
    # Escludiamo RAEE
    df_base = df_raw[~df_raw["CodArt"].astype(str).str.upper().str.contains('RAEE', na=False)].copy()
    
    # Conversione numerica importi e normalizzazione ID Agente
    df_base["ImportoNettoRiga"] = pd.to_numeric(df_base["ImportoNettoRiga"], errors='coerce').fillna(0)
    df_base["IdAgenteDoc"] = df_base["IdAgenteDoc"].astype(str)

    st.title("📊 Performance")
    
    # --- SEZIONE FILTRI ---
    with st.container(border=True):
        # Definiamo le colonne in base al ruolo
        if user_data["ruolo"] != "agente":
            f1, f2, f3 = st.columns([1, 1, 1.5])
        else:
            f1, f2 = st.columns(2)
            f3 = None

        with f1:
            anno_sel = st.selectbox("📅 Anno", sorted(df_base["AnnoRif"].unique().tolist(), reverse=True))
        with f2:
            mese_sel = st.selectbox("📅 Mese", ["Tutti"] + sorted(df_base["MeseRif"].unique().tolist()))
        
        # Filtro Agente per Admin
        agente_nome_sel = "Tutti"
        if f3 is not None:
            with f3:
                # Creiamo una mappatura Nome -> ID per l'interfaccia Admin
                mappa_agenti = df_base.groupby(["IdAgenteDoc", "AgenteDoc"]).size().reset_index()
                opzioni_agenti = ["Tutti"] + mappa_agenti["AgenteDoc"].tolist()
                agente_nome_sel = st.selectbox("👤 Filtra per Agente", opzioni_agenti)

    # --- LOGICA DI FILTRAGGIO FINALE ---
    df_final = df_base[df_base["AnnoRif"] == anno_sel]
    
    if mese_sel != "Tutti":
        df_final = df_final[df_final["MeseRif"] == mese_sel]
    
    # Filtraggio per ID
    if user_data["ruolo"] == "agente":
        # Se è un agente, vede SOLO il suo ID
        df_final = df_final[df_final["IdAgenteDoc"] == my_agente_id]
    else:
        # Se è admin e ha scelto un nome, troviamo l'ID corrispondente
        if agente_nome_sel != "Tutti":
            id_scelto = mappa_agenti[mappa_agenti["AgenteDoc"] == agente_nome_sel]["IdAgenteDoc"].values[0]
            df_final = df_final[df_final["IdAgenteDoc"] == id_scelto]

    # --- VISUALIZZAZIONE DATI ---
    if not df_final.empty:
        # Metrica Fatturato (Stile "Fine")
        totale_fatturato = df_final['ImportoNettoRiga'].sum()
        st.markdown(f"""
            <div style='text-align: right; padding-top: 10px; border-top: 1px solid #eee; margin-top: 10px; margin-bottom: 20px;'>
                <span style='font-size: 13px; color: #888; text-transform: uppercase; letter-spacing: 0.5px;'>Fatturato Netto {anno_sel}</span><br>
                <span style='font-size: 26px; font-weight: 500; color: #31333F;'>€ {totale_fatturato:,.2f}</span>
            </div>
        """, unsafe_allow_html=True)

        # 1. Grafico Andamento Mensile (Area Chart)
        st.subheader("📈 Andamento Mensile")
        res_mensile = df_final.groupby("MeseRif")["ImportoNettoRiga"].sum().reset_index()
        mesi_full = pd.DataFrame({"MeseRif": range(1, 13)})
        res_mensile = pd.merge(mesi_full, res_mensile, on="MeseRif", how="left").fillna(0)
        
        nomi_mesi = {1: "Gen", 2: "Feb", 3: "Mar", 4: "Apr", 5: "Mag", 6: "Giu", 7: "Lug", 8: "Ago", 9: "Set", 10: "Ott", 11: "Nov", 12: "Dic"}
        res_mensile["Mese"] = res_mensile["MeseRif"].map(nomi_mesi)

        fig_linea = px.area(
            res_mensile, x="Mese", y="ImportoNettoRiga", 
            markers=True, template="plotly_white", color_discrete_sequence=['#1f77b4']
        )
        fig_linea.update_layout(
            yaxis_range=[0, res_mensile["ImportoNettoRiga"].max() * 1.25 if res_mensile["ImportoNettoRiga"].max() > 0 else 1000],
            height=350, margin=dict(l=20, r=20, t=30, b=20),
            xaxis_title=None, yaxis_title="Euro (€)"
        )
        st.plotly_chart(fig_linea, use_container_width=True)

        # 2. Performance Agenti (Solo per Admin)
        if user_data["ruolo"] != "agente":
            st.subheader("👤 Performance per Agente")
            res_agenti = df_final.groupby("AgenteDoc")["ImportoNettoRiga"].sum().reset_index().sort_values("ImportoNettoRiga", ascending=False)
            st.bar_chart(res_agenti, x="AgenteDoc", y="ImportoNettoRiga", color="#1f77b4")

        # 3. Distribuzione per Categoria Merceologica
        st.subheader("📦 Fatturato per Categoria")
        res_merce = df_final.groupby("Merceologica")["ImportoNettoRiga"].sum().reset_index().sort_values("ImportoNettoRiga", ascending=True)
        fig_merce = px.bar(
            res_merce, x="ImportoNettoRiga", y="Merceologica", 
            orientation='h', color_discrete_sequence=['#1f77b4'], text_auto='.2s'
        )
        fig_merce.update_layout(height=max(400, len(res_merce)*30), yaxis_title=None, xaxis_title="Volume (€)")
        st.plotly_chart(fig_merce, use_container_width=True)
    
    else:
        st.info("Nessun dato disponibile per i filtri selezionati.")