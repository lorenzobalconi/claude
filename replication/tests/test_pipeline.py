"""Tests der Pipeline ohne Netzzugang: synthetische BRFSS-Dateien und simulierte Panels."""
import subprocess
import sys
import warnings
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from frm_panel import data as D  # noqa: E402
from frm_panel import estimators as E  # noqa: E402
from frm_panel.simulate import simulate_panel  # noqa: E402

warnings.simplefilter("ignore")


def fake_brfss(year: int, n: int = 4000, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed + year)
    smk_col = "_SMOKER2" if year <= 2004 else "_SMOKER3"
    w_col = "_FINALWT" if year <= 2010 else "_LLCPWT"
    race_col = "_RACEGR2" if year <= 2012 else "_RACEGR3"
    return pd.DataFrame({
        "_STATE": rng.choice([1, 6, 36, 72], n).astype(float),       # 72 = Puerto Rico, wird verworfen
        smk_col: rng.choice([1, 2, 3, 4, 9], n, p=[.12, .05, .25, .55, .03]).astype(float),
        w_col: rng.uniform(50, 500, n),
        "_AGEG5YR": rng.choice(np.arange(1, 15), n).astype(float),     # 14 = fehlend, wird verworfen
        "INCOME2": rng.choice([1, 3, 5, 6, 7, 8, 77, 99], n).astype(float),
        "SEX": rng.choice([1, 2], n).astype(float),
        race_col: rng.choice([1, 2, 3, 5, 9], n).astype(float),
        "EDUCA": rng.choice([1, 2, 3, 4, 5, 6, 9], n).astype(float),
        "STOPSMK2": rng.choice([1, 2, 7, np.nan], n).astype(float),
    })


@pytest.mark.parametrize("year", [2003, 2008, 2014])
def test_brfss_roundtrip_and_weighted_prevalence(tmp_path, year):
    import pyreadstat
    raw = fake_brfss(year)
    xpt = tmp_path / f"LLCP{year}.XPT"
    pyreadstat.write_xport(raw, str(xpt), file_format_version=5)
    zp = tmp_path / f"brfss_{year}.zip"
    with zipfile.ZipFile(zp, "w") as z:
        z.write(xpt, arcname=f"LLCP{year}.XPT ")                      # CDC-Dateinamen enden teils mit Leerzeichen
    cells = D.aggregate(D.harmonise(D.read_brfss_zip(zp), year))

    smk = raw["_SMOKER2" if year <= 2004 else "_SMOKER3"]
    w = raw["_FINALWT" if year <= 2010 else "_LLCPWT"]
    keep = raw["_STATE"].eq(36) & raw["_AGEG5YR"].between(1, 13) & smk.isin([1, 2, 3, 4])
    expected = np.average(smk[keep].isin([1, 2]), weights=w[keep])
    got = cells.loc[cells["fips"] == 36, "prev"].item()
    assert abs(got - expected) < 1e-12
    assert set(cells["fips"]) == {1, 6, 36}
    assert cells.loc[cells["fips"] == 36, "n"].item() == keep.sum()


def test_mundlak_pols_equals_fe():
    df, _ = simulate_panel(3, "A")
    d = E.add_mundlak(df, ["tax"])
    import statsmodels.api as sm
    pols = sm.OLS(d["prev_pct"], E.design(d, ["tax", "m_tax"])).fit()
    fe = E.fe_ols(df, "prev_pct", ["tax"])
    assert abs(pols.params["tax"] - fe["params"]["tax"]) < 1e-8


def test_ape_delta_gradient_matches_numeric():
    df, _ = simulate_panel(4, "A")
    fr = E.cre_fp(df, "prev", ["tax"])
    base = E.ape(fr, "tax")["ape"]
    X, b = fr.X.to_numpy(float), fr.params.to_numpy()
    from scipy import stats
    j = list(fr.X.columns).index("tax")
    num = []
    for k in range(len(b)):
        bb = b.copy()
        bb[k] += 1e-6
        num.append((bb[j] * stats.norm.pdf(X @ bb).mean() - base) / 1e-6)
    eta = X @ b
    g = stats.norm.pdf(eta)
    grad = b[j] * (-eta * g) @ X / len(eta)
    grad[j] += g.mean()
    assert np.allclose(grad, num, rtol=1e-3, atol=1e-6)


def test_cre_fp_recovers_true_ape_in_large_panel():
    df, true = simulate_panel(5, "A", N=1500)
    est = E.ape(E.cre_fp(df, "prev", ["tax"]), "tax")["ape"]
    assert abs(est - true) / abs(true) < 0.05


def test_run_replication_on_synthetic_panel(tmp_path):
    df, _ = simulate_panel(6, "B")
    rng = np.random.default_rng(6)
    p = df.rename(columns={"tax": "tax_nom"}).copy()
    p["state"] = "S" + p["state"].astype(str)
    p["tax_real"] = p["tax_nom"] * (1 + 0.02 * (2015 - p["year"]))
    for c in ["unemp", "ln_pcpi_real", "sh_age1824", "sh_age2544", "sh_age4564", "sh_female", "sh_black",
              "sh_hisp", "sh_college", "sh_lowinc", "smokefree"]:
        p[c] = rng.uniform(0, 1, len(p))
    for g in ["18-24", "25-44", "45-64", "65+", "male", "female", "<25k", "25-50k", "50-75k", "75k+",
              "white_nh", "black_nh", "hispanic"]:
        p[f"prev_{g}"] = np.clip(p["prev"] + rng.normal(0, 0.02, len(p)), 0, 1)
        p[f"n_{g}"] = 300
    p["quit"] = rng.uniform(0.4, 0.7, len(p))
    p["n_quit"] = 400
    panel = tmp_path / "panel.csv"
    p.to_csv(panel, index=False)
    p[["state", "year", "q"]].to_csv(tmp_path / "iv.csv", index=False)
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "run_replication.py"), "--panel", str(panel),
                        "--instruments", str(tmp_path / "iv.csv"), "--boot", "5", "--out", str(tmp_path)],
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-3000:]
    out = pd.read_csv(tmp_path / "replication_main.csv")
    assert len(out) == 14 and out["Effekt"].notna().all()
    assert len(pd.read_csv(tmp_path / "replication_groups.csv")) == 14
