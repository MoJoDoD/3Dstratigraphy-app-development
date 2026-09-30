# -*- coding: utf-8 -*-
"""
Builds an English practice case study (GeoPackage + Excel) from the Framework Archaeology
Stansted digital archive, in the layout stratigrafia3d imports: one polygon per context,
3D level points, a context register, a relations sheet, phases, finds, documentation.

The archive records plans and tape-measured depths but no absolute levels and no
covers/covered-by relations, so the levels here are DERIVED:
    stripped surface = SRTM terrain (10 m, resampled by Framework) - median topsoil depth
    cut base         = surface - recorded depth of the intervention
    fill tops        = surface - thickness of the fills above (stacking order from the
                       fill interpretation: primary at the bottom, then secondary, ...)
Every level point carries source = "derived" and the method is written in README and Info.

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
from shapely.geometry import MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union

warnings.filterwarnings("ignore")

CRS = "EPSG:27700"          # Ordnance Survey National Grid (the archive ships without .prj)
NOME = "Stansted_Hunting_Lodge"
TITOLO = "Stansted Airport – Hunting Lodge (Framework Archaeology)"
LODGE = ["LaterMedievalHuntingLodge", "EarlyPostMedievalHuntingLodge", "PostMedievalLodge", "PostMedievalMidden"]

# stacking of fills inside a cut: larger = deeper
RANGO_FILL = {"Primary Fill": 4, "Secondary Fill": 3, "Other Fill": 2, "Deliberate Backfill": 2,
              "Placed Deposit": 2, "Tertiary Fill": 1, "Layer": 1, "Bioturbation": 1,
              "Post-pipe": 0, "Brick Structure": 3, "Structure": 3, "Wall": 3, "Floor surface": 1}
COLORI = {  # sober palette per interpretation keyword
    "Primary Fill": "#6f6150", "Secondary Fill": "#8a7a63", "Tertiary Fill": "#a39377", "Other Fill": "#958a74",
    "Deliberate Backfill": "#7d6f5a", "Placed Deposit": "#9c8360", "Post-pipe": "#5a4e40", "Layer": "#a79c86",
    "Brick Structure": "#b0573f", "Structure": "#a8674e", "Wall": "#b0573f", "Cobbled Surface": "#9ea3a3",
    "Floor surface": "#b9ad92", "In situ burning": "#7a3b2e", "Hearth": "#8a4a33", "Topsoil": "#6b5d45",
}


# ---------------------------------------------------------------------------- terrain
class Terreno:
    """SRTM GeoTIFF read with tifffile; bilinear sampling on pixel centres."""

    def __init__(self, path):
        with tifffile.TiffFile(path) as t:
            p = t.pages[0]
            self.z = p.asarray().astype(float)
            sx, sy, _ = p.tags["ModelPixelScaleTag"].value
            _, _, _, x0, y0, _ = p.tags["ModelTiepointTag"].value
        self.x0, self.y0, self.sx, self.sy = x0, y0, sx, sy

    def __call__(self, x, y):
        c = (np.asarray(x) - self.x0) / self.sx - 0.5
        r = (self.y0 - np.asarray(y)) / self.sy - 0.5
        c0 = np.clip(np.floor(c).astype(int), 0, self.z.shape[1] - 2)
        r0 = np.clip(np.floor(r).astype(int), 0, self.z.shape[0] - 2)
        fc, fr = np.clip(c - c0, 0, 1), np.clip(r - r0, 0, 1)
        z = self.z
        return ((z[r0, c0] * (1 - fc) + z[r0, c0 + 1] * fc) * (1 - fr) +
                (z[r0 + 1, c0] * (1 - fc) + z[r0 + 1, c0 + 1] * fc) * fr)


# ---------------------------------------------------------------------------- geometry helpers
def campiona_bordo(geom, n_max=120, passo_min=0.25):
    pts = []
    per = sum(r.length for p in getattr(geom, "geoms", [geom]) for r in [p.exterior, *p.interiors])
    passo = max(passo_min, per / n_max)
    for p in getattr(geom, "geoms", [geom]):
        for ring in [p.exterior, *p.interiors]:
            n = max(6, int(ring.length / passo))
            for d in np.linspace(0, ring.length, n, endpoint=False):
                q = ring.interpolate(d)
                pts.append((q.x, q.y))
    return np.array(pts)


def griglia_interna(geom, n_target=60, passo_min=0.25, distanza_min=0.0):
    passo = max(passo_min, math.sqrt(max(geom.area, 1e-6) / n_target))
    x0, y0, x1, y1 = geom.bounds
    xs, ys = np.meshgrid(np.arange(x0 + passo / 2, x1, passo), np.arange(y0 + passo / 2, y1, passo))
    P = np.c_[xs.ravel(), ys.ravel()]
    if len(P) == 0:
        return np.zeros((0, 2))
    zona = geom.buffer(-distanza_min) if distanza_min > 0 else geom
    if zona.is_empty:
        return np.zeros((0, 2))
    return P[shapely.contains_xy(zona, P[:, 0], P[:, 1])]


def raggio_inscritto(geom):
    best = 0.0
    for p in getattr(geom, "geoms", [geom]):
        try:
            c = shapely.maximum_inscribed_circle(p, tolerance=0.01)
            best = max(best, c.length)          # the result is a line centre -> boundary
        except Exception:
            best = max(best, math.sqrt(p.area / math.pi))
    return best


def punto_interno(geom):
    p = max(getattr(geom, "geoms", [geom]), key=lambda g: g.area)
    q = shapely.polylabel(p, tolerance=0.01) if hasattr(shapely, "polylabel") else p.representative_point()
    return np.array([[q.x, q.y]])


def anello_interno(geom, d):
    g = geom.buffer(-d)
    if g.is_empty:
        return np.zeros((0, 2))
    return campiona_bordo(g, n_max=80, passo_min=0.2)


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

    terreno = Terreno(os.path.join(spaziali, "Chapter1", "SRTMTopography", "resampl_srtm_OSTN02_BL_10.tif"))
    top = cd[cd.Interpretation == "Topsoil"]["Context Depth (m)"]
    arativo = float(top[(top > 0) & (top < 1.5)].median())
    sup = lambda xy: terreno(xy[:, 0], xy[:, 1]) - arativo

    base_pendio = shp("hachures")
    base_pendio = base_pendio[(base_pendio.Layer1 == "Base of Slope") & base_pendio.intersects(studio.buffer(5))]
    idx_bp = base_pendio.sindex

    # --- depth of every cut
    def profondita(c):
        r = righe[c]
        for v, fonte in ((r["depth"], "recorded (plan)"),
                         (cd.loc[c, "Context Depth (m)"] if c in cd.index else np.nan, "recorded (context sheet)"),
                         (feats.loc[r["feature"], "MEANDEPTH"] if r["feature"] in feats.index else np.nan,
                          "feature mean depth")):
            if pd.notna(v) and 0 < float(v) < 5:
                return float(v), fonte
        return 0.15, "assumed (0.15 m, not recorded)"

    livelli = []           # (context, type, x, y, z)
    info = {}              # context -> extra fields for the register
    relazioni = []
    geom_ctx = {}

    def aggiungi(c, tipo, xy, z):
        for (x, y), zz in zip(xy, np.atleast_1d(z) if np.ndim(z) else np.full(len(xy), z)):
            livelli.append((c, tipo, float(x), float(y), round(float(zz), 3)))

    for c in sorted(tagli):
        g = righe[c]["geom"]
        geom_ctx[c] = g
        d, fonte = profondita(c)
        rin = raggio_inscritto(g)
        # wall width: median distance of "base of slope" hachures from the edge, else 0.6 x depth
        bp = base_pendio.iloc[list(idx_bp.query(g))]
        bp = bp[bp.intersects(g.buffer(-0.02))] if len(bp) else bp
        base_pts = np.zeros((0, 2))
        if len(bp):
            linee = unary_union(list(bp.geometry)).intersection(g.buffer(-0.02))
            if not linee.is_empty:
                base_pts = campiona_bordo_linee(linee)
        if len(base_pts):
            dist = shapely.distance(shapely.points(base_pts[:, 0], base_pts[:, 1]), g.boundary)
            w0 = float(np.clip(np.median(dist), 0.05, 0.9 * rin if rin > 0 else 0.5))
            fonte_parete = "base-of-slope line"
        else:
            w0 = float(min(0.6 * d, 0.9 * rin if rin > 0 else 0.3, 1.1))
            fonte_parete = "assumed slope"
        w0 = max(w0, 0.04)
        orlo = campiona_bordo(g)
        aggiungi(c, "rim", orlo, sup(orlo))
        meta = anello_interno(g, w0 / 2)
        if len(meta):
            aggiungi(c, "cut", meta, sup(meta) - 0.5 * d)
        fondo = np.vstack([base_pts, griglia_interna(g, distanza_min=w0)]) if len(base_pts) else \
            griglia_interna(g, distanza_min=w0)
        if len(fondo) == 0:
            fondo = punto_interno(g)
        aggiungi(c, "cut", fondo, sup(fondo) - d)
        info[c] = {"Depth (m)": round(d, 2), "Depth source": fonte, "Side width (m)": round(w0, 2),
                   "Side source": fonte_parete}
        # recut inside another cut
        f = fill_of(c)
        if f is not None and f != c and f in tagli:
            for x in fills.get(f, []) or [f]:
                relazioni.append((c, "cuts", x))

        # fills: order top -> bottom
        lista = fills.get(c, [])
        if not lista:
            continue
        rango = lambda x: (RANGO_FILL.get(str(cd.loc[x, "Interpretation"]) if x in cd.index else "", 2), x)
        lista = sorted(lista, key=rango)
        spess = []
        for x in lista:
            v = cd.loc[x, "Context Depth (m)"] if x in cd.index else np.nan
            spess.append(float(v) if pd.notna(v) and 0 < float(v) < 5 else np.nan)
        spess = np.array(spess)
        noto = np.nansum(spess)
        n_man = int(np.isnan(spess).sum())
        if n_man:
            spess[np.isnan(spess)] = max((d - noto) / n_man, 0.05)
        registrati = spess.copy()
        scala = 1.0
        if spess.sum() > d * 1.05:
            # fills recorded in different slots of a long feature: their thicknesses do not stack
            # at one spot. Scaled so that the sequence fits the recorded depth of the cut.
            scala = d / spess.sum()
            spess = spess * scala
        cum = 0.0
        for i, x in enumerate(lista):
            gx = righe[x]["geom"] if x in righe else g
            geom_ctx[x] = gx
            prof_top = min(cum, max(d - 0.03, 0.0))
            pts = np.vstack([campiona_bordo(gx, n_max=60), griglia_interna(gx, n_target=40)])
            aggiungi(x, "top", pts, sup(pts) - prof_top)
            info[x] = {"Thickness (m)": round(float(spess[i]), 2),
                       "Recorded thickness (m)": round(float(registrati[i]), 2),
                       "Thickness note": None if scala == 1.0 else
                       f"scaled x{scala:.2f}: the recorded fills of this cut add up to more than its depth",
                       "Stack position": f"{i + 1} of {len(lista)} (from top)",
                       "Plan outline": "own plan" if x in righe else f"outline of cut {c}"}
            relazioni.append((x, "fills", c))
            if i + 1 < len(lista):
                relazioni.append((x, "covers", lista[i + 1]))
            cum += float(spess[i])

    # free-standing deposits with their own plan (cobbles, midden, layers)
    for c in sorted(depositi_pianta):
        if c in geom_ctx:
            continue
        g = righe[c]["geom"]
        geom_ctx[c] = g
        v = cd.loc[c, "Context Depth (m)"] if c in cd.index else np.nan
        t = float(v) if pd.notna(v) and 0 < float(v) < 3 else 0.10
        pts = np.vstack([campiona_bordo(g, n_max=80), griglia_interna(g, n_target=60)])
        aggiungi(c, "top", pts, sup(pts))
        info[c] = {"Thickness (m)": round(t, 2), "Plan outline": "own plan"}

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
               "Colour HEX": COLORI.get(interp, "#8f8470" if not neg else None),
               "Levels": "derived (terrain model + recorded depths)"}
        row.update(info.get(c, {}))
        reg.append(row)
    contesti = pd.DataFrame(reg)
    col_ordine = ["Context", "Type", "Category", "Definition", "Description", "Interpretation", "Phase", "Feature",
                  "Feature type", "Fill of", "Stratigraphic group", "Thickness (m)", "Recorded thickness (m)",
                  "Thickness note", "Depth (m)", "Depth source",
                  "Side width (m)", "Side source", "Stack position", "Plan outline", "Length (m)", "Breadth (m)",
                  "Shape in plan", "Side shape", "Side slope", "Base", "Orientation", "Lower contact", "Formation",
                  "Site code", "Excavation stage", "Date recorded", "Colour HEX", "Levels"]
    contesti = contesti[[c for c in col_ordine if c in contesti.columns]]
    rel = pd.DataFrame(relazioni, columns=["Context", "Relation", "Related context"]).drop_duplicates()

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
    L = pd.DataFrame(livelli, columns=["context", "level_type", "x", "y", "z"])
    glev = gpd.GeoDataFrame(L[["context", "level_type", "z"]].assign(source="derived"),
                            geometry=[Point(x, y, z) for x, y, z in zip(L.x, L.y, L.z)], crs=CRS)
    glev.to_file(gpkg, layer="levels", driver="GPKG")
    area = studio.intersection(box(*gctx.total_bounds).buffer(2))
    gpd.GeoDataFrame({"name": ["Hunting Lodge study area"], "type": ["study area"]},
                     geometry=[_poligono(area)], crs=CRS).to_file(gpkg, layer="excavation_area", driver="GPKG")
    sl = shp("SectionLines")
    sl = sl[sl.intersects(area)]
    gpd.GeoDataFrame({"section": sl.SECTION_ID.astype(str).values}, geometry=sl.geometry.values, crs=CRS) \
        .to_file(gpkg, layer="section_lines", driver="GPKG")
    bp = base_pendio[base_pendio.intersects(area)]
    gpd.GeoDataFrame({"kind": bp.Layer1.values}, geometry=bp.geometry.values, crs=CRS) \
        .to_file(gpkg, layer="hachures_base_of_slope", driver="GPKG")

    # --- Excel
    xlsx = os.path.join(uscita, NOME + ".xlsx")
    info_df = pd.DataFrame({TITOLO: [
        "Source: Framework Archaeology, Stansted Framework Project digital archive (framearch.co.uk; ADS).",
        "Spatial data: plans digitised by Framework Archaeology (Stansted.shp), British National Grid.",
        "Area: the Later Medieval / Post-Medieval hunting lodge (monograph chapter 10) and its surroundings.",
        f"Built {dt.date.today().isoformat()} for practice with stratigrafia3d. Not a publication dataset.",
        "IMPORTANT: the archive has no absolute levels. All levels are DERIVED: SRTM terrain (10 m) minus "
        f"median topsoil depth ({arativo:.2f} m) = stripped surface; cut bases from the recorded depth; fill tops "
        "from the recorded fill thicknesses, stacked by fill type (primary at the bottom).",
        "Relations: 'fills' comes from the archive (Fill of); 'covers' between fills of the same cut is "
        "INFERRED from the stacking order. There are no recorded relations between different features.",
        "Where the fills of one cut add up to more than its depth (fills recorded in different slots of a long "
        "feature), their thicknesses are scaled to fit; the recorded values stay in 'Recorded thickness (m)'.",
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
    return dict(gpkg=gpkg, xlsx=xlsx, contesti=len(contesti), tagli=len(tagli), livelli=len(L),
                relazioni=len(rel), finds=len(finds), documenti=len(doc), area=area, arativo=arativo,
                foto=sorted(set(foto["View Number"].astype(int))), sezioni=sorted(set(sez["Section Number"].astype(int))),
                fasi=fasi)


def campiona_bordo_linee(linee, passo=0.2):
    pts = []
    for l in getattr(linee, "geoms", [linee]):
        if l.geom_type != "LineString" or l.length == 0:
            continue
        for d in np.arange(0, l.length + 1e-9, passo):
            q = l.interpolate(d)
            pts.append((q.x, q.y))
    return np.array(pts) if pts else np.zeros((0, 2))


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
