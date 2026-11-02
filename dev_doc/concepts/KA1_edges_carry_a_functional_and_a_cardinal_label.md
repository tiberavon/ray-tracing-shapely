---
key: KA1
title: Why every edge carries two labels, not one
one_line: >-
  An edge is labelled twice: a functional label saying what it does optically (entrance, wall, absorber, exit), and a cardinal label saying where it points in the scene.
status: active
informs: [core_labelling, core_scene_objects, nonimaging_design, analysis_signature, svg_renderer, optiland_scene_bridge, P-ROLE-MECHANISM, P-SCENE-NAMES, C-LABEL-01, C-LABEL-02, C-VOCAB-01, C-BRIDGE-01]
since: 0.1
---

An optical element — a prism, say — has edges. Each edge in this program
carries two names from two separate lists.

The first name says what the edge **does** in the optical path: *entrance
face*, *exit face*, *measuring surface*, *base*. This is the **functional**
label, and it stays the same however the prism is turned.

The second says where the edge **points** in the scene: *north*, *south*,
*east*, *west*, worked out from where the edge's midpoint sits relative to
the prism's centre. This is the **cardinal** label. Turn the prism and it
changes.

The two overlap in spelling — `E` is *entrance* on one list and *east* on
the other — and that is fine, because whoever asks for a label asks for one
list or the other.

## Why two names and not one

Because a description of a scene uses whichever frame the speaker happened
to be in, and the two frames answer different questions.

*"The edge facing the lens on its left"* is about position. It can only be
resolved against where things are, and it stays true whatever that edge is
for. *"The entrance face"* is about purpose. It can only be resolved against
what the edge does, and it stays true however the prism is rotated.

With only cardinal names you cannot say that two prisms, sitting at
different angles, have the same entrance face. With only functional names
you cannot say where anything is.

## What the functional names make possible

Two designs, simulated separately, have nothing in common that the computer
could match up: every ray and every surface gets a fresh internal identity
each time. What they *can* share is a vocabulary. If both call their
light-collecting surface *entrance* and their light-catching surface
*absorber*, then a route through one — *entered at the entrance, bounced off
a wall, reached the absorber* — means the same thing in the other. That is
the only reason two independently built optics can be compared at all.

For it to work, the word for what light *did* at a surface — *refract*,
*reflect*, or bounce by total internal reflection — must be spelled exactly
the same in the label list and in the simulator's own record of the event.
If the two drifted apart by so much as a capital letter, comparing two runs
would find no matching routes, and "no matching routes" looks exactly like
"no difference between these designs". A test checks the spellings agree.

## What the cardinal names make possible

A person or an assistant who has never seen the geometry can ask for *"the
west edge"* and get the right one. And when the scene is drawn, the same
labels go into the drawing, so the picture a person looks at and the object
a tool queries agree on what things are called.

## Names have to stay put

A label is only useful if it means the same thing twice. Two ways this has
gone wrong here. A name that had the swept parameter baked into it —
`prism_n1.5`, then `prism_n1.6` in the next run — made every run's
vocabulary unique and broke every comparison. And objects left unnamed
collapsed into one anonymous bucket that could not be told apart. Both
happened, which is why "names stay stable across runs" is now a checked
promise rather than advice.

## What this does not claim

That labels are decoration. The bridge that turns a 2D outline into a 3D
solid looks at each edge's functional name to decide what kind of surface
to build, and an edge with a name it does not recognise is an error rather
than a guess. Labelling that can be skipped will be skipped, and then the
comparison, the description and the bridge all degrade together.

## Read also

- **KB3** — [runs_are_compared_by_ordered_interaction_lists](KB3_runs_are_compared_by_ordered_interaction_lists.md) — the vocabulary this labelling exists to make comparable
- **KA2** — [every_query_tool_ships_a_list_or_describe_counterpart](KA2_every_query_tool_ships_a_list_or_describe_counterpart.md) — labels are only usable if their valid values can be discovered
- **KB7** — [optiland_verifies_2d_designs_in_3d_and_hands_them_back](KB7_optiland_verifies_2d_designs_in_3d_and_hands_them_back.md) — the 3D bridge dispatches on the functional role
