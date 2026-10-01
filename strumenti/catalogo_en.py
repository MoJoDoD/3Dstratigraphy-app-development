"""Genera src/stratigrafia3d/lingue/en.json, il catalogo inglese dell'interfaccia.

Chiavi: i testi italiani così come compaiono (un nodo di testo, un title, un messaggio); {0}, {1}...
segnano le parti variabili. Terminologia: US = SU (stratigraphic unit), USM = MSU (masonry
stratigraphic unit), scheda = record, quote = levels, rapporti = stratigraphic relationships.
Per rigenerare: python strumenti/catalogo_en.py
"""
import json
import os

T = {
    # ---------------------------------------------------------------- generale
    "Stratigrafia 3D": "Stratigrafia 3D",
    "{0} – Stratigrafia 3D": "{0} – Stratigrafia 3D",
    "– Stratigrafia 3D": "– Stratigrafia 3D",
    "Visualizzatore stratigrafico 3D": "3D stratigraphic viewer",
    "VISUALIZZATORE STRATIGRAFICO 3D": "3D STRATIGRAPHIC VIEWER",
    "Dalla pianta di scavo al volume di ogni US": "From the excavation plan to the volume of every SU",
    "Carica i limiti delle unità, le quote e le schede: l'app riconosce da sola i campi, controlla i rapporti stratigrafici e ricostruisce il modello 3D. Tutto resta sul tuo computer.":
        "Load the unit outlines, the levels and the records: the app recognises the fields by itself, checks the stratigraphic relationships and rebuilds the 3D model. Everything stays on your computer.",
    "Nuovo progetto dai file di scavo": "New project from excavation files",
    "Scegli i file del rilievo e delle schede; la procedura guidata propone come usarli.":
        "Choose the survey and record files; the guided import suggests how to use them.",
    "GPKG · SHP · DXF · GEOJSON · XLSX · CSV": "GPKG · SHP · DXF · GEOJSON · XLSX · CSV",
    "Apri un progetto": "Open a project",
    "Riprendi un progetto salvato, con il modello 3D già calcolato.": "Resume a saved project, with its 3D model already computed.",
    ".SCAVO": ".SCAVO",
    "PODERE ROVETO · DATI IMMAGINARI": "PODERE ROVETO · IMAGINARY DATA",
    "Prova con lo scavo dimostrativo": "Try the demo excavation",
    "Genera un piccolo scavo di esempio e percorri la procedura con dati già pronti.":
        "Generate a small sample excavation and walk through the procedure with ready-made data.",
    "Progetti recenti": "Recent projects",
    "Nuovo": "New", "Apri…": "Open…", "Salva": "Save", "Salva come…": "Save as…", "Verifica": "Check",
    "Ricostruisci": "Rebuild", "Esporta ▾": "Export ▾", "Esporta": "Export", "Resoconto": "Report",
    "Ctrl+S": "Ctrl+S", "Modifiche non salvate": "Unsaved changes", "nuovo progetto": "new project",
    "(non salvato)": "(not saved)", "{0} (non salvato)": "{0} (not saved)",
    "Attendere…": "Please wait…", "Annulla": "Cancel", "OK": "OK", "Chiudi": "Close", "Errore": "Error",
    "Lingua dell'interfaccia / Interface language": "Interface language / Lingua dell'interfaccia",
    "Scrivi nei file": "Write to files", "Scrivi nei file ({0})": "Write to files ({0})",
    "Scrive le modifiche fatte nell'app nei file da cui viene il progetto":
        "Writes the edits made in the app to the files the project comes from",
    "Aggiorna dai file": "Update from files", "I file d'origine sono cambiati: rileggili": "The source files have changed: read them again",
    "Apertura del progetto…": "Opening the project…", "Salvataggio…": "Saving…", "Verifica…": "Checking…",
    "Esportazione…": "Exporting…", "Lettura dei file…": "Reading the files…",
    "Creazione dello scavo dimostrativo…": "Creating the demo excavation…",
    "Applicazione della ricetta…": "Applying the recipe…", "Importazione e verifica…": "Importing and checking…",
    "Ricostruzione dei volumi 3D…": "Rebuilding the 3D volumes…", "Ricostruzione di {0} unità…": "Rebuilding {0} units…",
    "Nuova verifica…": "Checking again…", "Scrittura nei file d'origine…": "Writing to the source files…",
    "Lettura dei file d'origine e ricostruzione delle unità cambiate…": "Reading the source files and rebuilding the changed units…",
    "Apri progetto": "Open project", "Salva progetto": "Save project", "Salva come": "Save as",
    "Percorso del file": "File path", "Scrivi il percorso completo del file.": "Type the full path of the file.",
    "Percorso di un file": "Path of a file", "Progetto salvato:": "Project saved:", "Progetto salvato: {0}": "Project saved: {0}",
    "Esportato:": "Exported:", "Esportato: {0}": "Exported: {0}",
    "Il progetto aperto ha modifiche non salvate. Scrivi «sì» per continuare senza salvarle.":
        "The open project has unsaved changes. Type «sì» (yes) to continue without saving them.",
    "Modello ricostruito in {0} s.": "Model rebuilt in {0} s.", "Salvalo per conservarlo.": "Save it to keep it.",
    "Modello ricostruito in {0} s. Salvalo per conservarlo.": "Model rebuilt in {0} s. Save it to keep it.",
    "Ricostruite in {0} s.": "Rebuilt in {0} s.",
    "Nessun errore, {0} avvisi": "No errors, {0} warnings", "Nessun problema trovato": "No problems found",
    "{0} errori e {1} avvisi: apri la procedura per i dettagli": "{0} errors and {1} warnings: open the procedure for details",
    # ---------------------------------------------------------------- esporta
    "Modello 3D (.glb)": "3D model (.glb)", "Per Blender, MeshLab e visualizzatori glTF": "For Blender, MeshLab and glTF viewers",
    "Modello 3D esploso (.glb)": "Exploded 3D model (.glb)", "Unità separate in altezza di 30 cm per livello": "Units 30 cm apart for each level",
    "Pagina web (.html)": "Web page (.html)", "Visualizzatore autonomo, funziona senza internet": "Standalone viewer, works without internet",
    "Tabella dei volumi (.xlsx)": "Table of volumes (.xlsx)",
    "Area, volume, quote e affidabilità di ogni unità, totali per fase": "Area, volume, levels and reliability of every unit, totals by phase",
    "Piante per fase (.svg)": "Plans by phase (.svg)", "Una pianta per fase, scala 1:200, da stampare o ritoccare": "One plan per phase, scale 1:200, to print or retouch",
    "Pianta (.dxf)": "Plan (.dxf)", "Poligoni in coordinate reali, un layer per fase, per CAD e GIS": "Polygons in real coordinates, one layer per phase, for CAD and GIS",
    "Sezioni dal modello (.svg)": "Sections from the model (.svg)",
    "Lungo le tracce delle sezioni del GIS (o due sezioni centrali), scala 1:50": "Along the section lines of the GIS (or two central sections), scale 1:50",
    "Sezioni dal modello (.dxf)": "Sections from the model (.dxf)", "Le stesse sezioni come disegno CAD: distanza e quota": "The same sections as a CAD drawing: distance and elevation",
    "nessuna traccia di sezione nel GIS: due sezioni centrali": "no section lines in the GIS: two central sections",
    # ---------------------------------------------------------------- procedura: passi
    "File": "Files", "Layer": "Layers", "Schede e rapporti": "Records and relationships",
    "Aggiungi i file del rilievo (GeoPackage, SpatiaLite, shapefile, DXF, GeoJSON, CSV anche con geometrie, archivi .zip), le schede (Excel o più CSV collegati) e, se mancano le quote, un modello del terreno (GeoTIFF). Si possono aggiungere anche un'ortofoto (GeoTIFF a colori) e modelli 3D rilevati (OBJ, PLY). Una":
        "Add the survey files (GeoPackage, SpatiaLite, shapefile, DXF, GeoJSON, CSV also with geometries, .zip archives), the records (Excel or several linked CSV files) and, if there are no levels, a terrain model (GeoTIFF). You can also add an orthophoto (colour GeoTIFF) and surveyed 3D models (OBJ, PLY). A",
    "ricetta": "recipe",
    "ripete le scelte fatte per un archivio dello stesso tipo: ce ne sono di pronte, e ogni importazione si può salvare come ricetta.":
        "repeats the choices made for an archive of the same kind: some come ready-made, and every import can be saved as a recipe.",
    "Nessun file ancora.": "No files yet.", "Aggiungi file…": "Add files…", "Aggiungi file": "Add files",
    "…oppure incolla qui il percorso di un file e premi Invio": "…or paste the path of a file here and press Enter",
    "Ricetta": "Recipe", "Ricetta di importazione": "Import recipe", "Da file…": "From file…",
    "nessuna: proposta automatica": "none: automatic proposal", "Ricetta da file:": "Recipe from file:", "Ricetta da file: {0}": "Recipe from file: {0}",
    "Esamina i file →": "Examine the files →", "← File": "← Files", "Schede e rapporti →": "Records and relationships →",
    "← Layer": "← Layers", "Importa e verifica →": "Import and check →", "← Schede e rapporti": "← Records and relationships",
    "Salva come ricetta…": "Save as recipe…", "Ricostruisci il 3D →": "Rebuild in 3D →", "Ricostruisci comunque →": "Rebuild anyway →",
    "← Torna al progetto": "← Back to the project", "Salva la ricetta": "Save the recipe",
    "Ricetta salvata:": "Recipe saved:", "Ricetta salvata: {0}": "Recipe saved: {0}",
    "Togli {0}": "Remove {0}",
    # passo 2: layer
    "Per ogni layer trovato indica a cosa serve. Le scelte sono già proposte in base a nomi, geometrie e valori; il motivo è scritto accanto. Correggi solo ciò che non torna.":
        "For each layer found, say what it is for. Choices are already proposed from names, geometries and values; the reason is written alongside. Correct only what is wrong.",
    "Uso del layer": "Use of the layer", "Numero di US": "SU number", "Quote dai vertici": "Levels from vertices",
    "Tipo di quota": "Level type", "Perché": "Why", "Uso": "Use", "Campo": "Field", "Quota": "Level", "Dove": "Where",
    "Limiti delle US": "SU outlines", "Murature (USM)": "Walls (MSU)", "Quote": "Levels", "Profili di sezione (3D)": "Section profiles (3D)",
    "Linee di fondo dei tagli": "Base-of-slope lines of cuts", "Limite di scavo o saggio": "Excavation or trench limit",
    "Tracce delle sezioni": "Section lines", "Disegni di sezione": "Section drawings", "Reperti speciali": "Special finds",
    "Campioni": "Samples", "Non usare": "Do not use",
    "poligoni": "polygons", "linee": "lines", "punti": "points", "testi": "texts", "misto": "mixed",
    "— campo —": "— field —", "— colonna —": "— column —", "— ignora —": "— ignore —",
    "coordinata Z": "Z coordinate", "valore del testo": "text value", "non usare la Z": "do not use Z", "vertici 3D come quote": "3D vertices as levels",
    "dal campo «{0}»": "from field «{0}»", "sempre «{0}»": "always «{0}»", "etichette «{0}»": "labels «{0}»",
    "campo «{0}»": "field «{0}»", "campo:": "field:", "layer «{0}»": "layer «{0}»",
    "unità: automatica": "unit: automatic", "scelto a mano": "chosen by hand",
    "Sistema di riferimento": "Coordinate reference system",
    "I layer non dichiarano un sistema di riferimento: indicalo se lo conosci (per esempio EPSG:3003, EPSG:32633, EPSG:27700).":
        "The layers do not declare a coordinate reference system: enter it if you know it (for example EPSG:3003, EPSG:32633, EPSG:27700).",
    "I layer usano sistemi diversi: si convertono in quello indicato.": "The layers use different systems: they are converted to the one given.",
    "Letto dai file.": "Read from the files.", "es. EPSG:32633": "e.g. EPSG:32633",
    "Filtri": "Filters", "Per tenere solo una parte di un archivio più grande: un sito, un settore, un tipo di elemento.":
        "To keep only part of a larger archive: a site, a sector, a kind of feature.",
    "Nessun filtro: si importa tutto.": "No filter: everything is imported.", "Aggiungi un filtro": "Add a filter",
    "Tieni o escludi": "Keep or exclude", "tieni questi valori": "keep these values", "escludi questi valori": "exclude these values",
    "Valori da tenere": "Values to keep", "Togli il filtro": "Remove the filter",
    "Scegli prima un layer di US": "Choose an SU layer first",
    "Indica almeno un layer con i limiti delle US": "Choose at least one layer with the SU outlines",
    "Senza quote serve una superficie di riferimento (riquadro in basso)": "Without levels a reference surface is needed (box below)",
    "Scegli il foglio e la colonna con il numero di US": "Choose the sheet and the column with the SU number",
    # passo 3: schede
    "Indica dove stanno le schede delle US e i rapporti stratigrafici. I rapporti possono stare in un foglio a sé (US · rapporto · US) oppure in colonne della scheda come «Copre», «Tagliato da».":
        "Say where the SU records and the stratigraphic relationships are. Relationships can be in a sheet of their own (SU · relationship · SU) or in columns of the record such as «Covers», «Cut by».",
    "Schede US": "SU records", "Schede USM": "MSU records", "File principale": "Main file", "Foglio": "Sheet",
    "nessuno: schede dai poligoni": "none: records from the polygons", "nessuno o nello stesso foglio delle US": "none, or in the same sheet as the SUs",
    "Nessun file di schede.": "No record files.", "Nessun foglio scelto.": "No sheet chosen.", "Nessuna colonna riconosciuta": "No column recognised",
    "Altri file": "Other files", "{0} file collegati": "{0} linked files", "Colonna": "Column",
    "Unità": "Unit", "Rapporti": "Relationships", "Rapporto": "Relationship", "Prima US": "First SU", "Seconda US": "Second SU",
    "in un foglio a sé (US · rapporto · US)": "in a sheet of their own (SU · relationship · SU)",
    "in colonne della scheda US («Copre», «Taglia»…)": "in columns of the SU record («Covers», «Cuts»…)",
    "in una colonna di testo («copre 12, 15; taglia 20»)": "in a text column («covers 12, 15; cuts 20»)",
    "solo le colonne «padre» qui sotto, o nessuno": "only the «parent» columns below, or none",
    "Aggiungi una colonna «padre»": "Add a «parent» column",
    "Una colonna che indica l'unità riempita o coperta, come «Fill of» o «Riempie»": "A column naming the unit that is filled or covered, such as «Fill of» or «Riempie»",
    "l'unità della riga": "the unit of the row", "l'unità indicata": "the unit named",
    "Vocabolari": "Vocabularies", "Come leggere i valori dell'archivio. Proposti dal programma, correggili se serve.":
        "How to read the values of the archive. Proposed by the program: correct them if needed.",
    "Nessun valore da tradurre: il tipo di unità e i rapporti sono già nei termini del programma, oppure mancano.":
        "No values to translate: unit type and relationships are already in the program's terms, or missing.",
    "Tipo di unità": "Unit type", "positiva (strato)": "positive (layer)", "negativa (taglio)": "negative (cut)",
    "Tabelle collegate": "Linked tables", "Materiali e reperti": "Finds and materials", "Fasi": "Phases",
    "Documentazione (foto, disegni)": "Documentation (photos, drawings)",
    "Righe collegate alle unità tramite il loro numero: si vedono nella scheda di ogni unità.": "Rows linked to the units by their number: they appear in the record of each unit.",
    "Opzioni": "Options", "Le unità senza pianta propria (riempimenti) usano il poligono dell'unità che riempiono": "Units without their own plan (fills) use the polygon of the unit they fill",
    "Tieni solo le unità che hanno una pianta": "Keep only the units that have a plan", "Valori «vuoti»": "«Empty» values",
    "Numeri usati nell'archivio per dire «nessun valore», per esempio -9999 o -99,99": "Numbers used in the archive to mean «no value», for example -9999 or -99.99",
    "Numero di USM": "MSU number", "Superficie di riferimento e ortofoto": "Reference surface and orthophoto",
    "Da qui partono le unità senza quote proprie: i tagli scendono della loro profondità, gli strati e i riempimenti si impilano con il loro spessore. Le unità con quote rilevate non cambiano.":
        "Units without levels of their own start from here: cuts go down by their depth, layers and fills stack up with their thickness. Units with surveyed levels do not change.",
    "Tipo": "Type", "nessuna: solo le quote rilevate": "none: surveyed levels only", "piano a quota costante": "flat surface at a constant level",
    "modello del terreno (GeoTIFF)": "terrain model (GeoTIFF)", "interpolata dalle quote rilevate": "interpolated from the surveyed levels",
    "Quota (m)": "Level (m)", "Contenuto": "Contents", "Stato": "Status", "(non leggibile)": "(unreadable)", "{0} (non leggibile)": "{0} (unreadable)",
    "Nessun GeoTIFF tra i file: aggiungilo al passo 1.": "No GeoTIFF among the files: add it in step 1.",
    "{0}×{1} celle da {2} m, quote {3}–{4} m": "{0}×{1} cells of {2} m, levels {3}–{4} m",
    "Abbassa di (m)": "Lower by (m)", "Per esempio lo spessore dell'arativo asportato prima dello scavo": "For example the thickness of the ploughsoil removed before excavation",
    "Ortofoto": "Orthophoto", "nessuna": "none",
    "Nessuna immagine a colori tra i file. Un GeoTIFF RGB (ortofoto, fotopiano) si drappeggia sul modello.": "No colour image among the files. An RGB GeoTIFF (orthophoto, photomosaic) is draped on the model.",
    "{0} ({1}×{2} px, {3} cm)": "{0} ({1}×{2} px, {3} cm)",
    "Modelli 3D rilevati": "Surveyed 3D models",
    "Fotogrammetria o laser scanner (OBJ, PLY), mostrati accanto alle unità. Le coordinate devono essere quelle del GIS: se il modello è stato esportato con uno spostamento (per esempio da Metashape), scrivilo qui e verrà sommato.":
        "Photogrammetry or laser scanning (OBJ, PLY), shown alongside the units. Coordinates must be those of the GIS: if the model was exported with an offset (for example from Metashape), enter it here and it will be added.",
    "mostra nel 3D": "show in 3D", "Spostamento E, N, quota (m)": "Offset E, N, elevation (m)",
    "Anteprima del foglio delle US": "Preview of the SU sheet",
    "Scegli prima il foglio delle schede": "Choose the record sheet first",
    # campi della scheda
    "Positiva / negativa": "Positive / negative", "Categoria": "Category", "Spessore": "Thickness",
    "Spessore medio stimato (m)": "Estimated mean thickness (m)", "Spessore/profondità max (m)": "Max thickness/depth (m)",
    "Profondità (tagli)": "Depth (cuts)", "Margini": "Edges", "Margini (netti / rastremati)": "Edges (sharp / tapering)",
    "Fase": "Phase", "Colore (#rrggbb)": "Colour (#rrggbb)", "Colore HEX": "HEX colour", "Colore Munsell": "Munsell colour",
    "Definizione": "Definition", "Descrizione": "Description", "Interpretazione": "Interpretation", "Data scavo": "Excavation date",
    "Datazione da": "Dated from", "Datazione a": "Dated to", "Datazione da (anno)": "Dated from (year)", "Datazione a (anno)": "Dated to (year)",
    "Responsabile": "Recorded by", "Periodo": "Period", "Quota base usata (rilevata o stimata)": "Base level used (surveyed or estimated)",
    "Da (anno)": "From (year)", "A (anno)": "To (year)", "Titolo": "Title",
    "Classe": "Class", "Tipo / forma": "Type / form", "NR": "NR", "NMI": "MNI", "Peso (g)": "Weight (g)", "Cassetta": "Box",
    "Campione": "Sample", "Analisi": "Analysis", "Soggetto": "Subject", "Data": "Date",
    "Percorso file": "File path", "unità": "units", "{0} unità": "{0} units", "Codice": "Code",
    # passo 4: verifica
    "{0} US e {1} USM importate": "{0} SUs and {1} MSUs imported", "{0} errori": "{0} errors", "{0} avvisi": "{0} warnings",
    "errore": "error", "avviso": "warning", "info": "info", "ok": "ok",
    "Nessun problema: i dati sono pronti per la ricostruzione.": "No problems: the data are ready for the reconstruction.",
    "{0} unità": "{0} units", "Applica": "Apply", "Profondità tipica": "Typical depth", "Spessore tipico": "Typical thickness",
    "usa prima la mediana delle unità dello stesso tipo (Definizione), dove ce ne sono almeno tre":
        "first use the median of the units of the same type (Definition), where there are at least three",
    "Superficie a quota costante": "Surface at a constant level", "Reincludi tutte": "Include them all again",
    "Escludi {0} dal 3D": "Exclude {0} from 3D", "questa unità": "this unit", "queste {0} unità": "these {0} units",
    "Valori tipici aggiornati": "Typical values updated", "Unità escluse: puoi reincluderle da qui": "Units excluded: you can include them again from here",
    "Superficie di riferimento impostata": "Reference surface set", "Scrivi la quota in metri": "Type the level in metres",
    "es. 52,40": "e.g. 52.40",
    # ---------------------------------------------------------------- resoconto
    "Resoconto della ricostruzione": "Reconstruction report",
    "Quante misure sostengono ogni volume. «Stimata» vuol dire che la base viene dallo spessore della scheda, non da quote.":
        "How many measurements support each volume. «Estimated» means that the base comes from the thickness in the record, not from levels.",
    "Punti": "Points", "Base": "Base", "superficie": "surface", "misurata": "measured", "stimata": "estimated", "parziale": "partial",
    # ---------------------------------------------------------------- modifiche e file d'origine
    "Modifica salvata nel progetto": "Edit saved in the project",
    "Modifica salvata nel progetto. La forma di {0} {1} va ricostruita.": "Edit saved in the project. The shape of {0} {1} needs rebuilding.",
    "Scrivi nei file d'origine": "Write to the source files", "Scrivi": "Write",
    "{0} modifiche fatte nell'app verranno scritte nei file da cui viene il progetto, attraverso la ricetta di importazione.":
        "{0} edits made in the app will be written to the files the project comes from, through the import recipe.",
    "Prima di scrivere, una copia di ogni file va nella cartella": "Before writing, a copy of each file goes into the folder",
    "della tua cartella utente. Se un file è aperto in Excel, chiudilo.": "of your user folder. If a file is open in Excel, close it.",
    "Scrittura completata": "Writing completed", "Scrittura parziale": "Partial writing",
    "{0} modifiche scritte{1}.": "{0} edits written{1}.", "{0} modifiche scritte.": "{0} edits written.",
    "{0} modifiche scritte in {1}.": "{0} edits written to {1}.", " in ": " to ",
    "{0} restano solo nel progetto:": "{0} remain only in the project:",
    "US {0} · {1}: {2}": "SU {0} · {1}: {2}",
    "Un file d'origine è cambiato dall'ultima importazione": "A source file has changed since the last import",
    "{0} file d'origine sono cambiati dall'ultima importazione": "{0} source files have changed since the last import",
    "Aggiorna": "Update", "Modifiche non scritte": "Unwritten edits",
    "{0} modifiche fatte nell'app non sono ancora nei file d'origine. Rileggendo i file andranno perse.":
        "{0} edits made in the app are not yet in the source files. Reading the files again will lose them.",
    "Per tenerle, annulla e usa prima «Scrivi nei file».": "To keep them, cancel and use «Write to files» first.",
    "Rileggi e scartale": "Read again and discard them",
    "Nessuna unità cambiata": "No unit changed", "{0} unità cambiate nei file d'origine": "{0} units changed in the source files",
    "{0} · {1} unità ricostruite": "{0} · {1} units rebuilt", "· {0} unità ricostruite": "· {0} units rebuilt",
    # ---------------------------------------------------------------- visualizzatore
    "Dati immaginari": "Imaginary data", "DATI IMMAGINARI": "IMAGINARY DATA", "Scavo": "Excavation",
    "Caricamento del modello…": "Loading the model…", "Cerca US, USM o definizione": "Search SU, MSU or definition",
    "Cerca": "Search", "Tutte": "All", "Mostra tutte": "Show all", "Elenco delle US": "List of SUs", "Mostra fase {0}": "Show phase {0}",
    "Strumenti": "Tools", "Esploso": "Exploded", "per fase": "by phase", "per sequenza": "by sequence", "Ordine dell'esploso": "Order of the exploded view",
    "Scavo virtuale": "Virtual excavation", "nessuno": "none", "Esag. vert.": "Vert. exag.", "Sezione": "Section",
    "Piano di sezione": "Section plane", "N-S libera": "free N-S", "E-O libera": "free E-W", "Posizione del piano": "Plane position",
    "Inverti il lato conservato": "Flip the side kept", "Colore": "Colour", "Mostra": "Show",
    "Numeri di US": "SU numbers", "N.": "No.", "Spigoli": "Edges", "Quote rilevate": "Surveyed levels", "Profili": "Profiles",
    "Profili rilevati in sezione": "Profiles surveyed in section", "Reperti speciali e campioni": "Special finds and samples",
    "RS": "SF", "Superfici di taglio": "Cut surfaces", "Tagli": "Cuts", "Rilievo 3D": "3D survey",
    "Modelli 3D rilevati (fotogrammetria, laser scanner)": "Surveyed 3D models (photogrammetry, laser scanning)",
    "Pianta": "Plan", "Scheda": "Record", "Harris": "Harris", "Sezioni": "Sections", "Vista": "View",
    "Modello 3D delle unità stratigrafiche": "3D model of the stratigraphic units",
    "sedimento (Munsell)": "sediment (Munsell)", "fase": "phase", "categoria": "category", "affidabilità": "reliability",
    "ortofoto": "orthophoto", "Campi della scheda": "Record fields",
    "Colore del sedimento": "Sediment colour",
    "Colore Munsell registrato nella scheda di ogni US. Le USM in grigio pietra; i tagli sono superfici semitrasparenti.":
        "Munsell colour recorded for each SU. MSUs in stone grey; cuts are semi-transparent surfaces.",
    "reperto speciale": "special find", "campione": "sample", "Categorie": "Categories", "Affidabilità della forma": "Reliability of the shape",
    "misurata: quote o profili rilevati": "measured: surveyed levels or profiles", "da superficie e profondità": "from surface and depth",
    "impilata nella sequenza, spessore in scheda": "stacked in the sequence, thickness from the record", "schematica: valori tipici": "schematic: typical values",
    "non ricostruita": "not rebuilt", "non indicato": "not given",
    "{0}, {1} cm per pixel, proiettata dall'alto su ogni unità. Sulle pareti ripide l'immagine appare stirata.":
        "{0}, {1} cm per pixel, projected from above onto each unit. On steep sides the image looks stretched.",
    "Clic": "Click", "su un'unità per aprirne la scheda · trascina per ruotare · rotella per lo zoom · tasto destro per spostare":
        "on a unit to open its record · drag to rotate · wheel to zoom · right button to pan",
    "Scavo virtuale, passo {0} di {1}": "Virtual excavation, step {0} of {1}", "Scavo virtuale, passo": "Virtual excavation, step",
    ": asportate {0} US nell'ordine della sequenza ({1}). Le murature restano in posto.": ": {0} SUs removed in the order of the sequence ({1}). Walls stay in place.",
    "Scavo immaginario ·": "Imaginary excavation ·", "coordinate locali": "local coordinates",
    "unità stratigrafiche ricostruite in 3D a partire da poligoni, quote e profili del GIS, con": "stratigraphic units rebuilt in 3D from the polygons, levels and profiles of the GIS, with",
    "frammenti inventariati, {0} reperti speciali e {1} campioni.": "inventoried fragments, {0} special finds and {1} samples.",
    "Seleziona un'unità nella scena, nell'elenco o nel diagramma di Harris per aprirne la scheda.":
        "Select a unit in the scene, in the list or in the Harris matrix to open its record.",
    "separa le unità secondo la sequenza stratigrafica.": "separates the units according to the stratigraphic sequence.",
    "le asporta dall'alto verso il basso.": "removes them from the top down.",
    "taglia il modello con un piano: le campiture mostrano lo spessore irregolare degli strati.": "cuts the model with a plane: the hatching shows the irregular thickness of the layers.",
    # scheda
    "US {0}": "SU {0}", "USM {0}": "MSU {0}", "US {0} · {1}": "SU {0} · {1}", "Unità muraria": "Masonry unit",
    "Unità muraria · {0}": "Masonry unit · {0}", "positiva": "positive", "negativa": "negative",
    "US positiva": "positive SU", "US negativa": "negative SU",
    "Fase {0} · {1}": "Phase {0} · {1}", "Fase {0}": "Phase {0}", "Periodo {0} · fase {1}": "Period {0} · phase {1}",
    "{0} a.C.": "{0} BC", "{0} d.C.": "AD {0}",
    "Centra": "Centre", "Trasparenza": "Transparency", "Rende semitrasparenti le altre unità": "Makes the other units semi-transparent",
    "Isola": "Isolate", "Nascondi": "Hide", "Sezione qui": "Section here", "Modifica": "Edit", "Modifica la scheda e i rapporti": "Edit the record and the relationships",
    "Interpretazione.": "Interpretation.", "Ambiente": "Room", "Consistenza": "Consistency", "Componenti": "Components",
    "Morfologia": "Morphology", "Criteri": "Criteria", "Criteri di distinzione": "Distinguishing criteria",
    "Tecnica": "Technique", "Tecnica costruttiva": "Building technique", "Materiali": "Materials", "Orientamento": "Orientation",
    "Rapporti stratigrafici": "Stratigraphic relationships", "livello {0}": "level {0}", "Nessun rapporto registrato.": "No relationship recorded.",
    "copre": "covers", "coperto da": "covered by", "taglia": "cuts", "tagliato da": "cut by", "riempie": "fills", "riempito da": "filled by",
    "si appoggia a": "abuts", "gli si appoggia": "abutted by", "si lega a": "bonded with", "uguale a": "same as",
    "(dedotto)": "(inferred)", "copre (dedotto)": "covers (inferred)", "coperto da (dedotto)": "covered by (inferred)",
    "Ordine dei riempimenti dedotto dal programma, non registrato": "Order of the fills inferred by the program, not recorded",
    "{0} fr · {1} righe": "{0} fr · {1} rows", "Nessun materiale inventariato.": "No inventoried finds.",
    "Reperti speciali e campioni {0} + {1}": "Special finds and samples {0} + {1}", "{0} + {1}": "{0} + {1}",
    "Nessun reperto speciale o campione.": "No special finds or samples.", "Dati metrici": "Measurements",
    "Lunghezza": "Length", "Larghezza": "Width", "Rasatura": "Wall top", "Altezza conservata": "Surviving height",
    "Volume ricostruito": "Rebuilt volume", "Affidabilità": "Reliability", "Area documentata": "Recorded area",
    "Profondità max": "Max depth", "Spessore medio / max": "Mean / max thickness", "Stato di scavo": "Excavation status",
    "Settore": "Sector", "Data di scavo": "Excavation date", "— (superficie)": "— (surface)",
    "(rilevata)": "(surveyed)", "(stimata)": "(estimated)",
    "Il volume è ricostruito dalle quote e dai profili: tetto e base interpolati (trend + kriging), base agganciata alle unità coperte secondo i rapporti stratigrafici.":
        "The volume is rebuilt from the levels and profiles: top and base interpolated (trend + kriging), base snapped to the covered units according to the stratigraphic relationships.",
    "Altri dati della scheda": "Other record data", "Documentazione": "Documentation", "Nessuna voce.": "No entries.",
    "{0} · {1} file": "{0} · {1} files", "apri": "open", "Precedente": "Previous", "Successiva": "Next",
    "Note": "Notes", "Lunghezza (m)": "Length (m)", "Larghezza (m)": "Width (m)", "Area documentata (m²)": "Recorded area (m²)",
    "Quota max (m)": "Max level (m)", "Quota min (m)": "Min level (m)", "Stato scavo": "Excavation status",
    "Settore documentato": "Recorded sector", "Quota rasatura min": "Min wall-top level", "Quota rasatura max": "Max wall-top level",
    "Quota fondazione rilevata": "Surveyed foundation level", "Altezza conservata media (m)": "Mean surviving height (m)",
    "base misurata": "measured base", "base in parte misurata": "partly measured base", "base stimata dalla scheda": "base estimated from the record",
    "tetto da {0} punti · {1} ({2} punti)": "top from {0} points · {1} ({2} points)",
    "superficie da {0} quote e profili, {1} quote d'orlo": "surface from {0} levels and profiles, {1} rim levels",
    "({0} punti stimati)": "({0} estimated points)", "…misurata in": "…measured in",
    "quota {0} m": "level {0} m",
    # modifica della scheda
    "Modifica della scheda": "Editing the record",
    "Le modifiche restano nel progetto e si possono scrivere nei file d'origine con «Scrivi nei file».":
        "Edits stay in the project and can be written to the source files with «Write to files».",
    "Altri campi": "Other fields", "Nessun rapporto.": "No relationships.", "Aggiungi": "Add", "Salva ": "Save ",
    "L'unità {0} non è nel progetto": "Unit {0} is not in the project",
    # harris
    "Diagramma di Harris": "Harris matrix", "la sequenza dell'unità selezionata": "the sequence of the selected unit",
    "tutto il diagramma ({0} unità, {1} gruppi)": "the whole matrix ({0} units, {1} groups)",
    "Rapporti diretti dopo la riduzione transitiva: dall'alto le unità più recenti. Bordo tratteggiato = US negativa, angoli vivi = USM, tratteggio orizzontale = unità legate{0}. Colore = come nella scena.":
        "Direct relationships after transitive reduction: the most recent units at the top. Dashed border = negative SU, square corners = MSU, horizontal dashes = bonded units{0}. Colour = as in the scene.",
    ", linea a puntini = ordine dei riempimenti dedotto dal programma": ", dotted line = order of the fills inferred by the program",
    "{0} unità collegate": "{0} linked units", "su {0} livelli.": "on {0} levels.", "su {0} livelli": "on {0} levels",
    "L'unità {0} non ha rapporti registrati.": "Unit {0} has no recorded relationships.",
    "Seleziona un'unità nella scena o nell'elenco: qui compare la sua sequenza, con le unità collegate.":
        "Select a unit in the scene or in the list: its sequence appears here, with the linked units.",
    # sezioni
    "Disegno di sezione dal layer": "Section drawing from the layer", "Mostra nel 3D": "Show in 3D", "Sovrapposizioni": "Overlaps",
    "Risultato (fittizio)": "Result (fictitious)", "Scavo e dati inventati per dimostrazione": "Excavation and data invented for demonstration",
    "Tracce delle sezioni ·": "Section lines ·",
    "del GIS, esagerazione verticale ×2. Clic su un'unità per aprirne la scheda.": "of the GIS, vertical exaggeration ×2. Click on a unit to open its record.",
    "{0} · {1} – {2} · quota {3} m": "{0} · {1} – {2} · level {3} m",
}

# messaggi dal motore (verifica, importazione, errori)
T.update({
    "Ricetta applicata a {0} layer": "Recipe applied to {0} layers",
    "Fasi composte da «{0}» e «{1}»: {2} fasi numerate dalla più antica": "Phases combined from «{0}» and «{1}»: {2} phases numbered from the oldest",
    "«{0}»: {1} file estratti": "«{0}»: {1} files extracted",
    "Ortofoto «{0}»: sarà drappeggiata sul modello": "Orthophoto «{0}»: it will be draped on the model",
    "Modello del terreno «{0}» usato come superficie di riferimento per le unità senza quote": "Terrain model «{0}» used as reference surface for the units without levels",
    "{0} rapporti «{1}» dalla colonna «{2}»": "{0} «{1}» relationships from column «{2}»",
    "Rapporti non riconosciuti e ignorati: {0} (si possono tradurre nel vocabolario dei rapporti)": "Relationships not recognised and ignored: {0} (they can be translated in the relationship vocabulary)",
    "{0} fasi delle schede non compaiono nella periodizzazione: messe dopo le altre": "{0} phases of the records are not in the periodisation: placed after the others",
    "«{0}» completato dagli attributi dei poligoni per {1} unità": "«{0}» completed from the polygon attributes for {1} units",
    "Colonna Tipo assente: US negative riconosciute dalla parola «taglio»": "No Type column: negative SUs recognised by the word «taglio» (cut)",
    "US {0} ha un poligono ma nessuna scheda: aggiunta una scheda vuota": "SU {0} has a polygon but no record: an empty record was added",
    "{0} rapporti di un'unità con se stessa ignorati": "{0} relationships of a unit with itself ignored",
    "Foglio «{0}» letto come «{1}»": "Sheet «{0}» read as «{1}»",
    "Modello 3D «{0}»: {1} triangoli": "3D model «{0}»: {1} triangles", "Modello 3D «{0}»: {1} triangoli, con texture": "3D model «{0}»: {1} triangles, with texture",
    "Modello 3D «{0}»: {1} triangoli, con colori": "3D model «{0}»: {1} triangles, with colours",
    "«{0}» è un database Access: esporta le tabelle in CSV (in Access: Dati esterni → Esporta → File di testo) e aggiungi i CSV":
        "«{0}» is an Access database: export the tables to CSV (in Access: External Data → Export → Text File) and add the CSV files",
    "«{0}»: nessun file di dati riconosciuto nell'archivio": "«{0}»: no data file recognised in the archive",
    "Nessun foglio con i numeri di US: le schede verranno create dai poligoni": "No sheet with SU numbers: records will be created from the polygons",
    "quote dai vertici 3D": "levels from 3D vertices",
    "Molte schede senza pianta: i riempimenti useranno il poligono del taglio che riempiono": "Many records without a plan: fills will use the polygon of the cut they fill",
    "Le schede ({0}) sono molte più dei poligoni ({1}): si tengono solo le unità con una pianta": "There are many more records ({0}) than polygons ({1}): only units with a plan are kept",
    "Modello 3D «{0}»: sarà mostrato accanto alle unità": "3D model «{0}»: it will be shown alongside the units",
    "Nessuna quota: le unità partono da una superficie piana a quota 0. Puoi indicare una quota o un modello del terreno":
        "No levels: units start from a flat surface at level 0. You can give a level or a terrain model",
    "Colonne della ricetta non trovate: {0}": "Recipe columns not found: {0}",
    "Il foglio «{0}» della ricetta non c'è tra i file": "The recipe's sheet «{0}» is not among the files",
    "La ricetta usa un modello del terreno: aggiungilo ai file": "The recipe uses a terrain model: add it to the files",
    "Filtri: {0} elementi di «{1}» esclusi": "Filters: {0} features of «{1}» excluded",
    "Limite di scavo ritagliato attorno alle unità importate": "Excavation limit clipped around the imported units",
    "{0} numeri disegnati sia tra le US sia tra le USM: tenuta la pianta delle US ({1})": "{0} numbers drawn both as SUs and as MSUs: the SU plan is kept ({1})",
    "Filtri: {0} schede escluse": "Filters: {0} records excluded",
    "{0} unità senza pianta propria: usato il poligono dell'unità che riempiono": "{0} units without their own plan: the polygon of the unit they fill is used",
    "{0} schede senza poligono escluse": "{0} records without a polygon excluded",
    "{0} rapporti con unità escluse dai filtri tralasciati": "{0} relationships with units excluded by the filters left out",
    "{0} quote senza US: {1} assegnate dalla posizione, {2} scartate (più poligoni sovrapposti o nessuno)": "{0} levels without an SU: {1} assigned from their position, {2} discarded (several overlapping polygons or none)",
    "Modello del terreno non trovato: superficie di riferimento non impostata": "Terrain model not found: reference surface not set",
    "Superficie di riferimento non impostata: {0}": "Reference surface not set: {0}",
    "Ortofoto non trovata: il modello resterà senza immagine": "Orthophoto not found: the model will have no image",
    "Modello 3D non trovato: {0}": "3D model not found: {0}",
    "«{0}» non è un archivio zip valido (download incompleto?)": "«{0}» is not a valid zip archive (incomplete download?)",
    "Schede US nel foglio «{0}» (colonna «{1}»)": "SU records in sheet «{0}» (column «{1}»)",
    "Schede US nel foglio «{0}» (colonna «{1}»), USM nel foglio «{2}»": "SU records in sheet «{0}» (column «{1}»), MSUs in sheet «{2}»",
    "{0} altri file di tabelle collegati": "{0} other table files linked",
    "nome «{0}»": "name «{0}»", "numero di US dal campo «{0}»": "SU number from field «{0}»", "tipo di quota dal campo «{0}»": "level type from field «{0}»",
    "tipo di quota «{0}» per tutti i punti": "level type «{0}» for all points", "{0} quote dai vertici 3D di «{1}»": "{0} levels from the 3D vertices of «{1}»",
    "{0} poligoni di «{1}» senza numero di US: ignorati": "{0} polygons of «{1}» without an SU number: ignored",
    "«{0}»: nessun poligono con un numero di unità, layer ignorato": "«{0}»: no polygon with a unit number, layer ignored",
    "«{0}»: tenute le {1} righe delle unità del progetto su {2}": "«{0}»: kept the {1} rows of the project's units out of {2}",
    "Documentazione: {0} file trovati su {1} citati": "Documentation: {0} files found out of {1} listed",
    "Documentazione: {0} file trovati su {1} citati (gli altri non sono nelle cartelle del progetto)": "Documentation: {0} files found out of {1} listed (the others are not in the project folders)",
    "Ortofoto «{0}»: {1} × {2} pixel, {3} cm": "Orthophoto «{0}»: {1} × {2} pixels, {3} cm",
    "Modello 3D «{0}» non letto: {1}": "3D model «{0}» not read: {1}",
    "Il modello 3D «{0}» è a più di un chilometro dallo scavo: forse è stato esportato con uno spostamento delle coordinate, da indicare nel riquadro dei modelli 3D":
        "The 3D model «{0}» is more than a kilometre from the excavation: it was probably exported with a coordinate offset, to be entered in the 3D models box",
    "punti con quota": "points with levels", "punti senza quota": "points without levels",
    "numero di US dalle etichette «{0}»": "SU number from the labels «{0}»", "Schede dalle colonne di «{0}» (numero: «{1}»)": "Records from the columns of «{0}» (number: «{1}»)",
    "{0} punti di «{1}» senza quota o con quota nulla: ignorati": "{0} points of «{1}» without a level or with an empty level: ignored",
    "«{0}»: tenuti i {1} elementi attorno alle unità (su {2})": "«{0}»: kept the {1} features around the units (out of {2})",
    "Ortofoto non letta: {0}": "Orthophoto not read: {0}", "Rapporti «{0}» dalla colonna «{1}»": "«{0}» relationships from column «{1}»",
    "Rapporti dal foglio «{0}»": "Relationships from sheet «{0}»",
    "linee 3D": "3D lines", "linee 2D": "2D lines", "US assegnata dalla posizione (solo dove un solo poligono contiene il punto)": "SU assigned from the position (only where a single polygon contains the point)",
    "quota dal campo «{0}»": "level from field «{0}»", "testi con valori di quota": "texts with level values", "testi (usabili come etichette)": "texts (usable as labels)",
    "quote dai vertici 3D": "levels from 3D vertices", "ruolo dal nome": "role from the name",
    "{0} non è un progetto stratigrafia3d": "{0} is not a stratigrafia3d project",
    "progetto creato con una versione più recente del programma": "project created with a newer version of the program",
    "Modello 3D: {0} unità, volume totale {1} m³, basi stimate: {2}": "3D model: {0} units, total volume {1} m³, estimated bases: {2}",
    "Modello 3D: non ancora calcolato": "3D model: not yet computed",
    "manca il file del modello del terreno": "the terrain model file is missing",
    "i layer non dichiarano un sistema di riferimento": "the layers do not declare a coordinate reference system",
    "poligoni con un numero di US che non compare nell'Excel": "polygons with an SU number that is not in the records",
    "{0} unità escluse dalla ricostruzione 3D (restano nelle schede e nel diagramma di Harris)": "{0} units excluded from the 3D reconstruction (they remain in the records and in the Harris matrix)",
    "schede senza poligono in pianta: non avranno un volume": "records without a polygon in plan: they will have no volume",
    "tipi di quota non riconosciuti: {0}": "level types not recognised: {0}",
    "{0} rapporti «copre» tra riempimenti dello stesso taglio dedotti dal tipo di riempimento (primario in basso) e dal numero":
        "{0} «covers» relationships between fills of the same cut inferred from the fill type (primary at the bottom) and the number",
    "unità senza quote e senza superficie di riferimento: impossibile ricostruirle (indica una superficie di riferimento o aggiungi le quote)":
        "units without levels and without a reference surface: they cannot be rebuilt (give a reference surface or add levels)",
    "{0} unità senza quote inferiori: la base viene dall'unità sottostante o dallo spessore della scheda": "{0} units without lower levels: the base comes from the unit below or from the thickness in the record",
    "quote a oltre 30 cm dal poligono della propria unità": "levels more than 30 cm from the polygon of their unit",
    "manca il layer '{0}'": "layer '{0}' is missing", "manca il foglio Excel '{0}'": "Excel sheet '{0}' is missing",
    "{0} unità ricostruite da {1}": "{0} units rebuilt from {1}",
    "quote o profili rilevati": "surveyed levels or profiles",
    "superficie di riferimento (o tetto delle unità tagliate) e profondità della scheda": "reference surface (or top of the units cut) and depth from the record",
    "posizione nella sequenza e spessore della scheda": "position in the sequence and thickness from the record",
    "valori tipici (profondità o spessore non registrati)": "typical values (depth or thickness not recorded)",
    "non ricostruibile: servono quote o una superficie di riferimento": "cannot be rebuilt: levels or a reference surface are needed",
    "{0} tagli senza profondità registrata: si usa {1} m": "{0} cuts without a recorded depth: {1} m is used",
    "{0} tagli senza profondità registrata: si usa la mediana delle unità dello stesso tipo o {1} m": "{0} cuts without a recorded depth: the median of the units of the same type is used, or {1} m",
    "{0} unità senza spessore registrato: si usa {1} m (nei tagli, lo spazio rimasto)": "{0} units without a recorded thickness: {1} m is used (inside cuts, the remaining space)",
    "{0} unità senza spessore registrato: si usa la mediana delle unità dello stesso tipo o {1} m (nei tagli, lo spazio rimasto)":
        "{0} units without a recorded thickness: the median of the units of the same type is used, or {1} m (inside cuts, the remaining space)",
    "{0} tagli hanno riempimenti che, sommati, superano la profondità (probabilmente registrati in punti diversi): spessori ridotti in proporzione":
        "{0} cuts have fills whose total exceeds the depth (probably recorded at different points): thicknesses scaled down",
    "riga ignorata: {0}": "row ignored: {0}", "sequenza impossibile: ogni unità risulta posteriore alla successiva": "impossible sequence: each unit is later than the next one",
    "due unità sono sia contemporanee sia in sequenza": "two units are both contemporary and in sequence",
    "rapporti verso unità che non hanno una scheda": "relationships to units that have no record", "unità senza alcun rapporto": "units without any relationship",
    "ciclo nella sequenza: {0}": "cycle in the sequence: {0}",
    "L'unità {0} non ha una scheda nel progetto": "Unit {0} has no record in the project", "Scheda dell'unità {0} non trovata": "Record of unit {0} not found",
    "Il progetto non ricorda da quali file viene: riscrittura impossibile": "The project does not know which files it comes from: it cannot write back",
    "Il progetto non ricorda da quali file viene": "The project does not know which files it comes from",
    "{0} modifiche non ancora scritte nei file d'origine: scrivile prima, oppure scartale": "{0} edits not yet written to the source files: write them first, or discard them",
    "File d'origine non trovati: {0}": "Source files not found: {0}", "«{0}» non è un numero": "«{0}» is not a number",
    "Rapporto «{0} {1} {2}» non trovato": "Relationship «{0} {1} {2}» not found", "Rapporto «{0}» sconosciuto": "Unknown relationship «{0}»",
    "Un'unità non può avere un rapporto con se stessa": "A unit cannot have a relationship with itself", "L'unità {0} non esiste nel progetto": "Unit {0} does not exist in the project",
    "Il rapporto crea un ciclo nella sequenza: {0}": "The relationship creates a cycle in the sequence: {0}",
    "Colonna «{0}» assente in «{1}»": "Column «{0}» missing in «{1}»", "Il foglio «{0}» non si trova più nei file d'origine": "Sheet «{0}» is no longer in the source files",
    "le schede non vengono da un foglio (sono state create dai poligoni)": "the records do not come from a sheet (they were created from the polygons)",
    "la fase viene da periodo + fase: correggila nel file d'origine": "the phase comes from period + phase: correct it in the source file",
    "nessuna riga per l'unità {0} in «{1}»": "no row for unit {0} in «{1}»", "{0} righe per l'unità {1} in «{2}»": "{0} rows for unit {1} in «{2}»",
    "la cella di «{0}» contiene una formula: correggi i dati da cui dipende": "the cell of «{0}» contains a formula: correct the data it depends on",
    "la ricetta non dice dove scrivere questo rapporto": "the recipe does not say where to write this relationship",
    "Il tipo deve essere «positiva» o «negativa»": "The type must be «positiva» (positive) or «negativa» (negative)",
    "Formato non riscrivibile: {0}": "Format that cannot be written back: {0}",
    "il campo viene dagli attributi dei poligoni, non dalla scheda": "the field comes from the polygon attributes, not from the record",
    "il campo «{0}» non ha una colonna nel file d'origine": "field «{0}» has no column in the source file",
    "Ortofoto troppo grande ({0} × {1} pixel): riducila nel GIS a una risoluzione adatta alla vista d'insieme (per esempio 5 cm)":
        "Orthophoto too large ({0} × {1} pixels): reduce it in the GIS to a resolution suited to an overall view (for example 5 cm)",
    "Per le ortofoto serve il pacchetto 'Pillow': esegui di nuovo l'installazione": "Orthophotos need the 'Pillow' package: run the installation again",
    "L'ortofoto non copre l'area dello scavo": "The orthophoto does not cover the excavation area", "Impossibile leggere l'ortofoto: {0}": "Cannot read the orthophoto: {0}",
    "Il raster non è georiferito (mancano tag GeoTIFF e file .tfw)": "The raster is not georeferenced (GeoTIFF tags and .tfw file are missing)",
    "Per leggere i raster serve il pacchetto 'tifffile': esegui di nuovo l'installazione (Installa (Windows).bat)": "Reading rasters needs the 'tifffile' package: run the installation again (Installa (Windows).bat)",
    "Raster ruotato nel file .tfw: non supportato": "Rotated raster in the .tfw file: not supported", "Raster ruotato: non supportato": "Rotated raster: not supported",
    "Compressione del raster non supportata ({0}); salvalo senza compressione o con compressione DEFLATE": "Raster compression not supported ({0}); save it uncompressed or with DEFLATE compression",
    "Il file OBJ non contiene triangoli": "The OBJ file contains no triangles",
    "Il file PLY non contiene una superficie a triangoli (forse è solo una nuvola di punti)": "The PLY file contains no triangle surface (perhaps it is only a point cloud)",
    "Non è un file PLY": "Not a PLY file", "Formato di modello 3D non supportato: {0}": "3D model format not supported: {0}", "Intestazione PLY incompleta": "Incomplete PLY header",
    "Azione sconosciuta: {0}": "Unknown action: {0}", "File non trovato: {0}": "File not found: {0}", "Nessun progetto aperto": "No project open",
    "File non trovati: {0}": "Files not found: {0}", "Aggiungi almeno un file": "Add at least one file", "File non collegato al progetto": "File not linked to the project",
    "Scegli dove salvare il progetto": "Choose where to save the project", "Prima ricostruisci il modello 3D": "Rebuild the 3D model first",
    "Scegli il file di destinazione": "Choose the destination file", "Impossibile aprire il progetto: {0}": "Cannot open the project: {0}",
    "La verifica ha trovato errori: correggili prima di ricostruire": "The check found errors: correct them before rebuilding",
    "Impossibile scrivere {0}: il file è aperto in un altro programma?": "Cannot write {0}: is the file open in another program?",
    "Impossibile scrivere {0}: il file è aperto in un altro programma (Excel?). Chiudilo e riprova": "Cannot write {0}: the file is open in another program (Excel?). Close it and try again",
    "Accesso non autorizzato": "Unauthorised access", "Indica un valore in metri maggiore di zero": "Give a value in metres greater than zero",
    "Errore imprevisto: {0}": "Unexpected error: {0}",
    "modello 3D non calcolato": "3D model not computed", "Sezione di lunghezza nulla": "Section of zero length",
    "Le sezioni non attraversano nessuna unità": "The sections do not cross any unit", "Nessuna unità da disegnare": "No units to draw",
    "Nessuna unità nelle fasi indicate": "No units in the phases given",
    "modello 3D non calcolato: eseguire prima la ricostruzione": "3D model not computed: run the reconstruction first",
    "i rapporti stratigrafici contengono un ciclo: esegui la verifica": "the stratigraphic relationships contain a cycle: run the check",
    # ricette
    "Framework Archaeology (Stansted, Heathrow T5)": "Framework Archaeology (Stansted, Heathrow T5)",
    "Archivi digitali di Framework Archaeology così come si scaricano: pianta degli interventi (Stansted.shp o «T5 Volume 2.shp»), ContextData.csv e le altre tabelle CSV, il modello del terreno. Le quote delle unità non ci sono: i tagli scendono della profondità registrata dal piano di scavo, ricavato dal terreno abbassato di 30 cm (arativo) oppure, per Heathrow, dalla topografia del 1943 più il modello di troncamento. I riempimenti prendono il poligono del loro intervento. A Heathrow i punti quotati (DPs.shp, quota in ZCOORD) danno il piano di scavo dove il modello di troncamento non arriva. Conviene filtrare per sito: SITECODE per la pianta degli interventi e SiteCode per DPs (due filtri, uno per layer: i nomi delle colonne sono diversi; in DPs alcuni siti hanno più valori, es. «TEC05» e «TEC05 Phase1»).":
        "Framework Archaeology digital archives as downloaded: plan of the interventions (Stansted.shp or «T5 Volume 2.shp»), ContextData.csv and the other CSV tables, the terrain model. The units have no levels: cuts go down by the recorded depth from the excavation surface, derived from the terrain lowered by 30 cm (ploughsoil) or, for Heathrow, from the 1943 topography plus the truncation model. Fills take the polygon of their intervention. At Heathrow the spot heights (DPs.shp, level in ZCOORD) give the excavation surface where the truncation model does not reach. Filtering by site is advisable: SITECODE for the plan of the interventions and SiteCode for DPs (two filters, one per layer: the column names differ; in DPs some sites have several values, e.g. «TEC05» and «TEC05 Phase1»).",
    "pyArchInit (database SpatiaLite o esportazioni)": "pyArchInit (SpatiaLite database or exports)",
    "Database di pyArchInit per QGIS (SpatiaLite): layer pyunitastratigrafiche (limiti delle US), pyunitastratigrafiche_usm e pyarchinit_quote, tabella us_table con le schede e i rapporti scritti nel formato di pyArchInit, periodizzazione_table per le fasi (periodo + fase, ordinate per anno). Provata sul database di esempio distribuito con pyArchInit. Le unità senza quote proprie partono dalla superficie interpolata tra le quote rilevate. Se il database contiene più siti, aggiungi un filtro sul campo «sito» della scheda e su «scavo_s» del layer.":
        "pyArchInit database for QGIS (SpatiaLite): layers pyunitastratigrafiche (SU outlines), pyunitastratigrafiche_usm and pyarchinit_quote, table us_table with the records and the relationships written in pyArchInit format, periodizzazione_table for the phases (period + phase, ordered by year). Tested on the sample database distributed with pyArchInit. Units without levels of their own start from the surface interpolated between the surveyed levels. If the database holds several sites, add a filter on the «sito» field of the record and on «scavo_s» of the layer.",
})

# ---------------------------------------------------------------- elaborati esportati e testi brevi
T.update({
    "US": "SU", "USM": "MSU", "US/USM": "SU/MSU", "taglio": "cut", "Cass.": "Box", "Datazione": "Date",
    "Dove sono": "Where they are",
    "profondita": "depth", "impilata": "stacked", "schematica": "schematic",
    "Per fase": "By phase", "Nota": "Note", "Progetto: {0}": "Project: {0}", "Coordinate: {0}.": "Coordinates: {0}.",
    "locali": "local", "Area in pianta (m²)": "Plan area (m²)", "Volume (m³)": "Volume (m³)",
    "Quota massima (m)": "Highest level (m)", "Quota minima (m)": "Lowest level (m)", "Spessore medio (m)": "Mean thickness (m)",
    "Profondità del taglio (m)": "Depth of cut (m)", "Strategia": "Strategy", "Centro E": "Centre E", "Centro N": "Centre N",
    "Volumi calcolati dalle mesh chiuse ricostruite; i tagli sono superfici e non hanno volume.":
        "Volumes computed from the reconstructed closed meshes; cuts are surfaces and have no volume.",
    "«Strategia» dice da quali dati viene la forma (misurata, profondità, impilata, schematica).":
        "«Strategy» tells which data the shape comes from (measured, depth, stacked, schematic).",
    "Sezione {0}": "Section {0}", "Sezione E-O (centrale)": "E-W section (central)", "Sezione N-S (centrale)": "N-S section (central)",
    "{0} — sezioni dal modello 3D, scala 1:{1}": "{0} — sections from the 3D model, scale 1:{1}",
    ", altezze ×{0}": ", heights ×{0}", "US {0} (taglio)": "SU {0} (cut)",
    "{0} — piante per fase, scala 1:{1}": "{0} — plans by phase, scale 1:{1}",
    "TAGLI": "CUTS", "NUMERI": "NUMBERS", "TITOLI": "TITLES", "RIFERIMENTI": "REFERENCES",
    "US_fase_{0}_{1}": "SU_phase_{0}_{1}", "US_fase_{0}": "SU_phase_{0}", "USM_fase_{0}": "MSU_phase_{0}",
    "Rilievo {0}": "Survey {0}",
    "Mostra {0}": "Show {0}", "Scavo immaginario · {0}": "Imaginary excavation · {0}", "{0}; {1}": "{0}; {1}",
    "l'unità della riga {0} l'unità indicata": "the unit of the row {0} the unit named",
    "Copre": "Covers", "Coperto da": "Covered by", "Taglia": "Cuts", "Tagliato da": "Cut by", "Riempie": "Fills",
    "Riempito da": "Filled by", "Si lega a": "Bonded with", "Si appoggia a": "Abuts", "Gli si appoggia": "Abutted by",
    "Uguale a": "Same as",
    "Progetto stratigrafia3d": "stratigrafia3d project", "Dati di scavo": "Excavation data", "GIS e CAD": "GIS and CAD",
    "Schede": "Records", "glTF binario": "Binary glTF", "Pagina web": "Web page", "Foglio Excel": "Excel workbook",
    "Disegno SVG": "SVG drawing", "Disegno DXF": "DXF drawing", "Ricetta di importazione": "Import recipe", "Tutti i file": "All files",
    "Correzione": "Correction",
    "Collegamento a «{0}» non applicato: tabella o colonne mancanti": "Link to «{0}» not applied: table or columns missing",
    "«{0}» collegato alle schede con «{1}»: {2} schede su {3}": "«{0}» linked to the records through «{1}»: {2} records out of {3}",
    "Fasi dalla colonna «{0}»: {1} fasi numerate dalla più antica": "Phases from column «{0}»: {1} phases numbered from the oldest",
    "Il raster di correzione copre solo il {0} dell'area dello scavo: fuori si usa il valore del suo bordo più vicino":
        "The correction raster covers only {0} of the excavation area: outside it, the value at its nearest edge is used", "{0} (differenze)": "{0} (differences)",
    "Un raster di differenze da sommare al modello del terreno, per esempio il modello di troncamento (valori negativi)":
        "A raster of differences to add to the terrain model, for example the truncation model (negative values)",
    "«{0}» contiene differenze di quota (valori negativi): sommato al modello del terreno come troncamento":
        "«{0}» holds level differences (negative values): added to the terrain model as truncation",
    "Raster di correzione «{0}» non trovato: non usato": "Correction raster «{0}» not found: not used",
    "serve la pianta delle unità per sommare il raster di correzione": "the unit plans are needed to add the correction raster",
    "Impossibile aprire la finestra dell'app ({0}: {1}).": "Cannot open the app window ({0}: {1}).",
    "Stratigrafia 3D viene aperta nel browser predefinito.": "Stratigrafia 3D is opening in the default browser.",
    "{0} ({1} punti stimati)": "{0} ({1} estimated points)", "schede US «{0}»": "SU records «{0}»",
})

# ---------------------------------------------------------------- tabelle grezze (note di normalizzazione)
T.update({
    "{0} colonne vuote tolte": "{0} empty columns removed",
    "Schede in blocchi etichetta/valore: {0} unità riportate su righe con {1} campi":
        "Records in label/value blocks: {0} units laid out as rows with {1} fields",
    "Il foglio contiene {0} tabelle separate da righe vuote: si usa «{1}»":
        "The sheet holds {0} tables separated by empty rows: «{1}» is used",
    "Tabella trasposta (un'unità per colonna): {0} unità riportate su righe":
        "Transposed table (one unit per column): {0} units laid out as rows",
    "Matrice dei rapporti: {0} rapporti riportati in elenco (US, rapporto, US correlata)":
        "Relationship matrix: {0} relationships turned into a list (SU, relationship, related SU)",
    "Nella matrice i segni «{0}» sono letti come «la riga copre la colonna»":
        "In the matrix the marks «{0}» are read as «the row covers the column»",
    "Segni della matrice non riconosciuti e ignorati: {0}": "Matrix marks not recognised and ignored: {0}",
    "Intestazione alla riga {0}: {1} righe sopra (titoli, righe vuote) ignorate":
        "Header on row {0}: {1} rows above (titles, empty rows) ignored",
    "Intestazione su {0} righe: nomi uniti (es. «{1}»)": "Header on {0} rows: names joined (e.g. «{1}»)",
    "Nomi di colonna ripuliti (spazi, a capo, colonne senza nome o doppie)":
        "Column names cleaned up (spaces, line breaks, unnamed or duplicate columns)",
    "{0} righe vuote tolte": "{0} empty rows removed",
    "{0} righe che ripetono l'intestazione o il titolo tolte (salti pagina)":
        "{0} rows repeating the header or the title removed (page breaks)",
    "{0} righe di totale tolte": "{0} total rows removed",
    "{0} righe di note in fondo alla tabella tolte": "{0} rows of notes at the bottom of the table removed",
    "Tabella campo/valore: {0} unità riportate su righe con {1} campi":
        "Field/value table: {0} units laid out as rows with {1} fields",
    "Colonna «{0}»: valori convertiti da {1} a metri (ora «{2}»)": "Column «{0}»: values converted from {1} to metres (now «{2}»)",
    "Colonna «{0}»: unità di misura tolte dai valori e convertite in metri":
        "Column «{0}»: units of measurement removed from the values and converted to metres",
    "Colonna «{0}»: numeri con la virgola decimale o i separatori delle migliaia convertiti":
        "Column «{0}»: numbers with a decimal comma or thousands separators converted",
    "Foglio «{0}»: {1}": "Sheet «{0}»: {1}",
})

# ---------------------------------------------------------------- vocabolario dei termini: motivi e spiegazioni
T.update({
    # motivo = «nome» + come è stato riconosciuto + per che cosa; poi conferme e attendibilità
    "«{0}» è {1} per {2}": "«{0}» is {1} for {2}",
    "«{0}» contiene «{1}», {2} per {3}": "«{0}» contains «{1}», {2} for {3}",
    "«{0}» è parte di «{1}», {2} per {3}": "«{0}» is part of «{1}», {2} for {3}",
    "«{0}» somiglia a «{1}», {2} per {3}": "«{0}» resembles «{1}», {2} for {3}",
    "«{0}» ha la forma di una sigla per {1}": "«{0}» has the form of a code for {1}",
    "un termine aggiunto dall'utente": "a term added by the user", "un termine indicato dalla ricetta": "a term given by the recipe",
    "il nome usato da {0}": "the name used by {0}", "un'abbreviazione comune": "a common abbreviation",
    "un termine generico": "a generic term", "un termine noto": "a known term",
    "un termine italiano": "an Italian term", "un termine inglese": "an English term", "un termine francese": "a French term",
    "un termine tedesco": "a German term", "un termine spagnolo": "a Spanish term", "un termine svedese": "a Swedish term",
    "un termine olandese": "a Dutch term", "un termine {0}": "a {0} term",
    "{0} (indizio debole)": "{0} (weak clue)",
    "{0}; il contesto («{1}») lo conferma": "{0}; the context («{1}») confirms it",
    "il contesto («{0}») lo conferma": "the context («{0}») confirms it",
    "{0}; la geometria lo conferma": "{0}; the geometry confirms it", "la geometria lo conferma": "the geometry confirms it",
    "{0} (attendibilità {1}%)": "{0} (confidence {1}%)",
    "{0}; nel programma: «{1}»": "{0}; in the program: «{1}»", "nel programma: «{0}»": "in the program: «{0}»",
    "{0}. Altre possibilità: {1} ({2}%)": "{0}. Other possibilities: {1} ({2}%)",
    "{0}. Altre possibilità: {1} ({2}%), {3} ({4}%)": "{0}. Other possibilities: {1} ({2}%), {3} ({4}%)",
    "«{0}»: nessun termine noto": "«{0}»: no known term",
    "«{0}» è un nome noto al programma per «{1}»": "«{0}» is a name known to the program for «{1}»",
    "i valori della colonna «{0}» («{1}», «{2}») indicano unità positive e negative":
        "the values of column «{0}» («{1}», «{2}») indicate positive and negative units",
    "{0}; punti senza numero di US: solo per la superficie di riferimento":
        "{0}; points without an SU number: only for the reference surface",
    "punti senza numero di US: solo per la superficie di riferimento": "points without an SU number: only for the reference surface",
    # nei motivi composti questa parte va presa prima di «US {0}», che si prenderebbe tutto il resto
    "US assegnata dalla posizione (solo dove un solo poligono contiene il punto); {0}":
        "SU assigned from the position (only where a single polygon contains the point); {0}",
    # errori
    "Vocabolario dell'utente illeggibile ({0}): {1}": "User vocabulary unreadable ({0}): {1}",
    "Espressione non valida per «{0}»: {1} ({2})": "Invalid expression for «{0}»: {1} ({2})",
    "Concetto sconosciuto: «{0}»": "Unknown concept: «{0}»",
    "Ambito sconosciuto: «{0}» (ammessi: {1})": "Unknown scope: «{0}» (allowed: {1})", "Ambito sconosciuto: «{0}»": "Unknown scope: «{0}»",
    "Manca il termine da insegnare": "The term to teach is missing",
    "Uso del layer sconosciuto: «{0}»": "Unknown layer use: «{0}»",
    "Colonna del programma sconosciuta: «{0}»": "Unknown program column: «{0}»",
    "Impossibile salvare il vocabolario: {0}": "Cannot save the vocabulary: {0}",
    "un layer da non usare": "a layer not to be used",
    # descrizioni dei concetti (vocabolario/*.json): campi della scheda
    "i margini (limiti) dell'unità: netti, rastremati, sfumati": "the edges (boundaries) of the unit: sharp, tapering, diffuse",
    "la definizione sintetica dell'unità": "the short definition of the unit",
    "la descrizione dell'unità": "the description of the unit", "l'interpretazione dell'unità": "the interpretation of the unit",
    "le note e osservazioni": "the notes and remarks", "il colore": "the colour",
    "il colore di visualizzazione (codice esadecimale)": "the display colour (hexadecimal code)",
    "il colore secondo le tavole Munsell": "the colour according to the Munsell charts",
    "la composizione (componenti e inclusi)": "the composition (components and inclusions)",
    "la consistenza (compattezza) del deposito": "the consistency (compaction) of the deposit",
    "una data": "a date", "la data di scavo o di schedatura": "the date of excavation or recording",
    "il responsabile della scheda (chi ha scavato o registrato)": "the person responsible for the record (who excavated or recorded it)",
    "la classe di materiale del reperto (ceramica, metallo, osso…)": "the material class of the find (pottery, metal, bone…)",
    "il tipo o la forma del reperto": "the type or form of the find",
    "il numero di frammenti o di oggetti (NR)": "the number of fragments or objects (NR)",
    "il numero minimo di individui (NMI)": "the minimum number of individuals (MNI)", "il peso": "the weight",
    "la cassetta (contenitore di magazzino)": "the box (storage container)",
    "le analisi previste per il campione": "the analyses planned for the sample",
    "il file (percorso dell'immagine o del documento)": "the file (path of the image or document)",
    "il soggetto (didascalia) della foto o del disegno": "the subject (caption) of the photo or drawing",
    "il titolo (nome) della fase": "the title (name) of the phase",
    # documenti
    "i materiali (inventario dei reperti)": "the materials (inventory of the finds)", "l'inventario dei materiali": "the materials inventory",
    "i reperti speciali (oggetti registrati singolarmente)": "the special finds (individually recorded objects)",
    "i punti dei reperti speciali": "the special find points", "l'elenco dei reperti speciali": "the list of special finds",
    "i campioni (prelievi per analisi)": "the samples (taken for analysis)", "il numero del campione": "the sample number",
    "l'elenco dei campioni": "the list of samples", "i punti di prelievo dei campioni": "the sampling points",
    "la documentazione (foto, disegni, registri)": "the documentation (photos, drawings, registers)",
    "l'elenco della documentazione (foto, disegni)": "the list of documentation (photos, drawings)",
    "le sezioni (linee di sezione)": "the sections (section lines)", "il nome della sezione": "the section name",
    "le linee di sezione": "the section lines",
    "i disegni delle sezioni (in coordinate di sezione)": "the section drawings (in section coordinates)",
    "la griglia (quadrettatura) di scavo": "the excavation grid (squares)",
    "un'ortofoto (immagine raddrizzata dello scavo)": "an orthophoto (rectified image of the excavation)",
    "un modello digitale del terreno": "a digital terrain model",
    "un modello 3D (fotogrammetria, nuvola di punti)": "a 3D model (photogrammetry, point cloud)",
    "una tabella tecnica del database GIS (non contiene dati di scavo)": "a technical table of the GIS database (holds no excavation data)",
    "un campo tecnico del CAD o del GIS (da ignorare)": "a technical CAD or GIS field (to be ignored)",
    # quote
    "le quote (altezze rilevate)": "the levels (surveyed heights)", "il valore di quota (altezza)": "the level value (height)",
    "i punti quotati": "the spot heights", "la tabella delle quote": "the table of levels", "le quote": "the levels",
    "il tipo di quota (superiore, inferiore, taglio…)": "the level type (top, bottom, cut…)",
    "la quota superiore (tetto dell'unità)": "the top level (top of the unit)",
    "la quota inferiore (base dell'unità)": "the bottom level (base of the unit)",
    "la quota del fondo di un taglio": "the level of the bottom of a cut",
    "la quota dell'orlo (margine superiore) di un taglio": "the level of the rim (top edge) of a cut",
    "la quota di rasatura (cresta) di un muro": "the top level (crest) of a wall",
    "la quota di fondazione (base) di un muro": "the foundation level (base) of a wall",
    "i profili 3D delle US (linee delle interfacce rilevate)": "the 3D profiles of the SUs (lines of the surveyed interfaces)",
    "le linee di fondo dei tagli (dove la parete diventa fondo)": "the base-of-slope lines of the cuts (where the side becomes the base)",
    "i tratteggi (hachures) delle pareti dei tagli": "the hachures of the sides of the cuts",
    "la coordinata est (X)": "the east coordinate (X)", "la coordinata nord (Y)": "the north coordinate (Y)",
    "lo spessore medio dell'unità": "the mean thickness of the unit",
    "lo spessore o la profondità massima (per i tagli: dalla superficie)": "the thickness or maximum depth (for cuts: from the surface)",
    # rapporti
    "i rapporti stratigrafici": "the stratigraphic relationships",
    "la tabella dei rapporti stratigrafici": "the table of stratigraphic relationships",
    "i rapporti scritti per esteso": "the relationships written out in full",
    "il rapporto «copre» (sta sopra, è posteriore)": "the relationship «covers» (lies above, is later)",
    "il rapporto «coperto da» (sta sotto, è anteriore)": "the relationship «covered by» (lies below, is earlier)",
    "il rapporto «taglia»": "the relationship «cuts»", "il rapporto «tagliato da»": "the relationship «cut by»",
    "il rapporto «riempie» (l'unità di cui è il riempimento)": "the relationship «fills» (the unit of which it is the fill)",
    "il rapporto «riempito da»": "the relationship «filled by»", "il rapporto «si appoggia a»": "the relationship «abuts»",
    "il rapporto «gli si appoggia»": "the relationship «abutted by»",
    "il rapporto «si lega a» (contemporaneo, legato in costruzione)": "the relationship «bonded with» (contemporary, bonded in construction)",
    "il rapporto «uguale a» (stessa unità con due numeri)": "the relationship «same as» (same unit with two numbers)",
    # unità, fasi, sito
    "l'unità stratigrafica (US)": "the stratigraphic unit (SU)", "il numero di US": "the SU number",
    "le schede delle US": "the SU records", "le piante (poligoni) delle US": "the SU plans (polygons)", "le US": "the SUs",
    "l'unità stratigrafica muraria (USM)": "the masonry stratigraphic unit (MSU)", "il numero di USM": "the MSU number",
    "le schede delle USM": "the MSU records", "le piante delle murature (USM)": "the plans of the walls (MSU)",
    "il tipo di unità (positiva o negativa)": "the unit type (positive or negative)",
    "un'unità positiva (strato, deposito, riempimento, muratura)": "a positive unit (layer, deposit, fill, masonry)",
    "un'unità negativa (taglio, interfaccia)": "a negative unit (cut, interface)",
    "la categoria dell'unità (definizione generale)": "the category of the unit (general definition)",
    "un'evidenza (feature: insieme di tagli e riempimenti, come una fossa o una buca di palo)":
        "a feature (a group of cuts and fills, such as a pit or a posthole)",
    "un intervento di scavo (slot, segmento o sondaggio dentro un'evidenza)":
        "an excavation intervention (slot, segment or sondage within a feature)",
    "un gruppo stratigrafico (insieme di US interpretate insieme)": "a stratigraphic group (SUs interpreted together)",
    "la fase di appartenenza": "the phase it belongs to", "la tabella delle fasi (periodizzazione)": "the table of phases (periodisation)",
    "la fase": "the phase", "il periodo (o epoca) di appartenenza": "the period (or era) it belongs to",
    "la datazione (cronologia)": "the dating (chronology)", "la tabella delle datazioni (usata come fasi)": "the table of datings (used as phases)",
    "l'anno iniziale della datazione": "the start year of the dating", "l'anno finale della datazione": "the end year of the dating",
    "il sito (scavo, località)": "the site (excavation, locality)",
    "l'area di scavo (saggio, trincea, settore)": "the excavation area (test pit, trench, sector)",
    "il perimetro dell'area di scavo (saggio, trincea)": "the outline of the excavation area (test pit, trench)",
    "il limite dello scavo": "the limit of excavation", "l'ambiente (vano) dell'edificio": "the room of the building",
    "un identificativo generico di riga (poco indicativo)": "a generic row identifier (not very telling)",
    "la geometria (forma) dell'elemento": "the geometry (shape) of the element",
})

# ---------------------------------------------------------------- importazione flessibile, insegna, chiusura automatica
T.update({
    "Numeri di US scritti con sigle o lettere in «{0}» (es. «{1}»): si usa il numero ({2})":
        "SU numbers written with prefixes or letters in «{0}» (e.g. «{1}»): the number is used ({2})",
    "{0} numeri di US scritti in modi diversi diventano una sola unità (es. «{1}» e «{2}»)":
        "{0} SU numbers written in different ways become a single unit (e.g. «{1}» and «{2}»)",
    "Il numero di US si ripete in «{0}» diversi: per importare un sito alla volta aggiungi un filtro su «{1}»":
        "The SU number repeats across different «{0}» values: to import one site at a time, add a filter on «{1}»",
    "{0} punti quotati di «{1}» usati solo per la superficie di riferimento":
        "{0} spot heights from «{1}» used only for the reference surface",
    "{0} punti quotati di «{1}» usati solo per la superficie di riferimento ({2} senza quota)":
        "{0} spot heights from «{1}» used only for the reference surface ({2} without a level)",
    "Il raster di correzione copre solo il {0} dell'area dello scavo: fuori si usano {1} quote rilevate, raccordate al suo bordo":
        "The correction raster covers only {0} of the excavation area: outside it, {1} surveyed levels are used, blended into its edge",
    "{0} + quote rilevate": "{0} + surveyed levels",
    "Il foglio «{0}» è stato riorganizzato durante l'importazione: le modifiche vanno riportate a mano nel file d'origine":
        "Sheet «{0}» was reorganised during import: the changes must be copied by hand into the source file",
    "La pagina di Stratigrafia 3D è stata chiusa: il programma termina.": "The Stratigrafia 3D page has been closed: the program is ending.",
    "Senza modifiche da salvare, il programma termina da solo qualche minuto dopo la chiusura della pagina.":
        "With no changes to save, the program ends by itself a few minutes after the page is closed.",
    "Collegamento con Stratigrafia 3D perso: il programma è stato chiuso o non risponde. Riavvialo per continuare.":
        "Connection to Stratigrafia 3D lost: the program has been closed or is not responding. Restart it to continue.",
    "Insegna": "Teach", "Insegna questo termine": "Teach this term",
    "Nei prossimi archivi «{0}» sarà letto come «{1}».": "In future archives «{0}» will be read as «{1}».",
    "Il termine si aggiunge al tuo vocabolario e la proposta viene rifatta: le altre scelte fatte a mano in questa procedura si perdono.":
        "The term is added to your vocabulary and the proposal is redone: the other choices made by hand in this procedure are lost.",
    "Aggiornamento della proposta…": "Updating the proposal…", "Imparato: «{0}» indica «{1}»": "Learnt: «{0}» means «{1}»",
    "nessuna: solo per la superficie": "none: only for the surface",
    "Ricorda che questo nome di layer indica l'uso scelto, anche nei prossimi archivi":
        "Remember that this layer name means the chosen use, in future archives too",
    "Ricorda che questo nome di colonna indica «{0}», anche nei prossimi archivi":
        "Remember that this column name means «{0}», in future archives too",
    "Preparazione delle unità… {0} di {1}": "Preparing the units… {0} of {1}",
    "Preparazione degli spigoli… {0} di {1}": "Preparing the edges… {0} of {1}",
})
# il nome della colonna tra «» non si traduce da solo: una voce per ciascuna colonna della scheda proposta nell'app
T.update({f"Ricorda che questo nome di colonna indica «{x}», anche nei prossimi archivi":
          f"Remember that this column name means «{T[x]}», in future archives too"
          for x in ("Numero di US", "Positiva / negativa", "Categoria", "Definizione", "Descrizione", "Interpretazione",
                    "Spessore", "Profondità (tagli)", "Margini (netti / rastremati)", "Fase", "Data di scavo",
                    "Datazione da (anno)", "Datazione a (anno)", "Colore (#rrggbb)")})
T.update({
    "Rapporti dalle colonne della scheda US ({0})": "Relationships from the columns of the SU record ({0})",
    "Nessun rapporto stratigrafico trovato: le basi non saranno agganciate": "No stratigraphic relationships found: the bases will not be snapped",
    "Fase composta: colonne «{0}» e «{1}» non trovate nelle schede": "Composite phase: columns «{0}» and «{1}» not found in the records",
})

# ---------------------------------------------------------------- cartelle e inventario
# destinazioni proposte dall'inventario (inventario.DESTINAZIONE e quelle scritte a mano)
_DESTINAZIONI = {
    "Piante delle US": "SU plans", "Piante delle USM": "MSU plans", "Quote": "Levels", "Profili 3D": "3D profiles",
    "Linee di fondo": "Base-of-slope lines", "Limite di scavo": "Excavation limit",
    "Tracce delle sezioni": "Section lines", "Disegni delle sezioni": "Section drawings", "Reperti": "Finds",
    "Campioni": "Samples", "Schede US": "SU records", "Schede USM": "MSU records",
    "Rapporti stratigrafici": "Stratigraphic relationships", "Materiali": "Materials",
    "Documentazione (elenco)": "Documentation (list)", "Fasi": "Phases", "Gruppi stratigrafici": "Stratigraphic groups",
    "Datazioni": "Dates", "Superficie di riferimento": "Reference surface",
    "Correzione della superficie": "Surface correction", "Ortofoto": "Orthophoto",
    "Documentazione (foto)": "Documentation (photos)", "Documentazione (disegni)": "Documentation (drawings)",
    "Documentazione (scansioni)": "Documentation (scans)", "Documenti (relazione)": "Documents (report)",
    "Documenti (elenco)": "Documents (list)", "Documenti (metadati)": "Documents (metadata)", "Licenza": "Licence",
    "Dizionario dei dati": "Data dictionary", "Non usato": "Not used", "Modelli 3D": "3D models",
    "Documenti": "Documents", "Aperto: contenuto elencato": "Opened: contents listed",
    "Da esportare in CSV": "To be exported to CSV", "Piante e quote (da verificare)": "Plans and levels (to be checked)",
}
T.update(_DESTINAZIONI)
# un file con più layer o fogli ha più destinazioni, separate da virgole: «Piante delle US, Quote»
T.update({k + ", {0}": v + ", {0}" for k, v in _DESTINAZIONI.items()})
# «il nome «LEGGIMI» indica: documenti (metadati)»: la destinazione in minuscolo
T.update({k.lower(): v[0].lower() + v[1:] for k, v in _DESTINAZIONI.items() if k.startswith(("Documenti (", "Licenza", "Dizionario"))})
# tipo d'immagine dopo il motivo del collegamento: «… — foto: dati EXIF…»
_TIPI_IMMAGINE = {"foto": "photo", "disegno": "drawing", "scansione": "scan"}
# il gruppo dell'inventario prende il nome dalla destinazione (o dalla categoria): tra «» non si traduce da solo
T.update({f"Usa tutti i file di «{k}»": f"Use all the files of «{v}»" for k, v in list(_DESTINAZIONI.items()) + [
    ("tabella", "table"), ("modello 3D", "3D model"), ("archivio", "archive"), ("documento", "document"),
    ("immagine", "image"), ("altro", "other"), ("ignorato", "ignored")]})
T.update({"{0} — " + k + ": {1}": "{0} — " + v + ": {1}" for k, v in _TIPI_IMMAGINE.items()})
T.update({f"incerto tra {a} e {b}": f"uncertain between {_TIPI_IMMAGINE[a]} and {_TIPI_IMMAGINE[b]}"
          for a in _TIPI_IMMAGINE for b in _TIPI_IMMAGINE if a != b})
T.update({
    # ---- passo 1 dell'app: cartelle e inventario
    "Aggiungi cartella…": "Add folder…", "Aggiungi cartella": "Add folder",
    "Una cartella di scavo intera: il programma guarda ogni file e propone a cosa serve":
        "A whole excavation folder: the program looks at every file and suggests what it is for",
    "…oppure incolla qui il percorso di un file o di una cartella e premi Invio":
        "…or paste the path of a file or folder here and press Enter",
    "Contenuto delle cartelle": "Contents of the folders",
    "Filtra per nome…": "Filter by name…", "Filtra i file dell'inventario": "Filter the files of the inventory",
    "Guarda di nuovo le cartelle, se nel frattempo sono cambiate": "Look at the folders again, in case they have changed in the meantime",
    "Rileggi le cartelle": "Read the folders again",
    "Il programma ha guardato ogni file e propone a cosa serve. Togli la spunta ai file da non usare; per piante, tabelle, raster e immagini puoi cambiare la destinazione.":
        "The program has looked at every file and suggests what it is for. Untick the files not to be used; for plans, tables, rasters and images you can change the destination.",
    "Percorso della cartella": "Folder path", "Scrivi il percorso completo della cartella.": "Type the full path of the folder.",
    "cartella": "folder", "{0} file": "{0} files", "file": "files",
    "{0} file, {1} da usare": "{0} files, {1} to use", "{0} da usare": "{0} to use",
    "piante GIS": "GIS plans", "tabelle": "tables", "modelli 3D": "3D models", "archivi": "archives",
    "documenti": "documents", "foto": "photos", "altri file": "other files", "ignorati": "ignored",
    "tabella": "table", "modello 3D": "3D model", "archivio": "archive", "documento": "document",
    "immagine": "image", "altro": "other", "ignorato": "ignored",
    "Inventario delle cartelle…": "Inventory of the folders…",
    "L'inventario delle cartelle non è disponibile: si leggeranno tutti i file di dati che contengono":
        "The folder inventory is not available: all the data files they contain will be read",
    "Destinazione": "Destination", "Usa": "Use", "Usa {0}": "Use {0}", "Usa tutti i file di «{0}»": "Use all the files of «{0}»",
    "Affidabilità della proposta: {0}%": "Reliability of the proposal: {0}%",
    "Mostra solo questa categoria": "Show only this category", "nascondi": "hide", "mostra": "show",
    "Mostra altri {0}": "Show {0} more", "{0} non mostrati": "{0} not shown",
    "Nessun file corrisponde al filtro.": "No file matches the filter.",
    "Qui non si legge il percorso dei file trascinati: usa «Aggiungi file…» o «Aggiungi cartella…», oppure incolla il percorso":
        "The path of dragged files cannot be read here: use «Add files…» or «Add folder…», or paste the path",
    "Nessun file di dati scelto: spunta almeno una pianta, una tabella o un raster nell'inventario":
        "No data file chosen: tick at least one plan, table or raster in the inventory",
    "scelto a mano nell'inventario": "chosen by hand in the inventory", "trovato nell'inventario": "found in the inventory",
    # ---- importazione da cartelle (importa.py)
    "«{0}» non è un archivio zip valido (download incompleto?): {1}": "«{0}» is not a valid zip archive (incomplete download?): {1}",
    "estensione del file": "file extension",
    "Inventario di {0}: {1} file, {2} proposti per l'importazione": "Inventory of {0}: {1} files, {2} proposed for import",
    "In {0} nessun file di dati riconosciuto": "No data file recognised in {0}",
    "«{0}»: l'inventario lo indica come modello di troncamento": "«{0}»: the inventory marks it as a truncation model",
    "Modello 3D «{0}»: escluso dall'inventario (si può includere nel riquadro dei modelli 3D)":
        "3D model «{0}»: left out in the inventory (it can be included in the 3D models box)",
    "Documentazione: {0} immagini dell'inventario non sono sul disco (non estratte dall'archivio o spostate): non collegate":
        "Documentation: {0} images of the inventory are not on disk (not extracted from the archive, or moved): not linked",
    "Documentazione: {0} file citati ritrovati nelle cartelle esaminate": "Documentation: {0} listed files found in the folders examined",
    "Registro «{0}» non usato per la documentazione: {1}": "Register «{0}» not used for the documentation: {1}",
    "Documentazione dai file: {0} file collegati a {1} unità": "Documentation from the files: {0} files linked to {1} units",
    "Documentazione dai file: {0} file collegati a {1} unità ({2} immagine non collegata a nessuna unità)":
        "Documentation from the files: {0} files linked to {1} units ({2} image not linked to any unit)",
    "Documentazione dai file: {0} file collegati a {1} unità ({2} immagini non collegate a nessuna unità)":
        "Documentation from the files: {0} files linked to {1} units ({2} images not linked to any unit)",
    "Documentazione dai file: nessuna delle {0} immagini trovate è collegata a un'unità del progetto":
        "Documentation from the files: none of the {0} images found is linked to a unit of the project",
    "Documentazione dai file non creata: {0}": "Documentation from the files not created: {0}",
    "numero dell'unità nel nome del file ({0})": "unit number in the file name ({0})",
    "File dell'inventario non letti: {0}": "Inventory files not read: {0}",
    "{0} layer della ricetta trovati nell'inventario delle cartelle: {1}": "{0} recipe layers found in the folder inventory: {1}",
    "{0} tabelle della ricetta trovate nell'inventario delle cartelle: {1}": "{0} recipe tables found in the folder inventory: {1}",
    "Modello del terreno «{0}» trovato nell'inventario delle cartelle": "Terrain model «{0}» found in the folder inventory",
    "Foto": "Photo", "Disegno": "Drawing", "Scansione": "Scan", "automatico": "automatic", "Collegamento": "Link",
    # scelte fatte a mano nell'inventario
    "escluso nell'inventario": "left out in the inventory", "«{0}»: escluso nell'inventario": "«{0}»: left out in the inventory",
    "«{0}»: aggiunto a mano nell'inventario": "«{0}»: added by hand in the inventory",
    "«{0}»: {1} (scelto a mano nell'inventario)": "«{0}»: {1} (chosen by hand in the inventory)",
    "«{0}»: correzione della superficie senza un modello del terreno: non usata":
        "«{0}»: surface correction without a terrain model: not used",
    "«{0}»: nessuna colonna con i numeri delle unità: non usato come «{1}»": "«{0}»: no column with the unit numbers: not used as «{1}»",
    "«{0}»: nessuna colonna con i numeri delle unità: non usato come «Schede US»":
        "«{0}»: no column with the unit numbers: not used as «SU records»",
    "«{0}»: nessuna colonna con i numeri delle unità: non usato come «Schede USM»":
        "«{0}»: no column with the unit numbers: not used as «MSU records»",
    "«{0}»: rapporti non riconosciuti (servono le colonne unità, rapporto, unità correlata)":
        "«{0}»: relationships not recognised (the columns unit, relationship, related unit are needed)",
    "«{0}» ha {1} layer: il ruolo si sceglie layer per layer": "«{0}» has {1} layers: the role is chosen layer by layer",
    "Documentazione: {0} file esclusi nell'inventario non collegati": "Documentation: {0} files left out in the inventory not linked",
    "Documentazione: {0} file estratti dagli archivi": "Documentation: {0} files extracted from the archives",
    "disegno": "drawing", "scansione": "scan",
    # ---- inventario.py: note
    "Cartella «{0}» oltre la profondità massima ({1}): non esaminata": "Folder «{0}» beyond the maximum depth ({1}): not examined",
    "«{0}»: {1} immagini ({2} MB) elencate senza estrarle tutte (estratte {3} per riconoscerle)":
        "«{0}»: {1} images ({2} MB) listed without extracting them all ({3} extracted to recognise them)",
    "«{0}»: impossibile estrarre «{1}» ({2})": "«{0}»: cannot extract «{1}» ({2})",
    "«{0}»: troppi archivi uno dentro l'altro, non aperto": "«{0}»: too many archives nested in one another, not opened",
    "Alcuni file hanno lo stesso nome ma contenuto diverso: {0}. Forse la cartella contiene più scavi: controlla quali usare":
        "Some files have the same name but different contents: {0}. Perhaps the folder holds several excavations: check which ones to use",
    "«{0}» ({1} versioni)": "«{0}» ({1} versions)", "«{0}» ({1} versioni), {2}": "«{0}» ({1} versions), {2}",
    "«{0}» non esiste": "«{0}» does not exist",
    "Trovati più di {0} file: esaminati solo i primi {1}": "More than {0} files found: only the first {1} examined",
    "Esaminati {0} file ({1} voci, {2} file accessori uniti al file principale) in {3} cartelle e {4} archivi zip in {5} s":
        "{0} files examined ({1} entries, {2} sidecar files joined to their main file) in {3} folders and {4} zip archives in {5} s",
    "Nessun file di dati da importare (piante, schede, raster o modelli 3D)": "No data files to import (plans, records, rasters or 3D models)",
    # ---- inventario.py: motivo di ogni voce
    "cartella di sistema": "system folder", "cartella di sistema ({0} file)": "system folder ({0} files)",
    "file di sistema o temporaneo": "system or temporary file",
    "archivio zip: il contenuto è elencato qui sotto": "zip archive: its contents are listed below",
    "archivio zip illeggibile (download incompleto?)": "unreadable zip archive (incomplete download?)",
    "file non leggibile ({0}: {1})": "unreadable file ({0}: {1})",
    "nell'archivio, non estratto": "in the archive, not extracted", "nell'archivio, non estratta": "in the archive, not extracted",
    "{0} (nell'archivio, non estratta)": "{0} (in the archive, not extracted)",
    "shapefile incompleto: mancano .dbf e .shx": "incomplete shapefile: .dbf and .shx are missing",
    "file JSON senza geometrie": "JSON file without geometries",
    "KMZ: aprilo in QGIS ed esporta in GeoPackage": "KMZ: open it in QGIS and export to GeoPackage",
    "disegno DWG: esportalo in DXF per importarlo": "DWG drawing: export it to DXF to import it",
    "raster in formato {0}: esportalo in GeoTIFF per usarlo": "raster in {0} format: export it to GeoTIFF to use it",
    "modello 3D con materiale (.mtl)": "3D model with material (.mtl)", "modello 3D e {0} texture": "3D model and {0} textures",
    "modello 3D con materiale (.mtl) e {0} texture": "3D model with material (.mtl) and {0} textures",
    "modello 3D e 1 texture": "3D model and 1 texture",
    "modello 3D con materiale (.mtl) e 1 texture": "3D model with material (.mtl) and 1 texture",
    "ricetta «{0}»": "recipe «{0}»",
    "modello 3D in formato {0}: esportalo in OBJ o PLY per mostrarlo nel progetto":
        "3D model in {0} format: export it to OBJ or PLY to show it in the project",
    "database Access: esporta le tabelle in CSV (in Access: Dati esterni → Esporta → File di testo) e aggiungi i CSV":
        "Access database: export the tables to CSV (in Access: External Data → Export → Text File) and add the CSV files",
    "archivio {0}: estrailo per esaminarne il contenuto": "{0} archive: extract it to examine its contents",
    "file XML (metadati)": "XML file (metadata)",
    "schema.ini: descrive le colonne dei file di testo": "schema.ini: describes the columns of the text files",
    "progetto GIS: si importano i layer, non il progetto": "GIS project: the layers are imported, not the project",
    "file accessorio senza il file principale": "sidecar file without its main file",
    "formato non riconosciuto ({0})": "format not recognised ({0})", "senza estensione": "no extension",
    "curve di livello: la superficie si ricava dal modello del terreno": "contour lines: the surface is derived from the terrain model",
    "il nome contiene «{0}»": "the name contains «{0}»",
    "layer di servizio (griglia, tratteggi…)": "service layer (grid, hatching…)",
    "{0}: layer di servizio (griglia, tratteggi…)": "{0}: service layer (grid, hatching…)",
    "poligoni senza un nome riconoscibile: forse piante di US": "polygons without a recognisable name: perhaps SU plans",
    "punti con quota": "points with levels", "punti con quota (campo «{0}»)": "points with levels (field «{0}»)",
    "punti con quota (3D)": "points with levels (3D)",
    "linee 2D: forse tracce di sezione": "2D lines: perhaps section lines",
    "geometrie miste": "mixed geometries",
    "{0} elementi, {1}": "{0} features, {1}", "{0} ({1} elementi, {2})": "{0} ({1} features, {2})",
    "{0} ({1} entità)": "{0} ({1} entities)", "{0} ({1} righe)": "{0} ({1} rows)",
    "«{0}» è {1}": "«{0}» is {1}", "«{0}» contiene «{1}», {2}": "«{0}» contains «{1}», {2}",
    "«{0}» è parte di «{1}», {2}": "«{0}» is part of «{1}», {2}", "«{0}» somiglia a «{1}», {2}": "«{0}» resembles «{1}», {2}",
    "«{0}» ha la forma di una sigla": "«{0}» has the form of a code",
    "poligono": "polygon", "linea": "line", "punto": "point", "testo": "text",
    "poligono 3D": "3D polygon", "linea 3D": "3D line", "punto 3D": "3D point", "misto 3D": "mixed 3D",
    "{0}, senza .prj (sistema di riferimento ignoto)": "{0}, without .prj (unknown coordinate reference system)",
    "layer vuoto": "empty layer", "layer vuoto ({0})": "empty layer ({0})", "layer illeggibile ({0})": "unreadable layer ({0})",
    "non è un database SQLite": "not an SQLite database", "nessun layer né tabella": "no layers or tables",
    "nessuno riconosciuto": "none recognised",
    "{0} layer: {1}": "{0} layers: {1}", "1 layer: {0}": "1 layer: {0}",
    "{0} tabelle: {1}": "{0} tables: {1}", "1 tabella: {0}": "1 table: {0}",
    "{0} fogli: {1}": "{0} sheets: {1}", "1 foglio: {0}": "1 sheet: {0}",
    "{0} layer e {1} tabelle: {2}": "{0} layers and {1} tables: {2}", "{0} layer e 1 tabella: {1}": "{0} layers and 1 table: {1}",
    "1 layer e {0} tabelle: {1}": "1 layer and {0} tables: {1}", "1 layer e 1 tabella: {0}": "1 layer and 1 table: {0}",
    "disegno CAD molto grande: i layer si esaminano all'importazione": "very large CAD drawing: the layers are examined on import",
    "colonne con le unità e il tipo di rapporto («{0}»)": "columns with the units and the type of relationship («{0}»)",
    "la colonna «{0}» non contiene nomi di rapporti": "column «{0}» holds no relationship names",
    "una riga per unità (colonna «{0}»)": "one row per unit (column «{0}»)",
    "una riga per unità (colonna «{0}») e {1} colonne di rapporti": "one row per unit (column «{0}») and {1} relationship columns",
    "una riga per USM (colonna «{0}»)": "one row per MSU (column «{0}»)",
    "colonne di classe, quantità o peso dei reperti": "columns of class, quantity or weight of the finds",
    "colonne dei campioni": "sample columns",
    "colonne di file o soggetto (foto, disegni)": "file or subject columns (photos, drawings)",
    "colonne di fase o periodo con le date": "phase or period columns with dates",
    "colonna dei gruppi stratigrafici": "stratigraphic group column",
    "tabella non riconosciuta (nome e colonne)": "table not recognised (name and columns)", "tabella vuota": "empty table",
    "descrive tabelle, campi o file (dizionario dei dati)": "describes tables, fields or files (data dictionary)",
    "geometrie in testo (WKT, colonna «{0}»)": "geometries as text (WKT, column «{0}»)",
    "coordinate nelle colonne «{0}», «{1}»": "coordinates in columns «{0}», «{1}»",
    "coordinate nelle colonne «{0}», «{1}», «{2}»": "coordinates in columns «{0}», «{1}», «{2}»",
    "tabella dBase senza shapefile: per usarla salvala in CSV o Excel": "dBase table without a shapefile: to use it, save it as CSV or Excel",
    "cartella di lavoro vuota": "empty workbook",
    "TIFF senza georiferimento: {0}": "TIFF without georeferencing: {0}",
    "immagine georiferita a colori ({0} bande, passo {1} m): da drappeggiare sul modello":
        "georeferenced colour image ({0} bands, cell size {1} m): to be draped on the model",
    "raster a una banda ({0}) molto grande: considerato un modello del terreno (valori non controllati)":
        "very large single-band raster ({0}): taken as a terrain model (values not checked)",
    "raster senza valori": "raster without values",
    "valori tutti tra {0} e {1}: differenze di quota (troncamento) da sommare al modello del terreno":
        "all values between {0} and {1}: level differences (truncation) to be added to the terrain model",
    "una banda a 8 bit: forse un'immagine in scala di grigi più che un modello del terreno":
        "one 8-bit band: perhaps a greyscale image rather than a terrain model",
    "modello del terreno: quote da {0} a {1}": "terrain model: levels from {0} to {1}",
    "il nome «{0}» indica un disegno": "the name «{0}» suggests a drawing",
    "il nome «{0}» indica una scansione": "the name «{0}» suggests a scan",
    "il nome «{0}» indica: {1}": "the name «{0}» suggests: {1}",
    "fotografia (dal formato e dal nome)": "photograph (from the format and the name)",
    "riconosciuta solo dal formato": "recognised from the format only",
    "documento di testo: forse la relazione o una pubblicazione": "text document: perhaps the report or a publication",
    "file di testo: note sull'archivio": "text file: notes on the archive",
    "copia di «{0}» (si usa quella); {1}": "copy of «{0}» (that one is used); {1}",
    "stessi dati in un altro formato di «{0}» (si usa quella); {1}": "same data, in another format, as «{0}» (that one is used); {1}",
    "layer di una figura della pubblicazione (nome «{0}»): non proposto; {1}":
        "layer of a figure of the publication (name «{0}»): not proposed; {1}",
    "layer di una figura della pubblicazione (cartella «{0}»): non proposto; {1}":
        "layer of a figure of the publication (folder «{0}»): not proposed; {1}",
    "ruolo solo ipotizzato e nello stesso insieme c'è «{0}» ({1}): non proposto; {2}":
        "role only guessed, and the same dataset has «{0}» ({1}): not proposed; {2}",
    "come le altre immagini della cartella ({0})": "like the other images in the folder ({0})",
    # ---- documenti_auto.py: tipo d'immagine e collegamento alle unità
    "«{0}» nel nome del file": "«{0}» in the file name", "«{0}» nel nome della cartella": "«{0}» in the folder name",
    "{0} nel nome del file": "{0} in the file name", "{0} nel nome della cartella": "{0} in the folder name",
    "{0} nel nome del file (numero senza sigla, unità del progetto)": "{0} in the file name (number without a prefix, unit of the project)",
    "{0} nel nome della cartella (numero senza sigla, unità del progetto)": "{0} in the folder name (number without a prefix, unit of the project)",
    "dati EXIF di uno scanner ({0})": "EXIF data of a scanner ({0})", "dati EXIF di scatto ({0})": "EXIF shooting data ({0})",
    "dati EXIF di scatto (tempo, diaframma)": "EXIF shooting data (exposure time, aperture)",
    "dati EXIF della fotocamera ({0})": "EXIF data of the camera ({0})",
    "file PDF": "PDF file", "immagine enorme in bianco e nero o grigi": "huge image in black and white or greys",
    "immagine enorme": "huge image", "immagine non leggibile": "unreadable image",
    "nessun indizio chiaro: deciso dal formato del file": "no clear clue: decided from the file format",
    "foglio chiaro color carta con segni scuri": "light paper-coloured sheet with dark marks",
    "foglio chiaro color carta con segni scuri, grande o in TIFF": "light paper-coloured sheet with dark marks, large or in TIFF",
    "linee scure su fondo chiaro": "dark lines on a light background",
    "linee scure su fondo chiaro (formato da scansione)": "dark lines on a light background (scan format)",
    "linee sottili su fondo bianco, poche tinte": "thin lines on a white background, few hues",
    "immagine in toni di grigio": "greyscale image", "disegno a colori su fondo chiaro": "colour drawing on a light background",
    "immagine a colori con molte tinte": "colour image with many hues",
    "intervallo {0}-{1} non espanso (non tutte le unità sono note)": "range {0}-{1} not expanded (not all the units are known)",
    "{0} potrebbe essere un anno": "{0} could be a year", "ambiguo: nel percorso anche {0}": "ambiguous: the path also has {0}",
    "unità non presente nel progetto": "unit not in the project", "non espanso": "not expanded",
    "Immagini collegate alle unità dai nomi: {0} su {1}, per {2} unità": "Images linked to the units by their names: {0} of {1}, for {2} units",
    "{0} file collegati dal nome della cartella": "{0} files linked by the folder name",
    "{0} PDF collegati alle unità dal nome": "{0} PDFs linked to the units by name",
    "{0} collegamenti incerti (il motivo spiega perché)": "{0} uncertain links (the reason explains why)",
    "{0} numeri con sigla non sono unità del progetto (es. {1})": "{0} numbers with a prefix are not units of the project (e.g. {1})",
    "{0} file con numeri di unità scartati perché sembrano date, scale o numeri di foto":
        "{0} files with unit numbers discarded because they look like dates, scales or photo numbers",
    "Senza l'elenco delle unità si collegano solo i nomi con una sigla (US, SU, Context…)":
        "Without the list of units only the names with a prefix (US, SU, Context…) are linked",
    "Il registro è vuoto": "The register is empty",
    "Nel registro non c'è una colonna con le unità (US, Context…)": "The register has no column with the units (US, Context…)",
    "Nel registro non c'è una colonna con il nome del file o il numero della foto":
        "The register has no column with the file name or the photo number",
    "Registro: {0}": "Register: {0}",
    "file «{0}»": "file «{0}»", "numero «{0}»": "number «{0}»", "unità «{0}»": "unit «{0}»", "descrizione «{0}»": "description «{0}»",
    "file «{0}», {1}": "file «{0}», {1}", "numero «{0}», {1}": "number «{0}», {1}", "unità «{0}», {1}": "unit «{0}», {1}",
    "«{0}» citato nel registro": "«{0}» listed in the register",
    "«{0}» citato nel registro (con un'altra estensione)": "«{0}» listed in the register (with another extension)",
    "numero {0} del registro nel nome del file": "number {0} of the register in the file name",
    "numero {0} del registro nel nome del file (numero iniziale del nome)":
        "number {0} of the register in the file name (number at the start of the name)",
    "Immagini collegate con il registro: {0} su {1} ({2} per nome del file, {3} per numero), per {4} unità":
        "Images linked through the register: {0} of {1} ({2} by file name, {3} by number), for {4} units",
    "{0} righe del registro senza unità: unità prese dalla descrizione": "{0} register rows without units: units taken from the description",
    "{0} voci del registro senza un file corrispondente": "{0} register entries without a matching file",
})


def _numerati(*pezzi):
    """Unisce pezzi di modello con i segnaposto «{}» numerandoli di seguito: ("{}; x «{}»", " ({} y)")."""
    parti = "".join(pezzi).split("{}")
    return "".join(q + ("{%d}" % i if i < len(parti) - 1 else "") for i, q in enumerate(parti))


# Il motivo di un layer finisce con «(12 elementi, poligono)», «(12 entità)» o «(12 righe)»: dove prima c'è
# un testo che può contenere parentesi (le descrizioni del vocabolario) servono modelli con più testo fisso,
# che separino la fine nel punto giusto.
_CODE = ((" ({} elementi, {})", " ({} features, {})"), (" ({} entità)", " ({} entities)"), (" ({} righe)", " ({} rows)"))
_TESTE = (("{}; numero di US dal campo «{}»", "{}; SU number from field «{}»"),
          ("{}; la geometria lo conferma", "{}; the geometry confirms it"),
          ("{}; il contesto («{}») lo conferma", "{}; the context («{}») confirms it"),
          ("{}: layer di servizio (griglia, tratteggi…)", "{}: service layer (grid, hatching…)"),
          ("{} (indizio debole)", "{} (weak clue)"),
          ("punti con quota (campo «{}»)", "points with levels (field «{}»)"),
          ("punti con quota (3D)", "points with levels (3D)"),
          ("layer di servizio (griglia, tratteggi…)", "service layer (grid, hatching…)"),
          ("testi (usabili come etichette)", "texts (usable as labels)"),
          ("geometrie in testo (WKT, colonna «{}»)", "geometries as text (WKT, column «{}»)"))
_DESCRIZIONI = ("la griglia (quadrettatura) di scavo", "le piante (poligoni) delle US",
                "le linee di fondo dei tagli (dove la parete diventa fondo)",
                "un intervento di scavo (slot, segmento o sondaggio dentro un'evidenza)",
                "i tratteggi (hachures) delle pareti dei tagli", "il sito (scavo, località)",
                "un'ortofoto (immagine raddrizzata dello scavo)", "i profili 3D delle US (linee delle interfacce rilevate)",
                "un'evidenza (feature: insieme di tagli e riempimenti, come una fossa o una buca di palo)",
                "le piante delle murature (USM)", "i disegni delle sezioni (in coordinate di sezione)",
                "il perimetro dell'area di scavo (saggio, trincea)",
                "una tabella tecnica del database GIS (non contiene dati di scavo)")
for _ci, _ce in _CODE:
    T.update({_numerati(a, _ci): _numerati(b, _ce) for a, b in _TESTE})
    T.update({_numerati("{} per " + d, _ci): _numerati("{} for " + T[d], _ce) for d in _DESCRIZIONI})
    T.update({_numerati("{} per " + d + " (indizio debole)", _ci): _numerati("{} for " + T[d] + " (weak clue)", _ce)
              for d in _DESCRIZIONI})

if __name__ == "__main__":
    qui = os.path.dirname(os.path.abspath(__file__))
    dest = os.path.join(qui, "..", "src", "stratigrafia3d", "lingue", "en.json")
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(T.items())), f, ensure_ascii=False, indent=1)
    print(f"{len(T)} testi in {os.path.normpath(dest)}")
