# -*- coding: utf-8 -*-
"""
Ricostruzione dei volumi 3D delle unità stratigrafiche.

Per ogni US positiva:
  1. triangolazione vincolata del poligono in pianta
  2. tetto = trend planare + kriging dei residui (quote 'sup' + profili superiori)
  3. spessore = kriging dello spessore misurato (tetto - quote 'inf' e profili inferiori),
     che torna allo spessore medio lontano dalle misure; per le lenti con margini
     'rastremati' lo spessore va a zero sui bordi liberi
  4. aggancio stratigrafico: dal basso verso l'alto, dove A copre/riempie B la base di A
     coincide con il tetto (o con la superficie di taglio) di B
US negative -> superfici (orlo + fondo + parete stimata dai dati).
USM -> volume tra rasatura e fondazione (rilevata o stimata).
"""
import numpy as np
import pandas as pd
import networkx as nx
import shapely
from shapely import contains_xy
from shapely.ops import unary_union
from scipy.interpolate import LinearNDInterpolator

from . import schema as sc
from .interpolazione import Krig, smoothstep
from .mesh import triangola
from .progetto import Modello, UnitaModello
from .stima import stima_quote


def _numero_o_none(v):
    try:
        x = float(v)
        return None if np.isnan(x) else x
    except (TypeError, ValueError):
        return None


def _qualita_base(n_inf):
    return "misurata" if n_inf >= 6 else ("parziale" if n_inf > 0 else "stimata")


def da_ricalcolare(scavo, cambiate):
    """Unità da ricalcolare dopo una modifica: quelle cambiate e tutte quelle che stanno sopra."""
    G = scavo.rapporti().grafo
    out = set()
    for u in cambiate:
        out.add(u)
        if u in G:
            out |= nx.ancestors(G, u)
    return out


def ricostruisci(scavo, unita=None, log=None):
    """Ricostruisce il modello 3D dello scavo. ``unita``: sottoinsieme da ricalcolare (None = tutte).
    Ritorna un Modello e lo assegna a ``scavo.modello``."""
    log = log or (lambda *a: None)
    P = scavo.parametri
    # quote rilevate + quote stimate per le unità che non ne hanno (ricostruzione adattiva)
    stima = stima_quote(scavo)
    stimate, strategia, spessori_stimati = stima.quote, stima.strategia, stima.spessori
    q = scavo.quote_locali()
    if len(stimate):
        q = pd.concat([q, stimate], ignore_index=True) if len(q) else stimate
    n_stimate = stimate.groupby("us").size().to_dict() if len(stimate) else {}
    poly_us, poly_usm = scavo.poligoni_us(), scavo.poligoni_usm()
    schede_us, schede_usm = scavo.schede_us(), scavo.schede_usm()
    limiti = scavo.limiti()
    muri = unary_union(list(poly_usm.values())) if poly_usm else shapely.Polygon()
    rap = scavo.rapporti()
    G = rap.grafo
    if not nx.is_directed_acyclic_graph(G):
        raise ValueError("i rapporti stratigrafici contengono un ciclo: esegui la verifica")
    if stima.copre_dedotto:           # ordine dei riempimenti dedotto: vale per l'aggancio, non per l'archivio
        G = G.copy()
        for a_, b_ in stima.copre_dedotto:
            if not G.has_edge(a_, b_):
                G.add_edge(a_, b_, t=sc.R_COPRE, dedotto=True)
        if not nx.is_directed_acyclic_graph(G):
            G = rap.grafo

    precedente = scavo.modello.unita if (scavo.modello and unita is not None) else {}
    modello = Modello(unita=dict(precedente))
    da_fare = set(unita) if unita is not None else None

    def qpts(u, tipi):
        s = q[(q.us == u) & (q.tipo.isin(tipi))]
        return s[["x", "y", "z"]].to_numpy()

    def bordi_liberi(geom, passo=0.3):
        out = []
        for p in getattr(geom, "geoms", [geom]):
            for ring in [p.exterior, *p.interiors]:
                for d in np.arange(0, ring.length, passo):
                    pt = ring.interpolate(d)
                    if pt.distance(limiti) < 0.06 or pt.distance(muri) < 0.06:
                        continue
                    out.append((pt.x, pt.y))
        return np.array(out) if out else np.zeros((0, 2))

    def campionatore_tetto(u):
        m = modello.unita.get(u)
        if m is None or len(m.V2) < 3:
            return None
        interp = LinearNDInterpolator(m.V2, m.top)
        geom = (poly_us[u] if u in poly_us else poly_usm[u]).buffer(0.01)
        def f(xy):
            z = interp(xy)
            z[~contains_xy(geom, xy[:, 0], xy[:, 1])] = np.nan
            return z
        return f

    def superficie_taglio(u, geom, V2):
        rim_p = qpts(u, [sc.Q_ORLO])
        cut_p = np.vstack([qpts(u, [sc.Q_TAGLIO]), scavo.punti_profilo(u, "taglio", 0.05)])
        if len(cut_p) == 0:
            cut_p = rim_p
        krim = Krig(rim_p, rng=1.0) if len(rim_p) >= 2 else Krig(cut_p[cut_p[:, 2] >= np.percentile(cut_p[:, 2], 90)])
        bnd = geom.boundary.difference(muri.buffer(0.06)).difference(limiti.buffer(0.06))
        if bnd.is_empty or bnd.length < 0.2:
            bnd = geom.boundary
        dist = lambda xy: shapely.distance(shapely.points(xy[:, 0], xy[:, 1]), bnd)
        rim_c = krim(cut_p[:, :2])
        depth = rim_c - cut_p[:, 2]
        D = np.percentile(depth, 95) if len(depth) else 0
        fondo = cut_p[depth > 0.75 * D] if D > 0 else cut_p
        kbot = Krig(fondo, trend=len(fondo) >= 8, rng=1.0)
        Dloc = np.maximum(rim_c - kbot(cut_p[:, :2]), 0.02)
        phi = np.clip(depth / Dloc, 0, 1)
        d = dist(cut_p[:, :2])
        ws = np.linspace(0.02, 1.2, 120)
        w = ws[int(np.argmin([np.mean((smoothstep(d / w_) - phi) ** 2) for w_ in ws]))]
        zr, zb = krim(V2), kbot(V2)
        zb = np.minimum(zb, zr - 0.02)
        return zr - (zr - zb) * smoothstep(dist(V2) / w), dict(punti_orlo=len(rim_p), punti_taglio=len(cut_p),
                                                             parete_m=round(float(w), 2))

    for u in reversed(list(nx.topological_sort(G))):          # dal basso verso l'alto
        if da_fare is not None and u not in da_fare:
            continue
        # ---------------- murature
        if u in poly_usm:
            geom = poly_usm[u]
            V2, F = triangola(geom, passo=0.1, area_max=0.02)
            if len(V2) == 0 or len(F) == 0:
                log(f"USM {u}: poligono troppo piccolo o non valido, saltata"); continue
            S = np.vstack([qpts(u, [sc.Q_RASATURA]), scavo.punti_profilo(u, "sup", P.passo_profili)])
            if len(S) == 0:
                log(f"USM {u}: nessuna quota di rasatura, saltata"); continue
            top = Krig(S, trend=False, rng=0.8)(V2)
            B = np.vstack([qpts(u, [sc.Q_FONDAZIONE]), scavo.punti_profilo(u, "inf", P.passo_profili)])
            base_x = schede_usm.get(u, {}).get(sc.C_BASE_USM, np.nan) if u in schede_usm else np.nan
            base_x = float(base_x) if pd.notna(base_x) else float(np.min(top) - 0.5)
            bot = Krig(B, mean=base_x, rng=1.5)(V2) if len(B) >= 3 else np.full(len(V2), base_x)
            bot = np.minimum(bot, top - 0.02)
            modello.unita[u] = UnitaModello(u, "usm", V2, F, top, bot,
                                            dict(punti_tetto=len(S), punti_base=len(B), base=_qualita_base(len(B))))
            continue
        if u not in poly_us or u not in schede_us:
            continue
        info, geom = schede_us[u], poly_us[u]
        area = geom.area
        area_max = float(np.clip(area / P.area_triangolo_fattore, P.area_triangolo_min, P.area_triangolo_max))
        passo = P.passo_bordo_piccole if area < 3 else (P.passo_bordo_medie if area < 20 else P.passo_bordo_grandi)
        # unità molto grandi (carte archeologiche, aree estese): al massimo ~20 000 triangoli e 4 000 lati di bordo
        area_max = max(area_max, area / 20000)
        passo = max(passo, geom.length / 4000)
        V2, F = triangola(geom, passo=passo, area_max=area_max)
        if len(V2) == 0:
            continue
        # ---------------- tagli
        if str(info.get(sc.C_TIPO, "")).strip().lower() == "negativa":
            surf, qual = superficie_taglio(u, geom, V2)
            modello.unita[u] = UnitaModello(u, "taglio", V2, F, surf, surf.copy(), qual)
            continue
        # ---------------- strati
        S = np.vstack([qpts(u, [sc.Q_SUP]), scavo.punti_profilo(u, "sup", P.passo_profili)])
        if len(S) == 0:
            log(f"US {u}: nessuna quota superiore, saltata"); continue
        ktop = Krig(S)
        top = ktop(V2)
        B = np.vstack([qpts(u, [sc.Q_INF]), scavo.punti_profilo(u, "inf", P.passo_profili)])
        sp = pd.to_numeric(pd.Series([info.get(sc.C_SPESSORE, np.nan)]), errors="coerce").iloc[0]
        sp = spessori_stimati.get(u, float(sp) if pd.notna(sp) and sp > 0 else P.spessore_predefinito)
        fase = info.get(sc.C_FASE, np.nan)
        if _numero_o_none(fase) == 0:
            sp = min(sp, P.substrato_spessore_max)
        th_pts = np.zeros((0, 3))
        if len(B):
            th = ktop(B[:, :2]) - B[:, 2]
            th_pts = np.c_[B[:, :2], np.clip(th, 0.0, None)]
            media = float(np.median(th_pts[:, 2]))
        else:
            media = sp
        lente = P.lenti_rastremate and str(info.get(sc.C_MARGINI, "")).strip().lower() == "rastremati"
        if lente:
            fe = bordi_liberi(geom)
            if len(fe):
                th_pts = np.vstack([th_pts, np.c_[fe, np.zeros(len(fe))]])
        th = np.clip(Krig(th_pts, mean=media, rng=0.5 if lente else 1.0)(V2), P.spessore_minimo, None)
        bot = top - th
        agganciati = 0
        if P.aggancio_stratigrafico:
            sotto = [b for b in G.successors(u) if G.edges[u, b]["t"] in (sc.R_COPRE, sc.R_RIEMPIE)]
            snap = np.full(len(V2), -np.inf)
            for b in sotto:
                f = campionatore_tetto(b)
                if f is None:
                    continue
                z = f(V2)
                ok = ~np.isnan(z)
                snap[ok] = np.maximum(snap[ok], z[ok])
            has = np.isfinite(snap)
            bot[has] = snap[has]
            top = np.maximum(top, bot + P.spessore_minimo)
            agganciati = int(has.sum())
        qual = dict(punti_tetto=len(S), punti_base=len(B), spessore_medio=round(media, 3),
                    base=_qualita_base(len(B)), vertici_agganciati=round(agganciati / max(len(V2), 1), 2),
                    lente=bool(lente))
        modello.unita[u] = UnitaModello(u, "us", V2, F, top, bot, qual)

    for u, m in modello.unita.items():
        if da_fare is None or u in da_fare:
            m.qualita["strategia"] = strategia.get(u, "misurata")
            if n_stimate.get(u):
                m.qualita["quote_stimate"] = int(n_stimate[u])
    for u in set(P.escluse):
        modello.unita.pop(int(u), None)
    modello.rapporto = [dict(unita=int(u), tipo=m.tipo, **m.qualita) for u, m in sorted(modello.unita.items())]
    modello.dedotti = sorted((int(a), int(b)) for a, b, d in G.edges(data=True) if d.get("dedotto"))
    scavo.modello = modello
    scavo.registra("ricostruzione", dict(unita=len(modello.unita),
                                         parziale=sorted(da_fare) if da_fare is not None else None))
    return modello
