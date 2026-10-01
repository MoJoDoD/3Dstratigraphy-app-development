"""Elaborati dal modello: volumi, piante e sezioni in SVG e DXF."""
import numpy as np
import pandas as pd
import pytest

from stratigrafia3d import elaborati as el


def test_tabella_volumi(progetto, tmp_path):
    s, _ = progetto
    df = el.tabella_volumi(s)
    assert len(df) == len(s.modello.unita)
    vol = sum(m.volume() for m in s.modello.unita.values() if m.tipo != "taglio")
    assert df["Volume (m³)"].sum() == pytest.approx(vol, rel=1e-3)
    p = el.scrivi_tabella_volumi(s, str(tmp_path / "v.xlsx"))
    fogli = pd.read_excel(p, sheet_name=None)
    assert set(fogli) == {"Unità", "Per fase", "Note"}
    assert fogli["Per fase"]["Unità"].sum() == len(df)


def test_sezione_coerente_con_il_modello(progetto):
    s, _ = progetto
    nome, a, b = el.linee_sezione(s)[0]
    tagli, L = el.sezione(s, a, b)
    assert L == pytest.approx(np.hypot(b[0] - a[0], b[1] - a[1]))
    assert len(tagli) > 5
    o = s.origine
    A = np.array(a) - (o["E0"], o["N0"])
    u = (np.array(b) - np.array(a)) / L
    for t in tagli:
        m = s.modello.unita[t["unita"]]
        for g in t["aree"]:
            # le aree stanno tra la quota minima e massima dell'unità, dentro la sezione
            x0, z0, x1, z1 = g.bounds
            assert z0 >= m.bot.min() - 1e-3 and z1 <= m.top.max() + 1e-3
            assert -1e-6 <= x0 and x1 <= L + 1e-6
            # e il punto interno dell'area cade dentro la pianta dell'unità
            c = g.representative_point()
            xy = A + u * c.x
            from shapely.geometry import Point
            poli = {**s.poligoni_us(), **s.poligoni_usm()}[t["unita"]]
            assert poli.buffer(0.05).contains(Point(*xy))


def test_disegni(progetto, tmp_path):
    s, _ = progetto
    sez = el.linee_sezione(s)
    svg = el.sezioni_svg(s, sez, str(tmp_path / "s.svg"))
    testo = open(svg, encoding="utf-8").read()
    assert testo.startswith("<svg") and "A-A" in testo and "<path" in testo
    el.pianta_svg(s, str(tmp_path / "p.svg"))
    ezdxf = pytest.importorskip("ezdxf")
    d = ezdxf.readfile(el.sezioni_dxf(s, sez, str(tmp_path / "s.dxf")))
    assert len(d.modelspace().query("POLYLINE")) > 10
    d = ezdxf.readfile(el.pianta_dxf(s, str(tmp_path / "p.dxf")))
    pl = d.modelspace().query("POLYLINE")
    o = s.origine
    x = [v.dxf.location.x for p in pl for v in p.vertices]
    assert min(x) > o["E0"] - 1                        # coordinate reali
    assert any(l.dxf.name.startswith("US_fase_") for l in d.layers)


def test_sezioni_centrali(progetto):
    s, _ = progetto
    c = el.sezioni_centrali(s)
    assert len(c) == 2 and el.sezione(s, c[0][1], c[0][2])[0]


def test_esportazioni_dall_app(progetto, tmp_path):
    from stratigrafia3d.app.server import App
    _, path = progetto
    app = App(path)
    for tipo, est in (("volumi", ".xlsx"), ("pianta_svg", ".svg"), ("pianta_dxf", ".dxf"),
                      ("sezioni_svg", ".svg"), ("sezioni_dxf", ".dxf"), ("glb", ".glb")):
        r = app.azione("esporta", dict(tipo=tipo, percorso=str(tmp_path / f"x_{tipo}")))
        assert r["percorso"].endswith(est) and (tmp_path / f"x_{tipo}{est}").stat().st_size > 1000
