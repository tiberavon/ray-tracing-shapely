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
