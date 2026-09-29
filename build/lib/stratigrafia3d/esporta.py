# -*- coding: utf-8 -*-
"""Esportazioni: modello per il visualizzatore (JSON), pagina HTML autonoma, glTF binario (GLB)."""
import base64
import json
import os
import struct
from importlib import resources

import numpy as np
import pandas as pd

from . import schema as sc
from . import stratigrafia as st
from .mesh import mesh_chiusa


def _json_val(v, nd=3):
    if v is None:
        return None
    if isinstance(v, (pd.Timestamp,)) or hasattr(v, "strftime"):
        try:
            return v.strftime("%d/%m/%Y")
        except ValueError:
            return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        return None if np.isnan(v) else round(float(v), nd)
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def _rec(row):
    out = {}
    for k, v in row.items():
        v = _json_val(v)
        if v is not None:
            out[str(k)] = v
    return out


def _b64(a, dt):
    return base64.b64encode(np.ascontiguousarray(a, dtype=dt).tobytes()).decode()


def mesh_unita(m):
    """Vertici (assoluti, locali in pianta) e triangoli della mesh finale di un'unità."""
    if m.tipo == "taglio":
        return np.c_[m.V2, m.top], m.F
    return mesh_chiusa(m.V2, m.F, m.top, m.bot)


def dati_visualizzatore(scavo):
    """Dizionario completo letto dal visualizzatore web (stessa struttura del prototipo)."""
    if scavo.modello is None:
        raise ValueError("modello 3D non calcolato: eseguire prima la ricostruzione")
    o = scavo.origine
    Z0 = o["Z0"]
    rap = scavo.rapporti()
    livello = st.livelli_dal_basso(rap)
    tab = scavo.tabelle
    meshes = []
    for u, m in sorted(scavo.modello.unita.items()):
        P, F = mesh_unita(m)
        P = P.copy()
        P[:, 2] -= Z0
        Pq = np.round(P * 1000).astype("<u2")
        geom = (scavo.poligoni_us().get(u) if m.tipo != "usm" else scavo.poligoni_usm().get(u))
        outline = []
        if geom is not None:
            for p in getattr(geom, "geoms", [geom]):
                for ring in [p.exterior, *p.interiors]:
                    outline.append(np.round(np.asarray(ring.coords)[:, :2], 3).ravel().tolist())
            c = geom.representative_point()
            lab = [round(c.x, 3), round(c.y, 3), round(float(np.max(m.top) - Z0), 3)]
        else:
            lab = [float(m.V2[:, 0].mean()), float(m.V2[:, 1].mean()), float(np.max(m.top) - Z0)]
        meshes.append(dict(id=int(u), kind=m.tipo, pos=_b64(Pq, "<u2"),
                           idx=_b64(F, "<u2" if len(P) < 65536 else "<u4"), nv=len(P), ntop=len(m.V2), nt=len(F),
                           i32=bool(len(P) >= 65536), outline=outline, label=lab,
                           zmin=round(float(np.min(m.bot)), 3), zmax=round(float(np.max(m.top)), 3),
                           vol=round(m.volume(), 3), qual=m.qualita))
    recs = {}
    for u, r in scavo.schede_us().items():
        recs[u] = _rec(r); recs[u]["_tipo"] = "US"
    for u, r in scavo.schede_usm().items():
        recs[u] = _rec(r); recs[u]["_tipo"] = "USM"
    q = scavo.quote_locali()
    for u in recs:
        recs[u]["_livello"] = int(livello.get(u, 0))
        if u in scavo.modello.unita:
            recs[u]["_qualita"] = scavo.modello.unita[u].qualita
        qq = q[q.us == u]
        if len(qq):
            if recs[u]["_tipo"] == "US":
                recs[u].setdefault("Quota max (m)", round(float(qq.z.max()), 3))
                recs[u].setdefault("Quota min (m)", round(float(qq.z.min()), 3))
            else:
                ra = qq[qq.tipo == sc.Q_RASATURA].z
                if len(ra):
                    recs[u].setdefault("Quota rasatura max", round(float(ra.max()), 3))
                    recs[u].setdefault("Quota rasatura min", round(float(ra.min()), 3))
                    base = recs[u].get(sc.C_BASE_USM)
                    if base is not None:
                        recs[u].setdefault("Altezza conservata media (m)", round(float(ra.mean() - base), 2))

    def tabella(nome):
        df = tab.get(nome)
        return [] if df is None else [_rec(r) for _, r in df.iterrows()]

    rs, camp = tabella(sc.S_RS), tabella(sc.S_CAMPIONI)
    for r in rs + camp:
        if all(k in r for k in ("E (m)", "N (m)", "Quota (m)")):
            r["_xyz"] = [round(r["E (m)"] - o["E0"], 3), round(r["N (m)"] - o["N0"], 3), round(r["Quota (m)"] - Z0, 3)]
    rs = [r for r in rs if "_xyz" in r]
    camp = [r for r in camp if "_xyz" in r]
    quote_arr = q[["x", "y", "z"]].to_numpy().copy()
    quote_arr[:, 2] -= Z0
    profili = []
    prof = scavo.layers.get(sc.L_PROFILI)
    if prof is not None:
        for _, r in prof.iterrows():
            c = np.asarray(r.geometry.coords, float).copy()
            if c.shape[1] < 3:
                continue
            c[:, 0] -= o["E0"]; c[:, 1] -= o["N0"]; c[:, 2] -= Z0
            profili.append(dict(s=r[sc.F_SEZIONE], us=int(r[sc.F_US]), t=r[sc.F_INTERFACCIA],
                                c=np.round(c, 3).ravel().tolist()))
    sezioni = []
    if sc.L_SEZIONI in scavo.layers:
        for _, r in scavo.layers[sc.L_SEZIONI].iterrows():
            c = np.asarray(r.geometry.coords)
            sezioni.append(dict(nome=r[sc.F_SEZIONE], a=[round(c[0, 0] - o["E0"], 3), round(c[0, 1] - o["N0"], 3)],
                                b=[round(c[-1, 0] - o["E0"], 3), round(c[-1, 1] - o["N0"], 3)]))
    sez_draw = []
    if sc.L_SEZ_DISEGNO in scavo.layers:
        for _, r in scavo.layers[sc.L_SEZ_DISEGNO].iterrows():
            for p in getattr(r.geometry, "geoms", [r.geometry]):
                sez_draw.append(dict(s=r[sc.F_SEZIONE], us=int(r[sc.F_US]), lim=r.get("limite_inferiore", ""),
                                     c=np.round(np.asarray(p.exterior.coords), 3).ravel().tolist()))
    limiti = []
    if sc.L_AREA in scavo.layers:
        for _, r in scavo.layers[sc.L_AREA].iterrows():
            g = scavo.locale(r.geometry)
            limiti.append(dict(nome=r.get("nome", ""), tipo=r.get("tipo", ""),
                               c=np.round(np.asarray(g.exterior.coords)[:, :2], 3).ravel().tolist()))
    info = tab.get("Info")
    sito = scavo.meta.get("nome", "Scavo")
    if info is not None and len(info.columns):
        sito = str(info.columns[0]).replace("Database di scavo – ", "")
    return dict(
        sito=sito, origine=dict(E0=o["E0"], N0=o["N0"], Z0=Z0, crs=scavo.crs or ""),
        meshes=meshes, livello_max=int(max(livello.values()) if livello else 0),
        fasi=tabella(sc.S_FASI), schede=recs,
        rapporti=[[int(a), d["t"], int(b)] for a, b, d in rap.grafo.edges(data=True)] +
                 [[int(a), "si lega a", int(b)] for a, b in rap.contemporanei],
        materiali=tabella(sc.S_MATERIALI), rs=rs, campioni=camp, documentazione=tabella(sc.S_DOC),
        quote=dict(xyz=_b64(quote_arr, "<f4"), meta=[[int(a), b] for a, b in zip(q.us, q.tipo)]),
        profili=profili, sezioni=sezioni, sez_draw=sez_draw, limiti=limiti, harris=st.harris(rap),
    )


def visualizzatore(scavo, percorso_html):
    """Scrive la pagina web autonoma del visualizzatore 3D."""
    data = json.dumps(dati_visualizzatore(scavo), ensure_ascii=False, separators=(",", ":"), default=_json_val)
    tpl = resources.files("stratigrafia3d.visualizzatore").joinpath("modello.html").read_text(encoding="utf-8")
    os.makedirs(os.path.dirname(os.path.abspath(percorso_html)), exist_ok=True)
    with open(percorso_html, "w", encoding="utf-8") as f:
        f.write(tpl.replace("/*__DATA__*/", data.replace("</", "<\\/")))
    return percorso_html


# ---------------------------------------------------------------------------- GLB
def _normali(P, F):
    n = np.zeros_like(P)
    fn = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
    for k in range(3):
        np.add.at(n, F[:, k], fn)
    L = np.linalg.norm(n, axis=1, keepdims=True)
    L[L == 0] = 1
    return n / L


def _hex_rgb(h, default=(0.6, 0.6, 0.6)):
    try:
        h = str(h).lstrip("#")
        return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except (ValueError, TypeError):
        return default


def glb(scavo, percorso, esploso=0.0):
    """Esporta il modello in glTF binario (.glb), un nodo per unità (Y in alto, metri).
    Si apre in Blender, MeshLab, visualizzatori web. ``esploso``: distanza verticale tra livelli."""
    if scavo.modello is None:
        raise ValueError("modello 3D non calcolato")
    o = scavo.origine
    livello = st.livelli_dal_basso(scavo.rapporti())
    schede = {**{u: ("US", r) for u, r in scavo.schede_us().items()},
              **{u: ("USM", r) for u, r in scavo.schede_usm().items()}}
    blob = bytearray()
    views, accessors, meshes, nodes, materials = [], [], [], [], []

    def add_view(data, target):
        while len(blob) % 4:
            blob.append(0)
        off = len(blob)
        blob.extend(data)
        views.append(dict(buffer=0, byteOffset=off, byteLength=len(data), target=target))
        return len(views) - 1

    for u, m in sorted(scavo.modello.unita.items()):
        P, F = mesh_unita(m)
        # locali -> glTF: x = est, y = quota relativa, z = -nord
        G = np.c_[P[:, 0], P[:, 2] - o["Z0"] + livello.get(u, 0) * esploso, -P[:, 1]].astype("<f4")
        F = F.astype("<u4")
        N = _normali(G.astype(float), F).astype("<f4")
        vp = add_view(G.tobytes(), 34962)
        accessors.append(dict(bufferView=vp, componentType=5126, count=len(G), type="VEC3",
                              min=G.min(0).tolist(), max=G.max(0).tolist()))
        ap = len(accessors) - 1
        vn = add_view(N.tobytes(), 34962)
        accessors.append(dict(bufferView=vn, componentType=5126, count=len(N), type="VEC3"))
        an = len(accessors) - 1
        vi = add_view(F.ravel().tobytes(), 34963)
        accessors.append(dict(bufferView=vi, componentType=5125, count=F.size, type="SCALAR"))
        ai = len(accessors) - 1
        tipo, r = schede.get(u, ("US", {}))
        col = _hex_rgb(r.get(sc.C_COLORE) if tipo == "US" else r.get("Colore HEX", "#c9c2b4"),
                       (0.79, 0.76, 0.71) if tipo == "USM" else (0.6, 0.55, 0.5))
        mat = dict(name=f"{tipo} {u}", doubleSided=m.tipo == "taglio",
                   pbrMetallicRoughness=dict(baseColorFactor=[*col, 0.35 if m.tipo == "taglio" else 1.0],
                                             metallicFactor=0.0, roughnessFactor=0.9))
        if m.tipo == "taglio":
            mat["alphaMode"] = "BLEND"
        materials.append(mat)
        meshes.append(dict(name=f"{tipo} {u}", primitives=[dict(attributes=dict(POSITION=ap, NORMAL=an),
                                                                     indices=ai, material=len(materials) - 1)]))
        extras = {k: _json_val(v) for k, v in dict(r).items() if _json_val(v) is not None} if len(r) else {}
        extras.update(dict(unita=int(u), tipo_modello=m.tipo, livello=int(livello.get(u, 0)),
                           volume_m3=round(m.volume(), 3), qualita=m.qualita))
        nodes.append(dict(name=f"{tipo} {u}", mesh=len(meshes) - 1, extras=extras))
    gltf = dict(asset=dict(version="2.0", generator="stratigrafia3d"),
                scene=0, scenes=[dict(name=scavo.meta.get("nome", "scavo"), nodes=list(range(len(nodes))),
                                      extras=dict(origine=o, crs=scavo.crs))],
                nodes=nodes, meshes=meshes, materials=materials, accessors=accessors, bufferViews=views,
                buffers=[dict(byteLength=len(blob))])
    js = json.dumps(gltf, ensure_ascii=False, separators=(",", ":"), default=_json_val).encode("utf-8")
    js += b" " * ((4 - len(js) % 4) % 4)
    while len(blob) % 4:
        blob.append(0)
    total = 12 + 8 + len(js) + 8 + len(blob)
    with open(percorso, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, total))
        f.write(struct.pack("<II", len(js), 0x4E4F534A)); f.write(js)
        f.write(struct.pack("<II", len(blob), 0x004E4942)); f.write(bytes(blob))
    return percorso
