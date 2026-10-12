# Brewbird Coffee Co. data pack

This is the export Brewbird sent over at kickoff. It covers **17 August to 4 October 2026**. Reporting weeks run Monday to Sunday, IST, so the seven weeks start on 17 Aug, 24 Aug, 31 Aug, 7 Sep, 14 Sep, 21 Sep and 28 Sep.

It hasn't been cleaned or audited. Treat it the way you'd treat a real client export.

## mentions.csv

Social and review mentions pulled by Brewbird's social-listening export. The export matched on the names of Brewbird, its competitors and their products.

| Column | Meaning |
|---|---|
| `mention_id` | ID assigned by the listening tool |
| `platform` | `instagram`, `x`, `youtube_comment`, `reddit`, `amazon_review`, `google_review` |
| `posted_at` | When the post was published, ISO 8601 |
| `author_handle` | Public handle of the poster |
| `text` | Post text as captured |
| `likes` | Likes or upvotes at capture time |
| `is_repost_of` | Original `mention_id` when the tool recognised the post as a repost |
| `url` | Link to the post |

## products.csv

Brewbird's catalog. `aliases` holds the nicknames customers use for each product, separated by `|`.

## client_complaint_taxonomy.csv

Brewbird's own complaint codes, the team that owns each one, and Brewbird's routing rules. These are the codes Brewbird reports in.

## competitor_pricing.csv

Competitor list prices, captured from their websites on the date in `captured_at`.

## competitor_ads.csv

A public ad-library export: one row per ad, with the dates it was first and last seen.

## brand_site/ and competitor_snapshots/

Web pages saved as text. Each file shows the date it was captured and the URL it came from.
