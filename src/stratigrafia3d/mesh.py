# -*- coding: utf-8 -*-
"""Triangolazione dei poligoni e costruzione di mesh chiuse (tetto, base, pareti)."""
import os

import numpy as np
from scipy.spatial import Delaunay
from shapely import contains_xy
from shapely.geometry import Polygon

try:                      # libreria C di Shewchuk: triangoli di qualità, non disponibile per ogni Python
    import triangle as tr
except ImportError:       # pragma: no cover - dipende dall'installazione
    tr = None


def metodo_triangolazione():
    """"triangle" se disponibile, altrimenti "scipy" (forzabile con la variabile S3D_TRIANGOLAZIONE)."""
    forzato = os.environ.get("S3D_TRIANGOLAZIONE")
    if forzato in ("triangle", "scipy"):
        return forzato if (forzato == "scipy" or tr is not None) else "scipy"
    return "triangle" if tr is not None else "scipy"


def densify_ring(ring, step):
    c = np.asarray(ring.coords)[:, :2]
    out = []
    for a, b in zip(c[:-1], c[1:]):
        n = max(1, int(np.ceil(np.linalg.norm(b - a) / step)))
        for t in np.arange(n) / n:
            out.append(a + (b - a) * t)
    out = np.array(out)
    keep = [0]
    for i in range(1, len(out)):
        if np.linalg.norm(out[i] - out[keep[-1]]) > 0.01:
            keep.append(i)
    return out[keep]


def _anelli(p, passo):
    verts, segs, holes = [], [], []
    for k, ring in enumerate([p.exterior, *p.interiors]):
        c = densify_ring(ring, passo)
        if len(c) < 3:
            continue
        s0 = len(verts)
        verts.extend(c.tolist())
        segs.extend([(s0 + i, s0 + (i + 1) % len(c)) for i in range(len(c))])
        if k > 0:
            hp = Polygon(ring).representative_point()
            holes.append([hp.x, hp.y])
    return verts, segs, holes


def _triangola_triangle(p, passo, area_max):
    verts, segs, holes = _anelli(p, passo)
    d = dict(vertices=np.array(verts), segments=np.array(segs))
    if holes:
        d["holes"] = np.array(holes)
    t = tr.triangulate(d, f"pq28a{area_max:.4f}Q")
    return t["vertices"], t["triangles"]


def _triangola_scipy(p, passo, area_max):
    """Delaunay su bordo densificato + punti interni su reticolo triangolare; si tengono i
    triangoli con baricentro e punti medi dei lati dentro il poligono."""
    verts, _, _ = _anelli(p, passo)
    B = np.array(verts)
    h = max(passo, float(np.sqrt(area_max * 2.3)))          # lato di un triangolo equilatero di area ~area_max
    x0, y0, x1, y1 = p.bounds
    ys = np.arange(y0 + h / 2, y1, h * np.sqrt(3) / 2)
    pts = [np.c_[np.arange(x0 + (h / 2 if i % 2 else 0), x1, h), np.full(len(np.arange(x0 + (h / 2 if i % 2 else 0), x1, h)), y)]
           for i, y in enumerate(ys)]
    I = np.vstack(pts) if pts else np.zeros((0, 2))
    if len(I):
        dentro = p.buffer(-0.6 * passo)
        I = I[contains_xy(dentro, I[:, 0], I[:, 1])] if not dentro.is_empty else np.zeros((0, 2))
    P = np.vstack([B, I]) if len(I) else B
    if len(P) < 3:
        return np.zeros((0, 2)), np.zeros((0, 3), int)
    F = Delaunay(P).simplices
    a, b, c = P[F[:, 0]], P[F[:, 1]], P[F[:, 2]]
    area = 0.5 * np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0]))
    g = p.buffer(1e-7)
    ok = area > 1e-10
    for q in ((a + b + c) / 3, (a + b) / 2, (b + c) / 2, (c + a) / 2):
        ok &= contains_xy(g, q[:, 0], q[:, 1])
    F = F[ok]
    usati = np.unique(F)
    mappa = -np.ones(len(P), int)
    mappa[usati] = np.arange(len(usati))
    return P[usati], mappa[F]


def separa_vertici_pizzicati(V, F):
    """Un vertice di bordo toccato da due "ventagli" di triangoli separati (il bordo tocca se stesso)
    viene duplicato, uno per ventaglio: la mesh resta una superficie regolare."""
    if len(F) == 0:
        return V, F
    be = spigoli_di_bordo(F)
    uscenti = np.bincount(be[:, 0], minlength=len(V))
    pizzicati = np.flatnonzero(uscenti > 1)
    if len(pizzicati) == 0:
        return V, F
    V = [tuple(v) for v in V]
    F = F.copy()
    for v in pizzicati:
        tri = np.flatnonzero((F == v).any(1))
        # componenti connesse dei triangoli attorno a v (connessi se condividono un lato con v)
        altri = {t: set(F[t][F[t] != v]) for t in tri}
        gruppi, visti = [], set()
        for t in tri:
            if t in visti:
                continue
            g, coda = [], [t]
            visti.add(t)
            while coda:
                x = coda.pop()
                g.append(x)
                for y in tri:
                    if y not in visti and altri[x] & altri[y]:
                        visti.add(y)
                        coda.append(y)
            gruppi.append(g)
        for g in gruppi[1:]:
            V.append(V[v])
            nuovo = len(V) - 1
            for t in g:
                F[t][F[t] == v] = nuovo
    return np.array(V), F


def triangola(geom, passo=0.12, area_max=0.03, metodo=None):
    """Triangolazione di un (Multi)Polygon con buchi.
    Ritorna (V2 [n,2], F [m,3]) con triangoli in senso antiorario (normale verso l'alto)."""
    metodo = metodo or metodo_triangolazione()
    V, F = [], []
    for p in getattr(geom, "geoms", [geom]):
        if p.geom_type != "Polygon" or p.area < 0.005:
            continue
        v, f = (_triangola_triangle if metodo == "triangle" else _triangola_scipy)(p, passo, area_max)
        if len(f) == 0:
            continue
        a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
        cr = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
        f = f.copy()
        f[cr < 0] = f[cr < 0][:, [0, 2, 1]]
        v, f = separa_vertici_pizzicati(v, f)
        F.append(f + sum(len(x) for x in V))
        V.append(v)
    if not V:
        return np.zeros((0, 2)), np.zeros((0, 3), int)
    return np.vstack(V), np.vstack(F)


def spigoli_di_bordo(F):
    """Spigoli usati da un solo triangolo, orientati con l'interno a sinistra."""
    e = np.vstack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    key = np.sort(e, axis=1)
    _, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    return e[cnt[inv.ravel()] == 1]


def mesh_chiusa(V2, F, ztop, zbot):
    """Solido chiuso: tetto (F), base (F rovesciata), pareti laterali lungo il bordo.
    I vertici delle pareti sono duplicati per avere spigoli netti."""
    n = len(V2)
    top = np.c_[V2, ztop]
    bot = np.c_[V2, zbot]
    be = spigoli_di_bordo(F)
    i, j = be[:, 0], be[:, 1]
    side = np.stack([top[i], bot[i], bot[j], top[j]], axis=1).reshape(-1, 3)
    k = np.arange(len(be)) * 4 + 2 * n
    sf = np.r_[np.c_[k, k + 1, k + 2], np.c_[k, k + 2, k + 3]]
    P = np.vstack([top, bot, side])
    Fall = np.vstack([F, F[:, ::-1] + n, sf])
    return P, Fall


def volume_prismi(V2, F, top, bot):
    """Volume come somma di prismi triangolari (area del triangolo × spessore medio)."""
    a = 0.5 * np.abs((V2[F[:, 1], 0] - V2[F[:, 0], 0]) * (V2[F[:, 2], 1] - V2[F[:, 0], 1]) -
                     (V2[F[:, 1], 1] - V2[F[:, 0], 1]) * (V2[F[:, 2], 0] - V2[F[:, 0], 0]))
    return float(np.sum(a * (top[F] - bot[F]).mean(1)))
