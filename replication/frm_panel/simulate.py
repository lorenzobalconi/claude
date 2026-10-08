"""Datengenerator für ein BRFSS-artiges Bundesstaat-Jahr-Panel mit bekanntem wahren APE.

Strukturmodell (beide Szenarien):
    Prävalenz p_it = Phi(mu + delta_t + beta * tax_it + c_i + u_it)
    beobachtet:      y_it = Binomial(n_it / deff, p_it) / (n_it / deff)   (Survey-Stichprobenrauschen)
    Staatseffekt:    c_i  = -0.25 * (mean_t tax_it - Gesamtmittel) + a_i,  a_i ~ N(0, 0.12^2)
                     -> Staaten mit dauerhaft niedriger Steuer rauchen mehr (Mundlak-Struktur erfüllt)
    Jahreseffekte:   nationaler Abwärtstrend + Niveausprung 2011 (BRFSS-Methodenwechsel)

Szenario "A": Steuerpfade aus diskreten Erhöhungen, unabhängig von u_it (strikt exogen gegeben c_i).
Szenario "B": Zusätzlich zeitvariable Endogenität. Eine unbeobachtete Anti-Rauch-Stimmung s_it senkt
die Prävalenz (über u_it) und erhöht gleichzeitig die Steuer. Ein Instrument q_it (z. B. fiskalischer
Druck) verschiebt nur die Steuer.

Kalibrierung nach Sharbaugh et al. (2018): Prävalenz 2001 etwa 13–31 %, Steuern 2001 etwa
$0,03–1,11 und 2015 etwa $0,17–4,35 pro Packung.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def _ar1(rng, n_units, T, rho, sd):
    e = np.empty((n_units, T))
    e[:, 0] = rng.normal(0, sd, n_units)
    innov_sd = sd * np.sqrt(1 - rho ** 2)
    for t in range(1, T):
        e[:, t] = rho * e[:, t - 1] + rng.normal(0, innov_sd, n_units)
    return e


def _tax_paths_discrete(rng, N, T):
    base = 0.03 + rng.gamma(1.5, 0.27, N)
    propensity = (base - base.mean()) / base.std() + rng.normal(0, 1, N)
    tax = np.repeat(base[:, None], T, axis=1)
    for i in range(N):
        k = min(rng.poisson(2.6), T - 1)
        for t0 in rng.choice(np.arange(1, T), size=k, replace=False):
            tax[i, t0:] += rng.gamma(2.0, 0.2) * np.exp(0.4 * propensity[i])
    return tax


def simulate_panel(seed: int, scenario: str = "A", N: int = 51, T: int = 15, beta: float = -0.045,
                   deff: float = 1.6, trend: float = -0.015) -> tuple[pd.DataFrame, float]:
    """Gibt (Panel, wahrer APE je $1 Steuer in Anteilseinheiten) zurück.

    ``trend`` ist der nationale Jahrestrend im Probit-Index (Standard: Rückgang wie 2001–2015).
    """
    rng = np.random.default_rng(seed)
    years = np.arange(2001, 2001 + T)
    delta = trend * np.arange(T) + 0.04 * (years >= 2011) * (trend != 0) + rng.normal(0, 0.01, T)

    if scenario == "A":
        tax = _tax_paths_discrete(rng, N, T)
        u = _ar1(rng, N, T, 0.6, 0.03)
        q = np.zeros((N, T))
    elif scenario == "B":
        base = 0.03 + rng.gamma(1.5, 0.27, N)
        s = _ar1(rng, N, T, 0.7, 1.0)                              # unbeobachtete Anti-Rauch-Stimmung
        q = _ar1(rng, N, T, 0.5, 1.0)                              # Instrument
        tax = (base[:, None] + 0.07 * np.arange(T)[None, :] + 0.15 * q + 0.15 * s
               + rng.normal(0, 0.10, (N, T)))
        tax = np.clip(tax, 0.02, None)
        u = -0.03 * s + _ar1(rng, N, T, 0.6, 0.02)
    else:
        raise ValueError(scenario)

    xbar = tax.mean(axis=1)
    c = -0.25 * (xbar - xbar.mean()) + rng.normal(0, 0.12, N)

    eta = -0.78 + delta[None, :] + beta * tax + c[:, None] + u
    p = stats.norm.cdf(eta)
    n = rng.integers(2000, 12001, (N, T))
    n_eff = np.maximum((n / deff).astype(int), 1)
    y = rng.binomial(n_eff, p) / n_eff
    true_ape = float(np.mean(beta * stats.norm.pdf(eta)))

    df = pd.DataFrame({
        "state": np.repeat(np.arange(N), T),
        "year": np.tile(years, N),
        "tax": tax.ravel(),
        "q": q.ravel(),
        "n": n.ravel(),
        "prev": y.ravel(),
    })
    df["prev_pct"] = 100 * df["prev"]
    return df, true_ape
