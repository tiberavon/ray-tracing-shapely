---
key: KA4
title: Why the agentic layer returns errors instead of raising them
one_line: Frameworks disagree about what happens to a Python exception, so a tool returns a structured result carrying either a payload or an error message — the one outcome all of them handle the same way.
status: active
informs: [agentic_layer, optical_elements_units, eye_safety_classification_flow, C-AGENT-01]
since: 0.1
---

When something goes wrong inside a tool an AI assistant has called, the
tool does not crash. It returns an answer that says what went wrong.

Every tool returns the same shape: either `{"status": "ok", "data": ...}`
or `{"status": "error", "message": ...}`. The functions underneath the
tools still stop with an error the ordinary way; the change happens at the
boundary, and only there.

## Why a crash is the wrong answer here

In a program, an error usually stops things. The assistant frameworks that
call these tools disagree about what to do with that. One catches it and
passes the text back to the assistant. One lets it end the whole
conversation. One turns it into a message of its own shape. A tool that
crashes therefore behaves differently depending on which framework loaded
it, and that is not something this project can test or control.

A returned answer has no such variance. Every framework can pass an answer
back, because passing answers back is the one thing all of them do.

## An error is the next question

An assistant that gets a crash has lost the thread. One that gets
*"no object named 'entrance prism'; named objects are: 'main prism',
'sample'"* has been handed what to ask next. So error messages are written
as a step forward: they name the valid options where there is a known
list, and say which requirement was missing where there is not.

The order of the checks matters for the same reason. When several things
could be wrong at once — no simulation loaded, no ray tree, no such glass —
the checks run in a fixed order, so the assistant is told the *first*
missing thing rather than some later consequence of it. Told the real
problem, it recovers in one step.

## Where the line is

Below the boundary, functions crash. A wrong index inside an analysis
routine is a bug, and wrapping it in a polite message would hide it from
the person who can fix it. Above the boundary, what goes wrong is usually
not a bug: a name that does not exist, a simulation not yet loaded, a
search window with nothing in it. Those are answers, and they come back as
answers.

An empty result is not an error. A search that legitimately finds no rays
returns *ok* with an empty list, because *"nothing matches"* is a finding,
and reporting it as a failure would tempt the assistant to retry something
that was never wrong.

## What this does not claim

That the boundary is the only place errors need thought. It fixes their
*form*. What makes a message useful — naming the valid values, ordering the
checks — is work done tool by tool, and no rule about return shapes
supplies it.

## Read also

- **KA3** — [agent_tools_exchange_plain_dicts_and_strings](KA3_agent_tools_exchange_plain_dicts_and_strings.md) — the payload half of the same return shape
- **KA9** — [every_argument_is_parsed_and_checked_at_the_agent_boundary](KA9_every_argument_is_parsed_and_checked_at_the_agent_boundary.md) — what produces most of these errors
- **KD3** — [assertions_go_where_a_failure_would_be_silent](KD3_assertions_go_where_a_failure_would_be_silent.md) — why a returned error beats a plausible wrong answer
