---
key: KA2
title: Why every query tool has a list or describe counterpart
one_line: A tool taking a glass name is paired with one listing the glass names; a SQL surface is paired with a call describing its tables and columns, so no caller has to guess a legal value.
status: active
informs: [agentic_layer, analysis_run_registry, optiland_nsq_run_registry, C-AGENT-02, C-NSQ-RUN-03]
since: 0.1
---

Every tool that can be asked a question comes with a way to find out what
questions are legal.

A tool that filters rays by the name of a glass is paired with one that
lists the glass names in the scene. A database that answers questions
written in SQL — a standard language for asking questions of tables — is
paired with a call that describes its tables, its columns, and what each
column means. The list of tools is itself a tool.

## What goes wrong otherwise

Take a tool that finds the rays crossing an edge. It needs the name of a
glass and the label of one of its edges. Both are words. Neither has a
list of legal values anywhere the caller can see.

The caller has to guess what the glasses are called, and guess whether an
edge is written `N`, `North`, `entry_face` or `0`. A person guesses once,
reads the error, and adjusts. An AI assistant working from the tool's
description rather than from the scene has nothing to adjust toward: it
produces a plausible spelling, gets an error, produces another, and the
conversation becomes a search over spellings instead of a question about
optics.

The information was there all along. Functions that describe a scene's
objects and their edges existed before the query tools did — they just had
no tool of their own.

## A column the assistant cannot see is not there

Adding a column to a queryable table is two changes, not one: the column,
and its entry in the descriptions that the schema call returns. A column
present in the table but missing from that list is fully populated,
correctly computed, and unreachable — because nothing tells the caller it
exists.

The same holds for a table, a tool, or a parameter. Whatever becomes
askable becomes findable in the same change, or it is not really there.

## Why this matters more than it looks

It lets the assistant fix its own mistakes. One that asks about a column it
made up gets an error, calls the describe function, finds the real name,
and asks again — all inside one conversation, with nobody stepping in. The
descriptions are written for that: they say what a column *means* and in
what units, not just what type it is.

It also lets the assistant get its bearings before asking anything
specific. How many rays are there, what was the total brightness, which
detectors exist and how many hits did each one see. Without those, the
first question is a shot in the dark and every later one is built on it.

## What this does not claim

That every input needs its own listing tool. The test is whether a caller
could construct a legal value without already knowing the answer. A
threshold like *"brighter than 0.5"* needs no list. A name, a label, a
column or a table always does, because those come from a set only the
program knows.

## Read also

- **KA6** — [agents_query_a_database_not_a_function_per_question](KA6_agents_query_a_database_not_a_function_per_question.md) — the database is the thing being described
- **KA7** — [a_tool_is_registered_in_three_places_or_it_is_unreachable](KA7_a_tool_is_registered_in_three_places_or_it_is_unreachable.md) — schema exposure is part of shipping a capability
- **KA9** — [every_argument_is_parsed_and_checked_at_the_agent_boundary](KA9_every_argument_is_parsed_and_checked_at_the_agent_boundary.md) — name resolution at the boundary is where a bad guess is caught
