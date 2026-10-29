# My inventory

A private record of what you own: each item with the values read from its label, the condition
and faults you know about, what you mean to do with it, and whether a plan may count on it.
Nothing in it is published. A scan never posts anywhere; a listing draft is a separate step you
approve.

## From a reading to a record

Read a label, then **Save privately**. Every field the model read becomes an **observed** value
on the new item, marked *to confirm*. On the item page you accept or reject each one. A rejected
observation disappears from the item's current values but stays in the record.

Anything you know yourself goes in through **Add what you know**: a field, a value, a unit, and
how you know it (stated by you, documented, tested, estimated). Your value is accepted as stated
and shown as the current one, but it never replaces the observation: both stay, each with its
provenance, so a later reader can see what the label said and what you corrected.

## Condition, intent and availability

| Field | Meaning |
|---|---|
| Condition, known faults, tests done, included accessories | free text, yours |
| Intent | keep, use in a build, sell, give away |
| Availability | available, reserved (a plan counts on it), gone |
| Where it is, notes | private; shown only on the item page, never in a draft or a shared record |

Every edit bumps the item's version and records an event. The page sends the version it last
saw with each change; if the item changed in between, the write is refused and the page shows
the current state instead of overwriting it.

## Parts of a whole

A removable part can be separated into its own record with **Separate a part**: a camera module
from a broken phone, the cable from a charger. The part gets the parent's intent and a link
back; the parent's faults note what left, so a later plan does not count on a whole device that
is no longer whole.

## Measuring

Under **Measure a feature** a dimension is taken from a photo with a scale reference and, when
accepted, proposed on the item as an observed value with source `measurement`. The method, the
checks and the uncertainty are in [Measure a feature](measure.md).

## Deleting

Delete hides the item from the list. The record and its history stay, so an event log is never
missing an item it refers to.

## Storage

One SQLite file, `INVENTORY_DB_FILE` inside `DATA_DIR`, in WAL mode with a versioned schema.
Four tables: items, assertions (one row per value with its provenance, confidence, source and
review state), events (one row per change with the version it produced) and measurements (each
capture with its result and the prepared photo it was made on). Postgres and object
storage are the documented path after the hackathon; the service layer is the only place that
knows SQL.

## API

```bash
# save a reading privately
curl -s -X POST localhost:8000/api/items \
  -H 'Content-Type: application/json' \
  -d '{"extraction": <the answer of /api/extract>, "name": "Desk charger"}'

# list, read, edit
curl -s localhost:8000/api/items
curl -s localhost:8000/api/items/1
curl -s -X PATCH localhost:8000/api/items/1 -H 'Content-Type: application/json' \
  -d '{"intent": "sell", "version": 1}'

# your own value, beside the observed one
curl -s -X POST localhost:8000/api/items/1/fields -H 'Content-Type: application/json' \
  -d '{"field": "output_voltage", "value": "19", "unit": "V", "provenance": "tested"}'

# accept or reject an observation, separate a part, read the history
curl -s -X POST localhost:8000/api/items/1/assertions/3/review -H 'Content-Type: application/json' \
  -d '{"review": "accepted"}'
curl -s -X POST localhost:8000/api/items/1/components -H 'Content-Type: application/json' \
  -d '{"name": "power cable", "condition": "frayed"}'
curl -s localhost:8000/api/items/1/events
```

The full shapes are in the [HTTP API](../reference/http-api.md).
