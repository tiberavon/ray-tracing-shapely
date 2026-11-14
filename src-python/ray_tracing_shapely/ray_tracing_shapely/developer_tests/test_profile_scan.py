"""
Python-specific module: test profile scan
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
A scanned lens face: reading the DXF, and fitting an asphere with its tilt
===============================================================================
Synthetic scans, written here as a profilometer writes them: points and short
lines along one meridian in a plane z = const, a long chord and base points
as references, coordinates rounded to 0.001.

- The reader returns the meridian in order, the references apart, in the
  stated unit; it refuses an entity it does not read, by name.
- A noiseless conic, offset and tilted, is recovered exactly, and a sphere's
  vertex and tilt are reported as degenerate.
- The Thorlabs ACL25416U's face, scanned as the torch lens was (offset,
  tilted 0.3 deg, dome up, 0.5 um noise, rounded to 1 um): its surface and
  tilt are recovered within the noise. Its K and A4 cannot be told apart
  (K = -0.999 is nearly a paraboloid, where a change of K is an A4 term), so
  the fit warns of the correlation; with K fixed, A4 is recovered.
- With a narrow bump on the face (form error no polynomial absorbs), the
  as-measured model follows it and the fitted asphere does not; an odd
  ripple comes back as the residual's odd part.
- Either model, as a lens face, goes through profile.json with its fit
  record and rebuilds; one meridian is an assumption of symmetry, two are a
  measured spread, refused past the tolerance unless accepted.
===============================================================================
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from ray_tracing_shapely.core.glass_curves import AsphereCurve, curve_from_descriptor
from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.optical_elements.lenses.profile_scan import (fit_record, fit_scan_asphere,
                                                                     read_profile_scan, residual_parts,
                                                                     scanned_face, symmetry_record)
from ray_tracing_shapely.optical_elements.prisms.base_prism import BasePrism
from ray_tracing_shapely.optical_elements.prisms.profile_export import export_profile
from ray_tracing_shapely.optical_elements.roles import Mechanism, Role

ACL = dict(radius=8.818197, conic=-0.99917152,
           coefficients=[0.0, 8.6821674e-5, 6.3760123e-8, 2.4073084e-9, -1.7189021e-11])
VERTEX, TILT_DEG = (237.5, 58.4), 0.3


def _pairs(*items):
    return "".join(f"{code:>3}\n{value}\n" for code, value in items)


def _write_dxf(path, points, *, chord=True, base=(), z=42.806, extra=""):
    """An R12-style ASCII DXF: a POINT and a LINE per step of the meridian, a chord, base points."""
    body = []
    for p in points:
        body.append(_pairs((0, "POINT"), (8, "0"), (10, f"{p[0]:.3f}"), (20, f"{p[1]:.3f}"), (30, z)))
    for p, q in zip(points[:-1], points[1:]):
        body.append(_pairs((0, "LINE"), (8, "0"), (10, f"{p[0]:.3f}"), (20, f"{p[1]:.3f}"), (30, z),
                           (11, f"{q[0]:.3f}"), (21, f"{q[1]:.3f}"), (31, z)))
    if chord:
        p, q = points[-1], points[0]
        body.append(_pairs((0, "LINE"), (8, "0"), (10, f"{p[0]:.3f}"), (20, f"{p[1] - 7.0:.3f}"), (30, z),
                           (11, f"{q[0]:.3f}"), (21, f"{q[1] - 7.0:.3f}"), (31, z)))
    for b in base:
        body.append(_pairs((0, "POINT"), (8, "0"), (10, f"{b[0]:.3f}"), (20, f"{b[1]:.3f}"), (30, z)))
    text = (_pairs((0, "SECTION"), (2, "HEADER"), (9, "$LUNITS"), (70, 2), (0, "ENDSEC"),
                   (0, "SECTION"), (2, "ENTITIES")) + "".join(body) + extra + _pairs((0, "ENDSEC"), (0, "EOF")))
    path.write_text(text)
    return path


def _scan(curve, half_width, step=0.1, noise_mm=0.0, seed=3):
    ss = np.arange(-half_width, half_width + 1e-9, step)
    pts = np.array([curve.point(s) for s in ss])
    if noise_mm:
        pts = pts + np.random.default_rng(seed).normal(0.0, noise_mm, pts.shape)
    return np.round(pts, 3)


def _dome(radius, conic, coefficients, half_width=11.45):
    tilt = math.radians(TILT_DEG)
    return AsphereCurve(VERTEX, (math.sin(tilt), -math.cos(tilt)), radius, conic, coefficients,
                        -half_width, half_width)                       # dome up: sag downwards


def test_reading_a_scan_returns_the_meridian_and_the_references(tmp_path):
    pts = _scan(_dome(13.4, -0.5, [], 12.0), 12.0)
    base = [(223.673, 50.867), (224.404, 50.867), (251.402, 50.941), (252.182, 50.941), (223.673, 50.867)]
    scan = read_profile_scan(_write_dxf(tmp_path / "s.dxf", pts, base=base), unit="mm")
    assert len(scan.meridians) == 1
    meridian = scan.meridians[0]                                        # in order, from either end
    assert np.allclose(meridian, pts) or np.allclose(meridian[::-1], pts)
    assert len(scan.reference_segments) == 1 and len(scan.reference_points) == 4      # each base point once
    assert scan.plane_z == pytest.approx(42.806) and scan.entities == {"POINT": len(pts) + 5, "LINE": len(pts)}
    in_um = read_profile_scan(tmp_path / "s.dxf", unit="um")
    assert np.allclose(in_um.meridians[0] * 1000.0, scan.meridians[0])
    json.dumps(scan.summary())
    with pytest.raises(NotImplementedError, match="CIRCLE"):
        read_profile_scan(_write_dxf(tmp_path / "c.dxf", pts, extra=_pairs((0, "CIRCLE"), (10, 1), (20, 1), (40, 2))),
                          unit="mm")
    with pytest.raises(ValueError, match="one plane"):
        read_profile_scan(_write_dxf(tmp_path / "z.dxf", pts, extra=_pairs((0, "POINT"), (10, 1), (20, 1), (30, 5))),
                          unit="mm")
    with pytest.raises(ValueError, match="unit"):
        read_profile_scan(tmp_path / "s.dxf", unit="furlong")


def test_a_lwpolyline_meridian_and_a_branching_one(tmp_path):
    pts = _scan(_dome(13.4, -0.5, [], 12.0), 12.0)
    poly = _pairs((0, "LWPOLYLINE"), (8, "0"), (90, len(pts)), (38, 42.806),
                  *[item for p in pts for item in ((10, f"{p[0]:.3f}"), (20, f"{p[1]:.3f}"))])
    text = _pairs((0, "SECTION"), (2, "ENTITIES")) + poly + _pairs((0, "ENDSEC"), (0, "EOF"))
    (tmp_path / "p.dxf").write_text(text)
    scan = read_profile_scan(tmp_path / "p.dxf", unit="mm")
    assert len(scan.meridians) == 1 and len(scan.meridians[0]) == len(pts)
    mid = pts[len(pts) // 2]
    branch = _pairs((0, "LINE"), (10, f"{mid[0]:.3f}"), (20, f"{mid[1]:.3f}"), (30, 42.806),
                    (11, f"{mid[0] + 0.05:.3f}"), (21, f"{mid[1] + 0.05:.3f}"), (31, 42.806))
    with pytest.raises(ValueError, match="branches"):
        read_profile_scan(_write_dxf(tmp_path / "b.dxf", pts, chord=False, extra=branch), unit="mm")


def test_a_noiseless_conic_is_recovered_and_a_sphere_reports_its_degeneracy():
    exact = np.array([_dome(13.4, -0.5, [], 12.0).point(s) for s in np.linspace(-12.0, 12.0, 241)])
    fit = fit_scan_asphere(exact, terms=0)
    assert fit.radius == pytest.approx(13.4, abs=1e-8) and fit.conic == pytest.approx(-0.5, abs=1e-7)
    assert fit.tilt_deg == pytest.approx(TILT_DEG, abs=1e-8) and fit.rms_um < 1e-6
    assert fit.vertex == pytest.approx(VERTEX, abs=1e-8)
    # a sphere, with a scan's noise (a noiseless fit's covariance is rounding, its correlation meaningless):
    # a tilted sphere is a shifted sphere, and the fit says so
    sphere = _scan(_dome(20.0, 0.0, [], 8.0), 8.0, noise_mm=0.5e-3)
    assert fit_scan_asphere(sphere, terms=0, conic=0.0).alignment_correlation > 0.99


def test_the_acl25416u_face_is_recovered_from_a_synthetic_scan(tmp_path):
    truth = _dome(**ACL)
    scan = read_profile_scan(_write_dxf(tmp_path / "acl.dxf", _scan(truth, 11.45, noise_mm=0.5e-3)), unit="mm")
    fit = fit_scan_asphere(scan.meridians[0], design=ACL)
    # the surface and its alignment, within the noise
    deviation = max(fit.curve().nearest(truth.point(s))[0] for s in np.linspace(-11.4, 11.4, 61))
    assert deviation < 0.5e-3 and fit.rms_um < 1.0
    assert fit.tilt_deg == pytest.approx(TILT_DEG, abs=0.002)
    assert fit.form_error["rms_um"] < 1.0                               # the design, aligned: only the noise left
    assert fit.form_error["tilt_deg"] == pytest.approx(TILT_DEG, abs=0.002)
    # terms chosen by the RMS gain: the four the design has
    assert [c["terms"] for c in fit.candidates if c["chosen"]] == [4]
    # the shape parameters are not separately determined, and the fit says so
    assert fit.warnings and all("not separately determined" in w for w in fit.warnings)
    # with K fixed at the design's, A4 (the term K would trade with) is recovered
    fixed = fit_scan_asphere(scan.meridians[0], conic=ACL["conic"], terms=4)
    assert fixed.conic_fixed and fixed.coefficients[1] == pytest.approx(ACL["coefficients"][1], rel=0.02)
    json.dumps(fit.summary())


# --- the two models, the record, the symmetry --------------------------------------------------------

def _bumpy_scan(seed=4, even_um=2.0, odd_um=1.0):
    """The ACL25416U's face plus a narrow even bump at |s| = 6 and an odd ripple at |s| = 3, along the axis."""
    truth = _dome(**ACL)
    ss = np.arange(-11.45, 11.4501, 0.1)

    def extra(s):
        return 1e-3 * (even_um * (np.exp(-((s - 6) / 0.6) ** 2) + np.exp(-((s + 6) / 0.6) ** 2))
                       + odd_um * (np.exp(-((s - 3) / 0.6) ** 2) - np.exp(-((s + 3) / 0.6) ** 2)))

    axis = np.array(truth.axis)
    pts = np.array([truth.point(s) for s in ss]) + extra(ss)[:, None] * axis
    pts = pts + np.random.default_rng(seed).normal(0.0, 0.3e-3, pts.shape)
    return np.round(pts, 3), extra


def _sag_at(desc, s):
    """The face's sag at s, for a face placed at the origin with its axis along +x."""
    curve = curve_from_descriptor(desc, *_ends(desc))
    (t, _), = curve.line_hits((-50.0, s), (1.0, 0.0))
    return t - 50.0


def _ends(desc):
    if desc["type"] == "spline":
        return tuple(desc["points"][0]), tuple(desc["points"][-1])
    h = 11.0
    c = AsphereCurve(desc["vertex"], desc["axis"], desc["radius"], desc["conic"], desc["coefficients"], -h, h)
    return c.start, c.end


def test_the_as_measured_model_follows_form_error_the_fit_cannot():
    pts, extra = _bumpy_scan()
    fit = fit_scan_asphere(pts)
    fitted = scanned_face(fit, "fitted", half_width_mm=11.0)
    measured = scanned_face(fit, "as_measured", half_width_mm=11.0, smoothing_mm=0.8)
    assert fitted["type"] == "asphere" and measured["type"] == "spline"
    design = AsphereCurve((0, 0), (1, 0), ACL["radius"], ACL["conic"], ACL["coefficients"], -11, 11)
    true_sag = {s: design.point(s)[0] + float(extra(np.array([s]))[0]) for s in (0.0, 6.0, -6.0)}
    for s in (6.0, -6.0):                                    # the bump's top, relative to the vertex
        want = true_sag[s] - true_sag[0.0]
        err_fit = abs(_sag_at(fitted, s) - _sag_at(fitted, 0.0) - want)
        err_meas = abs(_sag_at(measured, s) - _sag_at(measured, 0.0) - want)
        assert err_meas < 0.5e-3 and err_meas < 0.5 * err_fit
    parts = residual_parts(fit)
    odd = np.interp(3.0, parts["abs_s"], parts["odd"])
    assert odd == pytest.approx(1e-3, abs=0.4e-3)            # the injected odd ripple, at |s| = 3
    with pytest.raises(ValueError, match="model"):
        scanned_face(fit, "polished")
    with pytest.raises(ValueError, match="beyond"):
        scanned_face(fit, "fitted", half_width_mm=20.0)


class _ScannedLens(BasePrism):
    """A flat back at x = 0 and the scanned face, its vertex at x = 9, sag towards -x."""

    _edge_roles = [("S1", "Flat Back", Role.ENTRANCE), ("RIM", "Edge", Role.BLOCKER),
                   ("S2", "Scanned Face", Role.EXIT), ("RIM", "Edge", Role.BLOCKER)]
    _edge_mechanisms = {"S1": Mechanism.REFRACT, "RIM": None, "S2": Mechanism.REFRACT}

    def __init__(self, scene, desc):
        self._desc = desc
        super().__init__(scene, size=11.0, n=1.49)

    def _compute_path(self):
        top, bottom = sorted(_ends(self._desc), key=lambda p: -p[1])
        return [{"x": 0.0, "y": top[1], "arc": False}, {"x": 0.0, "y": bottom[1], "arc": False},
                {"x": bottom[0], "y": bottom[1], "arc": False, "curve": self._desc},
                {"x": top[0], "y": top[1], "arc": False}]


@pytest.mark.parametrize("model", ["fitted", "as_measured"])
def test_a_scanned_face_goes_through_profile_json_with_its_record(tmp_path, model):
    pts, _ = _bumpy_scan()
    scan = read_profile_scan(_write_dxf(tmp_path / "s.dxf", pts), unit="mm")
    fit = fit_scan_asphere(scan.meridians[0], design=ACL)
    desc = scanned_face(fit, model, vertex=(9.0, 0.0), axis=(-1.0, 0.0), half_width_mm=11.0, smoothing_mm=0.8)
    record = fit_record(fit, model, scan=scan, smoothing_mm=0.8)
    profile = json.loads(json.dumps(export_profile(
        _ScannedLens(Scene(), desc), symmetry={"kind": "revolve", "axis": {"point": [0.0, 0.0], "direction": [1.0, 0.0]}},
        physical_params={}, numerical_params={}, fit={"S2": record})))
    stored = profile["fit"]["spans"]["S2"]
    assert stored["model"] == model and stored["source"]["sha256"] == scan.sha256
    assert stored["symmetry"]["status"] == "assumed" and "form_error" in stored
    assert ("smoothing_mm" in stored) == (model == "as_measured")
    rebuilt = BasePrism.from_profile(Scene(), profile, n=1.49)
    assert [sp.kind for sp in rebuilt.spans].count("asphere" if model == "fitted" else "spline") == 1
    with pytest.raises(ValueError, match="not span labels"):
        export_profile(_ScannedLens(Scene(), desc), symmetry={"kind": "free"}, physical_params={},
                       numerical_params={}, fit={"S9": record})


def test_symmetry_is_assumed_for_one_meridian_and_measured_for_two():
    one = fit_scan_asphere(_bumpy_scan(seed=1)[0])
    assert symmetry_record([one])["status"] == "assumed"
    same = fit_scan_asphere(_bumpy_scan(seed=2)[0])                    # the same face, other noise
    checked = symmetry_record([one, same], tolerance_um=2.0)
    assert checked["status"] == "checked" and checked["spread_um"] < 2.0
    other = _dome(ACL["radius"] * 1.01, ACL["conic"], ACL["coefficients"])
    different = fit_scan_asphere(_scan(other, 11.45, noise_mm=0.3e-3))
    with pytest.raises(ValueError, match="not rotationally symmetric"):
        symmetry_record([one, different], tolerance_um=2.0)
    accepted = symmetry_record([one, different], tolerance_um=2.0, accept=True)
    assert accepted["status"] == "accepted" and accepted["spread_um"] > 2.0

