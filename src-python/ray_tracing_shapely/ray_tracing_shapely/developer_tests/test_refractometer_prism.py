"""
Python-specific module: test_refractometer_prism
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
Acceptance tests for RefractometerPrism: the wide-top default trapezoid,
the meas2edge_angle property, and the two morphing operations
(morphing_meas2edge_angle, morphing_scale).

Design reference for every group: n_prism = 1.5168 (BK7),
n_sample_range = (1.33, 1.42), measuring_surface_length = 15.0,
n_mid = 1.375, theta_c(n_mid) = 65.028 deg, face_angle = 24.972 deg.

Morphing reference prism: from_critical_ray_path(n_prism=1.5168,
n_target=1.375, ray_path_length=60.0) -> M = 66.1876, B = 42.594,
H = 25.3306.
"""

import math

import pytest

from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.optical_elements.prisms import RefractometerPrism, tir_utils


N_PRISM = 1.5168
N_RANGE = (1.33, 1.42)
M_LEN = 15.0
N_MID = 1.375
THETA_C_MID = math.degrees(math.asin(N_MID / N_PRISM))   # 65.028
FACE_ANGLE = 90.0 - THETA_C_MID                         # 24.972


def _primary(scene=None, **kw):
    return RefractometerPrism(
        scene or Scene(), n_prism=N_PRISM, n_sample_range=N_RANGE,
        measuring_surface_length=M_LEN, **kw
    )


def _crp(scene=None, **kw):
    return RefractometerPrism.from_critical_ray_path(
        scene or Scene(), n_prism=N_PRISM, n_target=N_MID, ray_path_length=60.0, **kw
    )


def _height(prism):
    """Perpendicular distance between edge 2 (M) and edge 0 (B), frame-free."""
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = _snapshot_path(prism)[:4]
    M = math.hypot(x2 - x3, y2 - y3)
    ux, uy = (x2 - x3) / M, (y2 - y3) / M
    bx, by = (x0 + x1) / 2 - (x2 + x3) / 2, (y0 + y1) / 2 - (y2 + y3) / 2
    return abs(bx * uy - by * ux)


def _snapshot_path(prism):
    return [(v['x'], v['y']) for v in prism.path]


# =============================================================================
# 1. Primary constructor
# =============================================================================

def test_primary_constructor():
    p = _primary()
    assert p.n_prism == N_PRISM
    assert p.n_sample_range == N_RANGE
    assert p.measuring_surface_length == M_LEN
    assert p.system_type == 'angular'
    assert p.face_angle == pytest.approx(FACE_ANGLE, abs=0.01)

    lo, hi = p.theta_c_range
    assert isinstance(lo, float) and isinstance(hi, float) and lo < hi
    assert lo == pytest.approx(math.degrees(math.asin(N_RANGE[0] / N_PRISM)), abs=0.01)
    assert hi == pytest.approx(math.degrees(math.asin(N_RANGE[1] / N_PRISM)), abs=0.01)
    assert p.n_mid == pytest.approx(N_MID)
    assert p.theta_c_mid == pytest.approx(THETA_C_MID, abs=0.01)

    # Piece A: wide top, B = 8.014
    assert p.base_length < p.measuring_surface_length
    assert p.base_length == pytest.approx(8.014, abs=1e-3)
    # Piece A + B
    assert p.meas2edge_angle == pytest.approx(p.theta_c_mid, abs=0.1)
    assert p.meas2edge_angle == pytest.approx(90.0 - p.face_angle, abs=1e-9)
    assert p.get_interior_angle(2) == pytest.approx(p.meas2edge_angle, abs=1e-9)

    ends = p.get_measuring_surface_endpoints()
    assert len(ends) == 2
    (x1, y1), (x2, y2) = ends
    assert math.hypot(x2 - x1, y2 - y1) == pytest.approx(M_LEN, abs=1e-3)

    assert p.critical_angle_for(N_RANGE[0]) == pytest.approx(p.theta_c_range[0])
    assert p.exit_angle_for(N_MID) == pytest.approx(0.0, abs=0.1)
    assert isinstance(p.validate_geometry(), list)
    assert p.signed_area() > 0  # CCW


# =============================================================================
# 2. from_apex_angle
# =============================================================================

def test_from_apex_angle():
    face = round(FACE_ANGLE * 2) / 2   # nearest 0.5 deg -> 25.0
    p = RefractometerPrism.from_apex_angle(
        Scene(), face_angle_deg=face, n_prism=N_PRISM, measuring_surface_length=M_LEN
    )
    assert p.face_angle == face
    assert p.system_type == 'angular'
    assert p.base_length < p.measuring_surface_length
    assert p.get_edge_length(2) == pytest.approx(M_LEN, abs=1e-3)
    assert abs(p.exit_angle_for(N_MID)) < 1.0
    assert p.meas2edge_angle == pytest.approx(90.0 - face, abs=1e-9)


def test_from_apex_angle_degenerate_raises():
    # Piece A / decision 5: face_angle >= 45 deg gives B <= 0 for H = M/2.
    with pytest.raises(ValueError, match="45"):
        RefractometerPrism.from_apex_angle(
            Scene(), face_angle_deg=50.0, n_prism=N_PRISM, measuring_surface_length=M_LEN
        )


# =============================================================================
# 3. from_geometric_constraints
# =============================================================================

def test_from_geometric_constraints():
    p = RefractometerPrism.from_geometric_constraints(
        Scene(), n_prism=N_PRISM, n_sample_range=N_RANGE,
        source_distance=30.0, sensor_length=20.0, path_length=50.0,
    )
    assert p.system_type == 'geometric'
    assert (p.source_distance, p.sensor_length, p.path_length) == (30.0, 20.0, 50.0)
    assert p.measuring_surface_length > 0
    assert p.face_angle == pytest.approx(FACE_ANGLE, abs=0.01)
    pos = p.sensor_position_for(N_MID)
    assert math.isfinite(pos)
    assert pos == pytest.approx(0.0, abs=0.1)
    assert isinstance(p.validate_geometry(), list)
    assert p.base_length < p.measuring_surface_length


# =============================================================================
# 4. from_critical_ray_path (must be unchanged by this work)
# =============================================================================

def test_from_critical_ray_path():
    p = _crp()
    assert p.n_target == N_MID
    assert p.ray_path_length == 60.0
    assert p.face_angle == pytest.approx(FACE_ANGLE, abs=0.01)
    assert p.measuring_surface_length == pytest.approx(66.1876, abs=1e-3)
    assert p.base_length == pytest.approx(42.594, abs=1e-3)
    assert p.measuring_surface_length > p.base_length
    assert p.exit_angle_for(N_MID) == pytest.approx(0.0, abs=0.2)

    dims = tir_utils.trapezoid_from_critical_ray_path(N_MID, N_PRISM, 60.0)
    assert _height(p) == pytest.approx(dims['h'], abs=1e-9)
    assert p.meas2edge_angle == pytest.approx(dims['theta_c_deg'], abs=1e-6)


# =============================================================================
# 5. Position and rotation
# =============================================================================

def test_position_and_rotation():
    p = _primary(position=(100.0, 50.0), rotation=90.0)
    (x1, y1), (x2, y2) = p.get_measuring_surface_endpoints()
    assert math.hypot(x2 - x1, y2 - y1) == pytest.approx(M_LEN, abs=1e-3)
    assert abs(x2 - x1) < 1e-3   # vertical at 90 deg
    mid = ((x1 + x2) / 2, (y1 + y2) / 2)
    assert math.hypot(mid[0] - 100.0, mid[1] - 50.0) < 30.0
    # the angle is a property of the shape, not the frame
    assert p.meas2edge_angle == pytest.approx(THETA_C_MID, abs=0.1)


# =============================================================================
# 6. Error handling
# =============================================================================

def test_error_handling():
    with pytest.raises(ValueError):
        RefractometerPrism(Scene(), n_prism=1.38, n_sample_range=N_RANGE,
                           measuring_surface_length=M_LEN)
    with pytest.raises(ValueError):
        _primary(system_type='bogus')
    with pytest.raises(ValueError):
        RefractometerPrism.from_geometric_constraints(
            Scene(), n_prism=N_PRISM, n_sample_range=N_RANGE,
            source_distance=0.0, sensor_length=20.0, path_length=50.0)
    with pytest.raises(ValueError):
        RefractometerPrism.from_geometric_constraints(
            Scene(), n_prism=N_PRISM, n_sample_range=N_RANGE,
            source_distance=30.0, sensor_length=20.0, path_length=-1.0)
    with pytest.raises(ValueError):
        _primary().sensor_position_for(N_MID)


# =============================================================================
# 7. morphing_meas2edge_angle
# =============================================================================

def test_morph_angle_not_inplace():
    orig = _crp()
    face0, B0, path0 = orig.face_angle, orig.base_length, _snapshot_path(orig)
    M_edge0 = orig.get_edge_length(2)

    c = orig.morphing_meas2edge_angle(70.0, inplace=False)
    assert c is not orig
    assert orig.face_angle == face0
    assert orig.base_length == B0
    assert _snapshot_path(orig) == path0

    assert c.face_angle == pytest.approx(90.0 - 70.0)
    assert c.measuring_surface_length == orig.measuring_surface_length
    assert c.get_edge_length(2) == pytest.approx(M_edge0, abs=1e-6)
    assert c.base_length > B0
    assert c.base_length == pytest.approx(47.7485, abs=1e-3)

    # decision 1: detached copy shares the scene, is not registered, new uuid
    assert c.scene is orig.scene
    assert c not in orig.scene.objs
    assert c.uuid != orig.uuid
    assert c.path is not orig.path


def test_morph_angle_inplace_matches_copy():
    copy_B = _crp().morphing_meas2edge_angle(70.0, inplace=False).base_length
    p = _crp()
    r = p.morphing_meas2edge_angle(70.0)
    assert r is p
    assert p.face_angle == pytest.approx(20.0)
    assert p.base_length == pytest.approx(copy_B, abs=1e-12)


@pytest.mark.parametrize("rotation", [0.0, 37.0, 200.0])
@pytest.mark.parametrize("angle,expected_B", [
    (70.0, 47.7485), (65.028, 42.594), (60.0, 36.9384),
    (45.0, 15.5265), (90.0, 66.1876), (120.0, 95.4369),
])
def test_morph_angle_invariants(rotation, angle, expected_B):
    p = _crp(position=(12.0, -7.0), rotation=rotation)
    V2, V3 = dict(p.path[2]), dict(p.path[3])
    M_edge, H = p.get_edge_length(2), _height(p)

    p.morphing_meas2edge_angle(angle)

    assert p.path[2] == V2 and p.path[3] == V3          # top vertices untouched
    assert p.get_edge_length(2) == pytest.approx(M_edge, abs=1e-6)
    assert _height(p) == pytest.approx(H, abs=1e-6)
    assert p.get_interior_angle(3) == pytest.approx(angle, abs=1e-6)
    assert p.get_interior_angle(2) == pytest.approx(angle, abs=1e-6)   # symmetric
    assert p.meas2edge_angle == pytest.approx(angle, abs=1e-6)
    assert p.get_edge_length(1) == pytest.approx(p.get_edge_length(3), abs=1e-9)
    assert p.base_length == pytest.approx(expected_B, abs=1e-3)
    assert p.face_angle == pytest.approx(90.0 - angle)
    assert p.signed_area() > 0
    # decision 4: _position follows the vertex mean
    assert p._position == pytest.approx(p._get_centroid())
    assert all('arc' in v for v in p.path)


def test_morph_angle_keeps_physics_attributes():
    p = _crp()
    before = (p.n_prism, p.n_sample_range, p.theta_c_range, p.system_type,
              p.measuring_surface_length, p.refIndex, p.size)
    p.morphing_meas2edge_angle(70.0)
    after = (p.n_prism, p.n_sample_range, p.theta_c_range, p.system_type,
             p.measuring_surface_length, p.refIndex, p.size)
    assert before == after


@pytest.mark.parametrize("bad", [0.0, 180.0, -5.0, 200.0])
def test_morph_angle_out_of_range(bad):
    with pytest.raises(ValueError, match=r"\(0, 180\)"):
        _crp().morphing_meas2edge_angle(bad)


def test_morph_angle_degenerate_raises_before_change():
    p = _crp(rotation=37.0)
    path0, face0 = _snapshot_path(p), p.face_angle
    with pytest.raises(ValueError, match="37.431"):
        p.morphing_meas2edge_angle(1.0)
    assert _snapshot_path(p) == path0 and p.face_angle == face0


def test_morph_angle_keyword_only():
    with pytest.raises(TypeError):
        _crp().morphing_meas2edge_angle(70.0, False)


# =============================================================================
# 8. morphing_scale
# =============================================================================

@pytest.mark.parametrize("rotation", [0.0, 37.0])
def test_scale_half(rotation):
    p = _crp(position=(5.0, 9.0), rotation=rotation)
    M0, B0 = p.measuring_surface_length, p.base_length
    face0, m2e0, c0 = p.face_angle, p.meas2edge_angle, p._get_centroid()

    p.morphing_scale(scale=50)

    assert p.measuring_surface_length == pytest.approx(M0 / 2, abs=1e-9)
    assert p.measuring_surface_length == pytest.approx(33.0938, abs=1e-3)
    assert p.get_edge_length(2) == pytest.approx(M0 / 2, abs=1e-9)
    assert p.base_length == pytest.approx(B0 / 2, abs=1e-9)
    assert p.base_length == pytest.approx(21.2970, abs=1e-3)
    assert p.face_angle == pytest.approx(face0, abs=1e-6)
    assert p.meas2edge_angle == pytest.approx(m2e0, abs=1e-6)
    assert p._get_centroid() == pytest.approx(c0, abs=1e-9)
    assert p._position == pytest.approx(c0, abs=1e-9)


def test_scale_double():
    p = _crp().morphing_scale(scale=200)
    assert p.measuring_surface_length == pytest.approx(132.3752, abs=1e-3)
    assert p.base_length == pytest.approx(85.188, abs=1e-3)


def test_scale_to_target_length():
    p = _crp()
    factor = 30.0 / p.measuring_surface_length
    assert factor == pytest.approx(0.45326, abs=1e-5)
    p.morphing_scale(target_measuring_surface_length=30.0)
    assert p.measuring_surface_length == pytest.approx(30.0)
    assert p.get_edge_length(2) == pytest.approx(30.0, abs=1e-9)
    assert p.base_length == pytest.approx(19.3060, abs=1e-3)


def test_scale_inplace_and_copy():
    p = _crp()
    assert p.morphing_scale(scale=150) is p
    assert p.measuring_surface_length == pytest.approx(66.18763636 * 1.5, abs=1e-6)

    orig = _crp()
    path0, M0 = _snapshot_path(orig), orig.measuring_surface_length
    c = orig.morphing_scale(scale=50, inplace=False)
    assert c is not orig
    assert _snapshot_path(orig) == path0
    assert orig.measuring_surface_length == M0
    assert orig.ray_path_length == 60.0
    assert c.measuring_surface_length == pytest.approx(M0 / 2)


def test_scale_updates_length_attributes():
    # decisions 2 and 3: size and ray_path_length follow the scale
    p = _crp().morphing_scale(scale=50)
    assert p.size == pytest.approx(p.measuring_surface_length)
    assert p.ray_path_length == pytest.approx(30.0)
    assert p.n_target == N_MID

    g = RefractometerPrism.from_geometric_constraints(
        Scene(), n_prism=N_PRISM, n_sample_range=N_RANGE,
        source_distance=30.0, sensor_length=20.0, path_length=50.0,
    ).morphing_scale(scale=200)
    assert (g.source_distance, g.sensor_length, g.path_length) == \
        pytest.approx((60.0, 40.0, 100.0))

    q = _primary().morphing_scale(scale=200)
    assert q.source_distance is None and q.sensor_length is None and q.path_length is None


@pytest.mark.parametrize("kwargs", [
    {}, {'scale': 50, 'target_measuring_surface_length': 30.0},
    {'scale': -10}, {'scale': 0}, {'target_measuring_surface_length': 0},
])
def test_scale_errors(kwargs):
    p = _crp()
    path0 = _snapshot_path(p)
    with pytest.raises(ValueError):
        p.morphing_scale(**kwargs)
    assert _snapshot_path(p) == path0


def test_scale_then_morph_angle_compose():
    p = _crp(rotation=37.0)
    p.morphing_scale(scale=50).morphing_meas2edge_angle(70.0)
    assert p.meas2edge_angle == pytest.approx(70.0, abs=1e-6)
    assert p.base_length == pytest.approx(47.7485 / 2, abs=1e-3)
