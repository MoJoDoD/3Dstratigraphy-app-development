# -*- coding: utf-8 -*-
"""
Quote stimate per le unità che non ne hanno: la ricostruzione adattiva.

Ogni unità riceve una strategia, dalla più affidabile alla meno:
    misurata    ha quote o profili propri
    profondita  taglio senza quote: superficie di riferimento meno la profondità della scheda
    impilata    riempimento o strato senza quote: sotto la superficie (o l'orlo del suo taglio),
                al di sotto delle unità che lo coprono, con lo spessore della scheda
    schematica  come sopra, ma profondità o spessore mancano e si usano i valori tipici
    nessuna     non ricostruibile (nessuna superficie di riferimento e nessuna quota)

Le quote stimate sono punti come quelli rilevati: la ricostruzione li usa allo stesso modo,
ma restano fuori dal layer delle quote e ogni unità porta scritta la sua strategia.
"""
import math
from dataclasses import dataclass

import networkx as nx
import numpy as np
import pandas as pd
import shapely
from shapely.ops import unary_union

from . import schema as sc
from .interpolazione import Krig
from .superficie import campionatore

STRATEGIE = ["misurata", "profondita", "impilata", "schematica", "nessuna"]
DESCRIZIONE = {
    "misurata": "quote o profili rilevati",
    "profondita": "superficie di riferimento e profondità della scheda",
    "impilata": "posizione nella sequenza e spessore della scheda",
    "schematica": "valori tipici (profondità o spessore non registrati)",
    "nessuna": "non ricostruibile: servono quote o una superficie di riferimento",
}
# ordine dei riempimenti quando i rapporti non lo dicono: numero più alto = più in basso
RANGO_RIEMPIMENTO = [("primar", 4), ("primary", 4), ("second", 3), ("terz", 1), ("tertiary", 1), ("upper", 1),
                     ("post-pipe", 0), ("post pipe", 0), ("impronta del palo", 0)]


def _numero(v):
    try:
        x = float(str(v).replace(",", "."))
        return None if math.isnan(x) else x
    except (TypeError, ValueError):
        return None


def _bordo(geom, n_max=120, passo_min=0.25):
    pts = []
    per = sum(r.length for p in getattr(geom, "geoms", [geom]) for r in [p.exterior, *p.interiors])
    passo = max(passo_min, per / n_max)
    for p in getattr(geom, "geoms", [geom]):
        for ring in [p.exterior, *p.interiors]:
            n = max(6, int(ring.length / passo))
            for d in np.linspace(0, ring.length, n, endpoint=False):
                q = ring.interpolate(d)
                pts.append((q.x, q.y))
    return np.array(pts) if pts else np.zeros((0, 2))


def _griglia(geom, n=60, passo_min=0.25, distanza=0.0):
    passo = max(passo_min, math.sqrt(max(geom.area, 1e-6) / n))
    x0, y0, x1, y1 = geom.bounds
    xs, ys = np.meshgrid(np.arange(x0 + passo / 2, x1, passo), np.arange(y0 + passo / 2, y1, passo))
    P = np.c_[xs.ravel(), ys.ravel()]
    zona = geom.buffer(-distanza) if distanza > 0 else geom
    if len(P) == 0 or zona.is_empty:
        return np.zeros((0, 2))
    return P[shapely.contains_xy(zona, P[:, 0], P[:, 1])]


def _raggio_inscritto(geom):
    best = 0.0
    for p in getattr(geom, "geoms", [geom]):
        try:
            best = max(best, shapely.maximum_inscribed_circle(p, tolerance=0.01).length)
        except Exception:
            best = max(best, math.sqrt(p.area / math.pi))
    return best


def _punto_interno(geom):
    p = max(getattr(geom, "geoms", [geom]), key=lambda g: g.area)
    from shapely.ops import polylabel
    try:
        q = polylabel(p, tolerance=0.01)
    except Exception:
        q = p.representative_point()
    return np.array([[q.x, q.y]])


def _linee(linee, passo=0.2):
    pts = []
    for l in getattr(linee, "geoms", [linee]):
        if l.geom_type != "LineString" or l.length == 0:
            continue
        for d in np.arange(0, l.length + 1e-9, passo):
            q = l.interpolate(d)
            pts.append((q.x, q.y))
    return np.array(pts) if pts else np.zeros((0, 2))


def _rango(testo):
    t = str(testo or "").lower()
    for chiave, r in RANGO_RIEMPIMENTO:
        if chiave in t:
            return r
    return 2


@dataclass
class Stima:
    quote: pd.DataFrame           # us, tipo, x, y, z
    strategia: dict               # unità -> strategia
    spessori: dict                # unità -> spessore usato (riempimenti impilati)
    note: list                    # dict(messaggio, unita)
    copre_dedotto: list           # (a, b): a sta sopra b nello stesso taglio, ordine dedotto


def stima_quote(scavo):
    """Quote stimate, strategia per unità e ordine dedotto dei riempimenti (vedi Stima)."""
    P = scavo.parametri
    S = campionatore(scavo)
    q = scavo.quote_locali()
    poly_us, poly_usm = scavo.poligoni_us(), scavo.poligoni_usm()
    schede_us, schede_usm = scavo.schede_us(), scavo.schede_usm()
    G = scavo.rapporti().grafo
    fondi = scavo.linee_fondo()
    per_unita = {u: set(g.tipo) for u, g in q.groupby("us")}

    def misurata(u, tipi, interfaccia):
        return bool(per_unita.get(u, set()) & set(tipi)) or len(scavo.punti_profilo(u, interfaccia)) > 0

    negativa = {u for u, r in schede_us.items() if str(r.get(sc.C_TIPO, "")).strip().lower() == "negativa"}
    righe, strategia, spessori, note = [], {}, {}, []

    def aggiungi(u, tipo, xy, z):
        for (x, y), zz in zip(xy, z):
            righe.append((u, tipo, float(x), float(y), float(zz)))

    # ---------------------------------------------------------------- tagli
    rif_taglio, prof_taglio = {}, {}
    for u in sorted(negativa & set(poly_us)):
        g = poly_us[u]
        if misurata(u, [sc.Q_ORLO, sc.Q_TAGLIO], "taglio"):
            strategia[u] = "misurata"
            sq = q[q.us == u]
            orlo = sq[sq.tipo == sc.Q_ORLO][["x", "y", "z"]].to_numpy()
            fondo = np.vstack([sq[sq.tipo == sc.Q_TAGLIO][["x", "y", "z"]].to_numpy(), scavo.punti_profilo(u, "taglio")])
            if len(orlo) >= 2:
                k = Krig(orlo, rng=1.0)
                rif_taglio[u] = k
            elif S is not None:
                rif_taglio[u] = S
            alto = orlo[:, 2].max() if len(orlo) else (fondo[:, 2].max() if len(fondo) else None)
            if alto is not None and len(fondo):
                prof_taglio[u] = max(float(alto - fondo[:, 2].min()), 0.02)
            continue
        if S is None:
            strategia[u] = "nessuna"
            continue
        d = _numero(schede_us[u].get(sc.C_PROFONDITA))
        if d is not None and d > 0:
            strategia[u] = "profondita"
        else:
            d = P.profondita_predefinita
            strategia[u] = "schematica"
        rin = _raggio_inscritto(g)
        base = np.zeros((0, 2))
        if fondi is not None and not fondi.is_empty:
            dentro = fondi.intersection(g.buffer(-0.02))
            if not dentro.is_empty:
                base = _linee(dentro)
        if len(base):
            dist = shapely.distance(shapely.points(base[:, 0], base[:, 1]), g.boundary)
            w0 = float(np.clip(np.median(dist), 0.05, 0.9 * rin if rin > 0 else 0.5))
        else:
            w0 = float(min(0.6 * d, 0.9 * rin if rin > 0 else 0.3, 1.1))
        w0 = max(w0, 0.04)
        orlo = _bordo(g)
        aggiungi(u, sc.Q_ORLO, orlo, S(orlo))
        meta = _bordo(g.buffer(-w0 / 2), n_max=80, passo_min=0.2) if not g.buffer(-w0 / 2).is_empty else np.zeros((0, 2))
        if len(meta):
            aggiungi(u, sc.Q_TAGLIO, meta, S(meta) - 0.5 * d)
        piano = np.vstack([base, _griglia(g, distanza=w0)]) if len(base) else _griglia(g, distanza=w0)
        if len(piano) == 0:
            piano = _punto_interno(g)
        aggiungi(u, sc.Q_TAGLIO, piano, S(piano) - d)
        rif_taglio[u], prof_taglio[u] = S, d

    # ---------------------------------------------------------------- riempimenti, per taglio
    positive = [u for u in sorted(poly_us) if u not in negativa and u in schede_us]
    stimare = [u for u in positive if not misurata(u, [sc.Q_SUP], "sup")]
    for u in positive:
        if u not in stimare:
            strategia[u] = "misurata"

    def spessore(u):
        return _numero(schede_us[u].get(sc.C_SPESSORE))

    def taglio_di(u):
        for v in G.successors(u) if u in G else []:
            if G.edges[u, v]["t"] == sc.R_RIEMPIE and v in negativa and v in rif_taglio:
                return v
        return None

    gruppi = {}
    for u in stimare:
        c = taglio_di(u)
        if c is not None:
            gruppi.setdefault(c, []).append(u)
    in_taglio, ridotti, dedotti = set(), [], []
    for c, F in gruppi.items():
        H = nx.DiGraph()
        H.add_nodes_from(F)
        H.add_edges_from((a, b) for a, b in G.subgraph(F).edges if G.edges[a, b]["t"] == sc.R_COPRE)
        if not nx.is_directed_acyclic_graph(H):
            H = nx.DiGraph(); H.add_nodes_from(F)
        # dall'alto: prima i rapporti "copre", poi il tipo di riempimento, poi il numero
        chiave = lambda u: (_rango(schede_us[u].get("Definizione")), u)
        ordine = list(nx.lexicographical_topological_sort(H, key=chiave))
        t = np.array([spessore(u) if spessore(u) and spessore(u) > 0 else np.nan for u in ordine], float)
        D = prof_taglio.get(c, P.profondita_predefinita)
        mancano = np.isnan(t)
        if mancano.any():
            t[mancano] = max((D - np.nansum(t)) / mancano.sum(), 0.05)
        if t.sum() > D * 1.05:
            t = t * (D / t.sum())
            ridotti.append(c)
        dedotti.extend((a, b) for a, b in zip(ordine[:-1], ordine[1:]) if not G.has_edge(a, b))
        rif = rif_taglio[c]
        cum = 0.0
        for u, tu in zip(ordine, t):
            g = poly_us[u]
            pts = np.vstack([_bordo(g, n_max=60), _griglia(g, n=40)])
            aggiungi(u, sc.Q_SUP, pts, rif(pts) - min(cum, max(D - 0.03, 0.0)))
            spessori[u] = float(tu)
            strategia[u] = "impilata" if spessore(u) else "schematica"
            cum += float(tu)
            in_taglio.add(u)

    # ---------------------------------------------------------------- strati liberi
    liberi = [u for u in stimare if u not in in_taglio]
    if liberi and S is None:
        for u in liberi:
            strategia[u] = "nessuna"
        liberi = []
    memo = {}

    def profondita_tetto(u, visti=()):
        if u in memo:
            return memo[u]
        m = 0.0
        for p in (G.predecessors(u) if u in G else []):
            if p in liberi and p not in visti and G.edges[p, u]["t"] in (sc.R_COPRE, sc.R_RIEMPIE):
                tp = spessore(p) or P.spessore_predefinito
                m = max(m, profondita_tetto(p, visti + (u,)) + tp)
        memo[u] = m
        return m

    for u in liberi:
        g = poly_us[u]
        pts = np.vstack([_bordo(g, n_max=80), _griglia(g, n=60)])
        aggiungi(u, sc.Q_SUP, pts, S(pts) - profondita_tetto(u))
        strategia[u] = "impilata" if spessore(u) else "schematica"

    # ---------------------------------------------------------------- murature
    for u in sorted(poly_usm):
        if misurata(u, [sc.Q_RASATURA], "sup"):
            strategia[u] = "misurata"
        elif S is None:
            strategia[u] = "nessuna"
        else:
            g = poly_usm[u]
            pts = np.vstack([_bordo(g, n_max=80), _griglia(g, n=40)])
            aggiungi(u, sc.Q_RASATURA, pts, S(pts))
            strategia[u] = "schematica"

    for u in poly_us:
        strategia.setdefault(u, "nessuna" if u not in schede_us else "misurata")
    if ridotti:
        note.append(dict(messaggio=f"{len(ridotti)} tagli hanno riempimenti che, sommati, superano la profondità "
                                   "(probabilmente registrati in punti diversi): spessori ridotti in proporzione",
                         unita=sorted(ridotti)))
    est = pd.DataFrame(righe, columns=["us", "tipo", "x", "y", "z"]).astype(
        {"us": int, "tipo": str, "x": float, "y": float, "z": float})
    return Stima(est, strategia, spessori, note, dedotti)


def conteggio(strategia):
    """Numero di unità per strategia, nell'ordine di affidabilità."""
    return {s: sum(1 for v in strategia.values() if v == s) for s in STRATEGIE if any(v == s for v in strategia.values())}
