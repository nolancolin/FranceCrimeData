"""Recorded crime in French departments, following the OSEMN steps."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
REPORTS_DIR = ROOT / "reports"
DOCS_DIR = ROOT / "docs"
FIGURES_DIR = REPORTS_DIR / "figures"
