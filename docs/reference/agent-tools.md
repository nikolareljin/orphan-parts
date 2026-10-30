# Agent tools

The tools Muse Spark is given, as the Model API sees them. The rules check everything a tool's
answer leads to; a tool never changes the inventory.

## Function tools: project proposals

`POST /api/projects/propose` runs a tool-calling loop ([Muse Spark](../models/muse-spark.md)).
Three function tools, all `strict`:

| Name | Parameters | Returns |
|---|---|---|
| `list_inventory` | none | every item a build may use (not gone, not meant for sale or giving away): `id`, `name`, `item_type`, `profile`, `condition`, `intent`, `availability` and the current `fields` as `value unit` |
| `template_catalog` | none | the projects that may be proposed: `id`, `label`, `goal`, `effort` and the requirements as `key: label` |
| `item_details` | `item_id` (integer, required) | one item in full: the line above plus `faults`, `tests_done`, `accessories` and the ids of its `components`; `{"error": "no such item"}` otherwise |

An unknown tool name is answered with `{"error": "no tool named ..."}` and the loop goes on.
Each step resends the brief, the output items so far and one `function_call_output` per call
matched by `call_id`; the loop ends with the first answer that calls no tool, parsed against
the strict `ProposalSet` schema, and fails after four steps. Side effects: none; the projects
are written by the rules afterwards, from the allocations the inventory backs.

## Built-in tool: web search

`POST /api/items/{id}/price` sends one call with `{"type": "web_search"}`, a
`search_context_size` from `PRICE_SEARCH_CONTEXT` and an approximate `user_location`, and asks
for `web_search_call.results` back. The rules keep a comparable only when its page is among
the results or the citations ([Muse Spark](../models/muse-spark.md)). Side effects: the
searches are counted into the spend ledger at the published per-query rate.

## What is not a tool

Reading a label, a listing's text or a voice note is one structured call each, without tools.
Segmentation, measurement, matching, drafts, the build pack and the share text are the rules'
work; the model has no tool that writes to the inventory, posts anywhere or fetches a page.
