---
key: KD8
title: Why sweeps are run as parameterised notebooks (papermill), and when they are not
one_line: A sweep of independent points executes, with papermill, the same notebook a person reads, once per parameter set, in a disposable headless kernel — so the swept artefact and the readable one are the same file. A sweep of a scene's parameter runs as a flow with a job per point, and a loop whose next step depends on the last runs as a script.
status: active
informs: [analysis_run_registry, nonimaging_design, flows]
since: 0.1
---

A parameter sweep — running the same simulation many times with one
setting varied — is done by taking the very notebook a person reads,
feeding it each set of parameters in turn with **papermill**, and running it
without a screen, once per point, with each run's outputs saved into its own
folder.

Concretely: a template notebook (the sweep templates, named with a `_pm`
suffix) has a cell tagged `parameters`; a driver script (`papermill_scripts/`, for example
`run_n_sample_sweep.py`, which sweeps a refractometer's sample index) calls
`papermill.execute_notebook` once per value, each in a fresh kernel, and each
executed copy is kept beside the run bundle it saved. papermill is in the
`notebook` extra; no part of the package imports it.

**The grounding here is partial.** The mechanics are argued — disposable,
parallel, headless runs — and the choice of papermill over other sweep
runners is not. No alternative was compared.

## What it buys

**One file.** The thing that runs in the sweep and the thing a reader opens
are the same. A sweep driven by a separate script means the script and the
notebook drift apart, and the notebook is the one people read.

**Nothing carries over.** Each point runs in a fresh process and exits.
Nothing accumulates between points, and a crash in one does not spoil the
rest.

**Parallel for free.** Points are independent processes, so the sweep uses
every core without the analysis code knowing.

**A readable record per point.** Each run leaves behind a notebook with its
outputs in place — a document, not a row in a results table.

## When a sweep is not a papermill run

The way of working above fits a sweep whose points are independent and
whose varied value is something the notebook itself is written around. Two
other kinds of repeated run are done differently, on purpose.

**A scene's parameter, swept as a flow.** When what varies is a parameter of
a saved scene — an object's index, a designed element's argument, a rotation
— the `parameter_study` flow does the sweep: the scene file is the input, the
scene is built at the sweep's ends before anything runs, and each point is a
job (`in_process`, worker processes here, or Modal), never a notebook. What
it keeps from this concept is the substance: points independent, each in a
process of its own away from the kernel, a failing point recorded without
spoiling the rest, each point saved as a run with its parameters split. What
it gives up is the executed notebook per point; its readable record is the
flow's own (its questions and answers, its events, the table and plot), and
the one notebook that started it. It is the form an agent can drive, and the
form that can be sent off this machine, where a kernel per point would not
go.

**A loop whose next point depends on the last.** A convergence study or a
search — refine a mesh until a boundary stops moving, choose the next design
from the last result — is not a sweep: its points cannot be laid out in
advance or run side by side. It runs as one script (`papermill_scripts/
converge_rxi_mesh.py` refines an RXI's mesh level by level this way), each
step still saved as a run so the steps can be compared.

Splitting *one* long run into chunks sent to several workers (a targeted
re-simulation on Modal) is not a sweep either: the chunks merge back into a
single result.

## What it needs from everything else

A sweep only means something if the runs can be compared, which is where
the rest of the machinery earns its place: each run saves its settings
split into "about the device" and "about the simulation", and a comparison
refuses to run across runs whose object names differ. Without those, a
sweep is a pile of notebooks that happen to have run. This holds for all
three kinds above.

## What this does not claim

That papermill was chosen over alternatives. It was adopted, it works, and
the way of working it supports is the one described above. If it were
replaced, the argument above would survive the replacement — which
suggests the concept is about the way of working rather than the tool.

## Read also

- **KD7** — [human_agent_and_tools_share_one_live_kernel](KD7_human_agent_and_tools_share_one_live_kernel.md) — the interactive half of the same environment
- **KB8** — [a_run_bundle_records_its_schema_version_and_parameter_split](KB8_a_run_bundle_records_its_schema_version_and_parameter_split.md) — what each point leaves behind
- **KC3** — [physical_and_numerical_parameters_are_stored_separately](KC3_physical_and_numerical_parameters_are_stored_separately.md) — what a sweep's axis has to be recorded as
- **KD10** — [classification_runs_as_a_state_machine_with_one_fixed_diagram](KD10_classification_runs_as_a_state_machine_with_one_fixed_diagram.md) — the fixed diagram a flow-run sweep follows
