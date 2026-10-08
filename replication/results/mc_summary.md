# Monte-Carlo-Ergebnisse

500 Ziehungen je Szenario, N = 51 Staaten, T = 15 Jahre. Effekte in Prozentpunkten je $0,25 Steuer.

## Szenario A0

Wahrer APE im Mittel: -0.318 pp

| Schätzer                                        |   Mittel |   Bias |   Bias in % |   RMSE |    SD |   mittl. SE |   Abdeckung 95 % |
|:------------------------------------------------|---------:|-------:|------------:|-------:|------:|------------:|-----------------:|
| Paper: lineares Mixed Model, RE Staat + RE Jahr |   -0.180 |  0.138 |      43.328 |  0.151 | 0.061 |       0.019 |            4.800 |
| Lineares Mixed Model, RE Staat + Jahres-FE      |   -0.172 |  0.146 |      46.062 |  0.159 | 0.062 |       0.020 |            4.600 |
| FE-OLS (Staat + Jahr)                           |   -0.163 |  0.155 |      48.848 |  0.167 | 0.060 |       0.042 |            9.800 |
| Gepooltes fraktionales Probit (ohne Means)      |   -1.699 | -1.381 |    -434.411 |  1.389 | 0.150 |       0.142 |            0.000 |
| CRE-Fractional-Probit (Mundlak)                 |   -0.317 |  0.001 |       0.218 |  0.034 | 0.035 |       0.032 |           92.600 |
| CRE-Fractional-Logit (Mundlak)                  |   -0.341 | -0.023 |      -7.385 |  0.044 | 0.038 |       0.036 |           87.200 |

| Test | Ablehnrate bei 5 % |
|---|---|
| Mundlak-Test (H0: xi = 0) | 100.0 % |
| RESET | 15.4 % |
| Leads-Test | 5.4 % |

## Szenario A

Wahrer APE im Mittel: -0.295 pp

| Schätzer                                        |   Mittel |   Bias |   Bias in % |   RMSE |    SD |   mittl. SE |   Abdeckung 95 % |
|:------------------------------------------------|---------:|-------:|------------:|-------:|------:|------------:|-----------------:|
| Paper: lineares Mixed Model, RE Staat + RE Jahr |   -0.062 |  0.234 |      79.134 |  0.241 | 0.058 |       0.019 |            0.200 |
| Lineares Mixed Model, RE Staat + Jahres-FE      |   -0.057 |  0.239 |      80.795 |  0.245 | 0.057 |       0.019 |            0.200 |
| FE-OLS (Staat + Jahr)                           |   -0.048 |  0.248 |      83.870 |  0.254 | 0.055 |       0.044 |            0.600 |
| Gepooltes fraktionales Probit (ohne Means)      |   -1.595 | -1.299 |    -439.922 |  1.307 | 0.144 |       0.137 |            0.000 |
| CRE-Fractional-Probit (Mundlak)                 |   -0.294 |  0.001 |       0.505 |  0.034 | 0.035 |       0.033 |           92.600 |
| CRE-Fractional-Logit (Mundlak)                  |   -0.342 | -0.046 |     -15.744 |  0.061 | 0.039 |       0.038 |           77.400 |

| Test | Ablehnrate bei 5 % |
|---|---|
| Mundlak-Test (H0: xi = 0) | 100.0 % |
| RESET | 16.2 % |
| Leads-Test | 4.8 % |

## Szenario B

Wahrer APE im Mittel: -0.295 pp

| Schätzer                                         |   Mittel |   Bias |   Bias in % |   RMSE |    SD |   mittl. SE |   Abdeckung 95 % |
|:-------------------------------------------------|---------:|-------:|------------:|-------:|------:|------------:|-----------------:|
| Paper: lineares Mixed Model, RE Staat + RE Jahr  |   -0.815 | -0.520 |    -176.519 |  0.523 | 0.059 |       0.046 |            0.000 |
| Lineares Mixed Model, RE Staat + Jahres-FE       |   -0.779 | -0.484 |    -164.196 |  0.487 | 0.057 |       0.045 |            0.000 |
| FE-OLS (Staat + Jahr)                            |   -0.761 | -0.467 |    -158.350 |  0.470 | 0.057 |       0.058 |            0.000 |
| Gepooltes fraktionales Probit (ohne Means)       |   -1.658 | -1.363 |    -462.595 |  1.385 | 0.243 |       0.238 |            0.000 |
| CRE-Fractional-Probit (Mundlak)                  |   -0.770 | -0.475 |    -161.117 |  0.478 | 0.056 |       0.053 |            0.000 |
| CRE-Fractional-Logit (Mundlak)                   |   -0.773 | -0.478 |    -162.138 |  0.481 | 0.057 |       0.054 |            0.000 |
| CRE-FP + Kontrollfunktion (mit Mean der Steuer)  |   -0.295 | -0.000 |      -0.143 |  0.092 | 0.092 |       0.072 |           86.000 |
| CRE-FP + Kontrollfunktion (ohne Mean der Steuer) |   -0.297 | -0.003 |      -0.922 |  0.092 | 0.092 |     nan     |          nan     |
| FE-2SLS (Staat + Jahr)                           |   -0.292 |  0.003 |       0.976 |  0.094 | 0.094 |       0.090 |           93.800 |

| Test | Ablehnrate bei 5 % |
|---|---|
| Mundlak-Test (H0: xi = 0) | 94.6 % |
| RESET | 16.8 % |
| Leads-Test | 40.6 % |
| Exogenitätstest Kontrollfunktion | 100.0 % |
| Erste Stufe: mittlerer cluster-robuster F-Wert | 358.3 |
