# Anleitung für Claude: Rohdaten laden und Staat-Jahr-Panel in R bauen

**Auftrag.** Lade alle Rohdaten für die Bachelorarbeit „Senken höhere Zigarettensteuern die Raucherquote in den
US-Bundesstaaten?“ herunter und speichere sie unverändert in einem Ordner. Bau daraus zwei Datensätze für die
Auswertung in R:

1. einen **Personendatensatz** mit den BRFSS-Originalvariablen 2001–2015,
2. den **fertigen Datensatz**: ein Panel aus 50 Staaten und Washington, D.C. für 2001–2015 (765 Zeilen).

Schreib die gesamte Aufbereitung als **R-Skripte**. Ein Ergebnis ist ausdrücklich das Transformationsskript
`R/02_transform.R`: Es wandelt die Rohdateien ohne weitere Handgriffe in den fertigen Datensatz um, damit jeder
mit denselben Rohdaten genau denselben Datensatz erzeugen kann. Schätze **keine** Modelle; es geht nur um die
Daten.

**Grundregeln**

- **Originalnamen bleiben.** Jede Variable, die direkt aus einer Quelle stammt, behält ihren Namen exakt wie in
  der Quelle, einschließlich Unterstrich und Großschreibung (`_STATE`, `_SMOKER3`, `_LLCPWT`, `INCOME2`,
  `LocationAbbr`, `Data_Value` …). Auch die Codes bleiben unverändert. Nur neu berechnete Variablen (Anteile,
  reale Werte, Indikatoren) bekommen neue Namen. Das Codebook nennt für jede neue Variable die Quellvariable(n).
- **Keine automatische Namensbereinigung.** Nicht `read.csv()` ohne `check.names = FALSE` verwenden (macht aus
  `_STATE` ein `X_STATE`), kein `make.names()`, kein `janitor::clean_names()`. Nicht-syntaktische Namen in R
  mit Backticks ansprechen: `` df$`_STATE` ``.
- **Rohdateien nie verändern.** Jede Umwandlung schreibt in neue Dateien.
- **Nichts erfinden.** Scheitert eine Quelle, bleiben die betroffenen Spalten `NA`. Die Lücke kommt ins Protokoll,
  sie wird nicht mit Schätzwerten gefüllt.
- Jede Annahme, die nicht in dieser Anleitung steht, gehört in `data/logs/checks.md`. Am Ende berichtest du
  kurz, was geklappt hat, was nicht und wo du abgewichen bist.

---

## 0 Voraussetzungen

| Was | Details |
|---|---|
| Netzzugang | `www.cdc.gov`, `data.cdc.gov`, `fred.stlouisfed.org`; optional `catalog.data.gov`, `www.datalumos.org`, `journals.plos.org`, `doi.org` |
| R | ab 4.1, Pakete: `install.packages(c("haven", "dplyr", "tidyr", "readr", "purrr", "stringr", "curl", "digest"))` |
| Speicher | etwa 1,5 GB für die BRFSS-ZIPs; entpackte XPT-Dateien sind deutlich größer. Immer nur **ein** Jahr entpacken, einlesen, XPT wieder löschen. |

Im Repository `lorenzobalconi/claude` (Branch `claude/bold-faraday-s99cxd`, Ordner `replication/`) gibt es eine
getestete Python-Fassung derselben Aufbereitung (`frm_panel/data.py`). Sie dient nur als Referenz für die Logik;
ihre Spaltennamen weichen ab. Für diesen Auftrag gelten R und die Namen in dieser Anleitung.

## 1 Ordnerstruktur und Skripte

```
R/
├── 01_download.R             # Schritt 2: lädt die Rohdaten
├── 02_transform.R            # Schritte 3–5 und 7: Rohdaten → fertiger Datensatz, Protokolle, Codebook
└── 03_checks.R               # Schritt 6: Prüfungen
data/
├── raw/                                     # unverändert, so wie heruntergeladen
│   ├── brfss_2001.zip … brfss_2015.zip
│   ├── tax_burden.csv                       # The Tax Burden on Tobacco, 1970–2019
│   ├── state_tax_legislation.csv            # optional: Steuersätze mit Wirksamkeitsdatum
│   ├── smokefree.csv                        # Rauchverbote (STATE System)
│   ├── fred/                                # <ST>UR.csv, <ST>PCPI.csv, CPIAUCSL.csv
│   └── paper/                               # optional: Zusatztabellen S2/S3 des Papers
├── intermediate/
│   └── brfss_<Jahr>.rds                     # Originalvariablen eines Jahres
├── final/
│   ├── brfss_2001_2015_personen.rds         # Personendatensatz mit Originalnamen und -codes
│   ├── panel_state_year_2001_2015.rds       # ← FERTIGER DATENSATZ (für R)
│   ├── panel_state_year_2001_2015.csv       # derselbe Datensatz als CSV
│   └── codebook.md                          # Variablenverzeichnis, Transformationsprotokoll, Quellen
└── logs/
    ├── download_log.csv                     # URL, Datei, Bytes, SHA-256, Zeitpunkt, Status
    ├── transform_log.csv                    # Fallzahlen je Jahr und Transformationsschritt
    ├── code_frequencies.csv                 # gefundene Codes je Quellvariable und Jahr
    ├── join_log.csv                         # Treffer je Zusammenführung
    └── checks.md                            # Ergebnisse der Prüfungen aus Schritt 6
```

Jedes Skript lässt sich aus dem Projektordner mit `Rscript R/0x_….R` einzeln ausführen und liest nur Dateien
aus früheren Schritten.

**Anforderungen an `R/02_transform.R`**

- **Eigenständig:** liest nur `data/raw/`, schreibt nur nach `data/intermediate/`, `data/final/` und `data/logs/`,
  braucht keinen Netzzugang. Liegen die Rohdaten vor, genügt `Rscript R/02_transform.R`.
- **Kopfkommentar:** Zweck, Eingabedateien, Ausgabedateien, benötigte Pakete, ungefähre Laufzeit und
  Arbeitsspeicher.
- **Einstellungen oben im Skript:** Pfade, Jahre (2001–2015), Liste der FIPS-Codes, Zuordnung FIPS → Postkürzel.
- **Eine Funktion je Schritt**, jeweils mit einem Kommentar, welchen Abschnitt dieser Anleitung sie umsetzt, z. B.
  `read_brfss_year()` (3), `build_cells()` (4.1), `read_tax()` (4.2), `read_fred()` (4.3), `read_smokefree()`
  (4.4), `add_real_values()` (4.5), `merge_panel()` (5), `write_codebook()` (7). Unten im Skript ruft ein kurzer
  Hauptteil die Funktionen in dieser Reihenfolge auf.
- **Reproduzierbar:** Rohdaten werden nie verändert; ein zweiter Lauf überschreibt die Ausgaben mit identischem
  Inhalt. Teste das: Skript zweimal ausführen und die SHA-256 der Panel-CSV vergleichen; Ergebnis in
  `data/logs/checks.md`.
- **Keine fest eingetragenen Ergebnisse:** Was das Skript berechnen kann (Fallzahlen, gefundene Codes, Trefferquoten),
  berechnet es. Fest eingetragen sind nur die Regeln dieser Anleitung.
- Am Ende schreibt es `sessionInfo()` nach `data/logs/sessionInfo.txt`.

## 2 Downloads (`R/01_download.R`)

Jeden Download mit bis zu 4 Versuchen und wachsender Wartezeit ausführen (2, 4, 8, 16 s), z. B. mit
`curl::curl_download()`. Danach eine Zeile in `data/logs/download_log.csv` schreiben (SHA-256 per
`digest::digest(file = …, algo = "sha256")`), auch bei Fehlschlag. Vorhandene Dateien nicht erneut laden.

### 2.1 BRFSS-Mikrodaten 2001–2015

Gesucht ist je Jahr die **SAS-Transport-Datei (XPT, gezippt)** des Hauptdatensatzes. Speichern als
`data/raw/brfss_<Jahr>.zip`.

1. Zuerst den direkten Link probieren:
   - 2001–2010: `https://www.cdc.gov/brfss/annual_data/<Jahr>/files/CDBRFS<JJ>XPT.zip` (`<JJ>` = zweistellig, z. B. `CDBRFS03XPT`)
   - 2011–2015: `https://www.cdc.gov/brfss/annual_data/<Jahr>/files/LLCP<Jahr>XPT.zip`
   - Die Endung ist teils `.zip`, teils `.ZIP`. Beide probieren.
2. Scheitert das, die Jahresseite öffnen und dort den Link „SAS Transport Format“ nehmen. Ab 2011 gibt es
   zusätzlich reine Festnetz-Dateien („Landline“, z. B. 2012 und 2014). **Nicht diese** nehmen, sondern die
   kombinierte Datei für Festnetz und Mobilfunk (Gewicht `_LLCPWT`).
3. Ist die CDC nicht erreichbar, auf ein Archiv ausweichen:
   [DataLumos, BRFSS 1989–2023](https://www.datalumos.org/datalumos/project/240401/version/V1/view)
   (Stand vor den Änderungen der CDC-Seite Anfang 2025) oder
   [openICPSR, BRFSS 1999–2019](https://www.openicpsr.org/openicpsr/project/146342/version/V2/view).
   Die verwendete Quelle im Protokoll vermerken.

| Jahr | Jahresseite | Kennzahl zum Abgleich |
|---|---|---|
| 2001 | https://www.cdc.gov/brfss/annual_data/annual_2001.htm | ZIP etwa 34 MB, 212.510 Datensätze, 294 Variablen |
| 2002 | https://www.cdc.gov/brfss/annual_data/annual_2002.htm | |
| 2003 | https://www.cdc.gov/brfss/annual_data/annual_2003.htm | Dateiname `CDBRFS03XPT.ZIP`, etwa 48 MB |
| 2004 | https://www.cdc.gov/brfss/annual_data/annual_2004.htm | |
| 2005 | https://www.cdc.gov/brfss/annual_data/annual_2005.htm | ZIP etwa 68 MB |
| 2006 | https://www.cdc.gov/brfss/annual_data/annual_2006.htm | ZIP etwa 62 MB |
| 2007 | https://www.cdc.gov/brfss/annual_data/annual_2007.htm | |
| 2008 | https://www.cdc.gov/brfss/annual_data/annual_2008.htm | |
| 2009 | https://www.cdc.gov/brfss/annual_data/annual_2009.htm | ZIP etwa 110 MB |
| 2010 | https://www.cdc.gov/brfss/annual_data/annual_2010.htm | ZIP etwa 99 MB |
| 2011 | https://www.cdc.gov/brfss/annual_data/annual_2011.htm | ZIP etwa 128 MB |
| 2012 | https://www.cdc.gov/brfss/annual_data/annual_2012.html | 475.687 Datensätze |
| 2013 | https://www.cdc.gov/brfss/annual_data/annual_2013.html | 491.773 Datensätze |
| 2014 | https://www.cdc.gov/brfss/annual_data/annual_2014.html | 464.664 Datensätze |
| 2015 | https://www.cdc.gov/brfss/annual_data/annual_2015.html | ZIP etwa 96,5 MB, 441.456 Datensätze |

Die Datensatzzahlen schließen Territorien ein. Sie dienen nur dazu, die richtige Datei zu erkennen.

### 2.2 Steuern und Preise

| Datei | Quelle | Link |
|---|---|---|
| `tax_burden.csv` (Pflicht) | CDC STATE System: *The Tax Burden on Tobacco, 1970–2019* (Datensatz `7nwe-3aj9`) | https://data.cdc.gov/api/views/7nwe-3aj9/rows.csv?accessType=DOWNLOAD |
| Ausweichquelle dafür | Archivkopie, DOI 10.3886/E243679V1 | https://www.datalumos.org/datalumos/project/243679/version/V1/view |
| `state_tax_legislation.csv` (optional) | CDC STATE System: Tobacco Legislation – Tax (Steuersätze mit Wirksamkeitsdatum ab 1995) | Katalog: https://catalog.data.gov/dataset/cdc-state-system-tobacco-legislation-tax · Archiv: https://www.datalumos.org/datalumos/project/243424/version/V1/view |

### 2.3 Rauchverbote

`smokefree.csv` = CDC STATE System: Tobacco Legislation – Smokefree Indoor Air. Katalogeintrag:
https://catalog.data.gov/dataset/cdc-state-system-tobacco-legislation-smokefree-indoor-air.
Die Kataloge nennen zwei verschiedene IDs (`2snk-eav4` und `32fd-hyzc`). Nimm den CSV-Link direkt vom
Katalogeintrag und prüfe, dass die Datei Staaten, Jahre, Quartale und Regelungen zu Arbeitsstätten,
Restaurants und Bars enthält. Notiere die verwendete ID.

### 2.4 Wirtschaftliche Kontrollen (FRED)

Muster: `https://fred.stlouisfed.org/graph/fredgraph.csv?id=<Reihe>`, gespeichert als `data/raw/fred/<Reihe>.csv`.

- `<ST>UR` Arbeitslosenquote (monatlich) und `<ST>PCPI` Pro-Kopf-Einkommen (jährlich) für alle 51 Kürzel:
  AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK
  OR PA RI SC SD TN TX UT VT VA WA WV WI WY
- `CPIAUCSL` Verbraucherpreisindex (monatlich)

Existiert eine Reihe nicht unter diesem Namen, auf der FRED-Seite nach der richtigen ID suchen und die
Abweichung protokollieren.

### 2.5 Optional: Daten des Papers zum Abgleich

Sharbaugh et al. (2018), PLoS ONE, https://doi.org/10.1371/journal.pone.0204416. Die Zusatztabellen S2
(Raucherquote je Staat und Jahr) und S3 (Steuer je Staat und Jahr) nach `data/raw/paper/` laden. Sie dienen
nur dem Abgleich in Schritt 6.

## 3 BRFSS einlesen (`R/02_transform.R`)

Für jedes Jahr die XPT-Datei aus dem ZIP in ein temporäres Verzeichnis entpacken (der Dateiname im ZIP kann
mit Leerzeichen enden), mit `haven::read_xpt(…, col_select = any_of(vars))` nur diese Originalvariablen lesen und
die XPT-Datei danach löschen:

| Variable | Inhalt | Jahre |
|---|---|---|
| `_STATE` | Staat (FIPS-Code) | alle |
| `_SMOKER2` | Rauchstatus | 2001–2004 |
| `_SMOKER3` | Rauchstatus | 2005–2015 |
| `_FINALWT` | Gewicht | 2001–2010 |
| `_LLCPWT` | Gewicht (Raking, Festnetz und Mobilfunk) | 2011–2015 |
| `_STSTR`, `_PSU` | Schicht und Primäreinheit des Stichprobendesigns | alle |
| `IYEAR`, `IMONTH` | Jahr und Monat des Interviews | alle |
| `_AGEG5YR` | Alter in 5-Jahres-Gruppen | alle |
| `INCOME2` | Haushaltseinkommen | alle |
| `SEX` | Geschlecht | alle |
| `_RACEGR2` | Ethnie | 2001–2012 |
| `_RACEGR3` | Ethnie | 2013–2015 |
| `EDUCA` | Bildung | alle |
| `STOPSMK2` | Aufhörversuch in den letzten 12 Monaten | alle |

- Fehlt eine Variable in einem Jahr, nicht raten: im Codebook des Jahres nachsehen und die Entscheidung
  protokollieren. Eine Variable, die es in einem Jahr nicht gibt, bleibt dort `NA`.
- Variablen und Codes nicht umbenennen und nicht umkodieren. haven-Labels dürfen bleiben.
- Einzige neue Spalte: `FILE_YEAR` = Jahr der BRFSS-Datei (kann von `IYEAR` abweichen, weil Interviews ins
  Folgejahr reichen).
- Je Jahr nach `data/intermediate/brfss_<Jahr>.rds` speichern. Danach alle Jahre untereinanderhängen
  (`dplyr::bind_rows`, fehlende Variablen werden `NA`) und als `data/final/brfss_2001_2015_personen.rds`
  speichern. Dieser Personendatensatz enthält **alle** Datensätze, auch Territorien, ungefiltert.

## 4 Staat-Jahr-Zellen und Kontrollen (`R/02_transform.R`)

### 4.1 Zellwerte aus dem Personendatensatz

**Stichprobe für die Zellen** (der Personendatensatz selbst bleibt ungefiltert):

- nur 50 Staaten und D.C.: `_STATE` in {1, 2, 4, 5, 6, 8, 9, 10, 11, 12, 13, 15, 16, 17, 18, 19, 20, 21, 22, 23,
  24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 44, 45, 46, 47, 48, 49, 50, 51, 53,
  54, 55, 56}; Territorien (66, 72, 78) fallen weg,
- nur Befragte mit Altersangabe: `_AGEG5YR` zwischen 1 und 13 (14 = fehlend),
- nur Gewicht > 0. Das Gewicht ist `_FINALWT` bis 2010 und `_LLCPWT` ab 2011.

**Protokoll:** Für jedes Jahr die Zahl der Datensätze nach jedem Filter in `data/logs/transform_log.csv` schreiben
(Spalten `FILE_YEAR`, `schritt`, `n_vorher`, `n_nachher`, `n_entfernt`): eingelesen, nach Staatenfilter, nach
Altersfilter, nach Gewichtsfilter, mit gültigem Rauchstatus. Außerdem für jede verwendete Quellvariable die
Häufigkeit jedes vorkommenden Codes je Jahr in `data/logs/code_frequencies.csv` (Spalten `FILE_YEAR`, `variable`,
`code`, `n`). So fallen unerwartete Codes auf.

**Hilfsgrößen** (nur für die Rechnung, nicht im Personendatensatz speichern):

| Hilfsgröße | Regel |
|---|---|
| Raucher | Rauchstatus (`_SMOKER2` bzw. `_SMOKER3`) 1 oder 2 → 1; 3 oder 4 → 0; sonst `NA` |
| Altersgruppe | `_AGEG5YR` 1 → 18–24; 2–5 → 25–44; 6–9 → 45–64; 10–13 → 65+ |
| Einkommensgruppe | `INCOME2` 1–4 → unter $25.000; 5–6 → $25.000–49.999; 7 → $50.000–74.999; 8 → ab $75.000; 77/99 → `NA` |
| Ethnie | `_RACEGR2` bzw. `_RACEGR3`: 1 → weiß, nicht hispanisch; 2 → schwarz, nicht hispanisch; 5 → hispanisch |
| Geschlecht | `SEX` 1 → männlich, 2 → weiblich |
| Hochschulabschluss | `EDUCA` 6 → 1; 1–5 → 0; 9 → `NA` |
| Aufhörversuch | nur aktuelle Raucher: `STOPSMK2` 1 → 1, 2 → 0, sonst `NA` |

**Zellwerte je `_STATE` und `FILE_YEAR`** (nur Befragte mit gültigem Rauchstatus), mit
`weighted.mean(x, w, na.rm = TRUE)`:

- `prev` = gewichteter Raucheranteil. Das entspricht der Punktschätzung von SAS `SURVEYFREQ` im Paper.
- `n` = ungewichtete Zahl der Befragten.
- dieselbe Rechnung je Teilgruppe: `prev_<code>`, `n_<code>` (Codes im Codebook unten),
- `quit` = gewichteter Anteil mit Aufhörversuch unter aktuellen Rauchern, `n_quit` = Zahl gültiger Antworten,
- Zusammensetzung, gewichtet: `sh_age1824`, `sh_age2544`, `sh_age4564`, `sh_female`, `sh_black`, `sh_hisp`,
  `sh_college`, `sh_lowinc` (Anteil unter $25.000 an den Befragten mit Einkommensangabe).

### 4.2 Steuern und Preise

- `tax_burden.csv` mit `readr::read_csv()` lesen; Spaltennamen nicht verändern.
- Zuerst alle Werte von `SubMeasureDesc` ausgeben und protokollieren. Verwendet werden die Zeilen
  `State Tax per pack`, `Federal and State Tax per pack` und `Average Cost per pack` mit ihrem `Data_Value`
  (Dollar je Packung; `$` und Tausendertrennzeichen entfernen).
- Ins Panel kommen sie als Spalten, die genau so heißen wie der `SubMeasureDesc`-Wert (in R mit Backticks):
  `` `State Tax per pack` ``, `` `Federal and State Tax per pack` ``, `` `Average Cost per pack` ``.
- Schlüssel aus der Steuerdatei: `LocationAbbr`, `LocationDesc`, `Year`.
- Im Datensatzbeschreibungstext nachsehen, auf welchen Stichtag oder welches Fiskaljahr sich `Year` bezieht, und
  das im Codebook festhalten. Das Paper nutzt Steuersätze der Federation of Tax Administrators; Abweichungen im
  Stichtag sind deshalb zu erwarten.
- **Optional:** Liegt `state_tax_legislation.csv` vor, daraus je Staat und Kalenderjahr den zeitgewichteten
  Durchschnitt des staatlichen Zigarettensteuersatzes berechnen (`state_tax_calavg`). Die Struktur zuerst
  ansehen; ist unklar, wie Satz und Wirksamkeitsdatum kodiert sind, auslassen und protokollieren.

### 4.3 FRED

Die Monatsreihen zu Jahresmitteln mitteln; `<ST>PCPI` ist bereits jährlich. Die Datumsspalte kann `DATE` oder
`observation_date` heißen. Ins Panel kommen die Werte unter dem Stamm des FRED-Namens: `UR` (aus `<ST>UR`),
`PCPI` (aus `<ST>PCPI`) und `CPIAUCSL`.

### 4.4 Rauchverbote

Je Staat, Jahr und Quartal prüfen, ob Rauchen in privaten Arbeitsstätten, Restaurants **und** Bars vollständig
verboten ist. `smokefree_comprehensive` = Anteil der Quartale eines Jahres mit vollständigem Verbot an allen drei
Orten (0 bis 1). Welche Spalten und Textwerte als „vollständig verboten“ gelten, im Codebook dokumentieren.

### 4.5 Reale Werte

In Dollar von 2015: `x_real2015 = x × CPIAUCSL(2015) / CPIAUCSL(Jahr)`. Neue Spalten:
`state_tax_real2015`, `fedstate_tax_real2015`, `avg_price_real2015`, `PCPI_real2015` und
`ln_PCPI_real2015` (natürlicher Logarithmus).

## 5 Fertiger Datensatz (`R/02_transform.R`)

- Basis sind die BRFSS-Zellen (Schlüssel `_STATE`, `FILE_YEAR`). In den Zellen `FILE_YEAR` in `Year` umbenennen
  (so heißt der Jahresschlüssel in der Steuerdatei) und mit einer Zuordnung FIPS → Postkürzel die Spalte
  `LocationAbbr` ergänzen. Dann die Steuerdaten über `LocationAbbr` und `Year` anhängen; `Year` kommt damit immer
  aus den BRFSS-Zellen und ist nie leer.
- FRED über `LocationAbbr` und `Year`, die Rauchverbote über Kürzel und Jahr anhängen.
- Nur Left Joins auf die BRFSS-Zellen; keine Zeilen hinzufügen oder entfernen. Erwartet: genau 765 Zeilen
  (51 × 15), sortiert nach `LocationAbbr`, `Year`.
- Für jede Zusammenführung in `data/logs/join_log.csv` festhalten, wie viele der 765 Zeilen einen Treffer
  hatten, und alle Schlüssel ohne Treffer auflisten.
- Speichern als `data/final/panel_state_year_2001_2015.rds` (`saveRDS`) und als CSV (`readr::write_csv`, UTF-8,
  Komma als Trennzeichen, Punkt als Dezimalzeichen, leere Felder für `NA`).
- Das Codebook entsteht in Schritt 7 (`write_codebook()` in `R/02_transform.R`), nicht von Hand.

**Variablenverzeichnis des fertigen Datensatzes.** Diese Tabelle ist Teil A des Codebooks (Schritt 7). Die
Transformationen gelten verbindlich; wer davon abweicht, ändert die Tabelle und protokolliert den Grund.

Gemeinsame Begriffe:
- **Zellstichprobe** = Befragte mit `_STATE` in den 50 Staaten und D.C., `_AGEG5YR` 1–13 und Gewicht > 0.
- **Gewicht w** = `_FINALWT` für `Year` ≤ 2010, `_LLCPWT` für `Year` ≥ 2011.
- **Raucher r** = 1, wenn `_SMOKER2` (2001–2004) bzw. `_SMOKER3` (2005–2015) 1 oder 2 ist; 0 bei 3 oder 4;
  sonst `NA` (z. B. 9 = weiß nicht, verweigert).
- **Gewichteter Anteil** einer 0/1-Variable x = Σ w·x / Σ w über alle Befragten der Zelle mit gültigem x.

| Spalte | Quellvariable(n) | Transformation | Einheit | Fehlende Werte |
|---|---|---|---|---|
| `_STATE` | BRFSS `_STATE` | unverändert; nur 50 Staaten und D.C. | FIPS-Code | keine |
| `LocationAbbr` | Zuordnungstabelle FIPS → Postkürzel im Skript | aus `_STATE` abgeleitet; gleiche Schreibweise wie `LocationAbbr` der Steuerdatei | Text | keine |
| `LocationDesc` | Tax Burden `LocationDesc` | unverändert übernommen | Text | wenn Steuerdatei ohne Treffer |
| `Year` | BRFSS-Dateijahr (`FILE_YEAR`) | umbenannt in `Year`; Schlüssel für Steuern, FRED und Rauchverbote | Jahr | keine |
| `State Tax per pack` | Tax Burden `Data_Value` bei `SubMeasureDesc` = „State Tax per pack“ | `$` und Tausendertrennzeichen entfernt, in Zahl umgewandelt; sonst unverändert | $ nominal | wenn kein Eintrag |
| `Federal and State Tax per pack` | wie oben, `SubMeasureDesc` = „Federal and State Tax per pack“ | wie oben | $ nominal | wenn kein Eintrag |
| `Average Cost per pack` | wie oben, `SubMeasureDesc` = „Average Cost per pack“ | wie oben | $ nominal | wenn kein Eintrag |
| `UR` | FRED `<LocationAbbr>UR`, monatlich | arithmetisches Mittel der 12 Monate des Kalenderjahres `Year` | Prozent | `NA`, wenn nicht alle 12 Monate vorliegen |
| `PCPI` | FRED `<LocationAbbr>PCPI`, jährlich | Jahreswert für `Year`, unverändert | $ nominal | wenn kein Eintrag |
| `CPIAUCSL` | FRED `CPIAUCSL`, monatlich | arithmetisches Mittel der 12 Monate von `Year` | Index 1982–84 = 100 | keine erwartet |
| `prev` | `_SMOKER2`/`_SMOKER3`, Gewicht | gewichteter Anteil von r in der Zellstichprobe | Anteil 0–1 | keine erwartet |
| `n` | wie oben | Zahl der Befragten der Zellstichprobe mit gültigem r, ungewichtet | Anzahl | keine |
| `prev_age1824`, `prev_age2544`, `prev_age4564`, `prev_age65p` | zusätzlich `_AGEG5YR` | wie `prev`, nur `_AGEG5YR` = 1 bzw. 2–5 bzw. 6–9 bzw. 10–13 | Anteil | wenn Gruppe leer |
| `prev_male`, `prev_female` | zusätzlich `SEX` | wie `prev`, nur `SEX` = 1 bzw. 2 | Anteil | wenn Gruppe leer |
| `prev_inc_lt25k`, `prev_inc_25_50k`, `prev_inc_50_75k`, `prev_inc_ge75k` | zusätzlich `INCOME2` | wie `prev`, nur `INCOME2` = 1–4 bzw. 5–6 bzw. 7 bzw. 8; Codes 77, 99 und fehlend gehören zu keiner Gruppe | Anteil | wenn Gruppe leer |
| `prev_white_nh`, `prev_black_nh`, `prev_hisp` | zusätzlich `_RACEGR2` (bis 2012) bzw. `_RACEGR3` (ab 2013) | wie `prev`, nur Code 1 bzw. 2 bzw. 5 | Anteil | wenn Gruppe leer |
| `n_<code>` | wie die jeweilige Gruppe | Zahl der Befragten der Gruppe mit gültigem r | Anzahl | keine (0 bei leerer Gruppe) |
| `quit` | `STOPSMK2` | nur Befragte mit r = 1; q = 1 bei `STOPSMK2` = 1, 0 bei 2, sonst `NA`; gewichteter Anteil von q | Anteil | wenn keine gültige Antwort |
| `n_quit` | wie oben | Zahl der Raucher mit gültigem q | Anzahl | keine |
| `sh_age1824`, `sh_age2544`, `sh_age4564` | `_AGEG5YR` | gewichteter Anteil von `_AGEG5YR` = 1 bzw. 2–5 bzw. 6–9 an der Zellstichprobe mit gültigem r | Anteil | keine erwartet |
| `sh_female` | `SEX` | gewichteter Anteil von `SEX` = 2 | Anteil | keine erwartet |
| `sh_black`, `sh_hisp` | `_RACEGR2`/`_RACEGR3` | gewichteter Anteil von Code 2 bzw. 5 | Anteil | keine erwartet |
| `sh_college` | `EDUCA` | 1 bei `EDUCA` = 6, 0 bei 1–5, sonst `NA`; gewichteter Anteil der gültigen Werte | Anteil | keine erwartet |
| `sh_lowinc` | `INCOME2` | 1 bei `INCOME2` 1–4, 0 bei 5–8, sonst `NA`; gewichteter Anteil der gültigen Werte | Anteil | keine erwartet |
| `state_tax_real2015`, `fedstate_tax_real2015`, `avg_price_real2015` | Steuer- bzw. Preisspalte, `CPIAUCSL` | x × `CPIAUCSL`(2015) / `CPIAUCSL`(`Year`) | $ von 2015 | wenn x fehlt |
| `PCPI_real2015` | `PCPI`, `CPIAUCSL` | wie oben | $ von 2015 | wenn `PCPI` fehlt |
| `ln_PCPI_real2015` | `PCPI_real2015` | natürlicher Logarithmus | log $ | wenn `PCPI` fehlt |
| `smokefree_comprehensive` | STATE System, Smokefree Indoor Air | je Quartal 1, wenn private Arbeitsstätten, Restaurants und Bars vollständig rauchfrei sind, sonst 0; Mittel über die Quartale von `Year`. Welche Spalten und Textwerte als „vollständig rauchfrei“ zählen, steht in Teil B | Anteil 0–1 | wenn kein Quartal vorliegt |
| `state_tax_calavg` (optional) | STATE System, Tobacco Legislation – Tax | Steuersatz je Tag aus Wirksamkeitsdaten, gemittelt über das Kalenderjahr `Year` | $ nominal | wenn nicht berechnet |

## 6 Prüfungen (`R/03_checks.R`)

Alle Ergebnisse mit Zahlen in `data/logs/checks.md` schreiben. Eine fehlgeschlagene Prüfung nicht
„reparieren“, sondern Ursache suchen und berichten.

1. **Originalnamen:** Personendatensatz enthält `_STATE`, `_SMOKER2`, `_SMOKER3`, `_FINALWT`, `_LLCPWT`,
   `_AGEG5YR`, `INCOME2`, `SEX`, `_RACEGR2`, `_RACEGR3`, `EDUCA`, `STOPSMK2` unter genau diesen Namen; das Panel
   enthält `_STATE`, `LocationAbbr`, `Year` und die drei Steuer- bzw. Preisspalten unter ihren Originalnamen.
2. **Struktur:** Panel mit 765 Zeilen, 51 Staaten, 15 Jahren, keine doppelten Schlüssel.
3. **Wertebereiche:** alle Anteile in [0, 1]; Steuern und Preise > 0; `n` > 0.
4. **Fehlende Werte:** Anzahl je Spalte. Teilgruppen mit kleinen Zellen (z. B. hispanisch in kleinen Staaten)
   dürfen Lücken haben; `prev`, `State Tax per pack`, `UR` und `PCPI` sollten vollständig sein.
5. **Abgleich mit den Angaben des Papers** (dort ohne D.C. möglich, daher leichte Abweichungen zulässig):
   - Raucherquote 2001 zwischen 13,3 % und 30,9 %, 2015 zwischen 9,1 % und 26,1 %
   - Steuer 2001 zwischen $0,03 und $1,11, 2015 zwischen $0,17 und $4,35 (nominal)
   - Anteil mit Aufhörversuch 2001 zwischen 47,7 % und 65,7 %, 2015 zwischen 53,3 % und 68,3 %
6. **Datensatzzahlen** je Jahr im Personendatensatz mit der Tabelle in 2.1 vergleichen.
7. **Methodenbruch 2011:** Mittelwert von `prev` je Jahr ausgeben. Ein Sprung 2010/2011 ist erwartbar
   (Mobiltelefone, Raking), nur dokumentieren.
8. **Protokolle vollständig:** `transform_log.csv` hat für jedes Jahr alle fünf Schritte;
   `code_frequencies.csv` enthält keine Codes, die in Abschnitt 4.1 nicht vorkommen, oder sie sind in `checks.md`
   erklärt; `join_log.csv` zeigt für die Steuerdaten 765 Treffer.
9. **Falls S2/S3 des Papers vorliegen:** je Staat und Jahr Differenz zu `prev` und `State Tax per pack`;
   Korrelation, mittlere und größte absolute Abweichung berichten.

## 7 Codebook (`R/02_transform.R`, letzter Schritt)

`write_codebook()` erzeugt `data/final/codebook.md` aus den Regeln dieser Anleitung und den Protokollen. Zahlen kommen
immer aus den Protokolldateien, nie von Hand. Wird ein Schritt geändert und neu ausgeführt, entsteht ein neues
Codebook. Das Codebook hat drei Teile:

**Teil A: Variablenverzeichnis.** Die Tabelle aus Schritt 5, ergänzt um je Spalte Minimum, Maximum, Mittelwert
und Zahl fehlender Werte im fertigen Datensatz. Für den Personendatensatz genügt eine kurze Liste: die
Originalvariablen aus Abschnitt 3 mit Verweis auf das BRFSS-Codebook des jeweiligen Jahres, dazu die einzige neue
Spalte `FILE_YEAR`.

**Teil B: Transformationsprotokoll**, in dieser Reihenfolge:

1. *Einlesen:* je Jahr Datei, Quelle (CDC oder Archiv), Zahl der Datensätze und welche der Variablen aus
   Abschnitt 3 fehlten.
2. *Filter:* Tabelle Jahr × Schritt mit den Fallzahlen aus `transform_log.csv` (eingelesen → Staaten → Alter →
   Gewicht → gültiger Rauchstatus).
3. *Umkodierungen:* die Regeln aus Abschnitt 4.1 als Tabelle „Quellvariable, Code, neuer Wert“, dazu die
   tatsächlich gefundenen Codes aus `code_frequencies.csv` und wie unerwartete Codes behandelt wurden.
4. *Aggregation:* die Formel für gewichtete Anteile und welche Befragten jeweils in Zähler und Nenner eingehen.
5. *Steuerdaten:* alle gefundenen `SubMeasureDesc`-Werte, welche verwendet wurden, die Bereinigung von
   `Data_Value` und worauf sich `Year` in der Steuerdatei bezieht.
6. *FRED:* verwendete Reihen, Abweichungen von den Namensmustern, Jahre mit unvollständigen Monaten.
7. *Rauchverbote:* verwendete Datensatz-ID, die Spalten und die exakten Textwerte, die als „vollständig
   rauchfrei“ gezählt wurden.
8. *Reale Werte:* der verwendete Wert von `CPIAUCSL` für 2015.
9. *Zusammenführung:* Treffer je Join aus `join_log.csv` und alle Schlüssel ohne Treffer.
10. *Abweichungen und offene Punkte:* jede Abweichung von dieser Anleitung mit Begründung.

**Teil C: Quellen.** Je Rohdatei Datensatzname, URL, Abrufdatum, Dateigröße und SHA-256 aus
`download_log.csv`, dazu das „Zuletzt aktualisiert“-Datum der Quelle, soweit angegeben.

## 8 Ausgabe und Bericht

Am Ende müssen diese Dateien existieren:

- `R/01_download.R`, `R/02_transform.R`, `R/03_checks.R`
- `data/raw/…` (alle Rohdateien), `data/logs/download_log.csv`
- `data/final/brfss_2001_2015_personen.rds`
- `data/final/panel_state_year_2001_2015.rds` und `.csv` (der fertige Datensatz)
- `data/final/codebook.md`, `data/logs/checks.md` und die übrigen Protokolle in `data/logs/`

Diese Dateien zusätzlich als eigene Dateien an den Nutzer ausgeben:

- `R/02_transform.R` (das Transformationsskript von den Rohdaten zum fertigen Datensatz),
- `data/final/panel_state_year_2001_2015.rds` und `.csv` (der fertige Datensatz),
- `data/final/codebook.md`.

Im Abschlussbericht stehen:

- welche Quellen geladen wurden und welche Ausweichquellen nötig waren,
- die Ergebnisse der Prüfungen aus Schritt 6 in Kurzform,
- jede Abweichung von dieser Anleitung.

Laden in R zur Kontrolle:

```r
panel <- readRDS("data/final/panel_state_year_2001_2015.rds")
summary(panel$prev)
summary(panel$`State Tax per pack`)
```
