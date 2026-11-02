# `eye_safety_classification_flow`

Running a safety classification as a series of visible steps, instead of as
one function call that returns an answer.

`eye_safety` can classify a source in one call. This component wraps that
call in a **state machine** — a fixed diagram of steps, each one a box, with
arrows saying which box comes next. As the classification runs, it moves
from box to box, and each box writes down what it checked, against what,
and why. The answer is the same. What is added is the record of how it was
reached, and a way to watch it happen.

A second set of state machines handles the step *before* classification:
gathering the inputs from a person or an assistant, one field at a time,
explaining what each field is and giving an example.

## Concepts this component realises

- **`KD10`** — the diagram never changes shape. Every box is visited on
  every run. A hazard that does not apply to this source still enters its
  box and leaves immediately with a note saying *not applicable*, rather
  than being skipped. This is why the lamp standard's evaluation is fifteen
  boxes — five hazards times three risk groups — instead of five: one box
  showing one result would not match what the underlying function actually
  does. It is also why each standard has its own machine rather than one
  machine that chooses at runtime: a shared machine's diagram would look
  different depending on which standard was picked, and a diagram that
  varies with its input is a diagram nobody can check against the standard.

- **`KD4`** — each box explains itself, and the explaining found bugs. A
  classification box produces a `ComparisonExplanation`: the measured
  value, the threshold, both units, the comparison made, the verdict, and a
  citation to the table and row. Writing that out for one hazard required
  printing the limit's unit, which turned out to contradict the standard's
  table. Nothing had noticed, because until then only the bare number had
  ever been compared, and the number was right. An intake box produces a
  `FieldExplanation`: what is being asked, why, and a worked example. Both
  are reached through one method, `explain_current_state()`.

- **`KA9`** — checking the inputs is its own box. A `validate_dimensions`
  step sits between reading the inputs and the first evaluation. It rejects
  a bare number outright — a number with no unit is not a measurement — and
  confirms each quantity is the right kind, an irradiance where an
  irradiance is expected. It is a visible step so that a caller can see the
  check happen, and see it fail, rather than having it buried inside the
  next box.

- **`KA4`** — a run can be reset. An evaluator that sees the result heading
  the wrong way can trigger `reset` from any box, including a finished one,
  and start again with different parameters. The attempt number is recorded
  on every event, so the log shows all the attempts, not only the last.

## Modules

| File | What it holds |
|---|---|
| `flow_base.py` | `ObservableFlow`: the generic machine. Takes a table of boxes and arrows, records every move as an event, owns `reset` and `explain_current_state()`. |
| `iec62471_flow.py`, `iec60825_1_flow.py` | One table each — the boxes and arrows for the lamp standard and the laser standard. Two tables, one machine class. |
| `intake_flow.py` | Two more tables, for gathering inputs field by field before launching the matching classification. |
| `dimensional_checks.py` | The `validate_dimensions` step: is each input the right kind of quantity. |
| `explanations.py` | `ComparisonExplanation`, `FieldExplanation`, and `summarize_margins` — which criterion came closest to failing. |
| `persistence.py` | Writing a run to disk: an event log, a result file, and a live-state file. No dependency on the machine library, so it can be tested alone. |
| `dashboard.py` | A small web page, served from the standard library, that shows a run's current state and its events as they happen. |

## What it produces

- **`P-CLASSIFICATION-RUN`** — one folder per run: `events.jsonl` (every
  box entered, with its explanation), `result.json` (the final
  classification, latest attempt only), and a live-state file the dashboard
  polls.
- **`P-INTAKE-RUN`** — the same shape, for an intake session, with a link
  from the classification run it launched back to the intake that produced
  its inputs.

## What it needs from elsewhere

- **`P-HAZARD-ROUTINES`** from `eye_safety` — the classification function
  each machine calls, exactly once, unchanged. The machine reports what
  that call did; it never decides anything itself.
- **`P-QUANTITY-PARSING`** from `optical_elements_units` — the stricter
  radiometric check, used by `validate_dimensions`.

## Promises this component makes and relies on

| Contract | This component's part |
|---|---|
| `C-EYE-05` | **Owns** it. The machine's final result equals what calling `classify_measurement` directly gives. A test asserts that every recorded verdict agrees with the direct call, so the explanation can never drift from the answer it explains. |
| `C-EYE-04` | **Relies** on it. Two standards, two separate machines, because the standards are separate formula families. |
| `C-UNITS-02` | **Relies** on it. The dimensional check is `optical_elements_units`'s; this component only decides *where* in the sequence it runs. |

## How it is shipped

Core package, under `optical_elements/eye_safety_classification_flow/`. The
state-machine library and the diagram renderer are optional dependencies;
`persistence.py` needs neither.
