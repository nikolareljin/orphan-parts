# The demo set

`set.yaml` names the things in the walkthrough: each one's photos, what the owner knows about
it, whether a draft or price guidance is written for it, the searches with the listings brought
back, and the proposal brief. Everything the model answers for this set is recorded once and
replayed from then on, so the demo costs nothing to run. Each photo also has its own
recordings, as one sample photo sends it: SAM 3.1 on the item, the label and the connector, the
photo read alone, and read with its label crop where SAM found one.

```bash
./dev demo-scrub ~/raw-photos      # re-encoded copies into demo/photos/, WAV notes into demo/notes/
./dev record-fixtures              # with a key: the inventory reset, one run, every answer kept under backend/tests/fixtures
./dev demo                         # the inventory reset and the set loaded, in fixture mode
```

Only the owner's own photos go here, as the scrubbed copies; raw files stay out of the
repository. Listing texts under `listings/` are written examples labelled as such. A file the
set names that is not present is skipped with a note, so the set loads either way.
