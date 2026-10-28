# Evidence model

Every value the app shows carries its provenance:

```
Evidence(value, unit, confidence, source, raw)
```

- `value`, `unit`: normalised per the field (volts, amps, watts, codes, connector sizes).
- `confidence`: 0 to 1, from the model's structured output or from the matcher's rule.
- `source`: where the value came from. `photo` is a value read from a whole photo;
  `label_crop` is a value read when the label was found first by SAM 3.1 and its crop went to
  the model with the photo. `grounding_citation`, `voice_note`, `user_edit` and `video_frame`
  arrive with grounding, voice notes, editing and video.
- `raw`: the text as it was read, before normalisation, so the user can check the clean-up.

The evidence table in the UI, the listing generator and the matcher all consume this one shape, so
they work for any field set.

## How a reading becomes evidence

1. Muse Spark returns one entry per field it could read, with the value as printed, the unit and
   a confidence. Fields the photos do not support are left out.
2. Entries whose name is not in the field set are dropped with a warning; blank values are
   dropped silently; a field read twice keeps the more confident reading.
3. The field's normaliser cleans the value: `19,5 V` becomes `19.5` with unit `V`, `3330mA`
   becomes `3.33` `A`, `P/N OP065-19-333` becomes `OP065-19-333`.
4. Warnings are added when no part or model number was read and when any field is below 0.5
   confidence. Warnings travel with the result; nothing is silently filled in.

## Regions

A segmentation result is the other half of the evidence: one region per match with its concept
(item, label, connector), its box on the prepared photo, the model's confidence, how much of
the box the mask covers, the crop, and the mask outline. The overlay drawn over the photo is
the same data rendered, so what the user sees is what the next step read.
