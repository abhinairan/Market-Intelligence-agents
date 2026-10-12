"""Write the expected answers: python -m oracle.run"""
import json

from . import golden, load, rules
from .selfcheck import run as selfcheck

OUT = load.ROOT / "eval" / "expected"


def main() -> None:
    df = rules.mentions()
    lt = load.label_table()
    status = "final" if (lt["reviewer_ok"] == "yes").all() else "draft"
    checks = selfcheck(df)
    OUT.mkdir(parents=True, exist_ok=True)
    for i, fn in enumerate(golden.ALL, start=1):
        result = {"id": f"Q{i:02d}", "status": status, **fn(df)}
        (OUT / f"q{i:02d}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    (OUT / "selfcheck.json").write_text(json.dumps(checks, indent=2, default=str) + "\n", encoding="utf-8")
    failed = [c for c in checks if not c["ok"]]
    print(f"wrote {len(golden.ALL)} expected answers ({status}) to {OUT.relative_to(load.ROOT)}; "
          f"self-check {len(checks) - len(failed)}/{len(checks)} passed")
    for c in failed:
        print(f"  FAILED {c['check']}: expected {c['expected']}, got {c['actual']}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
