"""Test sullo scavo dimostrativo: il modello di verità permette di misurare l'errore della ricostruzione."""
import json
import struct

import numpy as np
import shapely
from shapely import contains_xy

from stratigrafia3d import Scavo, ricostruisci, da_ricalcolare, esporta
from stratigrafia3d.demo import modello_verita as mv


def test_verifica_senza_errori(progetto):
    s, _ = progetto
    assert not [p for p in s.verifica() if p.livello == "errore"]


def test_tutte_le_unita_ricostruite(progetto):
    s, _ = progetto
    attese = set(s.poligoni_us()) | set(s.poligoni_usm())
    assert set(s.modello.unita) == attese


def _interni(s, u, V2, margine=0.15):
    g = (s.poligoni_us().get(u) or s.poligoni_usm().get(u)).buffer(-margine)
    return contains_xy(g, V2[:, 0], V2[:, 1])


def test_accuratezza_rispetto_al_modello_di_verita(demo, progetto):
    """Scarto mediano del tetto sotto 3 cm per almeno il 90% delle US positive e dei muri."""
    s, _ = progetto
    T = demo["verita"]
    dx = demo["origine"][0] - s.origine["E0"]
    dy = demo["origine"][1] - s.origine["N0"]
    buoni, totale, dettagli = 0, 0, {}
    for u, m in s.modello.unita.items():
        if m.tipo == "taglio" or u not in T.bodies:
            continue
        ok = _interni(s, u, m.V2)
        if ok.sum() < 5:
            continue
        x = m.V2[ok, 0] - dx; y = m.V2[ok, 1] - dy
        r = np.clip((y / mv.RES).astype(int), 0, mv.NY - 1); c = np.clip((x / mv.RES).astype(int), 0, mv.NX - 1)
        vero = T.bodies[u]["top"][r, c]
        v = ~np.isnan(vero)
        if v.sum() < 5:
            continue
        err = float(np.median(np.abs(m.top[ok][v] - vero[v])))
        dettagli[u] = round(err * 100, 1)
        totale += 1
        buoni += err < 0.03
    assert totale >= 28
    print('scarto mediano del tetto (cm):', dettagli)
    assert buoni / totale >= 0.9, dettagli


def test_mesh_stagne(progetto):
    """Ogni volume è una superficie chiusa e orientata in modo coerente: ogni spigolo orientato
    compare una volta sola e il suo opposto esiste. I vertici duplicati delle pareti laterali
    vengono ricondotti ai vertici di tetto e base da cui nascono."""
    from stratigrafia3d.mesh import spigoli_di_bordo
    s, _ = progetto
    for u, m in s.modello.unita.items():
        if m.tipo == "taglio":
            continue
        P, F = esporta.mesh_unita(m)
        n = len(m.V2)
        be = spigoli_di_bordo(m.F)
        idx = np.r_[np.arange(2 * n), np.c_[be[:, 0], n + be[:, 0], n + be[:, 1], be[:, 1]].ravel()]
        G = idx[F]
        diretti = {}
        for f in G:
            for i, j in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
                diretti[(i, j)] = diretti.get((i, j), 0) + 1
        assert all(c == 1 for c in diretti.values()), u
        assert all((b_, a_) in diretti for a_, b_ in diretti), u
        assert np.all(m.top >= m.bot - 1e-9), u


def test_coerenza_stratigrafica(progetto):
    """Dove A copre B, la base di A non scende sotto il tetto di B (tolleranza 1 mm)."""
    from scipy.interpolate import LinearNDInterpolator
    s, _ = progetto
    G = s.rapporti().grafo
    violazioni = []
    for a, b, d in G.edges(data=True):
        if d["t"] != "copre" or a not in s.modello.unita or b not in s.modello.unita:
            continue
        A, B = s.modello.unita[a], s.modello.unita[b]
        if A.tipo != "us" or B.tipo == "taglio":
            continue
        f = LinearNDInterpolator(B.V2, B.top)
        gb = (s.poligoni_us().get(b) or s.poligoni_usm().get(b)).buffer(-0.02)
        dentro = contains_xy(gb, A.V2[:, 0], A.V2[:, 1])
        if dentro.sum() == 0:
            continue
        zb = f(A.V2[dentro])
        ok = ~np.isnan(zb)
        if (A.bot[dentro][ok] < zb[ok] - 0.001).any():
            violazioni.append((a, b))
    assert not violazioni


def test_salva_e_riapri(progetto):
    s, path = progetto
    r = Scavo.apri(path)
    assert set(r.modello.unita) == set(s.modello.unita)
    for u in s.modello.unita:
        assert np.allclose(r.modello.unita[u].top, s.modello.unita[u].top)
        assert np.array_equal(r.modello.unita[u].F, s.modello.unita[u].F)
    assert set(r.layers) == set(s.layers)
    assert set(r.tabelle) == set(s.tabelle)
    assert len(r.tabelle["US"]) == len(s.tabelle["US"])
    assert r.parametri == s.parametri
    assert r.origine == s.origine
    assert [h["azione"] for h in r.storico][:3] == ["importazione", "ricostruzione", "salvataggio"]


def test_ricalcolo_parziale(demo):
    s = Scavo.da_sorgenti(demo["gpkg"], demo["xlsx"])
    ricostruisci(s)
    prima = {u: m.top.copy() for u, m in s.modello.unita.items()}
    dip = da_ricalcolare(s, [1016])
    assert {1016, 1013, 1008, 1006, 1000} <= dip
    assert 1017 not in dip and 1021 not in dip
    ricostruisci(s, unita=dip)
    for u in (1017, 1021, 1031):
        assert s.modello.unita[u].top is not None and np.allclose(s.modello.unita[u].top, prima[u])


def test_glb_valido(progetto, tmp_path):
    s, _ = progetto
    p = esporta.glb(s, str(tmp_path / "m.glb"))
    b = open(p, "rb").read()
    magic, ver, tot = struct.unpack("<III", b[:12])
    assert magic == 0x46546C67 and ver == 2 and tot == len(b)
    ln, typ = struct.unpack("<II", b[12:20])
    g = json.loads(b[20:20 + ln])
    assert len(g["nodes"]) == len(s.modello.unita)
    assert all("POSITION" in m["primitives"][0]["attributes"] for m in g["meshes"])


def test_visualizzatore(progetto, tmp_path):
    s, _ = progetto
    p = esporta.visualizzatore(s, str(tmp_path / "index.html"))
    html = open(p, encoding="utf-8").read()
    assert "/*__DATA__*/" not in html and '"meshes"' in html and len(html) > 1_000_000


def test_verifica_trova_errori(demo):
    s = Scavo.da_sorgenti(demo["gpkg"], demo["xlsx"])
    q = s.layers["quote"]
    s.layers["quote"] = q[q.us != 1005]
    s.layers["profili_us"] = s.layers["profili_us"][s.layers["profili_us"].us != 1005]
    s.tabelle["US"] = s.tabelle["US"][s.tabelle["US"]["US"] != 1013]
    codici = {p.codice for p in s.verifica()}
    assert "senza-quote" in codici and "poligono-senza-scheda" in codici
