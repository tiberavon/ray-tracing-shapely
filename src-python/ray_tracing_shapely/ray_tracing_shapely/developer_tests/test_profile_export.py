"""
Python-specific module: test profile export
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

Tests for optical_elements.prisms.profile_export (C-PROFILE-01)."""

import json
import math

import pytest

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.optical_elements.prisms.refractometer import RefractometerPrism
from ray_tracing_shapely.optical_elements.prisms.profile_export import (
    PROFILE_SCHEMA_VERSION,
    export_profile,
    persist_profile_artifact,
)

EXTRUDE_SYMMETRY = {
    "kind": "extrude",
    "plane_axes": ["x", "z"],
    "extrude_axis": "y",
    "length": 10.0,
}


def _refractometer(scene):
    return RefractometerPrism.from_critical_ray_path(
        scene, n_prism=1.72, n_target=1.33, ray_path_length=20.0
    )


def test_schema_shape():
    scene = Scene()
    prism = _refractometer(scene)
    profile = export_profile(
        prism,
        symmetry=EXTRUDE_SYMMETRY,
        physical_params={"n_prism": prism.n_prism},
        numerical_params={},
    )
    assert profile["schema_version"] == PROFILE_SCHEMA_VERSION
    assert profile["fit"] is None
    assert len(profile["points"]) == len(profile["normals"])
    # Four straight edges, two points each.
    assert len(profile["points"]) == 8
    assert len(profile["spans"]) == 4


def test_spans_reference_valid_point_ranges():
    scene = Scene()
    prism = _refractometer(scene)
    profile = export_profile(
        prism, symmetry=EXTRUDE_SYMMETRY, physical_params={}, numerical_params={}
    )
    n_points = len(profile["points"])
    for span in profile["spans"]:
        assert 0 <= span["index_start"] < span["index_end"] <= n_points


def test_role_and_mechanism_match_refractometer_prism_edge_roles():
    scene = Scene()
    prism = _refractometer(scene)
    profile = export_profile(
        prism, symmetry=EXTRUDE_SYMMETRY, physical_params={}, numerical_params={}
    )
    by_label = {span["short_label"]: span for span in profile["spans"]}
    assert by_label["B"]["role"] == "blocker"
    assert by_label["B"]["mechanism"] is None
    assert by_label["X"]["role"] == "exit"
    assert by_label["X"]["mechanism"] == "refract"
    assert by_label["M"]["role"] == "sample_medium"
    assert by_label["M"]["mechanism"] == "tir"
    assert by_label["E"]["role"] == "entrance"
    assert by_label["E"]["mechanism"] == "refract"


def test_normals_are_unit_and_outward():
    """Each edge's normal should be unit length and point away from the
    polygon centroid (a convex trapezoid, so centroid-pointing-away is a
    valid outwardness check)."""
    scene = Scene()
    prism = _refractometer(scene)
    profile = export_profile(
        prism, symmetry=EXTRUDE_SYMMETRY, physical_params={}, numerical_params={}
    )
    cx = sum(p[0] for p in profile["points"]) / len(profile["points"])
    cy = sum(p[1] for p in profile["points"]) / len(profile["points"])
    for span in profile["spans"]:
        p = profile["points"][span["index_start"]]
        n = profile["normals"][span["index_start"]]
        assert math.isclose(math.hypot(*n), 1.0, rel_tol=1e-9)
        to_point = (p[0] - cx, p[1] - cy)
        dot = to_point[0] * n[0] + to_point[1] * n[1]
        assert dot > 0, f"normal for span {span['short_label']} does not point outward"


def test_symmetry_validation():
    scene = Scene()
    prism = _refractometer(scene)
    with pytest.raises(ValueError, match="kind"):
        export_profile(prism, symmetry={"kind": "bogus"}, physical_params={}, numerical_params={})
    with pytest.raises(ValueError, match="extrude"):
        export_profile(
            prism,
            symmetry={"kind": "extrude"},
            physical_params={},
            numerical_params={},
        )
    with pytest.raises(ValueError, match="revolve"):
        export_profile(
            prism,
            symmetry={"kind": "revolve"},
            physical_params={},
            numerical_params={},
        )


def test_persist_profile_artifact_writes_valid_json(tmp_path):
    scene = Scene()
    prism = _refractometer(scene)
    path = persist_profile_artifact(
        prism,
        symmetry=EXTRUDE_SYMMETRY,
        physical_params={"n_prism": prism.n_prism},
        numerical_params={},
        out_dir=tmp_path,
        design_id="refractometer_critical_path",
        run_id="n_target_1.33",
    )
    assert path == tmp_path / "refractometer_critical_path" / "n_target_1.33" / "profile.json"
    loaded = json.loads(path.read_text())
    assert loaded["schema_version"] == PROFILE_SCHEMA_VERSION


# --- flat prisms tagged for export, and the labelled inverse --------------

from ray_tracing_shapely.optical_elements.prisms.base_prism import BasePrism  # noqa: E402
from ray_tracing_shapely.optical_elements.prisms.equilateral import EquilateralPrism  # noqa: E402
from ray_tracing_shapely.optical_elements.prisms.right_angle import RightAnglePrism  # noqa: E402

FLAT_PRISMS = {
    "refractometer": _refractometer,
    "equilateral": lambda scene: EquilateralPrism(scene, side_length=50.0, rotation=17.0),
    "right_angle": lambda scene: RightAnglePrism(scene, leg_length=30.0, position=(3.0, -4.0)),
}


def _export(prism):
    return export_profile(
        prism, symmetry=EXTRUDE_SYMMETRY, physical_params={}, numerical_params={}
    )


@pytest.mark.parametrize("name", sorted(FLAT_PRISMS))
def test_every_flat_prism_span_carries_a_role(name):
    profile = _export(FLAT_PRISMS[name](Scene()))
    for span in profile["spans"]:
        assert span["role"] is not None, f"{name} span {span['short_label']} has no role"
    # Every span with a role other than BLOCKER is on the optical path, so
    # it must declare what happens there.
    for span in profile["spans"]:
        if span["role"] != "blocker":
            assert span["mechanism"] is not None, (
                f"{name} span {span['short_label']} has role {span['role']} but no mechanism"
            )


def test_right_angle_and_equilateral_tags():
    by_label = {s["short_label"]: s for s in _export(RightAnglePrism(Scene(), leg_length=30.0))["spans"]}
    assert (by_label["E"]["role"], by_label["E"]["mechanism"]) == ("entrance", "refract")
    assert (by_label["H"]["role"], by_label["H"]["mechanism"]) == ("wall", "tir")
    assert (by_label["X"]["role"], by_label["X"]["mechanism"]) == ("exit", "refract")
    by_label = {s["short_label"]: s for s in _export(EquilateralPrism(Scene(), side_length=50.0))["spans"]}
    assert (by_label["B"]["role"], by_label["B"]["mechanism"]) == ("blocker", None)
    assert (by_label["X"]["role"], by_label["X"]["mechanism"]) == ("exit", "refract")
    assert (by_label["E"]["role"], by_label["E"]["mechanism"]) == ("entrance", "refract")


@pytest.mark.parametrize("name", sorted(FLAT_PRISMS))
def test_from_profile_round_trips_export(name):
    """export -> from_profile -> export reproduces the profile: geometry,
    normals, labels, roles and mechanisms all survive."""
    original = _export(FLAT_PRISMS[name](Scene()))
    rebuilt = BasePrism.from_profile(Scene(), original, n=1.6)
    again = _export(rebuilt)
    assert again["spans"] == original["spans"]
    for a, b in zip(again["points"], original["points"]):
        assert a == pytest.approx(b, abs=1e-12)
    for a, b in zip(again["normals"], original["normals"]):
        assert a == pytest.approx(b, abs=1e-12)
    assert rebuilt.refIndex == 1.6
    assert type(rebuilt) is BasePrism


def test_from_profile_keeps_labels_addressable_unlike_from_vertices():
    profile = _export(_refractometer(Scene()))
    rebuilt = BasePrism.from_profile(Scene(), profile, n=1.72)
    m_index = rebuilt.find_edge_by_functional_label("M")
    assert m_index is not None
    assert rebuilt.get_functional_label(m_index) == ("M", "Measuring Surface")
    assert rebuilt.get_edge_role(m_index).value == "sample_medium"
    assert rebuilt._edge_mechanisms["M"].value == "tir"

    vertices = [tuple(profile["points"][s["index_start"]]) for s in profile["spans"]]
    unlabelled = BasePrism.from_vertices(Scene(), vertices, n=1.72)
    assert unlabelled.find_edge_by_functional_label("M") is None


def test_from_profile_rejects_curved_span():
    profile = _export(_refractometer(Scene()))
    profile["spans"][0]["index_end"] += 1
    with pytest.raises(NotImplementedError, match="two-point"):
        BasePrism.from_profile(Scene(), profile, n=1.5)


def test_from_profile_rejects_open_outline():
    profile = _export(_refractometer(Scene()))
    profile["points"][1] = [profile["points"][1][0] + 0.5, profile["points"][1][1]]
    with pytest.raises(ValueError, match="does not close"):
        BasePrism.from_profile(Scene(), profile, n=1.5)


def test_from_profile_rejects_clockwise_outline():
    profile = _export(_refractometer(Scene()))
    # Reverse the traversal: every span runs backwards and in reverse order.
    spans, points, normals = [], [], []
    for span in reversed(profile["spans"]):
        p1, p2 = profile["points"][span["index_start"]], profile["points"][span["index_start"] + 1]
        n = profile["normals"][span["index_start"]]
        spans.append(dict(span, index_start=len(points), index_end=len(points) + 2))
        points += [p2, p1]
        normals += [n, n]
    profile.update(spans=spans, points=points, normals=normals)
    with pytest.raises(ValueError, match="clockwise"):
        BasePrism.from_profile(Scene(), profile, n=1.5)


def test_from_profile_rejects_a_wrong_normal():
    profile = _export(_refractometer(Scene()))
    nx, ny = profile["normals"][0]
    profile["normals"][0] = [-nx, -ny]
    profile["normals"][1] = [-nx, -ny]
    with pytest.raises(ValueError, match="stored normal"):
        BasePrism.from_profile(Scene(), profile, n=1.5)


def test_from_profile_rejects_unknown_vocabulary():
    profile = _export(_refractometer(Scene()))
    profile["spans"][1]["mechanism"] = "diffract"
    with pytest.raises(ValueError, match="diffract"):
        BasePrism.from_profile(Scene(), profile, n=1.5)
