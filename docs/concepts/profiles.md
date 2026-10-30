# Category profiles

A profile is a YAML file that makes the engine understand one kind of part: which fields to read,
how to normalise them, what the segmentation prompts are, what counts as a match, how the listing
should read, which Marketplace and catalog category it maps to, and which questions to ask before
posting.

Three profiles ship:

- `vacuum_attachment`: the deep one, used in the demo; the opening and the insertion depth decide fit.
- `power_adapter`: volts, amps, polarity and the plug's two diameters.
- `generic_item`: the fallback for anything not yet specialised; free-form attributes, no strict verdicts.

The owner picks the profile on an item, on a search request or on the **Does it fit?** panel.
See [Creating a new category](../guides/new-category.md) and the
[profile schema](../reference/profile-schema.md).

## Built so far

Three profiles ship as YAML under `backend/app/profiles/data/`, loaded and validated at startup:
`vacuum_attachment`, `power_adapter` and `generic_item`. Each names its **features**: the
dimensions that decide fit, with a tolerance in millimetres and how to capture each one; the
[measurement](../guides/measure.md) step reads them. Each also names its **rules**: what a
candidate is checked against, hard or soft, with the kind of comparison, the tolerance and the
question to ask when a value is unknown; [Does it fit?](../guides/match.md) applies them and the
[verdict ladder](verdicts.md) reads the result. Fields, prompts and listing templates join the
same files next. The model never edits a profile.
