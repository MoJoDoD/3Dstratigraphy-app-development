# -*- coding: utf-8 -*-
"""
Schema dei dati di scavo: nomi dei layer GIS, dei fogli Excel e delle colonne.

Tutti i nomi stanno qui, in un solo punto. La tappa 2 aggiungerà l'abbinamento
guidato dei campi: gli ALIAS sotto sono il primo passo (riconoscono varianti
comuni dei nomi di colonna).
"""

# --- layer del GeoPackage ---------------------------------------------------
L_US = "us_poligoni"
L_USM = "usm_poligoni"
L_QUOTE = "quote"
L_PROFILI = "profili_us"
L_AREA = "area_scavo"
L_SEZIONI = "sezioni"
L_SEZ_DISEGNO = "sezioni_disegno"
L_RS = "reperti_speciali"
L_CAMPIONI = "campioni"
L_GRIGLIA = "griglia_2m"

LAYER_OBBLIGATORI = [L_US, L_QUOTE]
LAYER_FACOLTATIVI = [L_USM, L_PROFILI, L_AREA, L_SEZIONI, L_SEZ_DISEGNO, L_RS, L_CAMPIONI, L_GRIGLIA]

# campi nei layer
F_US = "us"
F_USM = "usm"
F_TIPO_QUOTA = "tipo_quota"
F_SEZIONE = "sezione"
F_INTERFACCIA = "interfaccia"

# tipi di quota
Q_SUP, Q_INF, Q_TAGLIO, Q_ORLO, Q_RASATURA, Q_FONDAZIONE = "sup", "inf", "taglio", "orlo", "rasatura", "fondazione"
TIPI_QUOTA = {Q_SUP, Q_INF, Q_TAGLIO, Q_ORLO, Q_RASATURA, Q_FONDAZIONE}

# --- fogli Excel ------------------------------------------------------------
S_US, S_USM, S_RAPPORTI, S_FASI = "US", "USM", "Rapporti", "Fasi"
S_MATERIALI, S_RS, S_CAMPIONI, S_DOC, S_QUOTE = "Materiali", "Reperti_speciali", "Campioni", "Documentazione", "Quote"
FOGLI_OBBLIGATORI = [S_US, S_RAPPORTI]

# colonne usate dal motore
C_US = "US"
C_USM = "USM"
C_TIPO = "Tipo"                       # positiva / negativa
C_CATEGORIA = "Categoria"
C_FASE = "Fase"
C_MARGINI = "Margini"                 # netti / rastremati / sfumati
C_SPESSORE = "Spessore medio stimato (m)"
C_BASE_USM = "Quota base usata (rilevata o stimata)"
C_COLORE = "Colore HEX"

# rapporti
R_COPRE, R_TAGLIA, R_RIEMPIE, R_APPOGGIA, R_LEGA, R_UGUALE = (
    "copre", "taglia", "riempie", "si appoggia a", "si lega a", "uguale a")
RAPPORTI_DIRETTI = {R_COPRE, R_TAGLIA, R_RIEMPIE, R_APPOGGIA}      # A è posteriore a B
RAPPORTI_CONTEMPORANEI = {R_LEGA, R_UGUALE}
INVERSI = {"copre": "coperto da", "taglia": "tagliato da", "riempie": "riempito da",
           "si appoggia a": "gli si appoggia", "si lega a": "si lega a", "uguale a": "uguale a"}
# forme inverse riconosciute in ingresso -> (rapporto diretto, scambia i termini)
DA_INVERSO = {v: k for k, v in INVERSI.items() if k != v}

# varianti dei nomi di colonna riconosciute in lettura (minuscolo, senza spazi doppi)
ALIAS = {
    C_US: ["us", "n. us", "n us", "numero us", "unità stratigrafica", "unita stratigrafica", "context"],
    C_USM: ["usm", "n. usm", "numero usm"],
    C_TIPO: ["tipo", "tipo us", "positiva/negativa"],
    C_SPESSORE: ["spessore", "spessore medio", "spessore (m)", "spessore medio (m)"],
    C_MARGINI: ["margini", "limiti", "limite"],
    C_FASE: ["fase", "phase", "periodo/fase"],
    C_CATEGORIA: ["categoria", "definizione generale"],
}


def normalizza_colonne(df, attese):
    """Rinomina le colonne di df che corrispondono a un alias noto."""
    ren = {}
    low = {str(c).strip().lower(): c for c in df.columns}
    for canon in attese:
        if canon in df.columns:
            continue
        for a in ALIAS.get(canon, []):
            if a in low:
                ren[low[a]] = canon
                break
    return df.rename(columns=ren) if ren else df
