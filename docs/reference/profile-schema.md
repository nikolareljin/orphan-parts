# Profile schema

Every key of a category profile YAML file, with its type, default and an example: fields, units, normalisers, segmentation prompts, matcher rules, listing template, category mappings, questions to resolve.

## Keys built so far

```yaml
id: vacuum_attachment          # snake_case, must equal the file name
label: Vacuum attachment
description: >                 # optional
  What this kind of item is and what decides fit.
features:                      # dimensions worth measuring
  - key: opening_inner_diameter   # snake_case
    label: Opening inner diameter
    unit: mm                      # default mm
    tolerance_mm: 0.5             # what a match may allow; must be positive
    how: >                        # how to photograph and mark it
      Photograph the opening straight on with a ruler across it ...
```

A file that fails validation stops the service at startup with the reason. The remaining keys
(fields, prompts, matcher rules, listing template, category mappings, questions) follow.
