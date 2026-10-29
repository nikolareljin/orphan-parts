# Verdict ladder

Every assessment ends in exactly one verdict. The profile's rules decide it; nothing written by
a model can move a candidate up the ladder.

| Verdict | Meaning |
|---|---|
| `EXACT_MATCH` | an identity rule passes (same part or model number) and no hard rule fails |
| `COMPATIBLE_LIKELY` | every hard rule passes; a soft rule may differ and is reported |
| `VISUALLY_SIMILAR` | no hard rule fails, some hard rules pass, and at least one hard rule is still unknown |
| `CONFLICT` | a hard rule fails: wrong voltage, wrong polarity, a dimension outside its tolerance |
| `INSUFFICIENT_INFO` | no hard rule could be decided either way |

Each rule answers **pass**, **fail** or **unknown**. Unknown is never a pass: a value missing on
either side, a number that cannot be read, or a measurement whose uncertainty straddles the
tolerance all stay unknown, and every unknown on the candidate's side becomes a question to ask.

A profile without hard rules (`generic_item`) reports instead of ruling: `COMPATIBLE_LIKELY` when
every known value fits, `VISUALLY_SIMILAR` when one differs, `INSUFFICIENT_INFO` when nothing is
known.

Rules are data in the [category profile](profiles.md); the [Does it fit?](../guides/match.md)
guide shows them at work.
