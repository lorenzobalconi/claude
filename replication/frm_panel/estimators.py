"""Schätzer für Anteilswerte in einem Bundesstaat-Jahr-Panel.

Enthält
- das lineare Mixed Model aus Sharbaugh et al. (2018) (Random Effects für Staat und Jahr),
- lineare Benchmarks (Two-way-FE-OLS, FE-2SLS),
- das gepoolte und das CRE-Fractional-Probit (Bernoulli-QMLE, Papke & Wooldridge 2008),
- die Kontrollfunktion für einen endogenen Regressor (Papke & Wooldridge 2008, Abschnitt 4),
- APEs mit Delta-Methode, Panel-Bootstrap und die Spezifikationstests (Mundlak, Leads, RESET).

Konventionen: ``y`` ist ein Anteil in [0, 1]. ``unit`` und ``time`` benennen Staat und Jahr.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import statsmodels.api as sm
from linearmodels.iv import IV2SLS
from linearmodels.panel import PanelOLS
from scipy import stats

# --------------------------------------------------------------------------- Hilfsfunktionen


def add_mundlak(df: pd.DataFrame, cols: list[str], unit: str = "state", prefix: str = "m_") -> pd.DataFrame:
    """Hängt die zeitlichen Mittelwerte (Mundlak-Means) der Spalten ``cols`` je Einheit an."""
    out = df.copy()
    for c in cols:
        out[prefix + c] = out.groupby(unit)[c].transform("mean")
    return out


def year_dummies(df: pd.DataFrame, time: str = "year") -> pd.DataFrame:
    return pd.get_dummies(df[time], prefix="yr", drop_first=True, dtype=float)


def design(df: pd.DataFrame, cols: list[str], time: str | None = "year", const: bool = True) -> pd.DataFrame:
    """Designmatrix aus Spalten, optional Konstante und Jahresdummies."""
    X = df[cols].astype(float).copy()
    if time is not None:
        X = pd.concat([X, year_dummies(df, time)], axis=1)
    if const:
        X.insert(0, "const", 1.0)
    return X


def wald(params: pd.Series, cov: pd.DataFrame, names: list[str]) -> dict:
    """Wald-Test H0: alle Koeffizienten in ``names`` sind null (mit der übergebenen, z. B. cluster-robusten Kovarianz)."""
    b = params[names].to_numpy()
    V = cov.loc[names, names].to_numpy()
    chi2 = float(b @ np.linalg.solve(V, b))
    return {"chi2": chi2, "df": len(names), "p": float(stats.chi2.sf(chi2, len(names)))}


def _link_parts(eta: np.ndarray, link: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """G(eta), g(eta) = G'(eta) und g'(eta) für Probit oder Logit."""
    if link == "probit":
        G = stats.norm.cdf(eta)
        g = stats.norm.pdf(eta)
        dg = -eta * g
    elif link == "logit":
        G = 1.0 / (1.0 + np.exp(-eta))
        g = G * (1.0 - G)
        dg = g * (1.0 - 2.0 * G)
    else:
        raise ValueError(link)
    return G, g, dg


# --------------------------------------------------------------------------- Fractional Response (QMLE)


@dataclass
class FracResult:
    res: object                     # statsmodels GLMResults
    X: pd.DataFrame
    link: str
    groups: np.ndarray
    extra: dict = field(default_factory=dict)

    @property
    def params(self) -> pd.Series:
        return self.res.params

    @property
    def cov(self) -> pd.DataFrame:
        return self.res.cov_params()


def frac_glm(y, X: pd.DataFrame, groups, link: str = "probit", weights=None) -> FracResult:
    """Bernoulli-QMLE (fraktionales Probit/Logit) mit cluster-robuster Sandwich-Kovarianz.

    ``weights`` (z. B. Zellgrößen n_it) machen daraus den Binomial-QMLE (W02 §19.3.2).
    """
    lk = sm.families.links.Probit() if link == "probit" else sm.families.links.Logit()
    fam = sm.families.Binomial(link=lk)
    mod = sm.GLM(np.asarray(y, float), X, family=fam, var_weights=None if weights is None else np.asarray(weights, float))
    res = mod.fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(np.asarray(groups))[0]}, maxiter=200)
    return FracResult(res=res, X=X, link=link, groups=np.asarray(groups))


def ape(fr: FracResult, var: str, avg_weights=None) -> dict:
    """Durchschnittlicher Partialeffekt eines stetigen Regressors, gemittelt über alle i und t (Gl. 5.3).

    Delta-Methode mit der Kovarianz aus ``fr`` (cluster-robust). Alle anderen Spalten, also auch
    Mundlak-Means und eine Kontrollfunktion, bleiben fest.
    """
    X = fr.X.to_numpy(float)
    b = fr.params.to_numpy()
    j = list(fr.X.columns).index(var)
    eta = X @ b
    _, g, dg = _link_parts(eta, fr.link)
    w = np.ones(len(eta)) if avg_weights is None else np.asarray(avg_weights, float)
    w = w / w.sum()
    est = b[j] * np.sum(w * g)
    grad = b[j] * (w * dg) @ X
    grad[j] += np.sum(w * g)
    se = float(np.sqrt(grad @ fr.cov.to_numpy() @ grad))
    return {"ape": float(est), "se": se}


def ape_discrete(fr: FracResult, var: str, avg_weights=None) -> float:
    """APE einer 0/1-Variable als Differenz der Average Structural Function (Gl. 5.4)."""
    X1 = fr.X.copy()
    X0 = fr.X.copy()
    X1[var] = 1.0
    X0[var] = 0.0
    b = fr.params.to_numpy()
    G1, _, _ = _link_parts(X1.to_numpy(float) @ b, fr.link)
    G0, _, _ = _link_parts(X0.to_numpy(float) @ b, fr.link)
    w = np.ones(len(G1)) if avg_weights is None else np.asarray(avg_weights, float)
    return float(np.sum(w * (G1 - G0)) / w.sum())


def pooled_fp(df, y, xs, unit="state", time="year", link="probit", weights=None) -> FracResult:
    """Gepooltes fraktionales Probit mit Jahresdummies, ohne Heterogenitätskontrolle."""
    X = design(df, xs, time)
    return frac_glm(df[y], X, df[unit], link, None if weights is None else df[weights])


def cre_fp(df, y, xs, unit="state", time="year", link="probit", weights=None,
           mean_cols: list[str] | None = None, extra_cols: list[str] | None = None) -> FracResult:
    """CRE-Fractional-Probit: x_it, Mundlak-Means aller zeitvariablen Regressoren, Jahresdummies (Gl. 4.4)."""
    mean_cols = xs if mean_cols is None else mean_cols
    d = add_mundlak(df, mean_cols, unit)
    cols = xs + ["m_" + c for c in mean_cols] + (extra_cols or [])
    X = design(d, cols, time)
    fr = frac_glm(d[y], X, d[unit], link, None if weights is None else d[weights])
    fr.extra["mundlak"] = wald(fr.params, fr.cov, ["m_" + c for c in mean_cols])
    return fr


def reset_test(fr: FracResult, y, weights=None) -> dict:
    """RESET (Papke & Wooldridge 1996): (x b)^2 und (x b)^3 ergänzen, robust testen."""
    eta = fr.X.to_numpy(float) @ fr.params.to_numpy()
    X = fr.X.copy()
    X["eta2"] = eta ** 2
    X["eta3"] = eta ** 3
    fr2 = frac_glm(y, X, fr.groups, fr.link, weights)
    return wald(fr2.params, fr2.cov, ["eta2", "eta3"])


def leads_test(df, y, xs, lead_vars, unit="state", time="year", link="probit", weights=None) -> dict:
    """Test auf strikte Exogenität (W02 S. 490): Leads ergänzen, Means aus allen T Perioden."""
    d = add_mundlak(df.sort_values([unit, time]), xs, unit)
    for v in lead_vars:
        d["lead_" + v] = d.groupby(unit)[v].shift(-1)
    d = d.dropna(subset=["lead_" + v for v in lead_vars])
    cols = xs + ["m_" + c for c in xs] + ["lead_" + v for v in lead_vars]
    X = design(d, cols, time)
    fr = frac_glm(d[y], X, d[unit], link, None if weights is None else d[weights])
    out = wald(fr.params, fr.cov, ["lead_" + v for v in lead_vars])
    out["coef"] = {v: float(fr.params["lead_" + v]) for v in lead_vars}
    return out


# --------------------------------------------------------------------------- Kontrollfunktion


def cf_cre_fp(df, y, endog, exog_tv, instruments, unit="state", time="year", link="probit",
              weights=None, mean_endog=True) -> FracResult:
    """Kontrollfunktion nach Papke & Wooldridge (2008), Gl. (7.1)–(7.6) im Leitfaden.

    Stufe 1: gepoolte OLS von ``endog`` auf Kontrollen, Instrumente, deren Means und Jahresdummies.
    Stufe 2: CRE-Fractional-Probit mit dem Residuum ``v2hat``. ``mean_endog`` ergänzt den Mean des
    endogenen Regressors (äquivalent zum Mean der Residuen), damit die zeitkonstante Heterogenität
    anders mit ``endog`` korrelieren darf als die zeitvariable.
    """
    z = exog_tv + instruments
    d = add_mundlak(df, z + ([endog] if mean_endog else []), unit)
    Z = design(d, z + ["m_" + c for c in z], time)
    fs = sm.OLS(d[endog].astype(float), Z).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(d[unit])[0]})
    d["v2hat"] = fs.resid
    first = wald(fs.params, fs.cov_params(), instruments)
    first["F"] = first["chi2"] / first["df"]
    cols = [endog] + exog_tv + ["m_" + c for c in z] + (["m_" + endog] if mean_endog else []) + ["v2hat"]
    X = design(d, cols, time)
    fr = frac_glm(d[y], X, d[unit], link, None if weights is None else d[weights])
    fr.extra["first_stage"] = first
    fr.extra["exog_test"] = wald(fr.params, fr.cov, ["v2hat"])
    return fr


# --------------------------------------------------------------------------- Lineare Modelle


def fe_ols(df, y, xs, unit="state", time="year") -> dict:
    """Two-way-FE-OLS mit Cluster-SE nach Staat."""
    d = df.set_index([unit, time])
    res = PanelOLS(d[y], d[xs].astype(float), entity_effects=True, time_effects=True).fit(
        cov_type="clustered", cluster_entity=True)
    return {"params": res.params, "se": res.std_errors, "res": res}


def fe_2sls(df, y, endog, exog_tv, instruments, unit="state", time="year") -> dict:
    """FE-2SLS (Gl. 7.7) über Staats- und Jahresdummies, Cluster-SE nach Staat."""
    dummies = pd.concat([pd.get_dummies(df[unit], prefix="st", drop_first=True, dtype=float),
                         year_dummies(df, time)], axis=1)
    exog = pd.concat([pd.Series(1.0, index=df.index, name="const"), df[exog_tv].astype(float), dummies], axis=1)
    res = IV2SLS(df[y].astype(float), exog, df[[endog]].astype(float), df[instruments].astype(float)).fit(
        cov_type="clustered", clusters=pd.Series(pd.factorize(df[unit])[0], index=df.index))
    return {"params": res.params, "se": res.std_errors, "res": res}


def paper_lmm(df, y, x="tax", unit="state", time="year") -> dict:
    """Spezifikation aus Sharbaugh et al. (2018): y ~ x + (1|Staat) + (1|Jahr), REML, modellbasierte SE."""
    d = df[[y, x, unit, time]].copy()
    d["_one"] = 1
    vc = {"st": f"0 + C({unit})", "yr": f"0 + C({time})"}
    mod = sm.MixedLM.from_formula(f"{y} ~ {x}", groups="_one", re_formula="0", vc_formula=vc, data=d)
    res = mod.fit(reml=True, method=["lbfgs", "bfgs"])
    return {"coef": float(res.params[x]), "se": float(res.bse[x]), "res": res}


def lmm_state_re_year_fe(df, y, x="tax", unit="state", time="year") -> dict:
    """Variante: Random Intercept für den Staat, feste Jahreseffekte."""
    d = df[[y, x, unit, time]].copy()
    res = sm.MixedLM.from_formula(f"{y} ~ {x} + C({time})", groups=unit, data=d).fit(reml=True, method=["lbfgs", "bfgs"])
    return {"coef": float(res.params[x]), "se": float(res.bse[x]), "res": res}


# --------------------------------------------------------------------------- Panel-Bootstrap


def cluster_bootstrap(df: pd.DataFrame, stat_fn, unit="state", B=499, seed=20261008) -> np.ndarray:
    """Zieht ganze Staaten mit Zurücklegen (mit allen Jahren) und wertet ``stat_fn`` aus.

    Gezogene Duplikate erhalten neue IDs, damit Means, Fixed Effects und Cluster korrekt bleiben.
    """
    rng = np.random.default_rng(seed)
    units = df[unit].unique()
    pos = {u: np.flatnonzero(df[unit].to_numpy() == u) for u in units}
    out = []
    for _ in range(B):
        draw = rng.choice(units, size=len(units), replace=True)
        bd = pd.concat([df.iloc[pos[u]].assign(**{unit: k}) for k, u in enumerate(draw)], ignore_index=True)
        try:
            out.append(stat_fn(bd))
        except Exception:  # sehr selten: Nicht-Konvergenz in einer Ziehung
            out.append(np.nan)
    return np.asarray(out, float)
