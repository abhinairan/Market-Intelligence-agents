## Output format

Finish by calling `answer` once, on its own. Do not write the answer as a normal message.

- `answer`: what the reader sees. Lead with the direct answer to the question asked, in one
  or two sentences. Then the figures, in a short table when several are compared (a table
  starts on its own line, after a blank line). When giving a figure per week, label each
  value with its week (a table, or "week of 14 Sep: 7"), never a bare sequence of numbers.
  Then how it was counted, in a line or two. Plain words, no preamble, no closing offer. Put mention IDs
  in brackets after any example or quote, e.g. (M10149).
- `claims`: one entry for every figure or fact in `answer`, each with `cites`: the result
  IDs, mention IDs or `file:row` references it rests on. A claim with nothing to cite does
  not belong in the answer.
- `answerable`: `yes` when the data answers the question, even with stated limits. `partly`
  only when you answer part of what was asked and decline the rest. `no` when it cannot
  answer the main thing asked. A nearby figure offered in place of the answer is not a part
  of it: that is still `no`.
- `needs`: for `partly` and `no`, the data that would answer what you could not. Empty for
  `yes`.
