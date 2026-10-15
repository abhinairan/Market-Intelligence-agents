# Brewbird Nitro cans are failing, and the brand numbers hide it

**For:** Ishita Rao, for the leadership review on 19 October 2026.
**Data:** Brewbird's listening export, 17 August to 4 October 2026: 987 genuine conversations
about Brewbird after spam, reposts and the Pune taproom are removed.

## The finding

Since mid-September, customers have been reporting swollen, bulging and flat Nitro cans, and
the reports are growing every week. Brand sentiment looks steady, so the brand-level report
shows nothing. Nitro's own sentiment has fallen from clearly positive to negative.

| Week starting | 7 Sep | 14 Sep | 21 Sep | 28 Sep |
|---|---|---|---|---|
| Nitro posts reporting a can or freshness defect (TST) | 0 | 7 | 9 | 13 |
| Nitro net sentiment | +0.53 | +0.03 | +0.03 | **−0.27** |
| Brewbird net sentiment, all lines | +0.44 | +0.37 | +0.32 | +0.31 |

## The evidence

- **29 Nitro posts report a defect, all since 14 Sep**, from 29 different people on six
  platforms; none in the four weeks before. 22 describe a swollen, puffed or bulging can, and
  7 a flat or sour one. Five say "the last batch".
- **It is now most of Nitro's complaints:** 13 of 19 negative Nitro posts in the week of
  28 Sep. That week 63% of Nitro posts were negative, against 7% in late August.
- **It is QA's problem, but it looks like Logistics'.** 11 of the 29 also mention the box, a
  leak or delivery. A tool that files by keyword puts them under packaging (PKG), which Logistics owns. Under Brewbird's own
  rule they are TST, owned by Quality Assurance. Farah says QA hears about them three weeks
  late.
- **It is not Saltmarsh.** Saltmarsh launched its nitro can on 14 Sep, the same week. But none
  of the 57 negative Nitro posts mentions Saltmarsh, and Nitro's conversation volume held at
  30 a week throughout. The fall comes from complaints about the can, not from talk of the
  rival.

## What to do in the week of 12 October

1. **QA (Farah):** treat it as a seal or nitrogen defect in recent Nitro batches. Pull the
   batch and filling records for cans shipped since early September, and decide whether to
   hold stock. The posts cannot say which batches; the records can.
2. **Route every can complaint to QA the same day (Dev, with Halyard).** Each morning, from a
   daily export, list new Nitro TST posts and send them to QA. Reply to each customer with a draft, approved by a
   person, asking for the batch code and a photo, so QA gets batch numbers.
3. **Don't answer it with price (Kunal).** Saltmarsh's "half the price" is not true: Rs 90 a
   can against Brewbird's Rs 110 at list price, 82% of ours. Only its 30% first-order offer
   brings it to Rs 63, 57%. Nitro's problem is the can, not the price.

## The one metric for the 19th

**Same-day routing to QA.** Of the Nitro posts from 12 to 18 October that describe a swollen,
bulging, puffed or flat can, the share that QA has logged within 24 hours of posting.

- **Target:** at least 90%. **Today:** close to 0%, since these reach QA by way of Logistics,
  about three weeks late.
- **It fails** if fewer than 90% reach QA in a day, or if QA or Dev's team finds a defect
  post that Halyard missed (each one counts as not routed).
- **How it is checked on the 19th:** Halyard's list of post IDs and times against the times in
  QA's log. Dev's team can count it; leadership sees one number.

**What success looks like on the 19th:** QA has matched the defect to specific batches, using
the batch codes customers sent back. The routing is the means; finding the batches is the
point.

Every figure here traces to its posts and rows with `halyard trace`. The data ends on
4 October; a fresh export on 12 October shows whether the defect is still rising.
