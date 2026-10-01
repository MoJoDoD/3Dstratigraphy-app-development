# -*- coding: utf-8 -*-
"""
Tabelle grezze -> tabelle ordinate (una riga per scheda, una sola riga di intestazione).

Gli archivi di scavo arrivano nelle forme più diverse: titoli e loghi sopra l'intestazione, intestazioni
su più righe con celle unite, righe vuote, intestazioni ripetute a ogni pagina, righe di totale, schede
«trasposte» (un'unità per colonna), esportazioni campo/valore, matrici dei rapporti, più tabelle nello
stesso foglio, misure scritte con l'unità («45 cm», «0,45 m»). Questo modulo riordina un foglio letto
così com'è e dice che cosa ha fatto, perché l'importazione possa poi riconoscere le colonne:

    df, rapporto = normalizza_tabella(pd.read_excel(path, sheet_name="US", header=None), nome="US")
    for nota in rapporto:
        print(nota["messaggio"])

Una tabella già ordinata torna identica (lo stesso oggetto) e senza note. Tutto è deterministico.
I testi delle note sono in ``MESSAGGI`` (italiano, con segnaposto ``{0}``, ``{1}``… e nomi tra «»,
come vuole il catalogo delle traduzioni).
"""
import re
from functools import lru_cache

import numpy as np
import pandas as pd

from . import schema as sc

# ============================================================================ note
MESSAGGI = {
    "colonne_vuote": "{0} colonne vuote tolte",
    "scheda_blocchi": "Schede in blocchi etichetta/valore: {0} unità riportate su righe con {1} campi",
    "tabelle_multiple": "Il foglio contiene {0} tabelle separate da righe vuote: si usa «{1}»",
    "trasposta": "Tabella trasposta (un'unità per colonna): {0} unità riportate su righe",
    "matrice": "Matrice dei rapporti: {0} rapporti riportati in elenco (US, rapporto, US correlata)",
    "matrice_segni": "Nella matrice i segni «{0}» sono letti come «la riga copre la colonna»",
    "matrice_ignoti": "Segni della matrice non riconosciuti e ignorati: {0}",
    "intestazione": "Intestazione alla riga {0}: {1} righe sopra (titoli, righe vuote) ignorate",
    "intestazione_multipla": "Intestazione su {0} righe: nomi uniti (es. «{1}»)",
    "nomi_colonne": "Nomi di colonna ripuliti (spazi, a capo, colonne senza nome o doppie)",
    "righe_vuote": "{0} righe vuote tolte",
    "intestazioni_ripetute": "{0} righe che ripetono l'intestazione o il titolo tolte (salti pagina)",
    "totali": "{0} righe di totale tolte",
    "piede": "{0} righe di note in fondo alla tabella tolte",
    "campo_valore": "Tabella campo/valore: {0} unità riportate su righe con {1} campi",
    "misura_intestazione": "Colonna «{0}»: valori convertiti da {1} a metri (ora «{2}»)",
    "misura_valori": "Colonna «{0}»: unità di misura tolte dai valori e convertite in metri",
    "virgola": "Colonna «{0}»: numeri con la virgola decimale o i separatori delle migliaia convertiti",
}


def _nota(rapporto, codice, *argomenti):
    rapporto.append({"codice": codice, "messaggio": MESSAGGI[codice].format(*argomenti)})


def _imp():
    """Il modulo di importazione, caricato solo quando serve (evita l'import circolare)."""
    from . import importa
    return importa


def _norm(s):
    return _imp()._norm(s)


# ============================================================================ celle
_NUM_RE = re.compile(r"^\s*[-+]?(\d[\d.,'’  ]*\d|\d|[.,]\d+)\s*(mm|cm|m)?\s*$", re.I)
_SENZA_NOME = re.compile(r"^unnamed:\s*\d+(_level_\d+)?$", re.I)


def _vuoto(v):
    if v is None:
        return True
    if isinstance(v, float):
        return v != v
    if isinstance(v, str):
        return not v.strip()
    if isinstance(v, (int, np.integer, bool, np.bool_)):
        return False
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def _e_numero(v):
    if isinstance(v, (bool, np.bool_)):
        return False
    if isinstance(v, (int, np.integer)):
        return True
    if isinstance(v, (float, np.floating)):
        return v == v
    if isinstance(v, str):
        return bool(_NUM_RE.match(v))
    return False


def _e_testo(v):
    return isinstance(v, str) and bool(v.strip()) and not _NUM_RE.match(v)


def _testo(v):
    """Testo di una cella per i confronti (minuscolo, spazi ridotti)."""
    if isinstance(v, (float, np.floating)) and v == v and float(v).is_integer():
        v = int(v)
    return " ".join(str(v).split()).lower()


def _pulisci_nome(v):
    if _vuoto(v):
        return None
    if isinstance(v, (float, np.floating)) and float(v).is_integer():
        return str(int(v))
    return " ".join(str(v).split())


def _unici(nomi):
    """Nomi di colonna senza vuoti né doppioni."""
    out, visti = [], {}
    for i, n in enumerate(nomi):
        n = n or f"Colonna {i + 1}"
        k = n.lower()
        if k in visti:
            visti[k] += 1
            n = f"{n} ({visti[k]})"
        else:
            visti[k] = 1
        out.append(n)
    return out


# ============================================================================ identificativi
_TAG_UNITA = {"us", "usm", "su", "ctx", "cxt", "context", "ue", "u.s", "usn", "usn°", "n.us", "nus", "sk", "bef",
              "befund", "ut", "uts", "us-", "su-", "sg", "cut", "fill", "f", "c", "n", "nr", "n°"}
ALIAS_ID = {"us", "usm", "n us", "n. us", "n.us", "nr us", "nr. us", "us n", "us n.", "us n°", "n° us", "numero us",
            "num us", "context", "context no", "context no.", "context number", "su", "unità", "unita",
            "unità stratigrafica", "unita stratigrafica", "stratigraphic unit", "ctx", "cxt", "ue", "ue n", "ue n°",
            "unité", "unité stratigraphique", "befund", "befund nr", "befund nr.", "befundnummer", "bef. nr",
            "unidad", "unidad estratigráfica", "ue nº", "us nº"}
_SEP_ID = " \t-_/:.#\\|"


def _parti_id(v):
    """(prefisso, numero, suffisso, ambiguo) di un identificativo di unità («US 1005», «1005a», «A/1005»)."""
    if _vuoto(v):
        return None, None, None, False
    if isinstance(v, (bool, np.bool_)):
        return None, None, None, True
    if isinstance(v, (int, np.integer)):
        return None, int(v), None, False
    if isinstance(v, (float, np.floating)):
        return (None, int(v), None, False) if float(v).is_integer() else (None, None, None, True)
    s = " ".join(str(v).split())
    gruppi = list(re.finditer(r"\d+", s))
    if not gruppi:
        return s or None, None, None, True
    g = gruppi[-1]
    pre = s[:g.start()].strip(_SEP_ID) or None
    suf = s[g.end():].strip(_SEP_ID) or None
    amb = len(gruppi) > 1 or (suf is not None and (len(suf) > 3 or not suf.isalpha()))
    if re.fullmatch(r"\d+\.0+", s):           # «1005.0» letto come testo
        return None, int(gruppi[0].group()), None, False
    return pre, int(g.group()), suf, amb


def _e_unita(v):
    """Vero se la cella sembra il numero di un'unità stratigrafica."""
    if isinstance(v, (float, np.floating)):
        return v == v and float(v).is_integer() and 0 <= v < 1e7
    pre, num, suf, amb = _parti_id(v)
    if num is None or amb or num >= 10 ** 7:
        return False
    if pre is None:
        return True
    p = pre.lower().replace(" ", "")
    return p in _TAG_UNITA or (len(p) <= 3 and p.replace(".", "").isalnum())


def _chiave_unita(v):
    pre, num, suf, _ = _parti_id(v)
    return (num, (suf or "").lower())


def _valore_id(v):
    """Identificativo in forma comoda: intero se è solo un numero, altrimenti il testo ripulito."""
    pre, num, suf, amb = _parti_id(v)
    if num is not None and pre is None and suf is None and not amb:
        return num
    return " ".join(str(v).split())


def _etichetta(v):
    return " ".join(str(v).split()).rstrip(":").strip()


def _e_chiave_id(v):
    """Vero se l'etichetta è il nome del campo «numero di US» («US», «n. US», «Context», «UE n°»…)."""
    if not isinstance(v, str):
        return False
    k = _norm(_etichetta(v))
    return k in ALIAS_ID or k.rstrip(".:° ").strip() in ALIAS_ID


def separa_identificativo(serie):
    """Scompone identificativi di unità scritti in modi diversi: «US 1005», «1005a», «SU-12», «Ctx 3»,
    «A/1005», 1005.0. Ritorna un DataFrame con lo stesso indice e le colonne ``prefisso`` (sigla o sito),
    ``numero`` (intero), ``suffisso`` (lettera o «bis») e ``ambiguo`` (vero se ci sono più numeri,
    nessun numero o un suffisso strano: «1005-1006», «Saggio 2 US 15», «n.d.»)."""
    serie = pd.Series(serie)
    righe = [_parti_id(v) for v in serie]
    return pd.DataFrame({
        "prefisso": pd.Series([r[0] for r in righe], index=serie.index, dtype=object),
        "numero": pd.array([r[1] for r in righe], dtype="Int64"),
        "suffisso": pd.Series([r[2] for r in righe], index=serie.index, dtype=object),
        "ambiguo": [bool(r[3]) for r in righe]}, index=serie.index)


_NOMI_SITO = {"sito", "site", "area", "saggio", "settore", "trench", "trincea", "scavo", "cantiere", "località",
              "localita", "sondage", "secteur", "sector", "zona", "intervento", "site code", "codice sito", "sigla"}


def trova_sito_numero(df):
    """Colonne (sito, numero) quando il numero di US da solo si ripete tra siti/saggi diversi ma la coppia
    sito+numero è unica. None se non serve (numeri già unici) o non si trova."""
    cu = next((c for c in df.columns if _norm(c) in ALIAS_ID), None)
    if cu is None:
        return None
    v = df[cu].dropna()
    if not len(v) or v.map(_e_unita).mean() < 0.8 or v.map(_chiave_unita).is_unique:
        return None
    for c in df.columns:
        if c != cu and _norm(c) in _NOMI_SITO:
            coppie = df[[c, cu]].dropna()
            if len(coppie) and not coppie.duplicated().any():
                return c, cu
    return None


def identificativo_composto(df, col_sito, col_numero, sep="-"):
    """Identificativo unico «sito-numero» (es. «A-1005») da due colonne."""
    def uno(s, n):
        if _vuoto(n):
            return None
        n = _valore_id(n)
        return str(n) if _vuoto(s) else f"{_pulisci_nome(s)}{sep}{n}"
    return pd.Series([uno(s, n) for s, n in zip(df[col_sito], df[col_numero])], index=df.index)


# ============================================================================ rapporti scritti a parole
_ALTRI_RAPPORTI = {
    # italiano
    "sopra": "copre", "sotto": "coperto da", "coperta da": "coperto da", "ricopre": "copre",
    "tagliata da": "tagliato da", "riempita da": "riempito da", "riempimento di": "riempie",
    "si appoggia": "si appoggia a", "appoggia a": "si appoggia a", "si appoggia su": "si appoggia a",
    "si lega con": "si lega a", "legato a": "si lega a", "legata a": "si lega a", "uguale": "uguale a",
    "corrisponde a": "uguale a", "equivale a": "uguale a",
    # english
    "over": "copre", "under": "coperto da", "underlies": "coperto da", "is covered by": "coperto da",
    "is cut by": "tagliato da", "is filled by": "riempito da", "is abutted by": "gli si appoggia",
    "abuts against": "si appoggia a", "butts against": "si appoggia a", "same": "uguale a",
    # français
    "couvre": "copre", "recouvre": "copre", "scelle": "copre", "est couvert par": "coperto da",
    "couvert par": "coperto da", "recouvert par": "coperto da", "scellé par": "coperto da", "sous": "coperto da",
    "sur": "copre", "coupe": "taglia", "recoupe": "taglia", "coupé par": "tagliato da",
    "recoupé par": "tagliato da", "est coupé par": "tagliato da", "remplit": "riempie", "comble": "riempie",
    "rempli par": "riempito da", "comblé par": "riempito da", "s'appuie contre": "si appoggia a",
    "s'appuie sur": "si appoggia a", "s'appuie à": "si appoggia a", "appuyé contre": "si appoggia a",
    "lié à": "si lega a", "liée à": "si lega a", "chaîné à": "si lega a", "égal à": "uguale a",
    "identique à": "uguale a", "même que": "uguale a", "équivalent à": "uguale a",
    # deutsch
    "überdeckt": "copre", "überlagert": "copre", "liegt über": "copre", "über": "copre",
    "überdeckt von": "coperto da", "wird überdeckt von": "coperto da", "überlagert von": "coperto da",
    "liegt unter": "coperto da", "unter": "coperto da", "schneidet": "taglia", "geschnitten von": "tagliato da",
    "wird geschnitten von": "tagliato da", "verfüllt": "riempie", "verfüllung von": "riempie",
    "verfüllt von": "riempito da", "wird verfüllt von": "riempito da", "stößt an": "si appoggia a",
    "stösst an": "si appoggia a", "verzahnt mit": "si lega a", "bindet ein in": "si lega a",
    "gleich": "uguale a", "identisch mit": "uguale a", "entspricht": "uguale a",
    # español
    "cubre": "copre", "sella": "copre", "sobre": "copre", "cubierto por": "coperto da",
    "cubierta por": "coperto da", "sellado por": "coperto da", "bajo": "coperto da", "debajo de": "coperto da",
    "corta": "taglia", "cortado por": "tagliato da", "cortada por": "tagliato da", "rellena": "riempie",
    "relleno de": "riempie", "rellenado por": "riempito da", "rellenada por": "riempito da",
    "se apoya en": "si appoggia a", "se apoya a": "si appoggia a", "se adosa a": "si appoggia a",
    "se le apoya": "gli si appoggia", "se le adosa": "gli si appoggia", "se une a": "si lega a",
    "enlaza con": "si lega a", "igual a": "uguale a",
}
_SIMBOLI = {"=": "uguale a", "==": "uguale a", "≡": "uguale a", ">": "copre", "<": "coperto da"}


@lru_cache(maxsize=1)
def _frasi_rapporto():
    imp = _imp()
    frasi = {r: r for r in imp.RAPPORTI_COLONNE}
    frasi.update(imp.RAPPORTI_INGLESE)
    frasi.update(_ALTRI_RAPPORTI)
    parole = sorted(frasi, key=len, reverse=True)
    rx = re.compile(r"(?<!\w)(" + "|".join(re.escape(p) for p in parole) + r")(?!\w)|(==|=|≡|>|<)")
    return frasi, rx


def _testo_rapporti(s):
    return re.sub(r"\s+", " ", str(s).replace("’", "'").replace("_", " ").lower()).strip()


def rapporto_da_parola(v):
    """Nome del rapporto (forma italiana del motore) per una parola o un segno: «covers», «couvre»,
    «schneidet», «=», «>»… None se non si riconosce."""
    if _vuoto(v):
        return None
    t = _testo_rapporti(v)
    frasi, _ = _frasi_rapporto()
    return _SIMBOLI.get(t) or frasi.get(t)


def _numeri(seg):
    """Numeri di unità in un pezzo di testo, con gli intervalli «1001-1004» (anche «1001-4») espansi."""
    out = []
    for m in re.finditer(r"(\d+)(?:\s*[a-z](?![a-z]))?(?:\s*(?:-|–|—|\.\.|÷)\s*(\d+))?", seg):
        a, b = m.group(1), m.group(2)
        if b is None:
            out.append(int(a))
            continue
        x, y = int(a), int(b)
        if y < x and len(b) < len(a):
            y = int(a[:len(a) - len(b)] + b)
        out.extend(range(x, y + 1) if x < y <= x + 200 else [x, y])
    return out


def rapporti_da_testo(testo):
    """Rapporti scritti in un campo di testo, in più lingue (it/en/fr/de/es) e con i segni «=», «>», «<»:
    «copre 12, 13; taglia 4», «fills 1005», «= 22», «under 3/4/5», «couvre 1001-1004». Ritorna
    [(rapporto, numero)] come ``importa._rapporti_da_testo``, di cui è un'estensione (il formato di
    pyArchInit [['Copre', '1002', …]] passa a quella)."""
    if _vuoto(testo):
        return []
    s = str(testo).strip()
    if s.startswith("[["):
        return _imp()._rapporti_da_testo(s)
    t = _testo_rapporti(s)
    frasi, rx = _frasi_rapporto()
    trovati = [(m.start(), m.end(), frasi.get(m.group(1)) if m.group(1) else _SIMBOLI[m.group(2)])
               for m in rx.finditer(t)]
    out = []
    for i, (a, b, r) in enumerate(trovati):
        fine = trovati[i + 1][0] if i + 1 < len(trovati) else len(t)
        out.extend((r, n) for n in _numeri(t[b:fine]))
    return out


# ============================================================================ numeri e misure
_UNITA_INT = re.compile(r"[\(\[]\s*(mm|cm|m)\.?\s*(?:s\.?\s*l\.?\s*m\.?|a\.?\s*s\.?\s*l\.?|o\.?\s*d\.?|slm|asl)?\s*[\)\]]",
                        re.I)
_UNITA_FINE = re.compile(r"(?:\s|^)(?:in\s+)?(mm|cm)\s*$", re.I)
_VAL_UNITA = re.compile(r"^(.*?\d)\s*(mm|cm|m(?:etri|etres|eters|\.)?(?:\s*s\.?\s*l\.?\s*m\.?|\s*a\.?s\.?l\.?)?)\s*$",
                        re.I)
FATTORI = {"m": 1.0, "cm": 0.01, "mm": 0.001}
_NULLI = {"-", "--", "—", "–", "n.d.", "n.d", "nd", "?", "n/a", "na", "/", "", "s.d.", "n.r."}


def _unita_intestazione(nome):
    """(unità, inizio, fine) dell'unità di misura scritta nell'intestazione («Prof. (cm)»), o None."""
    s = str(nome)
    m = _UNITA_INT.search(s) or _UNITA_FINE.search(s)
    return (m.group(1).lower(), m.start(1), m.end(1)) if m else None


def _modo_separatori(testi):
    """'it' (virgola decimale), 'en' (virgola delle migliaia) o None, guardando tutta la colonna."""
    it = en = False
    for t in testi:
        if "," in t and "." in t:
            if t.rfind(",") > t.rfind("."):
                it = True
            else:
                en = True
        elif "," in t:
            if t.count(",") > 1:
                en = True
            elif len(t) - t.rfind(",") - 1 != 3:
                it = True
    return "it" if it and not en else ("en" if en and not it else None)


def _leggi_numero(t, modo=None):
    """Valore di un numero scritto come testo, con virgola decimale e separatori delle migliaia."""
    t = t.replace("’", "'").replace(" ", " ").strip()
    segno = -1.0 if t.startswith("-") else 1.0
    t = t.lstrip("+-").strip()
    if re.fullmatch(r"\d{1,3}([ ']\d{3})+([.,]\d+)?", t):
        t = re.sub(r"[ ']", "", t)
    if not re.fullmatch(r"\d+([.,]\d+)*|[.,]\d+", t):
        return None
    if "," in t and "." in t:
        dec = "," if t.rfind(",") > t.rfind(".") else "."
        mil = "." if dec == "," else ","
        intera, frac = t.rsplit(dec, 1)
        if not re.fullmatch(r"\d{1,3}(" + re.escape(mil) + r"\d{3})*", intera):
            return None
        t = intera.replace(mil, "") + "." + frac
    elif "," in t:
        if t.count(",") > 1 or (modo == "en" and re.fullmatch(r"\d{1,3},\d{3}", t)):
            if not re.fullmatch(r"\d{1,3}(,\d{3})+", t):
                return None
            t = t.replace(",", "")
        else:
            t = t.replace(",", ".")
    elif "." in t:
        if t.count(".") > 1 or (modo == "it" and re.fullmatch(r"\d{1,3}\.\d{3}", t)):
            if not re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
                return None
            t = t.replace(".", "")
    try:
        return segno * float(t)
    except ValueError:
        return None


def numero_con_unita(v, modo=None):
    """(valore, unità) di una cella: 12.5 -> (12.5, None); «0,45 m» -> (0.45, 'm'); «45cm» -> (45.0, 'cm');
    «1.234,5» -> (1234.5, None). (None, None) se non è un numero."""
    if isinstance(v, (bool, np.bool_)):
        return None, None
    if isinstance(v, (int, float, np.integer, np.floating)):
        return (None, None) if v != v else (float(v), None)
    if not isinstance(v, str):
        return None, None
    s = v.strip()
    unita = None
    m = _VAL_UNITA.match(s)
    if m:
        s, u = m.group(1), m.group(2).lower()
        unita = "m" if u.startswith("m") and not u.startswith("mm") else u
    return _leggi_numero(s, modo), (unita if _leggi_numero(s, modo) is not None else None)


def _da_saltare(nome):
    """Colonne da non convertire: numeri di US, rapporti, date."""
    imp = _imp()
    n = _norm(nome)
    return (n in ALIAS_ID or n in imp.ALIAS_UNITA or imp._rapporto(n) in imp.RAPPORTI_COLONNE or
            n in imp.COLONNE_PADRE or any(k in n for k in ("rapport", "relation", "data", "date", "datum", "fecha")))


def converti_misure(df, rapporto=None):
    """Numeri scritti come testo -> numeri: virgola decimale, separatori delle migliaia, unità nei valori
    («0,45 m», «45cm») e nell'intestazione («Prof. (cm)»), tutto in metri. Le colonne in cm/mm cambiano
    nome («Prof. (m)») perché non vengano riconvertite. Ritorna (df, rapporto)."""
    rapporto = [] if rapporto is None else rapporto
    out = df
    rinomina = {}
    for c in list(df.columns):
        if _da_saltare(c):
            continue
        s = df[c]
        ui = _unita_intestazione(c)
        u_int = ui[0] if ui else None
        if pd.api.types.is_bool_dtype(s):
            continue
        if pd.api.types.is_numeric_dtype(s):
            if u_int in ("cm", "mm"):
                out = out.copy() if out is df else out
                out[c] = s * FATTORI[u_int]
                nuovo = str(c)[:ui[1]] + "m" + str(c)[ui[2]:]
                rinomina[c] = nuovo
                _nota(rapporto, "misura_intestazione", c, u_int, nuovo)
            continue
        pieni = [(i, v) for i, v in enumerate(s.tolist()) if not _vuoto(v)]
        if not pieni:
            continue
        prova = [v for _, v in pieni[:200]]
        if sum(_e_numero(v) or (isinstance(v, str) and _VAL_UNITA.match(v.strip()) is not None) or
               (isinstance(v, str) and v.strip().lower() in _NULLI) for v in prova) < len(prova):
            continue
        testi = [v.strip() for _, v in pieni if isinstance(v, str)]
        modo = _modo_separatori(testi)
        valori, unita, cambiati, nulli = [], [], 0, 0
        for _, v in pieni:
            if isinstance(v, str) and v.strip().lower() in _NULLI:
                valori.append(None)
                unita.append(None)
                nulli += 1
                continue
            x, u = numero_con_unita(v, modo)
            if x is None:
                break
            if isinstance(v, str):
                try:
                    semplice = float(v.strip())
                except ValueError:
                    semplice = None
                if semplice is None or abs(semplice - x) > 1e-12 or u:
                    cambiati += 1
            valori.append(x)
            unita.append(u)
        else:
            if nulli == len(pieni) or (not cambiati and u_int not in ("cm", "mm")):
                continue
            con_unita = [u for u in unita if u]
            predef = u_int or (max(set(con_unita), key=con_unita.count) if con_unita else None)
            nuovi = np.full(len(s), np.nan)
            for (i, _), x, u in zip(pieni, valori, unita):
                if x is not None:
                    nuovi[i] = x * FATTORI.get(u or predef, 1.0) if (u or predef) else x
            out = out.copy() if out is df else out
            out[c] = nuovi
            if u_int in ("cm", "mm"):
                nuovo = str(c)[:ui[1]] + "m" + str(c)[ui[2]:]
                rinomina[c] = nuovo
                _nota(rapporto, "misura_intestazione", c, u_int, nuovo)
            elif con_unita:
                _nota(rapporto, "misura_valori", c)
            else:
                _nota(rapporto, "virgola", c)
    if rinomina:
        out = out.rename(columns=rinomina)
    return out, rapporto


# ============================================================================ griglia
def _griglia(df):
    """Il foglio come matrice di oggetti (NaN nelle celle vuote). Se il DataFrame ha già dei nomi di colonna,
    questi diventano la riga 0. Ritorna (griglia, nomi_in_riga_0, intestazione_affidabile)."""
    col = df.columns
    if isinstance(col, pd.MultiIndex):
        nomi = [" ".join(str(p) for p in t if not _vuoto(p) and not _SENZA_NOME.match(str(p).strip()))
                for t in col]
    elif isinstance(col, pd.RangeIndex) or all(isinstance(c, (int, np.integer)) and c == i for i, c in enumerate(col)):
        nomi = None
    else:
        nomi = [c for c in col]
    if nomi is not None:
        nomi = [np.nan if _vuoto(c) or (isinstance(c, str) and _SENZA_NOME.match(c.strip())) else c for c in nomi]
    corpo = np.empty(df.shape, dtype=object)
    vuoto_s = np.frompyfunc(_vuoto, 1, 1)
    for j in range(df.shape[1]):
        s = df.iloc[:, j]
        col = s.to_numpy(dtype=object, copy=True)
        if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
            v = s.to_numpy(dtype=float, na_value=np.nan)
            col[np.isnan(v)] = np.nan
            inf = np.flatnonzero(np.isinf(v))
        else:
            col[vuoto_s(col).astype(bool)] = np.nan
            inf = [i for i, x in enumerate(col) if isinstance(x, (float, np.floating)) and np.isinf(x)]
        for i in inf:              # pandas legge la parola «inf» (quota inferiore!) come infinito: torna testo
            col[i] = "inf" if col[i] > 0 else "-inf"
        corpo[:, j] = col
    if nomi is not None:
        nomi = [np.nan if _vuoto(c) else c for c in nomi]
    G = np.vstack([np.array(nomi, dtype=object)[None, :], corpo]) if nomi is not None else corpo
    forte = nomi is not None and sum(_vuoto(n) for n in nomi) / max(len(nomi), 1) < 0.5
    return G, nomi is not None, forte


def _riga_intestazione(vals, W):
    ne = len(vals)
    if ne < 2 or ne < 0.5 * W:
        return False
    if sum(_e_testo(v) for v in vals) < 0.75 * ne or any(len(str(v)) > 80 for v in vals):
        return False
    return len({_testo(v) for v in vals}) == ne


def _pieni(A, i):
    return [v for v in A[i] if not _vuoto(v)]


# ============================================================================ schede in blocchi etichetta/valore
def _schede_a_blocchi(A):
    """Esportazioni «scheda»: coppie etichetta/valore una sotto l'altra (US | 1001, Tipo | strato, …),
    anche su più coppie di colonne. Ritorna (df, n_campi) o None."""
    nc = A.shape[1]
    if nc not in (2, 4, 6) or A.shape[0] < 4:
        return None
    etich = A[:, 0::2]
    campione = [v for v in etich[:60].ravel() if not _vuoto(v)]
    if len(campione) < 4 or sum(_e_testo(v) for v in campione) < 0.95 * len(campione):
        return None
    coppie = []
    for i in range(A.shape[0]):
        for k in range(0, nc, 2):
            e, v = A[i, k], A[i, k + 1]
            if _vuoto(e):
                if not _vuoto(v):
                    return None
                continue
            if not _e_testo(e):
                return None
            coppie.append((_etichetta(e), v))
    chiave = next((e for e, _ in coppie[:6] if _e_chiave_id(e)), None)
    if chiave is None:
        return None
    k0 = _testo(chiave)
    schede, cur = [], None
    for e, v in coppie:
        if _testo(e) == k0:
            cur = {}
            schede.append(cur)
        if cur is not None and e not in cur:
            cur[e] = v
    if len(schede) < 2:
        return None
    if sum(_e_unita(s[chiave] if chiave in s else next(iter(s.values()))) for s in schede) < 0.8 * len(schede):
        return None
    if sum(len(s) >= 2 for s in schede) < 0.7 * len(schede):
        return None
    campi = list(dict.fromkeys(e for s in schede for e in s))
    if len(campi) < 2:
        return None
    nomi = _unici(campi)
    df = pd.DataFrame([[s.get(e, np.nan) for e in campi] for s in schede], columns=nomi)
    return _tipi(df), len(campi)


# ============================================================================ più tabelle nello stesso foglio
def _profilo_diverso(A, righe, i0):
    """Vero se sotto la riga i0 ci sono numeri in colonne dove i0 ha un testo (i0 è un'intestazione)."""
    seguenti = [r for r in righe if r > i0][:30]
    for j in range(A.shape[1]):
        if not _e_testo(A[i0, j]):
            continue
        v = [A[r, j] for r in seguenti if not _vuoto(A[r, j])]
        if len(v) >= 2 and sum(_e_numero(x) for x in v) >= 0.5 * len(v):
            return True
    return False


def _blocchi(A, n):
    """Tabelle impilate nello stesso foglio, separate da righe vuote: [(titolo, righe)]."""
    segmenti, cur = [], []
    for i, k in enumerate(n):
        if k == 0:
            if cur:
                segmenti.append(cur)
                cur = []
        else:
            cur.append(i)
    if cur:
        segmenti.append(cur)
    if len(segmenti) <= 1:
        return [(None, list(range(A.shape[0])))]

    def titolo_di(righe):
        return next((_pulisci_nome(_pieni(A, r)[0]) for r in righe if n[r] == 1 and _e_testo(_pieni(A, r)[0])), None)

    def intestazione(righe):
        W = sum(1 for j in range(A.shape[1]) if any(not _vuoto(A[r, j]) for r in righe[:60]))
        for r in righe[:30]:
            if n[r] >= 2 and _riga_intestazione(_pieni(A, r), W):
                return [_testo(v) for v in _pieni(A, r)]
        return None

    tabelle, sospese = [], []
    for si, s in enumerate(segmenti):
        titoli = []
        for r in s:
            if n[r] == 1 and _e_testo(_pieni(A, r)[0]):
                titoli.append(r)
            else:
                break
        resto = s[len(titoli):]
        if not resto:                                  # solo titoli: valgono per la tabella che segue
            if tabelle and si == len(segmenti) - 1:
                tabelle[-1]["righe"].extend(sospese + s)
            else:
                sospese.extend(s)
            continue
        if not tabelle:
            tabelle.append({"titolo": titolo_di(sospese + titoli), "righe": sospese + s,
                            "int": intestazione(s)})
            sospese = []
            continue
        r0 = resto[0]
        W = sum(1 for j in range(A.shape[1]) if any(not _vuoto(A[r, j]) for r in resto[:60]))
        nuova = (n[r0] >= 2 and _riga_intestazione(_pieni(A, r0), W) and any(n[r] >= 2 for r in resto[1:]) and
                 [_testo(v) for v in _pieni(A, r0)] != tabelle[-1]["int"] and
                 bool(((titoli or sospese) and W >= 3) or _profilo_diverso(A, resto, r0)))
        if nuova:
            tabelle.append({"titolo": titolo_di(sospese + titoli), "righe": sospese + s,
                            "int": [_testo(v) for v in _pieni(A, r0)]})
        else:
            tabelle[-1]["righe"].extend(sospese + s)
        sospese = []
    if sospese and tabelle:
        tabelle[-1]["righe"].extend(sospese)
    if len(tabelle) <= 1:
        return [(None, list(range(A.shape[0])))]
    return [(t["titolo"], sorted(t["righe"])) for t in tabelle]


def _nomi_tabelle(blocchi):
    out, visti = [], set()
    for k, (titolo, _) in enumerate(blocchi):
        nome = titolo or f"Tabella {k + 1}"
        while nome in visti:
            nome = f"{nome} ({k + 1})"
        visti.add(nome)
        out.append(nome)
    return out


def dividi_tabelle(df):
    """Divide un foglio con più tabelle una sotto l'altra (separate da righe vuote, ognuna con il suo
    titolo o la sua intestazione) in tabelle distinte: {nome: tabella grezza}. Il nome è il titolo della
    tabella, altrimenti «Tabella N». Le tabelle restano grezze (senza intestazione, colonne 0, 1, …):
    si passano poi a ``normalizza_tabella``. Un foglio con una sola tabella torna intero."""
    G, _, _ = _griglia(df)
    G = G[:, ~pd.isna(G).all(axis=0)] if G.size else G
    n = (~pd.isna(G)).sum(axis=1)
    blocchi = _blocchi(G, n)
    out = {}
    for nome, (_, righe) in zip(_nomi_tabelle(blocchi), blocchi):
        B = G[righe]
        B = B[:, ~pd.isna(B).all(axis=0)]
        out[nome] = pd.DataFrame(B)
    return out


# ============================================================================ schede trasposte e matrici
def _trasposta(A, R):
    """Un'unità per colonna, i nomi dei campi nella prima colonna. Ritorna (df, n_unità) o None."""
    nc = A.shape[1]
    if nc < 2 or len(R) < 3:
        return None
    idr = None
    for i in R[:10]:
        altri = [v for v in A[i, 1:] if not _vuoto(v)]
        if len(altri) < 2 or len(altri) < 0.5 * (nc - 1) or sum(_e_unita(v) for v in altri) < 0.8 * len(altri):
            continue
        if len({_chiave_unita(v) for v in altri}) != len(altri):
            continue
        lab = A[i, 0]
        if (_vuoto(lab) and i == R[0]) or _e_chiave_id(lab):
            idr = i
            break
    if idr is None:
        return None
    campi = [i for i in R if i != idr]
    etich = [A[i, 0] for i in campi if not _vuoto(A[i, 0])]
    if len(etich) < 2 or sum(_e_testo(e) for e in etich) < 0.8 * len(etich):
        return None
    if len({_testo(e) for e in etich}) < 0.9 * len(etich):
        return None
    nomi = _unici([_pulisci_nome(A[idr, 0]) or "US"] + [_pulisci_nome(_etichetta(A[i, 0])) if not _vuoto(A[i, 0])
                                                       else None for i in campi])
    righe = [[_valore_id(A[idr, j])] + [A[i, j] for i in campi] for j in range(1, nc) if not _vuoto(A[idr, j])]
    return _tipi(pd.DataFrame(righe, columns=nomi)), len(righe)


_SEGNI_DIREZIONE = {"x", "•", "●", "*", "✓", "✔", "+", "si", "sì", "yes", "1"}


def _segno_matrice(v):
    """Rapporto per una cella della matrice: nome del rapporto, 'segno' (rapporto senza direzione esplicita),
    None (cella vuota o 0) o '?' (non riconosciuto)."""
    if _vuoto(v):
        return None
    if isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, (bool, np.bool_)):
        return None if v == 0 else ("segno" if v == 1 else "?")
    t = _testo_rapporti(v)
    if t in ("0", "-", "."):
        return None
    if t in _SEGNI_DIREZIONE:
        return "segno"
    return rapporto_da_parola(t) or "?"


def _matrice(A, R):
    """Matrice dei rapporti: unità sulle righe e sulle colonne, segni o parole nelle celle.
    Ritorna (df lungo, segni senza direzione, segni ignoti) o None."""
    nc = A.shape[1]
    if nc < 4 or len(R) < 3:
        return None
    i0 = R[0]
    if not (_vuoto(A[i0, 0]) or _e_testo(A[i0, 0])):
        return None
    cols = [j for j in range(1, nc) if not _vuoto(A[i0, j])]
    if len(cols) < 3 or sum(_e_unita(A[i0, j]) for j in cols) < 0.8 * len(cols):
        return None
    kc = [_chiave_unita(A[i0, j]) for j in cols]
    if len(set(kc)) != len(kc):
        return None
    righe = [i for i in R[1:] if not _vuoto(A[i, 0])]
    if len(righe) < 2 or sum(_e_unita(A[i, 0]) for i in righe) < 0.8 * len(righe):
        return None
    kr = [_chiave_unita(A[i, 0]) for i in righe]
    if len(set(kr) & set(kc)) < 0.5 * min(len(set(kr)), len(kc)):
        return None
    celle = [(i, j, A[i, j]) for i in righe for j in cols if not _vuoto(A[i, j])]
    if not celle or any(len(str(v).strip()) > 25 for _, _, v in celle):
        return None
    segni = [(i, j, v, _segno_matrice(v)) for i, j, v in celle]
    validi = [x for x in segni if x[3] is not None]
    if not validi or sum(x[3] != "?" for x in validi) < 0.7 * len(validi):
        return None
    if all(x[3] in ("segno", "?") for x in validi) and \
            all(isinstance(v, (int, float, np.integer, np.floating)) for _, _, v, _ in validi):
        # solo 0/1: è una matrice se la diagonale è vuota
        diag = [s for i, j, v, s in segni if _chiave_unita(A[i, 0]) == _chiave_unita(A[i0, j]) and s]
        if diag:
            return None
    out, visti, senza_dir, ignoti = [], set(), set(), set()
    for i, j, v, s in validi:
        a, b = _valore_id(A[i, 0]), _valore_id(A[i0, j])
        if s == "?":
            ignoti.add(str(v).strip())
            continue
        if _chiave_unita(A[i, 0]) == _chiave_unita(A[i0, j]):
            continue
        if s == "segno":
            senza_dir.add(_pulisci_nome(v))
            s = sc.R_COPRE
        if s in sc.DA_INVERSO:
            a, b, s = b, a, sc.DA_INVERSO[s]
        k = (a, s, b) if s not in sc.RAPPORTI_CONTEMPORANEI else (min(a, b, key=str), s, max(a, b, key=str))
        if k not in visti:
            visti.add(k)
            out.append((a, s, b))
    df = pd.DataFrame(out, columns=["US", "Rapporto", "US correlata"])
    return df, sorted(senza_dir), sorted(ignoti)


def matrice_in_elenco(df):
    """Matrice dei rapporti (unità sulle righe e sulle colonne) -> elenco (US, Rapporto, US correlata).
    I segni «>» «<» «=» e le parole («copre», «cuts»…) danno il rapporto; «x», «1», «•» si leggono come
    «la riga copre la colonna». None se la tabella non è una matrice."""
    G, _, _ = _griglia(df)
    G = G[:, ~pd.isna(G).all(axis=0)] if G.size else G
    R = [i for i in range(G.shape[0]) if not pd.isna(G[i]).all()]
    m = _matrice(G, R)
    return None if m is None else m[0]


# ============================================================================ intestazione
_UNITA_RIGA = re.compile(r"^[\(\[]?\s*(mm|cm|m|m\s*s\.?\s*l\.?\s*m\.?|%|g|kg|n\.?|nr\.?|n°|°)\s*[\)\]]?$", re.I)


def _trova_intestazione(A, R, n):
    W = A.shape[1]
    ultimo = max((r for r in R if n[r] >= 2), default=-1)
    for i in R[:30]:
        if i < ultimo and n[i] >= 2 and _riga_intestazione(_pieni(A, i), W):
            return i
    return next((i for i in R if n[i] >= max(2, 0.5 * W)), R[0])


def _continua_intestazione(H, C, D):
    """Vero se la riga C completa l'intestazione H (gruppi su celle unite, oppure le unità di misura)."""
    cn = [v for v in C if not _vuoto(v)]
    if not cn or any(not _e_testo(v) or len(str(v)) > 30 for v in cn):
        return False
    if all(_UNITA_RIGA.match(str(v).strip()) for v in cn):
        return any(not _vuoto(H[j]) for j in range(len(C)) if not _vuoto(C[j]))
    gruppo = False
    for j in range(1, len(H)):
        if _vuoto(H[j]) and not _vuoto(C[j]):
            k = j - 1
            while k >= 0 and _vuoto(H[k]):
                k -= 1
            if k >= 0 and not _vuoto(C[k]):
                gruppo = True
                break
    if not gruppo:
        return False
    if any(not _vuoto(H[j]) and _vuoto(C[j]) for j in range(len(C))):
        return True
    return D is not None and any(_e_testo(C[j]) and _e_numero(D[j]) for j in range(len(C)))


def _unisci_intestazione(H, C):
    out, gruppo = [], None
    for j in range(len(H)):
        h, c = H[j], C[j]
        if not _vuoto(h):
            gruppo = _pulisci_nome(h)
        elif _vuoto(c):
            gruppo = None
        base = _pulisci_nome(h) if not _vuoto(h) else (gruppo if not _vuoto(c) else None)
        if _vuoto(c):
            out.append(base)
        elif _UNITA_RIGA.match(str(c).strip()):
            u = str(c).strip().strip("()[]").strip()
            out.append(f"{base} ({u})" if base else _pulisci_nome(c))
        else:
            out.append(f"{base} {_pulisci_nome(c)}" if base else _pulisci_nome(c))
    return out


# ============================================================================ righe da togliere
_TOTALE_RE = re.compile(r"^\s*(?:sub\s*-?\s*)?(?:totale|totali|totals?|totaux?|totales?|tot\.?|somma|sum|summe|"
                        r"gesamt\w*|insgesamt)(?=$|[\s:.\-(])", re.I)


def _righe_da_togliere(A, D, n, righe_int, titoli):
    """Righe dei dati da togliere: vuote, intestazioni o titoli ripetuti, totali, note in fondo."""
    vuote = [i for i in D if n[i] == 0]
    piene = [i for i in D if n[i] > 0]
    if not piene:
        return vuote, [], [], []
    P = A[piene]
    occ = ~pd.isna(P)
    primo = P[np.arange(len(piene)), occ.argmax(axis=1)]
    teste = [[_testo(v) if not _vuoto(v) else None for v in A[h]] for h in righe_int]
    primi_int = {next((t for t in tt if t), None) for tt in teste}
    tit = {_testo(t) for t in titoli}
    ripetute, totali = [], []
    for k, (i, p) in enumerate(zip(piene, primo)):
        if not isinstance(p, str):
            continue
        tp = _testo(p)
        if tp in primi_int:
            for tt in teste:
                pieni_h = [j for j, t in enumerate(tt) if t]
                uguali = sum(1 for j in pieni_h if not _vuoto(A[i, j]) and _testo(A[i, j]) == tt[j])
                if uguali >= max(1, 0.8 * len(pieni_h)) and (len(pieni_h) == 1 or uguali >= 2):
                    ripetute.append(i)
                    break
            else:
                if n[i] == 1 and tp in tit:
                    ripetute.append(i)
        elif n[i] == 1 and tp in tit:
            ripetute.append(i)
        elif _TOTALE_RE.match(p) and len(p) <= 30:
            altri = [v for v in A[i] if not _vuoto(v) and v is not p]
            if all(_e_numero(v) for v in altri):          # anche senza numeri (formule non calcolate)
                totali.append(i)
    tolte = set(ripetute) | set(totali)
    piede = []
    if A.shape[1] >= 3:
        for i in reversed(piene):
            if i in tolte:
                continue
            v = _pieni(A, i)
            # una sola cella, nella prima colonna, con una frase (non un numero di US): «Compilato da…»
            if n[i] == 1 and not _vuoto(A[i, 0]) and _e_testo(v[0]) and len(v[0].strip()) >= 10 \
                    and not _e_unita(v[0]):
                piede.append(i)
            else:
                break
    return vuote, ripetute, totali, piede


# ============================================================================ campo/valore
_NOMI_CAMPO = {"campo", "field", "field name", "nome campo", "attributo", "attribute", "voce", "chiave", "key",
               "proprietà", "proprieta", "property", "variabile", "variable", "parametro", "parameter", "descrittore",
               "champ", "feld", "campo/field"}
_NOMI_VALORE = {"valore", "value", "val", "dato", "contenuto", "content", "testo", "text", "risposta", "valeur",
                "wert", "valor"}


def _campo_valore(df):
    """Tabella lunga [US, campo, valore] -> una riga per unità. Ritorna (df, n_unità, n_campi) o None."""
    if df.shape[1] < 3 or len(df) < 4:
        return None
    imp = _imp()
    low = {_norm(c): c for c in df.columns}
    cc = next((low[k] for k in low if k in _NOMI_CAMPO), None)
    cv = next((low[k] for k in low if k in _NOMI_VALORE), None)

    def unita_ok(c):
        v = df[c].dropna()
        return len(v) and v.map(_e_unita).mean() >= 0.8 and v.map(_chiave_unita).nunique() < len(v)

    if cc is not None and cv is not None and cc != cv:
        altre = [c for c in df.columns if c not in (cc, cv)]
        cu = next((c for c in altre if _norm(c) in ALIAS_ID and unita_ok(c)), None) or \
            next((c for c in altre if unita_ok(c)), None)
    elif df.shape[1] == 3:
        cu, cc, cv = df.columns
        if not unita_ok(cu):
            return None
        campi = df[cc].dropna()
        if not len(campi) or not campi.map(_e_testo).all():
            return None
        if campi.map(lambda x: imp._rapporto(x) in imp.RAPPORTI_COLONNE or rapporto_da_parola(x) is not None).any():
            return None
        # i valori di uno stesso campo hanno lo stesso tipo (Tipo: testo, Quota: numeri), i campi tra loro no
        coppie = df[[cc, cv]].dropna()
        coppie = coppie[~coppie[cv].map(lambda x: isinstance(x, str) and x.strip().lower() in _NULLI)]
        if not len(coppie):
            return None
        frazioni = coppie[cv].map(_e_numero).astype(float).groupby(coppie[cc].map(_testo)).mean()
        if not ((frazioni >= 0.8) | (frazioni <= 0.2)).all() or not (frazioni >= 0.8).any() or \
                not (frazioni <= 0.2).any():
            return None
        nu = df[cu].map(_chiave_unita).nunique()
        if not (2 <= campi.nunique() <= 60) or len(campi) < 2 * nu:
            return None
    else:
        return None
    if cu is None:
        return None
    sub = df[df[cu].notna() & df[cc].notna()]
    chiavi = sub[cu].map(_valore_id)
    if pd.DataFrame({"u": chiavi, "c": sub[cc].map(_pulisci_nome)}).duplicated().mean() > 0.05:
        return None
    extra = [c for c in df.columns if c not in (cu, cc, cv)]
    for c in extra:
        if sub.groupby(chiavi)[c].nunique(dropna=True).max() > 1:
            return None
    ordine_u = list(dict.fromkeys(chiavi))
    ordine_c = list(dict.fromkeys(sub[cc].map(_pulisci_nome)))
    tab = {u: {} for u in ordine_u}
    for u, c, v in zip(chiavi, sub[cc].map(_pulisci_nome), sub[cv]):
        tab[u].setdefault(c, v)
    ex = {u: {} for u in ordine_u}
    for c in extra:
        for u, v in zip(chiavi, sub[c]):
            if not _vuoto(v):
                ex[u].setdefault(c, v)
    nomi = _unici([_pulisci_nome(cu)] + [_pulisci_nome(c) for c in extra] + ordine_c)
    righe = [[u] + [ex[u].get(c, np.nan) for c in extra] + [tab[u].get(c, np.nan) for c in ordine_c]
             for u in ordine_u]
    return _tipi(pd.DataFrame(righe, columns=nomi)), len(ordine_u), len(ordine_c)


# ============================================================================ colonne larghe
_MATERIALI = {"ceramica", "ceramiche", "vetro", "vetri", "ossa", "osso", "metallo", "metalli", "ferro", "bronzo",
              "rame", "piombo", "selce", "litica", "litico", "laterizi", "laterizio", "intonaco", "malacofauna",
              "carboni", "monete", "fauna", "faunistici", "pottery", "glass", "bone", "bones", "animal bone", "metal",
              "iron", "copper alloy", "lead", "flint", "lithics", "tile", "cbm", "shell", "charcoal", "coins", "coin",
              "slag", "scorie", "ceramic", "céramique", "verre", "os", "métal", "keramik", "glas", "knochen",
              "metall", "cerámica", "vidrio", "hueso", "huesos", "anfore", "anfora", "sigillata", "terra sigillata",
              "lucerne", "chiodi", "nails", "macine", "pietra", "stone", "legno", "wood"}
_FASE_RE = re.compile(r"^(fase|phase|periodo|period|periode|période|phase)\s*[\w.]+$", re.I)


def colonne_larghe(df):
    """Colonne «una per materiale/fase» (Ceramica, Vetro, Ossa… o Fase I, Fase II…) con conteggi o pesi
    numerici: candidate per ``scomponi_colonne``. Lista vuota se meno di due."""
    out = []
    for c in df.columns:
        n = _norm(c)
        base = re.sub(r"\s*[\(\[].*?[\)\]]\s*$", "", n).strip()
        if base in _MATERIALI or _FASE_RE.match(base):
            v = df[c].dropna()
            if not len(v) or v.map(_e_numero).all():
                out.append(c)
    return out if len(out) >= 2 else []


def scomponi_colonne(df, colonna_id, colonne=None, nome_variabile="Classe", nome_valore="NR", tieni_zeri=False):
    """Da larga a lunga: una riga per (unità, materiale) invece di una colonna per materiale.
    ``colonne`` predefinite: quelle di ``colonne_larghe``. Le celle vuote (e gli zeri, se non
    ``tieni_zeri``) non danno righe. Le altre colonne si ripetono su ogni riga."""
    colonne = list(colonne) if colonne is not None else colonne_larghe(df)
    if not colonne:
        return df.copy()
    fisse = [c for c in df.columns if c not in colonne]
    if colonna_id not in fisse:
        raise KeyError(colonna_id)
    lungo = df.reset_index(drop=True).reset_index().melt(id_vars=["index"] + fisse, value_vars=colonne,
                                                         var_name=nome_variabile, value_name=nome_valore)
    lungo = lungo[lungo[nome_valore].notna()]
    if not tieni_zeri:
        lungo = lungo[pd.to_numeric(lungo[nome_valore], errors="coerce").fillna(1) != 0]
    lungo[nome_variabile] = pd.Categorical(lungo[nome_variabile], categories=colonne, ordered=True)
    lungo = lungo.sort_values(["index", nome_variabile], kind="stable").drop(columns="index")
    lungo[nome_variabile] = lungo[nome_variabile].astype(str)
    return lungo.reset_index(drop=True)


# ============================================================================ tipi
def _tipi(df):
    """Colonne di oggetti fatte solo di numeri -> numeriche (come farebbe pandas leggendo il file)."""
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_numeric_dtype(s) or pd.api.types.is_bool_dtype(s):
            continue
        pieni = s.notna()
        if not pieni.any():
            continue
        v = s[pieni]
        if not all(_e_numero(x) and not (isinstance(x, str) and re.search(r"[,'’  a-z]", x.strip(), re.I))
                   for x in v):
            continue
        conv = pd.to_numeric(s, errors="coerce")
        if conv.notna().sum() == pieni.sum():
            df[c] = conv
    return df


# ============================================================================ ingresso
def normalizza_tabella(df_grezzo, nome="", misure=True):
    """Riordina un foglio letto così com'è (anche con ``header=None``) in una tabella con una riga per
    scheda e una sola riga di intestazione. Ritorna ``(df, rapporto)``: ``rapporto`` è la lista delle
    trasformazioni fatte, ognuna ``{"codice", "messaggio"}``; vuota se la tabella era già in ordine,
    e in quel caso ``df`` è lo stesso oggetto ricevuto.

    Riconosce: intestazione non in prima riga (titoli, loghi, righe vuote sopra), intestazione su più
    righe (gruppi su celle unite: «Quote» sopra «sup»/«inf» -> «Quote sup»; riga delle unità), righe e
    colonne vuote, intestazioni ripetute (salti pagina), righe di totale e note in fondo, schede
    trasposte (un'unità per colonna), esportazioni campo/valore (in tre colonne o in blocchi
    etichetta/valore), matrici dei rapporti (-> US, Rapporto, US correlata), più tabelle nello stesso
    foglio (si tiene la più grande: per averle tutte ``normalizza_foglio``), misure con l'unità e
    virgola decimale (in metri se ``misure``). ``nome`` è il nome del foglio (per i messaggi
    dell'importazione: le note non lo ripetono)."""
    rapporto = []
    if not isinstance(df_grezzo, pd.DataFrame) or df_grezzo.shape[1] == 0:
        return df_grezzo, rapporto
    G, con_nomi, forte = _griglia(df_grezzo)
    if not G.size:
        return df_grezzo, rapporto
    piene_c = ~pd.isna(G).all(axis=0)
    if not piene_c.all():
        _nota(rapporto, "colonne_vuote", int((~piene_c).sum()))
    A, colonne = G[:, piene_c], np.flatnonzero(piene_c)
    if not A.shape[1]:
        return df_grezzo, rapporto
    blocchi = _schede_a_blocchi(A)
    if blocchi is not None:
        df, ncampi = blocchi
        _nota(rapporto, "scheda_blocchi", len(df), ncampi)
        return _fine(df, rapporto, misure)
    n = (~pd.isna(A)).sum(axis=1)
    tabelle = _blocchi(A, n)
    intero = len(tabelle) == 1
    if not intero:
        nomi = _nomi_tabelle(tabelle)
        k = max(range(len(tabelle)), key=lambda t: (len(tabelle[t][1]), -t))
        _nota(rapporto, "tabelle_multiple", len(tabelle), nomi[k])
        righe = tabelle[k][1]
        B = A[righe]
        tieni = ~pd.isna(B).all(axis=0)
        return _ordina(B[:, tieni], np.array(righe), colonne[tieni], False, df_grezzo, con_nomi, rapporto, misure)
    return _ordina(A, np.arange(A.shape[0]), colonne, forte, df_grezzo, con_nomi, rapporto, misure)


def _fine(df, rapporto, misure):
    if misure:
        df, rapporto = converti_misure(df, rapporto)
    return df.reset_index(drop=True), rapporto


def _ordina(A, righe, colonne, forte, df_grezzo, con_nomi, rapporto, misure):
    """Una tabella (già isolata nel foglio): forma, intestazione, righe da togliere, valori."""
    n = (~pd.isna(A)).sum(axis=1)
    R = [i for i in range(A.shape[0]) if n[i] > 0]
    if not R:
        return pd.DataFrame(), rapporto
    W = A.shape[1]
    inizio_nomi = forte and righe[R[0]] == 0 and con_nomi
    titoli = []
    if W >= 2 and not inizio_nomi:
        for i in R:
            if n[i] == 1 and _e_testo(_pieni(A, i)[0]):
                titoli.append(i)
            else:
                break
    resto = R[len(titoli):]
    if W >= 2 and len(resto) >= 3:
        t = _trasposta(A, resto)
        if t is not None:
            _nota(rapporto, "trasposta", t[1])
            return _fine(t[0], rapporto, misure)
        m = _matrice(A, resto)
        if m is not None:
            df, senza_dir, ignoti = m
            _nota(rapporto, "matrice", len(df))
            if senza_dir:
                _nota(rapporto, "matrice_segni", ", ".join(senza_dir))
            if ignoti:
                _nota(rapporto, "matrice_ignoti", ", ".join(ignoti[:12]))
            return df, rapporto
    if not resto:
        resto = R
    h = R[0] if inizio_nomi else _trova_intestazione(A, resto, n)
    if righe[h] > 0 and not inizio_nomi:
        _nota(rapporto, "intestazione", int(righe[h]) + 1, int(righe[h]))
    # intestazione su più righe
    righe_int = [h]
    nomi = list(A[h])
    dopo = [i for i in R if i > h]
    while len(righe_int) < 3 and dopo:
        c = dopo[0]
        D = A[dopo[1]] if len(dopo) > 1 else None
        if not _continua_intestazione(nomi, A[c], D):
            break
        nomi = _unisci_intestazione(nomi, A[c])
        righe_int.append(c)
        dopo = dopo[1:]
    nomi = [_pulisci_nome(x) or f"Colonna {int(colonne[j]) + 1}" for j, x in enumerate(nomi)]
    if len(righe_int) > 1:
        esempio = next((x for x in nomi if x and " " in x), next((x for x in nomi if x), ""))
        _nota(rapporto, "intestazione_multipla", len(righe_int), esempio)
    nomi_finali = _unici(nomi)
    if len(righe_int) == 1:
        grezzi = [df_grezzo.columns[c] for c in colonne] if inizio_nomi else list(A[h])
        if any(g != b if isinstance(g, str) else _vuoto(g) for g, b in zip(grezzi, nomi_finali)):
            _nota(rapporto, "nomi_colonne")
    D = list(range(righe_int[-1] + 1, A.shape[0]))
    vuote, ripetute, totali, piede = _righe_da_togliere(A, D, n, righe_int, [_pieni(A, t)[0] for t in titoli])
    if vuote:
        _nota(rapporto, "righe_vuote", len(vuote))
    if ripetute:
        _nota(rapporto, "intestazioni_ripetute", len(ripetute))
    if totali:
        _nota(rapporto, "totali", len(totali))
    if piede:
        _nota(rapporto, "piede", len(piede))
    via = set(vuote) | set(ripetute) | set(totali) | set(piede)
    tieni = [i for i in D if i not in via]
    if inizio_nomi and len(righe_int) == 1:
        # la tabella è quella ricevuta: si conservano i tipi delle colonne
        df = df_grezzo.iloc[[int(righe[i]) - 1 for i in tieni], list(colonne)]
        # un nome non testuale (2019) che si scrive uguale resta com'è; gli altri cambiano solo se serve
        nuovi = [a if str(a) == b else b for a, b in zip(df.columns, nomi_finali)]
        if any(str(a) != b for a, b in zip(df.columns, nomi_finali)):
            df = df.set_axis(nuovi, axis=1)
        if via:
            df = _tipi(df.copy())
    else:
        df = _tipi(pd.DataFrame(A[tieni], columns=nomi_finali))
    kv = _campo_valore(df)
    if kv is not None:
        df, nu, ncampi = kv
        _nota(rapporto, "campo_valore", nu, ncampi)
    df, rapporto = _fine(df, rapporto, misure)
    if not rapporto and inizio_nomi and len(righe_int) == 1:
        return df_grezzo, rapporto           # era già in ordine: lo stesso oggetto, senza note
    return df, rapporto


def normalizza_foglio(df_grezzo, nome="", misure=True):
    """Come ``normalizza_tabella`` ma tiene tutte le tabelle di un foglio che ne contiene più d'una.
    Ritorna {nome: (df, rapporto)}: con una sola tabella la chiave è ``nome``; con più tabelle
    «nome · titolo» (o «nome · Tabella N» se la tabella non ha titolo)."""
    parti = dividi_tabelle(df_grezzo) if isinstance(df_grezzo, pd.DataFrame) and df_grezzo.shape[1] else {}
    if len(parti) <= 1:
        return {nome: normalizza_tabella(df_grezzo, nome, misure)}
    out = {}
    for titolo, blocco in parti.items():
        chiave = f"{nome} · {titolo}" if nome else titolo
        out[chiave] = normalizza_tabella(blocco, chiave, misure)
    return out
