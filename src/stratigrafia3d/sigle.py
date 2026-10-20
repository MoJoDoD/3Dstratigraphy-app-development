# -*- coding: utf-8 -*-
"""
Sigle delle unità con una lettera di classe: «A1» (sedimento) e «B1» (architettura) sono due unità diverse.

Molti scavi numerano le unità per classe (Ba'ja: A = strati, B = architetture; altri: US/USM con numeri
ripetuti, F/C per fill/cut…). Il motore lavora con numeri interi: quando lo stesso numero compare con classi
diverse, ogni classe riceve un intervallo proprio (A1 → 1001, B1 → 2001) e la sigla originale resta come
etichetta («Sigla») in schede, visualizzatore ed elaborati. Senza numeri ripetuti tra classi nulla cambia:
«US 1005» resta 1005.

La codifica attiva vale nel contesto corrente (``attiva``): così ``importa._intero`` e la lettura dei
rapporti la usano senza cambiare ogni chiamata.
"""
import contextvars
import re
from contextlib import contextmanager
from dataclasses import dataclass, field

# parole che indicano solo «unità» (non una classe): «US 12», «Context 5», «n. 3»
_GENERICHE = {"us", "su", "ue", "se", "sk", "ctx", "cxt", "context", "n", "nr", "no", "num", "unit", "unita",
              "unità", "befund", "bef", "layer", "strato"}
# sigla + numero dentro un testo: «A12», «B 3», «US.A5», «US-B10»; il numero non continua in lettere lunghe
# (una sigla può seguire subito un numero: «G5A36» = locus G5, unità A36)
_TOKEN_RE = re.compile(r"(?<![A-Za-zÀ-ÿ])((?:[A-Za-z]{1,8}\s*[.\-_:#°/]?\s*)?)(\d+)(?:\s*([A-Za-z]{1,2})(?![A-Za-z0-9]))?")
# identificativo da solo: prefisso di lettere e segni, un numero, un breve suffisso (espressioni lineari: nessun
# ritorno all'indietro esponenziale sui testi lunghi)
_SOLO_RE = re.compile(r"([^\d]*)(\d+)\s*([A-Za-z]{0,10})")
_PREFISSO_RE = re.compile(r"[A-Za-zÀ-ÿ\s.\-_:#°/]*")

_ATTIVA = contextvars.ContextVar("codifica_sigle", default=None)


def _classe_da_prefisso(pre):
    """Classe (maiuscola) dal prefisso: «US.A» -> «A», «US » -> None, «GR» -> «GR», «» -> None."""
    if not pre:
        return None
    parti = [p for p in re.split(r"[\s.\-_:#°/]+", pre.strip()) if p]
    parti = [p for p in parti if p.lower() not in _GENERICHE]
    if not parti:
        return None
    p = parti[-1]
    # «USA5» scritto attaccato: «US» generico + classe «A» (solo per le sigle generiche più comuni: «SED»
    # non è «SE» + «D»)
    for g in ("us", "su"):
        if p.lower().startswith(g) and len(p) == len(g) + 1:
            p = p[len(g):]
            break
    return p.upper() if p.isalpha() and len(p) <= 4 else None


def parti(v):
    """(classe, numero, suffisso) di un identificativo scritto da solo («A1», «US.B12», «1005a»);
    None se non è un identificativo semplice."""
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return None, v, None
    if isinstance(v, float):
        return (None, int(v), None) if v == v and float(v).is_integer() else None
    s = str(v).strip()
    if re.fullmatch(r"\d+\.0+", s):
        return None, int(float(s)), None
    if len(s) > 40:
        return None
    m = _SOLO_RE.fullmatch(s)
    if not m or not _PREFISSO_RE.fullmatch(m.group(1)):
        return None
    suf = m.group(3) or None
    return _classe_da_prefisso(m.group(1)), int(m.group(2)), (suf.lower() if suf else None)


@dataclass
class Codifica:
    """Classi con il loro intervallo: {"A": 1000, "B": 2000}; ``passo`` è l'ampiezza di ogni intervallo."""
    classi: dict = field(default_factory=dict)
    passo: int = 1000

    # ------------------------------------------------------------------ costruzione
    @classmethod
    def da_valori(cls, valori):
        """Codifica necessaria per questi identificativi, o None se i numeri non si ripetono tra classi."""
        per_numero = {}
        massimo = 0
        classi = set()
        for v in valori:
            p = parti(v)
            if p is None:
                continue
            c, n, _ = p
            per_numero.setdefault(n, set()).add(c)
            massimo = max(massimo, n)
            if c:
                classi.add(c)
        if not classi or not any(len(cs) > 1 for cs in per_numero.values()):
            return None
        passo = 10 ** max(3, len(str(massimo)))
        return cls({c: passo * (i + 1) for i, c in enumerate(sorted(classi))}, passo)

    @classmethod
    def da_dict(cls, d):
        if not d or not d.get("classi"):
            return None
        return cls(dict(d["classi"]), int(d.get("passo") or 1000))

    def a_dict(self):
        return {"classi": dict(self.classi), "passo": self.passo}

    # ------------------------------------------------------------------ uso
    def codice(self, v):
        """Numero interno per un identificativo: «B1» -> 2001, 12 -> 12, «GR2» (classe sconosciuta) -> None."""
        p = parti(v)
        if p is None:
            return None
        c, n, _ = p
        if c is None:
            return n
        if c not in self.classi:
            return None
        return self.classi[c] + n

    def sigla(self, n):
        """Etichetta di un numero interno: 2001 -> «B1»; i numeri fuori dagli intervalli restano numeri."""
        try:
            n = int(n)
        except (TypeError, ValueError):
            return None
        for c, base in self.classi.items():
            if base < n < base + self.passo:
                return f"{c}{n - base}"
        return None

    def classe(self, n):
        s = self.sigla(n)
        return re.match(r"[A-Z]+", s).group(0) if s else None

    def nel_testo(self, testo):
        """Codici delle unità citate in un testo: «B1, B3; A 12» -> [2001, 2003, 1012]. Le sigle di
        classi sconosciute («GR2», «GS9»: stanze, aree) non diventano unità; i numeri nudi sì."""
        out, ignote = [], []
        for m in _TOKEN_RE.finditer(str(testo)):
            c = _classe_da_prefisso(m.group(1))
            n = int(m.group(2))
            if c is None:
                out.append(n)
            elif c in self.classi:
                out.append(self.classi[c] + n)
            else:
                ignote.append(f"{c}{n}")
        return out, ignote


def attiva():
    """La codifica in uso nel contesto corrente (None: numeri come sono)."""
    return _ATTIVA.get()


@contextmanager
def usa(codifica):
    """``with usa(c): ...``: le letture delle unità nel blocco usano la codifica ``c`` (anche None)."""
    tok = _ATTIVA.set(codifica)
    try:
        yield codifica
    finally:
        _ATTIVA.reset(tok)


def imposta(codifica):
    """Imposta la codifica fino al prossimo ``imposta`` (per le funzioni che non usano ``with``)."""
    return _ATTIVA.set(codifica)


def ripristina(tok):
    _ATTIVA.reset(tok)


def unita_nel_nome(nome, codifica=None, noti=None, solo_classe=False):
    """Unità indicate nel nome di un file o layer («B12», «GR6.A66», «US_1005»): codici interni delle sole
    unità note (se ``noti`` è dato), in ordine e senza ripetizioni. Con ``solo_classe`` contano solo le
    sigle con la lettera della classe («B1»), non i numeri nudi («2001_1.pdf» non è B1)."""
    codifica = codifica if codifica is not None else attiva()
    out = []
    testo = str(nome)
    prima, fine = None, -1
    for m in _TOKEN_RE.finditer(testo):
        c = _classe_da_prefisso(m.group(1))
        n = int(m.group(2))
        # «A30-39», «A16-33-B33»: il numero dopo il trattino ha la classe di quello prima
        if c is None and not m.group(1) and prima and testo[fine:m.start()] in ("-", "–"):
            c = prima
        prima, fine = c, m.end()
        if solo_classe and c is None:
            continue
        if codifica is not None:
            k = codifica.codice(f"{c}{n}" if c else n)
        else:
            k = n if c is None or c in ("US", "SU") else None
        if k is None or (noti is not None and k not in noti) or k in out:
            continue
        out.append(k)
    return out
