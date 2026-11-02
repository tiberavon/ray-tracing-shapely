# Conventions

How this tree is written, and what it must never do.

## What this tree is

A flat, current-state catalogue of the codebase: what the components are,
what crosses their boundaries, and what must hold at those boundaries. It is
edited in place. It carries no dates and no history.

It is one of three. `dev_doc/concepts/` says *why* the shape is this shape.
`dev_doc/roadmap/` records decisions in the order they were made and is not
published. See `KD6` — *one tree says what is true now, another says why* —
for why the split exists and what each tree does badly.

## Who this is written for

Someone curious about how the tool works underneath, who has **not**
programmed. Not a contributor, not a reviewer, not the maintainer. A page
that is clear to an experienced programmer and opaque to that reader has
failed, whatever else it does well.

Consequences:

- **Every term of art is explained the first time a page uses it**, in the
  page, in a clause. *A port — something this component makes available for
  other parts of the program to use.* *SQL, a standard language for asking
  questions of tables.* The explanation is short and it is there.
- **Mechanism over abstraction.** "The caller cannot be trusted to satisfy
  any precondition" is compact and means nothing to this reader. "This
  component is called by a language model that read a description of each
  tool, not the code, and may have guessed at what to pass" says the same
  thing and can be followed.
- **An example beats a principle.** Where a concept citation can show a
  real call, a real message, or a real failure that happened, it does. A
  reader who sees *"no object named 'entrance prism'; named objects are:
  ..."* understands errors-as-values without being told the phrase.
- **Length is allowed to grow for this.** A page written this way is
  longer than one written for a programmer. That is the cost of the
  audience, and it is paid.
- **Dry, still.** Didactic is not the same as chatty. No rhetorical
  questions, no "let's", no build-up. Plain statements, in order.

The section headings say what they mean to this reader: *What it produces*,
*What it needs from elsewhere*, *Promises this component makes and relies
on*, *How it is shipped* — rather than the jargon they stand for.

## The rule that governs every page

**A page in this tree never re-tells why.** Every temptation to explain a
decision here is a sign the sentence belongs in a concept, cited by key.

The previous version of this tree broke that rule in a specific way: it
pointed at the roadmap document a decision came from. That satisfied the
letter — the explanation was elsewhere — and failed in practice, because the
roadmap is not published, so the pointer went nowhere a reader could follow.
A concept key is a pointer to something in the same published set.

## Citing a concept

Cite the **key**, then name the concrete thing in this component that the
concept accounts for — a function, a field, a check, a failure that has
happened. Not a restatement of the concept, and not a slogan.

> **KA7** — a tool appears in `agentic_tools`, in `tool_registry`'s
> `_REGISTRY`, and in `mcp_server._EXPOSED_TOOLS`. Tools have been
> advertised in a prompt fragment while missing from the third, and failed
> as though they did not exist. The count is asserted in a test.

Not:

> **KA7** — a capability is unfinished until an agent can reach it. This is
> why registration spans three places.

The second is shorter and says less. It repeats the concept's title back and
leaves the reader with nothing to look at in the code. **If the only thing
that can be written is a paraphrase of the concept, the citation is not
earning its place** — either find the mechanism or drop the key.

Concept keys are greppable: `grep -rn 'KA9' dev_doc/architecture/` finds
every page that relies on one.

## The component page

```
# `component_name`

One-paragraph statement of what it is and what it is for.

## Why this component is different     <- optional; only where one fact explains most of it
## Concepts this component realises      <- the concept-first section
## Modules                                <- a table: file, what it holds
## What it produces                       <- ports, with "port" explained the first time
## What it needs from elsewhere           <- ports consumed
## Promises this component makes and relies on   <- contracts, with "contract" explained
## How it is shipped
```

**`Concepts this component realises` comes first**, before the module list.
A reader who knows which concepts a component is an instance of can predict
most of its shape; a reader given the module list first has to reconstruct
that from the code.

## The contract file

Front matter, then a plain-language title line, an optional one-paragraph
framing for a reader who has never met the idea, and six fixed headings:
`Assumptions`, `Guarantees`, `Invariants`, `Units and frames`, `If the
assumption is violated`, `Checked by`. The skeleton exists because every
heading is falsifiable content — see `KD11`. The prose under each heading
is written for the same reader as the component pages: a term of art is
explained where it appears, and where a promise exists because something
once went wrong, the thing that went wrong is described in a sentence.

```yaml
---
id: C-XXX-NN
title: <the whole obligation, in one sentence>
parties:
  provides: <who must satisfy the assumption — the party who can break it>
  relies:   <who depends on the guarantee>
binds:      <the module the prose is about, when that differs from provides>
port: P-XXX
viewpoint: structural | radiometric | physical | numerical | agentic | model validity
status: documented | enforced
failure_mode: loud | silent | deferred
checked_by: <test path::name, or null>
rationale: <concept key, or null>
---
```

`rationale:` replaces the old `origin:`. It points at the concept carrying
the argument, or is `null` where the contract's own prose is the entire
reasoning — `C-VOCAB-01` is the worked case. **A contract having a
`checked_by` does not mean its reasoning is written down anywhere** (`KD11`);
`rationale: null` is a claim that none is needed, not an admission that none
was found.

Milestone provenance for every unit is recorded in the private tree, not
in front matter here, because it would not survive publication.

## `provides` names who can break it

Not the module the contract is about. A component reading a configuration
cannot violate an assumption about that configuration; whoever supplies it
can. The test: *if this is violated, whose mistake was it?* Put that answer
in `provides`, even when it names a role rather than a module. Use `binds`
for the module the prose describes when the two differ.

## `failure_mode` decides where checking effort goes

| Value | Meaning |
|---|---|
| `loud` | An exception or assertion fires. |
| `silent` | The system keeps running and produces a plausible wrong number. |
| `deferred` | Detectable later, against a schema version rather than at write time. |

Most real defects in this codebase have been `silent` (`KD3`). A
`failure_mode: silent` contract with `checked_by: null` is where the next
one is.

## What this tree must never contain

- A date, or a milestone identifier.
- Narrative: *"raised directly by"*, *"this session"*, *"decided during"*.
- A local absolute path.
- An explanation that belongs in a concept.

These are checked before publication by grep, and the temporal-marker family
has a high false-positive rate, so the output is read rather than trusted.
