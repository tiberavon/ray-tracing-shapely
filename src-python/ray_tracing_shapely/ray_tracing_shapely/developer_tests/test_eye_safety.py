"""
Python-specific module: test eye safety
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
EYE SAFETY -- shared scaffolding verification (C-EYE-01, P-HAZARD-ROUTINES)
===============================================================================

Covers C-EYE-01 (dev_doc/architecture/contracts/C-EYE-01.md) and
dev_doc/architecture/components/eye_safety.md: angular subtense (`alpha_from_axes`,
`clip_alpha`), per-standard exposure-duration time-regime helpers
(`alpha_eff_iec62471`, `t2_iec60825_1`, `gamma_ph_iec60825_1`),
per-standard limiting-aperture selection and averaging
(`limiting_aperture_diameter_iec62471`, `limiting_aperture_diameter_iec60825_1`,
`average_over_aperture`), `LimitResult`, spectral power distributions
(`interp_log`, `SpectralPowerDistribution`), IEC 60825-1's correction
factors (`c3_iec60825_1`, `c4_iec60825_1`, `c6_iec60825_1`,
`c7_iec60825_1`), and its retinal-thermal MPE/AEL/classification chain
(`iec60825_1.mpe_retinal_thermal`, `iec60825_1.ael_class_1`/`_2`/`_3r`,
`iec60825_1.classify_measurement`) -- regression-tested against Henderson
& Schulmeister Sec. 4.8.1-4.8.2's two worked case studies.

IEC 62471's broadband (lamp/LED) hazard-function tables
(`hazard_functions.S_actinic_uv`/`B_blue_light`/`R_retinal_thermal`) and
exposure-limit/classification chain (`eye_safety.iec62471.mpe_*`,
`eye_safety.iec62471.classify_measurement`). **Neither standard's `mpe_*`/
`classify_measurement` is flattened into this file's top-level imports** --
both are accessed via their submodule (`eye_safety.iec60825_1.*` /
`eye_safety.iec62471.*`), per C-EYE-04: see `eye_safety/__init__.py`'s
module docstring for why this was made symmetric (it was briefly
asymmetric, which left the bare name silently defaulting to the laser
standard [KC6]). Regression-tested against two real worked examples from
Directive 2006/25/EC's non-binding implementation guide (Appendix
D.1.21/D.1.22) [KD5].

Design rationale and phase history:
dev_doc/architecture/components/eye_safety.md,
dev_doc/architecture/components/eye_safety.md.

Run with:
    python src-python/ray_tracing_shapely/developer_tests/test_eye_safety.py

Or with pytest:
    pytest developer_tests/test_eye_safety.py -v
===============================================================================
"""

import sys
import math
from pathlib import Path

src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from ray_tracing_shapely.optical_elements import eye_safety
from ray_tracing_shapely.optical_elements.eye_safety import hazard_functions, iec60825_1
from ray_tracing_shapely.optical_elements import (
    LimitResult,
    ALPHA_MIN_IEC62471_RAD,
    ALPHA_MIN_IEC60825_1_RAD,
    ALPHA_MAX_RAD,
    clip_alpha,
    alpha_from_axes,
    angle_from_size_distance,
    radiance_from_irradiance,
    irradiance_from_radiance,
    GAMMA_TH_IEC60825_1_RAD,
    alpha_eff_iec62471,
    t2_iec60825_1,
    gamma_ph_iec60825_1,
    limiting_aperture_diameter_iec62471,
    limiting_aperture_diameter_iec60825_1,
    average_over_aperture,
    SpectralPowerDistribution,
    interp_log,
    c3_iec60825_1,
    c4_iec60825_1,
    c6_iec60825_1,
    c7_iec60825_1,
)


def _assert_raises(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return
    except Exception as other:  # noqa: BLE001
        raise AssertionError(f"expected {exc_type.__name__}, got {other!r}")
    raise AssertionError(f"expected {exc_type.__name__}, nothing raised")


# ---------------------------------------------------------------------------
# Angular subtense
# ---------------------------------------------------------------------------

def test_alpha_min_values_differ_between_standards():
    """The two standards' alpha_min values differ -- must not silently agree."""
    assert ALPHA_MIN_IEC62471_RAD == 0.0017
    assert ALPHA_MIN_IEC60825_1_RAD == 0.0015
    assert ALPHA_MIN_IEC62471_RAD != ALPHA_MIN_IEC60825_1_RAD
    assert ALPHA_MAX_RAD == 0.1


def test_clip_alpha_within_bounds_unchanged():
    assert math.isclose(clip_alpha(0.02, 0.0015, 0.1), 0.02)


def test_clip_alpha_clamps_low():
    assert math.isclose(clip_alpha(0.0001, 0.0015, 0.1), 0.0015)


def test_clip_alpha_clamps_high():
    assert math.isclose(clip_alpha(0.5, 0.0015, 0.1), 0.1)


def test_clip_alpha_negative_raises():
    _assert_raises(ValueError, clip_alpha, -0.001, 0.0015, 0.1)


def test_clip_alpha_bad_bounds_raises():
    _assert_raises(ValueError, clip_alpha, 0.01, 0.1, 0.05)


def test_alpha_from_axes_iec62471_worked_example():
    """IEC 62471 Sec. 4.2.2's own worked example: a 20 mm x 3 mm tube at
    200 mm gives alpha = 0.058 rad."""
    alpha_x = 20.0e-3 / 200.0e-3   # 0.1 rad
    alpha_y = 3.0e-3 / 200.0e-3    # 0.015 rad
    alpha = alpha_from_axes(alpha_x, alpha_y, ALPHA_MIN_IEC62471_RAD)
    assert math.isclose(alpha, 0.0575)
    # The standard itself rounds 11.5 mm / 200 mm = 0,0575 to "0,058 radian".
    assert math.isclose(alpha, 0.058, abs_tol=6e-4)


def test_alpha_from_axes_henderson_line_laser_example():
    """Henderson Sec. 4.8.3's line-laser case: alpha_long clamped to
    alpha_max (100 mrad), alpha_short at alpha_min (1.5 mrad) ->
    (100+1.5)/2 = 50.75 mrad, which the book itself rounds to "50.8 mrad"."""
    alpha = alpha_from_axes(10.0, 0.0005, ALPHA_MIN_IEC60825_1_RAD)
    assert math.isclose(alpha, 0.05075, rel_tol=1e-9)
    assert math.isclose(alpha, 0.0508, abs_tol=1e-4)


def test_alpha_from_axes_clamps_each_axis_before_averaging():
    alpha = alpha_from_axes(0.2, 0.00001, alpha_min_rad=0.0015, alpha_max_rad=0.1)
    assert math.isclose(alpha, (0.1 + 0.0015) / 2.0)


# ---------------------------------------------------------------------------
# Exposure-duration time regimes
# ---------------------------------------------------------------------------

def test_alpha_eff_iec62471_at_boundaries():
    assert math.isclose(alpha_eff_iec62471(0.1), ALPHA_MIN_IEC62471_RAD)
    assert math.isclose(alpha_eff_iec62471(0.25), ALPHA_MIN_IEC62471_RAD)
    # The standard's own sqrt(t) approximation only reaches "about 0,011"
    # at t=10 s -- it does not land on it exactly (its own text flags this
    # as a rough continuity assumption, not an exact formula).
    assert math.isclose(alpha_eff_iec62471(10.0), 0.011, abs_tol=3e-4)
    assert math.isclose(alpha_eff_iec62471(50.0), 0.011)
    assert math.isclose(alpha_eff_iec62471(100.0), 0.011)
    assert math.isclose(alpha_eff_iec62471(10000.0), ALPHA_MAX_RAD)
    assert math.isclose(alpha_eff_iec62471(50000.0), ALPHA_MAX_RAD)


def test_alpha_eff_iec62471_monotonic_increasing():
    ts = [0.1, 0.25, 1, 5, 10, 50, 100, 500, 5000, 10000, 50000]
    values = [alpha_eff_iec62471(t) for t in ts]
    assert all(a <= b + 1e-15 for a, b in zip(values, values[1:]))


def test_alpha_eff_iec62471_bad_duration_raises():
    _assert_raises(ValueError, alpha_eff_iec62471, 0.0)
    _assert_raises(ValueError, alpha_eff_iec62471, -1.0)


def test_t2_iec60825_1_at_alpha_min_is_10s():
    assert math.isclose(t2_iec60825_1(ALPHA_MIN_IEC60825_1_RAD), 10.0)


def test_t2_iec60825_1_at_alpha_max_is_100s():
    assert math.isclose(t2_iec60825_1(ALPHA_MAX_RAD), 100.0)


def test_t2_iec60825_1_below_alpha_min_clamps():
    assert math.isclose(t2_iec60825_1(0.0), 10.0)


def test_t2_iec60825_1_monotonic_increasing():
    alphas = [0.0, 0.0015, 0.005, 0.02, 0.05, 0.1, 0.2]
    values = [t2_iec60825_1(a) for a in alphas]
    assert all(a <= b + 1e-12 for a, b in zip(values, values[1:]))


def test_gamma_ph_iec60825_1_at_boundaries():
    assert math.isclose(gamma_ph_iec60825_1(10.0), 0.011)
    assert math.isclose(gamma_ph_iec60825_1(100.0), 0.011)
    assert math.isclose(gamma_ph_iec60825_1(10000.0), 0.110, rel_tol=1e-9)
    assert math.isclose(gamma_ph_iec60825_1(20000.0), 0.110)


def test_gamma_ph_iec60825_1_below_10s_raises():
    _assert_raises(ValueError, gamma_ph_iec60825_1, 5.0)


def test_gamma_ph_iec60825_1_non_positive_raises():
    _assert_raises(ValueError, gamma_ph_iec60825_1, 0.0)


def test_gamma_th_iec60825_1_is_fixed_100_mrad():
    assert GAMMA_TH_IEC60825_1_RAD == 0.1


# ---------------------------------------------------------------------------
# Limiting aperture selection
# ---------------------------------------------------------------------------

def test_limiting_aperture_iec62471_bright_long_exposure_is_3mm():
    assert math.isclose(limiting_aperture_diameter_iec62471(1.0, 100.0), 0.003)


def test_limiting_aperture_iec62471_dim_source_is_7mm():
    assert math.isclose(limiting_aperture_diameter_iec62471(1.0, 1.0), 0.007)


def test_limiting_aperture_iec62471_short_exposure_is_7mm_regardless_of_luminance():
    assert math.isclose(limiting_aperture_diameter_iec62471(0.1, 5000.0), 0.007)


def test_limiting_aperture_iec62471_bad_inputs_raise():
    _assert_raises(ValueError, limiting_aperture_diameter_iec62471, 0.0, 100.0)
    _assert_raises(ValueError, limiting_aperture_diameter_iec62471, 1.0, -1.0)


def test_limiting_aperture_iec60825_1_uv_band():
    assert math.isclose(limiting_aperture_diameter_iec60825_1(300.0, 1.0), 0.001)
    assert math.isclose(limiting_aperture_diameter_iec60825_1(300.0, 1.0, 'skin'), 0.0035)


def test_limiting_aperture_iec60825_1_retinal_band():
    assert math.isclose(limiting_aperture_diameter_iec60825_1(632.8, 10.0), 0.007)
    assert math.isclose(limiting_aperture_diameter_iec60825_1(632.8, 10.0, 'skin'), 0.0035)


def test_limiting_aperture_iec60825_1_ir_band_duration_dependence():
    assert math.isclose(limiting_aperture_diameter_iec60825_1(2000.0, 0.1), 0.001)
    assert math.isclose(limiting_aperture_diameter_iec60825_1(2000.0, 20.0), 0.0035)
    mid = limiting_aperture_diameter_iec60825_1(2000.0, 1.0)
    assert 0.001 < mid < 0.0035


def test_limiting_aperture_iec60825_1_far_ir_band():
    assert math.isclose(limiting_aperture_diameter_iec60825_1(500000.0, 1.0), 0.011)
    assert math.isclose(limiting_aperture_diameter_iec60825_1(500000.0, 1.0, 'skin'), 0.011)


def test_limiting_aperture_iec60825_1_out_of_domain_raises():
    _assert_raises(ValueError, limiting_aperture_diameter_iec60825_1, 100.0, 1.0)
    _assert_raises(ValueError, limiting_aperture_diameter_iec60825_1, 2.0e6, 1.0)


def test_limiting_aperture_iec60825_1_bad_tissue_raises():
    _assert_raises(ValueError, limiting_aperture_diameter_iec60825_1, 632.8, 1.0, 'retina')


# ---------------------------------------------------------------------------
# Aperture averaging
# ---------------------------------------------------------------------------

def test_average_over_aperture_basic():
    positions = [-2.0, -1.0, 0.0, 1.0, 2.0]
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    # aperture diameter 2 -> radius 1 -> includes positions -1, 0, 1
    result = average_over_aperture(positions, values, aperture_diameter_m=2.0)
    assert math.isclose(result, (20.0 + 30.0 + 40.0) / 3.0)


def test_average_over_aperture_off_center():
    positions = [0.0, 1.0, 2.0, 3.0, 4.0]
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    result = average_over_aperture(positions, values, aperture_diameter_m=1.0,
                                    center_position_m=3.0)
    assert math.isclose(result, 4.0)


def test_average_over_aperture_mismatched_lengths_raises():
    _assert_raises(ValueError, average_over_aperture, [0.0, 1.0], [1.0], 1.0)


def test_average_over_aperture_bad_diameter_raises():
    _assert_raises(ValueError, average_over_aperture, [0.0], [1.0], 0.0)


def test_average_over_aperture_empty_window_raises():
    _assert_raises(ValueError, average_over_aperture, [10.0, 20.0], [1.0, 2.0],
                   aperture_diameter_m=1.0, center_position_m=0.0)


# ---------------------------------------------------------------------------
# LimitResult
# ---------------------------------------------------------------------------

def _sample_result(unit: str, value: float = 2.0, duration_s: float = 4.0) -> LimitResult:
    return LimitResult(
        value=value,
        unit=unit,
        wavelength_nm=632.8,
        duration_s=duration_s,
        alpha_rad=ALPHA_MIN_IEC60825_1_RAD,
        region='retinal_thermal',
        time_regime='t <= 10 s',
        equation='Henderson & Schulmeister eq. (3.10) [test fixture]',
    )


def test_limit_result_defaults():
    r = _sample_result('W')
    assert r.factors == {}
    assert r.notes == ""


def test_limit_result_as_power_w_passthrough():
    r = _sample_result('W', value=5.0)
    assert math.isclose(r.as_power_W(), 5.0)


def test_limit_result_as_power_w_from_joules():
    r = _sample_result('J', value=8.0, duration_s=4.0)
    assert math.isclose(r.as_power_W(), 2.0)


def test_limit_result_as_power_w_per_area_unit_raises():
    r = _sample_result('W/m^2')
    _assert_raises(ValueError, r.as_power_W)


# ---------------------------------------------------------------------------
# interp_log
# ---------------------------------------------------------------------------

def test_interp_log_exact_sample_point():
    assert math.isclose(interp_log([400.0, 500.0], [10.0, 100.0], 400.0), 10.0)
    assert math.isclose(interp_log([400.0, 500.0], [10.0, 100.0], 500.0), 100.0)


def test_interp_log_geometric_mean_at_midpoint():
    """Log-space interpolation at the midpoint of a decade-spanning table
    gives the geometric mean, not the arithmetic mean (55.0)."""
    value = interp_log([400.0, 500.0], [10.0, 100.0], 450.0)
    assert math.isclose(value, math.sqrt(10.0 * 100.0), rel_tol=1e-9)
    assert value < 55.0  # would be the (wrong, linear) arithmetic mean


def test_interp_log_nonpositive_value_raises():
    _assert_raises(ValueError, interp_log, [400.0, 500.0], [10.0, 0.0], 450.0)
    _assert_raises(ValueError, interp_log, [400.0, 500.0], [10.0, -1.0], 450.0)


def test_interp_log_out_of_domain_raises():
    _assert_raises(ValueError, interp_log, [400.0, 500.0], [10.0, 100.0], 399.0)
    _assert_raises(ValueError, interp_log, [400.0, 500.0], [10.0, 100.0], 501.0)


def test_interp_log_bad_grid_raises():
    _assert_raises(ValueError, interp_log, [400.0], [10.0], 400.0)
    _assert_raises(ValueError, interp_log, [400.0, 500.0], [10.0], 450.0)
    _assert_raises(ValueError, interp_log, [500.0, 400.0], [10.0, 100.0], 450.0)


# ---------------------------------------------------------------------------
# SpectralPowerDistribution
# ---------------------------------------------------------------------------

def test_spd_bad_quantity_raises():
    _assert_raises(ValueError, SpectralPowerDistribution, [400.0, 500.0], [1.0, 2.0], 'luminance')


def test_spd_bad_grid_raises():
    _assert_raises(ValueError, SpectralPowerDistribution, [400.0], [1.0], 'irradiance')
    _assert_raises(ValueError, SpectralPowerDistribution, [400.0, 500.0], [1.0], 'irradiance')


def test_spd_unit_property():
    spd_irr = SpectralPowerDistribution([400.0, 500.0], [1.0, 2.0], 'irradiance')
    spd_rad = SpectralPowerDistribution([400.0, 500.0], [1.0, 2.0], 'radiance')
    assert spd_irr.unit == 'W/m^2/nm'
    assert spd_rad.unit == 'W/(m^2*sr*nm)'


def test_spd_domain_nm():
    spd = SpectralPowerDistribution([400.0, 450.0, 500.0], [1.0, 2.0, 3.0], 'irradiance')
    assert spd.domain_nm == (400.0, 500.0)


def test_spd_value_at_linear_interp():
    spd = SpectralPowerDistribution([400.0, 500.0], [0.0, 10.0], 'irradiance')
    assert math.isclose(spd.value_at(400.0), 0.0)
    assert math.isclose(spd.value_at(500.0), 10.0)
    assert math.isclose(spd.value_at(450.0), 5.0)


def test_spd_value_at_handles_zero_unlike_interp_log():
    """A red LED's spectrum is legitimately zero in the blue -- value_at
    must not choke on it the way interp_log deliberately does."""
    spd = SpectralPowerDistribution([400.0, 450.0, 600.0, 650.0], [0.0, 0.0, 0.2, 1.0], 'irradiance')
    assert math.isclose(spd.value_at(425.0), 0.0)
    assert math.isclose(spd.value_at(625.0), 0.6)


def test_spd_value_at_out_of_domain_raises():
    spd = SpectralPowerDistribution([400.0, 500.0], [1.0, 2.0], 'irradiance')
    _assert_raises(ValueError, spd.value_at, 399.0)
    _assert_raises(ValueError, spd.value_at, 501.0)


def test_spd_integrate_flat_spectrum_flat_hazard():
    spd = SpectralPowerDistribution([400.0, 500.0], [2.0, 2.0], 'irradiance')
    total = spd.integrate(lambda w: 1.0)
    assert math.isclose(total, 2.0 * 100.0)  # W/m^2/nm * [-] * nm = W/m^2


def test_spd_integrate_matches_analytic_linear_ramp():
    """Trapezoidal quadrature is exact for a linear integrand regardless of
    step size, so this checks the implementation, not just the rule."""
    spd = SpectralPowerDistribution([400.0, 410.0], [0.0, 10.0], 'irradiance')
    total = spd.integrate(lambda w: 1.0, step_nm=5.0)
    assert math.isclose(total, 50.0)  # average value (5) * width (10 nm)


def test_spd_integrate_below_400nm_default_step_is_1nm_equivalent():
    """Domain starting below 400 nm or not shouldn't change the (exact,
    for a constant integrand) result -- only the resampling density."""
    below = SpectralPowerDistribution([200.0, 300.0], [3.0, 3.0], 'irradiance')
    above = SpectralPowerDistribution([400.0, 500.0], [3.0, 3.0], 'irradiance')
    assert math.isclose(below.integrate(lambda w: 1.0), 3.0 * 100.0)
    assert math.isclose(above.integrate(lambda w: 1.0), 3.0 * 100.0)


def test_spd_integrate_bad_step_raises():
    spd = SpectralPowerDistribution([400.0, 500.0], [1.0, 1.0], 'irradiance')
    _assert_raises(ValueError, spd.integrate, lambda w: 1.0, 0.0)
    _assert_raises(ValueError, spd.integrate, lambda w: 1.0, -1.0)


def test_spd_integrate_against_interp_log_hazard_table():
    """End-to-end: a hazard table looked up via interp_log, integrated
    against a synthetic source spectrum -- the shape the IEC 62471 chain uses."""
    hazard_wavelengths = [400.0, 450.0, 500.0]
    hazard_values = [1.0, 10.0, 100.0]  # decade-per-50nm, like B(lambda)'s rise
    hazard_fn = lambda w: interp_log(hazard_wavelengths, hazard_values, w)  # noqa: E731

    spd = SpectralPowerDistribution([400.0, 500.0], [1.0, 1.0], 'irradiance')
    total = spd.integrate(hazard_fn, step_nm=10.0)
    assert total > 0.0
    assert math.isfinite(total)


# ---------------------------------------------------------------------------
# IEC 60825-1 correction factors
# ---------------------------------------------------------------------------

def test_c4_below_700nm_is_one():
    assert math.isclose(c4_iec60825_1(500.0), 1.0)
    assert math.isclose(c4_iec60825_1(699.999), 1.0)


def test_c4_continuous_at_1050nm_boundary():
    # C4 -> 5 as lambda -> 1050 nm from below (Sec. 3.12.3: "a factor of 5
    # higher" at 1050 nm), then held at exactly 5 above.
    assert math.isclose(c4_iec60825_1(1049.999), 5.0, rel_tol=3e-3)
    assert math.isclose(c4_iec60825_1(1050.0), 5.0)
    assert math.isclose(c4_iec60825_1(1399.999), 5.0)


def test_c4_out_of_domain_raises():
    _assert_raises(ValueError, c4_iec60825_1, -1.0)
    _assert_raises(ValueError, c4_iec60825_1, 1400.0)


def test_c7_below_1150nm_is_one():
    assert math.isclose(c7_iec60825_1(1000.0), 1.0)


def test_c7_continuous_at_1200nm_boundary():
    assert math.isclose(c7_iec60825_1(1199.999), 8.0, rel_tol=1e-2)
    assert math.isclose(c7_iec60825_1(1200.0), 8.0)
    assert math.isclose(c7_iec60825_1(1399.999), 8.0)


def test_c7_out_of_domain_raises():
    _assert_raises(ValueError, c7_iec60825_1, -1.0)
    _assert_raises(ValueError, c7_iec60825_1, 1400.0)


def test_c6_at_alpha_min_is_one():
    assert math.isclose(c6_iec60825_1(ALPHA_MIN_IEC60825_1_RAD), 1.0)


def test_c6_at_alpha_max_is_66_67():
    assert math.isclose(c6_iec60825_1(ALPHA_MAX_RAD), 100.0 / 1.5, rel_tol=1e-9)


def test_c6_clamps_outside_bounds():
    assert math.isclose(c6_iec60825_1(0.0), 1.0)
    assert math.isclose(c6_iec60825_1(1.0), 100.0 / 1.5, rel_tol=1e-9)


def test_c3_at_domain_edges():
    assert math.isclose(c3_iec60825_1(400.0), 1.0)
    assert math.isclose(c3_iec60825_1(450.0), 1.0)
    assert math.isclose(c3_iec60825_1(600.0), 1000.0)


def test_c3_out_of_domain_raises():
    _assert_raises(ValueError, c3_iec60825_1, 399.0)
    _assert_raises(ValueError, c3_iec60825_1, 601.0)


# ---------------------------------------------------------------------------
# Retinal-thermal MPE
# ---------------------------------------------------------------------------

def test_mpe_retinal_thermal_ultrashort_raises_not_implemented():
    _assert_raises(NotImplementedError, iec60825_1.mpe_retinal_thermal, 632.8, 1e-6)


def test_mpe_retinal_thermal_wavelength_out_of_range_raises():
    _assert_raises(ValueError, iec60825_1.mpe_retinal_thermal, 300.0, 1.0)
    _assert_raises(ValueError, iec60825_1.mpe_retinal_thermal, 1400.0, 1.0)


def test_mpe_retinal_thermal_short_duration_units_are_radiant_exposure():
    r = iec60825_1.mpe_retinal_thermal(632.8, 0.25)
    assert r.unit == "J/m^2"
    assert math.isclose(r.value, 18.0 * 0.25 ** 0.75, rel_tol=1e-9)


def test_mpe_retinal_thermal_long_duration_units_are_irradiance():
    r = iec60825_1.mpe_retinal_thermal(632.8, 100.0)
    assert r.unit == "W/m^2"
    # Small source: T2(alpha_min) = 10 s exactly, so t_eff caps at 10 s.
    assert math.isclose(r.value, 18.0 * 10.0 ** -0.25, rel_tol=1e-9)


def test_mpe_retinal_thermal_at_alpha_max_matches_henderson_380():
    """Henderson's own worked number [KD5: the book is the oracle]:
    'for alpha=100 mrad, the minimum MPE value equals 66.6x18x100^-1/4
    W/m^2 = 380 W/m^2'."""
    r = iec60825_1.mpe_retinal_thermal(632.8, 100.0, alpha_rad=ALPHA_MAX_RAD)
    assert math.isclose(r.value, 380.0, rel_tol=1e-2)


def test_mpe_retinal_thermal_bad_duration_raises():
    _assert_raises(ValueError, iec60825_1.mpe_retinal_thermal, 632.8, 0.0)
    _assert_raises(ValueError, iec60825_1.mpe_retinal_thermal, 632.8, -1.0)


# ---------------------------------------------------------------------------
# Retinal-photochemical MPE
# ---------------------------------------------------------------------------

def test_mpe_retinal_photochemical_wavelength_out_of_range_raises():
    _assert_raises(ValueError, iec60825_1.mpe_retinal_photochemical, 399.0, 100.0)
    _assert_raises(ValueError, iec60825_1.mpe_retinal_photochemical, 601.0, 100.0)


def test_mpe_retinal_photochemical_below_10s_raises():
    _assert_raises(ValueError, iec60825_1.mpe_retinal_photochemical, 450.0, 5.0)


def test_mpe_retinal_photochemical_non_positive_duration_raises():
    _assert_raises(ValueError, iec60825_1.mpe_retinal_photochemical, 450.0, 0.0)


def test_mpe_retinal_photochemical_short_duration_is_radiant_exposure():
    r = iec60825_1.mpe_retinal_photochemical(450.0, 50.0)
    assert r.unit == "J/m^2"
    assert math.isclose(r.value, 100.0)  # C3(450)=1


def test_mpe_retinal_photochemical_long_duration_is_irradiance():
    r = iec60825_1.mpe_retinal_photochemical(450.0, 1000.0)
    assert r.unit == "W/m^2"
    assert math.isclose(r.value, 1.0)


def test_mpe_retinal_photochemical_continuous_at_100s_boundary():
    below = iec60825_1.mpe_retinal_photochemical(450.0, 99.999)
    above = iec60825_1.mpe_retinal_photochemical(450.0, 100.001)
    # below is J/m^2 (radiant exposure); dividing by duration gives the
    # equivalent irradiance, which should match "above"'s W/m^2 value.
    assert math.isclose(below.value / 99.999, above.value, rel_tol=1e-3)


def test_mpe_retinal_photochemical_wavelength_dependence_matches_c3():
    r400 = iec60825_1.mpe_retinal_photochemical(400.0, 200.0)
    r600 = iec60825_1.mpe_retinal_photochemical(600.0, 200.0)
    assert math.isclose(r400.value, 1.0)
    assert math.isclose(r600.value, 1000.0)


# ---------------------------------------------------------------------------
# Corneal/lens UV MPE -- Henderson & Schulmeister Sec. 3.11 regression
# ---------------------------------------------------------------------------

def test_mpe_cornea_uv_domain_errors():
    _assert_raises(ValueError, iec60825_1.mpe_cornea_uv, 179.0, 1.0)
    _assert_raises(ValueError, iec60825_1.mpe_cornea_uv, 400.0, 1.0)
    _assert_raises(ValueError, iec60825_1.mpe_cornea_uv, 250.0, 0.5e-9)
    _assert_raises(ValueError, iec60825_1.mpe_cornea_uv, 250.0, 30001.0)


def test_mpe_cornea_uv_180_to_302_5_is_flat_30():
    for wl in (180.0, 250.0, 302.4):
        r = iec60825_1.mpe_cornea_uv(wl, 1.0)
        assert r.unit == "J/m^2"
        assert math.isclose(r.value, 30.0)


def test_mpe_cornea_uv_308nm_matches_henderson_worked_example():
    """Henderson's own KrF/XeCl worked example [Chaves Ch. 3:854-860]:
    at 308 nm, T1 = 25 us, a 20 ns pulse (< T1) uses the thermal limit of
    67 J/m^2; the photochemical limit (for t > T1) equals 398 J/m^2."""
    thermal = iec60825_1.mpe_cornea_uv(308.0, 20e-9)
    assert math.isclose(thermal.value, 67.0, rel_tol=0.01)
    assert math.isclose(thermal.factors["T1_s"], 25e-6, rel_tol=0.01)

    photochemical = iec60825_1.mpe_cornea_uv(308.0, 1.0)
    assert math.isclose(photochemical.value, 398.0, rel_tol=0.01)


def test_mpe_cornea_uv_355nm_matches_henderson_worked_example():
    """Same worked example, continued at 355 nm: the thermal limit for a
    20 ns pulse is the SAME 67 J/m^2 as at 308 nm -- direct textual proof
    that the 315-400 nm short-duration bracket has no wavelength
    dependence (resolving this module's documented source ambiguity)."""
    thermal = iec60825_1.mpe_cornea_uv(355.0, 20e-9)
    assert math.isclose(thermal.value, 67.0, rel_tol=0.01)

    mid = iec60825_1.mpe_cornea_uv(355.0, 100.0)
    assert mid.unit == "J/m^2"
    assert math.isclose(mid.value, 10000.0)

    long_term = iec60825_1.mpe_cornea_uv(355.0, 5000.0)
    assert long_term.unit == "W/m^2"
    assert math.isclose(long_term.value, 10.0)


def test_mpe_cornea_uv_315_400_no_wavelength_dependence_below_10s():
    r1 = iec60825_1.mpe_cornea_uv(320.0, 1e-6)
    r2 = iec60825_1.mpe_cornea_uv(399.0, 1e-6)
    assert math.isclose(r1.value, r2.value)


def test_mpe_cornea_uv_302_5_to_315_crossover_continuity():
    """T1 evaluated at exactly 315 nm should equal exactly 10 s -- the
    handoff point into the 315-400 nm band's own 10 s bracket boundary."""
    t1_at_315 = iec60825_1.mpe_cornea_uv(314.999, 5.0).factors["T1_s"]
    assert math.isclose(t1_at_315, 10.0, rel_tol=3e-3)


# ---------------------------------------------------------------------------
# Skin thermal MPE -- Henderson & Schulmeister Sec. 3.8
# ---------------------------------------------------------------------------

def test_mpe_skin_thermal_domain_errors():
    _assert_raises(ValueError, iec60825_1.mpe_skin_thermal, 399.0, 1.0)
    _assert_raises(ValueError, iec60825_1.mpe_skin_thermal, 1400.0, 1.0)
    _assert_raises(ValueError, iec60825_1.mpe_skin_thermal, 500.0, 0.0)
    _assert_raises(ValueError, iec60825_1.mpe_skin_thermal, 500.0, 30001.0)


def test_mpe_skin_thermal_short_pulse_bracket():
    r = iec60825_1.mpe_skin_thermal(500.0, 50e-9)
    assert r.unit == "J/m^2"
    assert math.isclose(r.value, 200.0)  # C4(500nm)=1


def test_mpe_skin_thermal_long_duration_is_constant_irradiance():
    r = iec60825_1.mpe_skin_thermal(500.0, 1000.0)
    assert r.unit == "W/m^2"
    assert math.isclose(r.value, 2000.0)


def test_mpe_skin_thermal_wavelength_dependence_matches_c4():
    r_ir = iec60825_1.mpe_skin_thermal(1050.0, 1000.0)
    assert math.isclose(r_ir.value, 2000.0 * 5.0, rel_tol=1e-3)  # C4(1050)~5


def test_mpe_skin_thermal_continuous_across_10s_boundary():
    """The standard's own two brackets meet only approximately at 10 s
    (11000*10^0.25/10 = 1956 W/m^2 vs. the flat 2000 W/m^2 bracket) -- a
    ~2.2% gap consistent with the rounding this project has repeatedly
    found in the standard's own bracket boundaries, not a bug."""
    below = iec60825_1.mpe_skin_thermal(500.0, 9.999)
    above = iec60825_1.mpe_skin_thermal(500.0, 10.001)
    assert math.isclose(below.value / 9.999, above.value, rel_tol=0.03)


# ---------------------------------------------------------------------------
# AEL_class_1 UV dispatch, and ael_skin
# ---------------------------------------------------------------------------

def test_ael_class_1_dispatches_to_uv_below_400nm():
    r = iec60825_1.ael_class_1(250.0, duration_s=30000.0)
    assert r.unit == "W"
    assert r.value > 0.0
    assert math.isfinite(r.value)


def test_ael_class_1_far_ir_not_implemented():
    _assert_raises(NotImplementedError, iec60825_1.ael_class_1, 1500.0, 100.0)


def test_ael_class_1_uv_default_duration_matches_correct_time_base():
    """C-EYE-02 regression: ael_class_1's duration_s used to default to
    100.0 unconditionally, which is wrong for UV (Table 4.3 mandates
    30000 s there) -- silently giving a ~300x-too-permissive AEL unless the
    caller explicitly overrode it. duration_s now defaults to None, which
    resolves per wavelength band; the omitted-argument call must match the
    explicit-30000s call exactly, not the old explicit-100s one."""
    wavelength_nm = 250.0
    default = iec60825_1.ael_class_1(wavelength_nm)
    explicit_correct = iec60825_1.ael_class_1(wavelength_nm, duration_s=30000.0)
    explicit_wrong_old_default = iec60825_1.ael_class_1(wavelength_nm, duration_s=100.0)
    assert math.isclose(default.value, explicit_correct.value, rel_tol=1e-12)
    assert default.value < explicit_wrong_old_default.value  # tighter (correct) is smaller
    assert math.isclose(
        explicit_wrong_old_default.value / default.value, 300.0, rel_tol=1e-6
    )


def test_ael_class_1_visible_default_duration_unaffected():
    """The fix must not change visible/near-IR behaviour: 100 s was already
    correct there, and stays the resolved default."""
    default = iec60825_1.ael_class_1(632.8)
    explicit = iec60825_1.ael_class_1(632.8, duration_s=100.0)
    assert math.isclose(default.value, explicit.value, rel_tol=1e-12)


def test_ael_class_3r_uv_default_duration_matches_correct_time_base():
    default = iec60825_1.ael_class_3r(250.0)
    explicit_correct = iec60825_1.ael_class_3r(250.0, duration_s=30000.0)
    assert math.isclose(default.value, explicit_correct.value, rel_tol=1e-12)


def test_classify_measurement_uv_default_no_longer_silently_wrong():
    """The live worked example behind C-EYE-02: a UV exposure that is
    genuinely hazardous (above Class 3R) used to be silently reported as
    "Class 1 or 1M" (eye-safe) if the caller relied on
    classify_measurement's old duration_s_class1=100.0 default instead of
    knowing to pass 30000.0 for UV. It must now classify correctly by
    default."""
    wavelength_nm = 250.0
    correct_ael1 = iec60825_1.ael_class_1(wavelength_nm, duration_s=30000.0).value
    wrong_ael1 = iec60825_1.ael_class_1(wavelength_nm, duration_s=100.0).value
    hazardous_power = (correct_ael1 + wrong_ael1) / 2.0  # above the correct AEL,
                                                          # below the old wrong one
    assert iec60825_1.classify_measurement(hazardous_power, wavelength_nm) == "above Class 3R (3B or 4)"


def test_ael_skin_visible_uses_skin_aperture():
    r = iec60825_1.ael_skin(500.0, 100.0)
    assert r.unit == "W"
    assert "3.5000 mm" in r.notes  # skin's 3.5 mm aperture, not the eye's 7 mm


def test_ael_skin_uv_matches_cornea_mpe_different_aperture():
    """Below 400 nm, skin MPE == corneal MPE (Henderson Sec. 3.8), but the
    AEL differs because the limiting aperture differs (1 mm eye vs
    3.5 mm skin in the UV band)."""
    eye = iec60825_1.ael_class_1(250.0, 30000.0)
    skin = iec60825_1.ael_skin(250.0, 30000.0)
    assert skin.value > eye.value  # larger aperture -> larger AEL
    ratio = skin.value / eye.value
    assert math.isclose(ratio, (3.5 / 1.0) ** 2, rel_tol=1e-6)


def test_ael_skin_far_ir_not_implemented():
    _assert_raises(NotImplementedError, iec60825_1.ael_skin, 1500.0, 100.0)


# ---------------------------------------------------------------------------
# AEL and classification -- Henderson & Schulmeister Sec. 4.8 regression
# ---------------------------------------------------------------------------

def test_ael_class_1_small_source_visible_matches_henderson_04mw():
    r = iec60825_1.ael_class_1(632.8, 100.0)
    assert r.unit == "W"
    assert math.isclose(r.value, 0.4e-3, rel_tol=0.03)


def test_ael_class_1_photochemical_governs_in_blue_matches_henderson_004mw():
    """Henderson Sec. 3.12.7's own cross-check: for the wavelength range
    400-450 nm and t>=100s, the photochemical limit is 1 W/m^2, i.e.
    'the corresponding AEL for Class 1 and Class 1M equals 0.04 mW.'"""
    for wl in (400.0, 425.0, 450.0):
        r = iec60825_1.ael_class_1(wl, 100.0)
        assert math.isclose(r.value, 0.04e-3, rel_tol=0.05)
        assert "retinal_photochemical" in r.notes


def test_ael_class_1_thermal_governs_above_500nm():
    """Henderson: 'for wavelengths above 500 nm, for small sources, the
    thermal limit is the more critical one for all exposure durations.'"""
    r = iec60825_1.ael_class_1(600.0, 100.0)
    thermal_only = iec60825_1.ael_class_1(632.8, 100.0)  # outside photochemical domain entirely
    assert math.isclose(r.value, thermal_only.value, rel_tol=1e-9)
    assert "retinal_thermal" in r.notes


def test_ael_class_1_unaffected_outside_photochemical_wavelength_domain():
    """The two Sec. 4.8 case studies (632.8 nm, 670 nm) must be completely
    unaffected by adding the photochemical comparison."""
    r = iec60825_1.ael_class_1(632.8, 100.0)
    assert math.isclose(r.value, 0.4e-3, rel_tol=0.03)
    assert r.notes == "limiting aperture diameter = 7.0000 mm"


def test_ael_class_1_unaffected_at_short_duration_within_photochemical_wavelengths():
    """A blue/green wavelength at t<=10s must not attempt the photochemical
    comparison (undefined there) -- thermal-only, unchanged behaviour."""
    r_short = iec60825_1.ael_class_1(450.0, 1.0)
    assert "governing hazard" not in r_short.notes


def test_ael_class_2_small_source_visible_matches_henderson_1mw():
    r = iec60825_1.ael_class_2(632.8)
    assert math.isclose(r.value, 1.0e-3, rel_tol=0.03)


def test_ael_class_2_out_of_visible_range_raises():
    _assert_raises(ValueError, iec60825_1.ael_class_2, 900.0)


def test_ael_class_3r_visible_matches_henderson_5mw():
    r = iec60825_1.ael_class_3r(632.8, 100.0)
    assert math.isclose(r.value, 5.0e-3, rel_tol=0.03)


def test_hene_alignment_laser_case_study_4_8_1():
    """Henderson Sec. 4.8.1: 0.9 mW cw, 632.8 nm, small source (C6=1) ->
    exceeds AEL Class 1/1M (0.4 mW), below AEL Class 2/2M (1 mW) ->
    classified Class 2."""
    assert iec60825_1.classify_measurement(0.9e-3, 632.8) == "Class 2 or 2M"


def test_low_level_therapy_laser_case_study_4_8_2():
    """Henderson Sec. 4.8.2: 670 nm bare laser diode, small source.
    Condition 2 (14 mm, 7 mm aperture): 7.8 mW measured -> above AEL
    Class 3R (5 mW), i.e. would imply Class 3B in isolation. Condition 3
    (100 mm naked eye, 7 mm aperture): 0.34 mW measured -> below AEL
    Class 1/1M (0.4 mW). The book's own conclusion, combining both
    conditions (not automated by classify_measurement -- see its
    docstring), is Class 1M: safe for the naked eye, hazardous through an
    eye loupe."""
    condition_2 = iec60825_1.classify_measurement(7.8e-3, 670.0)
    condition_3 = iec60825_1.classify_measurement(0.34e-3, 670.0)
    assert condition_2 == "above Class 3R (3B or 4)"
    assert condition_3 == "Class 1 or 1M"


def test_classify_measurement_negative_power_raises():
    _assert_raises(ValueError, iec60825_1.classify_measurement, -1.0, 632.8)


def test_classify_measurement_non_visible_skips_class_2():
    """A non-visible wavelength (e.g. 900 nm) has no Class 2/2M -- a
    measurement between AEL1 and AEL3R should land on Class 3R directly,
    not silently fall through Class 2 (which does not apply there)."""
    ael1 = iec60825_1.ael_class_1(900.0, 100.0)
    ael3r = iec60825_1.ael_class_3r(900.0, 100.0)
    between = (ael1.value + ael3r.value) / 2.0
    assert iec60825_1.classify_measurement(between, 900.0) == "Class 3R"


# ---------------------------------------------------------------------------
# IEC 62471 hazard-function tables (S/B/R)
# ---------------------------------------------------------------------------

def test_s_actinic_uv_peak_at_270nm():
    assert hazard_functions.S_actinic_uv(270.0) == 1.0


def test_s_actinic_uv_known_checkpoints():
    """Spot-check against Directive Table 1.2's own tabulated values,
    the Directive 2006/25/EC guide."""
    assert math.isclose(hazard_functions.S_actinic_uv(180.0), 0.0120, rel_tol=1e-9)
    assert math.isclose(hazard_functions.S_actinic_uv(300.0), 0.3000, rel_tol=1e-9)
    assert math.isclose(hazard_functions.S_actinic_uv(400.0), 0.00003, rel_tol=1e-9)


def test_s_actinic_uv_out_of_domain_raises():
    _assert_raises(ValueError, hazard_functions.S_actinic_uv, 179.0)
    _assert_raises(ValueError, hazard_functions.S_actinic_uv, 401.0)


def test_b_blue_light_flat_below_380nm():
    assert hazard_functions.B_blue_light(300.0) == 0.01
    assert hazard_functions.B_blue_light(379.999) == 0.01


def test_b_blue_light_peak_at_435_440nm():
    assert hazard_functions.B_blue_light(435.0) == 1.0
    assert hazard_functions.B_blue_light(440.0) == 1.0


def test_b_blue_light_continuous_at_500nm_and_600nm():
    """The 500-600 nm closed-form tail must meet the tabulated value at
    500 nm and the flat 600-700 nm value at 600 nm exactly (both boundary
    conditions were used to reconstruct the formula's coefficients from
    the source table's OCR-garbled exponent notation)."""
    assert math.isclose(hazard_functions.B_blue_light(500.0), 0.1, rel_tol=1e-9)
    assert math.isclose(
        hazard_functions.B_blue_light(500.0 + 1e-6),
        0.1, rel_tol=1e-3,
    )
    assert math.isclose(hazard_functions.B_blue_light(600.0), 0.001, rel_tol=1e-6)
    assert hazard_functions.B_blue_light(600.0 + 1e-6) == 0.001


def test_b_blue_light_out_of_domain_raises():
    _assert_raises(ValueError, hazard_functions.B_blue_light, 299.0)
    _assert_raises(ValueError, hazard_functions.B_blue_light, 701.0)


def test_r_retinal_thermal_peak_at_435_440nm():
    assert hazard_functions.R_retinal_thermal(435.0) == 10.0
    assert hazard_functions.R_retinal_thermal(440.0) == 10.0


def test_r_retinal_thermal_is_ten_times_b_below_500nm():
    """Directive Table 1.3: R(lambda) = 10*B(lambda) throughout 380-500 nm."""
    for wl in (380.0, 400.0, 435.0, 470.0, 500.0):
        assert math.isclose(
            hazard_functions.R_retinal_thermal(wl),
            10.0 * hazard_functions.B_blue_light(wl),
            rel_tol=1e-9,
        )


def test_r_retinal_thermal_flat_500_to_700nm():
    assert hazard_functions.R_retinal_thermal(500.0) == 1.0
    assert hazard_functions.R_retinal_thermal(600.0) == 1.0
    assert hazard_functions.R_retinal_thermal(700.0) == 1.0


def test_r_retinal_thermal_continuous_at_1050_1150_1200nm():
    assert math.isclose(hazard_functions.R_retinal_thermal(1050.0), 0.2, rel_tol=2e-2)
    assert hazard_functions.R_retinal_thermal(1050.0 + 1e-6) == 0.2
    assert hazard_functions.R_retinal_thermal(1150.0) == 0.2
    assert math.isclose(hazard_functions.R_retinal_thermal(1200.0), 0.02, rel_tol=1e-6)
    assert hazard_functions.R_retinal_thermal(1200.0 + 1e-6) == 0.02
    assert hazard_functions.R_retinal_thermal(1400.0) == 0.02


def test_r_retinal_thermal_out_of_domain_raises():
    _assert_raises(ValueError, hazard_functions.R_retinal_thermal, 379.0)
    _assert_raises(ValueError, hazard_functions.R_retinal_thermal, 1401.0)


# ---------------------------------------------------------------------------
# IEC 62471 exposure limits (eye_safety.iec62471)
# ---------------------------------------------------------------------------

def test_iec62471_mpe_actinic_uv_daily_value():
    r = eye_safety.iec62471.mpe_actinic_uv(28800.0)
    assert math.isclose(r.value, 30.0 / 28800.0, rel_tol=1e-9)
    assert r.unit == "W/m^2"


def test_iec62471_mpe_actinic_uv_out_of_domain_raises():
    _assert_raises(ValueError, eye_safety.iec62471.mpe_actinic_uv, 0.0)
    _assert_raises(ValueError, eye_safety.iec62471.mpe_actinic_uv, 28800.001)


def test_iec62471_mpe_near_uv_daily_value():
    r = eye_safety.iec62471.mpe_near_uv(28800.0)
    assert math.isclose(r.value, 1.0e4 / 28800.0, rel_tol=1e-9)


def test_iec62471_mpe_blue_light_large_vs_small_source_dispatch():
    large = eye_safety.iec62471.mpe_blue_light(1000.0, 0.020)  # alpha >= 11 mrad
    small = eye_safety.iec62471.mpe_blue_light(1000.0, 0.005)  # alpha < 11 mrad
    assert large.unit == "W/(m^2*sr)"
    assert math.isclose(large.value, 1.0e6 / 1000.0, rel_tol=1e-9)
    assert small.unit == "W/m^2"
    assert math.isclose(small.value, 100.0 / 1000.0, rel_tol=1e-9)


def test_iec62471_mpe_blue_light_long_duration_constants():
    large = eye_safety.iec62471.mpe_blue_light(20000.0, 0.020)
    small = eye_safety.iec62471.mpe_blue_light(20000.0, 0.005)
    assert large.value == 100.0
    assert small.value == 0.01


def test_iec62471_mpe_blue_light_boundary_alpha_is_large_source():
    """alpha exactly 11 mrad is the large-source (radiance) branch --
    Directive text: 'for alpha >= 11 mrad'."""
    r = eye_safety.iec62471.mpe_blue_light(1000.0, 0.011)
    assert r.unit == "W/(m^2*sr)"


def test_iec62471_mpe_retinal_thermal_long_duration():
    r = eye_safety.iec62471.mpe_retinal_thermal(28800.0, 0.575)
    assert r.unit == "W/(m^2*sr)"
    assert math.isclose(r.value, 2.8e7 / 100.0, rel_tol=1e-9)  # alpha clamped to 100 mrad


def test_iec62471_mpe_retinal_thermal_continuous_at_10s_boundary():
    just_above = eye_safety.iec62471.mpe_retinal_thermal(10.0 + 1e-9, 0.05)
    just_below = eye_safety.iec62471.mpe_retinal_thermal(10.0 - 1e-9, 0.05)
    assert math.isclose(just_above.value, just_below.value, rel_tol=1e-2)


def test_iec62471_mpe_retinal_thermal_ultrashort_raises():
    _assert_raises(ValueError, eye_safety.iec62471.mpe_retinal_thermal, 1e-6, 0.02)


def test_iec62471_mpe_retinal_thermal_ira_long_duration_only():
    r = eye_safety.iec62471.mpe_retinal_thermal_ira(1000.0, 0.005)
    assert math.isclose(r.value, 6.0e6 / 11.0, rel_tol=1e-9)  # alpha clamped to 11 mrad
    _assert_raises(ValueError, eye_safety.iec62471.mpe_retinal_thermal_ira, 5.0, 0.02)


def test_iec62471_mpe_ir_eye_short_and_long_duration():
    short = eye_safety.iec62471.mpe_ir_eye(100.0)
    long = eye_safety.iec62471.mpe_ir_eye(2000.0)
    assert math.isclose(short.value, 18000.0 * (100.0 ** -0.75), rel_tol=1e-9)
    assert long.value == 100.0


def test_iec62471_mpe_skin_thermal_domain():
    r = eye_safety.iec62471.mpe_skin_thermal(1.0)
    assert math.isclose(r.value, 20000.0, rel_tol=1e-9)
    _assert_raises(ValueError, eye_safety.iec62471.mpe_skin_thermal, 10.001)


def test_iec62471_no_namespace_collision_with_iec60825_1():
    """C-EYE-04: the two standards' same-named functions must remain
    distinguishable by module, never silently shadow one another --
    and neither is flattened to a bare package-level name that could
    become an accidental default for the other."""
    assert eye_safety.iec62471.mpe_retinal_thermal is not eye_safety.iec60825_1.mpe_retinal_thermal
    assert eye_safety.iec62471.classify_measurement is not eye_safety.iec60825_1.classify_measurement
    assert not hasattr(eye_safety, "mpe_retinal_thermal")
    assert not hasattr(eye_safety, "classify_measurement")


# ---------------------------------------------------------------------------
# Retinal-thermal risk-group classification, corrected against IEC 62471's
# own Table 6.1 (C-EYE-06) -- found while adding dimensional checks to the
# inputs [KD4]. See iec62471.py's module docstring
# and _retinal_thermal_classification_limit_w_m2_sr's own docstring.
# ---------------------------------------------------------------------------

def test_retinal_thermal_classification_limit_exempt_equals_rg1():
    """Table 6.1: Exempt and RG1 share the *same* retinal-thermal limit --
    unlike every other hazard in this module, RG1 is not more permissive
    here. This was the core of the bug: the old code used a different
    ('100 s') duration lookup for RG1 that happened to give the right
    number by accident, framed as if it were RG1's own distinct criterion."""
    fn = eye_safety.iec62471._retinal_thermal_classification_limit_w_m2_sr
    for alpha in (0.0017, 0.02, 0.1, 0.5):
        assert math.isclose(fn("Exempt", alpha), fn("RG1", alpha), rel_tol=1e-9)


def test_retinal_thermal_classification_limits_match_table_6_1():
    """IEC 62471 Table 6.1: Exempt = RG1 = 28000/alpha_rad, RG2 =
    71000/alpha_rad, all W/(m^2*sr). Checked at alpha=0.1 rad (100 mrad),
    matching this project's own earlier diagnostic run exactly."""
    fn = eye_safety.iec62471._retinal_thermal_classification_limit_w_m2_sr
    alpha = 0.1
    assert math.isclose(fn("Exempt", alpha), 28000.0 / alpha, rel_tol=1e-9)
    assert math.isclose(fn("RG1", alpha), 28000.0 / alpha, rel_tol=1e-9)
    # RG2 reuses mpe_retinal_thermal's short-branch *value* rather than
    # duplicating Table 6.1's own rounded constant -- matches to within
    # the same <1% rounding tolerance already established elsewhere in
    # this module for the standard's own published constants.
    assert math.isclose(fn("RG2", alpha), 71000.0 / alpha, rel_tol=0.01)


def test_retinal_thermal_classification_limit_unknown_group_raises():
    _assert_raises(
        ValueError, eye_safety.iec62471._retinal_thermal_classification_limit_w_m2_sr,
        "RG7", 0.1,
    )


def test_retinal_thermal_classification_limit_public_matches_private_value():
    """The public, LimitResult-returning function must never drift
    from the float-only one classify_measurement actually uses -- the
    private function now delegates to this one, so this is really a
    delegation check, not two independent implementations."""
    for group in ("Exempt", "RG1", "RG2"):
        for alpha in (0.02, 0.1, 0.5):
            public = eye_safety.iec62471.retinal_thermal_classification_limit(group, alpha)
            private = eye_safety.iec62471._retinal_thermal_classification_limit_w_m2_sr(group, alpha)
            assert math.isclose(public.value, private, rel_tol=1e-12)


def test_retinal_thermal_classification_limit_unit_always_w_m2_sr():
    """Building the comparison explanations found this directly [KD4]: RG2's donor LimitResult
    (mpe_retinal_thermal's own short-pulse branch) is unit='J/(m^2*sr)'
    (a radiant exposure) -- correct for that function's own general-
    purpose role, but Table 6.1 states every risk group's classification
    limit is radiance-typed. The public wrapper must relabel it, not
    forward the donor's own unit verbatim."""
    for group in ("Exempt", "RG1", "RG2"):
        result = eye_safety.iec62471.retinal_thermal_classification_limit(group, 0.1)
        assert result.unit == "W/(m^2*sr)"
        assert result.region == "retinal_thermal"


def test_risk_group_reference_duration_s_matches_internal_table():
    for group in ("Exempt", "RG1", "RG2"):
        for hazard, key in (("uv", "uv"), ("near_uv", "near_uv"), ("blue", "blue"), ("ir", "ir")):
            expected = eye_safety.iec62471._RISK_GROUP_DURATIONS_S[group][key]
            assert eye_safety.iec62471.risk_group_reference_duration_s(group, hazard) == expected


def test_risk_group_reference_duration_s_unknown_raises_keyerror():
    _assert_raises(KeyError, eye_safety.iec62471.risk_group_reference_duration_s, "Exempt", "nope")


def test_risk_group_durations_no_longer_has_retinal_thermal_key():
    """The stale, misleading per-group duration lookup is gone entirely --
    retinal_thermal is handled by its own dedicated function now, not by
    treating it like every other duration-based hazard."""
    for group in ("Exempt", "RG1", "RG2"):
        assert "retinal_thermal" not in eye_safety.iec62471._RISK_GROUP_DURATIONS_S[group]


def test_classify_measurement_retinal_thermal_only_uses_corrected_limits():
    """A direct, black-box confirmation that classify_measurement's own
    ascending-severity loop actually calls the corrected function: a
    measured L_R comfortably under Exempt/RG1's shared limit, at an alpha
    where the old buggy code would have used a *different* limit for
    Exempt (wrong unit, ~1% different number) than RG1 -- both should now
    agree, and the source should classify Exempt."""
    alpha = 0.05
    limit = eye_safety.iec62471._retinal_thermal_classification_limit_w_m2_sr("Exempt", alpha)
    l_r = limit * 0.5  # comfortably under both Exempt's and RG1's (identical) limit
    assert eye_safety.iec62471.classify_measurement(alpha, l_r_w_m2_sr=l_r) == "Exempt"


def test_classify_measurement_retinal_thermal_rg1_boundary():
    """A value that exceeds Exempt's limit but stays under RG1's --
    meaningless before the fix (RG1 used a fabricated criterion), directly
    exercises the corrected shared Exempt/RG1 limit. Since Exempt and RG1
    now share the identical limit, no value can pass RG1 while failing
    Exempt for this hazard alone -- so a value just over the shared limit
    must fall through past RG1 (which also fails it) to RG2."""
    alpha = 0.05
    limit = eye_safety.iec62471._retinal_thermal_classification_limit_w_m2_sr("Exempt", alpha)
    l_r = limit * 1.5  # exceeds the shared Exempt/RG1 limit
    result = eye_safety.iec62471.classify_measurement(alpha, l_r_w_m2_sr=l_r)
    assert result in ("RG2", "RG3")  # not Exempt, not RG1 -- confirms Exempt/RG1 are genuinely linked


# ---------------------------------------------------------------------------
# Real worked examples, Directive 2006/25/EC non-binding guide [KD5]
# Appendix D.1.21 (UVA blacklight) and D.1.22 (metal-halide streetlight)
# ---------------------------------------------------------------------------

def test_worked_example_d1_21_uva_blacklight_limits_match_guide():
    """the Directive 2006/25/EC guide. All four stated limits must
    match the guide's own numbers exactly, and all four measured values
    (converted to radiance where the guide does) must be confirmed safe,
    exactly as the guide concludes."""
    alpha_rad = 0.575
    e_eff = 30e-6
    e_uva = 176e-3
    l_b = 55e-3   # 3e-3 W/m^2 / 0.055 sr, as stated in the guide
    l_r = 255e-3  # 14e-3 W/m^2 / 0.055 sr

    limit_a = eye_safety.iec62471.mpe_actinic_uv(28800.0)
    limit_b = eye_safety.iec62471.mpe_near_uv(28800.0)
    limit_d = eye_safety.iec62471.mpe_blue_light(28800.0, alpha_rad)
    limit_g = eye_safety.iec62471.mpe_retinal_thermal(28800.0, alpha_rad)

    assert math.isclose(limit_d.value, 100.0, rel_tol=1e-9)
    assert math.isclose(limit_g.value, 280000.0, rel_tol=1e-9)  # "280 kW/(m^2 sr)"

    assert e_eff <= limit_a.value
    assert e_uva <= limit_b.value
    assert l_b <= limit_d.value
    assert l_r <= limit_g.value

    assert eye_safety.iec62471.classify_measurement(
        alpha_rad, e_eff_w_m2=e_eff, e_uva_w_m2=e_uva,
        blue_light_value=l_b, l_r_w_m2_sr=l_r,
    ) == "Exempt"


def test_worked_example_d1_22_streetlight_limits_match_guide():
    """the Directive 2006/25/EC guide. Note the blue-light solid
    angle (0.01 sr, stated explicitly) differs from the source's true
    solid angle (0.0002 sr) used for retinal thermal -- both are the
    guide's own numbers, reproduced exactly, not independently derived
    here."""
    alpha_rad = 0.015
    e_eff = 7e-6
    e_uva = 29e-3
    l_b = 86e-3 / 0.01     # 8.6 W/(m^2 sr)
    l_r = 1323e-3 / 0.0002  # 6615 W/(m^2 sr)

    limit_a = eye_safety.iec62471.mpe_actinic_uv(28800.0)
    limit_b = eye_safety.iec62471.mpe_near_uv(28800.0)
    limit_d = eye_safety.iec62471.mpe_blue_light(28800.0, alpha_rad)
    limit_g = eye_safety.iec62471.mpe_retinal_thermal(28800.0, alpha_rad)

    assert math.isclose(limit_d.value, 100.0, rel_tol=1e-9)
    assert math.isclose(limit_g.value, 2.8e7 / 15.0, rel_tol=1e-9)

    assert e_eff <= limit_a.value
    assert e_uva <= limit_b.value
    assert l_b <= limit_d.value
    assert l_r <= limit_g.value

    assert eye_safety.iec62471.classify_measurement(
        alpha_rad, e_eff_w_m2=e_eff, e_uva_w_m2=e_uva,
        blue_light_value=l_b, l_r_w_m2_sr=l_r,
    ) == "Exempt"


def test_classify_measurement_iec62471_deliberately_hazardous_case_is_rg3():
    assert eye_safety.iec62471.classify_measurement(
        0.001, blue_light_value=500.0,
    ) == "RG3"


# ---------------------------------------------------------------------------
# Deterministic input-framing primitives
# ---------------------------------------------------------------------------

def test_angle_from_size_distance_matches_small_angle_approximation():
    """IEC 62471 Sec. 4.2.2's own worked example (also exercised by
    test_alpha_from_axes_iec62471_worked_example above via inline division):
    a 20 mm x 3 mm tube at 200 mm. The exact 2*atan(size/(2*distance)) form
    should agree with the small-angle approximation size/distance to a few
    parts in a thousand at this angle, not exactly -- the whole point of
    using the exact form."""
    exact = angle_from_size_distance(20.0e-3, 200.0e-3)
    approx = 20.0e-3 / 200.0e-3
    assert math.isclose(exact, approx, rel_tol=2e-3)
    assert exact != approx


def test_angle_from_size_distance_bad_size_raises():
    _assert_raises(ValueError, angle_from_size_distance, 0.0, 1.0)
    _assert_raises(ValueError, angle_from_size_distance, -1.0, 1.0)


def test_angle_from_size_distance_bad_distance_raises():
    _assert_raises(ValueError, angle_from_size_distance, 1.0, 0.0)
    _assert_raises(ValueError, angle_from_size_distance, 1.0, -1.0)


def test_radiance_from_irradiance_reproduces_worked_example_d1_21():
    """The exact E->L conversion done by hand in
    notebooks/_gen_eye_safety_iec62471_broadband_example_nb.py for D.1.21
    (l_b = 3e-3 / omega_sr), now a named, tested function instead of ad hoc
    notebook arithmetic. The guide itself rounds these to "55" and "255"
    mW/(m^2 sr) -- exact division gives 54.5/254.5, matching the notebook's
    own inline arithmetic (verified identical), not the guide's rounding."""
    l_b = radiance_from_irradiance(3e-3, 0.055)
    l_r = radiance_from_irradiance(14e-3, 0.055)
    assert math.isclose(l_b, 3e-3 / 0.055, rel_tol=1e-9)
    assert math.isclose(l_r, 14e-3 / 0.055, rel_tol=1e-9)
    assert math.isclose(l_b, 55e-3, rel_tol=0.02)
    assert math.isclose(l_r, 255e-3, rel_tol=0.02)


def test_radiance_from_irradiance_reproduces_worked_example_d1_22():
    """Same conversion, D.1.22's two different solid angles (blue-light's
    widened averaging aperture vs. retinal-thermal's true one)."""
    l_b = radiance_from_irradiance(86e-3, 0.01)
    l_r = radiance_from_irradiance(1323e-3, 0.0002)
    assert math.isclose(l_b, 8.6, rel_tol=1e-9)
    assert math.isclose(l_r, 6615.0, rel_tol=1e-9)


def test_radiance_from_irradiance_bad_solid_angle_raises():
    _assert_raises(ValueError, radiance_from_irradiance, 1.0, 0.0)
    _assert_raises(ValueError, radiance_from_irradiance, 1.0, -1.0)


def test_irradiance_from_radiance_is_the_inverse():
    e = 3e-3
    omega = 0.055
    l = radiance_from_irradiance(e, omega)
    assert math.isclose(irradiance_from_radiance(l, omega), e, rel_tol=1e-9)


def test_irradiance_from_radiance_bad_solid_angle_raises():
    _assert_raises(ValueError, irradiance_from_radiance, 1.0, 0.0)
    _assert_raises(ValueError, irradiance_from_radiance, 1.0, -1.0)


def test_hazard_label_to_function_covers_documented_letters():
    """Directive Annex I's own lettering, as a checkable table instead of
    something read from the guide's prose each time (the mapping this
    project's D.1.21/D.1.22 notebook performed by hand)."""
    table = eye_safety.iec62471.HAZARD_LABEL_TO_FUNCTION
    assert table['a'] is eye_safety.iec62471.mpe_actinic_uv
    assert table['b'] is eye_safety.iec62471.mpe_near_uv
    for letter in ('c', 'd', 'e', 'f'):
        assert table[letter] is eye_safety.iec62471.mpe_blue_light
    for letter in ('g', 'h'):
        assert table[letter] is eye_safety.iec62471.mpe_retinal_thermal
    assert table['j'] is eye_safety.iec62471.mpe_retinal_thermal_ira
    for letter in ('m', 'n'):
        assert table[letter] is eye_safety.iec62471.mpe_ir_eye
    assert table['o'] is eye_safety.iec62471.mpe_skin_thermal


def test_hazard_label_to_function_omits_unimplemented_brackets():
    """(i)/(l) (ultrashort-pulse) and (k) (mpe_retinal_thermal_ira's
    ambiguous short-pulse bracket) are deliberately not implemented --
    see iec62471.py's module docstring and mpe_retinal_thermal_ira's own
    docstring. Their absence here must be deliberate, not an oversight
    this test would otherwise never catch."""
    table = eye_safety.iec62471.HAZARD_LABEL_TO_FUNCTION
    for letter in ('i', 'k', 'l'):
        assert letter not in table


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _run_all() -> int:
    tests = [
        test_alpha_min_values_differ_between_standards,
        test_clip_alpha_within_bounds_unchanged,
        test_clip_alpha_clamps_low,
        test_clip_alpha_clamps_high,
        test_clip_alpha_negative_raises,
        test_clip_alpha_bad_bounds_raises,
        test_alpha_from_axes_iec62471_worked_example,
        test_alpha_from_axes_henderson_line_laser_example,
        test_alpha_from_axes_clamps_each_axis_before_averaging,
        test_alpha_eff_iec62471_at_boundaries,
        test_alpha_eff_iec62471_monotonic_increasing,
        test_alpha_eff_iec62471_bad_duration_raises,
        test_t2_iec60825_1_at_alpha_min_is_10s,
        test_t2_iec60825_1_at_alpha_max_is_100s,
        test_t2_iec60825_1_below_alpha_min_clamps,
        test_t2_iec60825_1_monotonic_increasing,
        test_gamma_ph_iec60825_1_at_boundaries,
        test_gamma_ph_iec60825_1_below_10s_raises,
        test_gamma_ph_iec60825_1_non_positive_raises,
        test_gamma_th_iec60825_1_is_fixed_100_mrad,
        test_limiting_aperture_iec62471_bright_long_exposure_is_3mm,
        test_limiting_aperture_iec62471_dim_source_is_7mm,
        test_limiting_aperture_iec62471_short_exposure_is_7mm_regardless_of_luminance,
        test_limiting_aperture_iec62471_bad_inputs_raise,
        test_limiting_aperture_iec60825_1_uv_band,
        test_limiting_aperture_iec60825_1_retinal_band,
        test_limiting_aperture_iec60825_1_ir_band_duration_dependence,
        test_limiting_aperture_iec60825_1_far_ir_band,
        test_limiting_aperture_iec60825_1_out_of_domain_raises,
        test_limiting_aperture_iec60825_1_bad_tissue_raises,
        test_average_over_aperture_basic,
        test_average_over_aperture_off_center,
        test_average_over_aperture_mismatched_lengths_raises,
        test_average_over_aperture_bad_diameter_raises,
        test_average_over_aperture_empty_window_raises,
        test_limit_result_defaults,
        test_limit_result_as_power_w_passthrough,
        test_limit_result_as_power_w_from_joules,
        test_limit_result_as_power_w_per_area_unit_raises,
        test_interp_log_exact_sample_point,
        test_interp_log_geometric_mean_at_midpoint,
        test_interp_log_nonpositive_value_raises,
        test_interp_log_out_of_domain_raises,
        test_interp_log_bad_grid_raises,
        test_spd_bad_quantity_raises,
        test_spd_bad_grid_raises,
        test_spd_unit_property,
        test_spd_domain_nm,
        test_spd_value_at_linear_interp,
        test_spd_value_at_handles_zero_unlike_interp_log,
        test_spd_value_at_out_of_domain_raises,
        test_spd_integrate_flat_spectrum_flat_hazard,
        test_spd_integrate_matches_analytic_linear_ramp,
        test_spd_integrate_below_400nm_default_step_is_1nm_equivalent,
        test_spd_integrate_bad_step_raises,
        test_spd_integrate_against_interp_log_hazard_table,
        test_c4_below_700nm_is_one,
        test_c4_continuous_at_1050nm_boundary,
        test_c4_out_of_domain_raises,
        test_c7_below_1150nm_is_one,
        test_c7_continuous_at_1200nm_boundary,
        test_c7_out_of_domain_raises,
        test_c6_at_alpha_min_is_one,
        test_c6_at_alpha_max_is_66_67,
        test_c6_clamps_outside_bounds,
        test_c3_at_domain_edges,
        test_c3_out_of_domain_raises,
        test_mpe_retinal_thermal_ultrashort_raises_not_implemented,
        test_mpe_retinal_thermal_wavelength_out_of_range_raises,
        test_mpe_retinal_thermal_short_duration_units_are_radiant_exposure,
        test_mpe_retinal_thermal_long_duration_units_are_irradiance,
        test_mpe_retinal_thermal_at_alpha_max_matches_henderson_380,
        test_mpe_retinal_thermal_bad_duration_raises,
        test_mpe_retinal_photochemical_wavelength_out_of_range_raises,
        test_mpe_retinal_photochemical_below_10s_raises,
        test_mpe_retinal_photochemical_non_positive_duration_raises,
        test_mpe_retinal_photochemical_short_duration_is_radiant_exposure,
        test_mpe_retinal_photochemical_long_duration_is_irradiance,
        test_mpe_retinal_photochemical_continuous_at_100s_boundary,
        test_mpe_retinal_photochemical_wavelength_dependence_matches_c3,
        test_mpe_cornea_uv_domain_errors,
        test_mpe_cornea_uv_180_to_302_5_is_flat_30,
        test_mpe_cornea_uv_308nm_matches_henderson_worked_example,
        test_mpe_cornea_uv_355nm_matches_henderson_worked_example,
        test_mpe_cornea_uv_315_400_no_wavelength_dependence_below_10s,
        test_mpe_cornea_uv_302_5_to_315_crossover_continuity,
        test_mpe_skin_thermal_domain_errors,
        test_mpe_skin_thermal_short_pulse_bracket,
        test_mpe_skin_thermal_long_duration_is_constant_irradiance,
        test_mpe_skin_thermal_wavelength_dependence_matches_c4,
        test_mpe_skin_thermal_continuous_across_10s_boundary,
        test_ael_class_1_dispatches_to_uv_below_400nm,
        test_ael_class_1_uv_default_duration_matches_correct_time_base,
        test_ael_class_1_visible_default_duration_unaffected,
        test_ael_class_3r_uv_default_duration_matches_correct_time_base,
        test_classify_measurement_uv_default_no_longer_silently_wrong,
        test_ael_class_1_far_ir_not_implemented,
        test_ael_skin_visible_uses_skin_aperture,
        test_ael_skin_uv_matches_cornea_mpe_different_aperture,
        test_ael_skin_far_ir_not_implemented,
        test_ael_class_1_small_source_visible_matches_henderson_04mw,
        test_ael_class_1_photochemical_governs_in_blue_matches_henderson_004mw,
        test_ael_class_1_thermal_governs_above_500nm,
        test_ael_class_1_unaffected_outside_photochemical_wavelength_domain,
        test_ael_class_1_unaffected_at_short_duration_within_photochemical_wavelengths,
        test_ael_class_2_small_source_visible_matches_henderson_1mw,
        test_ael_class_2_out_of_visible_range_raises,
        test_ael_class_3r_visible_matches_henderson_5mw,
        test_hene_alignment_laser_case_study_4_8_1,
        test_low_level_therapy_laser_case_study_4_8_2,
        test_classify_measurement_negative_power_raises,
        test_classify_measurement_non_visible_skips_class_2,
        test_s_actinic_uv_peak_at_270nm,
        test_s_actinic_uv_known_checkpoints,
        test_s_actinic_uv_out_of_domain_raises,
        test_b_blue_light_flat_below_380nm,
        test_b_blue_light_peak_at_435_440nm,
        test_b_blue_light_continuous_at_500nm_and_600nm,
        test_b_blue_light_out_of_domain_raises,
        test_r_retinal_thermal_peak_at_435_440nm,
        test_r_retinal_thermal_is_ten_times_b_below_500nm,
        test_r_retinal_thermal_flat_500_to_700nm,
        test_r_retinal_thermal_continuous_at_1050_1150_1200nm,
        test_r_retinal_thermal_out_of_domain_raises,
        test_iec62471_mpe_actinic_uv_daily_value,
        test_iec62471_mpe_actinic_uv_out_of_domain_raises,
        test_iec62471_mpe_near_uv_daily_value,
        test_iec62471_mpe_blue_light_large_vs_small_source_dispatch,
        test_iec62471_mpe_blue_light_long_duration_constants,
        test_iec62471_mpe_blue_light_boundary_alpha_is_large_source,
        test_iec62471_mpe_retinal_thermal_long_duration,
        test_iec62471_mpe_retinal_thermal_continuous_at_10s_boundary,
        test_iec62471_mpe_retinal_thermal_ultrashort_raises,
        test_iec62471_mpe_retinal_thermal_ira_long_duration_only,
        test_iec62471_mpe_ir_eye_short_and_long_duration,
        test_iec62471_mpe_skin_thermal_domain,
        test_iec62471_no_namespace_collision_with_iec60825_1,
        test_retinal_thermal_classification_limit_exempt_equals_rg1,
        test_retinal_thermal_classification_limits_match_table_6_1,
        test_retinal_thermal_classification_limit_unknown_group_raises,
        test_retinal_thermal_classification_limit_public_matches_private_value,
        test_retinal_thermal_classification_limit_unit_always_w_m2_sr,
        test_risk_group_reference_duration_s_matches_internal_table,
        test_risk_group_reference_duration_s_unknown_raises_keyerror,
        test_risk_group_durations_no_longer_has_retinal_thermal_key,
        test_classify_measurement_retinal_thermal_only_uses_corrected_limits,
        test_classify_measurement_retinal_thermal_rg1_boundary,
        test_worked_example_d1_21_uva_blacklight_limits_match_guide,
        test_worked_example_d1_22_streetlight_limits_match_guide,
        test_classify_measurement_iec62471_deliberately_hazardous_case_is_rg3,
        test_angle_from_size_distance_matches_small_angle_approximation,
        test_angle_from_size_distance_bad_size_raises,
        test_angle_from_size_distance_bad_distance_raises,
        test_radiance_from_irradiance_reproduces_worked_example_d1_21,
        test_radiance_from_irradiance_reproduces_worked_example_d1_22,
        test_radiance_from_irradiance_bad_solid_angle_raises,
        test_irradiance_from_radiance_is_the_inverse,
        test_irradiance_from_radiance_bad_solid_angle_raises,
        test_hazard_label_to_function_covers_documented_letters,
        test_hazard_label_to_function_omits_unimplemented_brackets,
    ]
    failures = 0
    for test in tests:
        try:
            test()
            print(f"  PASS  {test.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL  {test.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  ERROR {test.__name__}: {exc!r}")

    if failures:
        print(f"\n{failures} test(s) failed.")
    else:
        print("\nAll eye-safety shared-scaffolding tests passed.")
    return failures


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
