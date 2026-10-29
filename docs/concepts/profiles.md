# Category profiles

A profile is a YAML file that makes the engine understand one kind of part: which fields to read,
how to normalise them, what the segmentation prompts are, what counts as a match, how the listing
should read, which Marketplace and catalog category it maps to, and which questions to ask before
posting.

Three profiles ship:

- `power_adapter`: the deep one, used in the demo.
- `usb_c_charger`: data only, to show a new category needs no code.
- `generic_item`: the fallback for anything not yet specialised; free-form attributes, no strict verdicts.

The first photo is classified into a profile automatically, or the user picks one.
See [Creating a new category](../guides/new-category.md) and the
[profile schema](../reference/profile-schema.md).

## Built so far

Three profiles ship as YAML under `backend/app/profiles/data/`, loaded and validated at startup:
`vacuum_attachment`, `power_adapter` and `generic_item`. Each names its **features**: the
dimensions that decide fit, with a tolerance in millimetres and how to capture each one; the
[measurement](../guides/measure.md) step reads them. Fields, prompts, matcher rules and listing
templates join the same files next. The model never edits a profile.
