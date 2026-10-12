# Oracle

Independent expected answers for the twelve golden questions, computed straight from the raw data pack with pandas. The eval compares the agents' answers against these files.

```
pip install -r oracle/requirements.txt
python -m oracle.run          # writes eval/expected/q01.json … q12.json and selfcheck.json
python -m pytest tests/test_oracle.py
```

## Why it is independent

- It reads `data/raw/` directly and never the graph.
- It never imports pipeline code (`src/`); `tests/test_oracle.py` fails if it does.
- Its labels (brand, product line, sentiment, complaint code) come from `label_table.csv`, one human-reviewed row per text template (reviewed by Abhinav, 12 Oct 2026). The pipeline labels mentions its own way, so a disagreement is a finding, not an echo.
- The only thing it shares with the pipeline is `docs/definitions.md`. Every rule in `rules.py` names the D-rule it implements.

## Files

| File | What it does |
|---|---|
| `load.py` | Reads the raw files and keeps CSV line numbers for provenance |
| `rules.py` | Applies the D-rules: dedupe, IST weeks, reposts, double posts, spam, taproom, pop-up, labels, status |
| `primitives.py` | Reusable pieces: counts, weekly sentiment, complaint ranking, daily activity, share of voice, unit prices, dated observations |
| `golden.py` | One function per golden question |
| `selfcheck.py` | Recomputes the figures quoted in the definitions doc, and checks the rules against the label table where both say something |
| `label_table.csv` | The human-reviewed labels |

## Output

Each `eval/expected/qNN.json` has the answer, the mention IDs behind it, and the D-rules it relies on. Q6, Q11 and Q12 cannot be answered from the data, so they carry `facts` and a `rubric` that a grader checks the agent's answer against. Q4, Q5 and Q8 carry both numbers and a rubric.

`status` is `final` once every label-table row has `reviewer_ok = yes`, otherwise `draft`.

## Answering a new question

Most new questions are a few lines over `primitives.py`, for example the Drip complaint ranking for the last two weeks:

```python
from oracle import rules, primitives as p
df = rules.mentions()
drip = [r for r in p.complaint_ranking(df, rules.last_weeks(2)) if "Drip" in r["by_line"]]
```

Text the label table has never seen comes out with `labelled = False`; the oracle does not guess a label for it.
