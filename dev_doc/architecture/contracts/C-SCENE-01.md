---
id: C-SCENE-01
title: A scene file opens as the scene that was saved -- the same objects in the same order, the same names and rays, a designed element rebuilt from its recipe -- and an object that would not come back the same is refused, by name, before anything is written
parties:
  provides: whoever builds the scene being saved (a person, a notebook, a builder), and a package that adds a designed element (register_recipe)
  relies:   anyone who opens the scene again, or changes one of its parameters and opens it
binds:      analysis_run_registry (scene_file), core_scene_objects (BaseSceneObj's construction record)
port: P-SCENE-FILE
viewpoint: structural
status: enforced
failure_mode: loud
checked_by: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_scene_file.py::test_every_recipe_and_primitive_round_trips_through_a_file; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_scene_file.py::test_a_loaded_scene_traces_the_same_rays; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_scene_file.py::test_one_argument_changed_in_the_file_is_the_constructor_with_it; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_scene_file.py::test_parts_come_back_as_their_owners_own_objects_once; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_scene_file.py::test_a_designed_element_edited_after_it_was_built_is_refused; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_scene_file.py::test_shared_names_and_unknown_classes_are_refused; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_scene_file.py::test_a_file_that_cannot_be_read_is_refused
witness: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_scene_file.py::test_every_recipe_is_registered; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_scene_file.py::test_the_construction_record
tracked_by: null
conflicts_with: null
refines: C-LABEL-01
rationale: KC2
since: 0.4
---

# C-SCENE-01 — A saved scene opens as itself, or is not saved

A scene built in a notebook exists only while the notebook runs. A scene
file keeps it. The point of keeping a designed element — a collimator, an
RR lens — as the constructor and arguments that built it, rather than as
its outline, is that a later reader can change one argument and get the
element that argument gives. That only means something if the file, opened
unchanged, gives back exactly the scene that was saved.

**Assumptions.**
- Every object in the scene is a primitive the file knows by its type name,
  or a designed element whose constructor is registered as a recipe.
- A designed element is as its constructor left it. Moving it, rotating it,
  or editing one of its fields afterwards makes it a different element from
  the one its recipe builds.
- Names, where given, are unique.

**Guarantees.**
- **Opened, it is the same scene.** `load_scene` gives the objects in the
  saved order, with the saved names, roles and hand-set edge labels; each
  object's `serialize()` equals the original's, and a trace of the opened
  scene gives the same segments as a trace of the saved one.
- **A recipe is rebuilt by its constructor.** Changing one argument in the
  file and opening it gives what the constructor gives with that argument.
- **A part comes from its owner.** An object an element's constructor made
  (an XR concentrator's primary mirrors, an RXI's mirror) is taken from the
  rebuilt element, once, so the two cannot disagree and a part is not
  duplicated.
- **Checked before it is written.** Every object is rebuilt from what the
  file will hold and compared with the original. One that would not come
  back the same is refused, by name, saying how it differs; nothing is
  written.
- **A file it cannot read is refused,** not guessed at: another schema, a
  later major version, an unknown type, recipe or setting, or arguments the
  constructor refuses, each with the object's name.

**Invariants.** The file holds no live object: only numbers, text, lists
and records. Opening a file does not change it.

**Units and frames.** The scene's own. Lengths are in its length unit and
angles in degrees where an argument's name ends `_deg`; the file adds none.

**If the assumption is violated.** Loud. The silent alternative was the
reason for the check: a designed element moved after it was built saves as
its recipe, which builds it where it was before the move, and the scene
opened again would look right and trace the element in the wrong place.

**Checked by.**
- Every registered recipe and the primitives, in one scene, saved, opened,
  and compared object by object, with the settings, a role and an edge
  label.
- A collimator, a prism, a point source and a detector traced before and
  after, segment by segment.
- One argument changed in the file against the constructor called with it.
- An XR concentrator with its mirrors and an RXI with its mirror, the parts
  coming back as their owners' own objects, once.
- The refusals: a moved prism; shared names (nothing written); a class
  neither registry knows; another schema; a later version; an unknown
  recipe, type or setting; an argument the constructor refuses.
