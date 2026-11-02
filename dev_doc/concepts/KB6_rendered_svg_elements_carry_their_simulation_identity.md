---
key: KB6
title: Why every rendered element carries the identity of what it represents
one_line: Each SVG element is tagged with the uuid, name and label of the simulation object it draws, so one artefact serves a person editing it, a highlight query, and a caller that cannot see pictures.
status: active
informs: [svg_renderer, agentic_layer, core_labelling]
since: 0.1
---

A drawing of a traced scene is not just a picture. Every line in it carries
the identity of the thing it draws: a ray's identifier, a glass's name, an
edge's label. The drawing is an SVG — a vector image format that a browser
or a drawing program can open — arranged in layers the way a drawing
program expects.

## One drawing, three readers

Opened in a drawing program, a ray can be selected by its identifier and an
edge by its label, rather than by clicking near it and hoping.

Asked to highlight something, the program uses the same identities: a
question returns a set of ray identifiers, and the drawing routine draws
everything faded and then those rays again, in colour, on top. It draws
them last because in an SVG whatever is drawn later paints over whatever
came before.

For an AI assistant, which cannot look at pictures, the identity is what
makes asking for a drawing worthwhile at all: the tool reports where the
file was saved and what was highlighted, and the file is faithful to the
question because both were built from the same identifiers.

## Edges are laid on top, not cut out

Each edge of a glass needs to be addressable on its own, and the obvious
way — cutting the glass's outline into one piece per edge — breaks how
curves and filled shapes are drawn. Instead, an invisible line is drawn
over each edge to carry its label. The visible outline is untouched; the
addressability is added beside it.

## The drawing code does not know the object types

It works out what to draw by what an object *has* — an outline, a focal
length, two endpoints — rather than by asking what kind of object it is. A
drawing routine that had to know every type of object would have to change
whenever one of them did.

## What this does not claim

That the drawing is a data file. It is a picture that happens to be
addressable, and reading simulation results back out of it would be
recovering data from an image. Questions go to the database; the drawing
exists to be looked at, by a person or by something that can only be told
about it.

## Read also

- **KA1** — [edges_carry_a_functional_and_a_cardinal_label](KA1_edges_carry_a_functional_and_a_cardinal_label.md) — where the labels come from
- **KA8** — [tool_output_is_budgeted_against_the_context_window](KA8_tool_output_is_budgeted_against_the_context_window.md) — why a render returns a descriptor rather than the markup
- **KC7** — [headless_components_never_import_the_visualization_ones](KC7_headless_components_never_import_the_visualization_ones.md) — the same independence, one layer out
