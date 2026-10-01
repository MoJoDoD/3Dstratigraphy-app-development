"""Lingue dell'interfaccia: l'italiano è la lingua di partenza, le altre sono cataloghi di traduzioni.

Un catalogo (``en.json``) associa i testi italiani, così come compaiono nell'interfaccia, alla loro
traduzione. Le chiavi con segnaposto ``{0}``, ``{1}``... valgono per i testi composti con numeri o nomi
(«{0} unità collegate»). Nelle pagine (app e visualizzatore) un piccolo script traduce i testi a mano a
mano che compaiono; nel codice Python la funzione ``t`` fa lo stesso per gli elaborati esportati.
"""
import json
import locale
import os
import re
from functools import lru_cache
from importlib import resources

LINGUE = {"it": "Italiano", "en": "English"}
CARTELLA_CONFIG = os.path.join(os.path.expanduser("~"), ".stratigrafia3d")
_FILE_IMPOSTAZIONI = os.path.join(CARTELLA_CONFIG, "impostazioni.json")


@lru_cache(maxsize=None)
def catalogo(lingua):
    if lingua == "it" or lingua not in LINGUE:
        return {}
    try:
        testo = resources.files("stratigrafia3d.lingue").joinpath(f"{lingua}.json").read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return {}
    return {k: v for k, v in json.loads(testo).items() if not k.startswith("//")}


@lru_cache(maxsize=None)
def _modelli(lingua):
    out = []
    for k, v in catalogo(lingua).items():
        if "{" in k:
            parti = re.split(r"\{(\d+)\}", k)
            # un argomento tra «» è un nome (campo, foglio, file): non contiene «» e resta com'è
            rx = "".join(re.escape(p) if i % 2 == 0 else (r"([^«»]*?)" if parti[i - 1].endswith("«") else r"(.*?)")
                         for i, p in enumerate(parti))
            ordine = [int(p) for i, p in enumerate(parti) if i % 2]
            nomi = {int(parti[i]) for i in range(1, len(parti), 2) if parti[i - 1].endswith("«")}
            letterale = max((p for i, p in enumerate(parti) if i % 2 == 0), key=len)
            fisso = sum(len(p) for i, p in enumerate(parti) if i % 2 == 0)
            out.append((fisso, letterale, re.compile("^" + rx + "$", re.S), ordine, nomi, v))
    # prima i modelli più specifici (più testo fisso)
    return [x[1:] for x in sorted(out, key=lambda x: -x[0])]


def _numero(a, lingua):
    if lingua != "it" and re.fullmatch(r"-?\d+,\d+", a):
        return a.replace(",", ".")
    return a


def traduci(testo, lingua):
    """Traduzione di un testo così come appare (esatto, o secondo un modello con segnaposto)."""
    if lingua == "it" or not testo:
        return testo
    s = str(testo)
    nucleo = s.strip()
    if not nucleo:
        return s
    c = catalogo(lingua)
    if nucleo in c:
        return s.replace(nucleo, c[nucleo])
    for letterale, rx, ordine, nomi, v in _modelli(lingua):
        if letterale and letterale not in nucleo:
            continue
        m = rx.match(nucleo)
        if m:
            args = {n: g if n in nomi else _numero(traduci(g, lingua) if len(g) < len(nucleo) else g, lingua)
                    for n, g in zip(ordine, m.groups())}
            return s.replace(nucleo, re.sub(r"\{(\d+)\}", lambda x: args.get(int(x.group(1)), ""), v))
    return s


def t(testo, *args, lingua=None):
    """Testo italiano (con segnaposto) -> testo nella lingua scelta, con gli argomenti al loro posto."""
    lingua = lingua or lingua_corrente()
    modello = catalogo(lingua).get(testo, testo) if lingua != "it" else testo
    args = [_numero(str(a), lingua) if isinstance(a, str) else a for a in args]
    return re.sub(r"\{(\d+)\}", lambda x: str(args[int(x.group(1))]) if int(x.group(1)) < len(args) else "", modello)


def lingua_di_sistema():
    try:
        if os.name == "nt":
            import ctypes
            lid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            return "it" if lid & 0x3FF == 0x10 else "en"
        loc = (locale.getlocale()[0] or os.environ.get("LANG", "") or "").lower()
        return "it" if loc.startswith("it") else "en"
    except Exception:
        return "it"


def lingua_corrente():
    """La lingua scelta: variabile d'ambiente S3D_LINGUA, poi impostazioni dell'app, poi lingua del sistema."""
    v = os.environ.get("S3D_LINGUA")
    if v in LINGUE:
        return v
    try:
        with open(_FILE_IMPOSTAZIONI, encoding="utf-8") as f:
            v = json.load(f).get("lingua")
            if v in LINGUE:
                return v
    except (OSError, ValueError):
        pass
    return lingua_di_sistema()


def imposta_lingua(lingua):
    if lingua not in LINGUE:
        raise ValueError(f"lingua sconosciuta: {lingua}")
    d = {}
    try:
        with open(_FILE_IMPOSTAZIONI, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        pass
    d["lingua"] = lingua
    if "S3D_LINGUA" in os.environ:
        os.environ["S3D_LINGUA"] = lingua
    os.makedirs(CARTELLA_CONFIG, exist_ok=True)
    with open(_FILE_IMPOSTAZIONI, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)


_JS = r"""<script>
/* traduzione dell'interfaccia (stratigrafia3d.lingue) */
(function(){
const L="__LINGUA__", C=__CATALOGO__;
window.S3D_LINGUA=L; window.S3D_LOCALE=L==="en"?"en-GB":"it-IT";
const esatte=new Map(), modelli=[];
for(const [k,v] of Object.entries(C)){
  if(k.indexOf("{")<0){ esatte.set(k,v); continue }
  const parti=k.split(/\{(\d+)\}/); let rx="", ordine=[], lett="", fisso=0; const nomi=new Set();
  parti.forEach((p,i)=>{ if(i%2){ const nm=parti[i-1].endsWith("«"); rx+=nm?"([^«»]*?)":"([\\s\\S]*?)"; ordine.push(+p); if(nm) nomi.add(+p) }
    else { rx+=p.replace(/[.*+?^${}()|[\]\\]/g,"\\$&"); fisso+=p.length; if(p.length>lett.length) lett=p } });
  modelli.push([lett,new RegExp("^"+rx+"$"),ordine,v,nomi,fisso]);
}
modelli.sort((a,b)=>b[5]-a[5]);
const numero=a=>(L!=="it"&&/^-?\d+,\d+$/.test(a))?a.replace(",","."):a;
function traduci(s){
  if(L==="it"||!s) return null;
  const n=s.trim(); if(!n||n.length>1200) return null;
  let v=esatte.get(n);
  if(v===undefined){
    for(const [lett,rx,ord,tr,nomi] of modelli){
      if(lett&&n.indexOf(lett)<0) continue;
      const m=rx.exec(n); if(!m) continue;
      const a={}; ord.forEach((k,i)=>{ const g=m[i+1]; if(nomi.has(k)){ a[k]=g; return }
        const tg=g&&g.length<n.length?traduci(g):null; a[k]=numero(tg===null?g:tg) });
      v=tr.replace(/\{(\d+)\}/g,(_,k)=>a[k]??""); break;
    }
  }
  return v===undefined?null:s.replace(n,v);
}
window.T=function(s,...args){ let t=(L!=="it"&&esatte.has(s))?esatte.get(s):(L!=="it"&&C[s])||s;
  return t.replace(/\{(\d+)\}/g,(_,k)=>{const x=args[+k]; return x==null?"":numero(String(x))}) };
if(L==="it") return;
const SALTA=new Set(["SCRIPT","STYLE","TEXTAREA","CODE"]);
const ATTR=["title","placeholder","aria-label","alt"];
function nodo(n){
  if(n.nodeType===3){ const p=n.parentNode; if(!p||SALTA.has(p.nodeName)||(p.closest&&p.closest("[data-nt]"))) return;
    const t=traduci(n.data); if(t!==null&&t!==n.data) n.data=t; return }
  if(n.nodeType!==1||SALTA.has(n.nodeName)||n.hasAttribute("data-nt")) return;
  for(const a of ATTR){ const v=n.getAttribute(a); if(v){ const t=traduci(v); if(t!==null&&t!==v) n.setAttribute(a,t) } }
  for(let c=n.firstChild;c;c=c.nextSibling) nodo(c);
}
const avvia=()=>{ nodo(document.documentElement);
  new MutationObserver(ms=>{ for(const m of ms){
    if(m.type==="characterData") nodo(m.target);
    else if(m.type==="attributes") nodo(m.target);
    else m.addedNodes.forEach(nodo) } })
  .observe(document.documentElement,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:ATTR}) };
if(document.readyState==="loading") document.addEventListener("DOMContentLoaded",avvia); else avvia();
})();
</script>"""


def script(lingua):
    """Lo script da mettere in testa a una pagina: definisce T() e traduce i testi che compaiono."""
    c = catalogo(lingua)
    return (_JS.replace("__LINGUA__", lingua if lingua in LINGUE else "it")
               .replace("__CATALOGO__", json.dumps(c, ensure_ascii=False).replace("</", "<\\/")))


def inserisci(html, lingua):
    """Inserisce lo script di traduzione prima del primo <script> della pagina (o prima di </head>)."""
    s = script(lingua)
    i = html.find("<script")
    return html[:i] + s + "\n" + html[i:] if i >= 0 else html.replace("</head>", s + "\n</head>", 1)
