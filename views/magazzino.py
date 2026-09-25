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

TIPOLOGIE_PRODOTTO = ["Forno", "Piano Cottura", "Frigorifero", "Cantina Vino", "Lavastoviglie", "Lavatrice", "Altro"]

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

def get_mappa_agenti():
    """Recupera la corrispondenza ID -> Nome dalla tabella 'agenti'"""
    try:
        res = supabase.table("agenti").select("id_agente, nome_agente").execute()
        if res.data:
            return {str(row['id_agente']).strip(): str(row['nome_agente']).upper() for row in res.data}
    except Exception as e:
        st.error(f"Errore caricamento mappa agenti: {e}")
    return {}

def get_proposte(ids_prodotti):
    """Recupera, per i prodotti indicati, gli id_agente che li stanno proponendo a un cliente"""
    if not ids_prodotti:
        return {}
    try:
        res = supabase.table("magazzino_occasioni_proposte").select("id_prodotto, id_agente").in_("id_prodotto", ids_prodotti).execute()
    except Exception as e:
        st.error(f"Errore caricamento proposte: {e}")
        return {}
    mappa = {}
    for row in (res.data or []):
        mappa.setdefault(row['id_prodotto'], []).append(str(row['id_agente']).strip())
    return mappa

def proponi_prodotto(id_prodotto, id_agente):
    try:
        supabase.table("magazzino_occasioni_proposte").insert({
            "id_prodotto": id_prodotto, "id_agente": str(id_agente).strip()
        }).execute()
        return True
    except Exception as e:
        st.error(f"Errore durante la proposta: {e}")
        return False

def ritira_proposta(id_prodotto, id_agente):
    try:
        supabase.table("magazzino_occasioni_proposte").delete()\
            .eq("id_prodotto", id_prodotto).eq("id_agente", str(id_agente).strip()).execute()
        return True
    except Exception as e:
        st.error(f"Errore durante il ritiro della proposta: {e}")
        return False

# --- INTERFACCIA PRINCIPALE ---
def show_magazzino():
    st.subheader("📦 Magazzino Occasioni")

    user_data = st.session_state.get('user_info', {})
    ruolo = str(user_data.get("ruolo", "")).lower().strip()
    agente_id_corrente = str(user_data.get("agente_corrispondente", "")).strip()
    puo_gestire = ruolo in ["admin", "magazzino"]
    puo_proporre = ruolo in ["agente", "admin"]

    st.markdown("""
        <style>
        @keyframes blink-warning { 50% { opacity: 0.25; } }
        .blink-warning {
            color: #d90429; font-weight: bold; text-align: center;
            padding: 8px 12px; border: 2px solid #d90429; border-radius: 8px;
            margin: 8px 0; animation: blink-warning 1s linear infinite;
        }
        .occ-card-title { font-size: 0.95rem; font-weight: 700; margin-bottom: 2px; line-height: 1.3; }
        .occ-card-tag { font-size: 0.72rem; color: #888; margin-bottom: 6px; }
        .occ-price-row { display: flex; gap: 18px; flex-wrap: wrap; margin: 4px 0 8px 0; }
        .occ-price-item { display: flex; flex-direction: column; }
        .occ-price-label { font-size: 0.68rem; color: #888; }
        .occ-price-value { font-size: 0.9rem; font-weight: 700; }
        .occ-esaurito { color: #d90429; font-weight: 700; font-size: 0.85rem; }
        </style>
        """, unsafe_allow_html=True)

    # --- SEZIONE SEDE: AGGIUNGI NUOVO PRODOTTO ---
    if puo_gestire:
        with st.expander("🛠️ Sede - Aggiungi Nuovo Prodotto in Occasione", expanded=False):
            with st.form("form_nuovo_occasione", clear_on_submit=True):
                codice_prodotto = st.text_input("Codice Prodotto", placeholder="Es. RF-2024-001")
                descrizione = st.text_area("Descrizione Prodotto", placeholder="Es. Frigorifero Modello X, leggero difetto estetico...")
                tipologia = st.selectbox("Tipologia Prodotto", options=TIPOLOGIE_PRODOTTO)
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
                                "codice_prodotto": codice_prodotto.strip() if codice_prodotto else None,
                                "descrizione": descrizione.strip(),
                                "tipologia_prodotto": tipologia,
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
    col_search, col_tipo, col_toggle = st.columns([2, 1.5, 1])
    with col_search:
        ricerca = st.text_input("🔍 Cerca per codice o descrizione", placeholder="Digita per filtrare...")
    with col_tipo:
        tipo_sel = st.selectbox("Tipologia", options=["Tutte"] + TIPOLOGIE_PRODOTTO)
    with col_toggle:
        nascondi_esauriti = st.checkbox("Nascondi esauriti", value=False)

    prodotti = get_prodotti_occasione()

    if ricerca:
        r = ricerca.lower()
        prodotti = [p for p in prodotti if r in str(p.get('descrizione', '')).lower() or r in str(p.get('codice_prodotto', '')).lower()]
    if tipo_sel != "Tutte":
        prodotti = [p for p in prodotti if p.get('tipologia_prodotto') == tipo_sel]
    if nascondi_esauriti:
        prodotti = [p for p in prodotti if int(p.get('quantita', 0) or 0) > 0]

    if not prodotti:
        st.info("Nessun prodotto in occasione al momento.")
        return

    st.caption(f"Prodotti trovati: {len(prodotti)}")

    mappa_agenti = get_mappa_agenti()
    mappa_proposte = get_proposte([p['id'] for p in prodotti])

    # --- ELENCO PRODOTTI (SCHEDE) ---
    for p in prodotti:
        with st.container(border=True):
            c_img, c_info = st.columns([1, 3])

            with c_img:
                if p.get('foto_url'):
                    st.image(p['foto_url'], width=110)
                else:
                    st.caption("📷 Nessuna foto")

            with c_info:
                titolo = f"<code>{p['codice_prodotto']}</code> — {p['descrizione']}" if p.get('codice_prodotto') else p['descrizione']
                tag_html = f'<div class="occ-card-tag">🏷️ {p["tipologia_prodotto"]}</div>' if p.get('tipologia_prodotto') else ""

                disponibili = int(p.get('quantita', 0) or 0)
                if disponibili <= 0:
                    disp_html = '<div class="occ-price-item"><div class="occ-price-label">Disponibili</div><div class="occ-esaurito">ESAURITO</div></div>'
                else:
                    disp_html = f'<div class="occ-price-item"><div class="occ-price-label">Disponibili</div><div class="occ-price-value">{disponibili}</div></div>'

                st.markdown(f"""
                    <div class="occ-card-title">{titolo}</div>
                    {tag_html}
                    <div class="occ-price-row">
                        <div class="occ-price-item"><div class="occ-price-label">Prezzo Listino</div><div class="occ-price-value">€ {float(p.get('prezzo_listino') or 0):,.2f}</div></div>
                        <div class="occ-price-item"><div class="occ-price-label">Prezzo Netto</div><div class="occ-price-value">€ {float(p.get('prezzo_netto') or 0):,.2f}</div></div>
                        {disp_html}
                    </div>
                    """, unsafe_allow_html=True)

                proposte_prodotto = mappa_proposte.get(p['id'], [])
                if proposte_prodotto:
                    nomi_proponenti = [mappa_agenti.get(a, f"Agente ({a})") for a in proposte_prodotto]
                    st.caption("🤝 Proposto a un cliente da: " + ", ".join(nomi_proponenti))

                if disponibili == 1 and proposte_prodotto:
                    st.markdown(
                        '<div class="blink-warning">⚠️ ATTENZIONE: unico pezzo disponibile, già proposto a un cliente!</div>',
                        unsafe_allow_html=True
                    )

                if puo_proporre:
                    gia_proposto_da_me = agente_id_corrente in proposte_prodotto
                    if gia_proposto_da_me:
                        if st.button("🔴 Ritira la tua proposta", key=f"ritira_{p['id']}", use_container_width=True):
                            if ritira_proposta(p['id'], agente_id_corrente):
                                st.rerun()
                    else:
                        if st.button("🤝 Sto proponendo questo prodotto a un cliente", key=f"proponi_{p['id']}", use_container_width=True):
                            if proponi_prodotto(p['id'], agente_id_corrente):
                                st.rerun()

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
