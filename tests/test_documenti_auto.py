"""Foto e disegni collegati alle unità in automatico: tipo d'immagine, numeri nei nomi, registri."""
import os

import numpy as np
import pandas as pd
import pytest

from stratigrafia3d import documenti_auto as da

Image = pytest.importorskip("PIL.Image")


def _foto(p, exif=True):
    """Immagine «fotografica»: molte tinte, rumore, dati EXIF di una fotocamera."""
    rng = np.random.default_rng(1)
    y, x = np.mgrid[0:300, 0:400]
    a = np.stack([120 + 60 * np.sin(x / 40), 90 + 50 * np.cos(y / 30), 60 + 40 * np.sin((x + y) / 50)], -1)
    a = np.clip(a + rng.normal(0, 25, a.shape), 0, 255).astype("uint8")
    im = Image.fromarray(a, "RGB")
    if exif:
        ex = Image.Exif()
        ex[271], ex[272] = "Canon", "Canon EOS 5D"
        im.save(p, exif=ex.tobytes())
    else:
        im.save(p)
    return str(p)


def _disegno(p):
    """Disegno digitale: linee nere sottili su fondo bianco puro."""
    a = np.full((400, 600), 255, "uint8")
    for i in range(0, 600, 60):
        a[:, i:i + 2] = 0
    a[200:202, :] = 0
    a[100:300, 300:302] = 0
    Image.fromarray(a, "L").convert("RGB").save(p)
    return str(p)


def _scansione(p):
    """Foglio scansionato: fondo color carta un po' rumoroso, segni a matita, grande, TIFF a 300 dpi."""
    rng = np.random.default_rng(2)
    a = np.clip(rng.normal(232, 4, (3200, 2400)), 0, 255)
    a[1000:1004, 200:2200] = 60
    a[400:2800, 1200:1203] = 70
    Image.fromarray(a.astype("uint8"), "L").save(p, dpi=(300, 300))
    return str(p)


@pytest.fixture(scope="module")
def immagini(tmp_path_factory):
    d = tmp_path_factory.mktemp("img")
    return {"foto": _foto(d / "x1.jpg"), "disegno": _disegno(d / "x2.png"), "scansione": _scansione(d / "x3.tif"),
            "foto_senza_exif": _foto(d / "x4.jpg", exif=False)}


def test_tipo_dall_aspetto(immagini):
    t, p, m = da.tipo_immagine(immagini["foto"])
    assert t == "foto" and p > 0.5 and "Canon" in m
    t, p, m = da.tipo_immagine(immagini["disegno"])
    assert t == "disegno" and "fondo bianco" in m
    t, p, m = da.tipo_immagine(immagini["scansione"])
    assert t == "scansione" and "carta" in m
    assert da.tipo_immagine(immagini["foto_senza_exif"])[0] == "foto"


def test_tipo_dal_nome(tmp_path):
    # file assenti: decidono le parole del nome, in più lingue, file e cartelle
    assert da.tipo_immagine(str(tmp_path / "Schnitte" / "B17.jpg"))[0] == "disegno"
    assert da.tipo_immagine(str(tmp_path / "coupe 3.png"))[0] == "disegno"
    assert da.tipo_immagine(str(tmp_path / "photographs" / "1234.jpg"))[0] == "foto"
    assert da.tipo_immagine(str(tmp_path / "DSC00123.JPG"))[0] == "foto"
    assert da.tipo_immagine(str(tmp_path / "scansioni" / "tavola 4.jpg"))[0] == "scansione"
    t, p, m = da.tipo_immagine(str(tmp_path / "x.jpg"))
    assert t == "foto" and p < 0.5 and "nessun indizio" in m
    # il nome conta più dell'aspetto se l'aspetto è debole, ma l'EXIF della fotocamera vince sul nome
    d = tmp_path / "sezioni"
    d.mkdir()
    assert da.tipo_immagine(_foto(d / "US1005.jpg"))[0] == "foto"


def test_immagine_enorme_non_si_apre(tmp_path, monkeypatch):
    p = _scansione(tmp_path / "foglio.tif")
    monkeypatch.setattr(da, "PIXEL_MASSIMI", 1000)
    t, _, m = da.tipo_immagine(p)
    assert t == "scansione" and "enorme" in m


@pytest.mark.parametrize("nome, note, attese", [
    ("US1005_N.jpg", None, [1005]),
    ("us 1005 da nord.JPG", None, [1005]),
    ("1005-sez.tif", {1005}, [1005]),
    ("1005-sez.tif", None, []),                              # senza elenco: i numeri senza sigla no
    ("photographs/Context 1005/IMG_2231.JPG", None, [1005]),
    ("Ctx_1005 (2).png", None, [1005]),
    ("SU_12_a.jpg", None, [12]),
    ("UE 3021.jpg", None, [3021]),
    ("Befund 17.jpg", None, [17]),
    ("1005_1006.jpg", {1005, 1006}, [1005, 1006]),
    ("US1005-1007", {1005, 1006, 1007}, [1005, 1006, 1007]),
    ("US1005-1007", {1005, 1007}, [1005, 1007]),             # 1006 non è un'unità: intervallo non espanso
    ("US 1005 e 1006.jpg", None, [1005, 1006]),
    ("US1005_2.jpg", None, [1005]),                          # «_2»: numero dello scatto
    ("US 9999.jpg", {1005}, []),                             # sigla, ma non è un'unità del progetto
    # falsi positivi da evitare anche se il numero è un'unità nota
    ("2019/IMG_2231.jpg", {2019, 2231}, []),
    ("20190512_103000.jpg", {20190512, 103000}, []),
    ("DSC01005.JPG", {1005}, []),
    ("P1010023.JPG", {1010023}, []),
    ("Photo 12.jpg", {12}, []),
    ("sezione 1-20.tif", {20}, []),
    ("pianta_1_50.png", {50}, []),
    ("1200x800.jpg", {1200, 800}, []),
    ("foto/2019_05_12/1006.jpg", {1006, 2019}, [1006]),
    ("US1005 2019.jpg", {1005, 2019}, [1005]),
])
def test_numeri_nei_nomi(nome, note, attese):
    assert da.unita_dal_percorso(nome, note)[0] == attese


def test_ambiguita_nel_motivo():
    _, motivo, _ = da.unita_dal_percorso("Context 1005/1006.jpg", {1005, 1006})
    assert "cartella" in motivo and "ambiguo" in motivo and "1006" in motivo
    _, motivo, _ = da.unita_dal_percorso("2019.jpg", {2019})
    assert "anno" in motivo


def _voci(radice, nomi):
    out = []
    for rel in nomi:
        p = radice / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_bytes(b"")
        ext = os.path.splitext(rel)[1].lower()
        cat = "immagine" if ext in da.EST_IMMAGINI else "documento"
        out.append({"percorso": str(p), "relativo": rel, "categoria": cat})
    return out


def test_documenti_per_unita(tmp_path):
    _foto(tmp_path / "US1005_N.jpg")
    os.makedirs(tmp_path / "sezioni", exist_ok=True)
    _disegno(tmp_path / "sezioni" / "1006-sez.png")
    voci = _voci(tmp_path, ["US1005_N.jpg", "sezioni/1006-sez.png", "photographs/Context 1007/IMG_2231.JPG",
                            "1005_1006.jpg", "IMG_2019.jpg", "schede/US1007.pdf", "relazione.pdf",
                            "elenco.xlsx", "Photo 12.jpg"])
    r = da.documenti_per_unita(voci, unita_note={1005, 1006, 1007, 12, 2019})
    c = r["collegamenti"]
    assert sorted(c) == [1005, 1006, 1007]
    nomi = {u: sorted(os.path.basename(e["percorso"]) for e in lista) for u, lista in c.items()}
    assert nomi[1005] == ["1005_1006.jpg", "US1005_N.jpg"]
    assert nomi[1006] == ["1005_1006.jpg", "1006-sez.png"]
    assert nomi[1007] == ["IMG_2231.JPG", "US1007.pdf"]
    tipi = {os.path.basename(e["percorso"]): e["tipo"] for lista in c.values() for e in lista}
    assert tipi["US1005_N.jpg"] == "foto" and tipi["1006-sez.png"] == "disegno"
    assert tipi["US1007.pdf"] == "scansione"
    assert sorted(os.path.basename(p) for p in r["non_collegati"]) == ["IMG_2019.jpg", "Photo 12.jpg"]
    assert any("Immagini collegate alle unità dai nomi: 4 su 6" in n for n in r["note"])
    assert any("nome della cartella" in n for n in r["note"])
    motivo = next(e["motivo"] for e in c[1007] if e["percorso"].endswith("IMG_2231.JPG"))
    assert "Context 1007" in motivo and "cartella" in motivo


def test_senza_elenco_delle_unita(tmp_path):
    voci = _voci(tmp_path, ["US1005_N.jpg", "1005-sez.tif", "Befund 17.jpg"])
    r = da.documenti_per_unita(voci)
    assert sorted(r["collegamenti"]) == [17, 1005]
    assert [os.path.basename(p) for p in r["non_collegati"]] == ["1005-sez.tif"]
    assert any("sigla" in n for n in r["note"])
    # il tipo già noto nella voce non si ricalcola
    voci[0]["tipo"] = "disegno"
    assert da.documenti_per_unita(voci)["collegamenti"][1005][0]["tipo"] == "disegno"


def test_registro_per_numero(tmp_path):
    voci = _voci(tmp_path, ["photographs/1234.jpg", "photographs/Photo 1235.JPG", "photographs/0101a.jpg",
                            "photographs/1236_NE facing.jpg", "photographs/9999.jpg", "sections/1234.tif",
                            "photographs/US1005.jpg"])
    # registro «lungo» come ContextsPhotos (una riga per coppia scatto-unità) con l'unità in Intervention
    reg = pd.DataFrame({"View Number": [1234, 1234, 1235, 101, 1236, 1005],
                        "Intervention": [492001.0, 492002.0, 492003.0, None, 492005, 77]})
    r = da.collega_da_registro(reg, voci)
    c = r["collegamenti"]
    nomi = {u: sorted(os.path.basename(e["percorso"]) for e in lista) for u, lista in c.items()}
    assert nomi[492001] == ["1234.jpg"] and nomi[492002] == ["1234.jpg"]   # non la sezione 1234.tif
    assert nomi[492003] == ["Photo 1235.JPG"]
    assert nomi[492005] == ["1236_NE facing.jpg"]
    assert 77 not in c                                    # «US1005» è un'unità, non lo scatto 1005
    non = sorted(os.path.basename(p) for p in r["non_collegati"])
    assert non == ["0101a.jpg", "1234.tif", "9999.jpg", "US1005.jpg"]
    assert any("Registro: numero «View Number», unità «Intervention»" in n for n in r["note"])
    assert any("per numero" in n for n in r["note"])


def test_registro_per_nome_e_descrizione(tmp_path):
    voci = _voci(tmp_path, ["archivio/scansioni/s5.tif", "foto/Pre-ex.JPG", "foto/b.jpg", "foto/c.png"])
    reg = pd.DataFrame({"ID": ["Section 5", "Photo 1", "Photo 2", "Photo 3"],
                        "Context": [11, 10, None, None],
                        "Description": ["", "", "Half section of US 12", "ditch 492001"],
                        "File": ["sections\\s5.tif", "pre-ex.jpg", "b.jpg", "c.jpg"]})
    r = da.collega_da_registro(reg, voci)
    nomi = {u: sorted(os.path.basename(e["percorso"]) for e in lista) for u, lista in r["collegamenti"].items()}
    assert nomi == {10: ["Pre-ex.JPG"], 11: ["s5.tif"], 12: ["b.jpg"]}   # «ditch 492001»: senza sigla
    assert any("descrizione" in n for n in r["note"])
    # con l'elenco delle unità, anche i numeri senza sigla della descrizione; c.png ha un'altra estensione
    r = da.collega_da_registro(reg, voci, unita_note={10, 11, 12, 492001})
    assert [os.path.basename(e["percorso"]) for e in r["collegamenti"][492001]] == ["c.png"]
    assert "altra estensione" in r["collegamenti"][492001][0]["motivo"]


def test_registro_senza_colonne_utili():
    r = da.collega_da_registro(pd.DataFrame({"Colore": ["rosso"]}), [])
    assert r["collegamenti"] == {} and any("colonna" in n for n in r["note"])


def test_unisci_e_tabella(tmp_path):
    voci = _voci(tmp_path, ["US10.jpg", "7.jpg", "x.jpg"])
    for v in voci:
        v["tipo"] = "foto"
    a = da.documenti_per_unita(voci)
    b = da.collega_da_registro(pd.DataFrame({"Photo number": [7], "US": [11]}), voci)
    r = da.unisci(a, b)
    assert sorted(r["collegamenti"]) == [10, 11]
    assert [os.path.basename(p) for p in r["non_collegati"]] == ["x.jpg"]
    t = da.come_tabella(r, radice=str(tmp_path))
    assert list(t.columns) == ["US/USM", "Tipo", "File", "Percorso file", "Note"]
    assert set(t["File"]) == {"US10.jpg", "7.jpg"} and set(t["US/USM"]) == {10, 11}
    assert all(os.path.isabs(p) for p in t["Percorso file"])
