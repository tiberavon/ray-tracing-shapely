# `core_labelling`

A short vocabulary for saying what a surface *does*, so that two different
optical designs can be compared by function rather than by coordinates.

Two lists of words. **Role**: what a surface is for — entrance, wall,
absorber, exit, blocker, source, sample medium. **Mechanism**: what light does
there — refract, reflect, or total internal reflection. Every surface in a
designed element carries one of each.

## Concepts this component realises

- **`KA1`** — the functional half of the two-label scheme. A prism's edges
  carry a label saying what they are optically (*entrance face*) as well as
  one saying where they point (*west*). This component defines the words the
  first kind of label is drawn from. Without a shared list, one design would
  call its light-collecting surface *entrance* and another *aperture*, and
  the two could not be compared.

- **`KB3`** — the vocabulary that makes structural comparison work. When two
  runs are compared, each path through the optic is reduced to a list of
  *(surface, edge, what happened)*. The *what happened* is a `Mechanism`, and
  it has to be spelled exactly the same as the event the engine recorded on
  the ray — `refract`, `reflect`, `tir`. If the two drifted apart even by
  capitalisation, every comparison would find no matching paths and report
  that as "no difference". A test checks the spellings are identical.

## Modules

| File | What it holds |
|---|---|
| `optical_elements/roles.py` | The `Role` and `Mechanism` enumerations, and the `.role` property every scene object gains. |

## What it produces

- **`P-ROLE-MECHANISM`** — the two enumerations. `Mechanism`'s values are
  constrained to equal the strings the engine writes into a ray's
  `interaction_type` field. Nothing imports one from the other; the
  agreement is a convention held in place by a test.

## What it needs from elsewhere

Nothing by import. It agrees with `core_simulator` on four strings, and
that agreement is the contract below.

## Promises this component makes and relies on

| Contract | This component's part |
|---|---|
| `C-LABEL-02` | **Makes** it. Every surface carries a `(Role, Mechanism)` pair. The element's class decides the role of each of its surfaces; the template that assembles elements decides how they compose. |
| `C-VOCAB-01` | **Makes** it. `Mechanism`'s values are string-identical to `Ray.interaction_type`'s. Checked by `test_roles.py::test_role_mechanism_enum_values`. |

## How it is shipped

Core package. It lives under `optical_elements/` because the designed
elements are its main users, but nothing in it depends on them.
