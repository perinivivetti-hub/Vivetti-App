import streamlit as st
from datetime import datetime, timezone
from streamlit_searchbox import st_searchbox
from supabase import create_client


def get_supabase_client():
    url = st.secrets["connections"]["supabase"]["url"]
    key = st.secrets["connections"]["supabase"]["key"]
    return create_client(url, key)


supabase = get_supabase_client()

STATI = ["Aperta", "In lavorazione", "Chiusa"]
ICONE_STATO = {"Aperta": "🟠", "In lavorazione": "🔵", "Chiusa": "🟢"}


def _adesso():
    return datetime.now(timezone.utc).isoformat()


def _formatta(iso):
    if not iso:
        return "-"
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone().strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(iso)[:16]


def _cerca_clienti(term: str):
    if not term or len(term.strip()) < 2:
        return []
    user_data = st.session_state.get("user_info", {})
    query = supabase.table("rubrica_clienti").select("id, ragione_sociale, citta")
    if str(user_data.get("ruolo", "")).lower() == "agente":
        query = query.eq("id_agente", str(user_data.get("agente_corrispondente", "")).strip())
    res = query.ilike("ragione_sociale", f"%{term.strip()}%").limit(15).execute()
    return [(f"{r['ragione_sociale']} ({r.get('citta') or ''})", r) for r in (res.data or [])]


def _form_nuova(username, agente_id):
    if "rich_reset" not in st.session_state:
        st.session_state.rich_reset = 0
    k = st.session_state.rich_reset

    with st.expander("📝 Nuova richiesta", expanded=False):
        manuale = st.checkbox("Nuovo cliente (non in rubrica)", key=f"rich_man_{k}")
        cliente = None
        if manuale:
            nome = st.text_input("Ragione sociale", key=f"rich_nome_{k}").strip()
            if nome:
                cliente = {"id": None, "ragione_sociale": nome.upper()}
        else:
            sel = st_searchbox(_cerca_clienti, placeholder="🔍 Cerca cliente in rubrica...", key=f"rich_cli_{k}")
            if sel:
                cliente = {"id": sel["id"], "ragione_sociale": sel["ragione_sociale"]}
            if cliente:
                st.caption(f"Cliente selezionato: **{cliente['ragione_sociale']}**")

        oggetto = st.text_input("Oggetto della richiesta", key=f"rich_ogg_{k}")
        descrizione = st.text_area("Descrizione della richiesta", height=160, key=f"rich_desc_{k}")

        if st.button("📨 INVIA", type="primary", key=f"rich_invia_{k}", use_container_width=True):
            if not cliente:
                st.error("Seleziona o inserisci il cliente")
            elif not oggetto.strip():
                st.error("Inserisci l'oggetto della richiesta")
            elif not descrizione.strip():
                st.error("Inserisci la descrizione della richiesta")
            elif not agente_id:
                st.error("Utente non collegato a un agente")
            else:
                try:
                    supabase.table("richieste_commerciali").insert({
                        "id_agente": agente_id,
                        "nome_agente": username,
                        "id_cliente": str(cliente["id"]) if cliente["id"] is not None else None,
                        "cliente": cliente["ragione_sociale"],
                        "oggetto": oggetto.strip(),
                        "descrizione": descrizione.strip(),
                    }).execute()
                    st.session_state.rich_reset += 1
                    st.session_state.rich_ok = "✅ Richiesta inviata"
                    st.rerun()
                except Exception as e:
                    st.error(f"Errore: {e}")


def _carica(ruolo, agente_id):
    query = supabase.table("richieste_commerciali").select("*")
    if ruolo != "admin":
        query = query.eq("id_agente", agente_id)
    richieste = query.order("aggiornata_il", desc=True).limit(300).execute().data or []
    risposte = {}
    if richieste:
        ids = [r["id"] for r in richieste]
        rr = (
            supabase.table("richieste_risposte").select("*").in_("id_richiesta", ids).order("created_at").execute().data
            or []
        )
        for r in rr:
            risposte.setdefault(r["id_richiesta"], []).append(r)
    agenti = {}
    if ruolo == "admin":
        for a in supabase.table("agenti").select("id_agente, nome_agente").execute().data or []:
            agenti[str(a["id_agente"]).strip()] = str(a["nome_agente"]).upper()
    return richieste, risposte, agenti


def _scheda(r, risposte, agenti, ruolo, username):
    id_r = r["id"]
    stato = r.get("stato") or "Aperta"
    nome_agente = r.get("nome_agente") or agenti.get(str(r.get("id_agente", "")).strip(), "")
    titolo = f"{ICONE_STATO.get(stato, '🟠')} {r.get('oggetto', '')} — {r.get('cliente', '')}"

    with st.expander(titolo):
        riga = f"**{stato}** · {_formatta(r.get('created_at'))}"
        if ruolo == "admin" and nome_agente:
            riga += f" · Agente: **{nome_agente}**"
        st.caption(riga)
        st.write(r.get("descrizione", ""))

        for m in risposte.get(id_r, []):
            da_admin = m.get("ruolo") == "admin"
            chi = "Amministrazione" if da_admin else (m.get("autore") or "Agente")
            with st.chat_message("assistant" if da_admin else "user"):
                st.caption(f"{chi} · {_formatta(m.get('created_at'))}")
                st.write(m.get("testo", ""))

        if ruolo == "admin":
            nuovo = st.selectbox("Stato della richiesta", STATI, index=STATI.index(stato) if stato in STATI else 0, key=f"st_{id_r}")
            if nuovo != stato:
                supabase.table("richieste_commerciali").update(
                    {"stato": nuovo, "aggiornata_il": _adesso()}
                ).eq("id", id_r).execute()
                st.rerun()

        testo = st.text_area(
            "Rispondi" if ruolo == "admin" else "Aggiungi un messaggio",
            key=f"txt_{id_r}",
            height=100,
        )
        if st.button("Invia", key=f"inv_{id_r}", type="primary"):
            if testo.strip():
                try:
                    supabase.table("richieste_risposte").insert({
                        "id_richiesta": id_r,
                        "autore": username,
                        "ruolo": "admin" if ruolo == "admin" else "agente",
                        "testo": testo.strip(),
                    }).execute()
                    supabase.table("richieste_commerciali").update({"aggiornata_il": _adesso()}).eq("id", id_r).execute()
                    st.session_state.pop(f"txt_{id_r}", None)
                    st.rerun()
                except Exception as e:
                    st.error(f"Errore: {e}")


def show_richieste():
    st.subheader("📋 Richieste Commerciali")
    user_data = st.session_state.get("user_info", {})
    ruolo = str(user_data.get("ruolo", "")).lower().strip()
    agente_id = str(user_data.get("agente_corrispondente", "")).strip()
    username = user_data.get("username", "")

    if ruolo not in ("agente", "admin"):
        st.info("Questa pagina è riservata agli agenti e agli amministratori.")
        return

    if st.session_state.get("rich_ok"):
        st.success(st.session_state.pop("rich_ok"))

    if ruolo == "agente":
        _form_nuova(username, agente_id)

    try:
        richieste, risposte, agenti = _carica(ruolo, agente_id)
    except Exception as e:
        st.error(f"Errore nel caricamento: {e}")
        return

    # --- filtri ---
    cols = st.columns([2, 1, 1] if ruolo == "admin" else [2, 1])
    cerca = cols[0].text_input("Cerca per cliente o oggetto", placeholder="Scrivi per filtrare...").strip().upper()
    filtro_stato = cols[1].selectbox("Stato", ["Tutti"] + STATI)
    filtro_agente = "Tutti"
    if ruolo == "admin":
        voci = ["Tutti"] + sorted(agenti.keys(), key=lambda k: agenti[k])
        filtro_agente = cols[2].selectbox("Agente", voci, format_func=lambda k: "Tutti" if k == "Tutti" else agenti[k])

    visibili = []
    for r in richieste:
        if filtro_stato != "Tutti" and (r.get("stato") or "Aperta") != filtro_stato:
            continue
        if filtro_agente != "Tutti" and str(r.get("id_agente", "")).strip() != filtro_agente:
            continue
        if cerca and cerca not in f"{r.get('cliente', '')} {r.get('oggetto', '')}".upper():
            continue
        visibili.append(r)

    if not richieste:
        st.info("Nessuna richiesta presente.")
        return
    if not visibili:
        st.info("Nessuna richiesta con questi filtri.")
        return

    st.caption(f"{len(visibili)} richieste")
    for r in visibili:
        _scheda(r, risposte, agenti, ruolo, username)
