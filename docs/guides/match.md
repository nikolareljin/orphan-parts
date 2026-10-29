# Does it fit?

A candidate is checked against what is needed, one rule at a time, and gets one verdict from
the [ladder](../concepts/verdicts.md). The rules come from the item's
[category profile](../concepts/profiles.md); the evidence comes from the inventory or from values
written in. No model takes part.

## Two sides

- **The need**: what the part must satisfy. Either another inventory item (the laptop that needs
  an adapter, the vacuum that lost its tool, with the required values recorded on it under
  *Add what you know*), or values written straight into the form.
- **The candidate**: the item whose page you are on. Its values are the ones it currently shows:
  accepted ones first, else the latest observation still to confirm, each with its provenance.
  A value that came from a [measurement](measure.md) carries its uncertainty into the check.

Needed values are written in the candidate's terms: for a vacuum tool, the needed
`opening_inner_diameter` is the wand's outer diameter. A side can be an item and values at
once; a written value replaces the item's for that key. Numbers are compared in the rule's
unit: a value on either side recorded or written in another unit (`3300 mA` against a rule in
amps) stays unknown and asks for the right one.

## Rules

Each rule names a key, whether it is **hard** (decides the verdict) or **soft** (reported), and
how it compares:

| Kind | Passes when |
|---|---|
| `equal` | both sides read the same after the label normaliser (polarity, connector, part number) |
| `within` | the candidate is within the tolerance of the needed value: an absolute amount, a percentage, or the larger of the two |
| `at_least` | the candidate is at least the needed value, less any slack |
| `at_most` | the candidate is at most the needed value, plus any slack |

A numeric check takes the candidate's uncertainty into account. A measured 4.55 mm ± 0.3 mm
against 4.5 mm ± 0.1 mm is neither a pass nor a fail: the check stays **unknown** and asks for a
caliper reading. A rule marked `identity` (part or model number) is soft, and a pass on it makes
the match `EXACT_MATCH`.

## What comes back

The verdict with the one line that decided it, every check with the needed value, the
candidate's value and its backing (provenance, whether it is still to confirm, its uncertainty),
the result and the basis in words; the **questions** to ask the seller for every unknown on the
candidate's side; the rules the need gives no value for; and the checks that rest on
observations not yet accepted.

## In the web app

On an item's page, **Does it fit?** lists the other items under *Needed by*; pick one, or leave
*Values written in* and fill the rules' fields, then **Check fit**. The verdict, the checks and
the questions appear under the form.

## From the API

```bash
curl -s localhost:8000/api/assess -H 'content-type: application/json' -d '{
  "need": {"profile": "power_adapter", "values": {"output_voltage": "19.5 V", "polarity": "center positive"}},
  "candidate": {"item_id": 3}
}'
curl -s localhost:8000/api/profiles/power_adapter/rules
```

See [HTTP API](../reference/http-api.md) and the [profile schema](../reference/profile-schema.md).
