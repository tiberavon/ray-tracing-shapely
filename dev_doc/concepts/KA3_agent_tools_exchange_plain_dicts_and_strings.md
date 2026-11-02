---
key: KA3
title: Why the agentic boundary speaks plain dicts and strings
one_line: Every framework that calls a tool defines its own tool type, so the boundary uses the representation all of them already consume — JSON-serialisable values, with the metadata in a plain dict.
status: active
informs: [agentic_layer, optical_elements_units, P-QUANTITY-PARSING, C-AGENT-01]
since: 0.1
---

When an AI assistant calls a tool and gets an answer back, what crosses in
each direction is plain data: text, numbers, lists, and simple key-value
records. Never a live object from inside the program. And the description
of each tool — its name, what it does, what it needs — is itself a plain
record, not a type of thing this project invented.

## Why not invent our own

Every assistant framework already has its own idea of what a "tool" is,
and they do not agree. One reads the function's code to work out what
arguments it takes. One cannot do that and needs the arguments spelled out
in a formal list. One wraps the function in a structure of its own. If this
project defined its own tool type, it would replace none of those — it
would become a fourth thing that every framework has to unwrap before
reaching the one it actually wants.

A plain record with a name, the function, and a one-line description is
what every framework can read. Each builds its own representation from it
in a line.

## The arguments are written down, not guessed

Some frameworks work out a tool's arguments by reading its code. That fails
the moment something calls the tool directly, with no framework in between.
So the list of arguments — each with its type and a description — is
written out explicitly, and the descriptions are written for the assistant
that will read them, not for a programmer.

## Live objects stay on this side

A scene, a traced result, or the tree of ray ancestry cannot be an argument.
Turning one into plain data would either lose information or produce
something enormous, and the enormous version lands in the assistant's
limited reading budget. So the assistant sends names and thresholds, and
the tool looks those up against the live objects on this side.

## A physical quantity is one piece of text

An irradiance crosses as a single string, `"30 mW/cm^2"`, with the number
and the unit together, and is read and checked on arrival. Not as a number
in one field and a unit in another. Two fields can disagree, and a caller
that fills in one and forgets the other produces something that looks
complete. One string cannot be half supplied: it either becomes a checked
quantity of the right kind or it fails.

## What this does not claim

That "plain data" means "no structure". A tool's answer always has the same
shape — a status, then either the data or a message — and that shape is as
much a promise as a formal type would be. The rule is against *private*
structure at a boundary whose other side was written by someone else.

## Read also

- **KA4** — [agent_tools_return_errors_as_values_not_exceptions](KA4_agent_tools_return_errors_as_values_not_exceptions.md) — the error half of the same return shape
- **KA9** — [every_argument_is_parsed_and_checked_at_the_agent_boundary](KA9_every_argument_is_parsed_and_checked_at_the_agent_boundary.md) — why the string is parsed rather than trusted
- **KC4** — [physical_quantities_are_unit_checked_not_docstring_documented](KC4_physical_quantities_are_unit_checked_not_docstring_documented.md) — the unit-checking this wire format enables
