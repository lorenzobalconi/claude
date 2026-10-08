# Replikation: Zigarettensteuern und Raucherprävalenz mit einem Fractional Response Model

Replikation und Erweiterung von Sharbaugh, Althouse et al. (2018), *Impact of cigarette taxes on smoking
prevalence from 2001–2015*, PLoS ONE 13(9): e0204416.

**Original:** Lineares Mixed Model der Raucherprävalenz je Staat und Jahr (BRFSS, Survey-gewichtet) auf die
nominale Zigarettensteuer, Random Effects für Staat und Jahr, modellbasierte Standardfehler.
Hauptergebnis: −0,60 Prozentpunkte je $0,25 Steuer [−0,66; −0,55].

**Hier:** CRE-Fractional-Probit nach Papke & Wooldridge (2008) mit Mundlak-Means, Jahres-Fixed-Effects,
cluster-robuster Inferenz und APEs, dazu Tests auf Spezifikation und Endogenität sowie eine Monte-Carlo-Studie
zur Konsistenz der Schätzer.

## Aufbau

| Datei | Inhalt |
|---|---|
| `frm_panel/estimators.py` | Paper-Mixed-Model, FE-OLS, FE-2SLS, gepooltes und CRE-Fractional-Probit, Kontrollfunktion, APE mit Delta-Methode, Panel-Bootstrap, Mundlak-, Leads- und RESET-Test |
| `frm_panel/data.py` | Download und Aufbau des Staat-Jahr-Panels aus den BRFSS-Mikrodaten, Steuern, FRED-Kontrollen |
| `frm_panel/simulate.py` | Datengenerator mit bekanntem wahren APE |
| `scripts/monte_carlo.py` | Monte-Carlo-Studie (500 Ziehungen je Szenario, etwa 2,5 Minuten auf 4 Kernen) |
| `scripts/get_data.py`, `scripts/build_panel.py`, `scripts/run_replication.py` | Pipeline für die echten Daten |
| `tests/` | Tests ohne Netzzugang (synthetische BRFSS-Dateien, simulierte Panels) |

## Ausführen

```bash
pip install -r requirements.txt
python scripts/get_data.py          # braucht www.cdc.gov, data.cdc.gov, fred.stlouisfed.org
python scripts/build_panel.py       # -> data/panel.csv
python scripts/run_replication.py --boot 499
# optional mit Instrument(en) für die Steuer: --instruments data/raw/instruments.csv (Spalten state, year, …)
python scripts/monte_carlo.py --reps 500 --workers 4
python -m pytest -q tests
```

## Spezifikationen in `run_replication.py`

1. Paper-Modell (LMM, RE Staat + RE Jahr, nominale Steuer). Replikationsziel −0,60.
2. –3. dasselbe mit realer Steuer; Variante mit Jahres-FE.
4. –5. FE-OLS (Staat + Jahr), ohne und mit Kontrollen, Cluster-SE.
6. Gepooltes fraktionales Probit ohne Staatseffekte (zeigt die Verzerrung durch Unterschiede zwischen Staaten).
7. –8. CRE-Fractional-Probit, ohne und mit Kontrollen (Hauptspezifikation), APE mit Delta- und Bootstrap-SE.
9. –12. Robustheit: Gewichtung mit Zellgröße (Binomial-QMLE), Logit-Link, nominale Steuer, Vorjahressteuer.
13. –14. Kontrollfunktion und FE-2SLS, falls ein Instrument übergeben wird.

Kontrollen: Arbeitslosenquote, reales Pro-Kopf-Einkommen (log), Zusammensetzung der BRFSS-Stichprobe je Zelle
(Alter, Geschlecht, Ethnie, Bildung, Einkommen) und, falls verfügbar, umfassende Rauchverbote.
Tests: Mundlak (H0: Staatseffekte unkorreliert mit der Steuer), RESET, Leads (strikte Exogenität bzw.
Politik-Endogenität). Dazu die Teilgruppen aus Tabelle 1 des Papers und die Aufhörversuche.

## Ergebnisse der Monte-Carlo-Studie

51 Staaten × 15 Jahre, BRFSS-artiges Stichprobenrauschen, wahres Modell ist ein Probit im Index. Effekte in
Prozentpunkten je $0,25; wahrer APE etwa −0,30. Details in `results/mc_summary.md`.

| Schätzer | A0: CRE-Annahmen, kein Trend | A: wie A0 + nationaler Trend | B: + zeitvariable Endogenität |
|---|---|---|---|
| Paper-LMM (RE Staat + RE Jahr) | −0,18 (Bias 43 %, KI-Abdeckung 5 %) | −0,06 (79 %, 0 %) | −0,82 (−177 %, 0 %) |
| FE-OLS (Staat + Jahr) | −0,16 (49 %) | −0,05 (84 %) | −0,76 (−158 %) |
| Gepooltes fraktionales Probit | −1,70 (−434 %) | −1,60 (−440 %) | −1,66 (−463 %) |
| **CRE-Fractional-Probit** | **−0,32 (0 %, Abdeckung 93 %)** | **−0,29 (1 %, 93 %)** | −0,77 (−161 %) |
| CRE-Fractional-Logit | −0,34 (−7 %) | −0,34 (−16 %) | −0,77 (−162 %) |
| **CRE-FP + Kontrollfunktion** | – | – | **−0,30 (0 %)** |
| FE-2SLS | – | – | −0,29 (1 %) |

Was die Simulation zeigt:

- **Unterschiede zwischen Staaten:** Ohne Kontrolle der Staatseffekte ist der Schätzer massiv verzerrt
  (gepooltes Probit). Mundlak-Means beheben das vollständig.
- **Inferenz im Paper:** Die modellbasierten Standardfehler des Mixed Models sind etwa dreimal zu klein
  (mittlerer SE 0,019 bei tatsächlicher Streuung 0,06). Selbst ohne Bias wären die Konfidenzintervalle
  des Papers deutlich zu eng. Cluster-robuste Inferenz ist nötig.
- **Lineare Modelle schätzen eine andere Größe:** Ist das wahre Modell ein Probit, gewichtet FE-OLS die
  Staaten nach der Varianz ihrer Steueränderungen. Die größten Erhöhungen gab es in Niedrigraucherstaaten,
  wo der Effekt in Prozentpunkten kleiner ist. Additive Jahreseffekte in Prozentpunkten passen zudem nicht zu
  einem Trend im Index. Beides zieht die linearen Schätzer gegen null. Dieser Befund hängt an der Annahme eines
  Index-Modells; ob er in den echten Daten auftritt, zeigt der Vergleich von Spezifikation (5) und (8).
- **Endogenität:** Reagiert die Steuerpolitik auf zeitvariable Faktoren, die auch das Rauchen senken, sind
  alle Schätzer ohne Instrument verzerrt, auch das CRE-Probit. Die Kontrollfunktion und FE-2SLS treffen den
  wahren Wert. Die naiven Standardfehler der Kontrollfunktion sind zu klein (Abdeckung 86 %), deshalb
  Bootstrap über beide Stufen.
- **Tests:** Der Leads-Test hält sein Niveau (5 %) und erkennt die Endogenität in Szenario B in 41 % der
  Fälle. Der Exogenitätstest der Kontrollfunktion erkennt sie immer. RESET lehnt mit cluster-robusten
  Standardfehlern bei 51 Clustern auch beim korrekten Modell zu oft ab (etwa 16 % statt 5 %); eine
  RESET-Ablehnung ist deshalb nur ein schwaches Signal.
- **Probit statt Logit:** Unter normaler Heterogenität ist nur das CRE-Probit kohärent; das Logit weicht
  um 7–16 % ab.

## Offene Punkte für die echten Daten

- Steuer-Timing: Die CDC-Datei „Tax Burden on Tobacco“ meldet Steuersätze je Jahr; das Paper nutzt die
  Federation of Tax Administrators. Spezifikation (12) prüft die Vorjahressteuer.
- Die Paper-Spezifikation nutzt nominale Steuern; ab (2) werden reale Steuern in Dollar von 2015 verwendet.
- Der Parser für die Rauchverbote (CDC STATE System) ist ohne echte Datei ungetestet und wird bei
  unerwarteter Struktur ausgelassen.
- Ein glaubwürdiges Instrument für die Steuer ist nicht automatisch enthalten. Ohne Instrument stützt sich die
  Endogenitätsprüfung auf Mundlak-Means, Jahres-FE, Kontrollen und den Leads-Test.
- Inferenz mit 51 Clustern: Bei den Teilgruppen mit kleinen Zellen (Alter 18–24, Hispanisch, Schwarz)
  sind Bootstrap-SE maßgeblich.
