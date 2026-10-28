# Muse Spark

Vision extraction with structured output, tool-calling steps inside the agent, search grounding
for part numbers, and the explanations under each verdict. Runs at low reasoning effort for
parsing.

## Label extraction

One call per request, however many photos (up to `MAX_PHOTOS`, default 4):

- **Input.** The instructions describe the job (report only what is printed, confidence per
  field, leave out unsupported fields). The user message carries the field list from
  `app/extract/fields.py` and one `input_image` part per photo. Photos are re-encoded first:
  EXIF applied and dropped, longest side `IMAGE_MAX_PX` (default 1280), JPEG. JPEG, PNG, WebP
  and GIF up to 50 megapixels are accepted; HEIC is refused with a message to export as JPEG.
- **Output.** `text.format` is the strict JSON schema of `LabelReading`: `item_type`,
  `label_text` (a transcription) and a list of `{name, value, unit, confidence}`. The reply is
  validated back into the model; anything else is a `502` for the caller.
- **Effort and size.** `reasoning.effort` is `EXTRACT_REASONING_EFFORT` (default `low`),
  `max_output_tokens` is 800. The recorded one-photo call uses 1,480 input and 310 output
  tokens, about 0.003 USD at the standard rate.
- **Operation name** `extract`, which is also the name of the recorded fixture that answers
  every extraction in fixture mode.

The code path is `app/extract/service.py`; the normalisers in `app/extract/normalize.py` turn the
printed values into comparable ones, see the [evidence model](../concepts/evidence.md).

```bash
python -m app.extract photo.jpg          # prints the extraction as JSON
./dev shell backend                      # then the same inside the container
```
