# Providers and routing

One provider: the Meta Model API, through one [client](model-api-client.md). Each job names its
model by a setting (`MODEL_SPARK`, `MODEL_SAM`, `MODEL_VOICE`), so a model ID is configuration
and never a literal in code, and the client prices each call from the published rates of the
model it was made to. Fixture mode (`OPL_FAKE_API=1`) is the one alternative: recorded answers,
nothing spent.

Routing a job to another provider, a local open-weight model or a hosted one, is under
[Next steps](../project/next.md); the client's interface (one `respond`, one `transcribe`, one
tool loop) is the seam it would go behind.
