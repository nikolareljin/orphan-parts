# Muse Spark

Vision extraction with structured output, tool-calling steps inside the agent, search grounding
for prices and part numbers, and the explanations under each verdict. Runs at low reasoning
effort for parsing.

## Search grounding

Price guidance is one call with the `web_search` tool and the strict JSON schema of `Findings`
(comparables with their page, the estimate, the basis, caveats):

- **Request.** `tools: [{"type": "web_search", "search_context_size": PRICE_SEARCH_CONTEXT}]`,
  with an approximate `user_location` (country from the request or `PRICE_COUNTRY`, city from the
  request) when one is given, and `include: ["web_search_call.results"]` so the pages the search
  returned come back with the answer.
- **Response.** One `web_search_call` item per search, each with its `results` (title, URL,
  snippet), and `url_citation` annotations on the text. The rules keep a comparable only when
  its page is among those results or citations: the model proposes, the pages decide.
- **Billing.** The API reports no search count, so the client counts the `web_search_call`
  items and records them in the ledger at the published per-query rate, on top of the tokens.
- **Operation name** `price`, which is also the recorded fixture that answers in fixture mode:
  one search, four results, five proposed comparables of which one rests on no result.

The code path is `app/value/service.py`; the [value guide](../guides/value.md) shows what the
four figures mean.

## Listing text

A pasted listing is read with one call and the strict JSON schema of `ListingReading`: the
title, the asking price and currency, the place and what is included as written, and the
fields the text supports with a confidence each. The field names offered are the label fields
plus the search profile's rule keys, so a plug diameter a seller wrote can be read; the
instructions say to leave out anything the seller did not state. Known fields pass through the
same normalisers as a label reading; a rule key the label set does not know is kept as read;
any other name is dropped. Operation name `listing-text`, which is also the recorded fixture.
The code path is `app/find/service.py`.

## Label extraction

One call per request, however many photos (up to `MAX_PHOTOS`, default 4):

- **Input.** The instructions describe the job (report only what is printed, confidence per
  field, leave out unsupported fields). The user message carries the field list from
  `app/extract/fields.py` and one `input_image` part per photo. Photos are re-encoded first:
  EXIF applied and dropped, longest side `IMAGE_MAX_PX` (default 1280), JPEG. JPEG, PNG, WebP
  and GIF up to 50 megapixels are accepted; HEIC is refused with a message to export as JPEG.
- **Output.** `text.format` is the strict JSON schema of `LabelReading`: `item_type`,
  `label_text` (a transcription) and a list of `{name, value, unit, confidence}`. The reply is
  validated back into the model; anything else is a `502` for the caller.
- **Effort and size.** `reasoning.effort` is `EXTRACT_REASONING_EFFORT` (default `low`),
  `max_output_tokens` is 800. The recorded one-photo call uses 1,480 input and 310 output
  tokens, about 0.003 USD at the standard rate.
- **Operation name** `extract`, which is also the name of the recorded fixture that answers
  every extraction in fixture mode.

The code path is `app/extract/service.py`; the normalisers in `app/extract/normalize.py` turn the
printed values into comparable ones, see the [evidence model](../concepts/evidence.md).

```bash
python -m app.extract photo.jpg          # prints the extraction as JSON
./dev shell backend                      # then the same inside the container
```
