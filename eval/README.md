# Evaluation runs

`./dev eval` (or `python -m app.eval run` in the backend) writes here: `report.json`,
`report.md`, `charts/fields.png` and `charts/proposals.png` for one load of `demo/set.yaml`
scored by the rules, and `python -m app.eval export` writes `train.jsonl`. Everything but this
file is ignored by git; keep a report you want to compare under another name and run
`python -m app.eval diff a.json b.json`. See the guide
[Training and improving the reads](../docs/guides/improving.md).

`pictures/` is kept in git: `params-v<N>.json` is what version N of the drawing parameters
(`backend/app/picture/params.yaml`) scored on the demo set, written by
`./dev picture-review --evaluate`: the verdicts, the issues by category, each drawing's verdict
and the digest of its recording, and the parameters themselves. See
[Tuning the drawing parameters](../docs/guides/picture-review.md#tuning-the-drawing-parameters).
