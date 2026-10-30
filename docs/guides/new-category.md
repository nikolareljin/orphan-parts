# Creating a new category

A category is a profile: one YAML file under `backend/app/profiles/data/`, loaded and checked at
startup. Nothing else changes when a profile is added; the model never edits one.

## Write the file

```yaml
# backend/app/profiles/data/hose_fitting.yaml
id: hose_fitting                 # must equal the file name
label: Hose fitting
description: >
  A push-fit or threaded fitting between a hose and a tap or a tool; the thread or the
  outer diameter decides fit.
features:
  - key: outer_diameter
    label: Outer diameter
    unit: mm
    tolerance_mm: 0.5
    how: >
      Photograph the fitting end-on with a ruler across it, straight on, and mark the two
      outer edges.
rules:
  - key: outer_diameter
    label: Outer diameter
    kind: within
    hard: true
    question: What is the outer diameter of the fitting, in millimetres?
  - key: thread
    label: Thread
    kind: equal
    hard: true
    identity: false
    question: What thread does it have, as printed on it or on its packaging?
```

Every key is described in the [profile schema](../reference/profile-schema.md). A feature is a
dimension worth measuring, with its tolerance and how to capture it; a rule is what a candidate
is checked against, hard or soft, with the question to ask when the value is unknown. Rule keys
may be feature keys, label fields or any other `snake_case` name a listing or an owner might
supply.

## Check it

```bash
./dev test backend
```

The loader refuses a file whose `id` differs from its name, a repeated rule key, a `within` rule
without a tolerance, an `equal` rule with one, or a `kind` that is not one of the four, and
says which. `GET /api/profiles` lists what loaded; `GET /api/profiles/hose_fitting/rules` shows
the rules as the matcher reads them. In the web app the profile appears wherever one is chosen:
on an item, on a search request, on the **Does it fit?** panel.

## Use it

Set the profile on an item, measure its features, and the rules apply to any candidate: a
listing brought back for a search, or another item. A project template that needs such a part
names the profile in its requirement (`profile: hose_fitting`), so a missing requirement opens
a search under it; see [Build and reuse](reuse.md).

## Not yet

A profile drafted by a model from a few example photos, for you to review before it is saved,
is under [Next steps](../project/next.md).
