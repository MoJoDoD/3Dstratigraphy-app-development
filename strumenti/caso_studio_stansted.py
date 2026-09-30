# -*- coding: utf-8 -*-
"""
Builds an English practice case study (GeoPackage + Excel) from the Framework Archaeology
Stansted digital archive, in the layout stratigrafia3d imports: one polygon per context,
3D level points, a context register, a relations sheet, phases, finds, documentation.

The archive records plans and tape-measured depths but no absolute levels and no
covers/covered-by relations. The package keeps the data as recorded; the app reconstructs
the volumes from the terrain model (reference surface) and the depths, and flags what it
had to estimate.

    python caso_studio_stansted.py --spaziali <Stansted_Spatial_SHP folder> \
        --database <Stansted_Database_CSV folder> --uscita <output folder>
"""
import argparse
import datetime as dt
import math
import os
import warnings

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
import tifffile
from shapely.geometry import MultiPolygon, box
from shapely.ops import unary_union

warnings.filterwarnings("ignore")

CRS = "EPSG:27700"          # Ordnance Survey National Grid (the archive ships without .prj)
NOME = "Stansted_Hunting_Lodge"
TITOLO = "Stansted Airport – Hunting Lodge (Framework Archaeology)"
LODGE = ["LaterMedievalHuntingLodge", "EarlyPostMedievalHuntingLodge", "PostMedievalLodge", "PostMedievalMidden"]

COLORI = {  # sober palette per interpretation keyword
    "Primary Fill": "#6f6150", "Secondary Fill": "#8a7a63", "Tertiary Fill": "#a39377", "Other Fill": "#958a74",
    "Deliberate Backfill": "#7d6f5a", "Placed Deposit": "#9c8360", "Post-pipe": "#5a4e40", "Layer": "#a79c86",
    "Brick Structure": "#b0573f", "Structure": "#a8674e", "Wall": "#b0573f", "Cobbled Surface": "#9ea3a3",
    "Floor surface": "#b9ad92", "In situ burning": "#7a3b2e", "Hearth": "#8a4a33", "Topsoil": "#6b5d45",
}


# ---------------------------------------------------------------------------- build
def costruisci(spaziali, database, uscita, margine=4.0):
    os.makedirs(uscita, exist_ok=True)
    rd = lambda n: pd.read_csv(os.path.join(database, n + ".csv"), encoding="latin1", low_memory=False)
    shp = lambda n: gpd.read_file(os.path.join(spaziali, n + ".shp")).set_crs(CRS, allow_override=True)

    cd = rd("ContextData").drop_duplicates("Context Number").set_index("Context Number")
    cr = rd("ContextRegister").drop_duplicates("Context Number").set_index("Context Number")
    dating = rd("PermittedDating")

    # --- study area: hull of the published Hunting Lodge entities, inside the excavation polygon
    lodge = unary_union([shp(os.path.join("Chapter10", n)).geometry.make_valid().union_all() for n in LODGE])
    scavi = shp("Excavations")
    scavo_poly = scavi[scavi.intersects(lodge)].geometry.make_valid().union_all()
    studio = lodge.convex_hull.buffer(margine).intersection(scavo_poly)

    piano = shp("Stansted")
    piano = piano[piano.CONTEXT_ID > 0].copy()
    piano["geometry"] = piano.geometry.make_valid().buffer(0)
    piano = piano[shapely.contains_xy(studio, *np.array([[p.x, p.y] for p in piano.representative_point()]).T)]
    feats = shp("Features").drop_duplicates("FEATURE").set_index("FEATURE")

    righe = {}
    for ctx, sub in piano.groupby("CONTEXT_ID"):
        g = unary_union(list(sub.geometry)).buffer(0)
        g = MultiPolygon([p for p in getattr(g, "geoms", [g]) if p.geom_type == "Polygon" and p.area > 0.01])
        if g.is_empty:
            continue
        r = sub.iloc[0]
        righe[int(ctx)] = dict(geom=g, depth=float(sub.DEPTH.max()) if sub.DEPTH.notna().any() else np.nan,
                               feature=int(r.FEATURE) if pd.notna(r.FEATURE) else None,
                               archtype=r.ARCHTYPE, interp=r.INTERPRETN, site=r.SITECODE, status=r.STATUS)

    # --- classify: cuts (with plan), deposits with their own plan, fills without plan
    def tipo_cd(c):
        return cd.loc[c, "Context Type"] if c in cd.index else None

    def fill_of(c):
        v = cd.loc[c, "Fill of"] if c in cd.index else np.nan
        return int(v) if pd.notna(v) else None

    tagli = {c for c, r in righe.items() if tipo_cd(c) == "Cut" or (tipo_cd(c) is None and r["archtype"] in ("Cut", "SG"))}
    depositi_pianta = set(righe) - tagli
    fills = {}                                     # cut -> [fill contexts]
    for c in cd.index:
        if cd.loc[c, "Context Type"] != "Deposit":
            continue
        f = fill_of(c)
        if f is not None and f != c and f in tagli:
            fills.setdefault(f, []).append(int(c))
    for c in depositi_pianta:
        f = fill_of(c)
        if f is not None and f != c and f in tagli and c not in fills.get(f, []):
            fills.setdefault(f, []).append(c)

    base_pendio = shp("hachures")
    base_pendio = base_pendio[(base_pendio.Layer1 == "Base of Slope") & base_pendio.intersects(studio.buffer(5))]

    # --- depth of every cut, as recorded (nothing is assumed: the app fills the gaps and says so)
    def profondita(c):
        r = righe[c]
        for v, fonte in ((r["depth"], "recorded (plan)"),
                         (cd.loc[c, "Context Depth (m)"] if c in cd.index else np.nan, "recorded (context sheet)"),
                         (feats.loc[r["feature"], "MEANDEPTH"] if r["feature"] in feats.index else np.nan,
                          "feature mean depth")):
            if pd.notna(v) and 0 < float(v) < 5:
                return round(float(v), 2), fonte
        return None, "not recorded"

    def spessore(c):
        v = cd.loc[c, "Context Depth (m)"] if c in cd.index else np.nan
        return round(float(v), 2) if pd.notna(v) and 0 < float(v) < 5 else None

    info, relazioni, geom_ctx = {}, [], {}
    for c in sorted(tagli):
        geom_ctx[c] = righe[c]["geom"]
        d, fonte = profondita(c)
        info[c] = {"Depth (m)": d, "Depth source": fonte}
        for x in fills.get(c, []):
            geom_ctx[x] = righe[x]["geom"] if x in righe else righe[c]["geom"]
            info[x] = {"Thickness (m)": spessore(x),
                       "Plan outline": "own plan" if x in righe else f"outline of cut {c}"}
            relazioni.append((x, "fills", c, "archive (Fill of)"))
    for c in sorted(depositi_pianta):
        if c not in geom_ctx:
            geom_ctx[c] = righe[c]["geom"]
            info[c] = {"Thickness (m)": spessore(c), "Plan outline": "own plan"}

    # --- phases from the feature landscape
    def feature_di(c):
        if c in righe and righe[c]["feature"]:
            return righe[c]["feature"]
        f = fill_of(c)
        if f is not None and f in righe:
            return righe[f]["feature"]
        return None

    land = {}
    for c in geom_ctx:
        f = feature_di(c)
        if f in feats.index and pd.notna(feats.loc[f, "LANDNO"]):
            land[c] = int(feats.loc[f, "LANDNO"])
    codici = sorted({v for v in land.values() if v < 999})
    num_fase = {v: i + 1 for i, v in enumerate(codici)}
    fasi = [dict(Phase=0, Title="Unphased", Period="", **{"From (year)": None, "To (year)": None},
                 **{"Landscape code": 999})]
    for v in codici:
        r = dating[dating["Specific Number"] == v]
        nomi = feats[feats.LANDNO == v].LANDSCAPE.dropna()
        titolo = str(nomi.iloc[0]).split(" ", 1)[-1] if len(nomi) else (str(r["Specific Date"].iloc[0]) if len(r) else str(v))
        lo = r["Lower Date Value"].iloc[0] if len(r) else None
        hi = r["Upper Date Value"].iloc[0] if len(r) else None
        fasi.append(dict(Phase=num_fase[v], Title=titolo, Period=_periodo(lo, hi),
                         **{"From (year)": lo, "To (year)": hi, "Landscape code": v}))

    # --- context register (English)
    reg = []
    for c in sorted(geom_ctx):
        r = cd.loc[c] if c in cd.index else pd.Series(dtype=object)
        neg = c in tagli
        interp = str(r.get("Interpretation") if pd.notna(r.get("Interpretation")) else (righe.get(c, {}).get("interp") or ""))
        if neg:
            cat = "Cut"
        elif interp in ("Brick Structure", "Structure", "Wall"):
            cat = "Structure"
        elif c in [x for v in fills.values() for x in v]:
            cat = "Fill"
        else:
            cat = "Layer"
        f = feature_di(c)
        row = {"Context": c, "Type": "negative" if neg else "positive", "Category": cat, "Definition": interp,
               "Description": _txt(r.get("Brief Description")), "Interpretation": _txt(r.get("Context Comments")),
               "Phase": num_fase.get(land.get(c), 0), "Feature": f,
               "Feature type": feats.loc[f, "INTERPRETN"] if f in feats.index else None,
               "Fill of": fill_of(c) if (fill_of(c) not in (None, c)) else None,
               "Stratigraphic group": _int(r.get("SG Number")),
               "Length (m)": _num(r.get("Context Length (m)")), "Breadth (m)": _num(r.get("Context Breadth (m)")),
               "Shape in plan": _txt(r.get("Shape in Plan")), "Side shape": _txt(r.get("Side Shape")),
               "Side slope": _txt(r.get("Side Slope")), "Base": _txt(r.get("Base")),
               "Orientation": _txt(r.get("Orientation")), "Lower contact": _txt(r.get("Lower Contact")),
               "Formation": _txt(r.get("CtxtFormation")),
               "Site code": cr.loc[c, "Site Code"] if c in cr.index else righe.get(c, {}).get("site"),
               "Excavation stage": _txt(r.get("Excavation Stage")), "Date recorded": _data(r.get("Date Recorded")),
               "Colour HEX": COLORI.get(interp, "#8f8470" if not neg else None)}
        row.update(info.get(c, {}))
        reg.append(row)
    contesti = pd.DataFrame(reg)
    col_ordine = ["Context", "Type", "Category", "Definition", "Description", "Interpretation", "Phase", "Feature",
                  "Feature type", "Fill of", "Stratigraphic group", "Thickness (m)", "Depth (m)", "Depth source",
                  "Plan outline", "Length (m)", "Breadth (m)",
                  "Shape in plan", "Side shape", "Side slope", "Base", "Orientation", "Lower contact", "Formation",
                  "Site code", "Excavation stage", "Date recorded", "Colour HEX"]
    contesti = contesti[[c for c in col_ordine if c in contesti.columns]]
    rel = pd.DataFrame(relazioni, columns=["Context", "Relation", "Related context", "Source"]).drop_duplicates()

    # --- finds, samples, documentation
    fs = rd("FindsSummaries")
    fs = fs[fs.Deposit.isin(list(geom_ctx))].copy()
    fs.loc[fs.Weight >= 99999, "Weight"] = np.nan
    finds = (fs.groupby(["Deposit", "Material", "Object"], dropna=False)
             .agg(Count=("ObjectCount", "sum"), Weight=("Weight", "sum"), Date=("TypeDate", "first"),
                  Objects=("Object Number", lambda s: ", ".join(str(int(v)) for v in s.dropna().unique()[:12])))
             .reset_index().rename(columns={"Deposit": "Context", "Weight": "Weight (g)",
                                            "Objects": "Object numbers"}))
    finds["Weight (g)"] = finds["Weight (g)"].replace(0, np.nan)
    finds["Date"] = finds["Date"].replace("Undated", None)
    smp = rd("RegisteredSamples")
    smp = smp[smp["Context Number"].isin(list(geom_ctx))][["Sample Number", "Context Number", "Sample Type",
                                                     "Sample Collected for", "Type of Process", "FinalStatus"]]
    smp.columns = ["Sample", "Context", "Sample type", "Collected for", "Processing", "Status"]
    foto = rd("ContextsPhotos").merge(rd("Photographs")[["View Number", "Description"]], on="View Number", how="left")
    foto = foto[foto.Intervention.isin(list(geom_ctx))]
    sez = rd("ContextSections")
    sez = sez[sez.Intervention.isin(list(geom_ctx))]
    doc = pd.concat([
        pd.DataFrame({"ID": "Photo " + foto["View Number"].astype(str), "Context": foto.Intervention.astype(int),
                      "Subject": foto.Description.fillna("Photograph"), "Type": "Photograph",
                      "Date": None, "File": "photographs/" + foto["View Number"].astype(str) + ".jpg"}),
        pd.DataFrame({"ID": "Section " + sez["Section Number"].astype(str), "Context": sez.Intervention.astype(int),
                      "Subject": "Section drawing", "Type": "Section drawing", "Date": None,
                      "File": "sections/" + sez["Section Number"].astype(str) + ".jpg"}),
    ], ignore_index=True)

    # --- GIS
    gpkg = os.path.join(uscita, NOME + ".gpkg")
    if os.path.exists(gpkg):
        os.remove(gpkg)
    cat = contesti.set_index("Context")["Category"]
    gctx = gpd.GeoDataFrame({"context": list(geom_ctx), "category": [cat.get(c) for c in geom_ctx],
                             "feature": [feature_di(c) for c in geom_ctx],
                             "outline": [info.get(c, {}).get("Plan outline", "own plan") for c in geom_ctx]},
                            geometry=[MultiPolygon(list(getattr(g, "geoms", [g]))) for g in geom_ctx.values()], crs=CRS)
    gctx.to_file(gpkg, layer="contexts", driver="GPKG")
    area = studio.intersection(box(*gctx.total_bounds).buffer(2))
    gpd.GeoDataFrame({"name": ["Hunting Lodge study area"], "type": ["study area"]},
                     geometry=[_poligono(area)], crs=CRS).to_file(gpkg, layer="excavation_area", driver="GPKG")
    sl = shp("SectionLines")
    sl = sl[sl.intersects(area)]
    gpd.GeoDataFrame({"section": sl.SECTION_ID.astype(str).values}, geometry=sl.geometry.values, crs=CRS) \
        .to_file(gpkg, layer="section_lines", driver="GPKG")
    bp = base_pendio[base_pendio.intersects(area)]
    gpd.GeoDataFrame({"kind": bp.Layer1.values}, geometry=bp.geometry.values, crs=CRS) \
        .to_file(gpkg, layer="base_of_slope_lines", driver="GPKG")

    # --- terrain model, clipped to the area: the app uses it as reference surface
    os.makedirs(os.path.join(uscita, "rasters"), exist_ok=True)
    dem = os.path.join(uscita, "rasters", "terrain_SRTM_10m_resampled.tif")
    scrivi_dem(os.path.join(spaziali, "Chapter1", "SRTMTopography", "resampl_srtm_OSTN02_BL_10.tif"),
                area.buffer(40).bounds, dem)
    top = cd[cd.Interpretation == "Topsoil"]["Context Depth (m)"]
    arativo = float(top[(top > 0) & (top < 1.5)].median())

    # --- Excel
    xlsx = os.path.join(uscita, NOME + ".xlsx")
    info_df = pd.DataFrame({TITOLO: [
        "Source: Framework Archaeology, Stansted Framework Project digital archive (framearch.co.uk; ADS).",
        "Spatial data: plans digitised by Framework Archaeology (Stansted.shp), British National Grid.",
        "Area: the Later Medieval / Post-Medieval hunting lodge (monograph chapter 10) and its surroundings.",
        f"Built {dt.date.today().isoformat()} for practice with stratigrafia3d. Not a publication dataset.",
        "The archive has no absolute levels. Cuts carry the depth recorded on site ('Depth (m)'), deposits "
        "their thickness ('Thickness (m)'); blank = not recorded.",
        "For the 3D model use the terrain model in rasters/ as reference surface, lowered by the median "
        f"topsoil depth of the archive ({arativo:.2f} m): the app places cut bases and fills from there.",
        "Relations: only 'fills', from the archive field 'Fill of'. The order of fills inside a cut is not "
        "recorded; the app infers it from the fill type (primary at the bottom) and says so.",
        "Fills without their own plan use the outline of their cut (single-context plans were not drawn for fills).",
        "Licence: check the re-use terms stated by Framework Archaeology / ADS before any publication.",
    ]})
    with pd.ExcelWriter(xlsx, engine="openpyxl") as w:
        info_df.to_excel(w, sheet_name="Info", index=False)
        contesti.to_excel(w, sheet_name="Contexts", index=False)
        rel.to_excel(w, sheet_name="Relations", index=False)
        pd.DataFrame(fasi).to_excel(w, sheet_name="Phases", index=False)
        finds.to_excel(w, sheet_name="Finds", index=False)
        smp.to_excel(w, sheet_name="Samples", index=False)
        doc.to_excel(w, sheet_name="Documentation", index=False)
    _formatta(xlsx)
    return dict(gpkg=gpkg, xlsx=xlsx, dem=dem, contesti=len(contesti), tagli=len(tagli),
                relazioni=len(rel), finds=len(finds), documenti=len(doc), area=area, arativo=arativo,
                foto=sorted(set(foto["View Number"].astype(int))), sezioni=sorted(set(sez["Section Number"].astype(int))),
                fasi=fasi)


def scrivi_dem(sorgente, bounds, destinazione):
    """Ritaglio del DEM Framework (GeoTIFF int16, 10 m) scritto con tag GeoTIFF e EPSG:27700."""
    with tifffile.TiffFile(sorgente) as t:
        p = t.pages[0]
        z = p.asarray()
        sx, sy, _ = p.tags["ModelPixelScaleTag"].value
        _, _, _, x0, y0, _ = p.tags["ModelTiepointTag"].value
    c0, c1 = int((bounds[0] - x0) // sx), int((bounds[2] - x0) // sx) + 1
    r0, r1 = int((y0 - bounds[3]) // sy), int((y0 - bounds[1]) // sy) + 1
    sub = np.ascontiguousarray(z[r0:r1 + 1, c0:c1 + 1])
    geokeys = [1, 1, 0, 3, 1024, 0, 1, 1, 1025, 0, 1, 1, 3072, 0, 1, 27700]
    tifffile.imwrite(destinazione, sub, compression="zlib", extratags=[
        (33550, "d", 3, (sx, sy, 0.0), False),
        (33922, "d", 6, (0.0, 0.0, 0.0, x0 + c0 * sx, y0 - r0 * sy, 0.0), False),
        (34735, "H", len(geokeys), geokeys, False)])


def _poligono(g):
    ps = [p for p in getattr(g, "geoms", [g]) if p.geom_type == "Polygon"]
    return max(ps, key=lambda p: p.area) if ps else g


def _periodo(lo, hi):
    f = lambda v: "" if v is None or pd.isna(v) else (f"{int(-v)} BC" if v < 0 else f"AD {int(v)}")
    return f"{f(lo)} – {f(hi)}" if lo is not None and pd.notna(lo) else ""


def _txt(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    s = str(v).strip()
    return s or None


def _num(v):
    try:
        x = float(v)
        return None if math.isnan(x) or x <= 0 else round(x, 2)
    except (TypeError, ValueError):
        return None


def _int(v):
    try:
        return None if v is None or pd.isna(v) else int(v)
    except (TypeError, ValueError):
        return None


def _data(v):
    try:
        return pd.to_datetime(v).date().isoformat() if pd.notna(v) else None
    except Exception:
        return None


def _formatta(xlsx):
    from openpyxl import load_workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = load_workbook(xlsx)
    for ws in wb.worksheets:
        ws.freeze_panes = "A2"
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="4A4238")
            c.alignment = Alignment(vertical="center", wrap_text=True)
        for col in ws.columns:
            lung = max(len(str(c.value)) if c.value is not None else 0 for c in list(col)[:300])
            ws.column_dimensions[col[0].column_letter].width = min(max(10, lung + 2), 60 if ws.title != "Info" else 140)
        if ws.title != "Info":
            ws.auto_filter.ref = ws.dimensions
    wb.save(xlsx)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--spaziali", required=True)
    ap.add_argument("--database", required=True)
    ap.add_argument("--uscita", required=True)
    a = ap.parse_args()
    r = costruisci(a.spaziali, a.database, a.uscita)
    print({k: v for k, v in r.items() if k not in ("area", "foto", "sezioni", "fasi")})
    print("photos", len(r["foto"]), "sections", len(r["sezioni"]))
    for f in r["fasi"]:
        print(f)
