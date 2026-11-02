---
key: KA8
title: Why tool output is summarised, filtered, and sometimes replaced by a descriptor
one_line: Whatever reads a tool result has a finite budget for it, so output leads with a summary, carries only the fields the question needs, and returns a reference when the payload cannot usefully be read.
status: active
informs: [agentic_layer, svg_renderer, optical_elements_physics]
since: 0.1
---

An AI assistant can only read so much before it has to answer. That limit
is a design constraint on every tool it calls, in the same way a memory
limit is a constraint on a data structure. So a tool's answer leads with a
summary, carries only the fields the question asked about, and — when the
real result is something the assistant could not usefully read anyway —
hands back a reference to it instead.

## The failure

A question like *"which rays are inside this glass?"* can match a few
hundred rays. Listing each one in full — both endpoints, brightness in two
polarisations, its total-internal-reflection history, its grazing flags,
which source emitted it — is a faithful answer and a useless one. It can
use up everything the assistant had room to read, leaving nothing for the
next step.

Two specific things go wrong. With no summary, the assistant has to
reconstruct *"230 rays, total brightness 0.83, three with total internal
reflection"* by reading all of it. With no filtering, a question about
polarisation is answered with geometry it never asked for.

Size is not really the test. A small answer can waste space in exactly the
same way.

## Some things are never sent at all

A drawing is the clean case. Sending the assistant the text of an SVG file
spends the whole budget and tells it nothing, because it cannot look at
pictures. So a drawing tool returns a short record instead: where the file
was saved, how big it is, a sentence describing what was drawn, and a
summary of what was highlighted. The assistant gets facts it can use. A
person opens the file.

## The same reason the tools live where they live

The strongest version of this rule is that the big objects never enter the
budget at all. The scene, the traced rays and the ancestry tree stay in the
notebook's memory, and only answers — counts, rows, routes, file locations
— are ever sent. That is a large part of why the tool server runs *inside*
the notebook rather than as a separate program: a separate program would
have to be *sent* the simulation, spending the budget on the input before
any question was asked.

## What this does not claim

That shorter is better. An answer that was cut short and looks complete is
worse than a long one, because the assistant cannot tell. Where an answer is
limited, the limit is stated — *"10 of 230 matching"* — so the assistant can
ask for more or narrow the question, rather than reasoning confidently from
a fraction it took for the whole.

## Read also

- **KD7** — [human_agent_and_tools_share_one_live_kernel](KD7_human_agent_and_tools_share_one_live_kernel.md) — why the heavy objects never enter the budget
- **KA5** — [live_objects_reach_tools_through_an_explicit_registry](KA5_live_objects_reach_tools_through_an_explicit_registry.md) — how tools reach those objects instead
- **KA6** — [agents_query_a_database_not_a_function_per_question](KA6_agents_query_a_database_not_a_function_per_question.md) — query results are the usual output being budgeted
