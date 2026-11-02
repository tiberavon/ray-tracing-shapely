---
id: C-EYE-03
title: An apparent source's symmetry (revolve/extrude) determines whether alpha_from_axes needs one clamped value or a clamp-then-average of two
parties:
  provides: eye_safety (angular_subtense.py's alpha_from_axes)
  relies:   any caller assembling alpha_long_rad/alpha_short_rad for a real optical design (a human or an agent evaluating a real laser/lamp product)
port: P-HAZARD-ROUTINES
viewpoint: physical
status: documented
failure_mode: silent
checked_by: null
witness: null
tracked_by: null
conflicts_with: null
refines: null
rationale: null
since: 0.5
---

# C-EYE-03 — Whether a source is round or long changes how its apparent size is computed

**Assumptions.** Whoever computes a source's angular size for a hazard
limit has decided how many independent sizes the source has: one, for a
round (revolved) source; two, for a long (extruded) one, which is then
clamped on each axis and averaged, as the standard specifies.

**Guarantees.** None yet, by construction. The function `alpha_from_axes`
does the right thing given two sizes — pass the same size twice and it
reduces cleanly to the round case. What it cannot do is decide which case
applies. The projection model already records the symmetry for the
photometric conversion, but nothing yet reads that and feeds it into the
angular-size computation. This contract reserves the place where that
link belongs.

**Invariants.** The function is symmetry-agnostic on purpose.

**Units and frames.** Radians.

**If the assumption is violated.** Silent. A long source treated as round
gets a wrong apparent size and a wrong limit, both plausible.

**Checked by.** Nothing yet.
