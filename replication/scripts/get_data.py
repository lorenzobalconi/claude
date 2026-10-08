"""Lädt alle Rohdaten nach data/raw (BRFSS 2001–2015, Tax Burden on Tobacco, FRED, Rauchverbote).

Benötigte Hosts: www.cdc.gov, data.cdc.gov, fred.stlouisfed.org. Etwa 1,5 GB Download.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from frm_panel.data import download_all  # noqa: E402

if __name__ == "__main__":
    download_all(ROOT / "data" / "raw")
