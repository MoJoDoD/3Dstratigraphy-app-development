# -*- coding: utf-8 -*-
"""
Foto e disegni collegati alle unità in automatico.

Molti archivi di scavo hanno cartelle di immagini senza una tabella che dica a quale unità
appartiene ciascun file: il numero dell'unità sta nel nome del file («US1005_N.jpg»,
«Ctx_1005 (2).png») o della cartella («photographs/Context 1005/IMG_2231.JPG»). Altri hanno
un registro delle foto o dei disegni (numero dello scatto, unità, descrizione).

    tipo, punteggio, motivo = tipo_immagine("sezioni/US1005.tif")     # foto, disegno o scansione
    r = documenti_per_unita(voci, unita_note={1005, 1006})           # dai nomi dei file
    r = collega_da_registro(registro, voci)                          # da un registro foto/disegni
    tabella = come_tabella(r)                                        # tabella «Documentazione»

Le ``voci`` sono dizionari con almeno ``percorso`` (assoluto), ``relativo`` (rispetto alla
cartella dell'archivio, con le cartelle) e ``categoria`` ("immagine", "documento", ...).
Il risultato è ``{"collegamenti": {unità: [{percorso, tipo, motivo}]}, "non_collegati": [...],
"note": [...]}``.
"""
import os
import re

import numpy as np

EST_IMMAGINI = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".tif", ".tiff", ".bmp"}
EST_SCANSIONE = {".tif", ".tiff", ".bmp"}
TIPI = ("foto", "disegno", "scansione")
LATO_MINIATURA = 128
PIXEL_MASSIMI = 60_000_000        # oltre, un'immagine che non si può ridurre in lettura (TIFF, PNG) non si apre

# ---------------------------------------------------------------- parole nei nomi di file e cartelle
PAROLE_FOTO = {
    "photo", "photos", "photograph", "photographs", "photographie", "photographies", "foto", "fotos",
    "fotografia", "fotografie", "fotografias", "img", "image", "images", "dsc", "dscn", "dscf", "pict", "pxl",
    "imag", "bild", "bilder", "picture", "pictures", "scatto", "scatti", "aufnahme", "aufnahmen", "photogrammetry",
}
PAROLE_DISEGNO = {
    "section", "sections", "sezione", "sezioni", "sez", "schnitt", "schnitte", "coupe", "coupes", "profil",
    "profile", "profiles", "profilo", "profili", "plan", "plans", "pianta", "piante", "planum", "plana",
    "drawing", "drawings", "dwg", "disegno", "disegni", "rilievo", "rilievi", "prospetto", "prospetti",
    "zeichnung", "zeichnungen", "dessin", "dessins", "plano", "planos", "elevation", "elevations", "sketch",
    "schizzo", "schizzi",
}
PAROLE_SCANSIONE = {
    "scan", "scans", "scanned", "scansione", "scansioni", "scansionato", "scansionata", "scansionati",
    "scansionate", "tavola", "tavole", "tav", "sheet", "sheets", "foglio", "fogli", "digitalizzato",
    "digitalizzati", "digitalizzazione", "scansiona",
}
_PAROLE = {"foto": PAROLE_FOTO, "disegno": PAROLE_DISEGNO, "scansione": PAROLE_SCANSIONE}
_RX_CONTATORE = re.compile(r"^(?:p\d{7}|dsc[nf]?\d+|img\d+|pxl\d+)$")      # P1010023, DSC00123 come parola unica

# marche di soli scanner (le altre marche con dati EXIF sono fotocamere o telefoni)
_SCANNER = ("epson", "fujitsu", "plustek", "brother", "xerox", "avision", "microtek", "mustek", "visioneer",
            "umax", "kyocera", "canoscan", "scansnap", "hewlett", "hp scan", "contex", "colortrac", "rowe")


def _parole(testo):
    return [w for w in re.split(r"[^a-zà-ÿ0-9]+", testo.lower()) if w]


def _indizi_nome(nome):
    """Punteggi dal nome: le parole del file valgono più di quelle delle cartelle."""
    parti = [p for p in re.split(r"[\\/]+", nome) if p]
    punti = dict.fromkeys(TIPI, 0.0)
    motivi = []
    for i, parte in enumerate(reversed(parti)):
        peso = 1.0 if i == 0 else 0.7
        dove = "nel nome del file" if i == 0 else "nel nome della cartella"
        stem = os.path.splitext(parte)[0] if i == 0 else parte
        parole = _parole(stem)
        for tipo, insieme in _PAROLE.items():
            trovata = next((w for w in parole if w in insieme or (tipo == "foto" and _RX_CONTATORE.match(w))), None)
            if trovata and punti[tipo] < peso:
                punti[tipo] = peso
                motivi.append(f"«{trovata}» {dove}")
    return punti, motivi


def tipo_da_nome(nome):
    """Tipo suggerito dalle sole parole del nome (senza aprire il file), o None."""
    punti, _ = _indizi_nome(nome)
    migliore = max(punti, key=punti.get)
    return migliore if punti[migliore] > 0 else None


def _exif(im):
    """('foto' | 'scansione' | None, descrizione) dai dati EXIF."""
    try:
        ex = im.getexif()
    except Exception:
        return None, ""
    if not ex:
        return None, ""
    marca = str(ex.get(271, "") or "").strip("\x00 ")
    modello = str(ex.get(272, "") or "").strip("\x00 ")
    programma = str(ex.get(305, "") or "").strip("\x00 ")
    try:
        sotto = ex.get_ifd(0x8769)
    except Exception:
        sotto = {}
    esposizione = any(k in sotto for k in (33434, 33437, 34855, 37386))     # tempo, diaframma, ISO, focale
    chi = " ".join(x for x in (marca, modello) if x)
    testo = f"{chi} {programma}".lower()
    if "scan" in testo or any(s in testo for s in _SCANNER):
        return "scansione", f"dati EXIF di uno scanner ({chi or programma})"
    if esposizione:
        return "foto", f"dati EXIF di scatto ({chi})" if chi else "dati EXIF di scatto (tempo, diaframma)"
    if chi:
        return "foto", f"dati EXIF della fotocamera ({chi})"
    return None, ""


def _rumore(fondo):
    """Variabilità del fondo, senza i bordi sfumati delle linee."""
    if len(fondo) <= 10:
        return 0.0
    vicino = fondo[np.abs(fondo - np.median(fondo)) < 15]
    return float(vicino.std()) if len(vicino) > 10 else 0.0


def _statistiche(im):
    """Misure sulla miniatura: colori, fondo chiaro, linee scure."""
    im.thumbnail((LATO_MINIATURA, LATO_MINIATURA))
    grigia_nativa = im.mode in ("1", "L", "LA", "I", "I;16", "F")
    a = np.asarray(im.convert("RGB"), dtype=np.float32).reshape(-1, 3)
    lum = a @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    croma = a.max(1) - a.min(1)
    q = (a // 32).astype(np.int32)
    codici = q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2]
    conta = np.sort(np.bincount(codici, minlength=512))[::-1]
    chiari = lum > 190
    fondo = lum[chiari]
    return {
        "grigia": grigia_nativa or float(croma.mean()) < 10,
        "croma": float(croma.mean()),
        "dominanza": float(conta[:5].sum() / max(len(codici), 1)),     # quota dei 5 colori più frequenti
        "colori": int((conta > 0).sum()),
        "chiaro": float(chiari.mean()),
        "scuro": float((lum < 100).mean()),
        "fondo": float(np.median(fondo)) if len(fondo) else 0.0,
        "fondo_croma": float(np.median(croma[chiari])) if chiari.any() else 0.0,
        "fondo_rumore": _rumore(fondo),
    }


def tipo_immagine(path, nome=None):
    """(tipo, punteggio, motivo) di un'immagine: tipo è "foto", "disegno" o "scansione".

    Indizi: le parole del nome del file e delle cartelle (``nome``, se non dato le ultime tre parti del
    percorso), i dati EXIF della fotocamera o dello scanner, e l'aspetto dell'immagine su una miniatura
    (poche tinte o grigi su fondo chiaro con linee sottili = disegno; fondo color carta, foglio grande o
    TIFF = scansione). Le immagini molto grandi che non si possono ridurre in lettura non si aprono."""
    if nome is None:
        nome = os.sep.join(re.split(r"[\\/]+", str(path))[-3:])
    punti, motivi = _indizi_nome(nome)
    ext = os.path.splitext(str(path))[1].lower()
    if ext == ".pdf":
        punti["scansione"] += 1.0
        motivi.append("file PDF")
    elif os.path.isfile(str(path)):
        try:
            from PIL import Image
            with Image.open(path) as im:
                larghezza, altezza = im.size
                dpi = im.info.get("dpi") or (0, 0)
                try:
                    dpi = float(dpi[0] or 0)
                except Exception:
                    dpi = 0.0
                da_exif, perche = _exif(im)
                if da_exif:
                    punti[da_exif] += 3.0 if da_exif == "foto" else 2.0
                    motivi.append(perche)
                grande = max(larghezza, altezza) >= 3000 or (dpi >= 200 and da_exif != "foto")
                if im.format == "JPEG":
                    im.draft("RGB", (LATO_MINIATURA * 2, LATO_MINIATURA * 2))      # decodifica già ridotta
                if larghezza * altezza > PIXEL_MASSIMI and im.format != "JPEG":
                    st = None
                    if im.mode in ("1", "L"):
                        punti["scansione"] += 1.5
                        motivi.append("immagine enorme in bianco e nero o grigi")
                    else:
                        punti["scansione"] += 1.0
                        motivi.append("immagine enorme")
                else:
                    st = _statistiche(im)
                cartaceo = ext in EST_SCANSIONE or grande or im.mode == "1"
        except Exception:
            st, cartaceo, grande = None, False, False
            motivi.append("immagine non leggibile")
        if st is not None:
            _indizi_aspetto(st, punti, motivi, cartaceo, ext, grande)
    totale = sum(punti.values())
    if totale <= 0:
        tipo = "scansione" if ext in EST_SCANSIONE or ext == ".pdf" else "foto"
        return tipo, 0.3, "nessun indizio chiaro: deciso dal formato del file"
    tipo = max(TIPI, key=lambda k: punti[k])
    secondo = sorted(punti.values())[-2]
    if punti[tipo] - secondo < 0.5 and secondo > 0:
        altro = max((k for k in TIPI if k != tipo), key=lambda k: punti[k])
        motivi.append(f"incerto tra {tipo} e {altro}")
    return tipo, round(punti[tipo] / (totale + 1.0), 2), "; ".join(motivi)


def _indizi_aspetto(st, punti, motivi, cartaceo, ext, grande):
    poche_tinte = st["dominanza"] > 0.85 or st["colori"] <= 12
    fondo_chiaro = st["chiaro"] > 0.5
    linee = st["scuro"] < 0.35
    carta = st["fondo"] < 248 or st["fondo_croma"] > 6 or st["fondo_rumore"] > 3
    if (st["grigia"] or poche_tinte) and fondo_chiaro and linee:
        if carta and (cartaceo or st["fondo_rumore"] > 3):
            punti["scansione"] += 2.0
            motivi.append("foglio chiaro color carta con segni scuri" + (", grande o in TIFF" if cartaceo else ""))
        elif carta or cartaceo:
            punti["disegno"] += 1.2
            punti["scansione"] += 1.0
            motivi.append("linee scure su fondo chiaro" + (" (formato da scansione)" if cartaceo else ""))
        else:
            punti["disegno"] += 2.0
            motivi.append("linee sottili su fondo bianco, poche tinte")
    elif st["grigia"]:
        # in bianco e nero ma senza fondo bianco: stampa scansionata o foto in bianco e nero
        if cartaceo:
            punti["scansione"] += 1.5
        else:
            punti["scansione"] += 0.8
            punti["foto"] += 0.8
        motivi.append("immagine in toni di grigio")
    elif fondo_chiaro and linee and st["dominanza"] > 0.7:
        punti["disegno"] += 1.5
        if carta and cartaceo:
            punti["scansione"] += 1.0
        motivi.append("disegno a colori su fondo chiaro")
    else:
        punti["foto"] += 2.0
        motivi.append("immagine a colori con molte tinte")


# ---------------------------------------------------------------- numeri delle unità nei nomi
_SIGLE = ("unità stratigrafica", "unita stratigrafica", "stratigraphic unit", "contexts", "context", "contesto",
          "contesti", "intervention", "befund", "befunde", "stratum", "strato", "layer", "deposit", "usm", "usr",
          "sus", "us", "su", "ue", "ctx", "cxt", "bef", "cut", "fill", "unità", "unita", "unit")
_SIGLA = "(?:" + "|".join(re.escape(s).replace(r"\ ", r"\s+") for s in _SIGLE) + ")"
_NUM = r"(?:\s*(?:n\.?|nr\.?|no\.?|n°|nº|#))?[\s._\-:#°]*0*(\d{1,7})(?!\d)"
RX_SIGLA = re.compile(r"(?<![a-zà-ÿ])" + _SIGLA + _NUM, re.I)
_SEGUITO = re.compile(r"(\s*(?:[-–_,+&;]|\s(?:e|and|und|et|y|a|to|bis|al)\s)\s*)(?:" + _SIGLA + r"[\s._\-:#°]*)?0*(\d{1,7})(?!\d)",
                      re.I)
# numeri che non sono unità: date, scale, risoluzioni, contatori della fotocamera, numeri di foto o tavole
_RUMORE = [
    (re.compile(r"(?<!\d)(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])[_\-T ]?(?:[01]\d|2[0-3])[0-5]\d[0-5]\d"
                r"(?!\d)"), "data e ora"),
    (re.compile(r"(?<!\d)(?:19|20)\d{2}[-_.]?(?:0[1-9]|1[0-2])[-_.]?(?:0[1-9]|[12]\d|3[01])(?!\d)"), "data"),
    (re.compile(r"(?<!\d)\d{1,2}[-_.]\d{1,2}[-_.](?:19|20)?\d{2}(?!\d)"), "data"),
    (re.compile(r"(?<!\d)1\s*[-_:]\s*(?:1|2|5|10|20|25|50|100|200|250|500|1000|2000|2500|5000|10000)(?!\d)"), "scala"),
    (re.compile(r"\d{2,5}\s*[x×]\s*\d{2,5}"), "risoluzione"),
    (re.compile(r"\d+\s*(?:dpi|ppi|px|mp|mpx|mm|cm|kb|mb)(?![a-z])", re.I), "misura"),
    (re.compile(r"(?<![a-z])(?:img|dsc[nf]?|pict|pxl|imag|mvi|gopr|dji|wp|cimg|sam|pano|vid|dcp|dscim)[\s_\-]?\d+",
                re.I), "contatore della fotocamera"),
    (re.compile(r"(?<![a-z0-9])p\d{7}(?!\d)", re.I), "contatore della fotocamera"),
    (re.compile(r"\(\s*\d{1,2}\s*\)|(?:copia|copy|kopie)\s*\d*", re.I), "copia"),
    (re.compile(r"<\s*\d+\s*>"), "numero di campione"),          # <2747>: campione, all'inglese
    (re.compile(r"(?<![a-zà-ÿ])(?:photos?|photographs?|foto|fotografia|view|vista|fig|figure|figura|tav|tavola|"
                r"tavole|scan|scansione|sheet|foglio|frame|neg|film|roll|rullino|dia|slide|plate|tab|pl|plan|"
                r"pianta|planum|section|sezione|sez|sect|schnitt|profil|profile|profilo|coupe|drawing|dwg|"
                r"disegno|dis|ril|rilievo|sk|nr|no|num|n|trench|tr|area|saggio|sag|settore|sett|sector|"
                r"sondaggio|sond|sondage|quadrato|quad|q|grid|box|cassa|fase|phase|period|periodo|site|sito|"
                r"campagna|season|day|giorno|ver|rev|v|r|vol|page|pag|p)"
                r"\s*[._\-#°:]*\s*\d+", re.I), "numero di foto o disegno"),
]
_RX_NUMERO = re.compile(r"(?<!\d)0*(\d{1,7})(?!\d)")
_RX_ANNO = re.compile(r"^(?:19[5-9]\d|20[0-4]\d)$")


def _maschera(testo, inizio, fine):
    return testo[:inizio] + " " * (fine - inizio) + testo[fine:]


def _con_sigla(testo, unita_note):
    """[(numeri, testo trovato, avvisi)] per i numeri preceduti da una sigla (US, Context, Befund...)."""
    out = []
    for m in RX_SIGLA.finditer(testo):
        primo = int(m.group(1))
        nums, avvisi = [primo], []
        pos, fine = m.end(), m.end()
        while True:
            s = _SEGUITO.match(testo, pos)
            if not s:
                break
            n = int(s.group(2))
            sep = s.group(1).strip().lower()
            sigla_propria = bool(re.search(r"[a-zà-ÿ]", s.group(0)[len(s.group(1)):]))
            stesso = len(str(n)) == len(str(primo))
            noto = unita_note is not None and n in unita_note
            if not (sigla_propria or stesso or noto):
                break                                 # «US1005_2»: un numero di scatto, non un'unità
            intervallo = sep in ("-", "–", "a", "to", "bis", "al") and n > nums[-1] and not sigla_propria
            if intervallo and n - nums[-1] > 1:
                mezzo = list(range(nums[-1] + 1, n))
                if unita_note is not None and len(mezzo) <= 50 and all(x in unita_note for x in mezzo):
                    nums.extend(mezzo)
                else:
                    avvisi.append(f"intervallo {nums[-1]}-{n} non espanso (non tutte le unità sono note)")
            nums.append(n)
            pos = fine = s.end()
        out.append((nums, testo[m.start():fine].strip(" _-."), avvisi, (m.start(), fine)))
    return out


def _numeri_parte(parte, unita_note, cartella=False):
    """Numeri delle unità in una parte del percorso: (con sigla, senza sigla, avvisi, scartati noti)."""
    testo = parte
    sigla, nudi, avvisi, scartati = [], [], [], []
    for nums, trovato, av, (a, b) in _con_sigla(testo, unita_note):
        sigla.append((nums, trovato))
        avvisi += av
        testo = _maschera(testo, a, b)
    for rx, perche in _RUMORE:
        for m in rx.finditer(testo):
            for x in _RX_NUMERO.findall(m.group(0)):
                if unita_note is not None and int(x) in unita_note:
                    scartati.append((int(x), perche))
            testo = _maschera(testo, m.start(), m.end())
    if unita_note is None or sigla:          # con una sigla i numeri senza sigla della stessa parte non contano
        return sigla, nudi, avvisi, scartati
    trovati = [(int(m.group(1)), m.start(), m.end()) for m in _RX_NUMERO.finditer(testo)]
    validi = []
    for i, (n, a, b) in enumerate(trovati):
        if n < 10 or n not in unita_note:
            continue
        validi.append((n, a, b))
    # «1005-1007»: intervallo, se tutte le unità di mezzo sono note
    extra = []
    for (n1, _, b1), (n2, a2, _) in zip(validi, validi[1:]):
        if re.fullmatch(r"\s*[-–]\s*", testo[b1:a2]) and 1 < n2 - n1 <= 50:
            mezzo = list(range(n1 + 1, n2))
            if all(x in unita_note for x in mezzo):
                extra += mezzo
            else:
                avvisi.append(f"intervallo {n1}-{n2} non espanso (non tutte le unità sono note)")
    numeri = [n for n, _, _ in validi] + extra
    anni = [n for n in numeri if _RX_ANNO.match(str(n))]
    if anni and (cartella or len(set(numeri) - set(anni))):      # una cartella «2019» è un anno
        for n in anni:
            scartati.append((n, "anno"))
        numeri = [n for n in numeri if n not in anni]
    elif anni:
        avvisi.append(f"{anni[0]} potrebbe essere un anno")
    if numeri:
        nudi.append((list(dict.fromkeys(numeri)), " ".join(str(n) for n in dict.fromkeys(numeri))))
    return sigla, nudi, avvisi, scartati


def unita_dal_percorso(relativo, unita_note=None, livelli=3, testo_libero=False):
    """(numeri delle unità, motivo, scartati) ricavati dal nome del file e delle cartelle.

    Precedenza: numeri con sigla nel nome del file, con sigla nella cartella più vicina, poi i numeri
    senza sigla (solo se sono unità note, mai senza ``unita_note``). Date, anni, scale, risoluzioni,
    contatori della fotocamera (IMG_2231, DSC00123, P1010023) e numeri di foto o tavole non contano."""
    parti = [str(relativo)] if testo_libero else [p for p in re.split(r"[\\/]+", str(relativo)) if p]
    if not parti:
        return [], "", []
    if not testo_libero:
        parti[-1] = os.path.splitext(parti[-1])[0]
    analisi = []
    for i, parte in enumerate(reversed(parti[-(livelli + 1):])):
        analisi.append((i, parte, *_numeri_parte(parte, unita_note, cartella=i > 0)))
    scartati = [s for a in analisi for s in a[5]]
    scelta, dove, quale, avvisi, nota = None, None, None, [], ""
    for genere in ("sigla", "nudi"):
        for i, parte, sigla, nudi, av, _ in analisi:
            gruppi = sigla if genere == "sigla" else nudi
            if not gruppi:
                continue
            numeri = [n for nums, _ in gruppi for n in nums]
            if unita_note is not None and genere == "sigla":
                ignoti = [n for n in numeri if n not in unita_note]
                numeri = [n for n in numeri if n in unita_note]
                scartati += [(n, "unità non presente nel progetto") for n in ignoti]
                if not numeri:
                    continue
            scelta = list(dict.fromkeys(numeri))
            dove = "nel nome del file" if i == 0 else "nel nome della cartella"
            quale = ", ".join(f"«{t}»" for _, t in gruppi)
            nota = " (numero senza sigla, unità del progetto)" if genere == "nudi" else ""
            avvisi = list(av)
            break
        if scelta:
            break
    if not scelta:
        return [], "", scartati
    # altri numeri diversi altrove nel percorso: si segnala l'ambiguità
    altri = sorted({n for _, _, sigla, nudi, _, _ in analisi for nums, _ in sigla + nudi for n in nums
                    if unita_note is None or n in unita_note} - set(scelta))
    if altri:
        avvisi.append("ambiguo: nel percorso anche " + ", ".join(str(n) for n in altri))
    motivo = f"{quale} {dove}{nota}"
    if avvisi:
        motivo += "; " + "; ".join(avvisi)
    return scelta, motivo, scartati


# ---------------------------------------------------------------- collegamenti
def _ext(v):
    return os.path.splitext(str(v.get("relativo") or v.get("percorso") or ""))[1].lower()


def _immagine(v):
    return v.get("categoria") == "immagine" or _ext(v) in EST_IMMAGINI


def _tipo_voce(v, cache):
    if v.get("tipo") in TIPI:
        return v["tipo"], v.get("motivo_tipo", "")
    p = v.get("percorso")
    if p not in cache:
        rel = v.get("relativo") or p
        cache[p] = tipo_immagine(p, nome=os.sep.join(re.split(r"[\\/]+", str(rel))[-3:]))
    t, _, m = cache[p]
    return t, m


def _aggiungi(coll, unita, percorso, tipo, motivo):
    lista = coll.setdefault(int(unita), [])
    if not any(e["percorso"] == percorso for e in lista):
        lista.append({"percorso": percorso, "tipo": tipo, "motivo": motivo})


def documenti_per_unita(voci, unita_note=None):
    """Collega immagini (e PDF con il numero nel nome) alle unità dai nomi di file e cartelle.

    ``unita_note``: numeri delle unità del progetto. Con l'elenco si accettano anche i numeri senza
    sigla («1005-sez.tif») e si scartano quelli che non sono unità; senza, valgono solo i numeri con
    una sigla (US, SU, UE, USM, Context, Ctx, Befund, Layer, Cut, Fill...)."""
    note_set = None if unita_note is None else {int(u) for u in unita_note}
    coll, non_coll, cache = {}, [], {}
    n_imm = n_cartella = n_incerti = n_pdf = 0
    ignoti, scartati_noti = set(), 0
    for v in voci:
        ext = _ext(v)
        imm = _immagine(v)
        if not imm and ext != ".pdf":
            continue
        if imm:
            n_imm += 1
        numeri, motivo, scartati = unita_dal_percorso(v.get("relativo") or v.get("percorso"), note_set)
        ignoti |= {n for n, perche in scartati if perche == "unità non presente nel progetto"}
        if not numeri:
            if imm:
                non_coll.append(v.get("percorso"))
                if any(perche != "unità non presente nel progetto" for _, perche in scartati):
                    scartati_noti += 1
            continue
        if "cartella" in motivo.split(";")[0]:
            n_cartella += 1
        if "ambiguo" in motivo or "potrebbe" in motivo or "non espanso" in motivo:
            n_incerti += 1
        if imm:
            tipo, motivo_tipo = _tipo_voce(v, cache)
        else:
            tipo, motivo_tipo = "scansione", "file PDF"
            n_pdf += 1
        testo = f"{motivo} — {tipo}: {motivo_tipo}" if motivo_tipo else motivo
        for n in numeri:
            _aggiungi(coll, n, v.get("percorso"), tipo, testo)
    collegate = n_imm - len(non_coll)
    note = []
    if n_imm:
        note.append(f"Immagini collegate alle unità dai nomi: {collegate} su {n_imm}, "
                    f"per {len(coll)} unità")
    if n_cartella:
        note.append(f"{n_cartella} file collegati dal nome della cartella")
    if n_pdf:
        note.append(f"{n_pdf} PDF collegati alle unità dal nome")
    if n_incerti:
        note.append(f"{n_incerti} collegamenti incerti (il motivo spiega perché)")
    if ignoti:
        es = ", ".join(str(n) for n in sorted(ignoti)[:5])
        note.append(f"{len(ignoti)} numeri con sigla non sono unità del progetto (es. {es})")
    if scartati_noti:
        note.append(f"{scartati_noti} file con numeri di unità scartati perché sembrano date, scale "
                    f"o numeri di foto")
    if note_set is None and n_imm:
        note.append("Senza l'elenco delle unità si collegano solo i nomi con una sigla (US, SU, Context…)")
    return {"collegamenti": dict(sorted(coll.items())), "non_collegati": non_coll, "note": note}


# ---------------------------------------------------------------- registri di foto e disegni
def _norm_col(c):
    return re.sub(r"[^a-z0-9à-ÿ/]+", " ", str(c).lower()).strip()


_COL_FILE = ["file", "nome file", "file name", "filename", "nomefile", "percorso", "percorso file", "path",
             "file path", "immagine", "image", "file immagine", "image file", "datei", "dateiname", "fichier"]
_COL_NUMERO = ["view number", "photo number", "photograph number", "numero foto", "n foto", "nr foto",
               "num foto", "foto n", "foto nr", "photo no", "photo id", "view no", "numero scatto", "n scatto",
               "scatto", "section number", "section no", "numero sezione", "n sezione", "plan number", "plan no",
               "numero pianta", "drawing number", "drawing no", "numero disegno", "n disegno", "numero tavola",
               "n tavola", "sheet number", "sheet no", "foto", "photo", "view", "sezione", "section", "plan",
               "pianta", "disegno", "drawing", "tavola", "sheet", "bildnummer", "bild nr", "fotonummer"]
_COL_GENERICHE = ["numero", "number", "nr", "n", "no", "id"]
_COL_UNITA = ["us/usm", "us", "usm", "unità", "unita", "unità stratigrafica", "unita stratigrafica", "context",
              "context number", "context no", "contexts", "intervention", "contesto", "befund", "befund nr", "su",
              "ue", "unit", "stratigraphic unit", "layer", "strato", "cxt", "ctx"]
_COL_DESCR = ["description", "descrizione", "soggetto", "subject", "didascalia", "caption", "note", "notes",
              "beschreibung", "oggetto"]


def _trova_colonna(colonne, preferite, escluse=()):
    norm = {c: _norm_col(c) for c in colonne if c not in escluse}
    for p in preferite:
        for c, n in norm.items():
            if n == p:
                return c
    return None


def _colonna_numero(colonne, escluse):
    c = _trova_colonna(colonne, _COL_NUMERO, escluse)
    if c:
        return c
    for c in colonne:
        n = _norm_col(c)
        if c in escluse or any(w in n for w in ("film", "archive", "dial", "person", "roll")):
            continue
        if re.search(r"photo|foto|view|scatt|section|sezion|plan|piant|drawing|disegn|tavol|sheet|bild", n) and \
                re.search(r"number|numero|\bn\b|\bnr\b|\bno\b|\bid\b|num", n):
            return c
    return _trova_colonna(colonne, _COL_GENERICHE, escluse)


def _interi(v):
    """Numeri interi di una cella: 1005, 1005.0, "US 1005", "1005, 1006"."""
    if v is None:
        return []
    if isinstance(v, (int, np.integer)):
        return [int(v)]
    if isinstance(v, (float, np.floating)):
        return [] if np.isnan(v) else [int(v)] if float(v).is_integer() else []
    s = str(v).strip()
    if re.fullmatch(r"\d+\.0+", s):
        s = s.split(".")[0]
    return [int(x) for x in re.findall(r"(?<![\d.])0*(\d{1,7})(?![\d.]\d)", s)]


_RX_STEM_NUMERO = re.compile(
    r"^(?:(?:photos?|photograph|foto|view|vista|fig|scan|scansione|section|sezione|sez|sect|plan|pianta|"
    r"drawing|dwg|disegno|dis|tav|tavola|sheet|foglio|bild|s|p|f|v|d)\s*[._\-#]*\s*(?:n[.°]?\s*|nr\.?\s*|no\.?\s*)?)?"
    r"0*(\d{1,7})\s*[a-z]?$", re.I)
_RX_NUMERO_DOC = re.compile(
    r"(?<![a-z])(?:photos?|photograph|foto|view|vista|scan|section|sezione|sez|sect|plan|pianta|drawing|dwg|"
    r"disegno|tav|tavola|sheet|foglio|bild)\s*[._\-#]*\s*(?:n[.°]?\s*|nr\.?\s*|no\.?\s*)?0*(\d{1,7})(?!\d)", re.I)
_RX_INIZIALE = re.compile(r"^0*(\d{1,7})(?=[\s_\-.]+[a-z])", re.I)


def _numero_documento(stem):
    """(numero della foto o del disegno nel nome del file, come è stato trovato) o (None, None)."""
    s = re.sub(r"\s*(?:\(\s*\d+\s*\)|[-_ ]+(?:copia|copy|kopie)(?:\s*\d+)?)\s*$", "", stem.strip(), flags=re.I)
    m = _RX_STEM_NUMERO.match(s)
    if m:
        return int(m.group(1)), "esatto"
    if RX_SIGLA.search(s):
        s = RX_SIGLA.sub(" ", s)
    m = _RX_NUMERO_DOC.search(s)
    if m:
        return int(m.group(1)), "con sigla"
    m = _RX_INIZIALE.match(s)
    if m:
        return int(m.group(1)), "iniziale"
    return None, None


def _genere_registro(*nomi):
    testo = " ".join(_norm_col(n) for n in nomi if n)
    if re.search(r"section|sezion|plan|piant|drawing|disegn|tavol|sheet|schnitt|profil", testo):
        return "disegno"
    if re.search(r"photo|foto|view|scatt|bild", testo):
        return "foto"
    return None


def collega_da_registro(registro_df, voci, unita_note=None):
    """Collega le immagini alle unità con un registro delle foto o dei disegni.

    Le righe del registro si abbinano ai file per nome («Photo 12.jpg» citato nella colonna del file) o
    per numero (numero dello scatto 1234 ↔ «1234.jpg», «Photo 1234.JPG», «1234a.jpg»); l'unità viene
    dalla colonna delle unità (US, Context, Intervention...). Se la riga non ha l'unità, la si cerca
    nella descrizione (numeri con sigla, o unità note se c'è ``unita_note``). Registri «lunghi» (una
    riga per coppia scatto-unità) vanno bene."""
    note = []
    if registro_df is None or not len(registro_df):
        return {"collegamenti": {}, "non_collegati": [v.get("percorso") for v in voci if _immagine(v)],
                "note": ["Il registro è vuoto"]}
    colonne = list(registro_df.columns)
    c_file = _trova_colonna(colonne, _COL_FILE)
    c_unita = _trova_colonna(colonne, _COL_UNITA, {c_file})
    c_num = _colonna_numero(colonne, {c_file, c_unita})
    c_descr = _trova_colonna(colonne, _COL_DESCR, {c_file, c_unita, c_num})
    note_set = None if unita_note is None else {int(u) for u in unita_note}
    if not c_unita and not c_descr:
        note.append("Nel registro non c'è una colonna con le unità (US, Context…)")
    if not c_file and not c_num:
        note.append("Nel registro non c'è una colonna con il nome del file o il numero della foto")
    if note:
        return {"collegamenti": {}, "non_collegati": [v.get("percorso") for v in voci if _immagine(v)],
                "note": note}
    genere = _genere_registro(c_num, c_file)
    note.append("Registro: " + ", ".join(f"{k} «{c}»" for k, c in
                                        (("file", c_file), ("numero", c_num), ("unità", c_unita),
                                         ("descrizione", c_descr)) if c))

    per_nome, per_stem, per_numero = {}, {}, {}
    dalla_descr = 0
    for _, riga in registro_df.iterrows():
        unita = _interi(riga[c_unita]) if c_unita else []
        if note_set is not None:
            unita = [u for u in unita if u in note_set]
        if not unita and c_descr and isinstance(riga[c_descr], str):
            trovate, _, _ = unita_dal_percorso(riga[c_descr], note_set, livelli=0, testo_libero=True)
            if trovate:
                unita = trovate
                dalla_descr += 1
        if c_file and isinstance(riga[c_file], str) and riga[c_file].strip():
            base = re.split(r"[\\/]+", riga[c_file].strip())[-1].lower()
            per_nome.setdefault(base, set()).update(unita)
            per_stem.setdefault(os.path.splitext(base)[0], set()).update(unita)
        if c_num:
            for n in _interi(riga[c_num])[:1]:
                per_numero.setdefault(n, set()).update(unita)

    coll, non_coll, cache = {}, [], {}
    n_imm = n_nome = n_numero = 0
    usati = set()
    for v in voci:
        ext = _ext(v)
        imm = _immagine(v)
        if not imm and ext != ".pdf":
            continue
        n_imm += imm
        rel = str(v.get("relativo") or v.get("percorso") or "")
        base = re.split(r"[\\/]+", rel)[-1]
        stem = os.path.splitext(base)[0]
        unita, motivo = set(), ""
        if base.lower() in per_nome:
            unita, motivo = per_nome[base.lower()], f"«{base}» citato nel registro"
            usati.add(("nome", stem.lower()))
        elif stem.lower() in per_stem:
            unita, motivo = per_stem[stem.lower()], f"«{stem}» citato nel registro (con un'altra estensione)"
            usati.add(("nome", stem.lower()))
        elif per_numero:
            n, come = _numero_documento(stem)
            dal_nome = tipo_da_nome(rel)
            compatibile = genere is None or dal_nome is None or \
                (genere == "foto") == (dal_nome == "foto")
            if n is not None and n in per_numero and compatibile:
                unita = per_numero[n]
                motivo = f"numero {n} del registro nel nome del file" + \
                    (" (numero iniziale del nome)" if come == "iniziale" else "")
                usati.add(("numero", n))
                if unita:
                    n_numero += imm
        if not unita:
            if imm:
                non_coll.append(v.get("percorso"))
            continue
        if motivo.startswith("«"):
            n_nome += imm
        tipo, motivo_tipo = _tipo_voce(v, cache) if imm else ("scansione", "file PDF")
        testo = f"{motivo} — {tipo}: {motivo_tipo}" if motivo_tipo else motivo
        for u in sorted(unita):
            _aggiungi(coll, u, v.get("percorso"), tipo, testo)
    collegate = n_imm - len(non_coll)
    note.append(f"Immagini collegate con il registro: {collegate} su {n_imm} "
                f"({n_nome} per nome del file, {n_numero} per numero), per {len(coll)} unità")
    if dalla_descr:
        note.append(f"{dalla_descr} righe del registro senza unità: unità prese dalla descrizione")
    if c_file:
        senza = sum(1 for k in per_stem if ("nome", k) not in usati)
    else:
        senza = sum(1 for k in per_numero if ("numero", k) not in usati)
    if senza:
        note.append(f"{senza} voci del registro senza un file corrispondente")
    return {"collegamenti": dict(sorted(coll.items())), "non_collegati": non_coll, "note": note}


def unisci(*risultati):
    """Un solo risultato da più collegamenti (nomi dei file, registri): niente doppioni."""
    coll, collegati, tutti, note = {}, set(), [], []
    for r in risultati:
        for u, lista in r.get("collegamenti", {}).items():
            for e in lista:
                _aggiungi(coll, u, e["percorso"], e["tipo"], e["motivo"])
                collegati.add(e["percorso"])
        tutti += r.get("non_collegati", [])
        note += r.get("note", [])
    non_coll = [p for p in dict.fromkeys(tutti) if p not in collegati]
    return {"collegamenti": dict(sorted(coll.items())), "non_collegati": non_coll, "note": note}


def come_tabella(risultato, radice=None):
    """Tabella «Documentazione» (colonne US/USM, Tipo, File, Percorso file, Note) come quella dell'import."""
    import pandas as pd
    righe = []
    for u, lista in risultato.get("collegamenti", {}).items():
        for e in lista:
            p = e["percorso"]
            nome = os.path.relpath(p, radice) if radice and p else os.path.basename(str(p))
            righe.append({"US/USM": int(u), "Tipo": e["tipo"], "File": nome,
                          "Percorso file": os.path.abspath(p) if p else None, "Note": e["motivo"]})
    return pd.DataFrame(righe, columns=["US/USM", "Tipo", "File", "Percorso file", "Note"])
