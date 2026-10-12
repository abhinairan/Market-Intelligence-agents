"""Read the raw data pack exactly as delivered."""
import csv
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "data" / "raw" / "fde-v4-data-pack"
LABEL_TABLE = Path(__file__).resolve().parent / "label_table.csv"


def mentions_raw() -> pd.DataFrame:
    """mentions.csv with its 1-based file line number kept for provenance (header is line 1)."""
    df = pd.read_csv(PACK / "mentions.csv", dtype=str, keep_default_na=False)
    df["source_line"] = df.index + 2
    return df


def products() -> pd.DataFrame:
    return pd.read_csv(PACK / "products.csv", dtype=str, keep_default_na=False)


def taxonomy() -> pd.DataFrame:
    return pd.read_csv(PACK / "client_complaint_taxonomy.csv", dtype=str, keep_default_na=False)


def competitor_pricing() -> pd.DataFrame:
    return pd.read_csv(PACK / "competitor_pricing.csv", dtype=str, keep_default_na=False)


def competitor_ads() -> pd.DataFrame:
    return pd.read_csv(PACK / "competitor_ads.csv", dtype=str, keep_default_na=False)


def label_table() -> pd.DataFrame:
    return pd.read_csv(LABEL_TABLE, dtype=str, keep_default_na=False)


def pages() -> list[dict]:
    """Every saved web page (brand_site/ and competitor_snapshots/) with its capture date and URL."""
    out = []
    for folder in ("brand_site", "competitor_snapshots"):
        for path in sorted((PACK / folder).glob("*.md")):
            text = path.read_text(encoding="utf-8")
            m = re.search(r"Captured (\d{4}-\d{2}-\d{2}) from (\S+)", text)
            out.append({
                "file": f"{folder}/{path.name}",
                "captured_at": m.group(1) if m else None,
                "url": m.group(2) if m else None,
                "text": text,
            })
    return out


def pack_files() -> list[str]:
    return sorted(str(p.relative_to(PACK)) for p in PACK.rglob("*") if p.is_file())
