---
eval: E-07443f38
---
## Recorded result: 58 of 69 runs (84%)

The full run below passed 51 of 69. Three things were settled after it, each on that run's
questions, and the recorded figure takes the latest result for each:

| Question | In this run | After | How |
|---|---|---|---|
| Q5 | 0 of 3 | 3 of 3 | Consumer rule 6 fixed (both comparisons for an unusual day; a burst's account count and time span); re-run `E-db750b64` |
| A-beer | 0 of 3 | 3 of 3 | Grounding rule 11 fixed (a wrong premise is corrected with what is true instead); re-run `E-954d0a95` |
| Q10 | 2 of 3 | 3 of 3 | The failed run's answers re-judged with `gpt-6.1-sol`: a judge error (see below) |

So golden questions pass 32 of 36 runs and adversarial questions 26 of 33. The two fixes
changed rules that every question reads (consumer rule 6, grounding rule 11) and only Q5 and
A-beer were re-run after them; the figure is the latest result per question, not one run of
the whole set. The fixes are logged as F-P5-10 and F-P5-11 in [failure-log.md](failure-log.md).

**The remaining 11 failed runs** each leave out one thing a rubric item or key figure asks
for, in one or two of three runs: Q4 (TST rising from zero), Q8 (the offer price per
can), Q12 ×2 (the complaints are about defects), A-teams (codes named for each team),
A-subscription-reaction (what the posts cannot count), A-causation (Nitro volume stayed flat),
A-uae (compared per 100 ml rather than per can), A-reply (the can was swollen), A-leading ×2
(TST named as the reason).

**Judge check.** Five failed runs looked like judge errors and were re-judged with
`gpt-6.1-sol` on the same saved answers ([eval-runs/E-07443f38-rejudge-gpt-6.1-sol.json](eval-runs/E-07443f38-rejudge-gpt-6.1-sol.json),
$0.02). The two judges agreed on 11 of 14 items. The 3 they split on were all quotes
`gpt-6-luna` did not copy exactly from the answer; `gpt-6.1-sol` marked them met. That turned
one run into a pass (Q10). The other four runs still failed under both judges, so they were
omissions in the answer, not judge errors: three on A-beer (since fixed) and one on
A-subscription-reaction.

**After the recorded run (P6, 15 Oct).** The tool descriptions were made generic: parameter
examples that named Brewbird, its competitors or its codes were replaced with wording that
fits any client, and `price_compare` now asks for names as `brand_facts` returns them. This
changes what the model is sent, not what any tool does, so the recorded result stands. A
check on the questions that use those parameters passed every run: `E-8a88f98f` (Q1, Q2,
Q3, Q7, Q9, Q10, A-beer, 7 of 7) and `E-15aa5fe9` (Q7 and Q8 twice, 4 of 4), $0.03 in all.

**Costs in this report.** Agent costs here were computed before `config/llm_prices.yaml` had a
cached-input price, so cached tokens are priced as ordinary input and the agent costs are
about 2.4 times what was billed. At the cached rate this full run cost about $0.07 for the
agents and $0.02 for the judge.
