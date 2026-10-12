# Entity-resolution log

The brief asks for "a short log of anything you deliberately merged or deliberately kept apart, with your reason for each". This is that log. The pipeline links each decision to its rule in `docs/definitions.md`, and the graph records these merges as `inferred` edges with `rule = ER-xx`.

Status: draft, 12 Oct 2026. Only ER-08 needs a decision from Abhinav (open call O-1).

## Merged

| ID | Strings | Resolved to | Reason | Rule |
|---|---|---|---|---|
| ER-01 | "Peak Instant" | Bluepeak Roasters (sub-brand) | Bluepeak's own brands page (captured 2026-09-20) says it launched Peak Instant in 2024. Without this merge, Bluepeak's share of voice halves. | D-21 |
| ER-02 | "@saltmarshcoffee", "Saltmarsh", "Saltmarsh Coffee" | Saltmarsh Coffee | The handle and the names refer to the same company. | D-21 |
| ER-03 | "Bluepeak", "Bluepeak Roasters" | Bluepeak Roasters | Short form of the same name. | D-21 |
| ER-04 | "BB Nitro", "nitro can", "cold brew can", "Brewbird Nitro" | Brewbird Nitro (BB-NIT-6) | Client aliases in `products.csv`, applied only when the mention also refers to Brewbird. | D-20, D-24 |
| ER-05 | "drip bags" (10-pack and 30-pack) | Brewbird Drip (line level) | The alias is shared by both SKUs, and mentions rarely say which pack. Counts are kept at line level and never split by guessing the SKU. | D-24 |
| ER-06 | Reposts (`is_repost_of`, `RT @`, `#repost via`) | Their original mention | They amplify an original; they are not new conversations. Linked by the quoted handle plus matching text. | D-11 |
| ER-07 | `coupon_kart_*`, `lootbazaar_*`, `dealsloot_*` handles | One coordinated coupon-bot group | 84 identical promo posts in three hours on 22 Sep. | D-13 |

## Kept apart

| ID | Strings | Kept apart from | Reason | Rule |
|---|---|---|---|---|
| ER-08 | "Brewbird pop-up at the Bandra flea" | Nothing (default: included as Brewbird brand-level) | **Judgement call, open (O-1).** Nothing says whether this is the coffee brand or the taproom. | D-23 |
| ER-09 | "Brewbird taproom", "Brewbird Pune live music", beer, IPA, pints, Koregaon Park | Brewbird Coffee Co. | Brewbird's about page says it has no connection with any restaurant, bar or taproom using a similar name. Kept as `UnrelatedEntity`. | D-22 |
| ER-10 | "BB50" | Brewbird / "BB Nitro" | A coupon code in spam, not a brand reference. A prefix match on "BB" would wrongly count it. | D-20 |
| ER-11 | "Saltmarsh Nitro" | Brewbird Nitro | Both are called "Nitro". A mention naming only "nitro" with Saltmarsh is Saltmarsh's product. | D-24 |
| ER-12 | "the other nitro cans", "the other guys" | Brewbird | Implicit reference, not a mention of Brewbird. It is recorded but not counted for Brewbird. | D-20 |
| ER-13 | Product or line words without "Brewbird" ("nitro", "classic", "drip bags") | Brewbird | These are generic words; all 91 such mentions here are about Saltmarsh Nitro. | D-24 |
| ER-14 | Saltmarsh Nitro INR (IN) and AED (AE) prices | Each other | They are different markets and currencies; they are never compared and never converted. | D-53 |
| ER-15 | Bluepeak Chikmagalur Rs 420 (2025-11-03) and Rs 450 (2026-09-20) | Each other | These are two dated observations of the same product, so the older one is history, not a duplicate. | D-50, D-52 |
| ER-16 | Same handle posting twice (3 handles) | Nothing: each post counts | A conversation is a post, not a person. Distinct authors are reported alongside. | D-15 |
