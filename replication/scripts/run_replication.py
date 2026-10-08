"""Replikation und Erweiterung von Sharbaugh et al. (2018) mit einem Fractional Response Model.

Aufruf:  python scripts/run_replication.py --panel data/final/panel_state_year_2001_2015.csv --boot 499
Optional: --instruments data/raw/instruments.csv  (Spalten state, year und Instrumente für die Steuer)
Ergebnis: results/replication.md und results/replication_*.csv

Alle Effekte in Prozentpunkten je $0,25 Steuer pro Packung, wie in Tabelle 1 des Papers.
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from frm_panel import estimators as E  # noqa: E402

PP, LIN = 25.0, 0.25
BASE_CONTROLS = ["unemp", "ln_pcpi_real", "sh_age1824", "sh_age2544", "sh_age4564", "sh_female",
                 "sh_black", "sh_hisp", "sh_college", "sh_lowinc"]
GROUPS = {"Alter 18–24": "age1824", "Alter 25–44": "age2544", "Alter 45–64": "age4564", "Alter 65+": "age65p",
          "Männer": "male", "Frauen": "female",
          "Einkommen < $25k": "inc_lt25k", "Einkommen $25–50k": "inc_25_50k", "Einkommen $50–75k": "inc_50_75k",
          "Einkommen ≥ $75k": "inc_ge75k",
          "Weiß, nicht hispanisch": "white_nh", "Schwarz, nicht hispanisch": "black_nh", "Hispanisch": "hisp"}


def controls_for(panel: pd.DataFrame) -> list[str]:
    c = [v for v in BASE_CONTROLS if v in panel and panel[v].notna().all()]
    if "smokefree" in panel and panel["smokefree"].notna().mean() > 0.95:
        c.append("smokefree")
    return c


def row(label, est, se=None, boot_se=None, note=""):
    r = {"Spezifikation": label, "Effekt": est, "SE": se, "SE Bootstrap": boot_se}
    s = boot_se if boot_se is not None else se
    if s is not None:
        r["95%-KI"] = f"[{est - 1.96 * s:.2f}; {est + 1.96 * s:.2f}]"
    r["Anmerkung"] = note
    return r


def cre_ape_stat(y, x, ctrls, weights=None, link="probit"):
    def f(d):
        d = d.dropna(subset=[y, x] + ctrls)
        fr = E.cre_fp(d, y, [x] + ctrls, link=link, weights=weights)
        return E.ape(fr, x)["ape"] * PP
    return f


def main_table(p: pd.DataFrame, B: int, inst: list[str]) -> tuple[pd.DataFrame, list[str]]:
    ctrl = controls_for(p)
    rows, notes = [], []

    m = E.paper_lmm(p, "prev_pct", "tax_nom")
    rows.append(row("(1) Paper: LMM, RE Staat + RE Jahr, nominale Steuer", m["coef"] * LIN, m["se"] * LIN,
                    note="Replikationsziel: −0,60 [−0,66; −0,55]; modellbasierte SE"))
    m = E.paper_lmm(p, "prev_pct", "tax_real")
    rows.append(row("(2) wie (1), reale Steuer (Dollar von 2015)", m["coef"] * LIN, m["se"] * LIN))
    m = E.lmm_state_re_year_fe(p, "prev_pct", "tax_real")
    rows.append(row("(3) LMM, RE Staat + Jahres-FE, reale Steuer", m["coef"] * LIN, m["se"] * LIN))
    m = E.fe_ols(p, "prev_pct", ["tax_real"])
    rows.append(row("(4) FE-OLS (Staat + Jahr), reale Steuer", m["params"]["tax_real"] * LIN,
                    m["se"]["tax_real"] * LIN, note="Cluster-SE nach Staat"))
    m = E.fe_ols(p.dropna(subset=ctrl), "prev_pct", ["tax_real"] + ctrl)
    rows.append(row("(5) FE-OLS + Kontrollen", m["params"]["tax_real"] * LIN, m["se"]["tax_real"] * LIN))

    a = E.ape(E.pooled_fp(p, "prev", ["tax_real"]), "tax_real")
    rows.append(row("(6) Gepooltes fraktionales Probit, Jahres-FE", a["ape"] * PP, a["se"] * PP,
                    note="APE; ignoriert Staatseffekte"))

    fr = E.cre_fp(p, "prev", ["tax_real"])
    a = E.ape(fr, "tax_real")
    bs = E.cluster_bootstrap(p, cre_ape_stat("prev", "tax_real", []), B=B)
    rows.append(row("(7) CRE-Fractional-Probit (Mundlak), Jahres-FE", a["ape"] * PP, a["se"] * PP, np.nanstd(bs),
                    note=f"Mundlak-Test p = {fr.extra['mundlak']['p']:.3g}"))

    pc = p.dropna(subset=ctrl)
    frc = E.cre_fp(pc, "prev", ["tax_real"] + ctrl)
    a = E.ape(frc, "tax_real")
    bs = E.cluster_bootstrap(pc, cre_ape_stat("prev", "tax_real", ctrl), B=B)
    rows.append(row("(8) CRE-FP + Kontrollen (Hauptspezifikation)", a["ape"] * PP, a["se"] * PP, np.nanstd(bs),
                    note=f"Mundlak-Test p = {frc.extra['mundlak']['p']:.3g}"))

    frw = E.cre_fp(pc, "prev", ["tax_real"] + ctrl, weights="n")
    a = E.ape(frw, "tax_real")
    rows.append(row("(9) wie (8), gewichtet mit Zellgröße (Binomial-QMLE)", a["ape"] * PP, a["se"] * PP))
    a = E.ape(E.cre_fp(pc, "prev", ["tax_real"] + ctrl, link="logit"), "tax_real")
    rows.append(row("(10) wie (8), Logit-Link", a["ape"] * PP, a["se"] * PP))
    a = E.ape(E.cre_fp(pc, "prev", ["tax_nom"] + ctrl), "tax_nom")
    rows.append(row("(11) wie (8), nominale Steuer", a["ape"] * PP, a["se"] * PP))

    pl = pc.sort_values(["state", "year"]).copy()
    pl["tax_lag"] = pl.groupby("state")["tax_real"].shift(1)
    pl = pl.dropna(subset=["tax_lag"])
    a = E.ape(E.cre_fp(pl, "prev", ["tax_lag"] + ctrl), "tax_lag")
    rows.append(row("(12) wie (8), Steuer des Vorjahres", a["ape"] * PP, a["se"] * PP,
                    note="Timing der Steuerdaten"))

    if inst:
        pi = pc.dropna(subset=inst)
        cf = E.cf_cre_fp(pi, "prev", "tax_real", ctrl, inst, mean_endog=True)
        a = E.ape(cf, "tax_real")

        def cf_stat(d):
            return E.ape(E.cf_cre_fp(d, "prev", "tax_real", ctrl, inst, mean_endog=True), "tax_real")["ape"] * PP
        bs = E.cluster_bootstrap(pi, cf_stat, B=B)
        fs, ex = cf.extra["first_stage"], cf.extra["exog_test"]
        rows.append(row("(13) CRE-FP + Kontrollfunktion", a["ape"] * PP, None, np.nanstd(bs),
                        note=f"F erste Stufe = {fs['F']:.1f}; Exogenitätstest p = {ex['p']:.3g}"))
        iv = E.fe_2sls(pi, "prev_pct", "tax_real", ctrl, inst)
        rows.append(row("(14) FE-2SLS", iv["params"]["tax_real"] * LIN, iv["se"]["tax_real"] * LIN))

    reset = E.reset_test(frc, pc["prev"])
    leads = E.leads_test(pc, "prev", ["tax_real"] + ctrl, ["tax_real"])
    notes += [f"Mundlak-Test in (8): χ²({frc.extra['mundlak']['df']}) = {frc.extra['mundlak']['chi2']:.2f}, "
              f"p = {frc.extra['mundlak']['p']:.3g}",
              f"RESET in (8): χ²(2) = {reset['chi2']:.2f}, p = {reset['p']:.3g}",
              f"Leads-Test (Steuer t+1) in (8): χ²(1) = {leads['chi2']:.2f}, p = {leads['p']:.3g}",
              f"Kontrollen: {', '.join(ctrl)}"]
    return pd.DataFrame(rows), notes


def group_table(p: pd.DataFrame, B: int) -> pd.DataFrame:
    ctrl = controls_for(p)
    out = []
    for lab, g in GROUPS.items():
        y = f"prev_{g}"
        d = p.dropna(subset=[y] + ctrl).copy()
        d["y_pct"] = 100 * d[y]
        m = E.paper_lmm(d, "y_pct", "tax_nom")
        fr = E.cre_fp(d, y, ["tax_real"] + ctrl)
        a = E.ape(fr, "tax_real")
        bs = E.cluster_bootstrap(d, cre_ape_stat(y, "tax_real", ctrl), B=B)
        out.append({"Gruppe": lab, "Paper-LMM": m["coef"] * LIN, "Paper-LMM SE": m["se"] * LIN,
                    "CRE-FP APE": a["ape"] * PP, "CRE-FP SE (Bootstrap)": np.nanstd(bs),
                    "mittl. Zellgröße": d[f"n_{g}"].mean()})
    d = p.dropna(subset=["quit"] + ctrl).copy()
    d["y_pct"] = 100 * d["quit"]
    m = E.paper_lmm(d, "y_pct", "tax_nom")
    a = E.ape(E.cre_fp(d, "quit", ["tax_real"] + ctrl), "tax_real")
    bs = E.cluster_bootstrap(d, cre_ape_stat("quit", "tax_real", ctrl), B=B)
    out.append({"Gruppe": "Aufhörversuch (Raucher)", "Paper-LMM": m["coef"] * LIN, "Paper-LMM SE": m["se"] * LIN,
                "CRE-FP APE": a["ape"] * PP, "CRE-FP SE (Bootstrap)": np.nanstd(bs),
                "mittl. Zellgröße": d["n_quit"].mean()})
    return pd.DataFrame(out)


def main():
    ap = argparse.ArgumentParser()
    root = Path(__file__).resolve().parents[1]
    ap.add_argument("--panel", default=str(root / "data" / "final" / "panel_state_year_2001_2015.csv"))
    ap.add_argument("--instruments", default=None)
    ap.add_argument("--boot", type=int, default=499)
    ap.add_argument("--out", default=str(root / "results"))
    ap.add_argument("--skip-groups", action="store_true")
    a = ap.parse_args()
    warnings.simplefilter("ignore")

    p = pd.read_csv(a.panel)
    inst = []
    if a.instruments:
        iv = pd.read_csv(a.instruments)
        inst = [c for c in iv.columns if c not in ("state", "year")]
        p = p.drop(columns=[c for c in inst if c in p]).merge(iv, on=["state", "year"], how="left")

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tab, notes = main_table(p, a.boot, inst)
    tab.to_csv(out / "replication_main.csv", index=False)
    lines = ["# Replikation Sharbaugh et al. (2018) mit Fractional Response Model", "",
             f"Panel: {p['state'].nunique()} Staaten × {p['year'].nunique()} Jahre "
             f"({p['year'].min()}–{p['year'].max()}). Effekte in Prozentpunkten je $0,25 pro Packung.", "",
             "## Hauptergebnis", "", tab.to_markdown(index=False, floatfmt=".3f"), ""]
    lines += [f"- {n}" for n in notes] + [""]
    if not a.skip_groups:
        g = group_table(p, a.boot)
        g.to_csv(out / "replication_groups.csv", index=False)
        lines += ["## Teilgruppen (vgl. Tabelle 1 des Papers)", "", g.to_markdown(index=False, floatfmt=".3f"), ""]
    (out / "replication.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
