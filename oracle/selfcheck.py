"""Recompute the impact figures quoted in docs/definitions.md and cross-check rules against labels.

If the data, a rule or the label table drifts from what the definitions doc says, this fails.
"""
from . import rules

# Figures stated in docs/definitions.md.
EXPECTED = {
    "duplicate rows collapsed (D-10)": 18,
    "unique mentions (D-10)": 1904,
    "reposts (D-11)": 70,
    "reposts flagged by tool (D-11a)": 38,
    "reposts RT text (D-11b)": 15,
    "reposts '#repost via' (D-11c)": 17,
    "reposts left unlinked (D-11)": 0,
    "spam mentions (D-13)": 84,
    "taproom mentions incl. reposts (D-22)": 45,
    "pop-up genuine mentions excluded (D-23)": 22,
    "double posts (D-17)": 0,
    "genuine Brewbird conversations (D-15)": 987,
    "distinct Brewbird authors (D-15)": 984,
    "unlabelled mentions": 0,
}


def run(df) -> list[dict]:
    g = rules.genuine(df)
    actual = {
        "duplicate rows collapsed (D-10)": int((df["source_lines"].str.len() - 1).sum()),
        "unique mentions (D-10)": len(df),
        "reposts (D-11)": int(df["is_repost"].sum()),
        "reposts flagged by tool (D-11a)": int((df["repost_basis"] == "tool_flag").sum()),
        "reposts RT text (D-11b)": int((df["repost_basis"] == "rt_text").sum()),
        "reposts '#repost via' (D-11c)": int((df["repost_basis"] == "repost_via_text").sum()),
        "reposts left unlinked (D-11)": int((df["is_repost"] & df["repost_of"].isna()).sum()),
        "spam mentions (D-13)": int(df["spam"].sum()),
        "taproom mentions incl. reposts (D-22)": int(df["unrelated"].sum()),
        "pop-up genuine mentions excluded (D-23)": int((df["status"] == "ambiguous").sum()),
        "double posts (D-17)": int((df["status"] == "double_post").sum()),
        "genuine Brewbird conversations (D-15)": len(g),
        "distinct Brewbird authors (D-15)": int(g["author_handle"].nunique()),
        "unlabelled mentions": int((~df["labelled"]).sum()),
    }
    checks = [{"check": k, "expected": v, "actual": actual[k], "ok": actual[k] == v} for k, v in EXPECTED.items()]

    # Rules and human labels must agree wherever both say something.
    cross = {
        "spam rule vs label table": (df["spam"] != (df["label_brand"] == "SPAM")).sum(),
        "taproom rule vs label table": (df["unrelated"] != (df["label_brand"] == "TAP")).sum(),
        "pop-up rule vs label table": (df["ambiguous"] != (df["label_brand"] == "BB?")).sum(),
        "Brewbird reference rule vs label table": ((df["brewbird_ref"] & ~df["spam"]) != (df["label_brand"] == "BB")).sum(),
        "mention ids with differing content": df["id_clash"].sum(),
    }
    checks += [{"check": k, "expected": 0, "actual": int(v), "ok": int(v) == 0} for k, v in cross.items()]
    return checks
