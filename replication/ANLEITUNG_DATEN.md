# Anleitung für Claude: Rohdaten laden und Staat-Jahr-Panel in R bauen

**Auftrag.** Lade alle Rohdaten für die Bachelorarbeit „Senken höhere Zigarettensteuern die Raucherquote in den
US-Bundesstaaten?“ herunter und speichere sie unverändert in einem Ordner. Bau daraus zwei Datensätze für die
Auswertung in R:

1. einen **Personendatensatz** mit den BRFSS-Originalvariablen 2001–2015,
2. den **fertigen Datensatz**: ein Panel aus 50 Staaten und Washington, D.C. für 2001–2015 (765 Zeilen).

Schreib die gesamte Aufbereitung als **R-Skripte**, damit sie reproduzierbar ist. Schätze **keine** Modelle; es
geht nur um die Daten.

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
├── 01_download.R             # Schritt 2
├── 02_brfss.R                # Schritt 3
├── 03_panel.R                # Schritte 4–5
└── 04_checks.R               # Schritt 6
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
│   └── codebook.md                          # jede Spalte: Quelle, Konstruktion, Einheit
└── logs/
    ├── download_log.csv                     # URL, Datei, Bytes, SHA-256, Zeitpunkt, Status
    └── checks.md                            # Ergebnisse der Prüfungen aus Schritt 6
```

Jedes Skript lässt sich mit `Rscript R/0x_….R` einzeln ausführen und liest nur Dateien aus früheren Schritten.

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

## 3 BRFSS einlesen (`R/02_brfss.R`)

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

## 4 Staat-Jahr-Zellen und Kontrollen (`R/03_panel.R`, Teil 1)

### 4.1 Zellwerte aus dem Personendatensatz

**Stichprobe für die Zellen** (der Personendatensatz selbst bleibt ungefiltert):

- nur 50 Staaten und D.C.: `_STATE` in {1, 2, 4, 5, 6, 8, 9, 10, 11, 12, 13, 15, 16, 17, 18, 19, 20, 21, 22, 23,
  24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 44, 45, 46, 47, 48, 49, 50, 51, 53,
  54, 55, 56}; Territorien (66, 72, 78) fallen weg,
- nur Befragte mit Altersangabe: `_AGEG5YR` zwischen 1 und 13 (14 = fehlend),
- nur Gewicht > 0. Das Gewicht ist `_FINALWT` bis 2010 und `_LLCPWT` ab 2011.

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

## 5 Fertiger Datensatz (`R/03_panel.R`, Teil 2)

- Basis sind die BRFSS-Zellen (Schlüssel `_STATE`, `FILE_YEAR`). In den Zellen `FILE_YEAR` in `Year` umbenennen
  (so heißt der Jahresschlüssel in der Steuerdatei) und mit einer Zuordnung FIPS → Postkürzel die Spalte
  `LocationAbbr` ergänzen. Dann die Steuerdaten über `LocationAbbr` und `Year` anhängen; `Year` kommt damit immer
  aus den BRFSS-Zellen und ist nie leer.
- FRED über `LocationAbbr` und `Year`, die Rauchverbote über Kürzel und Jahr anhängen.
- Nur Left Joins auf die BRFSS-Zellen; keine Zeilen hinzufügen oder entfernen. Erwartet: genau 765 Zeilen
  (51 × 15), sortiert nach `LocationAbbr`, `Year`.
- Speichern als `data/final/panel_state_year_2001_2015.rds` (`saveRDS`) und als CSV (`readr::write_csv`, UTF-8,
  Komma als Trennzeichen, Punkt als Dezimalzeichen, leere Felder für `NA`).
- `data/final/codebook.md` schreiben, mit allen Spalten aus der folgenden Tabelle plus etwaigen Zusätzen.

**Codebook des fertigen Datensatzes**

| Spalte | Herkunft | Inhalt | Einheit |
|---|---|---|---|
| `_STATE` | BRFSS, Original | FIPS-Code des Staates | Zahl |
| `LocationAbbr`, `LocationDesc` | Tax Burden, Original | Postkürzel und Name des Staates | Text |
| `Year` | BRFSS-Dateijahr (`FILE_YEAR`), benannt wie der Jahresschlüssel der Steuerdatei | Jahr der Befragung bzw. der Steuerangabe | Jahr |
| `State Tax per pack` | Tax Burden, Original (`Data_Value`) | staatliche Zigarettensteuer je Packung, nominal | $ |
| `Federal and State Tax per pack` | Tax Burden, Original (`Data_Value`) | Bundes- plus Staatssteuer je Packung, nominal | $ |
| `Average Cost per pack` | Tax Burden, Original (`Data_Value`) | Durchschnittspreis je Packung, nominal | $ |
| `UR` | FRED `<ST>UR`, Jahresmittel | Arbeitslosenquote | Prozent |
| `PCPI` | FRED `<ST>PCPI` | Pro-Kopf-Einkommen, nominal | $ |
| `CPIAUCSL` | FRED, Jahresmittel | Verbraucherpreisindex | Index |
| `prev` | neu, aus `_SMOKER2`/`_SMOKER3` und Gewicht | gewichteter Raucheranteil (abhängige Variable) | Anteil 0–1 |
| `n` | neu | Befragte mit gültigem Rauchstatus | Anzahl |
| `prev_age1824`, `prev_age2544`, `prev_age4564`, `prev_age65p` | neu, zusätzlich `_AGEG5YR` | Raucheranteil nach Alter | Anteil |
| `prev_male`, `prev_female` | neu, zusätzlich `SEX` | Raucheranteil nach Geschlecht | Anteil |
| `prev_inc_lt25k`, `prev_inc_25_50k`, `prev_inc_50_75k`, `prev_inc_ge75k` | neu, zusätzlich `INCOME2` | Raucheranteil nach Haushaltseinkommen | Anteil |
| `prev_white_nh`, `prev_black_nh`, `prev_hisp` | neu, zusätzlich `_RACEGR2`/`_RACEGR3` | Raucheranteil nach Ethnie | Anteil |
| `n_<code>` | neu | Zellgröße je Teilgruppe (gleiche Codes wie oben) | Anzahl |
| `quit`, `n_quit` | neu, aus `STOPSMK2` | Anteil der Raucher mit Aufhörversuch; gültige Antworten | Anteil, Anzahl |
| `sh_age1824`, `sh_age2544`, `sh_age4564`, `sh_female`, `sh_black`, `sh_hisp`, `sh_college`, `sh_lowinc` | neu, aus `_AGEG5YR`, `SEX`, `_RACEGR2/3`, `EDUCA`, `INCOME2` | Zusammensetzung der Stichprobe, gewichtet | Anteil |
| `state_tax_real2015`, `fedstate_tax_real2015`, `avg_price_real2015` | neu | Steuern und Preis in Dollar von 2015 | $ |
| `PCPI_real2015`, `ln_PCPI_real2015` | neu | reales Pro-Kopf-Einkommen; Logarithmus | $; log |
| `smokefree_comprehensive` | neu, aus STATE System | Anteil des Jahres mit vollständigem Rauchverbot in Arbeitsstätten, Restaurants und Bars | Anteil |
| `state_tax_calavg` | optional, neu | zeitgewichtete staatliche Steuer im Kalenderjahr | $ |

## 6 Prüfungen (`R/04_checks.R`)

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
8. **Falls S2/S3 des Papers vorliegen:** je Staat und Jahr Differenz zu `prev` und `State Tax per pack`;
   Korrelation, mittlere und größte absolute Abweichung berichten.

## 7 Ausgabe und Bericht

Am Ende müssen diese Dateien existieren:

- `R/01_download.R` bis `R/04_checks.R`
- `data/raw/…` (alle Rohdateien), `data/logs/download_log.csv`
- `data/final/brfss_2001_2015_personen.rds`
- `data/final/panel_state_year_2001_2015.rds` und `.csv` (der fertige Datensatz)
- `data/final/codebook.md`, `data/logs/checks.md`

Den fertigen Datensatz (`panel_state_year_2001_2015.rds` und `.csv`) zusätzlich als eigene Dateien an den Nutzer
ausgeben. Im Abschlussbericht stehen:

- welche Quellen geladen wurden und welche Ausweichquellen nötig waren,
- die Ergebnisse der Prüfungen aus Schritt 6 in Kurzform,
- jede Abweichung von dieser Anleitung.

Laden in R zur Kontrolle:

```r
panel <- readRDS("data/final/panel_state_year_2001_2015.rds")
summary(panel$prev)
summary(panel$`State Tax per pack`)
```
