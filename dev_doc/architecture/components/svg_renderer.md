# `svg_renderer`

Drawing a traced scene as an SVG — a vector image that can be opened in a
browser or an editor, in which every line is still a named thing.

## Concepts this component realises

- **`KB6`** — each drawn element carries the identity of what it draws. A
  ray's line has the ray's identifier; a glass's outline has the glass's
  name; each edge has its label. Opened in a vector editor, the drawing is
  organised in layers — objects, rays, labels — and an element can be found
  by name instead of by clicking near it. The same identities are what make
  highlighting work: a query returns a set of ray identifiers, and
  `draw_scene_with_highlights` draws everything dimmed and then redraws
  just those in colour on top. Later elements in an SVG paint over earlier
  ones, so the highlighted set is drawn last.

- **`KA1`** — the labels in the drawing are the same labels the rest of the
  program uses. An edge marked `W` in the picture is the edge a tool call
  means by `"W"`. Individual edges are made addressable by drawing an
  invisible line over each one that carries the label, rather than by
  cutting the glass outline into pieces, which would break how curves and
  fills are drawn.

- **`KC7`** — the renderer does not import the scene-object classes. It
  works out what to draw by what an object *has* — an outline, a focal
  length, two endpoints — not by asking what class it is. A renderer that
  imported every scene type would have to change whenever one did.

- **`KA8`** — when an AI assistant asks for a drawing, it gets a description,
  not the drawing. The rendering tools in `agentic_layer` call this
  component, save the result to a file, and return the file's location, its
  size, and a sentence describing what was drawn and highlighted. An
  assistant cannot look at an image; a person can open the file.

## Modules

| File | What it holds |
|---|---|
| `core/svg_renderer.py` | `SVGRenderer`: the four drawing layers, the per-object draw methods, `draw_scene`, `draw_scene_with_highlights`, and the annotation helpers — point markers with labels, a direction arrow, an angle arc — for diagrams that need to explain themselves. |

## What it produces

A rendered image, as a string or a file. Not a port: nothing else in the
program reads the drawing back as data. Queries go to the database; the
drawing exists to be looked at.

## What it needs from elsewhere

- The scene and its objects from `core_simulator` and
  `core_scene_objects`, by inspection of what each object has.
- **`P-ROLE-MECHANISM`** from `core_labelling`, indirectly — the edge labels
  it writes into the drawing.

## Promises this component makes and relies on

None of its own. It is a leaf: it reads, draws, and is read by no one.

## How it is shipped

Core package. It needs only the `svgwrite` library.
