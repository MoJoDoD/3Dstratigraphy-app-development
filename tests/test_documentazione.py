"""Foto e disegni collegati alle schede, ortofoto drappeggiata sul modello."""
import os

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box

from stratigrafia3d import importa, ricostruisci, Scavo, esporta

tifffile = pytest.importorskip("tifffile")
PIL = pytest.importorskip("PIL")
CRS = "EPSG:27700"


def _scavo(d, ortofoto=True):
    gpkg = str(d / "sito.gpkg")
    gpd.GeoDataFrame({"context": [10, 11]}, geometry=[box(1000, 2000, 1004, 2003), box(1006, 2000, 1008, 2002)],
                     crs=CRS).to_file(gpkg, layer="contexts", driver="GPKG")
    xlsx = str(d / "sito.xlsx")
    with pd.ExcelWriter(xlsx) as w:
        pd.DataFrame({"Context": [10, 11], "Type": ["positive", "positive"], "Thickness (m)": [0.2, 0.3]}) \
            .to_excel(w, sheet_name="Contexts", index=False)
        pd.DataFrame({"ID": ["Photo 1", "Photo 2", "Section 5", "Photo 9"], "Context": [10, 10, 11, 11],
                      "Subject": ["Pre-ex", "Half section", "Drawing", "Missing"],
                      "File": ["photographs/1.jpg", "2.jpg", "sections\\s5.tif", "photographs/9.jpg"]}) \
            .to_excel(w, sheet_name="Documentation", index=False)
    from PIL import Image
    os.makedirs(d / "photographs", exist_ok=True)
    os.makedirs(d / "archivio" / "scansioni", exist_ok=True)
    os.makedirs(d / "sections", exist_ok=True)
    Image.new("RGB", (60, 40), (200, 50, 50)).save(d / "photographs" / "1.jpg")
    Image.new("RGB", (60, 40), (50, 200, 50)).save(d / "archivio" / "scansioni" / "2.jpg")    # cercata per nome
    Image.new("RGB", (60, 40), (50, 50, 200)).save(d / "sections" / "s5.tif")
    files = [gpkg, xlsx]
    if ortofoto:
        # 20 x 10 m a 0,5 m, angolo in alto a sinistra in (998, 2005): metà sinistra rossa, destra blu
        img = np.zeros((20, 40, 3), "uint8")
        img[:, :20] = (255, 0, 0)
        img[:, 20:] = (0, 0, 255)
        p = str(d / "orto.tif")
        tifffile.imwrite(p, img, photometric="rgb", extratags=[
            (33550, "d", 3, (0.5, 0.5, 0.0), False), (33922, "d", 6, (0.0, 0.0, 0.0, 998.0, 2005.0, 0.0), False)])
        files.append(p)
    return files


def test_file_della_documentazione(tmp_path):
    abb = importa.proponi(_scavo(tmp_path, ortofoto=False))
    abb.superficie = {"tipo": "costante", "quota": 50.0}
    s = importa.applica(abb)
    doc = s.tabelle["Documentazione"].set_index("ID")
    assert doc.loc["Photo 1", "Percorso file"] == str(tmp_path / "photographs" / "1.jpg")
    assert doc.loc["Photo 2", "Percorso file"] == str(tmp_path / "archivio" / "scansioni" / "2.jpg")
    assert doc.loc["Section 5", "Percorso file"] == str(tmp_path / "sections" / "s5.tif")
    assert pd.isna(doc.loc["Photo 9", "Percorso file"])
    assert any("3 file trovati su 4" in n for n in s.note_importazione)
    # il server mostra solo i file citati, e riduce o converte le immagini
    from stratigrafia3d.app.server import App
    app = App.__new__(App)
    from stratigrafia3d.app.server import Stato
    app.stato = Stato()
    app.stato.scavo = s
    corpo, tipo = app.media(str(tmp_path / "sections" / "s5.tif"), 30)
    assert tipo == "image/jpeg" and corpo[:2] == b"\xff\xd8"
    with pytest.raises(FileNotFoundError):
        app.media(str(tmp_path / "sito.xlsx"))


def test_ortofoto(tmp_path):
    files = _scavo(tmp_path)
    r = importa.esamina_raster(files)
    assert r[files[-1]]["tipo"] == "ortofoto"
    abb = importa.proponi(files)
    assert abb.ortofoto == files[-1] and abb.superficie.get("tipo") != "raster"
    abb.superficie = {"tipo": "costante", "quota": 50.0}
    s = importa.applica(abb)
    o = s.ortofoto
    assert o is not None
    # ritagliata sull'area (1000–1008 × 2000–2003) con 5 m di margine e dentro l'immagine, più 2 pixel di cornice
    x0, y0, x1, y1 = o.estensione
    assert x0 == pytest.approx(998 - 1.0) and x1 == pytest.approx(1008 + 5 + 1.0)
    ricostruisci(s)
    p = str(tmp_path / "o.scavo")
    s.salva(p)
    r = Scavo.apri(p)
    assert r.ortofoto.estensione == o.estensione and r.ortofoto.jpeg == o.jpeg
    d = esporta.dati_visualizzatore(r)
    E0 = r.origine["E0"]
    assert d["ortofoto"]["estensione"][0] == pytest.approx(x0 - E0)
    html = esporta.pagina_visualizzatore(r)
    assert html.startswith("<!doctype html>") and '<meta charset="utf-8">' in html[:200]


def _griglia(nx=30, ny=20, x0=1000.0, y0=2000.0):
    X, Y = np.meshgrid(np.linspace(x0, x0 + 8, nx), np.linspace(y0, y0 + 3, ny))
    V = np.c_[X.ravel(), Y.ravel(), 50 + 0.1 * X.ravel() - 100]
    i = np.arange(nx * ny).reshape(ny, nx)
    a, b, c, d = i[:-1, :-1].ravel(), i[:-1, 1:].ravel(), i[1:, :-1].ravel(), i[1:, 1:].ravel()
    return V, np.r_[np.c_[a, b, d], np.c_[a, d, c]]


@pytest.mark.parametrize("formato", ["ply_bin", "ply_ascii", "obj"])
def test_modelli_3d(tmp_path, formato):
    from stratigrafia3d.modelli3d import Modello3D
    V, F = _griglia()
    C = (np.c_[V[:, 0] - 1000, V[:, 1] - 2000, V[:, 2] * 0] * 20).astype("u1")
    if formato == "obj":
        p = tmp_path / "rilievo.obj"
        with open(p, "w") as f:
            for v, c in zip(V, C):
                f.write(f"v {v[0]} {v[1]} {v[2]} {c[0] / 255} {c[1] / 255} {c[2] / 255}\n")
            for t in F:
                f.write(f"f {t[0] + 1} {t[1] + 1} {t[2] + 1}\n")
    else:
        p = tmp_path / "rilievo.ply"
        testa = (f"ply\nformat {'binary_little_endian' if formato == 'ply_bin' else 'ascii'} 1.0\n"
                 f"element vertex {len(V)}\nproperty double x\nproperty double y\nproperty double z\n"
                 "property uchar red\nproperty uchar green\nproperty uchar blue\n"
                 f"element face {len(F)}\nproperty list uchar int vertex_indices\nend_header\n")
        with open(p, "wb") as f:
            f.write(testa.encode())
            if formato == "ply_bin":
                vt = np.zeros(len(V), dtype=[("x", "<f8"), ("y", "<f8"), ("z", "<f8"), ("r", "u1"), ("g", "u1"), ("b", "u1")])
                vt["x"], vt["y"], vt["z"] = V.T
                vt["r"], vt["g"], vt["b"] = C.T
                f.write(vt.tobytes())
                ft = np.zeros(len(F), dtype=[("n", "u1"), ("i", "<i4", 3)])
                ft["n"], ft["i"] = 3, F
                f.write(ft.tobytes())
            else:
                f.write("".join(f"{v[0]} {v[1]} {v[2]} {c[0]} {c[1]} {c[2]}\n" for v, c in zip(V, C)).encode())
                f.write("".join(f"3 {t[0]} {t[1]} {t[2]}\n" for t in F).encode())
    m = Modello3D.leggi(str(p), spostamento=(0, 0, 100))
    assert len(m.F) == len(F) and np.allclose(m.V[:, 2].min(), 50 + 0.1 * 1000)
    assert m.colori is not None and abs(int(m.colori[-1][0]) - int(C[-1][0])) <= 1
    piccolo = m.semplifica(200)
    assert 0 < len(piccolo.F) <= 200
    # nel progetto e nel visualizzatore
    files = _scavo(tmp_path, ortofoto=False) + [str(p)]
    abb = importa.proponi(files)
    assert abb.modelli3d[0]["percorso"] == str(p)
    abb.modelli3d[0]["spostamento"] = [0, 0, 100]
    abb.superficie = {"tipo": "costante", "quota": 50.0}
    s = importa.applica(abb)
    assert len(s.modelli3d) == 1 and not any("chilometro" in n for n in s.note_importazione)
    ricostruisci(s)
    q = str(tmp_path / "m.scavo")
    s.salva(q)
    r = Scavo.apri(q)
    assert len(r.modelli3d[0].F) == len(F)
    d = esporta.dati_visualizzatore(r)["modelli3d"][0]
    assert d["n"] == len(V) and "colori" in d


def test_modello_obj_con_texture(tmp_path):
    from PIL import Image
    from stratigrafia3d.modelli3d import Modello3D
    Image.new("RGB", (16, 16), (200, 20, 20)).save(tmp_path / "t.png")
    (tmp_path / "m.mtl").write_text("newmtl a\nmap_Kd t.png\n")
    (tmp_path / "m.obj").write_text("mtllib m.mtl\nv 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\n"
                                    "vt 0 0\nvt 1 0\nvt 1 1\nvt 0 1\nvt 0.5 0.5\nf 1/1 2/2 3/3 4/4\nf 1/5 3/3 4/4\n")
    m = Modello3D.leggi(str(tmp_path / "m.obj"))
    assert m.texture[:2] == b"\xff\xd8" and len(m.F) == 3
    assert len(m.V) == 5 and m.uv.shape == (5, 2)          # il vertice 1 ha due coordinate di texture
