# -*- coding: utf-8 -*-
"""Risorse statiche (three.js, caratteri IBM Plex) per funzionare senza internet."""
import base64
from importlib import resources

_STATICI = resources.files("stratigrafia3d.app").joinpath("statici")

FONT = [  # famiglia, peso, stile, file
    ("IBM Plex Sans Condensed", 400, "normal", "ibm-plex-sans-condensed-latin-400-normal.woff2"),
    ("IBM Plex Sans Condensed", 500, "normal", "ibm-plex-sans-condensed-latin-500-normal.woff2"),
    ("IBM Plex Sans Condensed", 600, "normal", "ibm-plex-sans-condensed-latin-600-normal.woff2"),
    ("IBM Plex Sans Condensed", 700, "normal", "ibm-plex-sans-condensed-latin-700-normal.woff2"),
    ("IBM Plex Serif", 400, "normal", "ibm-plex-serif-latin-400-normal.woff2"),
    ("IBM Plex Serif", 500, "normal", "ibm-plex-serif-latin-500-normal.woff2"),
    ("IBM Plex Serif", 400, "italic", "ibm-plex-serif-latin-400-italic.woff2"),
    ("IBM Plex Mono", 400, "normal", "ibm-plex-mono-latin-400-normal.woff2"),
    ("IBM Plex Mono", 500, "normal", "ibm-plex-mono-latin-500-normal.woff2"),
]

_LINK_FONT = [
    '<link rel="preconnect" href="https://fonts.googleapis.com">',
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+Condensed:wght@400;500;600;700&family=IBM+Plex+Serif:ital,wght@0,400;0,500;1,400&display=swap">',
]
_SCRIPT_THREE = '<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>'
_SCRIPT_ORBIT = '<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>'


def statico(percorso):
    """Byte di un file statico (percorso relativo a app/statici)."""
    p = _STATICI
    for parte in percorso.split("/"):
        if parte in ("", ".", ".."):
            raise FileNotFoundError(percorso)
        p = p.joinpath(parte)
    return p.read_bytes()


def css_font(inline=False, base="/statici/fonts/"):
    righe = []
    for fam, peso, stile, f in FONT:
        if inline:
            src = "data:font/woff2;base64," + base64.b64encode(statico("fonts/" + f)).decode()
        else:
            src = base + f
        righe.append(f"@font-face{{font-family:'{fam}';font-style:{stile};font-weight:{peso};"
                     f"font-display:swap;src:url({src}) format('woff2')}}")
    return "\n".join(righe)


def adatta_pagina(html, modo):
    """Adatta le dipendenze della pagina del visualizzatore:
    - "web": CDN e Google Fonts (per la pubblicazione online)
    - "app": file serviti dall'app locale
    - "offline": tutto incluso nel file (si apre con doppio clic, senza internet)"""
    if modo == "web":
        return html
    for l in _LINK_FONT:
        html = html.replace(l + "\n", "").replace(l, "")
    if modo == "app":
        font = f"<style>{css_font(inline=False)}</style>"
        three = '<script src="/statici/vendor/three.min.js"></script>'
        orbit = '<script src="/statici/vendor/OrbitControls.js"></script>'
    else:
        font = f"<style>{css_font(inline=True)}</style>"
        three = "<script>" + statico("vendor/three.min.js").decode("utf-8") + "</script>"
        orbit = "<script>" + statico("vendor/OrbitControls.js").decode("utf-8") + "</script>"
    html = html.replace("<style>", font + "\n<style>", 1)
    return html.replace(_SCRIPT_THREE, three).replace(_SCRIPT_ORBIT, orbit)
