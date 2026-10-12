"""Reusable building blocks over the rule-applied mentions and the competitor files.

Each returns plain Python data with the mention IDs or source references behind it, so a new
question can be answered in a few lines and every number stays traceable.
"""
import re

import pandas as pd

from . import load, rules


def ids(frame: pd.DataFrame) -> list[str]:
    return sorted(frame["mention_id"].tolist())


# ---------- consumer side ----------

def counts_by_line(df, weeks=None) -> dict:
    """D-15, D-24: genuine Brewbird conversations per product line; no line means brand-level only."""
    g = rules.genuine(df)
    if weeks is not None:
        g = g[g["week_ist"].isin(weeks)]
    out = {}
    for line, part in g.groupby(g["line"].replace("", "brand-level only")):
        out[line] = {"conversations": len(part), "mention_ids": ids(part)}
    return {"total": len(g), "authors": int(g["author_handle"].nunique()), "by_line": out}


def exclusions(df, brand_text="brewbird", dates=None) -> dict:
    """D-16: what was excluded among mentions whose text names the brand, and why."""
    m = df[df["text"].str.lower().str.contains(brand_text)]
    if dates is not None:
        m = m[m["date_ist"].isin(dates)]
    ex = m[m["status"] != "genuine"]
    return {s: {"count": len(p), "mention_ids": ids(p)} for s, p in ex.groupby("status")}


def sentiment_table(frame: pd.DataFrame) -> dict:
    """D-40: net score, % negative and negative like share, with the 10-point engagement flag."""
    n = len(frame)
    pos = int((frame["sentiment"] == "pos").sum())
    neg = int((frame["sentiment"] == "neg").sum())
    neu = n - pos - neg
    likes = int(frame["likes"].sum())
    neg_likes = int(frame.loc[frame["sentiment"] == "neg", "likes"].sum())
    pct_neg = round(100 * neg / n, 1) if n else None
    neg_like_share = round(100 * neg_likes / likes, 1) if likes else None
    return {
        "n": n, "positive": pos, "neutral": neu, "negative": neg,
        "net": round((pos - neg) / n, 2) if n >= 10 else None,
        "too_few_to_read": n < 10,
        "pct_negative": pct_neg,
        "negative_like_share": neg_like_share,
        "engagement_flag": bool(pct_neg is not None and neg_like_share is not None
                                and neg_like_share - pct_neg >= 10),
    }


def weekly_sentiment(df, line=None, exclude_line=None) -> dict:
    """D-40 per reporting week for Brewbird, one line, or Brewbird without one line."""
    g = rules.genuine(df)
    if line:
        g = g[g["line"] == line]
    if exclude_line:
        g = g[g["line"] != exclude_line]
    return {str(w): {**sentiment_table(g[g["week_ist"] == w]), "mention_ids": ids(g[g["week_ist"] == w])}
            for w in rules.WEEKS}


def complaint_ranking(df, weeks, examples=2) -> list[dict]:
    """D-31, D-34, D-42: Brewbird complaint codes ranked, with deterministic examples and owners."""
    tax = load.taxonomy().set_index("code")
    g = rules.genuine(df)
    g = g[g["week_ist"].isin(weeks) & (g["code"] != "")]
    rows = []
    for code, part in g.groupby("code"):
        ex = part.sort_values(["likes", "ts"], ascending=[False, True]).head(examples)
        rows.append({
            "code": code, "name": tax.at[code, "name"], "owner_team": tax.at[code, "owner_team"],
            "conversations": len(part),
            "by_line": part["line"].replace("", "brand-level only").value_counts().to_dict(),
            "examples": [{"mention_id": r.mention_id, "text": r.text, "likes": r.likes} for r in ex.itertuples()],
            "mention_ids": ids(part),
        })
    return sorted(rows, key=lambda r: (-r["conversations"], r["code"]))


def code_by_week(df, code, line=None) -> dict:
    g = rules.genuine(df)
    g = g[g["code"] == code]
    if line:
        g = g[g["line"] == line]
    return {str(w): {"count": int((g["week_ist"] == w).sum()), "mention_ids": ids(g[g["week_ist"] == w])}
            for w in rules.WEEKS}


def daily_activity(df, date) -> dict:
    """D-43: one day's volume decomposed by status, against the window's median day."""
    per_day = df.groupby("date_ist").size()
    day = df[df["date_ist"] == date]
    spam = day[day["status"] == "spam"]
    families = spam["author_handle"].str.replace(r"_\d+$", "", regex=True).value_counts().to_dict()
    return {
        "date": str(date), "total": len(day), "median_daily_total": float(per_day.median()),
        "anomalous": bool(len(day) > 2 * per_day.median()),
        "by_status": day["status"].value_counts().to_dict(),
        "spam": {
            "count": len(spam),
            "first": spam["ts"].min().isoformat() if len(spam) else None,
            "last": spam["ts"].max().isoformat() if len(spam) else None,
            "handle_families": families,
            "texts": spam["text"].value_counts().to_dict(),
            "mentions_naming_nitro": int(spam["text"].str.contains("Nitro", case=False).sum()),
            "mention_ids": ids(spam),
        },
        "genuine_that_day": len(day[day["status"] == "genuine"]),
        "median_daily_genuine": float(df[df["status"] == "genuine"].groupby("date_ist").size().median()),
    }


def share_of_voice(df, weeks) -> dict:
    """D-41 counted, the naive figure beside it, and D-44 reach."""
    w = df[df["week_ist"].isin(weeks)]
    counted, reach = {}, {}
    gen = w[w["status"] == "genuine"]
    for b in rules.BRANDS:
        part = gen[gen["brands"].map(lambda x: b in x)]
        counted[b] = {"conversations": len(part), "mention_ids": ids(part)}
        originals = set(part["mention_id"])
        rp = df[df["is_repost"] & df["repost_of"].isin(originals)]
        reach[b] = {"reposts": len(rp),
                    "reposts_per_100": round(100 * len(rp) / len(part), 1) if len(part) else None,
                    "likes_at_capture": int(part["likes"].sum())}
    total = sum(v["conversations"] for v in counted.values())
    for b in counted:
        counted[b]["share_pct"] = round(100 * counted[b]["conversations"] / total, 1)

    text = w["text"].str.lower()
    naive_pat = {"Brewbird": "brewbird|bb nitro", "Saltmarsh": "saltmarsh",
                 "Bluepeak": "bluepeak", "Filterhaus": "filterhaus"}
    naive = {b: int(text.str.contains(p).sum()) for b, p in naive_pat.items()}
    ntot = sum(naive.values())
    return {
        "weeks": [str(x) for x in weeks],
        "counted": counted, "counted_total": total,
        "naive": {b: {"mentions": v, "share_pct": round(100 * v / ntot, 1)} for b, v in naive.items()},
        "excluded_in_window": w[w["status"] != "genuine"]["status"].value_counts().to_dict(),
        "reach": reach,
    }


# ---------- competitor side ----------

def parse_pack(pack: str) -> dict:
    """D-53: unit count and unit size from strings such as '6 x 200ml', '250g', '100g jar', '10 bags'."""
    p = pack.lower()
    m = re.match(r"(\d+)\s*x\s*(\d+)\s*ml", p)
    if m:
        return {"units": int(m.group(1)), "unit": "can", "ml_each": int(m.group(2)), "ml_total": int(m.group(1)) * int(m.group(2))}
    m = re.match(r"(\d+)\s*g", p)
    if m:
        return {"units": 1, "unit": "pack", "g_total": int(m.group(1))}
    m = re.match(r"(\d+)\s*bags", p)
    if m:
        return {"units": int(m.group(1)), "unit": "bag"}
    return {}


def unit_prices(price: float, pack: str) -> dict:
    u = parse_pack(pack)
    out = {"per_pack": price}
    if u.get("unit") in ("can", "bag"):
        out[f"per_{u['unit']}"] = round(price / u["units"], 2)
    if "ml_total" in u:
        out["per_100ml"] = round(100 * price / u["ml_total"], 2)
    if "g_total" in u:
        out["per_100g"] = round(100 * price / u["g_total"], 2)
    return out


def observations(competitor: str) -> list[dict]:
    """D-50, D-52: dated price observations with age against the as-of date."""
    pr = load.competitor_pricing()
    pr = pr[pr["competitor"].str.startswith(competitor)]
    out = []
    for r in pr.itertuples():
        age = (rules.AS_OF.date() - pd.Timestamp(r.captured_at).date()).days
        out.append({"product": r.product, "pack": r.pack, "price": float(r.price), "currency": r.currency,
                    "region": r.region, "observed_at": r.captured_at, "age_days": age, "stale": age > 90,
                    "source": f"competitor_pricing.csv ({r.source_url})"})
    return out


def shipping_thresholds() -> list[dict]:
    """Free-shipping thresholds stated on saved pages, with their capture dates."""
    out = []
    for pg in load.pages():
        m = re.search(r"[Ff]ree shipping (?:on (?:all )?orders )?above Rs (\d+)", pg["text"])
        if m:
            out.append({"file": pg["file"], "captured_at": pg["captured_at"], "threshold_rs": int(m.group(1))})
    return out
