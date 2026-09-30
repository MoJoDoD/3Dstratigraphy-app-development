# stratigrafia3d

Ricostruzione 3D delle unità stratigrafiche (US) a partire dalla documentazione di scavo 2D:
poligoni in pianta, quote, profili di sezione (GeoPackage) e schede (Excel).

Tappe completate: **1** (motore, riga di comando, formato `.scavo`) e **2** (app desktop con import
guidato: si apre un rilievo reale, si abbinano i campi, si ricostruisce il 3D e si salva, senza codice).
In corso la tappa **2.5** (import flessibile): la ricostruzione adattiva è pronta.

## App su Windows

1. Installa Python 3.12 da python.org (spunta "Add python.exe to PATH").
2. Doppio clic su **Installa (Windows).bat** (solo la prima volta, qualche minuto).
3. Doppio clic su **Avvia Stratigrafia 3D.bat**. Si può trascinare un file `.scavo` sull'icona per aprirlo.

L'app funziona senza internet: gira sul tuo PC e usa una finestra propria (o il browser, se la
finestra non è disponibile). Per creare un eseguibile unico c'è il workflow
`.github/workflows/eseguibile-windows.yml` (PyInstaller), che parte appena il progetto è su GitHub.

## Import flessibile

L'app e il comando `strat3d importa` accettano file "come arrivano": GeoPackage, shapefile, GeoJSON,
DXF da stazione totale (polilinee chiuse per layer `US_1005`, punti 3D, testi come etichette o quote),
CSV di punti, Excel o CSV delle schede. Riconoscono da soli:
- il ruolo di ogni layer (limiti US, murature, quote, profili, limite di scavo…) da nome e geometria;
- il campo con il numero di US (anche scritto "US 1005") confrontandolo con le schede;
- la quota dalla Z o da un campo, e il tipo di quota da un campo o dal nome del file;
- i rapporti in un foglio a sé o nelle colonne della scheda ("Copre", "Tagliato da"…);
- US negative dalla parola "taglio", spessori in centimetri, USM nello stesso foglio delle US;
- archivi in inglese: context register (Context, Type, Thickness…), rapporti "fills", "covers",
  "cut by"…, livelli "top/bottom/cut/rim", fogli Phases, Finds, Samples, Documentation.

## Ricostruzione adattiva

Le quote non sono obbligatorie. Ogni unità viene ricostruita con quello che c'è, e la strategia
usata resta scritta nel progetto (nel visualizzatore: Colore → affidabilità):

| Dati dell'unità | Ricostruzione | Strategia |
| --- | --- | --- |
| quote o profili | kriging del tetto e dello spessore | misurata |
| taglio con profondità in scheda | superficie di riferimento meno la profondità; pareti dalle linee di fondo, se ci sono | profondita |
| riempimento o strato con spessore | sotto la superficie o l'orlo del taglio, nell'ordine della sequenza | impilata |
| profondità o spessore mancanti | valori tipici (0,20 m per i tagli, 0,10 m per gli strati) | schematica |

La **superficie di riferimento** può essere un modello del terreno (GeoTIFF), una quota costante o
l'interpolazione delle quote rilevate, abbassata se serve (per esempio dell'arativo asportato). Il
modello del terreno viene copiato nel `.scavo`. Quando i rapporti non dicono l'ordine dei riempimenti
di un taglio, lo si deduce dal tipo (primario in basso) e dal numero; se gli spessori registrati
superano la profondità, si riducono in proporzione. Tutto viene segnalato nella verifica.

Aree grandi (oltre 65 m) e centinaia di unità sono gestite; `strumenti/caso_studio_stansted.py`
ricava un caso studio in inglese dall'archivio aperto di Framework Archaeology (Stansted): senza
quote, con profondità, spessori e un modello del terreno.

Ogni scelta è modificabile e si salva come profilo riutilizzabile per lo stesso cantiere.

## Installazione

```
pip install -e .[demo,test]
```

## Uso dalla riga di comando

```
strat3d app                                        # apre l'applicazione
strat3d importa rilievo.dxf schede.xlsx -o scavo.scavo   # import automatico senza interfaccia
strat3d demo cartella_demo                         # genera lo scavo dimostrativo "Podere Roveto"
strat3d verifica scavo.gpkg schede.xlsx            # controlla dati e rapporti stratigrafici
strat3d crea-progetto scavo.gpkg schede.xlsx -o scavo.scavo
strat3d info scavo.scavo
strat3d ricostruisci scavo.scavo --unita 1016      # ricalcola 1016 e le unità che le stanno sopra
strat3d visualizzatore scavo.scavo -o web/index.html
strat3d esporta-glb scavo.scavo -o scavo.glb --esploso 0.3   # si apre in Blender
```

## Uso da Python

```python
from stratigrafia3d import Scavo, ricostruisci, esporta
s = Scavo.da_sorgenti("scavo.gpkg", "schede.xlsx")
for p in s.verifica():
    print(p)
ricostruisci(s)
s.salva("scavo.scavo")
esporta.visualizzatore(s, "index.html")
```

## Dati in ingresso

**GeoPackage** (nomi in `schema.py`):
- `us_poligoni` (campo `us`) e `usm_poligoni` (campo `usm`)
- `quote` (PointZ, campi `us`, `tipo_quota`: sup, inf, taglio, orlo, rasatura, fondazione)
- facoltativi: `profili_us` (LineStringZ, campi `sezione`, `us`, `interfaccia`: sup, inf, taglio),
  `area_scavo`, `sezioni`, `sezioni_disegno`, `reperti_speciali`, `campioni`

**Excel**: fogli `US` e `Rapporti` obbligatori; `USM`, `Fasi`, `Materiali`, `Reperti_speciali`,
`Campioni`, `Documentazione` facoltativi. Nel foglio Rapporti sono accettate anche le forme inverse
(“coperto da”, “tagliato da”…).

## Il formato `.scavo`

È un GeoPackage: contiene i layer, i fogli Excel come tabelle `tab_<foglio>`, le geometrie ricostruite
(`s3d_modelli`), i parametri (`s3d_progetto`), l'impronta dei file di origine (`s3d_sorgenti`) e il
registro delle operazioni (`s3d_storico`). QGIS lo apre come GeoPackage (scegliendo "Tutti i file" o
rinominandolo in `.gpkg`).

## Metodo

Per ogni US positiva: triangolazione vincolata del poligono; tetto per trend planare + kriging dei
residui; spessore krigato attorno allo spessore medio (a zero sui bordi liberi delle lenti); base
agganciata al tetto delle unità coperte secondo i rapporti. I tagli sono superfici (orlo, fondo e
larghezza della parete stimata dai dati); le USM volumi tra rasatura e fondazione.
Ogni unità riporta quanto è misurata e quanto stimata (`qualita`).

Sullo scavo dimostrativo lo scarto mediano del tetto rispetto al modello di verità è sotto 3 cm per
il 90% delle unità (verificato da `tests/test_scavo_demo.py`).

## Test

```
pytest -q
```

## Licenza

GPL-3.0-or-later (vedi `LICENSE`). Dati dello scavo dimostrativo interamente immaginari.
