# Search

Find a component or a device by text: part numbers, model names, specs. Results are grounded in
search with citations and dates, and anything that cannot be verified says so.

## Built so far

**Find a part**: a search request for something you need, run on Marketplace by you. Say what
is needed, as another item's requirements (a laptop that needs an adapter, a vacuum that lost
its tool) or as values written in under a profile, with a top price, a currency and a radius.
The request carries one link, **Search Marketplace**, that opens the search for you to run;
the service searches nothing, fetches nothing and posts nothing, and never implies a signed-in
session. A link you bring back is kept as given and never opened.

**Bring a listing back** in one of three ways: the listing's text, pasted as it reads, which
Muse Spark reads into fields (the label fields and the profile's rule keys, with a confidence
each; nothing the seller did not write); a screenshot, read by the same extractor as a label
photo; or values you know, typed in, which are your word and replace what was read. Every
candidate carries the day it was seen and the day it is too old to trust (`CANDIDATE_DAYS`,
default 14), the asking price and currency, the place and what is included.

Each candidate goes through [Does it fit?](match.md) against the need as it stands, and the
[verdict ladder](../concepts/verdicts.md) names where it stands: a **documented candidate**
(`EXACT_MATCH`, `COMPATIBLE_LIKELY`), **needs evidence** (`INSUFFICIENT_INFO`, or a
`VISUALLY_SIMILAR` with nothing against it), **conflicting evidence** (`VISUALLY_SIMILAR` with
a soft rule against it) or **rejected** (`CONFLICT`). A documented candidate is not an installed
part. **Recheck** runs the same listing against the need after it changed; **Withdraw** retires
it; **Ask the seller** turns the rules' open questions into a message you can send, written by
the rules, not by a model. A search is marked found or closed by you; a closed one takes no
listing until it is reopened.

## Plan the search

Marketplace has no public search API, and automating or scraping it is against its terms. The
app does neither: it builds search links that you open and run yourself, and it reads the
listings you bring back, pasted as text (several at once) or as screenshots. Nothing is
fetched from Marketplace and nothing is posted to it.

**Plan the search**, in an open search on **Find a part** or under **Find one on Marketplace**
in an item's *Measure and fit* section, is one Muse Spark call (effort `low`, operation
`search-plan`). From the need (its title, the profile, the needed values, the item's values,
the notes and the top price) it writes:

- **Three to six phrasings**, each a short search a seller's title would answer: the plain
  name, synonyms, the part or model number in the ways it gets written, the devices it is sold
  for, seller wording and common misspellings, each with a line on what it finds that the
  others miss. Each phrasing is a link that opens Marketplace's search in a new tab, with
  **Copy** beside it. The link carries the query and the top price
  (`MARKETPLACE_SEARCH_URL?query=...&maxPrice=...`); the radius is not in the link, since
  Marketplace's distance follows the location filter you set there.
- **One match pattern**: a regular expression, applied without regard to case to a listing's
  text, that a fitting listing matches, such as
  `OP-?065-?19-?333|19\.5\s*V.{0,20}3\.3\d?\s*A` for a 19.5 V, 3.33 A adapter.
  Marketplace's search box does not take regular expressions; the pattern only ranks what you
  bring back.
- **Exclusion words** that rule a listing out: the usual ones (*for parts*, *parts only*,
  *broken*, *not working*, *does not work*) and the ones written for this need, such as a
  variant that does not fit. They show as chips; remove one or add your own.

The plan is kept with the search, next to the listings brought back and the candidates.

## The pattern and its limits

The pattern runs on Python's `re`, which backtracks and has no timeout, so it is checked
before it is kept, whether Muse Spark wrote it or you did:

- it compiles, it is at most 300 characters, and it does not match empty text;
- no backreferences;
- no repeated group that repeats or branches inside (`(a+)+`, `(.*)*`, `(\w+\s?)*`,
  `(a|ab)+`); a character class such as `[-\s]?` does the same job safely;
- no open-ended `.*` or `.+` (write `.{0,40}`), no two open-ended repeats side by side
  (`\d+\d+`), and at most six open-ended repeats in all.

Those are the shapes that make a backtracking engine run for minutes on text that nearly
matches. The pattern is also run over the first 4,000 characters of a listing only. A written
pattern that fails the checks is not kept: the plan says why and the field stays empty for you
to fill. **Try the pattern on a line** under the field shows, as you type, how a line scores
and which span matched, through the same checks and engine as the ranking. **Save pattern**
keeps it and scores every listing again.

## Bring back listings

Paste one listing or several into **Bring back listings**: a line of dashes (`---`) between
listings, or a blank line when no listing has blank lines inside. Or choose up to six
screenshots: each is read into text by the label extractor (one call each). Each listing is
scored here, without a model call:

- **fits**: the pattern matches, no exclusion word, and the price is within the limit or not
  stated;
- **maybe**: no exclusion word and within the limit, but the pattern does not match (or there
  is no pattern yet);
- **does not fit**: an exclusion word is in the text, or the asking price is over the limit.

The ranked list puts fits first, then maybe, then the ones ruled out, cheaper first within
each. The matched span is highlighted in green, an exclusion word in red and struck through,
and the reason is written beside the verdict, so a listing that says *never broken* can be read
by eye. Every listing keeps the day it was seen and the day it was brought back.

**Check fit** on a listing is deliberate: Muse Spark reads it into fields once (the same
listing-text reading as below), the profile's rules assess it, and the listing becomes a
candidate with its state and the questions to ask the seller.

## From the API

```bash
curl -s -X POST localhost:8000/api/searches -H 'content-type: application/json' \
  -d '{"need_item_id": 3, "title": "65 W laptop adapter", "max_price": 25}'
curl -s -X POST localhost:8000/api/searches/1/candidates \
  -F 'request={"text": "Orbital 65W charger 19.5V 3.34A, centre positive, $15, Astoria", "observed_on": "2026-10-20"}'
curl -s localhost:8000/api/candidates/1/questions
curl -s -X POST localhost:8000/api/searches/1/plan
curl -s -X PATCH localhost:8000/api/searches/1/plan -H 'content-type: application/json' \
  -d '{"pattern": "19\\.5\\s*V", "exclusions": ["for parts", "12v"]}'
curl -s -X POST localhost:8000/api/searches/1/listings -H 'content-type: application/json' \
  -d '{"texts": ["Orbital charger 19.5V 3.34A, $15", "Charger for parts, $5"]}'
curl -s -X POST localhost:8000/api/searches/1/listings/1/check
```

See [HTTP API](../reference/http-api.md) and the [buyer flow](buyer.md).
