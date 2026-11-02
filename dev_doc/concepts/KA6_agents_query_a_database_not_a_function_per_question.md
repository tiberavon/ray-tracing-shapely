---
key: KA6
title: Why the query surface is a database rather than one function per question
one_line: Per-question wrappers were built and found non-composable — each filtered the whole population rather than a previous result — so the query surface became a described schema over which arbitrary queries compose.
status: active
informs: [agentic_layer, analysis_run_registry, optiland_nsq_run_registry, C-NSQ-RUN-03]
since: 0.1
---

The main way to ask a question about a traced simulation is to query a
small database built from that run. Rays, glasses, edges, which rays are
inside which glass, which rays cross which edge, detectors, hits: seven
tables. The assistant writes its question in SQL — a standard language for
asking questions of tables — against a layout it can ask to have described.
There is not a separate function for each kind of question.

## What was tried first

The first version *was* a function per question: rays inside a glass, rays
crossing an edge, rays within an angle range, rays by polarisation. Each
took a name or a number and returned a list. It was defended as combinable
— *the assistant can chain them freely.*

It could not. Each function searched the *whole* set of rays. Ask for
"rays inside this glass", then ask for "rays with high polarisation", and
you got two lists drawn from everything, with no way to ask for the rays
that were in both. No function accepted a previous answer, and none
returned something another would take.

Adding an "intersection" function would not have fixed it. Every combined
question — inside this glass *and* crossing that edge, grouped by which
edge, the three brightest — is a new function under that design, and the
questions worth asking are almost always combined: *of the rays that
reached the sensor, which struck the entrance face above the critical
angle?*

## What a database gives

Combination, for free. Joining two tables is the combined question. Adding
up a column is a distribution. Sorting and taking the top three is "the
most extreme". Adding one *column* — the angle at which each ray crossed
each edge, worked out in advance — makes a whole family of questions
askable with no new tool.

The surface is also smaller. One query tool and one describe tool cover
what a dozen functions covered incompletely, and cover it exactly rather
than approximately: the crossing table records actual geometric
intersections, where the old function had used a nearness rule of thumb.

## The one restriction

A query language accepts anything, so queries are checked for words that
would change the data rather than read it, and refused if any appear. The
database is built once when a run is loaded and read-only after that,
which is what makes the restriction enforceable.

The old one-question functions were not deleted. An assistant's saved
configuration might name them, and removing a published name breaks that
for no gain. They are marked as superseded so nothing new reaches for them.

## What this does not claim

That every analysis belongs in a query. Ranking routes by the energy they
carry walks a tree of ray ancestry, and stays a tree operation. The rule
covers *filtering and counting over the population of rays and surfaces*,
which is what query languages were built for.

## Read also

- **KA2** — [every_query_tool_ships_a_list_or_describe_counterpart](KA2_every_query_tool_ships_a_list_or_describe_counterpart.md) — how a caller learns the schema
- **KA8** — [tool_output_is_budgeted_against_the_context_window](KA8_tool_output_is_budgeted_against_the_context_window.md) — why query results are still shaped
- **KB8** — [a_run_bundle_records_its_schema_version_and_parameter_split](KB8_a_run_bundle_records_its_schema_version_and_parameter_split.md) — the schema that has to outlive the code
