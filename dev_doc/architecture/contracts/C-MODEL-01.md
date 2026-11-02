---
id: C-MODEL-01
title: Geometric optics is assumed valid; the model has no meaning at feature sizes approaching λ
parties:
  provides: whole stack (no single owning component — see note below)
  relies:   every component
port: null
viewpoint: model validity
status: documented
failure_mode: silent
checked_by: null
witness: null
tracked_by: null
conflicts_with: null
refines: null
rationale: null
since: 0.1
---

# C-MODEL-01 — This is ray optics, and stops being meaningful at very small sizes

**Assumptions.** The features in your scene — lens apertures, prism
faces, detector widths — are much larger than the wavelength of the light.
For visible light, that means comfortably above a micrometre.

**Guarantees.** Given that, light travels in straight lines between
surfaces, bends at surfaces according to Snell's law, and splits into
reflected and transmitted parts according to the Fresnel equations. That
is what the engine computes.

**Invariants.** Nothing in the codebase models diffraction, interference
or coherence. There is no switch that turns them on.

**Units and frames.** Not applicable.

**If the assumption is violated.** Silent. The engine will trace rays
through a slit narrower than the wavelength and report a perfectly
plausible result, which will be wrong, because at that scale light does
not behave as rays.

**Checked by.** Nothing. This is a statement about where the model
applies, and no test can decide whether your device is inside it.
