---
key: KA9
title: Why every argument is parsed and checked at the agent boundary
one_line: Quantities are parsed from text and dimension-checked, names are resolved against the scene, and SQL is rejected on a forbidden keyword — because design by contract's non-redundancy rule assumes a caller that can be held to a precondition, and this one cannot.
status: active
informs: [agentic_layer, optical_elements_units, eye_safety_classification_flow, P-QUANTITY-PARSING, C-AGENT-01, C-UNITS-02]
since: 0.1
---

Everywhere else in this program, a function trusts what it is given. If the
instructions say *pass a checked quantity*, the function assumes it got
one. Checking again at every step would be waste — that is exactly the
duplication a clear set of promises is meant to remove.

The part of the program an AI assistant talks to is the one exception. It
trusts nothing and checks everything.

## Why the usual rule stops working

A promise binds two parties who can both be held to it. When the caller is
another piece of code, a requirement like *"pass a checked quantity"* means
something: someone wrote that code, that person could be shown the
requirement, and a violation is a mistake with an owner.

An AI assistant reaching a tool is not that party. It has read a
*description* of the tool, not its code, and may have guessed at what to
pass. It was never in a position to accept a requirement. A requirement
with no one to keep it is not a requirement, and relying on one is relying
on nothing. So at this one line, and nowhere else, the direction of trust
flips.

## What "checks everything" means

- A quantity arrives as text — `"30 mW/cm^2"` — and is read, then checked
  for the right *kind* of unit. A bare number is refused rather than given
  an assumed unit, because an assumed unit is how a wrong answer stays
  plausible.
- A name is looked up in the actual scene before it is used, and a name
  that does not exist comes back with the list of names that do.
- A database query is refused if it contains anything that would change
  data rather than read it.
- Where a multi-step flow gathers inputs, checking them is its own visible
  step rather than something buried inside the next one, so a caller can
  watch it fail.

## Why this is not "check everything everywhere"

Because the cost is real and the benefit is local. Checks on every internal
call would bury the actual logic, slow the paths that run millions of times,
and guard against callers who *can* be held to their promises. The rule is
"check where the trust assumption fails", and there is one such place. It is
crossed once per request, which is what makes checking everything there
affordable.

## What this does not claim

That checking makes the assistant right. It makes the assistant's mistakes
*visible* — a plausible wrong answer becomes an explicit failure it can
recover from. Bad input is not prevented; it stops being indistinguishable
from good input.

## Read also

- **KA4** — [agent_tools_return_errors_as_values_not_exceptions](KA4_agent_tools_return_errors_as_values_not_exceptions.md) — what a failed check returns
- **KC4** — [physical_quantities_are_unit_checked_not_docstring_documented](KC4_physical_quantities_are_unit_checked_not_docstring_documented.md) — the unit checking this mandates
- **KD10** — [classification_runs_as_a_state_machine_with_one_fixed_diagram](KD10_classification_runs_as_a_state_machine_with_one_fixed_diagram.md) — validation as an explicit step in a flow
