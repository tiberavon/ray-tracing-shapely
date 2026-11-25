"""
Python-specific module: test blocks
Copyright 2026 ray-tracing-shapely authors and contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

===============================================================================
The typed construction surface: value types and blocks
===============================================================================
The vocabulary:
- every type's JSON form round-trips through its live form;
- a wrong unit, a bare number for a quantity, a malformed position, a zero
  direction, an unknown recipe, a missing key: refused, with the reason;
- the wire rule (`accepts`): an integer feeds a number, millimetres feed
  metres, degrees feed radians, a type feeds its optional; not otherwise;
- a type described as JSON reads back as itself.
The registry and the constructors:
- every designed element and every primitive with a schema is a block;
- a designed element built by its block from JSON equals the constructor
  called directly, outline for outline;
- a primitive's block gives the entry its own serialize() does;
- a constructor's refusal is the block's; an unknown or missing input too;
- the argument rules: a refractive index is a number, an angle a quantity in
  degrees, a normal a direction;
- a declared function runs from JSON; the catalogue is JSON and its wires check.
===============================================================================
"""

import json

import pytest

pytest.importorskip("pint")

from ray_tracing_shapely.analysis import scene_file as sf  # noqa: E402
from ray_tracing_shapely.blocks import (  # noqa: E402
    BlockTypeError, block, call_block, catalogue, from_description, get_block, list_blocks, run_block,
    vocabulary, wire_accepts,
)
from ray_tracing_shapely.blocks import types as T  # noqa: E402
from ray_tracing_shapely.core.scene import Scene  # noqa: E402

# --- the vocabulary -------------------------------------------------------------------

ROUND_TRIPS = [
    (T.NUMBER, 2.5), (T.INTEGER, 3), (T.BOOL, True), (T.TEXT, "M1"), (T.Choice(["a", "b"]), "b"),
    (T.Quantity("mm"), "7 mm"), (T.Quantity("deg"), "30 deg"), (T.IRRADIANCE, "12 W/m^2"),
    (T.POSITION, [1.5, -2.0]), (T.DIRECTION, [0.0, 1.0]),
    (T.Optional_(T.Quantity("mm")), None), (T.Optional_(T.Quantity("mm")), "1 mm"),
    (T.ListOf(T.POSITION), [[0.0, 0.0], [1.0, 2.0]]),
    (T.SCENE_ENTRY, {"recipe": "SingletLens", "args": {"thickness": 4}}),
    (T.SCENE_ENTRY, {"name": "M", "object": {"type": "Mirror", "p1": {"x": 0, "y": 0}, "p2": {"x": 1, "y": 0}}}),
    (T.DETECTOR_READING, {"power": 0.5, "hits": 12, "share": None, "centroid": 3.0}),
    (T.CLASSIFICATION, {"group": "RG1"}),
    (T.GLASS_VERTEX, {"x": 0.0, "y": 1.0, "arc": True}),
    (T.JSON, {"anything": [1, "two"]}),
]


@pytest.mark.parametrize("t,value", ROUND_TRIPS, ids=lambda x: repr(x)[:30])
def test_every_type_s_json_form_round_trips(t, value):
    assert t.format(t.parse(value)) == value
    assert from_description(json.loads(json.dumps(t.describe()))) == t


def test_a_quantity_s_live_form_is_a_number_in_its_unit():
    assert T.Quantity("mm").parse("2 cm") == pytest.approx(20.0)
    assert T.Quantity("nm").parse("0.65 um") == pytest.approx(650.0)
    assert T.Quantity("deg").parse("0.5 rad") == pytest.approx(28.6478897565)


REFUSALS = [
    (T.Quantity("mm"), "7 W", "dimensionality"),
    (T.Quantity("mm"), 7, "with its unit"),
    (T.Quantity("deg"), "7", "same \\*kind\\*"),          # pint would read it as 7 rad
    (T.IRRADIANCE, "5 W/(m^2*sr)", "radiometric"),       # a radiance, where an irradiance is wanted
    (T.NUMBER, "7", "a finite number"),
    (T.NUMBER, True, "a finite number"),
    (T.INTEGER, 2.5, "a whole number"),
    (T.POSITION, [1, 2, 3], "a position"),
    (T.DIRECTION, [0, 0], "not zero"),
    (T.Choice(["a"]), "c", "one of"),
    (T.SCENE_ENTRY, {"recipe": "NoSuchLens", "args": {}}, "no recipe"),
    (T.SCENE_ENTRY, {"object": {"type": "Rainbow"}}, "a primitive's type"),
    (T.DETECTOR_READING, {"power": 1.0}, "with hits"),
    (T.SCENE, 42, "a scene file"),
]


@pytest.mark.parametrize("t,value,reason", REFUSALS, ids=lambda x: repr(x)[:30])
def test_what_a_type_refuses_it_refuses_with_the_reason(t, value, reason):
    with pytest.raises(BlockTypeError, match=reason):
        t.parse(value, "here")


def test_the_wire_rule():
    Q = T.Quantity
    assert T.NUMBER.accepts(T.INTEGER) and not T.INTEGER.accepts(T.NUMBER)
    assert Q("m").accepts(Q("mm")) and Q("rad").accepts(Q("deg"))
    assert not Q("deg").accepts(Q("mm")) and not Q("mm").accepts(T.NUMBER)
    assert not T.IRRADIANCE.accepts(Q("W/(m^2*sr)")) and T.IRRADIANCE.accepts(Q("mW/cm^2"))
    assert not Q("deg").accepts(Q("dimensionless"))       # an angle is not a pure number
    assert not T.POSITION.accepts(T.DIRECTION)
    assert T.Optional_(Q("mm")).accepts(Q("cm"))
    assert not Q("mm").accepts(T.Optional_(Q("mm")))         # what may be null must not feed what may not
    assert T.ListOf(T.NUMBER).accepts(T.ListOf(T.INTEGER)) and not T.ListOf(T.NUMBER).accepts(T.NUMBER)
    assert T.Choice(["a", "b"]).accepts(T.Choice(["a"])) and not T.Choice(["a"]).accepts(T.Choice(["a", "b"]))
    assert T.JSON.accepts(T.SCENE)


def test_scenes_and_rayfiles_travel_as_files(tmp_path):
    np = pytest.importorskip("numpy")
    scene = sf.scene_from_dict({"schema": sf.SCHEMA, "version": sf.VERSION, "settings": {}, "objects": [
        {"name": "M", "object": {"type": "Mirror", "p1": {"x": 0, "y": 0}, "p2": {"x": 1, "y": 0}}}]})
    path = tmp_path / "s.scene.json"
    sf.save_scene(scene, path)
    live = T.SCENE.parse(str(path))
    assert [o.name for o in live.objs] == ["M"] and T.SCENE.format(live)["objects"][0]["name"] == "M"
    from ray_tracing_shapely.optical_elements.sources import write_tm25
    ray_path = tmp_path / "r.TM25RAY"
    write_tm25(ray_path, np.zeros((2, 3)), np.array([[0, 0, 1.0], [0, 0, 1.0]]), np.full(2, 0.5))
    rayfile = T.RAYFILE.parse(str(ray_path))
    assert T.RAYFILE.format(rayfile) == str(ray_path)
    with pytest.raises(BlockTypeError, match="existing file"):
        T.RAYFILE.parse(str(tmp_path / "missing.TM25RAY"))


def test_the_vocabulary_is_listed():
    v = vocabulary()
    assert {"number", "position", "direction", "scene_entry", "scene", "rayfile", "detector_reading"} <= set(v)


# --- the constructors as blocks -----------------------------------------------------------

def test_every_designed_element_and_every_primitive_with_a_schema_is_a_block():
    assert set(list_blocks("recipe")) == set(sf.list_recipes())
    with_schema = {k for k in sf.list_primitives() if sf._resolve(sf._PRIMITIVES[k]).property_schema()}
    assert set(list_blocks("primitive")) == with_schema
    assert "RaySetSource" not in with_schema                  # no schema: not a block until it has one


RECIPES = [
    ("SingletLens", {"radius_front": "30 mm", "radius_back": "-30 mm", "thickness": "4 mm", "semi_diameter": "8 mm",
                     "position": [10, 0], "rotation": "90 deg"},
     dict(radius_front=30, radius_back=-30, thickness=4, semi_diameter=8, position=(10, 0), rotation=90)),
    ("EquilateralPrism", {"side_length": "2 cm", "n": 1.6},
     dict(side_length=20, n=1.6)),
    ("TIRCollimator", {"cavity_depth": "6 mm", "exit_tilt_deg": "0.2 rad"},
     dict(cavity_depth=6, exit_tilt_deg=11.459155902616464)),
    ("CircularArcMirror", {"vertex": [0, 0], "axis": [1, 0], "radius": "20 mm", "semi_diameter": "5 mm"},
     dict(vertex=(0, 0), axis=(1, 0), radius=20, semi_diameter=5)),
]


def _outline(obj):
    path = getattr(obj, "path", None)
    if path:
        return [(round(p["x"], 9), round(p["y"], 9)) for p in path]
    return json.loads(json.dumps(obj.serialize()))


@pytest.mark.parametrize("recipe,inputs,direct", RECIPES, ids=[r[0] for r in RECIPES])
def test_a_designed_element_built_by_its_block_equals_its_constructor(recipe, inputs, direct):
    entry = run_block(recipe, {**inputs, "name": "E"})["entry"]
    assert entry["recipe"] == recipe and entry["name"] == "E"
    built = sf.scene_from_dict({"schema": sf.SCHEMA, "version": sf.VERSION, "settings": {}, "objects": [entry]})
    by_block = built.get_object_by_name("E")
    by_hand = sf.recipe_class(recipe)(Scene(), **direct)
    assert _outline(by_block) == _outline(by_hand)


PRIMITIVES = {
    "Mirror": {"p1": [0, 0], "p2": [10, 0]},
    "Beam": {"p1": [0, 0], "p2": [0, 10], "emisAngle": "0.1 rad", "wavelength": "0.65 um"},
    "PointSource": {"position": [1, 2], "brightness": 0.3},
    "Detector": {"p1": [0, 0], "p2": [10, 0], "twoSided": False, "binSize": "0.5 mm"},
    "Glass": {"path": [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 0, "y": 10}], "refIndex": 1.7},
    "IdealLens": {"p1": [0, -5], "p2": [0, 5], "focalLength": "2 cm"},
}


@pytest.mark.parametrize("kind", sorted(PRIMITIVES))
def test_a_primitive_s_block_gives_the_entry_its_serialize_does(kind):
    entry = run_block(kind, PRIMITIVES[kind])["entry"]
    cls = sf._resolve(sf._PRIMITIVES[kind])
    rebuilt = cls(Scene(), entry["object"])
    assert entry["object"] == json.loads(json.dumps(rebuilt.serialize()))


def test_a_primitive_s_quantities_arrive_in_its_units():
    beam = run_block("Beam", PRIMITIVES["Beam"])["entry"]["object"]
    assert beam["wavelength"] == pytest.approx(650.0) and beam["emisAngle"] == pytest.approx(5.729577951)
    det = run_block("Detector", PRIMITIVES["Detector"])["entry"]["object"]
    assert det["binSize"] == 0.5 and det["twoSided"] is False
    assert "wavelength" not in run_block("Mirror", PRIMITIVES["Mirror"])["entry"]["object"]   # a default stays out


def test_refusals_come_back_with_their_reason():
    with pytest.raises(BlockTypeError, match="thickness must be positive"):          # the constructor's own
        run_block("SingletLens", {"radius_front": "30 mm", "radius_back": "-30 mm", "thickness": "-1 mm",
                                  "semi_diameter": "8 mm"})
    with pytest.raises(BlockTypeError, match="'thickness' .* is required"):
        run_block("SingletLens", {"radius_front": "30 mm", "radius_back": "-30 mm", "semi_diameter": "8 mm"})
    with pytest.raises(BlockTypeError, match="no input 'thikness'"):
        run_block("SingletLens", {"thikness": "4 mm"})
    with pytest.raises(BlockTypeError, match="dimensionality"):
        run_block("SingletLens", {"radius_front": "30 mm", "radius_back": "-30 mm", "thickness": "4 W",
                                  "semi_diameter": "8 mm"})
    with pytest.raises(BlockTypeError, match="no block"):
        get_block("Teleporter")


def test_the_argument_rules():
    types = {p.name: p.type for p in get_block("XRConcentrator").inputs}
    assert types["r1"] == T.POSITION and types["p0"] == T.POSITION and types["n0"] == T.DIRECTION
    assert types["n"] == T.NUMBER and types["theta_deg"] == T.Quantity("deg")
    assert types["wavefront_offset"] == T.Quantity("mm")
    arc = {p.name: p.type for p in get_block("CircularArcMirror").inputs}
    assert arc["vertex"] == T.POSITION and arc["axis"] == T.DIRECTION
    singlet = {p.name: p for p in get_block("SingletLens").inputs}
    assert singlet["radius_front"].required and singlet["radius_front"].type == T.Optional_(T.Quantity("mm"))
    assert run_block("SingletLens", {"radius_front": None, "radius_back": "-30 mm", "thickness": "4 mm",
                                     "semi_diameter": "8 mm"})["entry"]["args"]["radius_front"] is None


# --- declared functions, and the catalogue ----------------------------------------------------

def test_a_declared_function_runs_from_json_and_stays_a_function():
    @block("test_double_length", inputs={"length": T.Quantity("mm"), "times": T.INTEGER},
           outputs={"total": T.Quantity("mm")})
    def double_length(length, times=2):
        """A length, so many times."""
        return length * times

    assert double_length(3.0) == 6.0                                          # unchanged
    assert run_block("test_double_length", {"length": "1.5 cm"}) == {"total": "30 mm"}
    assert call_block("test_double_length", {"length": "1 mm", "times": 5}) == {"total": 5.0}
    d = get_block("test_double_length").describe()
    assert d["doc"] == "A length, so many times." and d["inputs"][1]["required"] is False
    with pytest.raises(ValueError, match="exists"):
        @block("test_double_length", inputs={}, outputs={"x": T.NUMBER})
        def other():
            return 1


def test_the_catalogue_is_json_and_its_wires_check():
    cat = json.loads(json.dumps(catalogue()))
    by_name = {b["name"]: b for b in cat}
    for b in cat:
        for port in b["inputs"] + b["outputs"]:
            assert from_description(port["type"]).describe() == port["type"]
    lens_out = by_name["SingletLens"]["outputs"][0]["type"]
    assert wire_accepts(lens_out, T.SCENE_ENTRY.describe())
    assert wire_accepts(lens_out, T.ListOf(T.SCENE_ENTRY).describe()) is False
    assert not wire_accepts(T.Quantity("deg").describe(), by_name["SingletLens"]["inputs"][2]["type"])


# --- angles and solid angles, kept apart as the eye-safety layer keeps them ---------------

ANGLES = [
    # (expected unit, given, value in the expected unit or None if refused)
    ("rad", "1 deg", 0.017453292519943295), ("rad", "1 mrad", 0.001), ("deg", "1 rad", 57.29577951308232),
    ("deg", "60 arcmin", 1.0), ("sr", "1 deg^2", 0.0003046174197867086), ("sr", "2 sr", 2.0),
    ("rad", "1 sr", None), ("rad", "1", None), ("deg", "1 deg^2", None),
    ("sr", "1 rad", None), ("sr", "1 deg", None), ("sr", "1", None),
]


@pytest.mark.parametrize("unit,given,expected", ANGLES, ids=lambda x: str(x))
def test_an_angle_a_solid_angle_and_a_pure_number_are_three_kinds(unit, given, expected):
    from ray_tracing_shapely.optical_elements.units import ANGLE, SOLID_ANGLE
    assert T.Quantity(ANGLE)._kind() == "radian" and T.Quantity(SOLID_ANGLE)._kind() == "radian ** 2"
    if expected is None:
        with pytest.raises(BlockTypeError, match="kind|dimensionality"):
            T.Quantity(unit).parse(given)
    else:
        assert T.Quantity(unit).parse(given) == pytest.approx(expected)


def test_wires_keep_angles_and_solid_angles_apart():
    Q = T.Quantity
    assert Q("deg").accepts(Q("rad")) and Q("sr").accepts(Q("deg^2"))
    assert not Q("sr").accepts(Q("rad")) and not Q("rad").accepts(Q("sr"))
    assert not Q("rad").accepts(Q("dimensionless")) and not Q("sr").accepts(Q("dimensionless"))
