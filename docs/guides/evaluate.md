# Find and rank

One need, several candidates, and an honest place for each. This page is about how candidates
are judged and compared; [Find a part](search.md) is the flow that brings them in.

## Built so far

**One candidate at a time.** A listing brought back for a search request is read into fields
(from its text by Muse Spark, from a screenshot by the extractor, or typed in as your word),
dated, and checked against the need by the profile's rules: pass, fail or unknown per rule,
with the candidate's provenance and, for a measured value, its uncertainty. The
[ladder](../concepts/verdicts.md) gives one verdict, and the search page names the state it
puts the candidate in: a documented candidate, needs evidence, conflicting evidence, rejected,
or withdrawn. Every unknown on the candidate's side is a question to ask the seller.

**Several side by side, by hand.** The candidates table on a search lists every listing brought
back with its state, its asking price, the day it was seen and where it came from, so the
documented ones stand out and the rejected ones say why. Open any of them for its checks. A
candidate seen more than `CANDIDATE_DAYS` ago is marked too old to trust; **Recheck** runs it
against the need as it stands now.

**What a fit score is not.** There is none. A candidate is not ranked by a number a model
produced; it is placed by which rules passed, which failed and which are still unknown, and the
asking price is shown beside that, not folded into it.

## Not yet

A comparison view across the candidates of one need, with the fit, the price and the open
questions of each in one table, is on the [roadmap](../project/roadmap.md).
