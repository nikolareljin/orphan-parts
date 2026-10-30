# Meta models

Every call to a Meta model goes through one client against the Model API at `https://api.meta.ai/v1`.
Model IDs are configuration, never literals in code (see [Configuration](../reference/configuration.md)).

| Model | ID (default) | Used for |
|---|---|---|
| [Muse Spark](muse-spark.md) | `muse-spark-1.3` | label extraction with structured output, listing text read into fields, price guidance with search grounding, listing drafts, project proposals through a tool-calling loop |
| [SAM 3.1](sam-3-1.md) | `sam-3.1` | the item, the label and the connector found in a photo, one concept per call; the label crop feeds extraction |
| [Muse Voice Transcribe](muse-voice-transcribe.md) | `muse-voice-transcribe-1.0` | voice notes kept as the owner's words, from the web and from the phone |

Considered and not used in this version, each with its own page saying so:
[Muse Wonder](muse-wonder.md), [Muse Image](muse-image.md), [Muse Glimmer](muse-glimmer.md),
[Muse Spark Open](muse-spark-open.md); there is one provider ([Providers and routing](providers.md)).

Each model page covers its job in the app, the exact request shape, the settings that affect it,
cost notes and failure modes. The rules decide and the model proposes, everywhere: a verdict, a
price, a listing line or a project allocation is kept only where the evidence backs it.

## Fixture mode

With `OPL_FAKE_API=1` the client serves recorded responses from `backend/tests/fixtures/` and
spends nothing. Tests always run this way.
