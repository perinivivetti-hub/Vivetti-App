import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from folium.plugins import MarkerCluster
from supabase import create_client

def show_mappa():
    st.subheader("🗺️ Mappa Clienti")

    # 1. Connessione a Supabase tramite secrets
    url = st.secrets["connections"]["supabase"]["url"]
    key = st.secrets["connections"]["supabase"]["key"]
    supabase = create_client(url, key)

    # 2. Recupero info agente loggato dalla session_state di app.py
    user_data = st.session_state.get('user_info')
    if not user_data:
        st.error("Errore: Utente non autenticato. Effettua il login.")
        return
        
    # Recuperiamo l'ID (es. 605456)
    id_agente_loggato = user_data['agente_corrispondente']

    # 3. Caricamento dati filtrati per ID_AGENTE
    with st.spinner("Accesso al database in corso..."):
        try:
            # Interroghiamo la tabella filtrando per l'ID numerico dell'agente
            # e prendendo solo i record che hanno le coordinate (non null)
            response = supabase.table("rubrica_clienti") \
                .select("ragione_sociale, indirizzo, citta, prov, lat, lon, email, id_agente") \
                .eq("id_agente", id_agente_loggato) \
                .not_.is_("lat", "null") \
                .execute()
            
            df = pd.DataFrame(response.data)
        except Exception as e:
            st.error(f"Errore durante la query al database: {e}")
            return

    # 4. Verifica se il DataFrame è vuoto
    if df.empty:
        st.warning(f"Nessun cliente trovato per l'ID Agente: {id_agente_loggato}")
        st.info("Verifica che i clienti abbiano le coordinate Lat/Lon popolate su Supabase.")
        return

    # 5. Opzione di ricerca testuale sopra la mappa
    search = st.text_input("🔍 Cerca un cliente per Ragione Sociale", placeholder="Inizia a scrivere...")
    if search:
        df = df[df['ragione_sociale'].str.contains(search, case=False)]

    # 6. Configurazione della Mappa Folium
    # Calcoliamo il centro basandoci sui clienti trovati
    centro_lat = df['lat'].astype(float).mean()
    centro_lon = df['lon'].astype(float).mean()
    
    m = folium.Map(location=[centro_lat, centro_lon], zoom_start=8, control_scale=True)
    
    # Aggiungiamo i Cluster (i pallini numerati che raggruppano i punti)
    marker_cluster = MarkerCluster().add_to(m)

    for _, row in df.iterrows():
        # Popup con stile e link al navigatore
        popup_html = f"""
            <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; font-size: 13px; width: 220px;">
                <h4 style="margin-bottom: 5px; color: #1d3557;">{row['ragione_sociale']}</h4>
                <p style="margin: 0; color: #457b9d;"><b>Indirizzo:</b> {row['indirizzo']}</p>
                <p style="margin: 0; color: #457b9d;"><b>Città:</b> {row['citta']} ({row['prov']})</p>
                <hr style="margin: 10px 0; border: 0; border-top: 1px solid #eee;">
                <div style="display: flex; flex-direction: column; gap: 8px;">
                    <a href="mailto:{row['email']}" style="text-decoration: none; color: #E63946;">📧 Invia Email</a>
                    <a href="https://www.google.com/maps/dir/?api=1&destination={row['lat']},{row['lon']}" 
                       target="_blank" 
                       style="background-color: #2a9d8f; color: white; padding: 8px; border-radius: 4px; text-decoration: none; text-align: center; font-weight: bold;">
                       🚗 Naviga al Cliente
                    </a>
                </div>
            </div>
        """
        
        folium.Marker(
            location=[float(row['lat']), float(row['lon'])],
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=row['ragione_sociale']
        ).add_to(marker_cluster)

    # 7. Rendering della mappa
    # returned_objects=[] evita ricariche inutili della pagina Streamlit
    st_folium(m, width="100%", height=600, returned_objects=[])
