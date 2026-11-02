---
key: KB7
title: Why 3D verification uses Optiland, and why the bridge runs both ways
one_line: Three properties separate Optiland from the field — not that it is Python-native — and the bridge exports a 2D profile into it and imports the polished result back, because a one-way export ends in a dead end.
status: active
informs: [optiland_scene_bridge, optiland_sms_plugin, optiland_nsq_run_registry, nonimaging_design, C-3D-01, C-PROFILE-01, C-BRIDGE-01]
since: 0.1
---

A design made in two dimensions is checked by building it as a
three-dimensional solid and tracing rays through it in Optiland, a separate
optics library. The outline crosses over as data — each surface's
position, its exact outward direction, and what it is for — and the bridge
builds the solid from that, with neither program needing to know the
other's internal types.

## The reasons are not the obvious one

"It is written in Python and works in a notebook" is true of several tools
and decides nothing. Three things set this one apart:

- **It can be differentiated.** The design methods used here give a
  physically sound starting shape, but a starting shape is not a finished
  one. Being able to compute how the trace changes when the shape changes
  is what lets the shape be *polished* toward a goal rather than searched
  for by trial and error.
- **It traces non-sequentially.** In a concentrator, a ray may hit any
  surface in any order. A tracer that assumes a fixed sequence of surfaces
  cannot model that; this one does not assume it.
- **It accepts plug-in geometry.** A shape designed here can be registered
  as a native kind of surface rather than approximated by whatever built-in
  shapes happen to exist.

## The bridge has to go both ways

Sending a design out to be checked is only half of it. If the 3D trace can
polish the shape, the polished shape has to come *back* to the environment
where designs are built, labelled, traced in 2D and compared — or the
checking is a dead end.

So there is one bridge with two doors, not two bridges. Two components
whose names differed only in word order would have been a permanent source
of confusion for no benefit.

## What crosses and what does not

The handoff is geometry, not procedure: positions and exact directions per
surface, plus the settings the shape was built from. It is not a mesh and
not a call into either program. That keeps the two sides independent, and
makes the handoff format checkable on its own.

Each surface's label — entrance, wall, absorber — decides what kind of 3D
surface it becomes, and a label with no mapping is an error rather than a
default. A silent default would place a surface that traces plausibly and
is not the surface that was designed.

## What this does not claim

That the 3D solid is complete. Solids built by extruding an outline have no
end caps, and are not checked for being closed. A ray aimed even slightly
along the extrusion direction leaves through the open end, and nothing
reports it. That is a known limit with a known cause, written down, not an
assumption that it does not matter.

## Read also

- **KB5** — [shapely_provides_the_2d_geometry_predicates](KB5_shapely_provides_the_2d_geometry_predicates.md) — the 2D side this hands off from
- **KC7** — [headless_components_never_import_the_visualization_ones](KC7_headless_components_never_import_the_visualization_ones.md) — the dependency rule the bridge follows
- **KD3** — [assertions_go_where_a_failure_would_be_silent](KD3_assertions_go_where_a_failure_would_be_silent.md) — why an unmapped role is loud
