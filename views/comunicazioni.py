import streamlit as st
from datetime import datetime
from supabase import create_client


def get_supabase_client():
    url = st.secrets["connections"]["supabase"]["url"]
    key = st.secrets["connections"]["supabase"]["key"]
    return create_client(url, key)


supabase = get_supabase_client()

TIPO_AVVISO = "avviso"
TIPO_INVITO = "invito"
RISP_LETTO = "letto"
RISP_PRESENTE = "presente"
RISP_ASSENTE = "assente"

ARG_GENERALE = "GENERALE"
ARG_EVENTO = "EVENTO"
# Argomenti selezionabili: GENERALE, EVENTO e poi i marchi (stesso elenco dell'app mobile)
ARGOMENTI = [
    ARG_GENERALE, ARG_EVENTO, "MIELE", "BORA", "SIEMENS", "BOSCH", "LIEBHERR", "GROHE", "GESSI",
    "FOSTER", "BARAZZA", "ELICA", "PANDO", "TEMPTECH", "GALVAMET", "PROACQUA",
]
TUTTI_AGENTI = "TUTTI_AGENTI"


def _formatta_data(iso, con_ora=False):
    if not iso:
        return "-"
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone()
        return d.strftime("%d/%m/%Y %H:%M" if con_ora else "%d/%m/%Y")
    except Exception:
        return str(iso)[:10]


def _argomento_di(c):
    a = str(c.get("argomento") or "").strip()
    return a or ARG_GENERALE


def _carica():
    comunicazioni = (
        supabase.table("comunicazioni").select("*").order("created_at", desc=True).execute().data or []
    )
    risposte = (
        supabase.table("comunicazioni_risposte")
        .select("id_comunicazione, id_agente, risposta, created_at")
        .execute()
        .data
        or []
    )
    agenti = {}
    for a in supabase.table("agenti").select("id_agente, nome_agente").execute().data or []:
        agenti[str(a["id_agente"]).strip()] = str(a["nome_agente"]).upper()
    return comunicazioni, risposte, agenti


def _pubblica(titolo, testo, tipo, argomento, destinatario, data_evento, autore):
    supabase.table("comunicazioni").insert({
        "titolo": titolo.strip(),
        "testo": testo.strip(),
        "tipo": tipo,
        "argomento": argomento,
        "destinatario": None if destinatario == TUTTI_AGENTI else destinatario,
        "data_evento": data_evento.isoformat() if (tipo == TIPO_INVITO and data_evento) else None,
        "creato_da": autore,
    }).execute()


def _rispondi(id_comunicazione, id_agente, risposta):
    supabase.table("comunicazioni_risposte").upsert(
        {"id_comunicazione": id_comunicazione, "id_agente": id_agente, "risposta": risposta},
        on_conflict="id_comunicazione,id_agente",
    ).execute()


def _form_nuova(agenti, autore):
    with st.expander("✍️ Nuova comunicazione", expanded=False):
        with st.form("form_nuova_comunicazione", clear_on_submit=True):
            titolo = st.text_input("Titolo")
            c1, c2 = st.columns(2)
            destinatari = [TUTTI_AGENTI] + sorted(agenti.keys(), key=lambda k: agenti[k])
            destinatario = c1.selectbox(
                "Destinatario",
                destinatari,
                format_func=lambda k: "Tutti gli agenti" if k == TUTTI_AGENTI else agenti[k],
            )
            argomento = c2.selectbox("Argomento", ARGOMENTI)
            testo = st.text_area("Testo della comunicazione", height=140)
            c3, c4 = st.columns(2)
            tipo = c3.selectbox(
                "Tipo di risposta richiesta",
                [TIPO_AVVISO, TIPO_INVITO],
                format_func=lambda t: "Avviso — conferma di lettura" if t == TIPO_AVVISO else "Invito — presente / non presente",
            )
            data_evento = c4.date_input("Data dell'evento (solo per gli inviti, facoltativa)", value=None, format="DD/MM/YYYY")
            if st.form_submit_button("📢 PUBBLICA", type="primary", use_container_width=True):
                if not titolo.strip() or not testo.strip():
                    st.error("Inserisci titolo e testo della comunicazione")
                else:
                    try:
                        _pubblica(titolo, testo, tipo, argomento, destinatario, data_evento, autore)
                        st.success("✅ Comunicazione pubblicata")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Errore: {e}")


def _scheda(c, risposte, agenti, ruolo, agente_id):
    id_c = c["id"]
    is_invito = c.get("tipo") == TIPO_INVITO
    dest = str(c.get("destinatario") or "").strip()
    mie = {}
    per_comunicazione = [r for r in risposte if r["id_comunicazione"] == id_c]
    if ruolo == "agente":
        for r in per_comunicazione:
            if str(r["id_agente"]).strip() == agente_id:
                mie = r

    da_rispondere = ruolo == "agente" and not mie
    with st.container(border=True, key=f"scheda_com_{id_c}"):
        top = st.columns([0.9, 0.1])
        titolo = f"🔴 {c.get('titolo', '')}" if da_rispondere else c.get("titolo", "")
        top[0].markdown(f"#### {titolo}")
        if ruolo == "admin" and top[1].button("🗑️", key=f"del_{id_c}", help="Elimina la comunicazione"):
            st.session_state[f"conferma_del_{id_c}"] = True

        if ruolo == "admin" and st.session_state.get(f"conferma_del_{id_c}"):
            st.warning(f"\"{c.get('titolo')}\" e tutte le risposte degli agenti verranno eliminate.")
            b1, b2, _ = st.columns([1, 1, 4])
            if b1.button("Elimina", key=f"si_{id_c}", type="primary"):
                supabase.table("comunicazioni").delete().eq("id", id_c).execute()
                st.session_state.pop(f"conferma_del_{id_c}", None)
                st.rerun()
            if b2.button("Annulla", key=f"no_{id_c}"):
                st.session_state.pop(f"conferma_del_{id_c}", None)
                st.rerun()

        etichette = [f"`{_argomento_di(c)}`"]
        if ruolo == "admin" and dest:
            etichette.append(f"**Solo per: {agenti.get(dest, 'agente ' + dest)}**")
        st.caption(" · ".join(etichette) + f" · Inviata il {_formatta_data(c.get('created_at'), True)}")
        data_evento = str(c.get("data_evento") or "")
        if is_invito and data_evento:
            st.markdown(f"📅 **Evento: {_formatta_data(data_evento)}**")
        st.write(c.get("testo", ""))

        if ruolo == "agente":
            _risposte_agente(id_c, agente_id, is_invito, mie.get("risposta"))
        elif ruolo == "admin":
            _riepilogo_admin(id_c, is_invito, per_comunicazione, agenti, dest)


def _risposte_agente(id_c, agente_id, is_invito, mia):
    if not is_invito:
        if mia:
            st.success("✅ Hai confermato di aver letto")
        elif st.button("✔️ Ho letto", key=f"letto_{id_c}", type="primary", use_container_width=True):
            _rispondi(id_c, agente_id, RISP_LETTO)
            st.rerun()
        return
    b1, b2 = st.columns(2)
    for col, valore, etichetta in ((b1, RISP_PRESENTE, "✅ Sarò presente"), (b2, RISP_ASSENTE, "❌ Non presente")):
        selezionato = mia == valore
        if col.button(etichetta, key=f"{valore}_{id_c}", type="primary" if selezionato else "secondary", use_container_width=True):
            _rispondi(id_c, agente_id, valore)
            st.rerun()


def _riepilogo_admin(id_c, is_invito, risposte, agenti, destinatario):
    risposto = {str(r["id_agente"]).strip() for r in risposte}
    in_attesa = sorted(
        [a for a in agenti if (not destinatario or a == destinatario) and a not in risposto],
        key=lambda a: agenti[a],
    )

    def conta(v):
        return sum(1 for r in risposte if r["risposta"] == v)

    if is_invito:
        sintesi = f"✅ {conta(RISP_PRESENTE)} presenti   ❌ {conta(RISP_ASSENTE)} assenti   ⏳ {len(in_attesa)} in attesa"
    else:
        sintesi = f"✅ {conta(RISP_LETTO)} hanno letto   ⏳ {len(in_attesa)} in attesa"

    def etichetta(v):
        return {RISP_PRESENTE: "✅ Sarà presente", RISP_ASSENTE: "❌ Non sarà presente"}.get(v, "✅ Letto")

    with st.expander(sintesi):
        for r in risposte:
            nome = agenti.get(str(r["id_agente"]).strip(), f"Agente {r['id_agente']}")
            st.write(f"**{nome}** — {etichetta(r['risposta'])}")
        for a in in_attesa:
            st.write(f"{agenti[a]} — ⏳ In attesa")


def show_comunicazioni():
    st.subheader("📢 Comunicazioni")
    user_data = st.session_state.get("user_info", {})
    ruolo = str(user_data.get("ruolo", "")).lower().strip()
    agente_id = str(user_data.get("agente_corrispondente", "")).strip()
    autore = user_data.get("username", "")

    try:
        comunicazioni, risposte, agenti = _carica()
    except Exception as e:
        st.error(f"Errore nel caricamento: {e}")
        return

    # L'agente vede solo le comunicazioni per tutti o indirizzate a lui
    if ruolo == "agente":
        comunicazioni = [
            c for c in comunicazioni
            if not str(c.get("destinatario") or "").strip() or str(c.get("destinatario")).strip() == agente_id
        ]
        risposte = [r for r in risposte if str(r["id_agente"]).strip() == agente_id]

    if ruolo == "admin":
        _form_nuova(agenti, autore)

    if not comunicazioni:
        st.info("Nessuna comunicazione presente.")
        return

    presenti = {_argomento_di(c) for c in comunicazioni}
    voci = [a for a in ARGOMENTI if a in presenti] + sorted(a for a in presenti if a not in ARGOMENTI)
    scelta = st.selectbox("Filtra per argomento", ["Tutti gli argomenti"] + voci)
    visibili = comunicazioni if scelta == "Tutti gli argomenti" else [c for c in comunicazioni if _argomento_di(c) == scelta]

    if not visibili:
        st.info("Nessuna comunicazione per questo argomento.")
        return
    for c in visibili:
        _scheda(c, risposte, agenti, ruolo, agente_id)
