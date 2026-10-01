"""Interfaccia in inglese: catalogo, traduzione dei testi composti, elaborati esportati."""
import re
import runpy
from pathlib import Path

import pandas as pd
import pytest

from stratigrafia3d import lingue
from stratigrafia3d.lingue import catalogo, traduci, t

RADICE = Path(__file__).resolve().parents[1]


def test_catalogo_aggiornato():
    """en.json è quello generato da strumenti/catalogo_en.py, e i segnaposto corrispondono."""
    c = catalogo("en")
    assert len(c) > 700
    T = runpy.run_path(str(RADICE / "strumenti" / "catalogo_en.py"))["T"]
    assert T == c, "rigenera en.json con: python strumenti/catalogo_en.py"
    for k, v in c.items():
        assert sorted(re.findall(r"\{\d+\}", k)) == sorted(re.findall(r"\{\d+\}", v)), k


def test_traduzione_dei_testi_composti():
    assert traduci("Salva", "en") == "Save"
    assert traduci("  Salva ", "en") == "  Save "
    assert traduci("Salva", "it") == "Salva"
    assert traduci("USM 1013", "en") == "MSU 1013"
    # gli argomenti si traducono a loro volta, e i decimali prendono il punto
    assert traduci("Fase 3", "en") == "Phase 3"
    assert traduci("l'unità della riga copre l'unità indicata", "en") == "the unit of the row covers the unit named"
    assert traduci("campo «Riempie»", "en") == "field «Riempie»"          # i nomi tra «» restano com'erano
    assert traduci("nome «us»; numero di US dal campo «us»", "en") == "name «us»; SU number from field «us»"
    assert t("Sezione {0}", 2, lingua="en") == "Section 2"
    assert t("testo che non c'è {0}", 2, lingua="en") == "testo che non c'è 2"


def test_lingua_scelta(tmp_path, monkeypatch):
    monkeypatch.setattr(lingue, "_FILE_IMPOSTAZIONI", str(tmp_path / "imp.json"))
    monkeypatch.setattr(lingue, "CARTELLA_CONFIG", str(tmp_path))
    monkeypatch.delenv("S3D_LINGUA")
    lingue.imposta_lingua("en")
    assert lingue.lingua_corrente() == "en"
    lingue.imposta_lingua("it")
    assert lingue.lingua_corrente() == "it"
    monkeypatch.setenv("S3D_LINGUA", "en")
    assert lingue.lingua_corrente() == "en"
    with pytest.raises(ValueError):
        lingue.imposta_lingua("xx")


def test_pagine_tradotte(progetto):
    from stratigrafia3d import esporta
    s, _ = progetto
    html = esporta.pagina_visualizzatore(s, lingua="en")
    assert '<html lang="en">' in html and 'S3D_LOCALE=L==="en"' in html and '"Salva": "Save"' in html.replace('":"', '": "')
    it = esporta.pagina_visualizzatore(s, lingua="it")
    assert '<html lang="it">' in it


def test_elaborati_in_inglese(progetto, tmp_path, monkeypatch):
    from stratigrafia3d import elaborati as el
    s, _ = progetto
    monkeypatch.setenv("S3D_LINGUA", "en")
    fogli = pd.read_excel(el.scrivi_tabella_volumi(s, str(tmp_path / "v.xlsx")), sheet_name=None)
    assert set(fogli) == {"Unit", "By phase", "Notes"}
    assert {"Plan area (m²)", "Strategy"} <= set(fogli["Unit"].columns)
    assert set(fogli["Unit"]["Type"]) <= {"SU", "MSU", "cut"}
    testo = open(el.pianta_svg(s, str(tmp_path / "p.svg")), encoding="utf-8").read()
    assert "plans by phase" in testo and ">Phase " in testo and "Fase" not in testo
    sez = el.sezioni_centrali(s)
    assert sez[0][0] == "E-W section (central)"
    testo = open(el.sezioni_svg(s, sez, str(tmp_path / "s.svg")), encoding="utf-8").read()
    assert "sections from the 3D model" in testo and "<title>SU " in testo
    dxf = open(el.pianta_dxf(s, str(tmp_path / "p.dxf")), encoding="cp1252").read()
    assert "SU_phase_" in dxf and "NUMBERS" in dxf and "US_fase_" not in dxf


def test_testi_dell_interfaccia_coperti():
    """I testi fissi delle pagine (contenuto degli elementi, title, placeholder) hanno una traduzione."""
    c = catalogo("en")
    mancano = []
    for f in ("src/stratigrafia3d/app/statici/app.html", "src/stratigrafia3d/visualizzatore/modello.html"):
        html = (RADICE / f).read_text(encoding="utf-8")
        html = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S)
        testi = re.findall(r">([^<>]*[A-Za-zà-ù]{3}[^<>]*)<", html)
        testi += re.findall(r'(?:title|placeholder|aria-label)="([^"$]*[a-zà-ù]{3}[^"$]*)"', html)
        for x in testi:
            x = re.sub(r"\s+", " ", x).strip()
            if x and "${" not in x and x not in c and traduci(x, "en") == x and x not in ("Stratigrafia 3D", "English", "Interface language"):
                mancano.append(x)
    assert not mancano, mancano
