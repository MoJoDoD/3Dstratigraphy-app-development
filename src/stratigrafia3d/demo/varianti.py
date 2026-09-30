# -*- coding: utf-8 -*-
"""
Versioni "come arrivano dal cantiere" dello scavo dimostrativo, per collaudare l'import:

- ``disordinata``: shapefile con nomi di campo diversi, quote 2D con la quota in un campo,
  quote superiori e inferiori in due file senza tipo, Excel con un solo foglio, numeri di US
  scritti "US 1005", spessori in centimetri, rapporti nelle colonne della scheda.
- ``cad``: un DXF da stazione totale (una polilinea chiusa per US sul layer US_<n>,
  punti 3D sui layer QSUP_<n> / QINF_<n>, limite di scavo) + la stessa Excel.
"""
import os

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point


def _base(demo):
    L = {n: gpd.read_file(demo["gpkg"], layer=n) for n in
         ["us_poligoni", "usm_poligoni", "quote", "area_scavo"]}
    X = pd.read_excel(demo["xlsx"], sheet_name=None)
    return L, X


def _excel_disordinata(X, path):
    us, usm = X["US"], X["USM"]
    rel = X["Rapporti"]
    cols = {"copre": "Copre", "coperto da": "Coperto da", "taglia": "Taglia", "tagliato da": "Tagliato da",
            "riempie": "Riempie", "riempito da": "Riempito da", "si appoggia a": "Si appoggia a",
            "gli si appoggia": "Gli si appoggia", "si lega a": "Si lega a"}
    inv = {"copre": "coperto da", "taglia": "tagliato da", "riempie": "riempito da",
           "si appoggia a": "gli si appoggia", "si lega a": "si lega a"}
    lista = {}
    for _, r in rel.iterrows():
        a, t, b = int(r["US"]), r["Rapporto"], int(r["US correlata"])
        lista.setdefault(a, {}).setdefault(t, []).append(b)
        if t != "si lega a":
            lista.setdefault(b, {}).setdefault(inv[t], []).append(a)
    righe = []
    for _, r in us.iterrows():
        righe.append({"N. US": f"US {int(r['US'])}", "Definizione": r["Definizione"], "Categoria": r["Categoria"],
                      "Spessore (cm)": None if pd.isna(r["Spessore medio stimato (m)"]) else round(r["Spessore medio stimato (m)"] * 100),
                      "Margini": r["Margini"], "Fase": r["Fase"], "Descrizione": r["Descrizione"]})
    for _, r in usm.iterrows():
        righe.append({"N. US": f"USM {int(r['USM'])}", "Definizione": r["Definizione"], "Categoria": r["Categoria"],
                      "Fase": r["Fase"], "Descrizione": r["Descrizione"]})
    df = pd.DataFrame(righe)
    for t, c in cols.items():
        df[c] = [", ".join(str(x) for x in sorted(set(lista.get(int(''.join(ch for ch in n if ch.isdigit())), {}).get(t, [])))) or None
                 for n in df["N. US"]]
    with pd.ExcelWriter(path) as w:
        df.to_excel(w, sheet_name="Schede", index=False)
        X["Materiali"].to_excel(w, sheet_name="Materiali", index=False)
    return path


def disordinata(demo, cartella):
    os.makedirs(cartella, exist_ok=True)
    L, X = _base(demo)
    us = L["us_poligoni"][["us", "geometry"]].copy()
    us["NUM_US"] = ["US " + str(u) for u in us.us]
    us[["NUM_US", "geometry"]].to_file(os.path.join(cartella, "US_limiti.shp"))
    m = L["usm_poligoni"][["usm", "geometry"]].rename(columns={"usm": "N_USM"})
    m.to_file(os.path.join(cartella, "murature.shp"))
    q = L["quote"]
    q2 = gpd.GeoDataFrame({"COD": q.us.values, "QUOTA": q.geometry.z.round(3).values},
                          geometry=[Point(p.x, p.y) for p in q.geometry], crs=q.crs)
    sup = q.tipo_quota.isin(["sup", "taglio", "orlo", "rasatura"]).values
    q2[sup].to_file(os.path.join(cartella, "quote_superiori.shp"))
    q2[~sup].to_file(os.path.join(cartella, "quote_inferiori.shp"))
    L["area_scavo"][L["area_scavo"].tipo == "area"][["geometry"]].to_file(os.path.join(cartella, "limite_scavo.shp"))
    xl = _excel_disordinata(X, os.path.join(cartella, "schede.xlsx"))
    shp = sorted(os.path.join(cartella, f) for f in os.listdir(cartella) if f.endswith(".shp"))
    return shp + [xl]


def cad(demo, cartella):
    import ezdxf
    os.makedirs(cartella, exist_ok=True)
    L, X = _base(demo)
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()

    def anelli(geom, layer):
        for p in getattr(geom, "geoms", [geom]):
            for ring in [p.exterior, *p.interiors]:
                msp.add_lwpolyline(list(ring.coords)[:-1], close=True, dxfattribs={"layer": layer})

    for u, g in zip(L["us_poligoni"].us, L["us_poligoni"].geometry):
        anelli(g, f"US_{u}")
        c = g.representative_point()
        msp.add_text(str(u), dxfattribs={"layer": "ETICHETTE", "insert": (c.x, c.y), "height": 0.2})
    for u, g in zip(L["usm_poligoni"].usm, L["usm_poligoni"].geometry):
        anelli(g, f"USM_{u}")
    a = L["area_scavo"][L["area_scavo"].tipo == "area"].geometry.iloc[0]
    anelli(a, "LIMITE_SCAVO")
    for u, t, p in zip(L["quote"].us, L["quote"].tipo_quota, L["quote"].geometry):
        lay = f"QINF_{u}" if t in ("inf", "fondazione") else f"QSUP_{u}"
        msp.add_point((p.x, p.y, p.z), dxfattribs={"layer": lay})
    dxf = os.path.join(cartella, "rilievo_stazione_totale.dxf")
    doc.saveas(dxf)
    xl = _excel_disordinata(X, os.path.join(cartella, "schede.xlsx"))
    return [dxf, xl]
