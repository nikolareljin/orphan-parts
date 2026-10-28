# Evidence model

Every value the app shows carries its provenance:

```
Field(value, unit, confidence, source)
```

- `value`, `unit`: normalised per the profile (volts, amps, millimetres, free text).
- `confidence`: 0 to 1, from the model's structured output or from the matcher's rule.
- `source`: one of `label_crop`, `grounding_citation`, `voice_note`, `user_edit`, `video_frame`.

The evidence table in the UI, the listing generator and the matcher all consume this one shape, so
they work for any profile.

!!! note
    Not built yet.
