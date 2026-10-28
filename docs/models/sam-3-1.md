# SAM 3.1

Finds the item, its label and its connector in a photo from short text prompts, one concept
per call, and returns a box and a pixel mask for every match. The masks become the overlay in
the UI and the crops the next step reads; the label crop is what Muse Spark extracts from when
segmentation runs first. Video tracking (the sharpest label frame from a short clip) is not
wired in yet.

## Segmentation

- **Request.** `POST /v1/responses` with `model` `sam-3.1` and one user message holding an
  `input_text` part (the noun phrase, for example `product label with printed text`) and one
  `input_image` part (the prepared photo as a JPEG data URL). `metadata` asks for
  `include_confidence` and the `one_bit` mask encoding, which is the smaller payload. One
  concept per call; the default set is item, label and connector, so a photo costs three calls.
- **Output.** Plain text in a line grammar: a frame marker, then one record per match with a
  box token (`x1, y1, x2, y2` inclusive, plus the image size the model saw) and a mask token
  (a raster the size of the box, base85 encoded). Meta's `meta-sam-parser` package validates
  the grammar and decodes the masks; `app/segment/parse.py` reduces its records to matches.
  Zero matches is an empty text, which is a valid answer and becomes a warning.
- **Scaling.** The model sees a copy of the photo at most `SEGMENT_MAX_PX` (default 800)
  wide: masks come back the size of their box and decoding them is plain Python, so fewer
  pixels is faster at no cost in boxes. Boxes are reported in the pixels of that copy and are
  scaled onto the prepared photo, clipped, and at most four matches per concept are kept,
  ordered by confidence.
- **Rendering.** `app/segment/render.py` tints each mask in a colour per concept, outlines the
  box, and cuts a crop with an eight percent margin. Both are returned as data URLs, so the UI
  needs no second request. The mask outline is also returned as an SVG path in photo pixels for
  the measurement step.
- **Cost.** 2.50 USD per thousand images; each concept is one image. Fixture mode answers
  from `tests/fixtures/api/responses/segment-<concept>.json`.

Concepts live in `app/segment/concepts.py`; an unknown key is sent as its own phrase, which is
how a new category can ask for `round opening of a hose or tube` before it has a profile.

```bash
python -m app.segment photo.jpg --out out/      # regions as JSON, overlay.jpg and the crops in out/
python -m app.segment photo.jpg --concepts label,opening
```
