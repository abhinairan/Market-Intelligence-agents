# What the evaluation caught, and how we fixed it

We ran the evaluation before tuning the agents, then fixed what it found and ran it again. This
page tells one of those stories in full and lists the rest in a line each. The technical detail
for every fix (cause, files changed, run IDs, before and after) is in
[failure-log.md](failure-log.md); the grading itself is in [eval-report.md](eval-report.md).

## "What happened on 22 September?"

**Why the question matters.** On 22 September Brewbird had 132 mentions, almost four times a
normal day (36). A brand manager seeing that spike needs to know one thing: is something wrong
with Brewbird, or is it noise?

**The right answer.** Mostly noise. 84 of the 132 were coupon-bot posts: the same few promo
texts, posted by 84 different accounts between 2 and 5 am. Real conversation about Brewbird that
day was 26 posts, against a usual 20 a day, so slightly busy but not alarming.

**What the evaluation found, and what we changed.** It took three rounds, and one of our fixes
made things worse before the evaluation caught it.

1. **The agent explained the spam but not the real conversation.** Every answer said the spike
   was spam, but none said whether real conversation that day was normal. A reader could not
   tell whether a real problem sat under the noise. *Fix (tool and skill):* the daily-activity tool now
   returns the typical number of real conversations a day, and the agent's instructions ask it
   to compare the day against it.
2. **That fix caused a new failure.** The agent started giving the new comparison *instead of*
   the old one, so it stopped saying the day had 132 posts against a normal 36, which is what
   makes the day unusual in the first place. The next full evaluation caught it (0 of 3). *Fix (skill):*
   the agent's instructions ask for both comparisons.
3. **"Spam" was not specific enough.** Answers called the burst spam without saying it was
   coordinated: many accounts posting the same text at the same time, which is what separates a
   bot campaign from people talking. *Fix (skill):* for a burst of identical posts, the agent's
   instructions ask for how many accounts posted and over what time span, and to call it
   coordinated.

| Evaluation | Date | Runs passed |
|---|---|---|
| `E-d583c183` (first run, before any fix) | 14 Oct | 0 of 3 |
| `E-2824e5be` (after fix 1) | 15 Oct | 2 of 3 |
| `E-07443f38` (full run; fix 1 had caused the new failure) | 15 Oct | 0 of 3 |
| `E-37f9b91b` (after fix 2) | 15 Oct | 1 of 3 |
| `E-db750b64` (after fix 3) | 15 Oct | **3 of 3** |

**The answer now** (run `A-c17347c6`): *"132 mentions versus a median of 36 per day, but only 26
were genuine Brewbird conversations versus Brewbird's median of 20. The spike was driven mainly
by coordinated spam: four repeated BB50 discount texts appeared 84 times from 84 distinct
accounts between 02:00 and 04:59."*

**Why it is real.** The expected answer (132, 36, 26, 20, 84 posts from 84 accounts) is computed
by the oracle, a separate program that reads the raw data and shares no code with the agents.
Each round was a full rerun graded against it, and the counts in the answer can be traced to the
posts behind them with `halyard trace`. To rerun it: `uv run halyard eval --only Q5`.

## The other fixes

| Question | What went wrong | What we changed |
|---|---|---|
| Did Saltmarsh's launch cause the fall in Nitro sentiment? | The answer rightly did not claim cause, but missed the two facts that count most against it: no negative Nitro post names Saltmarsh, and Nitro's conversation volume stayed flat. It also read 200 posts to look for patterns. | **Tool and skill.** The counting tool now shows zeros ("Saltmarsh: 0") and reading posts is paged. The agent tests a suspected cause with counts and reads posts only for examples. A cause question is answered in three parts: what the data shows, what it suggests, and what would be needed to prove it. Cost of the answer fell by about 60%. |
| Is anything going wrong that the brand-level numbers hide? | Weekly complaint counts were attached to the wrong weeks. | **Skill** (output format). Every weekly figure is labelled with its week. |
| Any answer citing a saved web page | The citation pointed at the whole page, not the sentence that says it. | **Graph and tool.** The graph keeps where each page's text starts, so citations point at the exact line of the page. |
| How are consumers reacting to our subscription products? | The agent used the lines' overall sentiment as if it were the reaction to subscriptions. | **Skill** (grounding rules). The agent answers about the thing asked, and says what posts can and cannot show. |
| "So Saltmarsh caused it, right?", and the causation question above | Said what would establish cause but named only quality records, not sales and repeat purchase or a comparison of markets with and without Saltmarsh. | **Skill.** The agent names all three kinds of evidence. |
| How is Brewbird's beer? | Missed that "Brewbird" beer posts are about an unrelated taproom in Pune, and never said what Brewbird does sell. | **Tool and skill.** The coverage tool lists posts that were left out and why. The agent says the posts are about a different business, how many there are, and what Brewbird sells. |
| Is Saltmarsh Nitro half the price in the UAE? | Declined without making the comparison the data does allow. | **Skill.** The agent says the comparison asked for cannot be made, then gives the nearest one that can be made like with like, labelled as such. |
| Reply to review M11441 for us | The draft did not say a person must approve it, and missed what the customer said (a swollen can). | **Skill.** Every draft is marked for a person to approve and send, and answers the post itself. |
| What does Filterhaus charge cafés wholesale? | Lawful alternatives to the gated trade portal were incomplete. | **Skill.** The agent offers three: the public retail price as a ceiling, consented café conversations, and asking Filterhaus. |
| Top complaints, and share of voice | A ranking came without its counts; share of voice came without what was left out. | **Skill and tool.** Rankings give their counts; share of voice gives what was excluded and how sub-brands were counted. |
| The evaluation itself | It marked some correct answers as failures: it compared the wrong scope of mentions, and the judge read wording rather than meaning. | **Eval definition.** We corrected the expected figure, the grader and the judge's instructions, and said so in the report, rather than tuning the agents to pass a faulty test. |
