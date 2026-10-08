"""Daten für die Replikation von Sharbaugh et al. (2018): Download und Aufbau des Staat-Jahr-Panels.

Quellen (alle öffentlich):
- BRFSS-Mikrodaten 2001–2015 (CDC), SAS-Transportdateien:   www.cdc.gov
- Zigarettensteuer und Durchschnittspreis je Packung, "The Tax Burden on Tobacco" (CDC STATE System):
  data.cdc.gov, Datensatz 7nwe-3aj9
- Arbeitslosenquote, Pro-Kopf-Einkommen je Staat und CPI-U:   fred.stlouisfed.org
- optional: Rauchverbote (CDC STATE System, Smokefree Indoor Air) über den Katalog von data.cdc.gov

Variablen wie im Paper: _SMOKER2 (2001–2004) bzw. _SMOKER3 (2005–2015), Codes 1/2 = aktueller Raucher;
Gewicht _FINALWT (bis 2010) bzw. _LLCPWT (ab 2011, Raking); nur Befragte mit Altersangabe (_AGEG5YR 1–13).
"""
from __future__ import annotations

import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

YEARS = list(range(2001, 2016))

# 50 Staaten + DC: FIPS -> Postkürzel
STATES = {1: "AL", 2: "AK", 4: "AZ", 5: "AR", 6: "CA", 8: "CO", 9: "CT", 10: "DE", 11: "DC", 12: "FL",
          13: "GA", 15: "HI", 16: "ID", 17: "IL", 18: "IN", 19: "IA", 20: "KS", 21: "KY", 22: "LA", 23: "ME",
          24: "MD", 25: "MA", 26: "MI", 27: "MN", 28: "MS", 29: "MO", 30: "MT", 31: "NE", 32: "NV", 33: "NH",
          34: "NJ", 35: "NM", 36: "NY", 37: "NC", 38: "ND", 39: "OH", 40: "OK", 41: "OR", 42: "PA", 44: "RI",
          45: "SC", 46: "SD", 47: "TN", 48: "TX", 49: "UT", 50: "VT", 51: "VA", 53: "WA", 54: "WV", 55: "WI",
          56: "WY"}

BRFSS_VARS = ["_STATE", "_SMOKER2", "_SMOKER3", "_FINALWT", "_LLCPWT", "_AGEG5YR", "INCOME2", "SEX",
              "_RACEGR2", "_RACEGR3", "EDUCA", "STOPSMK2"]

TAX_URL = "https://data.cdc.gov/api/views/7nwe-3aj9/rows.csv?accessType=DOWNLOAD"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"


# --------------------------------------------------------------------------- Download


def _fetch(url: str, dest: Path, tries: int = 4) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (replication script)"})
            with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
                while chunk := r.read(1 << 20):
                    f.write(chunk)
            return True
        except Exception as e:  # Netzfehler: mit Backoff erneut versuchen
            if dest.exists():
                dest.unlink()
            if k == tries - 1:
                print(f"  fehlgeschlagen: {url} ({e})", file=sys.stderr)
                return False
            time.sleep(2 ** (k + 1))
    return False


def brfss_urls(year: int) -> list[str]:
    base = f"https://www.cdc.gov/brfss/annual_data/{year}/files/"
    stem = f"LLCP{year}XPT" if year >= 2011 else f"CDBRFS{str(year)[2:]}XPT"
    return [base + stem + ext for ext in (".zip", ".ZIP")]


def download_all(raw: Path) -> None:
    raw.mkdir(parents=True, exist_ok=True)
    for y in YEARS:
        dest = raw / f"brfss_{y}.zip"
        print(f"BRFSS {y} …", flush=True)
        if not any(_fetch(u, dest) for u in brfss_urls(y)):
            print(f"  BRFSS {y} nicht geladen", file=sys.stderr)
    print("Tax Burden on Tobacco …", flush=True)
    _fetch(TAX_URL, raw / "tax_burden.csv")
    print("FRED …", flush=True)
    for fips, ab in STATES.items():
        _fetch(FRED_URL.format(sid=f"{ab}UR"), raw / "fred" / f"{ab}UR.csv")
        _fetch(FRED_URL.format(sid=f"{ab}PCPI"), raw / "fred" / f"{ab}PCPI.csv")
    _fetch(FRED_URL.format(sid="CPIAUCSL"), raw / "fred" / "CPIAUCSL.csv")
    print("Rauchverbote (optional) …", flush=True)
    try:
        _download_smokefree(raw)
    except Exception as e:
        print(f"  Rauchverbote nicht geladen ({e}); die Pipeline läuft ohne diese Kontrolle.", file=sys.stderr)


def _download_smokefree(raw: Path) -> None:
    import json
    url = "https://data.cdc.gov/api/catalog/v1?q=Smokefree%20Indoor%20Air&only=datasets&limit=20"
    with urllib.request.urlopen(url, timeout=60) as r:
        hits = json.load(r)["results"]
    cand = [h["resource"] for h in hits if "legislation" in h["resource"]["name"].lower()
            and "smokefree" in h["resource"]["name"].lower().replace("-", "").replace(" ", "")]
    if not cand:
        raise RuntimeError("kein passender Datensatz im Katalog")
    rid = cand[0]["id"]
    print(f"  Datensatz {rid}: {cand[0]['name']}")
    _fetch(f"https://data.cdc.gov/api/views/{rid}/rows.csv?accessType=DOWNLOAD", raw / "smokefree.csv")


# --------------------------------------------------------------------------- BRFSS-Mikrodaten


def read_brfss_zip(path: Path) -> pd.DataFrame:
    """Liest die benötigten Spalten aus einer BRFSS-XPT-Zip-Datei."""
    import pyreadstat
    with zipfile.ZipFile(path) as z:
        member = next(m for m in z.namelist() if m.strip().upper().endswith(".XPT"))
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "brfss.xpt"
            with z.open(member) as src, open(target, "wb") as dst:
                while chunk := src.read(1 << 22):
                    dst.write(chunk)
            _, meta = pyreadstat.read_xport(str(target), metadataonly=True)
            cols = [c for c in BRFSS_VARS if c in meta.column_names]
            df, _ = pyreadstat.read_xport(str(target), usecols=cols)
    return df


def harmonise(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """Einheitliche Variablen auf Personenebene (Definitionen wie im Paper)."""
    smk = df["_SMOKER2"] if year <= 2004 else df["_SMOKER3"]
    w = df["_FINALWT"] if year <= 2010 else df["_LLCPWT"]
    race = df["_RACEGR2"] if year <= 2012 else df["_RACEGR3"]
    age = df["_AGEG5YR"]
    inc = df["INCOME2"]
    out = pd.DataFrame({
        "fips": df["_STATE"].astype("Int64"),
        "year": year,
        "w": w.astype(float),
        "smoker": np.where(smk.isin([1, 2]), 1.0, np.where(smk.isin([3, 4]), 0.0, np.nan)),
        "age_ok": age.between(1, 13),
        "age_grp": pd.cut(age, [0, 1, 5, 9, 13], labels=["18-24", "25-44", "45-64", "65+"]).astype(object),
        "sex": df["SEX"].map({1: "male", 2: "female"}),
        "inc_grp": pd.cut(inc.where(inc.between(1, 8)), [0, 4, 6, 7, 8],
                          labels=["<25k", "25-50k", "50-75k", "75k+"]).astype(object),
        "race_grp": race.map({1: "white_nh", 2: "black_nh", 5: "hispanic"}),
        "college": np.where(df["EDUCA"] == 6, 1.0, np.where(df["EDUCA"].between(1, 5), 0.0, np.nan)),
        "quit_try": np.where(df["STOPSMK2"] == 1, 1.0, np.where(df["STOPSMK2"] == 2, 0.0, np.nan)),
    })
    out = out[out["fips"].isin(list(STATES)) & out["age_ok"] & out["w"].gt(0)]
    return out.drop(columns="age_ok")


def _wmean(x: pd.Series, w: pd.Series) -> float:
    m = x.notna()
    return float(np.average(x[m], weights=w[m])) if m.any() else np.nan


def aggregate(p: pd.DataFrame) -> pd.DataFrame:
    """Staat-Jahr-Zellen: gewichtete Prävalenz (wie SURVEYFREQ), Teilgruppen, Zusammensetzung, Zellgrößen."""
    rows = []
    for (fips, year), g in p.groupby(["fips", "year"], sort=True):
        s = g[g["smoker"].notna()]
        r = {"fips": int(fips), "year": int(year), "n": len(s), "prev": _wmean(s["smoker"], s["w"])}
        for col, levels in [("age_grp", ["18-24", "25-44", "45-64", "65+"]), ("sex", ["male", "female"]),
                            ("inc_grp", ["<25k", "25-50k", "50-75k", "75k+"]),
                            ("race_grp", ["white_nh", "black_nh", "hispanic"])]:
            for lv in levels:
                sub = s[s[col] == lv]
                r[f"prev_{lv}"] = _wmean(sub["smoker"], sub["w"])
                r[f"n_{lv}"] = len(sub)
        cur = s[s["smoker"] == 1]
        r["quit"] = _wmean(cur["quit_try"], cur["w"])
        r["n_quit"] = int(cur["quit_try"].notna().sum())
        # Zusammensetzung der Stichprobe (gewichtet): Kontrollen gegen Kompositionseffekte
        r["sh_age1824"] = _wmean((s["age_grp"] == "18-24").astype(float), s["w"])
        r["sh_age2544"] = _wmean((s["age_grp"] == "25-44").astype(float), s["w"])
        r["sh_age4564"] = _wmean((s["age_grp"] == "45-64").astype(float), s["w"])
        r["sh_female"] = _wmean((s["sex"] == "female").astype(float), s["w"])
        r["sh_black"] = _wmean((s["race_grp"] == "black_nh").astype(float), s["w"])
        r["sh_hisp"] = _wmean((s["race_grp"] == "hispanic").astype(float), s["w"])
        r["sh_college"] = _wmean(s["college"], s["w"])
        r["sh_lowinc"] = _wmean((s["inc_grp"] == "<25k").astype(float).where(s["inc_grp"].notna()), s["w"])
        rows.append(r)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- Steuern, FRED, Rauchverbote


def _col(df: pd.DataFrame, name: str) -> str:
    for c in df.columns:
        if c.strip().lower().replace(" ", "") == name:
            return c
    raise KeyError(f"Spalte {name!r} fehlt; vorhanden: {list(df.columns)}")


def read_tax(path: Path) -> pd.DataFrame:
    t = pd.read_csv(path)
    yc, sc, mc, vc = _col(t, "year"), _col(t, "locationabbr"), _col(t, "submeasuredesc"), _col(t, "data_value")
    sub = t[mc].astype(str).str.strip().str.lower()
    pick = {"tax_nom": sub.str.fullmatch(r"state tax per pack"),
            "price_nom": sub.str.fullmatch(r"average cost per pack")}
    out = None
    for name, m in pick.items():
        if not m.any():
            raise KeyError(f"{name}: keine passende SubMeasureDesc; vorhanden: {sorted(sub.unique())}")
        part = t.loc[m, [sc, yc, vc]].rename(columns={sc: "abbr", yc: "year", vc: name})
        part[name] = pd.to_numeric(part[name].astype(str).str.replace(r"[$,]", "", regex=True), errors="coerce")
        part = part.groupby(["abbr", "year"], as_index=False)[name].mean()
        out = part if out is None else out.merge(part, on=["abbr", "year"], how="outer")
    out["year"] = out["year"].astype(int)
    return out


def _fred_annual(path: Path) -> pd.Series:
    f = pd.read_csv(path)
    f.columns = ["date", "value"]
    f["value"] = pd.to_numeric(f["value"], errors="coerce")
    f["year"] = pd.to_datetime(f["date"]).dt.year
    return f.groupby("year")["value"].mean()


def read_fred(raw: Path) -> pd.DataFrame:
    rows = []
    for ab in STATES.values():
        ur = _fred_annual(raw / "fred" / f"{ab}UR.csv")
        pc = _fred_annual(raw / "fred" / f"{ab}PCPI.csv")
        for y in YEARS:
            rows.append({"abbr": ab, "year": y, "unemp": ur.get(y, np.nan), "pcpi_nom": pc.get(y, np.nan)})
    out = pd.DataFrame(rows)
    cpi = _fred_annual(raw / "fred" / "CPIAUCSL.csv")
    out["cpi"] = out["year"].map(cpi)
    return out


def read_smokefree(path: Path) -> pd.DataFrame | None:
    """Anteil der Quartale eines Jahres mit vollständigem Rauchverbot in Arbeitsstätten, Restaurants und Bars."""
    if not path.exists():
        return None
    s = pd.read_csv(path, low_memory=False)
    try:
        yc, qc, sc = _col(s, "year"), _col(s, "quarter"), _col(s, "locationabbr")
        pc, vc = _col(s, "provisiondesc"), _col(s, "provisionvalue")
    except KeyError as e:
        print(f"Rauchverbote: Struktur unerwartet ({e}); Kontrolle wird ausgelassen.", file=sys.stderr)
        return None
    s["venue"] = s[pc].astype(str).str.lower().str.extract(r"(work|restaurant|\bbar)")[0]
    s["banned"] = s[vc].astype(str).str.lower().str.contains("ban")
    s = s.dropna(subset=["venue"])
    q = s.groupby([sc, yc, qc, "venue"])["banned"].max().unstack("venue")
    q["comprehensive"] = q.reindex(columns=["work", "restaurant", "bar"]).fillna(False).all(axis=1).astype(float)
    a = q.groupby(level=[0, 1])["comprehensive"].mean().reset_index()
    a.columns = ["abbr", "year", "smokefree"]
    a["year"] = a["year"].astype(int)
    return a


# --------------------------------------------------------------------------- Panel


def build_panel(raw: Path, out: Path, years=YEARS) -> pd.DataFrame:
    cells = []
    for y in years:
        f = raw / f"brfss_{y}.zip"
        if not f.exists():
            raise FileNotFoundError(f"{f} fehlt. Erst scripts/get_data.py ausführen.")
        print(f"BRFSS {y} einlesen …", flush=True)
        cells.append(aggregate(harmonise(read_brfss_zip(f), y)))
    panel = pd.concat(cells, ignore_index=True)
    panel["abbr"] = panel["fips"].map(STATES)

    panel = panel.merge(read_tax(raw / "tax_burden.csv"), on=["abbr", "year"], how="left")
    panel = panel.merge(read_fred(raw), on=["abbr", "year"], how="left")
    sf = read_smokefree(raw / "smokefree.csv")
    if sf is not None:
        panel = panel.merge(sf, on=["abbr", "year"], how="left")

    cpi15 = panel.loc[panel["year"] == 2015, "cpi"].iloc[0]
    panel["tax_real"] = panel["tax_nom"] * cpi15 / panel["cpi"]        # in Dollar von 2015
    panel["price_real"] = panel["price_nom"] * cpi15 / panel["cpi"]
    panel["ln_pcpi_real"] = np.log(panel["pcpi_nom"] * cpi15 / panel["cpi"])
    panel["prev_pct"] = 100 * panel["prev"]
    panel = panel.rename(columns={"abbr": "state"}).sort_values(["state", "year"]).reset_index(drop=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(out, index=False)
    return panel
