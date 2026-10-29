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

## From the API

```bash
curl -s -X POST localhost:8000/api/searches -H 'content-type: application/json' \
  -d '{"need_item_id": 3, "title": "65 W laptop adapter", "max_price": 25}'
curl -s -X POST localhost:8000/api/searches/1/candidates \
  -F 'request={"text": "Orbital 65W charger 19.5V 3.34A, centre positive, $15, Astoria", "observed_on": "2026-10-20"}'
curl -s localhost:8000/api/candidates/1/questions
```

See [HTTP API](../reference/http-api.md) and the [buyer flow](buyer.md).
