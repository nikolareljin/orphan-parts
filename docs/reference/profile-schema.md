# Profile schema

Every key of a category profile YAML file, with its type, default and an example: fields, units, normalisers, segmentation prompts, matcher rules, listing template, category mappings, questions to resolve.

## Keys built so far

```yaml
id: vacuum_attachment          # snake_case, must equal the file name
label: Vacuum attachment
description: >                 # optional
  What this kind of item is and what decides fit.
part_of_device: true           # optional, default false: a part that comes off a device; one
                               # with no identity value of its own asks which device it came from
features:                      # dimensions worth measuring
  - key: opening_inner_diameter   # snake_case
    label: Opening inner diameter
    unit: mm                      # always mm: a measurement is computed in millimetres
    tolerance_mm: 0.5             # what a match may allow; must be positive
    how: >                        # how to photograph and mark it
      Photograph the opening straight on with a ruler across it ...
rules:                         # what a candidate is checked against
  - key: opening_inner_diameter   # a feature key, a label field, or any snake_case key
    label: Opening inner diameter
    kind: within                  # equal | within | at_least | at_most
    unit: mm                      # default: the feature's unit when the key is a feature
    hard: true                    # default true; a soft rule is reported, not decisive
    identity: false               # true for a part or model number: a pass makes it exact
    tolerance: 0.5                # absolute, in the unit; default: the feature's tolerance
    tolerance_pct: 5              # relative to the needed value; the larger of the two applies
    question: >                   # asked when the candidate's value is unknown
      What is the inner diameter of the opening at its widest point?
```

Checks at load time: rule keys are unique, `within` has a tolerance (its own or the feature's),
`equal` has none, `kind` is one of the four. A file that fails validation stops the service at
startup with the reason. The remaining keys (fields, prompts, listing template, category
mappings) follow.
