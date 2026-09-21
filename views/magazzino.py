import streamlit as st
import pandas as pd
from supabase import create_client
import time

# --- CONNESSIONE ---
def get_supabase_client():
    url = st.secrets["connections"]["supabase"]["url"]
    key = st.secrets["connections"]["supabase"]["key"]
    return create_client(url, key)

supabase = get_supabase_client()

# --- FUNZIONI DATI & STORAGE ---
def get_prodotti_occasione():
    res = supabase.table("magazzino_occasioni").select("*").order("created_at", desc=True).execute()
    return res.data or []

def upload_foto_occasione(file):
    """Carica la foto del prodotto nello storage di Supabase e restituisce l'URL pubblico"""
    try:
        clean_name = file.name.replace(' ', '_').replace('(', '').replace(')', '')
        file_name = f"occasione_{int(time.time())}_{clean_name}"

        supabase.storage.from_("occasioni_foto").upload(
            path=file_name,
            file=file.getvalue(),
            file_options={"content-type": file.type}
        )

        url_data = supabase.storage.from_("occasioni_foto").get_public_url(file_name)

        if isinstance(url_data, str): return url_data
        if hasattr(url_data, "public_url"): return url_data.public_url
        if isinstance(url_data, dict) and "publicUrl" in url_data: return url_data["publicUrl"]
        return str(url_data)
    except Exception as e:
        st.error(f"❌ Errore durante l'upload della foto: {e}")
        return None

def inserisci_prodotto(record):
    try:
        res = supabase.table("magazzino_occasioni").insert(record).execute()
        return bool(res.data)
    except Exception as e:
        st.error(f"Errore durante l'inserimento: {e}")
        return False

def aggiorna_quantita(id_prodotto, nuova_quantita):
    try:
        supabase.table("magazzino_occasioni").update({"quantita": int(nuova_quantita)}).eq("id", id_prodotto).execute()
        return True
    except Exception as e:
        st.error(f"Errore aggiornamento quantità: {e}")
        return False

def elimina_prodotto(id_prodotto):
    try:
        supabase.table("magazzino_occasioni").delete().eq("id", id_prodotto).execute()
        return True
    except Exception as e:
        st.error(f"Errore durante l'eliminazione: {e}")
        return False

# --- INTERFACCIA PRINCIPALE ---
def show_magazzino():
    st.subheader("📦 Magazzino Occasioni")

    user_data = st.session_state.get('user_info', {})
    ruolo = str(user_data.get("ruolo", "")).lower().strip()
    puo_gestire = ruolo in ["amministrazione", "admin"]

    # --- SEZIONE SEDE: AGGIUNGI NUOVO PRODOTTO ---
    if puo_gestire:
        with st.expander("🛠️ Sede - Aggiungi Nuovo Prodotto in Occasione", expanded=False):
            with st.form("form_nuovo_occasione", clear_on_submit=True):
                descrizione = st.text_area("Descrizione Prodotto", placeholder="Es. Frigorifero Modello X, leggero difetto estetico...")
                foto_file = st.file_uploader("📸 Foto Prodotto", type=["jpg", "jpeg", "png"])

                c1, c2, c3 = st.columns(3)
                prezzo_listino = c1.number_input("Prezzo Listino (€)", min_value=0.0, value=0.0, format="%.2f")
                prezzo_netto = c2.number_input("Prezzo Netto (€)", min_value=0.0, value=0.0, format="%.2f")
                quantita = c3.number_input("Quantità Disponibile", min_value=0, value=1)

                submit_prodotto = st.form_submit_button("🚀 AGGIUNGI PRODOTTO", use_container_width=True)

                if submit_prodotto:
                    if not descrizione.strip():
                        st.error("La descrizione del prodotto è obbligatoria!")
                    else:
                        url_foto = None
                        upload_valido = True
                        if foto_file:
                            with st.spinner("Caricamento foto..."):
                                url_foto = upload_foto_occasione(foto_file)
                                if not url_foto: upload_valido = False

                        if upload_valido:
                            nuovo_prodotto = {
                                "descrizione": descrizione.strip(),
                                "foto_url": url_foto,
                                "prezzo_listino": float(prezzo_listino),
                                "prezzo_netto": float(prezzo_netto),
                                "quantita": int(quantita)
                            }
                            if inserisci_prodotto(nuovo_prodotto):
                                st.success("✅ Prodotto aggiunto al magazzino occasioni!")
                                time.sleep(1)
                                st.rerun()

    st.divider()

    # --- FILTRI DI VISUALIZZAZIONE (per tutti) ---
    col_search, col_toggle = st.columns([3, 1])
    with col_search:
        ricerca = st.text_input("🔍 Cerca per descrizione", placeholder="Digita per filtrare...")
    with col_toggle:
        nascondi_esauriti = st.checkbox("Nascondi esauriti", value=False)

    prodotti = get_prodotti_occasione()

    if ricerca:
        prodotti = [p for p in prodotti if ricerca.lower() in str(p.get('descrizione', '')).lower()]
    if nascondi_esauriti:
        prodotti = [p for p in prodotti if int(p.get('quantita', 0) or 0) > 0]

    if not prodotti:
        st.info("Nessun prodotto in occasione al momento.")
        return

    st.caption(f"Prodotti trovati: {len(prodotti)}")

    # --- ELENCO PRODOTTI (SCHEDE) ---
    for p in prodotti:
        with st.container(border=True):
            c_img, c_info = st.columns([1, 3])

            with c_img:
                if p.get('foto_url'):
                    st.image(p['foto_url'], use_container_width=True)
                else:
                    st.caption("📷 Nessuna foto")

            with c_info:
                st.markdown(f"#### {p['descrizione']}")
                c_p1, c_p2, c_p3 = st.columns(3)
                c_p1.metric("Prezzo Listino", f"€ {float(p.get('prezzo_listino') or 0):,.2f}")
                c_p2.metric("Prezzo Netto", f"€ {float(p.get('prezzo_netto') or 0):,.2f}")

                disponibili = int(p.get('quantita', 0) or 0)
                if disponibili <= 0:
                    c_p3.error("ESAURITO")
                else:
                    c_p3.metric("Disponibili", disponibili)

                if puo_gestire:
                    with st.expander("✏️ Gestisci (Sede)"):
                        nuova_qta = st.number_input(
                            "Aggiorna quantità disponibile",
                            min_value=0, value=disponibili, key=f"qta_{p['id']}"
                        )
                        cb1, cb2 = st.columns(2)
                        if cb1.button("💾 Salva Quantità", key=f"save_{p['id']}", use_container_width=True):
                            if aggiorna_quantita(p['id'], nuova_qta):
                                st.success("Quantità aggiornata!")
                                time.sleep(0.8)
                                st.rerun()
                        if cb2.button("🗑️ Elimina Prodotto", key=f"del_{p['id']}", use_container_width=True, type="secondary"):
                            if elimina_prodotto(p['id']):
                                st.rerun()

if __name__ == "__main__":
    show_magazzino()
