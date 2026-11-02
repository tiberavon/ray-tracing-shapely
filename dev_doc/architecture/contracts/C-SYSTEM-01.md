---
id: C-SYSTEM-01
title: What ray_tracing_shapely as a whole assumes of its user, and guarantees in return
parties:
  provides: whoever builds a scene, runs a comparison, or feeds a result downstream (a researcher/design author)
  relies:   the researcher's own conclusions, Era 5 surrogate (planned), a pyOpenSci/JOSS reviewer assessing scope
port: null
viewpoint: structural
status: documented
failure_mode: silent
checked_by: null
witness: dev_doc/architecture/04_worked_example.md
tracked_by: null
conflicts_with: null
refines: null
rationale: KD11
since: 0.1
---

# C-SYSTEM-01 — What this software assumes of you, all in one place

The other contracts each state one obligation. This one collects the ones
that fall on *the person using the software* rather than on a part of it.

**Assumptions.** You, building a scene, running a comparison, or handing a
result on:

- name your objects with plain words and keep them the same across runs
  you intend to compare (`C-LABEL-01` — checked when two runs are compared);
- give a beam its full spread angle, never negative (`C-BEAM-01` — checked);
- when you convert to physical units, say whether your source is revolved,
  extruded or neither, and match that when comparing to a 3D result
  (`C-UNITS-01` — the declaration is checked; the 3D comparison does not
  exist yet);
- keep the settings that describe the device separate from the settings
  that describe the simulation (`C-RUN-02` — the separation is checked;
  which side a setting belongs on is your judgement);
- when comparing two runs, hold the sampling density and the surface
  discretisation fixed, and say what tolerance you used
  (`C-CONV-01`, `C-MATCH-01`);
- stay within ray optics: features well above the wavelength
  (`C-MODEL-01`).

**Guarantees.** Given those, a comparison between runs means what it says,
a physical quantity has the unit it claims, and a route through the optic
has the same description in any run that traced it.

**Invariants.** None of these is inferred by the software. Each is either
checked at the one point it can be, or left to you.

**Units and frames.** As each listed contract states.

**If the assumption is violated.** As each listed contract states. Where a
check exists it is loud; where none can exist, the result is wrong and
looks fine.

**Checked by.** Each listed contract's own test, where it has one.
