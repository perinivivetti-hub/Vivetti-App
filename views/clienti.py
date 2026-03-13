import streamlit as st
import pandas as pd
import plotly.express as px
from streamlit_searchbox import st_searchbox
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

    # --- 2. FUNZIONI DI RICERCA E CARICAMENTO ---

    def search_clienti(search_term: str):
        """Funzione per la Searchbox: cerca nella rubrica anagrafica"""
        if not search_term or len(search_term) < 2:
            return []
        
        query = conn.table("rubrica_clienti").select("ragione_sociale")
        
        # Filtro per Agente se non è Admin
        if user_data["ruolo"] == "agente":
            query = query.eq("id_agente", my_agente_id)
            
        # Ricerca parziale (ilike)
        res = query.ilike("ragione_sociale", f"%{search_term}%").limit(15).execute()
        return [d["ragione_sociale"] for d in res.data] if res.data else []

    @st.cache_data(ttl=600)
    def get_cliente_years(nome_cliente):
        """Recupera gli anni in cui il cliente ha fatturato"""
        res = conn.table("fatturati").select("AnnoRif").eq("Cliente", nome_cliente).execute()
        df_y = pd.DataFrame(res.data)
        if df_y.empty: return []
        return sorted(df_y["AnnoRif"].unique().tolist(), reverse=True)

    @st.cache_data(ttl=600)
    def get_cliente_detail_filtered(nome_cliente, anno):
        """Recupera i dettagli delle vendite per cliente e anno"""
        res = conn.table("fatturati").select("*").eq("Cliente", nome_cliente).eq("AnnoRif", anno).execute()
        return pd.DataFrame(res.data)

    # --- 3. INTERFACCIA FILTRI (SEARCHBOX) ---
    st.subheader("👥 Analisi Anagrafica e Performance")
    
    with st.container(border=True):
        c1, c2, c3 = st.columns([1, 2, 1])
        
        with c1:
            st.info(f"👤 **Agente:** {user_data.get('agente_nome', 'Mio Profilo')}")

        with c2:
            cliente_sel = st_searchbox(
                search_clienti,
                key="search_clienti_dashboard",
                placeholder="🔍 Scrivi il nome del cliente...",
                label="🏢 Cerca Cliente in Rubrica"
            )

        with c3:
            if cliente_sel:
                anni_disp = get_cliente_years(cliente_sel)
                if anni_disp:
                    anno_sel = st.selectbox("📅 Anno", anni_disp)
                else:
                    st.warning("Nessun acquisto trovato")
                    anno_sel = None
            else:
                st.selectbox("📅 Anno", ["-"], disabled=True)
                anno_sel = None

    # --- 4. LOGICA DI VISUALIZZAZIONE ---
    if not cliente_sel:
        st.info("💡 Utilizza la barra di ricerca sopra per selezionare un cliente dalla rubrica.")
        return

    if anno_sel:
        with st.spinner(f"Analisi dati per {cliente_sel}..."):
            df_cliente = get_cliente_detail_filtered(cliente_sel, anno_sel)
        
        if df_cliente.empty:
            st.warning(f"Nessun dettaglio vendite trovato per {anno_sel}.")
        else:
            # Pulizia dati
            df_cliente = df_cliente[~df_cliente["CodArt"].astype(str).str.upper().str.contains('RAEE', na=False)].copy()
            df_cliente["ImportoNettoRiga"] = pd.to_numeric(df_cliente["ImportoNettoRiga"], errors='coerce').fillna(0)
            
            # Gestione Famiglia (Marchio)
            if "Famiglia" in df_cliente.columns:
                df_cliente["Famiglia"] = df_cliente["Famiglia"].astype(str).str.upper().replace(["0", "NAN", ""], "NON SPECIFICATO")

            # --- 5. KPI & HEADER ---
            fatturato_totale = df_cliente["ImportoNettoRiga"].sum()
            
            st.markdown(f"""
                <div style="background-color: #f0f2f6; padding: 20px; border-radius: 10px; margin: 20px 0;">
                    <h2 style="margin:0; color: #1f77b4;">{cliente_sel}</h2>
                    <p style="margin:0; color: #555;">Dettaglio performance anno <b>{anno_sel}</b></p>
                </div>
            """, unsafe_allow_html=True)

            col1, col2 = st.columns(2)
            col1.metric("💰 Fatturato Totale", f"€ {fatturato_totale:,.2f}")
            col2.metric("📦 Righe Ordine", f"{len(df_cliente):,}")

            # --- 6. GRAFICI IN SEQUENZA VERTICALE ---
            
            # GRAFICO 1: DETTAGLIO MARCHI
            st.divider()
            st.subheader("🏆 Dettaglio Marchi")
            res_fam = df_cliente.groupby("Famiglia")["ImportoNettoRiga"].sum().reset_index().sort_values("ImportoNettoRiga", ascending=True)
            
            fig_fam = px.bar(
                res_fam, 
                x="ImportoNettoRiga", 
                y="Famiglia", 
                orientation='h', 
                text_auto='.2s', 
                color_discrete_sequence=['#ff7f0e'], 
                template="plotly_white"
            )
            fig_fam.update_layout(height=max(350, len(res_fam)*35), yaxis_title=None, xaxis_title="Fatturato (€)")
            st.plotly_chart(fig_fam, use_container_width=True)

            # GRAFICO 2: DETTAGLIO CATEGORIE
            st.divider()
            st.subheader("📦 Dettaglio Categorie")
            res_cat = df_cliente.groupby("Merceologica")["ImportoNettoRiga"].sum().reset_index().sort_values("ImportoNettoRiga", ascending=True)
            
            fig_cat = px.bar(
                res_cat, 
                x="ImportoNettoRiga", 
                y="Merceologica", 
                orientation='h', 
                text_auto='.2s', 
                color_discrete_sequence=['#1f77b4'], 
                template="plotly_white"
            )
            fig_cat.update_layout(height=max(350, len(res_cat)*35), yaxis_title=None, xaxis_title="Fatturato (€)")
            st.plotly_chart(fig_cat, use_container_width=True)

    # --- 7. DIARIO VISITE ---
    st.divider()
    st.subheader("📝 Diario Visite & Note")
    
    with st.container(border=True):
        st.write(f"Aggiungi un appunto per la visita a **{cliente_sel}**")
        d_col1, d_col2 = st.columns([1, 2])
        with d_col1:
            data_v = st.date_input("Data Visita", value=pd.Timestamp.now())
        
        nota_v = st.text_area("Note dell'incontro", placeholder="Descrivi l'esito della visita...")
        
        if st.button("Salva Nota", type="primary", use_container_width=True):
            if nota_v:
                st.success(f"Nota per {cliente_sel} salvata in locale (Simulazione)!")
            else:
                st.warning("Inserisci del testo prima di salvare.")

if __name__ == "__main__":
    show_clienti()