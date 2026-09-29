# -*- coding: utf-8 -*-
"""
01 - Genera lo scavo IMMAGINARIO "Podere Roveto - Area 1000".

Prodotti:
  01_GIS/podere_roveto_area1000.gpkg        (vettori stile QGIS con stili incorporati)
  02_Database/podere_roveto_area1000.xlsx   (database di scavo)
  05_Anteprime/pianta_composita.png, sezioni.png

Il modello "di verità" (modello_verita.py) viene campionato come farebbe un
archeologo: poligoni delle US dove sono documentate, quote puntuali dove le
superfici sono esposte, profili lungo le sezioni. Il visualizzatore 3D
(script 02) lavora SOLO su questi prodotti, non sul modello di verità.
"""
import os, sys, json, sqlite3, datetime
import numpy as np
import pandas as pd
import geopandas as gpd
from scipy import ndimage
from skimage import measure
from shapely.geometry import (Polygon, MultiPolygon, Point, LineString, box, mapping)
from shapely.ops import unary_union
from shapely import affinity

from . import modello_verita as mv
from .catalogo import SITO, FASI, US, USM, M as MAT, RS, CAMPIONI



def genera(out_dir, seed=1974, anteprime_png=True, verbose=True):
    """Genera lo scavo immaginario in out_dir (01_GIS, 02_Database, 05_Anteprime).
    Ritorna un dizionario con i percorsi e il modello di verità (per i test)."""
    log = print if verbose else (lambda *a, **k: None)
    OUT = os.path.abspath(out_dir)
    GPKG = os.path.join(OUT, "01_GIS", "podere_roveto_area1000.gpkg")
    XLSX = os.path.join(OUT, "02_Database", "podere_roveto_area1000.xlsx")
    PREV = os.path.join(OUT, "05_Anteprime")
    for p in [os.path.dirname(GPKG), os.path.dirname(XLSX), PREV]:
        os.makedirs(p, exist_ok=True)

    E0, N0 = 681240.0, 4796380.0
    CRS = "EPSG:6707"
    RES = mv.RES
    rng = np.random.default_rng(seed + 5033)

    T = mv.build(seed)
    FASE_INFO = {f[0]: f for f in FASI}

    # ----------------------------------------------------------------------------
    # Regole di documentazione / asportazione
    # ----------------------------------------------------------------------------
    SOND = mv.SONDAGE
    ONLY_SOND = {1017, 1019, 1020, 1021, 1022, 1023, 1024, 1025, 1026, 1027, 1028, 1029,
                 1030, 1031, 1037, 1038}
    REMOVED_ALL = {1000, 1002, 1004, 1005, 1006, 1007, 1008, 1010, 1011, 1012, 1013, 1018,
                   1032, 1034, 1036}
    REMOVED_SOND = {1016, 1017, 1020, 1021, 1022, 1023, 1025, 1027, 1029, 1030, 1038}
    WALL_IDS = [1100, 1101, 1102, 1103, 1105, 1106, 1107]
    CUT_IDS = sorted(T.cuts.keys())

    mSOND = mv.M(SOND)
    mTR = np.ones(mv.X.shape, bool)


    def doc_geom(us):
        return SOND if us in ONLY_SOND else mv.TRENCH


    def doc_mask(us):
        return mSOND if us in ONLY_SOND else mTR


    def removed_mask(us):
        if us in REMOVED_ALL:
            return mTR
        if us in REMOVED_SOND:
            return mSOND
        return np.zeros(mv.X.shape, bool)


    # superficie finale di scavo E: tetto del corpo più alto NON asportato
    E = np.full(mv.X.shape, -np.inf)
    for us, b in T.bodies.items():
        ex = ~np.isnan(b["top"])
        keep = ex & ~removed_mask(us)
        E = np.where(keep, np.maximum(E, b["top"]), E)
    # superficie "vista" da una parete di sezione: minimo di E entro ±30 cm (±60 cm per i muri),
    # escludendo le piccole buche di palo che non sono tagliate dalle sezioni
    E_for_sec = E.copy()
    for _c in (1024, 1026, 1028):
        _m = ~np.isnan(T.cuts[_c]["surf"])
        E_for_sec[_m] = np.inf
    E_SEC = ndimage.minimum_filter(E_for_sec, size=int(0.6 / RES) | 1)
    E_SEC_W = ndimage.minimum_filter(E_for_sec, size=int(1.2 / RES) | 1)


    def cell(x, y):
        c = np.clip((np.asarray(x) / RES).astype(int), 0, mv.NX - 1)
        r = np.clip((np.asarray(y) / RES).astype(int), 0, mv.NY - 1)
        return r, c


    # ----------------------------------------------------------------------------
    # Maschera -> poligono (contorni lisciati, come una digitalizzazione a mano)
    # ----------------------------------------------------------------------------
    def mask_to_geom(mask, clip_geom, min_area=0.01):
        if mask.sum() == 0:
            return None
        pad = np.pad(mask.astype(float), 1)
        sm = ndimage.gaussian_filter(pad, 0.8)
        geom = None
        for c in measure.find_contours(sm, 0.5):
            if len(c) < 5:
                continue
            x = (c[:, 1] - 1 + 0.5) * RES
            y = (c[:, 0] - 1 + 0.5) * RES
            p = Polygon(np.c_[x, y]).buffer(0)
            if p.is_empty:
                continue
            geom = p if geom is None else geom.symmetric_difference(p)
        if geom is None:
            return None
        geom = geom.intersection(clip_geom).buffer(0).simplify(0.012)
        parts = [g for g in getattr(geom, "geoms", [geom]) if g.geom_type == "Polygon" and g.area >= min_area]
        if not parts:
            return None
        return MultiPolygon(parts)


    def to_crs_geom(g):
        return affinity.translate(g, E0, N0)


    # ----------------------------------------------------------------------------
    # Poligoni US e USM
    # ----------------------------------------------------------------------------
    wall_mask_all = mv.M(mv.WALLS_ALL)
    us_geoms = {}
    for us in sorted(US):
        if us in T.cuts:
            m = ~np.isnan(T.cuts[us]["surf"]) & doc_mask(us)
        else:
            b = T.bodies[us]
            m = ~np.isnan(b["top"]) & doc_mask(us)
        g = mask_to_geom(m, doc_geom(us))
        if g is None:
            log("ATTENZIONE: US senza poligono", us); continue
        if (m & wall_mask_all).sum() < 20:
            g = g.difference(mv.WALLS_ALL.buffer(0.005))
            g = MultiPolygon([p for p in getattr(g, "geoms", [g]) if p.geom_type == "Polygon" and p.area > 0.01])
        us_geoms[us] = g

    wall_geoms = {1100: mv.W1100.difference(unary_union([mv.W1101, mv.W1102, mv.W1103])),
                  1101: mv.W1101, 1102: mv.W1102, 1103: mv.W1103,
                  1105: mv.W1105, 1106: mv.W1106, 1107: mv.W1107}
    # il tramezzo spoliato: in pianta resta la fondazione (stessa impronta)
    wall_geoms = {k: MultiPolygon([p for p in getattr(v.intersection(mv.TRENCH), "geoms", [v.intersection(mv.TRENCH)])])
                  for k, v in wall_geoms.items()}

    # ----------------------------------------------------------------------------
    # Quote puntuali
    # ----------------------------------------------------------------------------
    quote = []  # dict(us, tipo, x, y, z)


    def rand_points(geom, n, cond=None, edge_frac=0.3, edge_w=0.25, max_try=40000):
        pts = []
        if geom is None or geom.is_empty or n <= 0:
            return pts
        minx, miny, maxx, maxy = geom.bounds
        inner = geom.buffer(-0.03)
        ring = inner.difference(geom.buffer(-edge_w)) if edge_frac > 0 else None
        targets = [(inner, int(round(n * (1 - edge_frac))))]
        if ring is not None and not ring.is_empty:
            targets.append((ring, n - targets[0][1]))
        from shapely import contains_xy
        dmin2 = min(0.09, 0.5 * geom.area / max(n, 1))   # distanza minima tra punti
        for g, k in targets:
            if g.is_empty or k <= 0:
                continue
            got, tries = 0, 0
            bx0, by0, bx1, by1 = g.bounds
            while got < k and tries < max_try:
                tries += 200
                px = rng.uniform(bx0, bx1, 200); py = rng.uniform(by0, by1, 200)
                ok = contains_xy(g, px, py)
                if cond is not None:
                    r, c = cell(px, py)
                    ok &= cond[r, c]
                for x, y in zip(px[ok], py[ok]):
                    if got >= k:
                        break
                    # distanza minima tra punti (rilievo realistico)
                    if all((x - a) ** 2 + (y - b) ** 2 > dmin2 for a, b in pts[-60:]):
                        pts.append((x, y)); got += 1
        return pts


    def add_q(us, tipo, pts, arr, noise=0.004):
        for x, y in pts:
            r, c = cell(x, y)
            z = arr[r, c]
            if np.isnan(z):
                continue
            quote.append(dict(us=us, tipo=tipo, x=x, y=y, z=round(float(z + rng.normal(0, noise)), 3)))


    for us in sorted(US):
        g = us_geoms.get(us)
        if g is None:
            continue
        if us in T.cuts:
            cs = T.cuts[us]["surf"]
            vis = ~np.isnan(cs)
            a = g.area
            n = int(np.clip(6 + 5 * a, 8, 40))
            add_q(us, "taglio", rand_points(g, n, cond=vis, edge_frac=0.45, edge_w=0.2), cs)
            # quote d'orlo lungo il limite superiore del taglio
            rim = T.cuts[us]["rim"]
            k = int(np.clip(g.length / 0.5, 6, 30))
            for p in getattr(g, "geoms", [g]):
                L = p.exterior.length
                for d in np.linspace(0, L, max(4, int(k * L / g.length)), endpoint=False):
                    q = p.exterior.interpolate(d)
                    # spostato di 3 cm verso l'interno per leggere il valore del taglio
                    qi = p.buffer(-0.03).exterior.interpolate(p.buffer(-0.03).exterior.project(q)) \
                        if not p.buffer(-0.03).is_empty and p.buffer(-0.03).geom_type == "Polygon" else q
                    r, c = cell(qi.x, qi.y)
                    z = rim[r, c]
                    if not np.isnan(z):
                        quote.append(dict(us=us, tipo="orlo", x=q.x, y=q.y, z=round(float(z), 3)))
            continue
        b = T.bodies[us]
        ex = ~np.isnan(b["top"]) & doc_mask(us)
        sup_vis = ex & (b["top"] >= E - 0.002)
        inf_vis = ex & removed_mask(us)
        a = g.area
        n_sup = int(np.clip(5 + 1.1 * a, 6, 45))
        lens = US[us]["margini"] == "rastremati"
        add_q(us, "sup", rand_points(g, n_sup, cond=sup_vis, edge_frac=0.35 if lens else 0.25), b["top"])
        if inf_vis.any():
            a_rm = inf_vis.sum() * RES * RES
            n_inf = int(np.clip(4 + 0.7 * a_rm, 4, 32))
            add_q(us, "inf", rand_points(g, n_inf, cond=inf_vis, edge_frac=0.35 if lens else 0.2), b["bot"])

    # murature: quote di rasatura e (dove visibile) di fondazione
    dil_low = {}
    for w in WALL_IDS:
        b = T.bodies[w]; g = wall_geoms[w]
        ex = ~np.isnan(b["top"])
        n = int(np.clip(g.area * 5, 8, 45))
        add_q(w, "rasatura", rand_points(g, n, cond=ex, edge_frac=0.3, edge_w=0.12), b["top"], noise=0.006)
        # base visibile: celle del muro adiacenti a celle scavate più in basso della base
        lowE = ndimage.minimum_filter(np.where(ex, np.inf, E), size=5)
        vis_base = ex & (lowE <= b["bot"] + 0.03)
        if vis_base.sum() > 3:
            add_q(w, "fondazione", rand_points(g, int(np.clip(vis_base.sum() / 60, 4, 14)), cond=vis_base,
                                                 edge_frac=0.8, edge_w=0.1), b["bot"], noise=0.005)

    qdf = pd.DataFrame(quote)
    qdf.insert(0, "id", [f"Q{i + 1:04d}" for i in range(len(qdf))])
    log("quote:", len(qdf), qdf.tipo.value_counts().to_dict())

    # ----------------------------------------------------------------------------
    # Sezioni e profili
    # ----------------------------------------------------------------------------
    SEZIONI = {
        "A-A'": ((0.3, 10.5), (19.7, 10.5), "E-O"),
        "B-B'": ((12.2, 0.3), (12.2, 15.7), "N-S"),
        "C-C'": ((17.0, 0.3), (17.0, 15.7), "N-S"),
        "D-D'": ((5.1, 3.2), (5.1, 8.6), "N-S"),
    }
    prof_rows, sez_poly_rows = [], []
    all_bodies = {**{u: T.bodies[u] for u in T.bodies}}


    def runs(mask):
        idx = np.flatnonzero(mask)
        if len(idx) == 0:
            return []
        splits = np.flatnonzero(np.diff(idx) > 1)
        starts = np.r_[idx[0], idx[splits + 1]]
        ends = np.r_[idx[splits], idx[-1]]
        return [(s, e) for s, e in zip(starts, ends) if e - s >= 2]


    def simplify_sz(s, z, tol=0.004):
        ls = LineString(np.c_[s, z]).simplify(tol)
        return np.array(ls.coords)


    for sez, (p0, p1, ori) in SEZIONI.items():
        L = np.hypot(p1[0] - p0[0], p1[1] - p0[1])
        ss = np.arange(0, L + 1e-9, RES / 2)
        px = p0[0] + (p1[0] - p0[0]) * ss / L
        py = p0[1] + (p1[1] - p0[1]) * ss / L
        r, c = cell(px, py)
        Es0 = E_SEC[r, c]; EsW = E_SEC_W[r, c]
        def to3d(sz):
            s_, z_ = sz[:, 0], sz[:, 1]
            return LineString(np.c_[E0 + p0[0] + (p1[0] - p0[0]) * s_ / L,
                                    N0 + p0[1] + (p1[1] - p0[1]) * s_ / L, z_])
        for us, b in all_bodies.items():
            top = b["top"][r, c]; bot = b["bot"][r, c]
            Es = EsW if us in WALL_IDS else Es0
            ex = ~np.isnan(top)
            vis = ex & (top > Es + 0.004)
            if us == 1031:   # substrato non scavato: disegnato con 10 cm convenzionali sotto il tetto
                vis = ex & (top >= Es - 0.004)
                bot = top - 0.10
                Es = np.minimum(Es, bot)
            for s0, s1 in runs(vis):
                sl = slice(s0, s1 + 1)
                t_ = top[sl]; b_ = np.maximum(bot[sl], Es[sl])
                real_bot = (bot[sl] >= Es[sl] - 0.004) & (us != 1031)
                sz = simplify_sz(ss[sl], t_)
                prof_rows.append(dict(sezione=sez, us=us, interfaccia="sup", geometry=to3d(sz)))
                for q0, q1 in runs(real_bot):
                    sl2 = slice(s0 + q0, s0 + q1 + 1)
                    sz = simplify_sz(ss[sl2], bot[sl2])
                    prof_rows.append(dict(sezione=sez, us=us, interfaccia="inf", geometry=to3d(sz)))
                poly = Polygon(np.r_[np.c_[ss[sl], t_], np.c_[ss[sl], b_][::-1]]).buffer(0)
                if poly.area > 0.0005:
                    sez_poly_rows.append(dict(sezione=sez, us=us,
                                              limite_inferiore="interfaccia" if real_bot.all() else "limite di scavo",
                                              geometry=poly.simplify(0.003)))
        for us, cdat in T.cuts.items():
            cs = cdat["surf"][r, c]
            vis = ~np.isnan(cs) & (cs >= Es0 - 0.004)
            for s0, s1 in runs(vis):
                sl = slice(s0, s1 + 1)
                sz = simplify_sz(ss[sl], cs[sl])
                prof_rows.append(dict(sezione=sez, us=us, interfaccia="taglio", geometry=to3d(sz)))

    log("profili:", len(prof_rows), " poligoni di sezione:", len(sez_poly_rows))

    # ----------------------------------------------------------------------------
    # Reperti speciali e campioni (con posizione 3D)
    # ----------------------------------------------------------------------------
    def pick_xyz(us, prefer=None):
        b = T.bodies[us]
        ex = ~np.isnan(b["top"]) & doc_mask(us) & (removed_mask(us) | (b["top"] >= E - 0.002))
        cand = np.argwhere(ex)
        if prefer is not None:
            d = (mv.X[ex] - prefer[0]) ** 2 + (mv.Y[ex] - prefer[1]) ** 2
            cand = cand[np.argsort(d)[:30]]
        rr, cc = cand[rng.integers(len(cand))]
        x = mv.X[rr, cc] + rng.uniform(-0.02, 0.02); y = mv.Y[rr, cc] + rng.uniform(-0.02, 0.02)
        z = b["bot"][rr, cc] + (b["top"][rr, cc] - b["bot"][rr, cc]) * rng.uniform(0.25, 0.8)
        return x, y, round(float(z), 3)


    prefs = {1012: (4.5, 5.4)}   # corredo presso la testa dell'inumato (O)
    rs_rows = []
    for i, (us, ogg, mat, descr, dim, d0, d1) in enumerate(RS):
        x, y, z = pick_xyz(us, prefs.get(us))
        rs_rows.append(dict(rs=f"RS{i + 1:03d}", us=us, oggetto=ogg, materiale=mat, descrizione=descr,
                            dimensioni=dim, datazione_da=d0, datazione_a=d1, x=x, y=y, z=z))
    camp_rows = []
    for i, (us, tipo, an, ris) in enumerate(CAMPIONI):
        x, y, z = pick_xyz(us)
        camp_rows.append(dict(campione=f"C{i + 1:02d}", us=us, tipo=tipo, analisi=an, risultato=ris, x=x, y=y, z=z))

    # ----------------------------------------------------------------------------
    # Statistiche per le schede US (dai dati "osservati" + stime da sezione)
    # ----------------------------------------------------------------------------
    def fmt_date(v):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return ""
        v = int(v)
        return f"{-v} a.C." if v < 0 else f"{v} d.C."


    def stato_scavo(us):
        if us in T.cuts:
            return "svuotato" if us not in (1019, 1037) else "svuotato (nel saggio)"
        if us in REMOVED_ALL:
            return "sì"
        if us in REMOVED_SOND:
            return "parziale (saggio)"
        return "no"


    us_stats = {}
    for us in sorted(US):
        g = us_geoms.get(us)
        qq = qdf[qdf.us == us]
        st = dict(area=round(g.area, 2) if g is not None else None,
                  zmax=qq.z.max() if len(qq) else None, zmin=qq.z.min() if len(qq) else None)
        if us in T.bodies:
            b = T.bodies[us]; m = ~np.isnan(b["top"]) & doc_mask(us)
            th = (b["top"] - b["bot"])[m]
            st["sp_medio"] = round(float(np.median(th)), 2) if th.size else None
            st["sp_max"] = round(float(np.percentile(th, 98)), 2) if th.size else None
        else:
            cs = T.cuts[us]["surf"]; rim = T.cuts[us]["rim"]; m = ~np.isnan(cs)
            st["sp_medio"] = None
            st["sp_max"] = round(float(np.nanmax(rim[m] - cs[m])), 2)   # profondità del taglio
        us_stats[us] = st

    wall_stats = {}
    for w in WALL_IDS:
        b = T.bodies[w]; g = wall_geoms[w]; qq = qdf[qdf.us == w]
        rot = g.minimum_rotated_rectangle
        xs_, ys_ = rot.exterior.coords.xy
        e = sorted([np.hypot(xs_[i + 1] - xs_[i], ys_[i + 1] - ys_[i]) for i in range(4)])
        ras = qq[qq.tipo == "rasatura"].z; fon = qq[qq.tipo == "fondazione"].z
        wall_stats[w] = dict(area=round(g.area, 2), lungh=round(e[-1], 2), largh=round(e[0], 2),
                             q_ras_max=ras.max(), q_ras_min=ras.min(),
                             q_fond=round(fon.mean(), 3) if len(fon) else None,
                             q_fond_stimata=round(float(np.nanmedian(b["bot"])), 2),
                             h_cons=round(float(ras.mean() - np.nanmedian(b["bot"])), 2))

    # ----------------------------------------------------------------------------
    # Rapporti stratigrafici (dal modello, filtrati come li registrerebbe lo scavatore)
    # ----------------------------------------------------------------------------
    ALLNUM = set(US) | set(USM)
    rel = []
    for (a, t, b), n in T.rel.items():
        a, b = int(a), int(b)
        if a not in ALLNUM or b not in ALLNUM:
            continue
        if t == "riempie" and a in US and US[a]["cat"] != "riempimento":
            t = "copre"
            continue
        if t in ("copre", "taglia", "si appoggia a") and n < 20:
            continue
        rel.append((a, t, b))
    # 1000 copre anche la soglia; aggiunte manuali per chiarezza
    rel = sorted(set(rel))
    log("rapporti:", len(rel))

    INV = {"copre": "coperto da", "taglia": "tagliato da", "riempie": "riempito da",
           "si appoggia a": "gli si appoggia", "si lega a": "si lega a"}
    rel_by_us = {}
    for a, t, b in rel:
        rel_by_us.setdefault(a, {}).setdefault(t, []).append(b)
        rel_by_us.setdefault(b, {}).setdefault(INV[t], []).append(a)

    # ----------------------------------------------------------------------------
    # Materiali
    # ----------------------------------------------------------------------------
    mat_rows = []
    cass = 1
    for us in sorted(MAT):
        for (cl, tp, n0, n1, pm, d0, d1) in MAT[us]:
            nr = int(rng.integers(n0, n1 + 1))
            if cl.startswith(("Ceramica", "Terra sigillata", "Anfore", "Lucerne", "Maiolica", "Invetriata", "Vetro")):
                nmi = max(1, int(round(nr / rng.uniform(4, 8))))
            elif cl in ("Resti osteologici umani",):
                nmi = 1
            else:
                nmi = None
            peso = round(nr * pm * float(rng.lognormal(0, 0.18)), 1)
            mat_rows.append(dict(id=f"MAT{len(mat_rows) + 1:04d}", us=us, cassetta=f"CS{cass:03d}",
                                 classe=cl, tipo_forma=tp, NR=nr, NMI=nmi, peso_g=peso,
                                 datazione_da=d0, datazione_a=d1))
        cass += 1
    mdf = pd.DataFrame(mat_rows)
    log("materiali:", len(mdf))

    # ----------------------------------------------------------------------------
    # GEOPACKAGE
    # ----------------------------------------------------------------------------
    if os.path.exists(GPKG):
        os.remove(GPKG)


    def per(us):
        f = US[us]["fase"] if us in US else USM[us]["fase"]
        return f, FASE_INFO[f][1]


    rows = []
    for us, g in us_geoms.items():
        d = US[us]; f, p = per(us)
        rows.append(dict(us=us, tipo=d["tipo"], categoria=d["cat"], definizione=d["defin"], fase=f, periodo=p,
                         ambiente=d["amb"], munsell=d["munsell"], colore_hex=d["hex"], scavata=stato_scavo(us),
                         estensione="ricostruita (lacune del pavimento)" if us == 1015 else "documentata",
                         area_m2=round(g.area, 2), geometry=to_crs_geom(g)))
    g_us = gpd.GeoDataFrame(rows, crs=CRS)
    # ordine di disegno: prima i più antichi
    order_idx = {u: i for i, u in enumerate(T.order)}
    g_us["ordine"] = g_us.us.map(order_idx)
    g_us = g_us.sort_values("ordine").reset_index(drop=True)
    g_us.to_file(GPKG, layer="us_poligoni", driver="GPKG")

    rows = []
    for w, g in wall_geoms.items():
        d = USM[w]; f, p = per(w)
        rows.append(dict(usm=w, categoria=d["cat"], definizione=d["defin"], fase=f, periodo=p, tecnica=d["tecnica"],
                         colore_hex=d["hex"], area_m2=round(g.area, 2), geometry=to_crs_geom(g)))
    gpd.GeoDataFrame(rows, crs=CRS).to_file(GPKG, layer="usm_poligoni", driver="GPKG")

    gpd.GeoDataFrame([dict(nome="Limite di scavo Area 1000", tipo="area", geometry=to_crs_geom(mv.TRENCH)),
                      dict(nome="Saggio 1 (approfondimento)", tipo="saggio", geometry=to_crs_geom(SOND))],
                     crs=CRS).to_file(GPKG, layer="area_scavo", driver="GPKG")

    cols = "ABCDEFGHIJ"
    rows = []
    for i in range(10):
        for j in range(8):
            rows.append(dict(quadrato=f"{cols[i]}{j + 1}", geometry=to_crs_geom(box(i * 2, j * 2, i * 2 + 2, j * 2 + 2))))
    gpd.GeoDataFrame(rows, crs=CRS).to_file(GPKG, layer="griglia_2m", driver="GPKG")

    gq = gpd.GeoDataFrame(qdf.assign(quota=qdf.z), geometry=gpd.points_from_xy(qdf.x + E0, qdf.y + N0, qdf.z), crs=CRS)
    gq = gq.rename(columns={"tipo": "tipo_quota"})[["id", "us", "tipo_quota", "quota", "geometry"]]
    gq.to_file(GPKG, layer="quote", driver="GPKG")

    rows = []
    for sez, (p0, p1, ori) in SEZIONI.items():
        rows.append(dict(sezione=sez, orientamento=ori, lunghezza_m=round(np.hypot(p1[0] - p0[0], p1[1] - p0[1]), 2),
                         geometry=LineString([(p0[0] + E0, p0[1] + N0), (p1[0] + E0, p1[1] + N0)])))
    gpd.GeoDataFrame(rows, crs=CRS).to_file(GPKG, layer="sezioni", driver="GPKG")

    gp = gpd.GeoDataFrame(prof_rows, crs=CRS)
    gp.to_file(GPKG, layer="profili_us", driver="GPKG")
    gsp = gpd.GeoDataFrame(sez_poly_rows)
    gsp = gsp.set_geometry("geometry")
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")   # layer in coordinate di sezione: senza SR per scelta
        gsp.to_file(GPKG, layer="sezioni_disegno", driver="GPKG")

    rsdf = pd.DataFrame(rs_rows)
    grs = gpd.GeoDataFrame(rsdf.assign(quota=rsdf.z), geometry=gpd.points_from_xy(rsdf.x + E0, rsdf.y + N0, rsdf.z), crs=CRS)
    grs.drop(columns=["x", "y", "z"]).to_file(GPKG, layer="reperti_speciali", driver="GPKG")
    cdf = pd.DataFrame(camp_rows)
    gcs = gpd.GeoDataFrame(cdf.assign(quota=cdf.z), geometry=gpd.points_from_xy(cdf.x + E0, cdf.y + N0, cdf.z), crs=CRS)
    gcs.drop(columns=["x", "y", "z"]).to_file(GPKG, layer="campioni", driver="GPKG")

    # stili QGIS incorporati (tabella layer_styles letta automaticamente da QGIS)
    from .. import stili_qgis
    stili_qgis.scrivi_stili(GPKG)
    log("GPKG scritto:", GPKG)


    # ----------------------------------------------------------------------------
    # EXCEL
    # ----------------------------------------------------------------------------
    from . import excel_demo
    excel_demo.scrivi_excel(XLSX, dict(
        SITO=SITO, FASI=FASI, US=US, USM=USM, us_stats=us_stats, wall_stats=wall_stats,
        stato=stato_scavo, rel=rel, rel_by_us=rel_by_us, mdf=mdf, rsdf=rsdf, cdf=cdf, qdf=qdf,
        SEZIONI=SEZIONI, prof=gp, E0=E0, N0=N0, fmt_date=fmt_date, order=T.order,
        only_sond=ONLY_SOND))
    log("XLSX scritto:", XLSX)

    # ----------------------------------------------------------------------------
    # ANTEPRIME
    # ----------------------------------------------------------------------------
    from . import anteprime
    if anteprime_png:
        anteprime.piante_per_fase(g_us, gpd.read_file(GPKG, layer="usm_poligoni"), gq, gpd.read_file(GPKG, layer="sezioni"),
                              grs, SOND, E0, N0, FASI, os.path.join(PREV, "piante_per_fase.png"))
        anteprime.sezioni(gsp, US, USM, os.path.join(PREV, "sezioni.png"))
        log("anteprime ok")
    return dict(gpkg=GPKG, xlsx=XLSX, anteprime=PREV, verita=T, origine=(E0, N0))
