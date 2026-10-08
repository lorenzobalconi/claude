"""Monte-Carlo-Studie: Welche Schätzer treffen den wahren APE der Zigarettensteuer?

Aufruf:  python scripts/monte_carlo.py --reps 500 --workers 4
Ergebnis: results/mc_draws_<Szenario>.csv (je Ziehung) und results/mc_summary.md
Alle Effekte in Prozentpunkten je $0,25 Steuer, wie in Sharbaugh et al. (2018), Tabelle 1.
"""
from __future__ import annotations

import argparse
import os
import sys
import warnings

# Ein BLAS-Thread je Worker: sonst bremsen sich die parallelen Prozesse gegenseitig aus.
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from frm_panel import estimators as E  # noqa: E402
from frm_panel.simulate import simulate_panel  # noqa: E402

PP = 25.0        # Anteil je $1  ->  Prozentpunkte je $0,25
LIN = 0.25       # Prozentpunkte je $1  ->  je $0,25


def one_draw(args):
    seed, scenario = args
    warnings.simplefilter("ignore")
    df, true = simulate_panel(seed, "A", trend=0.0) if scenario == "A0" else simulate_panel(seed, scenario)
    r = {"seed": seed, "true": true * PP}

    m = E.paper_lmm(df, "prev_pct")
    r["paper_lmm"], r["paper_lmm_se"] = m["coef"] * LIN, m["se"] * LIN
    m = E.lmm_state_re_year_fe(df, "prev_pct")
    r["lmm_yearfe"], r["lmm_yearfe_se"] = m["coef"] * LIN, m["se"] * LIN
    m = E.fe_ols(df, "prev_pct", ["tax"])
    r["fe_ols"], r["fe_ols_se"] = m["params"]["tax"] * LIN, m["se"]["tax"] * LIN

    a = E.ape(E.pooled_fp(df, "prev", ["tax"]), "tax")
    r["pooled_fp"], r["pooled_fp_se"] = a["ape"] * PP, a["se"] * PP
    fr = E.cre_fp(df, "prev", ["tax"])
    a = E.ape(fr, "tax")
    r["cre_fp"], r["cre_fp_se"] = a["ape"] * PP, a["se"] * PP
    r["mundlak_p"] = fr.extra["mundlak"]["p"]
    r["reset_p"] = E.reset_test(fr, df["prev"])["p"]
    r["leads_p"] = E.leads_test(df, "prev", ["tax"], ["tax"])["p"]
    a = E.ape(E.cre_fp(df, "prev", ["tax"], link="logit"), "tax")
    r["cre_flogit"], r["cre_flogit_se"] = a["ape"] * PP, a["se"] * PP

    if scenario == "B":
        cf = E.cf_cre_fp(df, "prev", "tax", [], ["q"], mean_endog=True)
        a = E.ape(cf, "tax")
        r["cf_cre_fp"], r["cf_cre_fp_se_naive"] = a["ape"] * PP, a["se"] * PP
        r["exog_p"] = cf.extra["exog_test"]["p"]
        r["first_F"] = cf.extra["first_stage"]["F"]
        cf0 = E.cf_cre_fp(df, "prev", "tax", [], ["q"], mean_endog=False)
        r["cf_nomean"] = E.ape(cf0, "tax")["ape"] * PP
        m = E.fe_2sls(df, "prev_pct", "tax", [], ["q"])
        r["fe_2sls"], r["fe_2sls_se"] = m["params"]["tax"] * LIN, m["se"]["tax"] * LIN
    return r


LABELS = {
    "paper_lmm": "Paper: lineares Mixed Model, RE Staat + RE Jahr",
    "lmm_yearfe": "Lineares Mixed Model, RE Staat + Jahres-FE",
    "fe_ols": "FE-OLS (Staat + Jahr)",
    "pooled_fp": "Gepooltes fraktionales Probit (ohne Means)",
    "cre_fp": "CRE-Fractional-Probit (Mundlak)",
    "cre_flogit": "CRE-Fractional-Logit (Mundlak)",
    "cf_cre_fp": "CRE-FP + Kontrollfunktion (mit Mean der Steuer)",
    "cf_nomean": "CRE-FP + Kontrollfunktion (ohne Mean der Steuer)",
    "fe_2sls": "FE-2SLS (Staat + Jahr)",
}


def summarise(d: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for k, lab in LABELS.items():
        if k not in d:
            continue
        bias = d[k] - d["true"]
        row = {"Schätzer": lab, "Mittel": d[k].mean(), "Bias": bias.mean(),
               "Bias in %": 100 * bias.mean() / d["true"].abs().mean(),
               "RMSE": np.sqrt((bias ** 2).mean()), "SD": d[k].std()}
        se = k + "_se" if k + "_se" in d else (k + "_se_naive" if k + "_se_naive" in d else None)
        if se:
            row["mittl. SE"] = d[se].mean()
            row["Abdeckung 95 %"] = 100 * ((d[k] - 1.96 * d[se] <= d["true"]) & (d["true"] <= d[k] + 1.96 * d[se])).mean()
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=500)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "results"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    lines = ["# Monte-Carlo-Ergebnisse", "",
             f"{a.reps} Ziehungen je Szenario, N = 51 Staaten, T = 15 Jahre. "
             "Effekte in Prozentpunkten je $0,25 Steuer.", ""]
    for sc in ["A0", "A", "B"]:
        with Pool(a.workers) as pool:
            draws = pd.DataFrame(pool.map(one_draw, [(s, sc) for s in range(1, a.reps + 1)]))
        draws.to_csv(out / f"mc_draws_{sc}.csv", index=False)
        summ = summarise(draws)
        lines += [f"## Szenario {sc}", "", f"Wahrer APE im Mittel: {draws['true'].mean():.3f} pp", "",
                  summ.to_markdown(index=False, floatfmt=".3f"), ""]
        tests = {"Mundlak-Test (H0: xi = 0)": "mundlak_p", "RESET": "reset_p", "Leads-Test": "leads_p",
                 "Exogenitätstest Kontrollfunktion": "exog_p"}
        lines.append("| Test | Ablehnrate bei 5 % |")
        lines.append("|---|---|")
        for lab, col in tests.items():
            if col in draws:
                lines.append(f"| {lab} | {100 * (draws[col] < 0.05).mean():.1f} % |")
        if "first_F" in draws:
            lines.append(f"| Erste Stufe: mittlerer cluster-robuster F-Wert | {draws['first_F'].mean():.1f} |")
        lines.append("")
        print(f"Szenario {sc} fertig", flush=True)
    (out / "mc_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
