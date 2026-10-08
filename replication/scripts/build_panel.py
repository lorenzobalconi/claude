"""Baut data/panel.csv: ein Staat-Jahr-Panel 2001–2015 (50 Staaten + DC) aus den Rohdaten."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from frm_panel.data import build_panel  # noqa: E402

if __name__ == "__main__":
    p = build_panel(ROOT / "data" / "raw", ROOT / "data" / "panel.csv")
    print(p.groupby("year")[["prev", "tax_nom", "tax_real"]].agg(["min", "mean", "max"]).round(3))
