---
key: KA7
title: Why a tool is registered in three places
one_line: A tool is callable only if it is defined, catalogued with its schema, and published; two of three fails as though it were never written, so the published list is derived from the catalogue rather than kept by hand, and the agreement is checked by a test.
status: active
informs: [agentic_layer, analysis_run_registry, eye_safety, C-AGENT-02]
since: 0.1
---

A new tool is not finished when the code works. It is finished when an AI
assistant can call it. That takes three things:
- it is defined (`agentic_tools`);
- it is catalogued with its description and parameter schema
  (`tool_registry`);
- it is in the list the server publishes.

Where the tool produces data worth querying, the database's column
descriptions count as a fourth.

The published list is not kept by hand. It is derived: every catalogued tool
except those deliberately withdrawn, each withdrawal written down with its
reason. A package outside the core adds a tool to all three through one call
(`register_tool`), so it cannot land in two of them.

## "Add the exposure later" was tried

A detector-path analysis once shipped as working code with the assistant
side left for a follow-up. In the gap, the capability was real and
unreachable: an assistant could rank every route in the scene but not the
routes that reached the sensor — the reason the feature had been built. The
follow-up did nothing but close that gap.

The lesson is not that the follow-up was slow. It is that *"done"* meant
different things to the person writing the function and the assistant
trying to use it, and only the second definition counts.

## Two out of three fails in a confusing way

A tool in two of the three places exists, has a real name, and may even be
listed in the instructions the assistant was given — and every call to it
fails as if it had never been written. That has happened: four tools were
named in the paragraph a person pastes into the assistant's chat, and none
was in the server's list.

While the lists were three hand-kept literals, that incident was noticed
but never fixed: the paragraph went on announcing the same four tools. In
the meantime three more tools were catalogued under one name and published
under another.

A test of the *count* catches an addition to one list, not a rename or a
swap. So the agreement itself is checked, name by name. Deriving the third
list from the second removes the commonest way to break it.

The check also must not depend on the server's library. A test that skips
whenever that library fails to import also skips when a new release of it
breaks the server. Such a test kept passing in CI while the server could
not start on any fresh install.

## What this does not claim

That everything should be exposed. Many internals should not be — every
exposed tool is carried forever, and adding one is a decision. The rule is
conditional: *if* a capability is meant to be reachable, it becomes
reachable in the same change that creates it. Choosing not to expose
something is fine. Discovering six weeks later that you thought you had is
not.

## Read also

- **KA2** — [every_query_tool_ships_a_list_or_describe_counterpart](KA2_every_query_tool_ships_a_list_or_describe_counterpart.md) — discovery is one of the places exposure must reach
- **KA6** — [agents_query_a_database_not_a_function_per_question](KA6_agents_query_a_database_not_a_function_per_question.md) — data exposure means the query schema too
- **KD12** — [the_tool_list_is_audited_before_it_is_extended](KD12_the_tool_list_is_audited_before_it_is_extended.md) — the counterweight — exposure is a permanent cost
