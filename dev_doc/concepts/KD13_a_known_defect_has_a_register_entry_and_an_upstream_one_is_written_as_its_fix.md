---
key: KD13
title: Why a known defect has a register entry, and a dependency's defect is written as its upstream fix
one_line: A defect we know about and have not fixed gets a stable id, so "we know" can be told apart from "nobody noticed"; a defect in a dependency is written up as the issue or pull request that would fix it there, and worked around visibly or not at all.
status: active
informs: [optiland_scene_bridge, eye_safety, C-BRIDGE-09, C-BRIDGE-12, C-UNITS-02]
since: 0.3
---

Some things are known to be wrong and are not going to be fixed this week.
A roadmap has no place for them: a planned phase means someone has scoped
the work, and most of these have no scope. Left in a commit message or a
comment, they are indistinguishable from things nobody has noticed. So each
gets an entry in a standing register, with an id that does not change:
`KW-<area>-<nn>` — `KW-EYE-01`, `KW-OPTILAND-04`.

## What an entry is for

**Telling "we know" from "nobody noticed".** An entry states the wrong
behaviour (not the fix), how bad it is, which component it touches, and
which contracts it contradicts. The severity that justifies the register is
*silent-wrong* — wrong, and nothing says so (`KD3`). A page or a report
that mentions the limitation cites the id, so a reader can tell it was
seen.

**Being able to say a limitation is on the register when it is.** A safety
report issued to someone outside the project once said of a live defect
that it was "on our register to fix". There was no register. A document
asserting a control that does not exist is worse than the defect it
discloses. The rule since: a limitation written into a document that leaves
the project has an entry, and the document cites it by id.

## A dependency's defect is written as its fix

This project traces in 3D through Optiland, a library it does not own. When
the bridge finds Optiland doing something wrong, the entry is written as the
issue or pull request that would fix it upstream:

- the upstream commit the defect was measured on;
- a measurement — the input, the wrong output, the right one;
- what it means here: whether this project calls the defective code, and
  what guards against it;
- the smallest correct change upstream, and the test that would have caught
  it, in words that can become the pull request's text.

An entry is closed only when the fix is merged upstream *and* the version
this project depends on includes it.

**Worked around visibly, or not at all.** Optiland's `Volume` decides
whether a solid is closed by sampling each surface's rim and counting how
often rays cross the boundary. It treats every subclass of its conic
surface as a plain conic, so it rejects a solid with a conic zone (a conic
with a hole) that is in fact closed (`KW-OPTILAND-07`). The bridge needs
that check, so it runs its own version — same tolerance, same directions,
same seed, same errors — that asks each surface for its own rims, and the
contract that promises the check (`C-BRIDGE-09`) names the entry. A reader
of the contract sees both what is checked and why it is not Optiland's own
function.

Where a workaround would hide the defect rather than route around it, there
is none. Optiland's tracer can let a ray re-hit the surface it just left,
near the world origin or after a long path (`KW-OPTILAND-05`); the bridge
does not nudge rays to compensate. Its tests place mirrors away from the
origin, and the contract that covers revolved mirrors (`C-BRIDGE-12`) says
so, with the id.

## What follows

**The fix is half-written when the defect is found.** The measurement is
fresh, the reproduction is in hand, and the test that catches it is often
the one that found it. Writing the upstream fix then costs little; writing
it months later means re-deriving all of it.

**A workaround is temporary by construction.** Because the entry says what
the upstream fix is, a workaround in this project's code is visibly a stand-in
for it. When the fix lands upstream, the entry says what to delete.

**Upstream moves.** An entry records the commit it was measured on, and is
re-measured on upstream's current head before it is filed.

## What this does not claim

That every disagreement with a dependency is a defect in it. Where an
upstream *document* gives a number this project's code gets right, that is
recorded where it arises, not here. Nor that the register is published:
it is kept with the project's other working records, and published pages
cite its ids. An id is stable, and an upstream entry becomes public once it
is filed as an issue or a pull request.

## Read also

- **KD3** — [assertions_go_where_a_failure_would_be_silent](KD3_assertions_go_where_a_failure_would_be_silent.md) — why silent-wrong is the severity that matters
- **KD5** — [correctness_is_checked_against_an_external_number](KD5_correctness_is_checked_against_an_external_number.md) — how most of these defects are found
- **KB7** — [optiland_verifies_2d_designs_in_3d_and_hands_them_back](KB7_optiland_verifies_2d_designs_in_3d_and_hands_them_back.md) — the dependency most of the upstream entries are about
- **KD2** — [divergences_from_the_plan_are_written_down_with_their_reason](KD2_divergences_from_the_plan_are_written_down_with_their_reason.md) — the same practice for plans rather than defects
