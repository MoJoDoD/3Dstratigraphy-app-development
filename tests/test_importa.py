"""Import flessibile: dati canonici, dati 'disordinati' (shapefile, Excel a foglio unico) e DXF da CAD."""
import numpy as np
import pytest

from stratigrafia3d import importa, ricostruisci, Scavo
from stratigrafia3d.demo import varianti


@pytest.fixture(scope="module")
def disordinata(demo, tmp_path_factory):
    return varianti.disordinata(demo, str(tmp_path_factory.mktemp("dis")))


@pytest.fixture(scope="module")
def cad(demo, tmp_path_factory):
    pytest.importorskip("ezdxf")
    return varianti.cad(demo, str(tmp_path_factory.mktemp("cad")))


def _ruoli(abb):
    return {r.layer: r.ruolo for r in abb.layers}


def test_proposta_su_dati_canonici(demo):
    abb = importa.proponi([demo["gpkg"], demo["xlsx"]])
    r = _ruoli(abb)
    assert r["us_poligoni"] == "us" and r["usm_poligoni"] == "usm" and r["quote"] == "quote"
    assert r["griglia_2m"] == "ignora" and r["profili_us"] == "profili"
    q = next(x for x in abb.layers if x.layer == "quote")
    assert q.campo_unita == "us" and q.campo_tipo == "tipo_quota"
    assert abb.rapporti["modo"] == "foglio"
    s = importa.applica(abb)
    rif = Scavo.da_sorgenti(demo["gpkg"], demo["xlsx"])
    assert set(s.schede_us()) == set(rif.schede_us())
    assert len(s.layers["quote"]) == len(rif.layers["quote"])
    assert not [p for p in s.verifica() if p.livello == "errore"]


def test_dati_disordinati(disordinata, demo):
    abb = importa.proponi(disordinata)
    r = _ruoli(abb)
    assert r["US_limiti"] == "us" and r["murature"] == "usm" and r["limite_scavo"] == "area"
    qi = next(x for x in abb.layers if x.layer == "quote_inferiori")
    assert qi.tipo_predefinito == "inf" and qi.quota_da == "campo:QUOTA" and qi.campo_unita == "COD"
    assert abb.rapporti["modo"] == "colonne"
    s = importa.applica(abb)
    assert len(s.schede_us()) == 39 and len(s.schede_usm()) == 7
    assert s.tabelle["US"]["Spessore medio stimato (m)"].dropna().max() < 2      # cm -> m
    neg = set(s.tabelle["US"].loc[s.tabelle["US"]["Tipo"] == "negativa", "US"])
    assert {1001, 1003, 1009, 1019, 1024} <= neg
    assert not [p for p in s.verifica() if p.livello == "errore"]
    m = ricostruisci(s)
    assert len(m.unita) == 46


def test_dxf_da_stazione_totale(cad):
    abb = importa.proponi(cad)
    r = _ruoli(abb)
    assert r["US_# · poligono"] == "us" and r["USM_# · poligono"] == "usm"
    assert r["QINF_# · punto"] == "quote" and r["QSUP_# · punto"] == "quote"
    s = importa.applica(abb)
    assert len(s.poligoni_us()) == 39
    # i buchi disegnati come anelli interni restano buchi
    rif = s.poligoni_us()[1014]
    assert len(rif.geoms[0].interiors) >= 1 if rif.geom_type == "MultiPolygon" else len(rif.interiors) >= 1
    assert not [p for p in s.verifica() if p.livello == "errore"]
    assert len(ricostruisci(s).unita) == 46


def test_profilo_di_abbinamento(disordinata, tmp_path):
    abb = importa.proponi(disordinata)
    p = str(tmp_path / "profilo.json")
    abb.salva_profilo(p)
    abb2 = importa.Abbinamento.carica_profilo(p)
    assert abb2 == abb


def test_abbinamento_salvato_nel_progetto(disordinata, tmp_path):
    s = importa.applica(importa.proponi(disordinata))
    ricostruisci(s)
    p = str(tmp_path / "d.scavo")
    s.salva(p)
    r = Scavo.apri(p)
    assert r.abbinamento == s.abbinamento


def test_pagina_offline(progetto, tmp_path):
    from stratigrafia3d import esporta
    s, _ = progetto
    html = open(esporta.visualizzatore(s, str(tmp_path / "v.html")), encoding="utf-8").read()
    assert "cdnjs" not in html and "googleapis" not in html and "THREE" in html
