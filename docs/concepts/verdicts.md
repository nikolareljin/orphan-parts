# Verdict ladder

The buyer comparison ends in exactly one verdict per candidate listing:

| Verdict | Meaning |
|---|---|
| `EXACT_MATCH` | same part number, or every must-equal field equal |
| `COMPATIBLE_LIKELY` | all must-equal fields equal, tolerance fields within range |
| `VISUALLY_SIMILAR` | looks alike, but at least one tolerance field is outside range |
| `CONFLICT` | a must-equal field differs (polarity, connector type) |
| `INSUFFICIENT_INFO` | too little evidence on either side to decide |

Rules come from the category profile. The model writes the explanation shown under the verdict;
it cannot move a `CONFLICT` up the ladder.

!!! note
    Not built yet.
