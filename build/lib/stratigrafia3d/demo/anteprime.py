# -*- coding: utf-8 -*-
"""Anteprime PNG della pianta composita e delle sezioni (matplotlib)."""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch
from matplotlib.path import Path
from shapely import affinity

plt.rcParams["font.family"] = "DejaVu Sans"


def _patch(geom, **kw):
    polys = getattr(geom, "geoms", [geom])
    verts, codes = [], []
    for p in polys:
        if p.geom_type != "Polygon":
            continue
        for ring in [p.exterior, *p.interiors]:
            c = np.asarray(ring.coords)[:, :2]
            verts.append(c); codes.append([Path.MOVETO] + [Path.LINETO] * (len(c) - 2) + [Path.CLOSEPOLY])
    if not verts:
        return None
    return PathPatch(Path(np.vstack(verts), np.concatenate(codes)), **kw)


def pianta(g_us, g_usm, gq, gsez, grs, sond, E0, N0, out):
    fig, ax = plt.subplots(figsize=(14, 11.5), dpi=130)
    sh = lambda g: affinity.translate(g, -E0, -N0)
    # disegno dal basso verso l'alto: ogni US copre le precedenti (pianta composita)
    for _, r in g_us.iterrows():
        g = sh(r.geometry)
        if r.tipo == "negativa":
            p = _patch(g, facecolor="none", edgecolor="#111", lw=1.0, ls="--", zorder=3)
        else:
            p = _patch(g, facecolor=r.colore_hex, edgecolor="#2b2b2b", lw=0.4, alpha=0.9, zorder=2)
        if p is not None:
            ax.add_patch(p)
    for _, r in g_usm.iterrows():
        p = _patch(sh(r.geometry), facecolor=r.colore_hex, edgecolor="#3b3024", lw=0.9, hatch="xx", zorder=4)
        ax.add_patch(p)
        c = sh(r.geometry).representative_point()
        ax.text(c.x, c.y, f"USM {r.usm}", fontsize=6.5, ha="center", va="center", zorder=9,
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.8))
    for _, r in g_us.iterrows():
        g = sh(r.geometry)
        big = max(getattr(g, "geoms", [g]), key=lambda x: x.area)
        c = big.representative_point()
        ax.text(c.x, c.y, str(r.us), fontsize=6, ha="center", va="center", zorder=8, color="#111",
                bbox=dict(boxstyle="round,pad=0.1", fc="#fff8", ec="none"))
    ax.add_patch(_patch(sond, facecolor="none", edgecolor="#c31", lw=1.6, ls=(0, (5, 3)), zorder=6))
    for _, r in gsez.iterrows():
        x, y = np.asarray(r.geometry.coords).T
        ax.plot(x - E0, y - N0, color="#d00", lw=1.2, zorder=7)
        ax.text(x[0] - E0, y[0] - N0, r.sezione.split("-")[0], color="#d00", fontsize=10, weight="bold", zorder=9)
        ax.text(x[-1] - E0, y[-1] - N0, r.sezione.split("-")[1], color="#d00", fontsize=10, weight="bold", zorder=9)
    qx = gq.geometry.x - E0; qy = gq.geometry.y - N0
    ax.scatter(qx, qy, s=3, c="k", zorder=7, linewidths=0)
    ax.scatter(grs.geometry.x - E0, grs.geometry.y - N0, marker="*", s=60, c="gold", edgecolors="k", lw=0.5, zorder=8)
    ax.set_xlim(-0.5, 20.5); ax.set_ylim(-0.5, 16.5); ax.set_aspect("equal")
    ax.set_xticks(range(0, 21, 2)); ax.set_yticks(range(0, 17, 2)); ax.grid(ls=":", lw=0.4, color="#999")
    ax.set_title("Podere Roveto (sito immaginario) – Area 1000 – pianta composita delle US documentate", fontsize=11)
    ax.set_xlabel(f"x locale (m)  —  E = {E0:.0f} + x   [EPSG:6707]"); ax.set_ylabel(f"y locale (m)  —  N = {N0:.0f} + y")
    ax.annotate("N", xy=(19.6, 15.9), xytext=(19.6, 14.9), arrowprops=dict(arrowstyle="-|>", color="k"),
                ha="center", fontsize=12, weight="bold")
    fig.tight_layout(); fig.savefig(out); plt.close(fig)


def sezioni(gsp, US, USM, out):
    sez = sorted(gsp.sezione.unique())
    fig, axes = plt.subplots(len(sez), 1, figsize=(16, 3.6 * len(sez)), dpi=120)
    for ax, s in zip(np.atleast_1d(axes), sez):
        sub = gsp[gsp.sezione == s]
        for _, r in sub.iterrows():
            u = int(r.us)
            col = US[u]["hex"] if u in US else USM[u]["hex"]
            p = _patch(r.geometry, facecolor=col, edgecolor="#222", lw=0.5, hatch="xx" if u in USM else None)
            ax.add_patch(p)
            if r.geometry.area > 0.02:
                c = r.geometry.representative_point()
                ax.text(c.x, c.y, str(u), fontsize=6, ha="center", va="center")
        b = sub.total_bounds
        ax.set_xlim(b[0] - 0.2, b[2] + 0.2); ax.set_ylim(b[1] - 0.1, b[3] + 0.1)
        ax.set_aspect(2.0)
        ax.set_title(f"Sezione {s}  (esagerazione verticale ×2)", fontsize=10, loc="left")
        ax.set_ylabel("m s.l.m."); ax.grid(ls=":", lw=0.4)
    fig.tight_layout(); fig.savefig(out); plt.close(fig)


def piante_per_fase(g_us, g_usm, gq, gsez, grs, sond, E0, N0, FASI, out):
    fig, axes = plt.subplots(3, 3, figsize=(18, 15), dpi=110)
    sh = lambda g: affinity.translate(g, -E0, -N0)
    for ax, f in zip(axes.flat, reversed(FASI)):
        fase = f[0]
        for _, r in g_usm.iterrows():
            col = r.colore_hex if r.fase == fase else "#e6e2da"
            ax.add_patch(_patch(sh(r.geometry), facecolor=col, edgecolor="#6b5d4d", lw=0.5,
                                hatch="xx" if r.fase == fase else None, zorder=4 if r.fase == fase else 1))
        sub = g_us[g_us.fase == fase]
        for _, r in sub.iterrows():
            g = sh(r.geometry)
            if r.tipo == "negativa":
                p = _patch(g, facecolor="none", edgecolor="#111", lw=1.1, ls="--", zorder=6)
            else:
                p = _patch(g, facecolor=r.colore_hex, edgecolor="#222", lw=0.5, alpha=0.92, zorder=3)
            ax.add_patch(p)
            big = max(getattr(g, "geoms", [g]), key=lambda x: x.area)
            c = big.representative_point()
            ax.text(c.x, c.y, str(r.us), fontsize=7, ha="center", va="center", zorder=9,
                    bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.8))
        qq = gq[gq.us.isin(list(sub.us) + list(g_usm[g_usm.fase == fase].usm))]
        ax.scatter(qq.geometry.x - E0, qq.geometry.y - N0, s=2.5, c="k", zorder=7, linewidths=0)
        rr = grs[grs.us.isin(sub.us)]
        ax.scatter(rr.geometry.x - E0, rr.geometry.y - N0, marker="*", s=70, c="gold", edgecolors="k", lw=0.5, zorder=8)
        ax.add_patch(_patch(sond, facecolor="none", edgecolor="#c31", lw=1.0, ls=(0, (4, 3)), zorder=5))
        for _, r in gsez.iterrows():
            x, y = np.asarray(r.geometry.coords).T
            ax.plot(x - E0, y - N0, color="#d00", lw=0.6, alpha=0.6, zorder=5)
        ax.add_patch(_patch(sh(affinity.translate(g_us.geometry.iloc[0].envelope, 0, 0)), facecolor="none", edgecolor="none"))
        ax.set_xlim(-0.3, 20.3); ax.set_ylim(-0.3, 16.3); ax.set_aspect("equal")
        ax.set_xticks(range(0, 21, 4)); ax.set_yticks(range(0, 17, 4)); ax.grid(ls=":", lw=0.3)
        per = f[1] if f[2] is None else f"{f[1]}"
        ax.set_title(f"Fase {fase} – {f[4]}  ({per})", fontsize=10, loc="left")
    fig.suptitle("Podere Roveto (sito immaginario) – Area 1000 – US documentate per fase "
                 "(punti = quote; stelle = reperti speciali; tratteggio rosso = Saggio 1)", fontsize=12)
    fig.tight_layout(); fig.savefig(out); plt.close(fig)
