# -*- coding: utf-8 -*-
"""Triangolazione dei poligoni e costruzione di mesh chiuse (tetto, base, pareti)."""
import numpy as np
import triangle as tr
from shapely.geometry import Polygon


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


def triangola(geom, passo=0.12, area_max=0.03):
    """Triangolazione vincolata di un (Multi)Polygon con buchi.
    Ritorna (V2 [n,2], F [m,3]) con triangoli in senso antiorario (normale verso l'alto)."""
    V, F = [], []
    for p in getattr(geom, "geoms", [geom]):
        if p.geom_type != "Polygon" or p.area < 0.005:
            continue
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
        d = dict(vertices=np.array(verts), segments=np.array(segs))
        if holes:
            d["holes"] = np.array(holes)
        t = tr.triangulate(d, f"pq28a{area_max:.4f}Q")
        v, f = t["vertices"], t["triangles"]
        a, b, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
        cr = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
        f[cr < 0] = f[cr < 0][:, [0, 2, 1]]
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
