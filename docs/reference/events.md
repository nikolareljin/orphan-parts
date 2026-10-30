# Events and history

Nothing runs in the background: every call does its work within the request and answers when
it is done, which is why a model call can take a few seconds. What the service keeps track of
is history, not progress.

## The item's history

Every change to an item writes one event: `actor` (always `owner` today: the web app, the
phone and the command line all act for the owner), `at`, a `change` in plain words and the item
`version` it produced. `GET /api/items/{id}/events`
lists them. The changes written today:

| Change | When |
|---|---|
| `created from a label reading with <n> observed field(s)` or `created` | an item saved from a reading or by hand |
| `changed <fields>` | the item's own fields edited |
| `<field> accepted` / `rejected` / `proposed` | an observed value reviewed |
| `<field> set to <value> (<provenance>)` | an owner value added; a voice note kept writes its line the same way |
| `<feature> measured: <value> ± <uncertainty> mm (<method>)` / `<feature> capture refused: <reason>` | a measurement made, or refused with the reason |
| `sale reported: <price> <currency> on <date>` | a sale the owner reported |
| `component separated: <name>` and `separated from item <id>` | a part given its own record, on both items |
| `sell draft written (v<n>)` / `give draft written (v<n>)` | a listing draft |
| `price guidance written (v<n>)` | a guidance |
| `uses written (v<n>)` | what the item is good for, asked |
| `decided: <choice>: <note>` | the owner's decision (`keep_build`, `sell`, `give`, `not_worth`), with the note when given; the intent it implies is set in the same change |
| `search opened: <title>` | a missing-item search for what the item needs |
| `proposed for: <project>` / `put on: <project>` | an allocation, by a proposal or by hand |
| `deleted` | the item hidden |

Drafts, guidances and packs carry the item or project version they were written from, which is
how `stale` is decided: a later version means an input changed.

## The request's trail

Every response carries an `X-Request-ID` (an incoming one is honoured), and every log line
written while handling it carries the same id, including the model call lines with their cost
([Observability](../operations/observability.md)). The spend ledger line for a call carries the
request id too, so a figure in the ledger can be traced to the request that spent it.

## Not yet

Progress over a stream for a long call, and a queue for work that outlives a request, are not
needed by anything built; they are under [Next steps](../project/next.md) with video capture.
