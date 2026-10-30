# HTTP API

Interactive documentation is served by the running backend at http://localhost:8000/docs.
The same OpenAPI document is rendered below.

<swagger-ui src="openapi.json"/>

## Feature endpoints

| Path | Purpose |
|---|---|
| `POST /api/extract` | multipart `photos` (one to `MAX_PHOTOS` images, each at most `MAX_UPLOAD_MB`) and optional `crops` (label crops from `/api/segment`): reads the label into typed fields, each with `value`, `unit`, `confidence`, `source` (`photo`, or `label_crop` when crops were sent) and `raw`, plus `item_type`, `label_text`, `warnings`, the counts of photos and crops, the model used, `from_fixture` and `cost_usd` |
| `POST /api/segment` | multipart `photo` (one image) and optional repeated `concepts` (default `item`, `label`, `connector`; an unknown key is sent to the model as its own phrase): one region per match with `concept`, `box` (half-open pixels of the prepared photo), `confidence`, `coverage`, a JPEG `crop` data URL and the mask outline as `svg_path`; plus the `overlay` (the photo with the masks drawn over it), `warnings`, `width`, `height`, the model, `from_fixture` and `cost_usd` |

Errors, for both: `400` for a bad or oversized photo (by upload size or pixel count), a HEIC
file, too many photos or concepts, `422` when the required file field is missing, `502` when the model answer was incomplete or the Model API failed, `503` when the spend
cap is reached or fixture mode has no recorded answer. The `detail` text is safe to show.

## Inventory endpoints

JSON in, JSON out. An item carries its `fields` (the current value per field), every
`assertion` with its `provenance`, `confidence`, `source` and `review` state, the ids of its
separated `components`, and a `version` that every write increments.

| Path | Purpose |
|---|---|
| `POST /api/items` | save an item privately: `extraction` (an answer of `/api/extract`, every field becomes an observed value to confirm) and/or the item's own fields (`name`, `item_type`, `condition`, `faults`, `tests_done`, `accessories`, `location`, `notes`, `intent`, `availability`, `parent_id`); `201` with the item |
| `GET /api/items` | every item not deleted, newest first, without location and notes |
| `GET /api/items/{id}` | the item with its assertions and components |
| `PATCH /api/items/{id}` | change any of the item's own fields; with `version` set, a stale write is refused with `409` |
| `DELETE /api/items/{id}` | hide the item; `204`; its events stay readable |
| `POST /api/items/{id}/fields` | an owner value: `field`, `value`, `unit`, `provenance` (`owner_reported`, `documented`, `tested`, `estimated`); accepted as stated, beside any observation |
| `POST /api/items/{id}/assertions/{aid}/review` | `{"review": "accepted" \| "rejected" \| "proposed"}` for one observed value |
| `POST /api/items/{id}/components` | separate a part into its own item under this one; the parent's faults note it; `201` with the part |
| `GET /api/items/{id}/events` | the history: actor, time, change, version |

Errors: `404` for an unknown item or assertion, `409` on a version mismatch, `422` for a value
outside the allowed sets (intent, availability, provenance, review), a field name that is not
`snake_case`, a blank name, part name or value, an owner value claiming to be `observed`, a
`profile` that is not one that ships, or text
over its bound (names 200 characters, values 500, details and `*_notes` fields 4000). A key sent as `null` in a
`PATCH` means not given.

## Measurement and profile endpoints

| Path | Purpose |
|---|---|
| `POST /api/measure` | multipart `photo` and `request` (JSON: `feature`, `profile`, `image` size as marked, `reference` of kind `two_point` with `points` and `length_mm` or `rectangle` with `corners`, `width_mm` and `height_mm`, each with a `tolerance_mm`, the feature `points`, `straight_on`): the result with `accepted`, `value_mm`, `uncertainty_mm`, `method`, `basis`, every `check` with `passed`, `detail` and `blocking`, `redo` when refused, `px_per_mm`, the marks scaled to the stored photo, `tolerance_mm` and `needs_direct_reading` when the profile names the feature. Nothing is stored |
| `POST /api/items/{id}/measurements` | the same, stored on the item; an accepted capture proposes an observed value (source `measurement`) to confirm; `201` with the measurement (`id`, `assertion_id`, `at`) |
| `GET /api/items/{id}/measurements` | every capture on the item, accepted or refused |
| `GET /api/items/{id}/measurements/{mid}/photo` | the prepared JPEG the marks refer to |
| `GET /api/access`, `POST /api/access`, `DELETE /api/access` | the demo gate: whether a code is needed and whether this caller has a session; the code for a session (a cookie, and the same `token` in the answer for a caller without cookies; 401 for a wrong code, 429 after too many tries); the end of a session. With a code set, every other path but `/healthz`, `/readyz`, `/api/version` and the documentation answers 401 without a session, 429 over an allowance with `Retry-After`, and 503 for a call that spends while `DEMO_PAUSED` is set |
| `GET /api/profiles` | the shipped category profiles with their feature counts |
| `GET /api/profiles/{id}` | one profile |
| `GET /api/profiles/{id}/features` | the features worth measuring, each with `key`, `label`, `unit`, `tolerance_mm` and `how` |
| `GET /api/profiles/{id}/rules` | what a candidate is checked against: each rule with `key`, `label`, `kind` (`equal`, `within`, `at_least`, `at_most`), `unit`, `hard`, `identity`, `tolerance`, `tolerance_pct` and the `question` to ask when the value is unknown |
| `POST /api/assess` | JSON `need` and `candidate`, each an inventory `item_id` or `values` keyed by rule key (a `profile` on the need when no item carries one): the `verdict` from the ladder with its `summary`, every `check` with `status` (`pass`, `fail`, `unknown`), `needed`, `observed`, `unit`, `basis` and the candidate's `backing` (provenance, review, source, uncertainty), the `questions` for the candidate's unknowns, the rules `missing` a needed value and the checks `to_confirm`; 422 without a profile or when both sides are the same item, 404 for an unknown item |
| `POST /api/items/{id}/drafts` | JSON `mode` (`sell` or `give`), `holds_data`, `pickup`, `asking_price` (200 characters each, one line): Muse Spark writes the prose from the item's accepted values and the owner's details, the rules append the disclosures (faults, what was tested, what is included, price or free, pickup) and drop any line that rests on nothing confirmed; the draft comes with `facts` (each naming its field), `uses` (give), `keywords`, `warnings`, `to_confirm`, its `checklist` (`prepare`, `photos`, and `data` when the item holds data), `ready`, `stale` and the `handoff_url`; 201 |
| `GET /api/items/{id}/drafts`, `GET /api/drafts/{id}` | the drafts written for an item, each with `stale` set when the item changed since |
| `POST /api/drafts/{id}/checklist` | JSON `key` and `done`: tick or untick one step; 422 for an unknown step |
| `POST /api/items/{id}/price` | JSON `currency` (ISO 4217, default `USD`), `country` (ISO 3166-1, optional), `city` (optional): Muse Spark searches for listings and sales of the same model, the rules keep only comparables a search result backs; four `quantities` (`asking`, `sold`, `reported`, `estimate`), each with `count`, `low`, `high`, `typical`, `basis`; the backed `comparables` with page and date, the `sources`, how many lines were `dropped`, three `strategies`, `weak` with its reason, `caveats`, `parts` when the item has components, `searches` made, and `stale` when the item changed since; 201 |
| `GET /api/items/{id}/price` | every guidance written for the item, newest last |
| `POST /api/items/{id}/price/reports`, `GET /api/items/{id}/price/reports` | a sale you know of (`price` above 0, `currency`, `sold_on` as `YYYY-MM-DD`, `note` up to 200 characters), kept apart from everything the search finds and counted under `reported` in the next guidance; 201 |
| `POST /api/searches`, `GET /api/searches`, `GET /api/searches/{id}`, `PATCH /api/searches/{id}` | a missing-item search: `need_item_id` or `profile` with `spec` (rule key to needed value), `title`, `max_price`, `currency`, `radius_km`, `budget_left`, `notes`; the answer carries `handoff_url`, the Marketplace search to run by hand, and the candidate count; `PATCH` takes `status` (`open`, `found`, `closed`) and `notes`; 422 without a profile |
| `POST /api/searches/{id}/candidates` | multipart `request` (JSON: `source_kind` `text`, `screenshot` or `manual`, `text`, `values`, `observed_on`, `asking_price`, `currency`, `location`, `included_parts`, `url`, `note`) and the `screenshot` file for a screenshot candidate: the listing read into `fields` with their source, the `assessment`, the `state`, the `questions`, `observed_on` and `expires_on`; 422 for a candidate without its source or a date in the future; 201 |
| `GET /api/searches/{id}/candidates`, `GET /api/candidates/{id}` | the candidates of a search, one candidate |
| `POST /api/candidates/{id}/recheck`, `POST /api/candidates/{id}/withdraw` | the same listing against the need as it stands now (422 once withdrawn); retire a candidate |
| `GET /api/candidates/{id}/questions` | the rules' open questions as a message to the seller: `subject`, `message`, `questions` |
| `GET /api/preferences`, `PUT /api/preferences` | what you want from a build, kept once: `interests`, `effort` (`low`, `medium`, `high`), `skills`, `tools`, `opens_devices`, `budget`, `currency`, `radius_km`, `purchase` (`used`, `new`, `either`) |
| `GET /api/templates` | the projects that may be proposed, kept as data, each with its requirements |
| `POST /api/projects/propose` | JSON `count` (1 to 5) and `note`: Muse Spark reads the inventory and the templates through tools and proposes projects; only a proposal with at least one allocation the inventory backs is kept, every other allocation is `dropped` and said; each becomes a project with `requirements` (`pass` or `unknown`, blocking or not, the search opened for it), exploratory `allocations`, `effort`, `spend_estimate`, `unknowns`, the template's `steps`, `safety` and `sources`; 201; 422 when nothing in the inventory may be used |
| `GET /api/projects`, `GET /api/projects/{id}` | every project with the `budget` line (what the selected set expects to spend, what is left); one project |
| `POST /api/projects/{id}/shortlist`, `POST /api/projects/{id}/select`, `POST /api/projects/{id}/abandon` | move the project; `select` takes JSON `take` and commits the items, reserving them in the inventory; 409 with `conflicts` when an item is committed to another selected project, and `take: true` moves it here and opens the requirement there; abandoning releases what nobody else holds |
| `POST /api/projects/{id}/advance/{to}` | a selected project to `building`, then `done`; 422 otherwise |
| `POST /api/projects/{id}/requirements/{key}/search` | a missing requirement becomes a search request under the requirement's profile, with the budget left as its top price; 422 when the requirement is filled, already searched or unknown |
| `POST /api/projects/{id}/requirements/{key}/fill` | JSON `item_id` and `why`: an item of yours for a requirement the proposal left open; it must be usable and of a kind the requirement takes, and not committed elsewhere; committed at once on a selected project; a search open for the requirement is marked found; 422 otherwise |
| `POST /api/items/{id}/voice` | multipart `audio` (one WAV, at most `VOICE_MAX_SECONDS`): Muse Voice Transcribe turns it into text, kept on the item as `condition_notes` with source `voice_note`, accepted as the owner's words; returns the `transcript`, the `seconds` heard, the cost and the item; 400 for anything that is not a WAV file or is too long |

Errors: `400` for a bad photo, `404` for an unknown item, measurement or profile, `422` for a
`request` that does not parse, a profile that does not exist, or a feature key that is not
`snake_case`.

## Operational endpoints

| Path | Purpose |
|---|---|
| `GET /healthz` | process is up |
| `GET /readyz` | config loaded, Model API mode (`live`, `record` or `fixture`), data directory writable, spend so far against the cap, `paused` once the cap is reached |
| `GET /api/version` | package version, the configured model IDs and the upload `limits` (`max_photos`, `max_upload_mb`) the web form follows |
| `GET /api/spend` | the spend ledger: total, cap, remaining, calls per model with token counts, live versus fixture calls |

Every response carries `X-Request-ID`. Send your own to have it echoed back and used in the logs
and in the spend ledger.
