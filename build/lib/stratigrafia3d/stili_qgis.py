# -*- coding: utf-8 -*-
"""
Scrive stili QGIS (QML) nella tabella `layer_styles` del GeoPackage.
QGIS li applica automaticamente quando si trascina il layer nel progetto.
"""
import sqlite3

HDR = '<!DOCTYPE qgis PUBLIC \'http://mrcc.com/qgis.dtd\' \'SYSTEM\'>\n<qgis version="3.34.0" styleCategories="Symbology|Labeling">\n'


def opt(name, value, typ="QString"):
    return f'<Option name="{name}" type="{typ}" value="{value}"/>'


def dd(prop, expr):
    """proprietà data-defined da espressione"""
    return (f'<Option name="{prop}" type="Map">{opt("active", "true", "bool")}'
            f'{opt("expression", expr)}{opt("type", "3", "int")}</Option>')


def ddblock(props):
    if not props:
        return ""
    inner = "".join(dd(k, v) for k, v in props.items())
    return (f'<data_defined_properties><Option type="Map">{opt("name", "")}'
            f'<Option name="properties" type="Map">{inner}</Option>{opt("type", "collection")}</Option>'
            f'</data_defined_properties>')


def fill_symbol(name, color="200,200,200,255", style="solid", outline="60,60,60,255", ow="0.26",
                ostyle="solid", alpha="1", props=None):
    return (f'<symbol type="fill" name="{name}" alpha="{alpha}" clip_to_extent="1" force_rhr="0" frame_rate="10" is_animated="0">'
            f'<layer class="SimpleFill" enabled="1" locked="0" pass="0"><Option type="Map">'
            f'{opt("color", color)}{opt("joinstyle", "bevel")}{opt("offset", "0,0")}{opt("offset_unit", "MM")}'
            f'{opt("outline_color", outline)}{opt("outline_style", ostyle)}{opt("outline_width", ow)}'
            f'{opt("outline_width_unit", "MM")}{opt("style", style)}</Option>{ddblock(props)}</layer></symbol>')


def line_symbol(name, color="200,0,0,255", width="0.4", style="solid", props=None):
    return (f'<symbol type="line" name="{name}" alpha="1" clip_to_extent="1" force_rhr="0" frame_rate="10" is_animated="0">'
            f'<layer class="SimpleLine" enabled="1" locked="0" pass="0"><Option type="Map">'
            f'{opt("capstyle", "round")}{opt("joinstyle", "round")}{opt("line_color", color)}'
            f'{opt("line_style", style)}{opt("line_width", width)}{opt("line_width_unit", "MM")}'
            f'</Option>{ddblock(props)}</layer></symbol>')


def marker_symbol(name, shape="circle", color="0,0,0,255", size="1.6", outline="255,255,255,255", props=None):
    return (f'<symbol type="marker" name="{name}" alpha="1" clip_to_extent="1" force_rhr="0" frame_rate="10" is_animated="0">'
            f'<layer class="SimpleMarker" enabled="1" locked="0" pass="0"><Option type="Map">'
            f'{opt("angle", "0")}{opt("color", color)}{opt("name", shape)}{opt("outline_color", outline)}'
            f'{opt("outline_style", "solid")}{opt("outline_width", "0.2")}{opt("outline_width_unit", "MM")}'
            f'{opt("scale_method", "diameter")}{opt("size", size)}{opt("size_unit", "MM")}'
            f'</Option>{ddblock(props)}</layer></symbol>')


def single(sym):
    return f'<renderer-v2 type="singleSymbol" symbollevels="0" enableorderby="0" forceraster="0"><symbols>{sym}</symbols></renderer-v2>'


def rules(rule_list, syms):
    r = "".join(f'<rule key="{{r{i}}}" filter="{f}" label="{lab}" symbol="{i}"/>' for i, (f, lab) in enumerate(rule_list))
    return (f'<renderer-v2 type="RuleRenderer" symbollevels="0" enableorderby="0" forceraster="0">'
            f'<rules key="{{root}}">{r}</rules><symbols>{"".join(syms)}</symbols></renderer-v2>')


def labels(field_expr, size="8", color="30,30,30,255", buffer=True, is_expr=False, placement="0", dist="0"):
    b = ('<text-buffer bufferDraw="1" bufferSize="0.7" bufferSizeUnits="MM" bufferColor="255,255,255,255" '
         'bufferOpacity="0.85" bufferJoinStyle="128" bufferNoFill="1"/>') if buffer else ""
    return (f'<labeling type="simple"><settings calloutType="simple">'
            f'<text-style fieldName="{field_expr}" isExpression="{1 if is_expr else 0}" fontFamily="Arial" '
            f'fontSize="{size}" fontSizeUnit="Point" textColor="{color}" fontWeight="75" namedStyle="Bold" textOpacity="1" '
            f'multilineHeight="1" allowHtml="0" fontKerning="1" capitalization="0" blendMode="0">{b}</text-style>'
            f'<text-format wrapChar="" multilineAlign="1" plussign="0" decimals="3" formatNumbers="0" reverseDirectionSymbol="0" leftDirectionSymbol="&lt;" rightDirectionSymbol="&gt;" addDirectionSymbol="0" placeDirectionSymbol="0" autoWrapLength="0" useMaxLineLengthForAutoWrap="1"/>'
            f'<placement placement="{placement}" dist="{dist}" distUnits="MM" offsetType="0" quadOffset="4" priority="5" '
            f'centroidInside="1" centroidWhole="0" fitInPolygonOnly="0" xOffset="0" yOffset="0" offsetUnits="MM"/>'
            f'<rendering drawLabels="1" obstacle="1" scaleVisibility="0" labelPerPart="0" displayAll="0" upsidedownLabels="0" fontLimitPixelSize="0" minFeatureSize="0"/>'
            f'</settings></labeling>')


def qml(renderer, labeling="", opacity="1"):
    return HDR + renderer + labeling + f'<layerOpacity>{opacity}</layerOpacity><blendMode>0</blendMode></qgis>'


STYLES = {
    "us_poligoni": qml(
        rules([("&quot;tipo&quot; = 'negativa'", "US negative (tagli)"), ("ELSE", "US positive")],
              [fill_symbol("0", color="0,0,0,0", style="no", outline="20,20,20,255", ow="0.45", ostyle="dash"),
               fill_symbol("1", alpha="0.85", props={"fillColor": '"colore_hex"'})]),
        labels("'US ' || \"us\"", size="7", is_expr=True)),
    "usm_poligoni": qml(
        single(fill_symbol("0", color="201,194,180,255", outline="70,60,50,255", ow="0.5",
                           props={"fillColor": '"colore_hex"'})),
        labels("'USM ' || \"usm\"", size="8", is_expr=True)),
    "area_scavo": qml(
        rules([("&quot;tipo&quot; = 'saggio'", "Saggio"), ("ELSE", "Limite di scavo")],
              [fill_symbol("0", color="0,0,0,0", style="no", outline="200,30,30,255", ow="0.6", ostyle="dash"),
               fill_symbol("1", color="0,0,0,0", style="no", outline="0,0,0,255", ow="0.8")]),
        labels("nome", size="8", color="200,30,30,255")),
    "griglia_2m": qml(single(fill_symbol("0", color="0,0,0,0", style="no", outline="150,150,150,160", ow="0.15", ostyle="dot")),
                      labels("quadrato", size="6", color="140,140,140,255", buffer=False)),
    "quote": qml(
        rules([("&quot;tipo_quota&quot; = 'sup'", "quota superiore"),
               ("&quot;tipo_quota&quot; = 'inf'", "quota inferiore"),
               ("&quot;tipo_quota&quot; IN ('taglio','orlo')", "quota di taglio / orlo"),
               ("&quot;tipo_quota&quot; IN ('rasatura','fondazione')", "quota muraria")],
              [marker_symbol("0", "cross2", "20,20,20,255", "1.8"),
               marker_symbol("1", "triangle", "30,90,200,255", "1.6"),
               marker_symbol("2", "diamond", "200,40,40,255", "1.6"),
               marker_symbol("3", "square", "90,90,90,255", "1.4")]),
        labels("format_number(\"quota\", 2)", size="5.5", is_expr=True, placement="0", dist="1")),
    "sezioni": qml(single(line_symbol("0", "220,0,0,255", "0.6", "dash")), labels("sezione", size="10", color="220,0,0,255", placement="2")),
    "profili_us": qml(single(line_symbol("0", "0,0,0,255", "0.25"))),
    "sezioni_disegno": qml(single(fill_symbol("0", color="200,180,150,255", outline="40,40,40,255", ow="0.2")),
                           labels("us", size="6")),
    "reperti_speciali": qml(single(marker_symbol("0", "star", "255,200,0,255", "3.2", "0,0,0,255")),
                            labels("rs", size="6.5", placement="0", dist="1.5")),
    "campioni": qml(single(marker_symbol("0", "hexagon", "0,160,120,255", "2.4", "0,0,0,255")),
                    labels("campione", size="6", placement="0", dist="1.5")),
}


def scrivi_stili(gpkg):
    con = sqlite3.connect(gpkg)
    cur = con.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS layer_styles (
        id INTEGER PRIMARY KEY AUTOINCREMENT, f_table_catalog TEXT(256), f_table_schema TEXT(256),
        f_table_name TEXT(256), f_geometry_column TEXT(256), styleName TEXT(30), styleQML TEXT,
        styleSLD TEXT, useAsDefault BOOLEAN, description TEXT, owner TEXT(30), ui TEXT(30),
        update_time DATETIME DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')))""")
    cur.execute("SELECT count(*) FROM gpkg_contents WHERE table_name='layer_styles'")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO gpkg_contents (table_name, data_type, identifier, description, last_change) "
                    "VALUES ('layer_styles','attributes','layer_styles','',strftime('%Y-%m-%dT%H:%M:%fZ','now'))")
    geomcols = dict(cur.execute("SELECT table_name, column_name FROM gpkg_geometry_columns").fetchall())
    for t, q in STYLES.items():
        if t not in geomcols:
            continue
        cur.execute("DELETE FROM layer_styles WHERE f_table_name=?", (t,))
        cur.execute("INSERT INTO layer_styles (f_table_catalog,f_table_schema,f_table_name,f_geometry_column,"
                    "styleName,styleQML,styleSLD,useAsDefault,description,owner,ui) VALUES ('','',?,?,?,?,'',1,'Stile predefinito','','')",
                    (t, geomcols[t], t, q))
    con.commit(); con.close()
