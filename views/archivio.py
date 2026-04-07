import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime
from fpdf import FPDF
from streamlit_searchbox import st_searchbox
import io
import os
import time
import base64

# --- CONFIGURAZIONE PAGINA ---
st.markdown("""
    <style>
    .main h1 { font-size: 1.8rem !important; margin-bottom: 0.5rem !important; }
    .stMetric { background-color: #f8f9fa; padding: 10px; border-radius: 10px; border: 1px solid #ddd; }
    .config-card { background-color: #f1f3f6; padding: 20px; border-radius: 12px; border-left: 6px solid #ff4b4b; margin: 15px 0; }
    .stButton button { border-radius: 8px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 1. CONNESSIONE ---
def get_supabase_client():
    url = st.secrets["connections"]["supabase"]["url"]
    key = st.secrets["connections"]["supabase"]["key"]
    return create_client(url, key)

supabase = get_supabase_client()

# --- 2. FUNZIONI DI RICERCA SERVER-SIDE ---
def search_clients_arc(search_term: str):
    if not search_term or len(search_term) < 2:
        return []
    user_data = st.session_state.get('user_info', {})
    query = supabase.table("rubrica_clienti").select("id, ragione_sociale, citta")
    if user_data.get("ruolo") == "agente":
        ag_id = str(user_data.get("agente_corrispondente", "")).strip()
        query = query.eq("id_agente", ag_id)
    res = query.ilike("ragione_sociale", f"%{search_term}%").limit(15).execute()
    if not res.data: return []
    return [(f"{row['ragione_sociale']} ({row.get('citta', '')})", row['id']) for row in res.data]

def search_articles_arc(search_term: str):
    if not search_term or len(search_term) < 3:
        return []
    res = supabase.table("listino_import")\
        .select("CODICE, DESCRIZIONE, PREZZO, SCONTO1, SCONTO2, SCONTO3")\
        .or_(f"CODICE.ilike.%{search_term}%,DESCRIZIONE.ilike.%{search_term}%")\
        .limit(20).execute()
    if not res.data: return []
    return [(f"{row['CODICE']} | {row['DESCRIZIONE'][:70]}...", row) for row in res.data]

# --- 3. GESTIONE DATI ---
def carica_preventivo(id_preventivo):
    testata = supabase.table("preventivi_testata").select("*").eq("id", id_preventivo).single().execute()
    righe = supabase.table("preventivi_righe").select("*").eq("id_preventivo", id_preventivo).order("id").execute()
    session_righe = []
    for r in righe.data:
        if r['nota_riga'] == 'NOTA_TESTO':
            session_righe.append({"tipo": "NOTA_TESTO", "DESCRIZIONE": r['descrizione']})
        else:
            session_righe.append({
                "CODICE": r['codice_articolo'], "DESCRIZIONE": r['descrizione'],
                "PREZZO_LORDO": float(r['prezzo_lordo_unitario'] or 0), 
                "PREZZO_NETTO": float(r['prezzo_netto_unitario'] or 0),
                "QTA": int(r['quantita'] or 1), "SCONTO_MERCE": bool(r['is_sconto_merce']),
                "S1": float(r['sconto_1'] or 0), "S2": float(r['sconto_2'] or 0), "S3": float(r['sconto_3'] or 0),
                "NOTA": r['nota_riga'] if r['nota_riga'] != 'NOTA_TESTO' else ""
            })
    return testata.data, session_righe

def trasforma_in_ordine(id_preventivo):
    """
    Trasforma il preventivo in ordine e aggiorna la data created_at
    al momento esatto della conversione.
    """
    try:
        ora_attuale = datetime.now().isoformat()
        supabase.table("preventivi_testata").update({
            "stato": "Ordine",
            "created_at": ora_attuale  # Aggiornamento timestamp
        }).eq("id", id_preventivo).execute()
        return True
    except Exception as e: 
        return str(e)

def aggiorna_preventivo_db(id_preventivo, info_testata, righe):
    try:
        supabase.table("preventivi_testata").update(info_testata).eq("id", id_preventivo).execute()
        supabase.table("preventivi_righe").delete().eq("id_preventivo", id_preventivo).execute()
        righe_db = [{
            "id_preventivo": id_preventivo, "codice_articolo": r.get('CODICE', 'NOTA'), 
            "descrizione": r['DESCRIZIONE'], "quantita": r.get('QTA', 0), 
            "prezzo_lordo_unitario": r.get('PREZZO_LORDO', 0),
            "sconto_1": r.get('S1', 0), "sconto_2": r.get('S2', 0), "sconto_3": r.get('S3', 0),
            "is_sconto_merce": r.get('SCONTO_MERCE', False), "prezzo_netto_unitario": r.get('PREZZO_NETTO', 0), 
            "nota_riga": r.get('tipo', r.get('NOTA', ''))
        } for r in righe]
        supabase.table("preventivi_righe").insert(righe_db).execute()
        return True
    except Exception as e: return str(e)

# --- 4. UTILITY PDF E CALCOLI ---
def format_sconti_string(s1, s2, s3):
    parts = []
    for s in [s1, s2, s3]:
        try:
            val = float(s)
            if val > 0: parts.append(f"{val:g}")
        except: continue
    return "+".join(parts) if parts else "-"

def calcola_netto(listino, s1, s2, s3):
    return float(listino) * (1 - float(s1 or 0)/100) * (1 - float(s2 or 0)/100) * (1 - float(s3 or 0)/100)

def genera_pdf_ordine(cliente_ragione_sociale, testata, righe):
    # Funzione interna per sostituire i caratteri speciali con uno spazio
    def pulisci_testo(testo):
        if not testo:
            return ""
        # Encode in latin-1 con 'replace' mette un '?' sui caratteri non supportati
        # Poi decodifichiamo e sostituiamo il '?' con uno spazio
        temp = str(testo).encode('latin-1', 'replace').decode('latin-1')
        return temp.replace('?', ' ')

    pdf = FPDF(orientation='P', unit='mm', format='A4')
    pdf.add_page()
    logo_path = 'LogoVivetti.png'
    if os.path.exists(logo_path): pdf.image(logo_path, x=10, y=8, w=45) 
    
    pdf.set_font("Arial", 'B', 15); pdf.set_y(12)
    pdf.cell(0, 10, pulisci_testo(f"OFFERTA: {testata['numero_preventivo']}"), ln=True, align='R')
    
    pdf.ln(18)
    # --- GRASSETTO: Cliente ---
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 6, pulisci_testo(f"SPETT.LE CLIENTE: {cliente_ragione_sociale}"), ln=True)
    
    # --- GRASSETTO: Riferimento ---
    pdf.set_font("Arial", 'B', 10)
    rif_val = testata['riferimento'] if testata['riferimento'] else '-'
    pdf.cell(100, 6, pulisci_testo(f"RIFERIMENTO: {rif_val}"), ln=False)
    
    # Data Emissione (normale)
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 6, f"DATA EMISSIONE: {datetime.now().strftime('%d/%m/%Y')}", ln=True, align='R')
    
    consegna_str = "-"
    if testata.get('data_consegna'):
        try: consegna_str = datetime.strptime(str(testata['data_consegna']), '%Y-%m-%d').strftime('%d/%m/%Y')
        except: consegna_str = str(testata['data_consegna'])
            
    # --- GRASSETTO: Consegna ---
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(100, 6, pulisci_testo(f"CONSEGNA PREVISTA: {consegna_str}"), ln=True)
    
    pdf.ln(8); pdf.set_font("Arial", 'B', 8); pdf.set_fill_color(230, 230, 230)
    cols = [("CODICE", 35), ("DESCRIZIONE", 55), ("Q.TA", 10), ("PREZZO U.", 20), ("SCONTI", 20), ("NETTO U.", 20), ("TOTALE", 20)]
    for txt, w in cols: pdf.cell(w, 8, txt, 1, 0, 'C', True)
    pdf.ln(); pdf.set_font("Arial", '', 8)

    for r in righe:
        if pdf.get_y() > 250:
            pdf.add_page()
            pdf.set_font("Arial", 'B', 8); pdf.set_fill_color(230, 230, 230)
            for txt, w in cols: pdf.cell(w, 8, txt, 1, 0, 'C', True)
            pdf.ln(); pdf.set_font("Arial", '', 8)

        if r.get('tipo') == 'NOTA_TESTO':
            pdf.set_font("Arial", 'B', 9); pdf.set_fill_color(245, 245, 245)
            testo_nota = pulisci_testo(r['DESCRIZIONE']).upper()
            pdf.multi_cell(180, 8, testo_nota, border=1, align='L', fill=True)
            pdf.set_font("Arial", '', 8)
        else:
            p_l, p_u = float(r['PREZZO_LORDO']), (0.0 if r['SCONTO_MERCE'] else float(r['PREZZO_NETTO']))
            s_str = "OMAGGIO" if r['SCONTO_MERCE'] else format_sconti_string(r['S1'], r['S2'], r['S3'])
            
            # --- PULIZIA: Descrizione e Note ---
            desc_testo = pulisci_testo(r['DESCRIZIONE'])
            if len(desc_testo) > 250: desc_testo = desc_testo[:247] + "..."
            if r.get('NOTA'): desc_testo += pulisci_testo(f"\nNote: {r['NOTA']}")
            
            y_before = pdf.get_y()
            pdf.set_xy(45, y_before)
            pdf.multi_cell(55, 5, desc_testo, border=0, align='L')
            h = max(pdf.get_y() - y_before, 8)
            
            pdf.set_xy(10, y_before)
            pdf.cell(35, h, pulisci_testo(r['CODICE']), border=1, align='C')
            pdf.set_xy(45, y_before)
            pdf.multi_cell(55, 5, desc_testo, border=1, align='L')
            pdf.set_xy(100, y_before)
            pdf.cell(10, h, str(r['QTA']), border=1, align='C')
            pdf.cell(20, h, f"{p_l:,.2f}", border=1, align='R')
            pdf.cell(20, h, pulisci_testo(s_str), border=1, align='C')
            pdf.cell(20, h, f"{p_u:,.2f}", border=1, align='R')
            pdf.cell(20, h, f"{(p_u * r['QTA']):,.2f}", border=1, ln=1, align='R')
            
    # --- GRASSETTO E DICITURA: Totale ---
    pdf.ln(5); pdf.set_font("Arial", 'B', 12)
    pdf.cell(160, 10, "TOTALE NETTO (IVA ESCLUSA)", 0, 0, 'R')
    pdf.cell(30, 10, f"EUR {testata['totale_netto']:,.2f}", 0, 1, 'R')
    
    return pdf.output(dest='S').encode('latin-1', errors='replace')

# --- 5. INTERFACCIA PRINCIPALE ---
def show_archivio():
    st.subheader("📁 Archivio Preventivi")
    
    if 'edit_id' not in st.session_state: st.session_state.edit_id = None
    if 'righe_archivio' not in st.session_state: st.session_state.righe_archivio = []
    if 'temp_item_arc' not in st.session_state: st.session_state.temp_item_arc = None
    if 'search_key_arc' not in st.session_state: st.session_state.search_key_arc = 500
    if 'opened_expander_id' not in st.session_state: st.session_state.opened_expander_id = None

    user_data = st.session_state.get('user_info', {})

    if st.session_state.edit_id is None:
        col_f1, col_f2 = st.columns([2, 1])
        with col_f1:
            filtro_cliente_id = st_searchbox(search_clients_arc, key="filtro_cliente_archivio", placeholder="🔍 Filtra per cliente...")
        
        # Carichiamo solo i documenti che NON sono ordini
        query = supabase.table("preventivi_testata").select("*").neq("stato", "Ordine")
        if user_data.get("ruolo") == "agente":
            query = query.eq("id_agente", str(user_data.get("agente_corrispondente")))
        if filtro_cliente_id:
            query = query.eq("id_cliente", filtro_cliente_id)
        
        prev_data = query.order("created_at", desc=True).limit(50).execute()
        
        if not prev_data.data:
            st.info("Nessun preventivo in bozza trovato.")
        else:
            for row in prev_data.data:
                data_f = datetime.fromisoformat(row['created_at'].replace('Z', '+00:00')).strftime('%d/%m/%Y')
                label = f"📄 {row['numero_preventivo']} | {row['ragione_sociale_cliente']} | € {row['totale_netto']:,.2f} | {data_f}"
                
                is_open = st.session_state.opened_expander_id == row['id']
                
                with st.expander(label, expanded=is_open):
                    c1, c_edit, c_pdf, c_ord, c_del = st.columns([1.6, 0.7, 0.7, 0.8, 0.7])
                    c1.markdown(f"**Riferimento:** {row['riferimento'] or '-'}")
                    
                    if c_edit.button("✏️ EDIT", key=f"ed_{row['id']}", use_container_width=True):
                        testata, righe = carica_preventivo(row['id'])
                        st.session_state.edit_id = row['id']
                        st.session_state.edit_testata = testata
                        st.session_state.righe_archivio = righe
                        st.rerun()
                    
                    pdf_key = f"pdf_ready_{row['id']}"
                    if pdf_key not in st.session_state: st.session_state[pdf_key] = None

                    if c_pdf.button("📄 PDF", key=f"btn_gen_{row['id']}", use_container_width=True):
                        with st.spinner("..."):
                            st.session_state.opened_expander_id = row['id'] 
                            _, r_pdf = carica_preventivo(row['id'])
                            pdf_bytes = genera_pdf_ordine(row['ragione_sociale_cliente'], row, r_pdf)
                            st.session_state[pdf_key] = base64.b64encode(pdf_bytes).decode()
                            st.rerun()
                    
                    if st.session_state[pdf_key]:
                        b64_data = st.session_state[pdf_key]
                        file_n = f"{row['numero_preventivo']}.pdf"
                        pdf_link_html = f"""
                            <div style="text-align: center; margin-top: 5px;">
                                <a href="data:application/pdf;base64,{b64_data}" 
                                   target="_blank" 
                                   download="{file_n}" 
                                   style="color: #ff4b4b; text-decoration: none; font-weight: bold; font-size: 14px;">
                                   ⬇️ SCARICA
                                </a>
                            </div>
                        """
                        c_pdf.markdown(pdf_link_html, unsafe_allow_html=True)

                    if c_ord.button("🛒 ORDINE", key=f"ord_{row['id']}", use_container_width=True):
                        st.session_state.opened_expander_id = None
                        risultato = trasforma_in_ordine(row['id'])
                        if risultato is True:
                            st.success("✅ Convertito in ordine e data aggiornata!")
                            time.sleep(1); st.rerun()
                        else:
                            st.error(f"Errore: {risultato}")

                    if c_del.button("🗑️ DEL", key=f"del_{row['id']}", use_container_width=True, type="secondary"):
                        supabase.table("preventivi_testata").delete().eq("id", row['id']).execute()
                        st.rerun()

    else:
        # --- SEZIONE EDIT (Invariata ma inclusa per completezza) ---
        st.info(f"Modifica Documento: **{st.session_state.edit_testata['numero_preventivo']}**")
        if st.button("⬅️ ANNULLA E TORNA INDIETRO"):
            st.session_state.edit_id = None; st.rerun()
        
        st.divider()
        with st.expander("👤 Dati Testata", expanded=False):
            st.write(f"Cliente: **{st.session_state.edit_testata['ragione_sociale_cliente']}**")
            c_test1, c_test2 = st.columns(2)
            try: d_init = datetime.strptime(st.session_state.edit_testata['data_consegna'], '%Y-%m-%d').date() if st.session_state.edit_testata['data_consegna'] else None
            except: d_init = None
            data_cons = c_test1.date_input("Consegna", value=d_init)
            rif_ordine = c_test2.text_input("Riferimento", value=st.session_state.edit_testata.get('riferimento', ''))

        st.subheader("🔍 Aggiungi Righe")
        cs, cm, cn = st.columns([0.7, 0.15, 0.15], vertical_alignment="bottom")
        with cs: sel_art = st_searchbox(search_articles_arc, placeholder="Cerca codice o descrizione...", key=f"search_arc_{st.session_state.search_key_arc}")
        if cm.button("➕ Manuale", use_container_width=True): 
            st.session_state.temp_item_arc = {"CODICE": "EXTRA", "DESCRIZIONE": "", "PREZZO": 0.0, "is_manual": True}; st.rerun()
        if cn.button("🗒️ Nota", use_container_width=True): 
            st.session_state.temp_item_arc = {"tipo": "NOTA_TESTO", "DESCRIZIONE": ""}; st.rerun()

        if sel_art: st.session_state.temp_item_arc = sel_art

        if st.session_state.temp_item_arc:
            item = st.session_state.temp_item_arc
            with st.container():
                st.markdown('<div class="config-card">', unsafe_allow_html=True)
                if item.get("tipo") == "NOTA_TESTO":
                    t_n = st.text_area("Nota", value=item["DESCRIZIONE"])
                    if st.button("AGGIUNGI NOTA"):
                        st.session_state.righe_archivio.append({"tipo": "NOTA_TESTO", "DESCRIZIONE": t_n})
                        st.session_state.temp_item_arc = None; st.session_state.search_key_arc += 1; st.rerun()
                else:
                    if item.get("is_manual"):
                        item["CODICE"] = st.text_input("Codice", value=item["CODICE"])
                        item["DESCRIZIONE"] = st.text_input("Descrizione", value=item["DESCRIZIONE"])
                    else: st.write(f"**{item['CODICE']}** - {item['DESCRIZIONE']}")
                    cp1, cp2 = st.columns(2)
                    pl = cp1.number_input("Lordo", value=float(item.get('PREZZO', item.get('PREZZO_LORDO', 0.0))))
                    qta = cp2.number_input("Q.tà", min_value=1, value=int(item.get('QTA', 1)))
                    cs1, cs2, cs3 = st.columns(3)
                    s1 = cs1.number_input("S1", value=float(item.get('S1', item.get('SCONTO1', 0.0))))
                    s2 = cs2.number_input("S2", value=float(item.get('S2', item.get('SCONTO2', 0.0))))
                    s3 = cs3.number_input("S3", value=float(item.get('S3', item.get('SCONTO3', 0.0))))
                    pn = calcola_netto(pl, s1, s2, s3)
                    if st.button("SALVA RIGA"):
                        st.session_state.righe_archivio.append({"CODICE": item["CODICE"], "DESCRIZIONE": item["DESCRIZIONE"], "PREZZO_LORDO": pl, "PREZZO_NETTO": pn, "QTA": qta, "SCONTO_MERCE": False, "S1": s1, "S2": s2, "S3": s3, "NOTA": ""})
                        st.session_state.temp_item_arc = None; st.session_state.search_key_arc += 1; st.rerun()
                if st.button("Annulla"): st.session_state.temp_item_arc = None; st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

        tot_n = 0.0
        for idx, r in enumerate(st.session_state.righe_archivio):
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 1, 0.8])
                if r.get('tipo') == 'NOTA_TESTO': c1.markdown(f"**🗒️ NOTA:** {r['DESCRIZIONE']}")
                else:
                    val = r['PREZZO_NETTO'] * r['QTA']; tot_n += val
                    c1.markdown(f"**{r['CODICE']}** - {r['DESCRIZIONE']}"); c1.caption(f"Sconti: {format_sconti_string(r['S1'], r['S2'], r['S3'])}")
                    c2.markdown(f"**€ {val:,.2f}**")
                b1, b2 = c3.columns(2)
                if b1.button("✏️", key=f"e_{idx}"): st.session_state.temp_item_arc = st.session_state.righe_archivio.pop(idx); st.rerun()
                if b2.button("🗑️", key=f"d_{idx}"): st.session_state.righe_archivio.pop(idx); st.rerun()

        st.divider(); st.metric("TOTALE", f"€ {tot_n:,.2f}")
        if st.button("💾 SALVA MODIFICHE", type="primary", use_container_width=True):
            upd = {"totale_netto": tot_n, "data_consegna": str(data_cons) if data_cons else None, "riferimento": rif_ordine}
            if aggiorna_preventivo_db(st.session_state.edit_id, upd, st.session_state.righe_archivio) is True:
                st.success("Documento aggiornato!"); time.sleep(1); st.session_state.edit_id = None; st.rerun()

if __name__ == "__main__":
    show_archivio()