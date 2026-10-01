# -*- coding: utf-8 -*-
"""Dati del visualizzatore web: forma compatta delle mesh (piante, quote e contorni senza doppioni),
ricostruzione esatta delle mesh e dimensioni molto minori del formato precedente."""
import base64
import json
import os
import re
import shutil
import subprocess

import numpy as np
import pytest

from stratigrafia3d import esporta

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# progetto reale grande (3028 unità), se disponibile su questa macchina
TEC05 = os.environ.get("S3D_TEC05", "/tmp/claude-0/-home-claude-3dstratigraphy-app-development/"
                       "4ba2ea40-837f-59ee-84c1-f903439d9f5a/scratchpad/t5/t5_TEC05.scavo")


def _js(d):
    return json.dumps(d, ensure_ascii=False, separators=(",", ":"), default=esporta._json_val)


def _dimensione_formato_precedente(scavo, quant):
    """Byte delle sole mesh nel formato precedente: posizioni e indici della mesh chiusa per unità."""
    Z0 = scavo.origine["Z0"]
    tot = 0
    for _, m in sorted(scavo.modello.unita.items()):
        P, F = esporta.mesh_unita(m)
        P = P.copy()
        P[:, 2] -= Z0
        tot += len(esporta._b64(np.clip(np.round(P / quant), 0, 65535), "<u2"))
        tot += len(esporta._b64(F, "<u2" if len(P) < 65536 else "<u4"))
    return tot


def _decodifica(d, mesh):
    """Ricostruisce la mesh di un'unità dai dati compatti, come fa il visualizzatore."""
    p = d["piante"][mesh["g"]]
    xy = np.frombuffer(base64.b64decode(p["xy"]), "<u2").reshape(-1, 2)
    F = np.frombuffer(base64.b64decode(p["f"]), {1: "u1", 2: "<u2", 4: "<u4"}[p["t"]]).reshape(-1, 3).astype(int)
    zt = np.frombuffer(base64.b64decode(d["zeta"][mesh["zt"]]), "<u2")
    zb = np.frombuffer(base64.b64decode(d["zeta"][mesh["zb"]]), "<u2") if "zb" in mesh else None
    return xy, F, zt, zb


def _verifica(scavo, d):
    U = scavo.modello.unita
    quant, Z0 = d["quant"], scavo.origine["Z0"]
    assert sorted(m["id"] for m in d["meshes"]) == sorted(int(u) for u in U)
    for m in d["meshes"]:
        u = U[m["id"]]
        # campi non usati dal visualizzatore: tolti
        assert not {"outline", "nv", "ntop", "nt", "i32", "idx", "qual", "zmin", "zmax"} & set(m)
        xy, F, zt, zb = _decodifica(d, m)
        assert len(xy) == len(u.V2) and np.array_equal(F, np.asarray(u.F).reshape(-1, 3))
        assert np.abs(xy * quant - u.V2).max(initial=0) <= quant / 2 + 1e-9
        assert np.abs(zt * quant - (u.top - Z0)).max(initial=0) <= quant / 2 + 1e-9
        assert (zb is None) == (u.tipo == "taglio")
        if zb is not None:
            assert np.abs(zb * quant - (u.bot - Z0)).max(initial=0) <= quant / 2 + 1e-9
            # stessa mesh chiusa del formato precedente: tetto, base, pareti
            P, Fc = esporta.mesh_chiusa(xy * quant, F, zt * quant, zb * quant)
            P0, F0 = esporta.mesh_unita(u)
            assert len(P) == len(P0) and len(Fc) == len(F0)
        # riquadro quantizzato (xyz minimi e massimi)
        r = np.frombuffer(base64.b64decode(m["pos"]), "<u2").reshape(-1, 3)
        if len(xy):
            assert r.shape == (2, 3) and (r[0, :2] == xy.min(0)).all() and (r[1, :2] == xy.max(0)).all()
            zz = np.r_[zt, zb if zb is not None else []]
            assert r[0, 2] == zz.min() and r[1, 2] == zz.max()


def test_mesh_compatte_demo(progetto):
    s, _ = progetto
    d = esporta.dati_visualizzatore(s)
    _verifica(s, d)
    # i riempimenti che ereditano il poligono del taglio condividono la pianta
    assert len(d["piante"]) < len(d["meshes"])
    assert len(d["zeta"]) < sum(1 + ("zb" in m) for m in d["meshes"])
    nuove = sum(len(_js(d[k])) for k in ("meshes", "piante", "zeta", "contorni"))
    prima = _dimensione_formato_precedente(s, d["quant"])
    assert nuove < 0.6 * prima, (nuove, prima)


def test_contorni_quantizzati(progetto):
    """Contorni dei poligoni: interi a 16 bit in base64, ritrovati entro mezzo passo di quantizzazione."""
    s, _ = progetto
    d = esporta.dati_visualizzatore(s)
    quant = d["quant"]
    poli_us, poli_usm = s.poligoni_us(), s.poligoni_usm()
    controllati = 0
    for m in d["meshes"]:
        geom = poli_usm.get(m["id"]) if m["kind"] == "usm" else poli_us.get(m["id"])
        if geom is None:
            assert "o" not in m
            continue
        c = d["contorni"][m["o"]]
        xy = np.frombuffer(base64.b64decode(c["xy"]), "<u2").reshape(-1, 2) * quant
        assert sum(c["anelli"]) == len(xy)
        anelli = np.split(xy, np.cumsum(c["anelli"])[:-1])
        orig = [np.asarray(r.coords)[:, :2] for p in getattr(geom, "geoms", [geom]) for r in [p.exterior, *p.interiors]]
        assert len(anelli) == len(orig)
        for a, b in zip(anelli, orig):
            assert a.shape == b.shape and np.abs(a - b).max() <= quant / 2 + 1e-9
        controllati += 1
    assert controllati > 0
    # contorni uguali (riempimento con il poligono del taglio) inviati una volta sola
    assert len(d["contorni"]) <= controllati


def test_schede_qualita_ridotta(progetto):
    s, _ = progetto
    d = esporta.dati_visualizzatore(s)
    q = [r["_qualita"] for r in d["schede"].values() if isinstance(r.get("_qualita"), dict)]
    assert q and all(set(x) <= esporta._QUALITA_VIS for x in q)
    assert any("strategia" in x or "punti_tetto" in x or "punti_taglio" in x for x in q)


def test_pagina_visualizzatore_costruzione_progressiva(progetto):
    s, _ = progetto
    html = esporta.pagina_visualizzatore(s, "web", "it")
    assert '"piante"' in html and '"zeta"' in html
    tpl = open(os.path.join(RADICE, "src/stratigrafia3d/visualizzatore/modello.html"), encoding="utf-8").read()
    # avanzamento a schermo, tradotto con T(...); nessun EdgesGeometry (spigoli calcolati sulla pianta)
    assert 'T("Preparazione delle unità… {0} di {1}"' in tpl and 'id="avanz"' in tpl
    assert "new THREE.EdgesGeometry" not in tpl and "requestAnimationFrame" in tpl


@pytest.mark.skipif(shutil.which("node") is None, reason="node non disponibile")
def test_sintassi_script_visualizzatore(tmp_path):
    tpl = open(os.path.join(RADICE, "src/stratigrafia3d/visualizzatore/modello.html"), encoding="utf-8").read()
    js = re.findall(r"<script>(.*?)</script>", tpl, flags=re.S)[-1]
    f = tmp_path / "v.js"
    f.write_text(js, encoding="utf-8")
    r = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


@pytest.mark.skipif(not os.path.exists(TEC05), reason="progetto TEC05 non disponibile")
def test_progetto_grande_tec05(tmp_path):
    from stratigrafia3d import Scavo
    p = str(tmp_path / "tec05.scavo")
    shutil.copy(TEC05, p)              # il file originale resta intatto
    s = Scavo.apri(p)
    d = esporta.dati_visualizzatore(s)
    _verifica(s, d)
    nuove = sum(len(_js(d[k])) for k in ("meshes", "piante", "zeta", "contorni"))
    prima = _dimensione_formato_precedente(s, d["quant"])
    assert nuove < 0.2 * prima, (nuove, prima)
    assert len(_js(d)) < 15_000_000
