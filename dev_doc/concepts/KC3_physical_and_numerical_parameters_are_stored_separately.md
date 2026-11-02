---
key: KC3
title: Why physical and numerical parameters are stored separately
one_line: >-
  `params.json` keeps geometry and refractive index apart from ray density and mesh resolution, because a physical difference between runs should persist as resolution increases and a numerical one should vanish.
status: active
informs: [analysis_run_registry, nonimaging_design, analysis_bidirectional, C-RUN-02, C-CONV-01]
since: 0.1
---

When a run is saved, its settings are kept in two groups. **Physical**:
geometry, refractive index, wavelength, acceptance angle — things about the
device. **Numerical**: how many rays were traced, the brightness below which
a ray is dropped, how finely a curved surface was cut into straight pieces —
things about the simulation. They are never mixed into one list.

## The two behave in opposite ways

Make the simulation finer — more rays, a finer mesh — and run it again. A
difference between two runs that was caused by the physics is still there.
A difference that was caused by the coarseness of the simulation has got
smaller. That is the whole distinction, and it is what makes a comparison
mean anything: a claim that two designs differ is only good if the
difference outlives the coarseness that produced it.

A reader that cannot tell the two apart will, sooner or later, treat a
simulation setting as a property of the device. A model trained on runs in
which the ray count varied alongside the design parameter would learn that
the ray count affects the optics, and report that as physics.

## "Numerical" is two things, not one

The random noise from tracing a finite number of rays, and the error from
approximating a curve with straight pieces, are independent. More rays do
not improve a coarse curve; a finer curve does not reduce the noise. They
have to be checked separately, and mixing them up is the likely practical
mistake: refine one, and the result *looks* converged while the error from
the other is untouched.

Neither has a guaranteed rate at which it shrinks. Cutting a smooth curve
into chords does not come with a clean formula for the error the way some
numerical methods do, so the rate is *measured* from several levels of
refinement rather than assumed.

## A refinement study is just another sweep

The code that compares two runs does not care *why* they differ. So a
convergence study — the same design at several mesh resolutions — is the
same operation as a physical study: one design, a list of runs along one
axis, the same comparison between neighbours. Nothing new is needed on the
comparison side. What is needed is the ability to refine only part of a
surface, and a record of which axis moved.

## What this does not claim

That the numerical settings are uninteresting. Which mesh turned out to be
fine enough is a real result and worth keeping. The claim is that the two
groups answer different questions, and a comparison that cannot say which
it is looking at has not established anything.

## Read also

- **KB8** — [a_run_bundle_records_its_schema_version_and_parameter_split](KB8_a_run_bundle_records_its_schema_version_and_parameter_split.md) — where the split is recorded
- **KB3** — [runs_are_compared_by_ordered_interaction_lists](KB3_runs_are_compared_by_ordered_interaction_lists.md) — the comparison this makes trustworthy
- **KC2** — [elements_are_built_from_optical_requirements_not_vertices](KC2_elements_are_built_from_optical_requirements_not_vertices.md) — why the split falls out of the constructor
