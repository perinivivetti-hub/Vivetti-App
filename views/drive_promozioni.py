import re
from datetime import datetime

import requests
import streamlit as st

# Marchi riconosciuti dal nome del file (stesso elenco dell'app mobile)
PAROLE_MARCHIO = {
    "MIELE": ["MIELE"],
    "BORA": ["BORA"],
    "SIEMENS": ["SIEMENS", "STUDIOLINE"],
    "BOSCH": ["BOSCH"],
    "LIEBHERR": ["LIEBHERR"],
    "GROHE": ["GROHE"],
    "GESSI": ["GESSI"],
    "FOSTER": ["FOSTER"],
    "BARAZZA": ["BARAZZA"],
    "ELICA": ["ELICA"],
    "PANDO": ["PANDO"],
    "TEMPTECH": ["TEMPTECH"],
    "GALVAMET": ["GALVAMET"],
    "PROACQUA": ["PROACQUA"],
    "GORENJE": ["GORENJE"],
    "SCHOCK": ["SCHOCK"],
    "ISE": ["ISE"],
    "MABE": ["MABE"],
    "SKS": ["SKS"],
}


def _funzione(azione, **extra):
    """Chiama la funzione Supabase `documenti-marchi`, che legge la cartella Drive."""
    cfg = st.secrets["connections"]["supabase"]
    url = f"{cfg['url'].rstrip('/')}/functions/v1/documenti-marchi"
    headers = {"apikey": cfg["key"], "Authorization": f"Bearer {cfg['key']}", "Content-Type": "application/json"}
    return requests.post(url, json={"azione": azione, **extra}, headers=headers, timeout=120)


@st.cache_data(ttl=300, show_spinner=False)
def _elenco(cartella):
    r = _funzione("elenco", **({"cartella": cartella} if cartella else {}))
    dati = r.json()
    if "voci" not in dati:
        raise RuntimeError(dati.get("errore", f"risposta non valida ({r.status_code})"))
    return dati["voci"]


@st.cache_data(ttl=1800, max_entries=4, show_spinner=False)
def _scarica(id_file, modificato):
    r = _funzione("scarica", id=id_file)
    if "application/json" in r.headers.get("content-type", ""):
        raise RuntimeError(r.json().get("errore", "file non valido"))
    return r.content


def _contiene(nome, parole):
    n = nome.upper()
    return any(re.search(rf"(^|[^A-Z0-9]){re.escape(p)}($|[^A-Z0-9])", n) for p in parole)


def _titolo(nome):
    return re.sub(r"\.pdf$", "", nome, flags=re.IGNORECASE)


def _dimensione(byte):
    if not byte:
        return ""
    return f"{byte / 1024 / 1024:.1f} MB" if byte >= 1024 * 1024 else f"{-(-byte // 1024)} KB"


def _data(iso):
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone().strftime("%d/%m/%Y")
    except Exception:
        return ""


def show_drive_promozioni():
    st.subheader("☁️ Drive Promozioni")

    percorso = st.session_state.setdefault("drive_percorso", [])  # elenco di (id, nome)
    cartella = percorso[-1][0] if percorso else None

    top = st.columns([1.3, 3, 1.7])
    if percorso and top[0].button("← Indietro"):
        percorso.pop()
        st.rerun()
    if top[2].button("🔄 Aggiorna"):
        _elenco.clear()
        st.rerun()
    if percorso:
        top[1].markdown("**" + " › ".join(["Promozioni"] + [n for _, n in percorso]) + "**")

    try:
        with st.spinner("Carico i documenti..."):
            voci = _elenco(cartella)
    except Exception as e:
        st.error(f"Impossibile caricare i documenti: {e}")
        return
    if not voci:
        st.info("Nessun documento in questa cartella.")
        return

    # --- filtri: ricerca e marchio ---
    marchi = [m for m, parole in PAROLE_MARCHIO.items()
              if any(not v["cartella"] and _contiene(v["nome"], parole) for v in voci)]
    c1, c2 = st.columns([2, 3])
    cerca = c1.text_input("Cerca un documento", placeholder="Scrivi per cercare...").strip().upper()
    marchio = c2.pills("Marchio", marchi, selection_mode="single") if marchi else None

    visibili = []
    for v in voci:
        if marchio and (v["cartella"] or not _contiene(v["nome"], PAROLE_MARCHIO[marchio])):
            continue
        if cerca and cerca not in v["nome"].upper():
            continue
        visibili.append(v)
    if not visibili:
        st.info("Nessun documento trovato.")
        return

    for v in visibili:
        with st.container(border=True, key=f"scheda_drv_{v['id']}"):
            col = st.columns([6, 2, 2])
            if v["cartella"]:
                col[0].markdown(f"📁 **{v['nome']}**")
                if col[2].button("Apri", key=f"cart_{v['id']}"):
                    percorso.append((v["id"], v["nome"]))
                    st.rerun()
                continue
            col[0].markdown(f"📄 **{_titolo(v['nome'])}**")
            col[1].caption(" · ".join(x for x in (_dimensione(v.get("dimensione")), _data(v.get("modificato"))) if x))
            if col[2].button("Scarica", key=f"sc_{v['id']}"):
                try:
                    with st.spinner("Scarico il file..."):
                        dati = _scarica(v["id"], v.get("modificato"))
                    st.session_state["drive_pronto"] = {"id": v["id"], "nome": _titolo(v["nome"]) + ".pdf", "dati": dati}
                except Exception as e:
                    st.error(f"Errore: {e}")
            pronto = st.session_state.get("drive_pronto")
            if pronto and pronto["id"] == v["id"]:
                st.download_button(
                    "💾 Salva il PDF",
                    data=pronto["dati"],
                    file_name=pronto["nome"],
                    mime="application/pdf",
                    key=f"dl_{v['id']}",
                    type="primary",
                )
