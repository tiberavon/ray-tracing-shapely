---
key: KD8
title: Why sweeps are run as parameterised notebooks
one_line: A sweep executes the same notebook a person reads, once per parameter set, in a disposable headless kernel — so the swept artefact and the readable one are the same file.
status: active
informs: [analysis_run_registry, nonimaging_design]
since: 0.1
---

A parameter sweep — running the same simulation many times with one
setting varied — is done by taking the very notebook a person reads,
feeding it each set of parameters in turn, and running it without a screen,
once per point, with each run's outputs saved into its own folder.

**The grounding here is partial.** The mechanics are argued — disposable,
parallel, headless runs — and the choice of this particular tool
(papermill) over other sweep runners is not. No alternative was compared.

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

## What it needs from everything else

A sweep only means something if the runs can be compared, which is where
the rest of the machinery earns its place: each run saves its settings
split into "about the device" and "about the simulation", and a comparison
refuses to run across runs whose object names differ. Without those, a
sweep is a pile of notebooks that happen to have run.

## What this does not claim

That the tool was chosen over alternatives. It was adopted, it works, and
the way of working it supports is the one described above. If it were
replaced, the argument above would survive the replacement — which
suggests the concept is about the way of working rather than the tool.

## Read also

- **KD7** — [human_agent_and_tools_share_one_live_kernel](KD7_human_agent_and_tools_share_one_live_kernel.md) — the interactive half of the same environment
- **KB8** — [a_run_bundle_records_its_schema_version_and_parameter_split](KB8_a_run_bundle_records_its_schema_version_and_parameter_split.md) — what each point leaves behind
- **KC3** — [physical_and_numerical_parameters_are_stored_separately](KC3_physical_and_numerical_parameters_are_stored_separately.md) — what a sweep's axis has to be recorded as
