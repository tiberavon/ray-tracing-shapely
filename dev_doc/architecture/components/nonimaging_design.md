# `nonimaging_design`

Building the shapes of concentrators and lenses from the rules that define
them, rather than drawing them.

A nonimaging optic — a concentrator that gathers light from a range of
angles onto a small receiver — has a shape that follows from what it must
do: the acceptance angle, the receiver size, the refractive indices. Those
shapes have published construction methods. This component implements the
methods, so that a caller states the requirement and gets the geometry.

## Concepts this component realises

- **`KC2`** — every class here is constructed from its optical requirement.
  A `DTIRCPrism` takes an edge angle and a wall count. A `RefractometerPrism`
  takes two refractive indices and the internal path length, and derives
  every vertex so that a ray entering square-on strikes the measuring
  surface at exactly the critical angle. Below a certain critical angle the
  shape degenerates, and the constructor raises rather than producing a
  trapezoid with a negative base.

- **`KD5`** — the construction primitives are tested against the textbook.
  `nonimaging_geometry.py` holds the book's own building blocks — line
  intersection, vector refraction, constant-optical-path point construction
  — and the tests compare their output to the intermediate values the book
  publishes for its worked examples. The reference material is the test
  oracle, which is rare and worth having. The two LED collimators are
  checked the same way against an outside reference: the patent's drawing
  for the `TIRCollimator`'s computed dimensions, and Optiland's sequential
  engine, which receives the designed faces (`P-DESIGNED-FACES`) and must
  send every ray from the source out parallel, as the 2D trace does.

- **`KD9`** — the chapters those methods come from are transcribed in the
  private repository and never published. The code, the citations by
  chapter and section, and the tests against published values all ship. The
  text does not.

- **`KA1`** — each element's surfaces carry a role and a mechanism. A
  `RefractometerPrism` knows which edge is its entrance face and that light
  refracts there. This is what a downstream 3D bridge dispatches on, and
  what a signature is written in. The three flat prisms — refractometer,
  equilateral, right-angle — carry them on every edge; an edge nothing is
  meant to happen at, such as a dispersing prism's base, is a `blocker`
  with no mechanism. A `SingletLens` — one piece of glass with two
  spherical or flat faces — carries them too: its front face `S1` is the
  entrance and refracts, its back face `S2` is the exit and refracts, and
  its rim is a `blocker`. The two LED collimators carry them as well: a
  `TIRCollimator` names its faces as the patent it follows does (`12a`,
  `12b` refract; `22c` is `tir`; the mount `22d-back`, `22d-side` has no
  mechanism), and a `FresnelLens` names its `FLAT` face, `CAP`, facets
  `F1..` and risers `R1..` (all refract) and its `RIM` (none). The SMS
  elements carry them as well (`label_sms_edges`, in the table below), so
  their profiles export and rebuild like the lenses'.
  `BasePrism.from_profile` reads the tags back: given a `profile.json`, it
  builds an element whose edges have the profile's names, roles and
  mechanisms, where `from_vertices` would number them.

- **Mirrors** carry them too. A `ConicMirror` — a piece of a conic section
  (parabola, ellipse, hyperbola) given by vertex, axis, vertex radius and
  conic constant, intersected exactly — its circle case `CircularArcMirror`, and a
  `SplineMirror` through designed points and normals are walls that reflect; the object's `name` is the surface's label. A flat
  `Mirror` with a name exports the same way. `export_sheet_profile` writes
  a set of them, mirror-symmetric about an axis, as a revolve profile with
  `body: "sheet"`: a paraboloid, an ellipsoid, a sphere or a cone.
  `mirrors_from_sheet_profile` is its inverse: the 2D mirrors back, each
  with its label and role, the far side mirrored unless an azimuth cut
  removes it, and a curve or flat mirror the axis cut joined into one.

- An element's edges are its **physical surfaces**: a straight edge, a
  whole circular arc, or an exact conic or spline edge. In the stored
  outline an arc takes three points (its start, a point it passes through,
  its end), and a conic or spline edge two, the first carrying the curve's
  description; either way it is one edge, with one label, one length
  measured along the curve, and one entry in a profile. A spline edge is a
  curve through designed points with the exact direction given at each, so
  a face designed point by point keeps the design's own normals.

## Modules

| File | What it holds |
|---|---|
| `base_prism.py`, `equilateral.py`, `right_angle.py`, `refractometer.py` | The prism family. `BasePrism` owns the two-label scheme, the per-surface edge methods (`spans`, `get_span_curve`, endpoints and arc length), and the two escape-hatch constructors: `from_vertices` (corners only, numbered edges) and `from_profile` (a `profile.json`, labelled edges, arcs and revolve half-sections included). An edge whose mechanism is `reflect` is mirror-coated by the glass itself (`edge_reflects`). |

| `lenses/singlet.py` | `SingletLens`: a labelled lens built from its two radii, centre thickness, semi-diameter and refractive index. Radii follow Optiland's sign convention — positive when the face's centre of curvature lies downstream, in the direction the light travels — so the same numbers describe the lens in both programs. It gives its paraxial focal lengths, and converts a `SphericalLens` (the drawing-tool lens, whose radii are named by side rather than by which face the light meets first). |
| `lenses/tir_collimator.py` | `TIRCollimator`: the LED collimator of US 7,762,697 B2, FIG. 3, as a section to revolve: a central lens (flat rear face, front face designed to collimate a point F) inside a ring (cavity wall, a face designed to send the light of F out parallel by total internal reflection, a flat exit face, a mounting protrusion). Both designed faces are exact points with exact normals, built by constant optical path length, stored as spline edges; the central face can instead be its best-fit conic. Defaults are the patent's figure read in units of its 1 mm chip. `design` reports where each channel begins and ends, in angles from F, and the margin over the critical angle. |
| `lenses/fresnel.py` | `FresnelLens`: a straight-facet Fresnel collimator for a point F, its grooves towards F or away. The central cap is exact (a conic, or a spline for grooves facing away, or that spline's best-fit conic); each facet is tilted so that the ray of F through its middle leaves parallel; risers lean by a draft angle. |
| `lenses/collimator_design.py` | The constructions both collimators share: a ray through a flat face, the face behind it that collimates a point (a Cartesian oval), the inverse (the ray that reaches a given point), points and normals as a spline edge, and a least-squares conic fit. |
| `lenses/profile_scan.py` | A measured lens face. `read_profile_scan`: a profilometer's ASCII DXF (`POINT`, `LINE`, `LWPOLYLINE`, `POLYLINE`; anything else refused by name), in one plane, the unit stated by the caller; each meridian a chain of short segments, long segments and stray points returned as references. `fit_scan_asphere`: an even asphere with its vertex and tilt, by Levenberg–Marquardt on the sag (numpy only); the residual's RMS, PV and slope with the slope's noise floor; the parameters' correlation, with a warning for each pair not separately determined; the number of terms by the RMS gain of one more; K fixed or free; with a design, the form error. The two models of a scanned face (`scanned_face`): `fitted`, the asphere, and `as_measured`, the asphere plus the residual's even part smoothed by local quadratics, as a spline with tangents from the smooth fit; the odd part, the asymmetry one meridian shows, reported (`residual_parts`). `fit_record`, a span's record for `profile.json`'s `fit`; `symmetry_record`, assumed for one meridian, the spread between several, refused past a tolerance unless accepted. `export_profile` takes the records (`fit=`). |
| `mirrors/conic.py` | `ConicMirror` and `CircularArcMirror` (formerly `ArcMirror`, a name left to the JavaScript simulator's three-point mirror): exact curved mirrors in 2D. A ray meets the curve where a quadratic says it does, and reflects about the exact normal: no sampled facets. Only the branch through the vertex, and only where it is single-valued along the axis, is the mirror — exactly what Optiland's `ConicGeometry` describes, so a revolve of it is exact. The profile export of a set of mirrors (`export_sheet_profile`) lives in `profile_export.py`. |
| `mirrors/spline.py` | `SplineMirror`: an exact freeform mirror in 2D, on the cubic Hermite curve a glass's spline edge is, through designed points with designed normals (an SMS primary). A ray meets it where the curve's cubic segments cross the ray, found exactly, and reflects about the curve's normal there: exact at its points, and between them to the interpolation, which falls as the cube of the spacing. It exports as a sheet whose span is a spline starting on the axis, on one of its points; a spline mirror crossing the axis between its points is refused. |
| `mirrors/sheet_profile.py` | `mirrors_from_sheet_profile`: a `body: "sheet"` profile's mirrors rebuilt in 2D — a line span as a `Mirror`, a conic as a `ConicMirror`, a circle as an `CircularArcMirror`, a spline as a `SplineMirror` through its points and their mirror images — each sample checked against its curve. The sheet counterpart of `BasePrism.from_profile`. |
| `dtirc.py`, `angle_transformer.py` | A dielectric total-internal-reflection concentrator, and a four-mirror angle transformer — the book's worked examples. |
| `rxi.py`, `rxi_direct.py` | A closed-form RXI dome, and the complete RXI of Chaves section 9.7 (Figure 9.70), built by the direct method: the start AC and DE, the receiver cavity MN and its mirror image joined by a cubic, then top and bottom portions alternating inward, each at the optical path of an edge ray through the cavity (`RefractedEikonal`, `eikonal_reflect_step`). The top's centre is mirrored out to M, where the ray from R2 meets it at the critical angle. Its edge rays land on the receiver's edges to 2e-3 over most of the aperture outside the central shadow; the start's portion and the chain's inner end are not edge-ray designed. |
| `sms_chain.py`, `rr_lens.py`, `rx_concentrator.py`, `xr_concentrator.py` | The simultaneous-multiple-surface chain and the elements built with it. `grow_sms_chains` grows the chains as the book does, one from every seed point, each ending where its surface does (the RX's top ends where it no longer faces both bundles). With it, `RRLens` reproduces Example 9.1's complete point lists (26 on each surface; built in its own frame about the vertical line E1/E2 and R1/R2 are mirror images about, which it checks, so a lens placed anywhere is the same lens) and `XRConcentrator` Example 9.2's (42 on the primary, 45 on the lens). `RXConcentrator` is the RX of Chaves eq. 9.34: one dielectric, light refracted at the top, reflected off the coated bottom, onto a receiver inside facing down. `XRConcentrator` is the XR: a dielectric under the receiver, closed by a straight top, and its primary apart from it in air, a `SplineMirror`. Its lens curls back toward the axis past its widest point, so it is cut there into pieces of the one spline over narrower domains (`R1` through the axis, `R2` beyond): each revolves single-valued in r. With spline surfaces, the RX's and the XR's edge rays land on the receiver's edges to 1e-4. Each SMS element labels its surfaces with role and mechanism (`label_sms_edges`: RR `N`, `X`; RX `R`, mirror `X`; the RXI `TOP`, mirrors `MT` and `MB`, cavity `CAV`; a surface drawn as several edges numbered from the axis), and its mirror is its own glass's coating, a `reflect` edge, not mirror objects laid on it. Each designed surface is one exact spline through the chain's points with the chain's normals (`spline_outline`; split at a corner; it and `label_sms_edges` read the far half as the near half's mirror about the element's axis, `axis_x`, so an element placed anywhere is the same element), or, with `edges="polyline"`, the chain's polyline. |
| `nonimaging_geometry.py` | The book's construction primitives. |
| `prism_utils.py`, `tir_utils.py` | Dispersion formulas, critical-angle helpers, and the derivation behind the refractometer's constructor. |
| `profile_export.py` | Writing a `profile.json` for the 3D bridge, with the `sources` the element is designed for. `BasePrism.from_profile` is its inverse. |
| `sources/source_spec.py`, `sources/ray_set_source.py` | The source half of the handoff (`P-SOURCE-SPEC`): `validate_source_spec`, a patch's frame and its exact section by the scene plane (`source_axes`, `patch_centre`, `patch_section`), `build_source_2d`, and a profile's sources (`profile_sources`, `merged_sources`). A measured LED (schema 1.4): `rayfile_source_spec` writes one (path, parser format, the file's count, flux and digest, the slice), `spec_rayfile` reads its file back and refuses another; in 2D it is its recorded slice, checked. `RaySetSource` emits a given list of rays, independent of the scene's ray density. The 3D builder is the bridge's (`optiland_scene_bridge`). |
| `sources/rayfile.py` | A measured LED's rays (`P-RAYFILE`): `read_rayfile` (IES TM-25, only the layout checked against a file), `write_tm25` (the same layout, for synthetic files), `intensity_vs_angle` (the far field, flux per steradian against the angle from the axis). numpy only. |
| `sources/rayfile_slice.py` | A rayfile in a 2D section of a symmetric optic (`C-SOURCE-03`): `slice_rayfile` turns each ray about the axis into the plane with its direction kept, keeps those passing within a stated distance of the axis, and reports `skew_share`, the flux it could not keep; `RayfileSlice.source_2d` emits them. |
| `sources/radiation_plot.py` | A rayfile's radiation pattern and its slice's (`C-SOURCE-03`): `radiation_pattern` (intensity against the signed angle from the axis: the 3D half averages, the 3D cross sections in the plane and across it, the slice scaled to the whole flux; the share within stated angles), `radiation_plot_svg` (drawn as a datasheet draws it, cartesian or polar, with svgwrite). |
| `sources/rayfile_slicing_flow.py` | Choosing a slice's limit on h (`C-SOURCE-03`): `RayfileSlicingFlow` asks for a rayfile and its package's footprint, checks the rays start inside it, slices at the footprint's half diagonal in equal steps (10 by default), and tabulates the flux each limit keeps, with the exact limits at the ends of a kept range (50% to 75% by default). It does not choose: it asks for the choice (a kept share or a limit), with the table as the question's context, and optionally writes the source, with its slice, into a `profile.json`. A machine of `eye_safety_classification_flow`'s `ObservableFlow`; needs the `eye-safety` extra, so `sources` does not import it. |

## What it produces

- **`P-PROFILE`** — a `profile.json`: for each span of the outline (one
  physical surface), its exact shape (a line, a circle with its centre and
  radius, a conic, or a spline through designed points), points along it
  with the exact outward normal at each — the two ends of a straight span,
  33 evenly spaced points on any curved one by default — its role and
  mechanism, a symmetry declaration saying how the 2D outline becomes a 3D
  solid, and the physical/numerical parameter
  split. For a solid of revolution only the half of the outline on one side
  of the axis is written, after checking that the outline is a mirror image
  of itself across that axis. Built for straight-edged prisms,
  `SingletLens`, `TIRCollimator` and `FresnelLens`, and for sets of mirrors
  (`export_sheet_profile`), and for the SMS elements: `RRLens`,
  `RXConcentrator`, `RXIOpticDirect` and the `XRConcentrator`'s dielectric
  as solids, its `SplineMirror` primary as a sheet.
- **`P-SLICING-RUN`** — a rayfile slicing session's folder: its questions
  and answers as events, the table of limits on h and the choice as its
  result.
- **`P-DESIGNED-FACES`** — `TIRCollimator.section_faces`: the collimator's
  optical faces as exact points and normals in its own frame, for a tracer
  that is not given a profile.

## What it needs from elsewhere

- **`P-ROLE-MECHANISM`** from `core_labelling` — the words each surface is
  tagged with.
- `core_scene_objects`'s glass classes — every element here *is* a glass,
  with a computed outline.
- `ObservableFlow` and `explain_field` from `flows`, and `checked_scalar`
  from `optical_elements_units`: the machine, its questions and its quantity
  check, for the rayfile slicing flow only (`P-SLICING-RUN`).

## Promises this component makes and relies on

| Contract | This component's part |
|---|---|
| `C-PROFILE-01` | **Owns** it. A profile handoff carries position and exact normal per span, plus the construction parameters, so the receiving side never has to re-derive a normal from neighbouring points. |
| `C-BRIDGE-06` | **Owns** it, with `optiland_scene_bridge`. `from_profile` keeps every edge's name, role and mechanism, and refuses an outline that does not close, winds clockwise, carries a wrong normal, or has a point on a curved span that is off the curve (circle, conic or spline) the span declares. |
| `C-SOURCE-01` | **Owns** it, with `optiland_scene_bridge`. A source specification is validated here, and its 2D source is its exact section by the scene plane, with the same emission law. |
| `C-SOURCE-02` | **Owns** it, with `optiland_scene_bridge`. A rayfile is read only in the layout checked against a file; every other is refused by the field that differs. |
| `C-SOURCE-03` | **Owns** it, with `optiland_scene_bridge`. A rayfile slice keeps each ray's direction, keeps only the near-meridional rays, and reports the share it could not keep, and its radiation pattern against the LED's. |
| `C-LABEL-02` | **Implements** it. The class owns each surface's role; the template that assembles a compound device owns how they compose. |

## How it is shipped

Core package, under `optical_elements/prisms/`.
