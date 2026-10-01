"""Elaborati dal modello 3D: tabella dei volumi, piante e sezioni in DXF e SVG.

Le sezioni si calcolano tagliando le mesh chiuse delle unità con un piano verticale: ogni unità dà
una o più aree (in coordinate «distanza lungo la sezione, quota»), i tagli danno una linea. Le piante
sono i poligoni delle unità, raggruppati per fase. I DXF sono in formato R12 (si aprono in qualsiasi
CAD e in QGIS) e in coordinate reali; gli SVG sono pronti per la stampa o per Inkscape/Illustrator.
"""
import math
import os

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import LineString, MultiLineString, box
from shapely.ops import linemerge, polygonize, unary_union

from . import schema as sc
from . import stratigrafia as st
from .esporta import mesh_unita, _hex_rgb
from .lingue import lingua_corrente, t as _tr

PALETTE_FASI = ["#8e8a7c", "#5c7196", "#6f8f45", "#b88a2c", "#a8573a", "#7b4b86", "#cf6e4f", "#2f8580", "#6d6659"]


# ---------------------------------------------------------------------------------------------- dati
def _traduttore(lingua=None):
    """Funzione che traduce i testi degli elaborati nella lingua scelta (quella dell'interfaccia)."""
    L = lingua or lingua_corrente()
    return lambda s, *a: _tr(s, *a, lingua=L)


def _schede(scavo):
    return {**{u: ("US", r) for u, r in scavo.schede_us().items()},
            **{u: ("USM", r) for u, r in scavo.schede_usm().items()}}


def _fase(r):
    try:
        v = float(r.get(sc.C_FASE))
        return int(v) if not math.isnan(v) else 0
    except (TypeError, ValueError):
        return 0


def colore_unita(scavo, u, schede=None):
    """Colore della scheda (Munsell convertito) oppure quello della fase."""
    schede = schede or _schede(scavo)
    tipo, r = schede.get(u, ("US", {}))
    hx = r.get(sc.C_COLORE) if hasattr(r, "get") else None
    if isinstance(hx, str) and hx.startswith("#") and len(hx) == 7:
        return hx
    if tipo == "USM":
        return "#c9c2b4"
    f = _fase(r)
    if f < len(PALETTE_FASI):
        return PALETTE_FASI[f]
    h = (f * 137.5 + 20) % 360
    r_, g_, b_ = _hsl(h, 0.42, 0.47)
    return f"#{r_:02x}{g_:02x}{b_:02x}"


def _hsl(h, s, l):
    def f(n):
        k = (n + h / 30) % 12
        a = s * min(l, 1 - l)
        return round(255 * (l - a * max(-1, min(k - 3, 9 - k, 1))))
    return f(0), f(8), f(4)


def tabella_volumi(scavo):
    """Una riga per unità: tipo, definizione, fase, area, volume, quote, spessore, affidabilità."""
    if scavo.modello is None:
        raise ValueError("modello 3D non calcolato")
    schede = _schede(scavo)
    poli = {**scavo.poligoni_us(), **scavo.poligoni_usm()}
    o = scavo.origine
    righe = []
    for u, m in sorted(scavo.modello.unita.items()):
        tipo, r = schede.get(u, ("US", {}))
        g = poli.get(u)
        area = float(g.area) if g is not None else float("nan")
        vol = m.volume() if m.tipo != "taglio" else float("nan")
        spess = (np.asarray(m.top) - np.asarray(m.bot))
        righe.append({
            "Unità": u, "Tipo": "USM" if tipo == "USM" else ("taglio" if m.tipo == "taglio" else "US"),
            "Definizione": r.get("Definizione") if hasattr(r, "get") else None,
            "Fase": _fase(r) if len(r) else None,
            "Area in pianta (m²)": round(area, 3),
            "Volume (m³)": round(vol, 3) if not math.isnan(vol) else None,
            "Quota massima (m)": round(float(np.max(m.top)), 3),
            "Quota minima (m)": round(float(np.min(m.bot)), 3),
            "Spessore medio (m)": round(float(np.mean(spess)), 3) if m.tipo != "taglio" else None,
            "Profondità del taglio (m)": round(float(np.max(m.top) - np.min(m.top)), 3) if m.tipo == "taglio" else None,
            "Strategia": m.qualita.get("strategia"),
            "Base": m.qualita.get("base"),
            "Centro E": round(g.representative_point().x + o["E0"], 2) if g is not None else None,
            "Centro N": round(g.representative_point().y + o["N0"], 2) if g is not None else None,
        })
    return pd.DataFrame(righe)


def scrivi_tabella_volumi(scavo, percorso):
    df = tabella_volumi(scavo)
    fasi = scavo.tabelle.get(sc.S_FASI)
    titoli = {}
    if fasi is not None and "Fase" in fasi.columns:
        for _i, r in fasi.iterrows():
            try:
                titoli[int(float(r["Fase"]))] = r.get("Titolo")
            except (TypeError, ValueError):
                pass
    per_fase = df.groupby("Fase", dropna=False).agg(**{
        "Unità": ("Unità", "count"), "Volume (m³)": ("Volume (m³)", "sum"),
        "Area in pianta (m²)": ("Area in pianta (m²)", "sum")}).reset_index()
    per_fase.insert(1, "Titolo", per_fase["Fase"].map(titoli))
    per_fase = per_fase.sort_values("Fase", ascending=False)
    L = lingua_corrente()
    _ = _traduttore(L)
    if L != "it":
        for c in ("Tipo", "Strategia", "Base"):
            df[c] = df[c].map(lambda v: _(v) if isinstance(v, str) else v)
        df = df.rename(columns=_)
        per_fase = per_fase.rename(columns=_)
    with pd.ExcelWriter(percorso, engine="openpyxl") as w:
        df.to_excel(w, sheet_name=_("Unità"), index=False)
        per_fase.to_excel(w, sheet_name=_("Per fase"), index=False)
        pd.DataFrame({_("Nota"): [
            _("Progetto: {0}", scavo.meta.get('nome', '')),
            _("Volumi calcolati dalle mesh chiuse ricostruite; i tagli sono superfici e non hanno volume."),
            _("«Strategia» dice da quali dati viene la forma (misurata, profondità, impilata, schematica)."),
            _("Coordinate: {0}.", scavo.crs or _("locali"))]}).to_excel(w, sheet_name=_("Note"), index=False)
        for ws in w.book.worksheets:
            for col in ws.columns:
                larg = max(len(str(c.value)) if c.value is not None else 0 for c in col)
                ws.column_dimensions[col[0].column_letter].width = min(max(10, larg + 2), 60)
            ws.freeze_panes = "A2"
    return percorso


# ---------------------------------------------------------------------------------------------- sezioni
class _Mesh:
    """Mesh chiuse delle unità calcolate una volta sola, con il loro ingombro in pianta."""

    def __init__(self, scavo):
        self.scavo, self.m = scavo, {}
        self.ingombri = {u: (m.V2[:, 0].min(), m.V2[:, 1].min(), m.V2[:, 0].max(), m.V2[:, 1].max())
                         for u, m in scavo.modello.unita.items() if len(m.V2)}

    def __call__(self, u):
        if u not in self.m:
            self.m[u] = mesh_unita(self.scavo.modello.unita[u])
        return self.m[u]


def sezione(scavo, a, b, reali=True, mesh=None):
    """Taglia il modello lungo la linea a -> b (coordinate reali se ``reali``, altrimenti locali).

    Ritorna una lista di dict(unita, tipo, colore, aree=[Polygon], linee=[LineString]) in coordinate
    (distanza lungo la sezione, quota assoluta)."""
    if scavo.modello is None:
        raise ValueError("modello 3D non calcolato")
    o = scavo.origine
    A = np.asarray(a, float)[:2] - ((o["E0"], o["N0"]) if reali else (0, 0))
    B = np.asarray(b, float)[:2] - ((o["E0"], o["N0"]) if reali else (0, 0))
    L = float(np.hypot(*(B - A)))
    if L < 1e-6:
        raise ValueError("Sezione di lunghezza nulla")
    uvec = (B - A) / L
    nvec = np.array([-uvec[1], uvec[0]])
    schede = _schede(scavo)
    finestra = box(0, -1e5, L, 1e5)
    mesh = mesh or _Mesh(scavo)
    traccia = LineString([A, B])
    out = []
    for u, m in sorted(scavo.modello.unita.items()):
        ing = mesh.ingombri.get(u)
        if ing is None or not traccia.intersects(box(*ing)):
            continue
        P, F = mesh(u)
        xy = P[:, :2] - A
        s = xy @ nvec
        if s.min() > 0 or s.max() < 0:
            continue
        d = xy @ uvec
        if d.max() < 0 or d.min() > L:
            continue
        segmenti = _taglia(s, d, P[:, 2], F)
        if not segmenti:
            continue
        linee = unary_union(MultiLineString(segmenti))
        aree, tratti = [], []
        if m.tipo != "taglio":
            poligoni = [p for p in polygonize(linee) if p.area > 1e-6]
            if poligoni:
                tot = unary_union(poligoni).intersection(finestra)
                aree = [g for g in getattr(tot, "geoms", [tot]) if g.geom_type == "Polygon" and g.area > 1e-6]
        else:
            lm = (linemerge(linee) if linee.geom_type == "MultiLineString" else linee).intersection(finestra)
            tratti = [g for g in getattr(lm, "geoms", [lm]) if g.geom_type == "LineString" and g.length > 1e-4]
        if aree or tratti:
            tipo = schede.get(u, ("US", {}))[0]
            out.append(dict(unita=int(u), tipo=tipo if m.tipo != "taglio" else "taglio",
                            colore=colore_unita(scavo, u, schede), aree=aree, linee=tratti))
    return out, L


def _taglia(s, d, z, F):
    """Segmenti (d, z) dove il piano s = 0 attraversa i triangoli."""
    S = s[F]
    sopra = S > 0
    n_sopra = sopra.sum(1)
    attraversati = np.where((n_sopra == 1) | (n_sopra == 2))[0]
    seg = []
    for t in attraversati:
        idx = F[t]
        punti = []
        for i, j in ((0, 1), (1, 2), (2, 0)):
            a_, b_ = idx[i], idx[j]
            sa, sb = s[a_], s[b_]
            if (sa > 0) != (sb > 0):
                k = sa / (sa - sb)
                punti.append((round(d[a_] + k * (d[b_] - d[a_]), 6), round(z[a_] + k * (z[b_] - z[a_]), 6)))
        if len(punti) == 2 and punti[0] != punti[1]:
            seg.append(punti)
    return seg


def linee_sezione(scavo):
    """Tracce delle sezioni del GIS: [(nome, (x0, y0), (x1, y1))] in coordinate reali."""
    g = scavo.layers.get(sc.L_SEZIONI)
    out = []
    if g is None:
        return out
    campo = next((c for c in g.columns if c.lower() in ("sezione", "nome", "name", "section_id", "id")), None)
    for i, r in g.reset_index(drop=True).iterrows():
        geom = r.geometry
        if geom is None or geom.is_empty:
            continue
        linee = getattr(geom, "geoms", [geom])
        cc = np.asarray(linee[0].coords)
        if len(cc) < 2 or np.hypot(*(cc[-1][:2] - cc[0][:2])) < 0.05:
            continue
        nome = str(r[campo]).strip() if campo and pd.notna(r[campo]) else ""
        out.append([nome, tuple(cc[0][:2]), tuple(cc[-1][:2])])
    # nomi vuoti o ripetuti (archivi senza identificativo): si numerano
    from collections import Counter
    _ = _traduttore()
    conta = Counter(n for n, _, _ in out)
    for i, x in enumerate(out):
        if x[0] in ("", "0", "—", "nan", "None"):
            x[0] = _("Sezione {0}", i + 1)
        elif conta[x[0]] > 1:
            x[0] = f"{x[0]} ({i + 1})"
    return [tuple(x) for x in out]


def sezioni_centrali(scavo):
    """Due sezioni per il centro dello scavo (E-O e N-S), quando il GIS non ne ha."""
    poli = list({**scavo.poligoni_us(), **scavo.poligoni_usm()}.values())
    if not poli:
        return []
    x0, y0, x1, y1 = unary_union(poli).bounds
    o = scavo.origine
    cx, cy = (x0 + x1) / 2 + o["E0"], (y0 + y1) / 2 + o["N0"]
    _ = _traduttore()
    return [(_("Sezione E-O (centrale)"), (x0 + o["E0"], cy), (x1 + o["E0"], cy)),
            (_("Sezione N-S (centrale)"), (cx, y0 + o["N0"]), (cx, y1 + o["N0"]))]


# ---------------------------------------------------------------------------------------------- SVG
def _svg_testa(w, h):
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}mm" height="{h:.0f}mm" '
            f'viewBox="0 0 {w:.2f} {h:.2f}" font-family="Arial, Helvetica, sans-serif">',
            f'<rect width="{w:.2f}" height="{h:.2f}" fill="#ffffff"/>']


def _esc(t):
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def sezioni_svg(scavo, sezioni, percorso, scala=50, esagerazione=1.0):
    """Disegno delle sezioni in un unico SVG, una sotto l'altra. ``sezioni``: [(nome, a, b)] reali.
    ``scala``: 1:scala (mm sulla carta)."""
    k = 1000.0 / scala                      # mm di carta per metro
    _ = _traduttore()
    calcolate = []
    mesh = _Mesh(scavo)
    for nome, a, b in sezioni:
        tagli, L = sezione(scavo, a, b, mesh=mesh)
        zs = [c[1] for t in tagli for g in t["aree"] + t["linee"] for c in
              (g.exterior.coords if g.geom_type == "Polygon" else g.coords)]
        if not zs:
            continue
        z0, z1 = min(zs) - 0.1, max(zs) + 0.1
        calcolate.append((nome, tagli, L, z0, z1, (z1 - z0) * k * esagerazione + 24, max(L * k, k) + 34))
    if not calcolate:
        raise ValueError("Le sezioni non attraversano nessuna unità")
    # impaginazione a righe: le sezioni corte stanno una accanto all'altra (larghezza come un A3)
    larghezza = max(400.0, max(c[6] for c in calcolate) + 10)
    blocchi, x, y, alt = [], 0.0, 12.0, 0.0
    for nome, tagli, L, z0, z1, h, w in calcolate:
        if x and x + w > larghezza:
            x, y, alt = 0.0, y + alt + 8, 0.0
        blocchi.append((nome, tagli, L, z0, z1, y, h, x))
        x += w
        alt = max(alt, h)
    W, H = larghezza, y + alt + 6
    out = _svg_testa(W, H)
    titolo = _("{0} — sezioni dal modello 3D, scala 1:{1}", scavo.meta.get("nome") or _("Scavo"), scala)
    if esagerazione != 1:
        titolo += _(", altezze ×{0}", f"{esagerazione:g}")
    out.append(f'<text x="10" y="8" font-size="4" font-weight="bold">{_esc(titolo)}</text>')
    for nome, tagli, L, z0, z1, y0, h, x0 in blocchi:
        X = lambda d, x0=x0: x0 + 20 + d * k
        Y = lambda z, y0=y0, z1=z1: y0 + 12 + (z1 - z) * k * esagerazione
        out.append(f'<g><text x="{X(0):.2f}" y="{y0 + 6:.2f}" font-size="3.5" font-weight="bold">{_esc(nome)}</text>')
        # griglia delle quote ogni 0,5 m
        passo = 0.5 if (z1 - z0) < 6 else 1.0
        z = math.ceil(z0 / passo) * passo
        while z <= z1:
            out.append(f'<line x1="{X(0) - 2:.2f}" x2="{X(L) + 2:.2f}" y1="{Y(z):.2f}" y2="{Y(z):.2f}" stroke="#ddd" stroke-width="0.15"/>'
                       f'<text x="{X(0) - 3:.2f}" y="{Y(z) + 1:.2f}" font-size="2.2" text-anchor="end" fill="#777">{z:.2f}</text>')
            z += passo
        for t in tagli:
            for g in t["aree"]:
                pts = " ".join(f"{X(x):.2f},{Y(y):.2f}" for x, y in g.exterior.coords)
                buchi = "".join(" M" + " L".join(f"{X(x):.2f},{Y(y):.2f}" for x, y in r.coords) + " Z" for r in g.interiors)
                out.append(f'<path d="M{pts.replace(" ", " L")} Z{buchi}" fill="{t["colore"]}" fill-opacity="0.85" '
                           f'stroke="#222" stroke-width="0.25" fill-rule="evenodd"><title>{_esc(_("US {0}", t["unita"]))}</title></path>')
            for g in t["linee"]:
                pts = " L".join(f"{X(x):.2f},{Y(y):.2f}" for x, y in g.coords)
                out.append(f'<path d="M{pts}" fill="none" stroke="#111" stroke-width="0.35" stroke-dasharray="1.2 0.8">'
                           f'<title>{_esc(_("US {0} (taglio)", t["unita"]))}</title></path>')
        for t in tagli:                      # etichette sopra i colori
            for g in t["aree"]:
                if g.area * k * k * esagerazione > 20:
                    c = g.representative_point()
                    out.append(f'<text x="{X(c.x):.2f}" y="{Y(c.y) + 0.9:.2f}" font-size="2.4" text-anchor="middle">{t["unita"]}</text>')
        # scala grafica: 1 m
        out.append(f'<line x1="{X(0):.2f}" x2="{X(1):.2f}" y1="{y0 + h - 4:.2f}" y2="{y0 + h - 4:.2f}" stroke="#000" stroke-width="0.6"/>'
                   f'<text x="{X(1) + 2:.2f}" y="{y0 + h - 3:.2f}" font-size="2.4">1 m</text>')
        out.append(f'<text x="{X(0):.2f}" y="{y0 + h - 8:.2f}" font-size="2.6" text-anchor="middle">A</text>'
                   f'<text x="{X(L):.2f}" y="{y0 + h - 8:.2f}" font-size="2.6" text-anchor="middle">B</text></g>')
    out.append("</svg>")
    with open(percorso, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    return percorso


def pianta_svg(scavo, percorso, scala=200, fasi=None):
    """Piante per fase in un unico SVG: un riquadro per fase, dalla più recente, con il limite dello
    scavo e i numeri delle unità. ``fasi``: elenco delle fasi da disegnare (tutte se None)."""
    schede = _schede(scavo)
    poli = {**scavo.poligoni_us(), **scavo.poligoni_usm()}
    if not poli:
        raise ValueError("Nessuna unità da disegnare")
    per_fase = {}
    for u in poli:
        f = _fase(schede.get(u, ("", {}))[1]) if u in schede else 0
        if fasi is None or f in fasi:
            per_fase.setdefault(f, []).append(u)
    if not per_fase:
        raise ValueError("Nessuna unità nelle fasi indicate")
    _ = _traduttore()
    titoli = {}
    t = scavo.tabelle.get(sc.S_FASI)
    if t is not None and "Fase" in t.columns:
        for _i, r in t.iterrows():
            try:
                titoli[int(float(r["Fase"]))] = str(r.get("Titolo") or "")
            except (TypeError, ValueError):
                pass
    area = scavo.limiti() if hasattr(scavo, "limiti") else None
    tutte = unary_union(list(poli.values()))
    x0, y0, x1, y1 = tutte.bounds
    if area is not None and not area.is_empty:
        area = area.intersection(box(x0, y0, x1, y1))
    k = 1000.0 / scala
    pw, ph = (x1 - x0) * k + 16, (y1 - y0) * k + 22
    col = 2 if pw < 260 else 1
    fasi_ord = sorted(per_fase, reverse=True)
    righe = math.ceil(len(fasi_ord) / col)
    W, H = col * pw + 20, righe * ph + 30
    out = _svg_testa(W, H)
    o = scavo.origine
    titolo = _("{0} — piante per fase, scala 1:{1}", scavo.meta.get("nome") or _("Scavo"), scala)
    out.append(f'<text x="10" y="9" font-size="4" font-weight="bold">{_esc(titolo)}</text>')
    livello = st.livelli_dal_basso(scavo.rapporti())
    for n, f in enumerate(fasi_ord):
        ox, oy = 10 + (n % col) * pw, 16 + (n // col) * ph
        X = lambda x, ox=ox: ox + 8 + (x - x0) * k
        Y = lambda y, oy=oy: oy + 10 + (y1 - y) * k
        out.append(f'<g><text x="{ox + 8:.2f}" y="{oy + 6:.2f}" font-size="3.2" font-weight="bold">{_esc(_("Fase {0}", f))}'
                   f'{" · " + _esc(titoli[f]) if titoli.get(f) else ""}</text>')
        def tracciato(g):
            d = ""
            for p in getattr(g, "geoms", [g]):
                if p.geom_type != "Polygon":
                    continue
                for r in [p.exterior, *p.interiors]:
                    d += "M" + " L".join(f"{X(x):.2f},{Y(y):.2f}" for x, y in r.coords) + " Z "
            return d
        if area is not None and not area.is_empty:
            linee = getattr(area, "geoms", [area])
            for ln in linee:
                if ln.is_empty or ln.geom_type not in ("LineString", "LinearRing", "Polygon"):
                    continue
                cc = list(ln.coords) if hasattr(ln, "coords") else list(ln.exterior.coords)
                out.append('<path d="M' + " L".join(f"{X(x):.2f},{Y(y):.2f}" for x, y in cc) +
                           '" fill="none" stroke="#999" stroke-width="0.25"/>')
        for u in sorted(per_fase[f], key=lambda u: (livello.get(u, 0), u)):
            tipo, r = schede.get(u, ("US", {}))
            neg = str(r.get(sc.C_TIPO, "")).lower() == "negativa" if len(r) else False
            if neg:
                out.append(f'<path d="{tracciato(poli[u])}" fill="none" stroke="#111" stroke-width="0.3" '
                           f'stroke-dasharray="1 0.7"><title>{_esc(_(tipo + " {0}", u))}</title></path>')
            else:
                out.append(f'<path d="{tracciato(poli[u])}" fill="{colore_unita(scavo, u, schede)}" fill-opacity="0.8" '
                           f'stroke="#222" stroke-width="0.2" fill-rule="evenodd"><title>{_esc(_(tipo + " {0}", u))}</title></path>')
        visti = []
        for u in sorted(per_fase[f], key=lambda u: -poli[u].area):
            c = poli[u].representative_point()
            if poli[u].area * k * k < 6 or any(abs(c.x - a) * k < 6 and abs(c.y - b) * k < 2.5 for a, b in visti):
                continue
            visti.append((c.x, c.y))
            out.append(f'<text x="{X(c.x):.2f}" y="{Y(c.y) + 0.8:.2f}" font-size="2.2" text-anchor="middle">{u}</text>')
        out.append("</g>")
    m = 5 if scala >= 100 else 1
    out.append(f'<line x1="10" x2="{10 + k * m:.2f}" y1="{H - 8:.2f}" y2="{H - 8:.2f}" stroke="#000" stroke-width="0.6"/>'
               f'<text x="{12 + k * m:.2f}" y="{H - 7:.2f}" font-size="2.4">{m} m</text>'
               f'<text x="{W - 10:.2f}" y="{H - 7:.2f}" font-size="2.4" text-anchor="end" fill="#555">'
               f'E {x0 + o["E0"]:.1f}–{x1 + o["E0"]:.1f}, N {y0 + o["N0"]:.1f}–{y1 + o["N0"]:.1f}'
               f'{" — " + _esc(scavo.crs) if scavo.crs else ""}  ↑ N</text>')
    out.append("</svg>")
    with open(percorso, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    return percorso


# ---------------------------------------------------------------------------------------------- DXF
class _DXF:
    """Scrittore DXF R12 minimo: layer con colore, polilinee 2D/3D chiuse, testi."""

    def __init__(self):
        self.layers, self.ent = {}, []

    def layer(self, nome, rgb="#808080"):
        nome = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(nome))[:60] or "0"
        if nome not in self.layers:
            self.layers[nome] = _aci(rgb)
        return nome

    def polilinea(self, layer, punti, chiusa=True, z=None):
        e = ["0", "POLYLINE", "8", layer, "66", "1", "70", "9" if (chiusa and z is not None) else
             ("8" if z is not None else ("1" if chiusa else "0")), "10", "0", "20", "0", "30", "0"]
        for p in punti:
            e += ["0", "VERTEX", "8", layer, "10", f"{p[0]:.4f}", "20", f"{p[1]:.4f}", "30",
                  f"{(p[2] if len(p) > 2 else (z or 0)):.4f}", "70", "32" if z is not None else "0"]
        e += ["0", "SEQEND", "8", layer]
        self.ent += e

    def testo(self, layer, x, y, testo, h=0.25):
        self.ent += ["0", "TEXT", "8", layer, "10", f"{x:.4f}", "20", f"{y:.4f}", "30", "0", "40", f"{h:.3f}",
                     "1", str(testo), "72", "1", "11", f"{x:.4f}", "21", f"{y:.4f}", "31", "0"]

    def salva(self, percorso):
        out = ["0", "SECTION", "2", "HEADER", "9", "$ACADVER", "1", "AC1009", "0", "ENDSEC",
               "0", "SECTION", "2", "TABLES", "0", "TABLE", "2", "LAYER", "70", str(len(self.layers))]
        for n, c in self.layers.items():
            out += ["0", "LAYER", "2", n, "70", "0", "62", str(c), "6", "CONTINUOUS"]
        out += ["0", "ENDTAB", "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"] + self.ent + ["0", "ENDSEC", "0", "EOF"]
        with open(percorso, "w", encoding="cp1252", errors="replace", newline="\r\n") as f:
            f.write("\n".join(out) + "\n")
        return percorso


_ACI = {1: (255, 0, 0), 2: (255, 255, 0), 3: (0, 255, 0), 4: (0, 255, 255), 5: (0, 0, 255), 6: (255, 0, 255),
        7: (255, 255, 255), 8: (128, 128, 128), 9: (192, 192, 192), 30: (255, 127, 0), 40: (255, 191, 0),
        52: (191, 165, 0), 94: (0, 127, 0), 140: (0, 127, 255), 150: (0, 63, 127), 200: (127, 0, 255),
        14: (127, 0, 0), 34: (127, 63, 0), 42: (127, 95, 0), 54: (127, 127, 0), 33: (153, 76, 0)}


def _aci(hx):
    r, g, b = (int(v * 255) for v in _hex_rgb(hx))
    return min(_ACI, key=lambda k: sum((a - c) ** 2 for a, c in zip(_ACI[k], (r, g, b))))


def pianta_dxf(scavo, percorso):
    """Poligoni delle unità in coordinate reali, un layer per fase (e uno per i tagli), con i numeri.
    Le quote del tetto ricostruito sono nei vertici (polilinee 3D) quando il modello c'è."""
    schede = _schede(scavo)
    poli = {**scavo.poligoni_us(), **scavo.poligoni_usm()}
    o = scavo.origine
    dxf = _DXF()
    _ = _traduttore()
    fasi = scavo.tabelle.get(sc.S_FASI)
    titoli = {}
    if fasi is not None and "Fase" in fasi.columns:
        for _i, r in fasi.iterrows():
            try:
                titoli[int(float(r["Fase"]))] = str(r.get("Titolo") or "")
            except (TypeError, ValueError):
                pass
    for u, g in sorted(poli.items()):
        tipo, r = schede.get(u, ("US", {}))
        f = _fase(r) if len(r) else 0
        neg = str(r.get(sc.C_TIPO, "")).lower() == "negativa" if len(r) else False
        nome = _("TAGLI") if neg else (_("USM_fase_{0}", f) if tipo == "USM" else _("US_fase_{0}_{1}", f, titoli.get(f, '')))
        lay = dxf.layer(nome, "#333333" if neg else colore_unita(scavo, u, schede))
        for p in getattr(g, "geoms", [g]):
            for ring in [p.exterior, *p.interiors]:
                cc = np.asarray(ring.coords)[:-1]
                dxf.polilinea(lay, [(x + o["E0"], y + o["N0"]) for x, y in cc[:, :2]], chiusa=True)
        c = g.representative_point()
        dxf.testo(dxf.layer(_("NUMERI"), "#000000"), c.x + o["E0"], c.y + o["N0"], _("USM {0}", u) if tipo == "USM" else u)
    return dxf.salva(percorso)


def sezioni_dxf(scavo, sezioni, percorso, distanza=2.0):
    """Sezioni come disegno 2D: x = distanza lungo la sezione, y = quota; una sotto l'altra."""
    dxf = _DXF()
    _ = _traduttore()
    schede = _schede(scavo)
    base_y = 0.0
    mesh = _Mesh(scavo)
    for nome, a, b in sezioni:
        tagli, L = sezione(scavo, a, b, mesh=mesh)
        if not tagli:
            continue
        zs = [c[1] for t in tagli for g in t["aree"] + t["linee"]
              for c in (g.exterior.coords if g.geom_type == "Polygon" else g.coords)]
        z1 = max(zs)
        dy = base_y - z1                      # la sezione successiva va sotto
        lay_t = dxf.layer(_("TITOLI"), "#000000")
        dxf.testo(lay_t, 0, z1 + dy + 0.6, f"{nome}  (A -> B, {L:.2f} m)", h=0.3)
        for t in tagli:
            tipo, r = schede.get(t["unita"], ("US", {}))
            f = _fase(r) if len(r) else 0
            lay = dxf.layer(_("TAGLI") if t["tipo"] == "taglio" else _(("USM" if tipo == "USM" else "US") + "_fase_{0}", f), t["colore"])
            for g in t["aree"]:
                for ring in [g.exterior, *g.interiors]:
                    dxf.polilinea(lay, [(x, y + dy) for x, y in list(ring.coords)[:-1]], chiusa=True)
                c = g.representative_point()
                dxf.testo(dxf.layer(_("NUMERI"), "#000000"), c.x, c.y + dy, t["unita"], h=0.12)
            for g in t["linee"]:
                dxf.polilinea(lay, [(x, y + dy) for x, y in g.coords], chiusa=False)
        dxf.polilinea(dxf.layer(_("RIFERIMENTI"), "#808080"), [(0, z1 + dy + 0.3), (L, z1 + dy + 0.3)], chiusa=False)
        dxf.testo(lay_t, 0, z1 + dy + 0.35, "A", h=0.2)
        dxf.testo(lay_t, L, z1 + dy + 0.35, "B", h=0.2)
        base_y = min(zs) + dy - distanza
    return dxf.salva(percorso)
