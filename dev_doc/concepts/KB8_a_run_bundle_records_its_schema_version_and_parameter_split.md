---
key: KB8
title: Why a run bundle records its own schema version and parameter split
one_line: A persisted bundle carries a schema version independent of the package version, its parameters split into physical and numerical, and a fingerprint of the scene's object names.
status: active
informs: [analysis_run_registry, optiland_nsq_run_registry, C-RUN-01, C-LABEL-01]
since: 0.1
---

When a simulation run is saved to disk, the saved folder describes itself:
which version of the file layout it uses, its settings sorted into "about
the device" and "about the simulation", and a fingerprint of every object's
name. It does that because the program that wrote it will have moved on by
the time anything interesting reads it.

## The reader is a program that does not exist yet

The point of saving runs is to accumulate them. A model of how a design
behaves across its whole parameter space is trained on hundreds of runs
gathered over months, written by different versions of this software. That
reader cannot be asked to know which version wrote which folder.

So each saved run states its own layout version. The software's version
number would not do: it changes for reasons that have nothing to do with
the file layout, and it does not change when the layout does.

## What has to be in the folder

- **The settings, sorted.** A reader has to be able to tell a physical
  input from a simulation setting, and that distinction cannot be
  recovered from the values alone.
- **The name fingerprint**, so a comparison can refuse to run against a run
  whose objects were named differently. Comparing across mismatched names
  gives an answer that is not wrong but meaningless — and it has happened
  twice.
- **The derived results**, not just the raw output, so a reader is not
  required to re-run the analysis with whatever version of the code matched
  the run.

## Two layouts side by side, not one for both

A 3D trace records different things from a 2D one: it logs *events* — a
ray at a point, heading a certain way, with a certain amount of light —
where the 2D engine logs *segments* with their relationships to glasses and
edges already worked out. Forcing both into one table would mean either
dropping real 3D fields or inventing 2D-only ones. So there are two
layouts, side by side, in the same folder structure with the same settings
file.

The code that runs a query over a saved run does not care what the tables
are called, so two layouts do not mean two query implementations.

## What this does not claim

That the layout is fixed. It carries a version number precisely because it
is not. The promise is that a saved run says which version it is, so a
future reader can refuse it, convert it, or go ahead knowing what it has —
not that no conversion will ever be needed.

## Read also

- **KC3** — [physical_and_numerical_parameters_are_stored_separately](KC3_physical_and_numerical_parameters_are_stored_separately.md) — the parameter split this records
- **KA1** — [edges_carry_a_functional_and_a_cardinal_label](KA1_edges_carry_a_functional_and_a_cardinal_label.md) — where name stability comes from
- **KD8** — [parameter_sweeps_run_as_disposable_headless_notebooks](KD8_parameter_sweeps_run_as_disposable_headless_notebooks.md) — what produces a portfolio
