"""The definitions (docs/definitions.md) applied to the raw mentions, one rule at a time.

Every derived column names the D-rule that produced it. Labels (brand, line, sentiment,
code) come from the human-reviewed label table, never from this module.
"""
import re

import pandas as pd

from . import load

IST = "Asia/Kolkata"
WINDOW_START = pd.Timestamp("2026-08-17", tz=IST)          # D-03
AS_OF = pd.Timestamp("2026-10-04", tz=IST)                  # D-03
WEEKS = [d.date() for d in pd.date_range("2026-08-17", "2026-09-28", freq="7D")]  # D-02

# D-45 direction thresholds, the values set in config/brewbird/client.yaml (sentiment.direction).
DIRECTION_STEADY_BELOW = 0.10
DIRECTION_CLEAR_CHANGE = 0.20
DIRECTION_MIN_SHARE = 0.5

BRAND_CODES = {                                             # label table brand column
    "BB": ["Brewbird"], "SM": ["Saltmarsh"], "BP": ["Bluepeak"], "FH": ["Filterhaus"],
    "SM+BP": ["Saltmarsh", "Bluepeak"], "SPAM": [], "TAP": [], "BB?": [],
}
BRANDS = ["Brewbird", "Saltmarsh", "Bluepeak", "Filterhaus"]

# D-12: filler and decoration added around the text, and repost markers.
_RT = re.compile(r"^rt @\S+?:\s*", re.I)
_VIA = re.compile(r"\s*#repost via @\S+", re.I)
_PREFIX = re.compile(r"^(psa:|ngl|honestly|update:|ok so|lol)\s+", re.I)
_SUFFIX = re.compile(r"(\s*(lol|!!|\(\w+\)|#coffee|☕|👍|🍻|😩|🙄|😍|🔥|\?!!))+\s*$", re.I)


def normalise(text: str) -> str:
    """D-12 normalised text."""
    s = _VIA.sub("", _RT.sub("", text.strip()))
    for _ in range(3):
        s = _PREFIX.sub("", s)
        s = _SUFFIX.sub("", s)
    return s.lower().strip(" !?.")


# D-13 promotional markers: a coupon code (letters then digits, e.g. BB50) or a shortened link.
_PROMO = re.compile(r"\b[A-Z]{2,}\d{2,}\b|bit\.ly/|tinyurl\.com/|t\.co/")
# D-22 the unrelated "Brewbird" taproom in Pune.
_TAPROOM = re.compile(r"taproom|\bbar\b|beer|\bipa\b|\bpints?\b|pitchers?|live music|koregaon", re.I)
# D-23 ambiguous pop-up.
_POPUP = re.compile(r"pop-?up", re.I)
# D-20 explicit Brewbird reference ("BB" alone or inside a code such as BB50 does not count).
_BREWBIRD = re.compile(r"brewbird|\bbb nitro\b", re.I)


def mentions() -> pd.DataFrame:
    """One row per unique mention with every D-rule applied and labels joined."""
    raw = load.mentions_raw()

    # D-10: collapse byte-identical duplicate rows, keeping every source line for provenance.
    content = [c for c in raw.columns if c != "source_line"]
    lines = raw.groupby(content, sort=False)["source_line"].apply(list).reset_index()
    df = lines.rename(columns={"source_line": "source_lines"})
    clash = df["mention_id"].duplicated(keep=False)
    df["id_clash"] = clash                                   # same id, different content: none expected

    # D-01, D-02: IST dates and Monday-start weeks, computed once here.
    df["ts"] = pd.to_datetime(df["posted_at"]).dt.tz_convert(IST)
    df["date_ist"] = df["ts"].dt.date
    df["week_ist"] = (df["ts"].dt.normalize() - pd.to_timedelta(df["ts"].dt.weekday, unit="D")).dt.date
    df["likes"] = df["likes"].astype(int)
    df["norm"] = df["text"].map(normalise)

    _reposts(df)
    _double_posts(df)
    _spam(df)
    df["unrelated"] = df["text"].str.contains(_BREWBIRD) & df["text"].str.contains(_TAPROOM)    # D-22
    df["ambiguous"] = df["text"].str.contains(_BREWBIRD) & df["text"].str.contains(_POPUP)      # D-23
    df["brewbird_ref"] = df["text"].str.contains(_BREWBIRD) & ~df["unrelated"] & ~df["ambiguous"]  # D-20

    _labels(df)
    _status(df)
    return df


def _reposts(df: pd.DataFrame) -> None:
    """D-11: tool flag, RT prefix, or '#repost via'; link by quoted handle plus matching text."""
    rt = df["text"].str.extract(r"(?i)^RT @(\S+?):")[0]
    via = df["text"].str.extract(r"#repost via @(\S+)")[0]
    df["repost_basis"] = None
    df.loc[via.notna(), "repost_basis"] = "repost_via_text"
    df.loc[rt.notna(), "repost_basis"] = "rt_text"
    df.loc[df["is_repost_of"] != "", "repost_basis"] = "tool_flag"
    df["repost_of"] = df["is_repost_of"].replace("", None)

    quoted = rt.fillna(via)
    for i in df.index[df["repost_of"].isna() & quoted.notna()]:
        cand = df[(df["author_handle"] == quoted[i]) & (df["norm"] == df.at[i, "norm"])
                  & (df["ts"] < df.at[i, "ts"]) & df["repost_basis"].isna()]
        if len(cand):
            df.at[i, "repost_of"] = cand.sort_values("ts").iloc[-1]["mention_id"]
    df["is_repost"] = df["repost_basis"].notna()


def _double_posts(df: pd.DataFrame) -> None:
    """D-17: same author, same normalised text, same platform, within 24 hours. Different platforms count separately."""
    df["double_post_of"] = None
    orig = df[~df["is_repost"]].sort_values("ts")
    for _, g in orig.groupby(["author_handle", "platform", "norm"]):
        if len(g) < 2:
            continue
        first = g.iloc[0]
        for i, row in g.iloc[1:].iterrows():
            if row["ts"] - first["ts"] <= pd.Timedelta(hours=24):
                df.at[i, "double_post_of"] = first["mention_id"]
            else:
                first = row


def _spam(df: pd.DataFrame) -> None:
    """D-13: >= 5 distinct handles posting the same promotional text within 6 hours."""
    df["spam"] = False
    promo = df[df["text"].str.contains(_PROMO)]
    for _, g in promo.groupby("norm"):
        g = g.sort_values("ts")
        for i, row in g.iterrows():
            win = g[(g["ts"] >= row["ts"]) & (g["ts"] <= row["ts"] + pd.Timedelta(hours=6))]
            if win["author_handle"].nunique() >= 5:
                df.loc[win.index, "spam"] = True


def _labels(df: pd.DataFrame) -> None:
    """Join the human-reviewed label table on normalised text. Unseen text stays unlabelled."""
    lt = load.label_table()
    lt["norm"] = lt["template"].map(normalise)
    lt = lt.drop_duplicates("norm")
    lab = df[["norm"]].merge(lt[["norm", "brand", "line", "sentiment", "code"]], on="norm", how="left")
    df["label_brand"] = lab["brand"].values
    df["line"] = lab["line"].fillna("").values
    df["sentiment"] = lab["sentiment"].values
    df["code"] = lab["code"].fillna("").values
    df["labelled"] = lab["brand"].notna().values
    df["brands"] = df["label_brand"].map(lambda b: BRAND_CODES.get(b, []) if isinstance(b, str) else [])


def _status(df: pd.DataFrame) -> None:
    """D-15, D-16: every mention keeps a status; only 'genuine' is ever counted by default."""
    status, reason = [], []
    for _, r in df.iterrows():
        if r["is_repost"]:
            s, why = "repost", f"D-11 {r['repost_basis']}"
        elif r["double_post_of"]:
            s, why = "double_post", "D-17"
        elif r["spam"]:
            s, why = "spam", "D-13 coordinated promotion"
        elif r["unrelated"]:
            s, why = "unrelated", "D-22 Brewbird taproom"
        elif r["ambiguous"]:
            s, why = "ambiguous", "D-23 unresolved entity"
        else:
            s, why = "genuine", ""
        status.append(s)
        reason.append(why)
    df["status"] = status
    df["exclusion_reason"] = reason


def genuine(df: pd.DataFrame, brand: str | None = "Brewbird") -> pd.DataFrame:
    """D-15 genuine conversations, optionally about one brand."""
    g = df[df["status"] == "genuine"]
    if brand:
        g = g[g["brands"].map(lambda b: brand in b)]
    return g


def last_weeks(n: int) -> list:
    """D-03: the n most recent full reporting weeks ending on the as-of date."""
    return WEEKS[-n:]
