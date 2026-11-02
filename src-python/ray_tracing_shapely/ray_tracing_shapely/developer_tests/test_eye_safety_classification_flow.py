"""
Python-specific module: test eye safety classification flow
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
EYE SAFETY CLASSIFICATION FLOW -- verification
===============================================================================
Covers the eye_safety_classification_flow package:
persistence.py (pure filesystem I/O, no transitions/graphviz dependency),
flow_base.py's ObservableFlow, and the two per-standard flows
(IEC62471ClassificationFlow, IEC60825_1ClassificationFlow).

FSM transition-logic tests use
`render_svg=False` (plain transitions.Machine, no Graphviz subprocess per
transition -- confirmed ~350x faster in this environment: 0.02s vs 7.6s
for one full run) and are unconditional; SVG-content tests are marked to
skip when `dot` cannot be found on PATH, so the suite stays green on a
machine without Graphviz installed.

Every physical value in a payload (every hazard's `value`,
`alpha_rad`, and IEC 60825-1's `measured_power_W`/`wavelength_nm`/
`duration_s_class1`) must be a `pint.Quantity` or a Pint-formatted string
-- **mandatory, not opt-in**. A bare `int`/`float` is rejected outright
(see `dimensional_checks.py`'s own module docstring for why an earlier,
opt-in version of this check defeated its own purpose). `validate_
dimensions` is each flow's own dedicated FSM state for this, immediately
after `frame_input` -- reaching it at all already means every dimension
was stated clearly, since a malformed payload never leaves `frame_input`.

Run with:
    python developer_tests/test_eye_safety_classification_flow.py

Or with pytest:
    pytest developer_tests/test_eye_safety_classification_flow.py -v
===============================================================================
"""

import math
import shutil
import sys
import tempfile
from pathlib import Path

src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from ray_tracing_shapely.optical_elements import eye_safety
from ray_tracing_shapely.optical_elements.eye_safety_classification_flow import (
    IEC62471ClassificationFlow,
    IEC60825_1ClassificationFlow,
    IEC62471_TERMINAL_STATES,
    IEC60825_1_TERMINAL_STATES,
    IEC62471IntakeFlow,
    IEC62471_INTAKE_TERMINAL_STATES,
    IEC60825_1IntakeFlow,
    IEC60825_1_INTAKE_TERMINAL_STATES,
    graphviz_available,
    make_run_id,
    run_dir,
    write_inputs,
    read_result,
    write_result,
    append_event,
    read_events,
    append_manifest,
    read_manifest,
    latest_manifest_rows,
    update_heartbeat,
    read_heartbeats,
    is_stale,
    expected_dimensionality_for_hazard,
    checked_hazard_value,
    checked_scalar,
    checked_radiance_from_irradiance,
    checked_irradiance_from_radiance,
    ComparisonExplanation,
    explain_comparison,
    FieldExplanation,
    explain_field,
    MarginSummary,
    summarize_margins,
)
from ray_tracing_shapely.optical_elements.eye_safety.result import LimitResult
from ray_tracing_shapely.optical_elements import ureg, IRRADIANCE, RADIANCE, POWER, ANGLE


def _assert_raises(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return
    except Exception as other:  # noqa: BLE001
        raise AssertionError(f"expected {exc_type.__name__}, got {other!r}")
    raise AssertionError(f"expected {exc_type.__name__}, nothing raised")


def _tmp_base() -> Path:
    return Path(tempfile.mkdtemp(prefix="eye_safety_flow_test_"))


Q = ureg.Quantity


# D.1.21's own numbers (the Directive 2006/25/EC guide), plain floats --
# used only for direct eye_safety.iec62471.classify_measurement comparisons,
# never passed to a flow (which now requires explicit units on everything).
_D1_21_ALPHA_RAD = 0.575
_D1_21_E_EFF = 30e-6
_D1_21_E_UVA = 176e-3
_D1_21_L_B = 55e-3
_D1_21_L_R = 255e-3

# The same data as a FRAME_INPUT payload -- every physical value stated
# with explicit units, as the mandatory-units rule requires.
_D1_21_PAYLOAD = {
    "alpha_rad": "0.575 rad",
    "hazards": {
        "actinic_uv": {"applicable": True, "value": "30e-6 W/m^2"},
        "near_uv": {"applicable": True, "value": "176e-3 W/m^2"},
        "blue_light": {"applicable": True, "value": "55e-3 W/(m^2*sr)"},
        "retinal_thermal": {"applicable": True, "value": "255e-3 W/(m^2*sr)"},
        "ir": {"applicable": False, "value": None},
    },
}


# ---------------------------------------------------------------------------
# persistence.py -- pure I/O, no transitions/graphviz dependency
# ---------------------------------------------------------------------------

def test_make_run_id_includes_standard_and_pid():
    run_id = make_run_id("iec62471")
    assert run_id.startswith("iec62471-")
    parts = run_id.split("-")
    assert len(parts) == 3
    assert parts[1].isdigit()
    assert parts[2].isdigit()


def test_run_dir_creates_directory():
    base = _tmp_base()
    d = run_dir(base, "some-run")
    assert d.exists() and d.is_dir()
    assert d == base / "some-run"


def test_write_inputs_and_read_result_roundtrip():
    base = _tmp_base()
    write_inputs(base, "run-1", {"a": 1})
    assert (run_dir(base, "run-1") / "inputs.json").exists()
    assert read_result(base, "run-1") is None  # not written yet
    write_result(base, "run-1", {"result": "Exempt", "wall_clock_s": 1.5})
    result = read_result(base, "run-1")
    assert result["result"] == "Exempt"


def test_append_event_assigns_sequential_seq():
    base = _tmp_base()
    seq0 = append_event(base, "run-1", {"message": "first"})
    seq1 = append_event(base, "run-1", {"message": "second"})
    assert seq0 == 0 and seq1 == 1
    events = read_events(base, "run-1")
    assert [e["message"] for e in events] == ["first", "second"]
    assert [e["seq"] for e in events] == [0, 1]
    assert all("timestamp" in e for e in events)


def test_read_events_empty_for_unknown_run():
    base = _tmp_base()
    assert read_events(base, "nope") == []


def test_append_manifest_and_latest_manifest_rows():
    base = _tmp_base()
    append_manifest(base, "run-1", standard="iec62471", started_at=100.0)
    append_manifest(base, "run-1", standard="iec62471", started_at=100.0,
                     finished_at=105.0, result="Exempt")
    append_manifest(base, "run-2", standard="iec60825_1", started_at=200.0)
    rows = read_manifest(base)
    assert len(rows) == 3  # every append, not deduplicated
    latest = latest_manifest_rows(base)
    assert len(latest) == 2  # one per run_id
    by_id = {r["run_id"]: r for r in latest}
    assert by_id["run-1"]["result"] == "Exempt"
    assert by_id["run-1"]["finished_at"] == 105.0
    assert by_id["run-2"]["finished_at"] is None
    # most-recently-started first
    assert latest[0]["run_id"] == "run-2"


def test_update_heartbeat_upserts_single_row_per_run():
    base = _tmp_base()
    update_heartbeat(base, "run-1", fsm_name="iec62471", state="frame_input")
    update_heartbeat(base, "run-1", fsm_name="iec62471", state="done",
                      detail={"x": 1})
    heartbeats = read_heartbeats(base)
    assert len(heartbeats) == 1
    row = heartbeats["run-1"]
    assert row["state"] == "done"
    assert row["detail"] == {"x": 1}
    assert row["started_at"] <= row["updated_at"]


def test_is_stale_true_for_old_nonterminal_state():
    row = {"state": "frame_input", "updated_at": 0.0}  # 1970 -- ancient
    assert is_stale(row, terminal_states=("done",))


def test_is_stale_false_for_terminal_state_regardless_of_age():
    row = {"state": "done", "updated_at": 0.0}
    assert not is_stale(row, terminal_states=("done",))


def test_is_stale_false_for_fresh_heartbeat():
    import time
    row = {"state": "frame_input", "updated_at": time.time()}
    assert not is_stale(row, terminal_states=("done",))


# ---------------------------------------------------------------------------
# IEC 62471 flow
# ---------------------------------------------------------------------------

def test_iec62471_flow_full_state_sequence():
    """Each hazard gets three atomic per-risk-group states, not one
    bundled state -- 15 eval_* states, not 5."""
    base = _tmp_base()
    flow = IEC62471ClassificationFlow(base_dir=base, render_svg=False)
    flow.submit_input(_D1_21_PAYLOAD)
    states = [e["state"] for e in read_events(base, flow.run_id)]
    assert states == [
        "validate_dimensions",
        "eval_actinic_uv_exempt", "eval_actinic_uv_rg1", "eval_actinic_uv_rg2",
        "eval_near_uv_exempt", "eval_near_uv_rg1", "eval_near_uv_rg2",
        "eval_blue_light_exempt", "eval_blue_light_rg1", "eval_blue_light_rg2",
        "eval_retinal_thermal_exempt", "eval_retinal_thermal_rg1", "eval_retinal_thermal_rg2",
        "eval_ir_exempt", "eval_ir_rg1", "eval_ir_rg2",
        "determine_risk_group", "summarize_margins", "done",
    ]
    assert flow.state in IEC62471_TERMINAL_STATES


def test_iec62471_flow_skipped_hazard_recorded_as_inapplicable():
    base = _tmp_base()
    flow = IEC62471ClassificationFlow(base_dir=base, render_svg=False)
    flow.submit_input(_D1_21_PAYLOAD)
    events = {e["hazard"]: e for e in read_events(base, flow.run_id) if "hazard" in e}
    assert events["ir"]["applicable"] is False
    assert events["ir"]["value"] is None
    assert events["actinic_uv"]["applicable"] is True


def test_iec62471_flow_parity_with_classify_measurement_directly():
    """C-EYE-05: the FSM's terminal result must exactly match calling
    classify_measurement directly with the same inputs."""
    base = _tmp_base()
    flow = IEC62471ClassificationFlow(base_dir=base, render_svg=False)
    flow.submit_input(_D1_21_PAYLOAD)
    direct = eye_safety.iec62471.classify_measurement(
        _D1_21_ALPHA_RAD,
        e_eff_w_m2=_D1_21_E_EFF, e_uva_w_m2=_D1_21_E_UVA, blue_light_value=_D1_21_L_B,
        l_r_w_m2_sr=_D1_21_L_R, e_ir_w_m2=None,
    )
    assert flow.result == direct == "Exempt"


def test_iec62471_flow_parity_hazardous_case_is_rg3():
    base = _tmp_base()
    payload = {
        "alpha_rad": "0.001 rad",
        "hazards": {
            "actinic_uv": {"applicable": False, "value": None},
            "near_uv": {"applicable": False, "value": None},
            "blue_light": {"applicable": True, "value": "500.0 W/m^2"},
            "retinal_thermal": {"applicable": False, "value": None},
            "ir": {"applicable": False, "value": None},
        },
    }
    flow = IEC62471ClassificationFlow(base_dir=base, render_svg=False)
    flow.submit_input(payload)
    direct = eye_safety.iec62471.classify_measurement(0.001, blue_light_value=500.0)
    assert flow.result == direct == "RG3"


def test_iec62471_flow_writes_inputs_result_and_manifest():
    base = _tmp_base()
    flow = IEC62471ClassificationFlow(base_dir=base, render_svg=False)
    flow.submit_input(_D1_21_PAYLOAD)
    assert (run_dir(base, flow.run_id) / "inputs.json").exists()
    result = read_result(base, flow.run_id)
    assert result["result"] == "Exempt"
    latest = {r["run_id"]: r for r in latest_manifest_rows(base)}
    assert latest[flow.run_id]["result"] == "Exempt"
    assert latest[flow.run_id]["finished_at"] is not None


def test_iec62471_frame_input_rejects_missing_alpha():
    base = _tmp_base()
    flow = IEC62471ClassificationFlow(base_dir=base, render_svg=False)
    bad = {"hazards": _D1_21_PAYLOAD["hazards"]}
    _assert_raises(ValueError, flow.submit_input, bad)
    assert flow.state == "frame_input"


def test_iec62471_frame_input_rejects_negative_alpha():
    base = _tmp_base()
    flow = IEC62471ClassificationFlow(base_dir=base, render_svg=False)
    bad = dict(_D1_21_PAYLOAD, alpha_rad="-0.1 rad")
    _assert_raises(ValueError, flow.submit_input, bad)
    assert flow.state == "frame_input"


def test_iec62471_frame_input_rejects_bare_float_alpha():
    """The core mandatory-units rule: a bare number, even a valid-looking one, is
    rejected -- units must be stated, not assumed."""
    base = _tmp_base()
    flow = IEC62471ClassificationFlow(base_dir=base, render_svg=False)
    bad = dict(_D1_21_PAYLOAD, alpha_rad=0.575)
    _assert_raises(ValueError, flow.submit_input, bad)
    assert flow.state == "frame_input"


def test_iec62471_frame_input_rejects_missing_hazards_dict():
    base = _tmp_base()
    flow = IEC62471ClassificationFlow(base_dir=base, render_svg=False)
    _assert_raises(ValueError, flow.submit_input, {"alpha_rad": "0.1 rad"})
    assert flow.state == "frame_input"


def test_iec62471_frame_input_rejects_missing_hazard_key():
    base = _tmp_base()
    flow = IEC62471ClassificationFlow(base_dir=base, render_svg=False)
    hazards = dict(_D1_21_PAYLOAD["hazards"])
    del hazards["ir"]
    bad = dict(_D1_21_PAYLOAD, hazards=hazards)
    _assert_raises(ValueError, flow.submit_input, bad)


def test_iec62471_frame_input_rejects_applicable_without_value():
    base = _tmp_base()
    flow = IEC62471ClassificationFlow(base_dir=base, render_svg=False)
    hazards = dict(_D1_21_PAYLOAD["hazards"])
    hazards["ir"] = {"applicable": True, "value": None}
    bad = dict(_D1_21_PAYLOAD, hazards=hazards)
    _assert_raises(ValueError, flow.submit_input, bad)


def test_iec62471_frame_input_rejects_applicable_with_bare_float_value():
    base = _tmp_base()
    flow = IEC62471ClassificationFlow(base_dir=base, render_svg=False)
    hazards = dict(_D1_21_PAYLOAD["hazards"])
    hazards["ir"] = {"applicable": True, "value": 1.0}  # bare float -- no units stated
    bad = dict(_D1_21_PAYLOAD, hazards=hazards)
    _assert_raises(ValueError, flow.submit_input, bad)


def test_iec62471_frame_input_rejects_inapplicable_with_value():
    base = _tmp_base()
    flow = IEC62471ClassificationFlow(base_dir=base, render_svg=False)
    hazards = dict(_D1_21_PAYLOAD["hazards"])
    hazards["ir"] = {"applicable": False, "value": "1.0 W/m^2"}
    bad = dict(_D1_21_PAYLOAD, hazards=hazards)
    _assert_raises(ValueError, flow.submit_input, bad)


def test_iec62471_frame_input_valid_payload_advances_and_recovers():
    """After a rejected payload, the same flow instance can still accept
    a valid one -- a failed FRAME_INPUT attempt must not corrupt state."""
    base = _tmp_base()
    flow = IEC62471ClassificationFlow(base_dir=base, render_svg=False)
    _assert_raises(ValueError, flow.submit_input, {"alpha_rad": -1.0})
    flow.submit_input(_D1_21_PAYLOAD)
    assert flow.result == "Exempt"


# ---------------------------------------------------------------------------
# IEC 60825-1 flow
# ---------------------------------------------------------------------------

_HENE_PAYLOAD = {"measured_power_W": "0.0004 W", "wavelength_nm": "632.8 nm"}
_NON_VISIBLE_PAYLOAD = {"measured_power_W": "1e-6 W", "wavelength_nm": "905.0 nm"}


def test_iec60825_1_flow_full_state_sequence_visible_wavelength():
    base = _tmp_base()
    flow = IEC60825_1ClassificationFlow(base_dir=base, render_svg=False)
    flow.submit_input(_HENE_PAYLOAD)
    states = [e["state"] for e in read_events(base, flow.run_id)]
    assert states == [
        "validate_dimensions", "eval_class_1", "eval_class_2", "eval_class_3r", "summarize_margins", "done",
    ]
    assert flow.state in IEC60825_1_TERMINAL_STATES


def test_iec60825_1_flow_class_2_skipped_for_non_visible_wavelength():
    """The concrete 'skipped state': ael_class_2 raises for wavelengths
    outside [400, 700) nm -- the flow must not let that propagate, it
    records a skip event instead."""
    base = _tmp_base()
    flow = IEC60825_1ClassificationFlow(base_dir=base, render_svg=False)
    flow.submit_input(_NON_VISIBLE_PAYLOAD)
    events = read_events(base, flow.run_id)
    class_2_event = next(e for e in events if e.get("ael_class") == "class_2_2m")
    assert class_2_event["result"] is None
    assert "skipped" in class_2_event["message"]


def test_iec60825_1_flow_parity_with_classify_measurement_directly():
    """C-EYE-05, IEC 60825-1 side."""
    base = _tmp_base()
    flow = IEC60825_1ClassificationFlow(base_dir=base, render_svg=False)
    flow.submit_input(_HENE_PAYLOAD)
    direct = eye_safety.iec60825_1.classify_measurement(0.0004, 632.8)
    assert flow.result == direct


def test_iec60825_1_flow_parity_non_visible_wavelength():
    base = _tmp_base()
    flow = IEC60825_1ClassificationFlow(base_dir=base, render_svg=False)
    flow.submit_input(_NON_VISIBLE_PAYLOAD)
    direct = eye_safety.iec60825_1.classify_measurement(1e-6, 905.0)
    assert flow.result == direct


def test_iec60825_1_flow_default_alpha_and_duration_applied():
    """FRAME_INPUT fills in classify_measurement's own defaults
    (ALPHA_MIN_IEC60825_1_RAD, duration_s_class1=None) rather than
    requiring a caller to know them -- 'omitted' (not given at all) is
    still fine under the mandatory-units rule; only a *stated*
    value must carry units."""
    base = _tmp_base()
    flow = IEC60825_1ClassificationFlow(base_dir=base, render_svg=False)
    flow.submit_input(_HENE_PAYLOAD)
    assert flow.payload["alpha_rad"] == eye_safety.ALPHA_MIN_IEC60825_1_RAD
    assert flow.payload["duration_s_class1"] is None


def test_iec60825_1_frame_input_rejects_missing_power():
    base = _tmp_base()
    flow = IEC60825_1ClassificationFlow(base_dir=base, render_svg=False)
    _assert_raises(ValueError, flow.submit_input, {"wavelength_nm": "632.8 nm"})
    assert flow.state == "frame_input"


def test_iec60825_1_frame_input_rejects_negative_power():
    base = _tmp_base()
    flow = IEC60825_1ClassificationFlow(base_dir=base, render_svg=False)
    bad = {"measured_power_W": "-1.0 W", "wavelength_nm": "632.8 nm"}
    _assert_raises(ValueError, flow.submit_input, bad)


def test_iec60825_1_frame_input_rejects_missing_wavelength():
    base = _tmp_base()
    flow = IEC60825_1ClassificationFlow(base_dir=base, render_svg=False)
    _assert_raises(ValueError, flow.submit_input, {"measured_power_W": "1e-3 W"})


def test_iec60825_1_frame_input_rejects_bare_float_power():
    base = _tmp_base()
    flow = IEC60825_1ClassificationFlow(base_dir=base, render_svg=False)
    bad = {"measured_power_W": 0.0004, "wavelength_nm": "632.8 nm"}
    _assert_raises(ValueError, flow.submit_input, bad)
    assert flow.state == "frame_input"


def test_iec60825_1_frame_input_rejects_bare_float_wavelength():
    base = _tmp_base()
    flow = IEC60825_1ClassificationFlow(base_dir=base, render_svg=False)
    bad = {"measured_power_W": "0.0004 W", "wavelength_nm": 632.8}
    _assert_raises(ValueError, flow.submit_input, bad)
    assert flow.state == "frame_input"


def test_iec60825_1_frame_input_rejects_bare_float_alpha_when_given():
    base = _tmp_base()
    flow = IEC60825_1ClassificationFlow(base_dir=base, render_svg=False)
    bad = dict(_HENE_PAYLOAD, alpha_rad=0.0015)
    _assert_raises(ValueError, flow.submit_input, bad)
    assert flow.state == "frame_input"


def test_iec60825_1_frame_input_accepts_explicit_alpha_and_duration():
    base = _tmp_base()
    flow = IEC60825_1ClassificationFlow(base_dir=base, render_svg=False)
    flow.submit_input(dict(_HENE_PAYLOAD, alpha_rad="1.5 mrad", duration_s_class1="100 s"))
    assert math.isclose(flow.payload["alpha_rad"], 1.5e-3)
    assert math.isclose(flow.payload["duration_s_class1"], 100.0)


# ---------------------------------------------------------------------------
# Dimensional consistency checks at FRAME_INPUT [KA9]
# ---------------------------------------------------------------------------

def test_expected_dimensionality_fixed_hazards():
    assert expected_dimensionality_for_hazard("actinic_uv", 0.5) == IRRADIANCE
    assert expected_dimensionality_for_hazard("near_uv", 0.001) == IRRADIANCE
    assert expected_dimensionality_for_hazard("ir", 0.5) == IRRADIANCE
    assert expected_dimensionality_for_hazard("retinal_thermal", 0.001) == RADIANCE
    assert expected_dimensionality_for_hazard("retinal_thermal", 0.5) == RADIANCE


def test_expected_dimensionality_blue_light_depends_on_alpha():
    assert expected_dimensionality_for_hazard("blue_light", 0.5) == RADIANCE       # large source
    assert expected_dimensionality_for_hazard("blue_light", 0.001) == IRRADIANCE   # small source
    # exactly at the boundary (11 mrad): large-source, matching mpe_blue_light's own >= dispatch
    assert expected_dimensionality_for_hazard("blue_light", 0.011) == RADIANCE


def test_expected_dimensionality_unknown_hazard_raises():
    _assert_raises(ValueError, expected_dimensionality_for_hazard, "nope", 0.5)


def test_checked_hazard_value_rejects_bare_float():
    """The core rule: a bare number is never trusted, even a
    correctly-valued one."""
    _assert_raises(ValueError, checked_hazard_value, "actinic_uv", 30e-6, 0.5, name="x")


def test_checked_hazard_value_rejects_bare_int():
    _assert_raises(ValueError, checked_hazard_value, "actinic_uv", 0, 0.5, name="x")


def test_checked_hazard_value_rejects_bool():
    """bool is an int subclass in Python -- must not slip through as 0/1."""
    _assert_raises(ValueError, checked_hazard_value, "actinic_uv", True, 0.5, name="x")


def test_checked_hazard_value_accepts_quantity_correct_family():
    v = checked_hazard_value("blue_light", Q(55, "mW/(m^2*sr)"), 0.5, name="x")
    assert math.isclose(v, 0.055)


def test_checked_hazard_value_accepts_string():
    v = checked_hazard_value("near_uv", "176 mW/m^2", 0.5, name="x")
    assert math.isclose(v, 0.176)


def test_checked_hazard_value_rejects_wrong_radiometric_family():
    """The core motivating case: an irradiance where blue_light's
    large-source dispatch expects a radiance."""
    _assert_raises(
        ValueError, checked_hazard_value, "blue_light", Q(55, "mW/m^2"), 0.5, name="x",
    )


def test_checked_hazard_value_rejects_dose_where_rate_expected():
    _assert_raises(
        ValueError, checked_hazard_value, "actinic_uv", Q(30, "uJ/m^2"), 0.5, name="x",
    )


def test_checked_scalar_rejects_bare_float():
    _assert_raises(ValueError, checked_scalar, 0.4, POWER, name="p")


def test_checked_scalar_rejects_bool():
    _assert_raises(ValueError, checked_scalar, False, POWER, name="p")


def test_checked_scalar_accepts_quantity_and_converts():
    assert math.isclose(checked_scalar(Q(0.4, "mW"), POWER, name="p"), 0.4e-3)


def test_checked_scalar_accepts_string():
    assert math.isclose(checked_scalar("0.4 mW", POWER, name="p"), 0.4e-3)


def test_checked_scalar_rejects_wrong_dimensionality():
    _assert_raises(ValueError, checked_scalar, Q(0.4, "mJ"), POWER, name="p")


def test_checked_scalar_angle_converts_degrees():
    """ANGLE's check can't distinguish rad from a bare number or sr (Pint
    treats radian as dimensionless) -- but it still gives free unit
    conversion, e.g. deg -> rad."""
    v = checked_scalar("90 deg", ANGLE, name="alpha_rad")
    assert math.isclose(v, math.pi / 2)


def test_checked_radiance_from_irradiance_matches_worked_example():
    """Reproduces D.1.21's own E->L conversion via the checked wrapper."""
    result = checked_radiance_from_irradiance(Q(3, "mW/m^2"), Q(0.055, "sr"))
    assert math.isclose(result.to("mW/(m^2*sr)").magnitude, 54.545, rel_tol=1e-3)
    assert result.check(RADIANCE)


def test_checked_radiance_from_irradiance_accepts_strings():
    result = checked_radiance_from_irradiance("3 mW/m^2", "0.055 sr")
    assert math.isclose(result.to("mW/(m^2*sr)").magnitude, 54.545, rel_tol=1e-3)


def test_checked_radiance_from_irradiance_rejects_dose_as_irradiance():
    _assert_raises(ValueError, checked_radiance_from_irradiance, Q(3, "mJ/m^2"), Q(0.055, "sr"))


def test_checked_radiance_from_irradiance_rejects_radiance_as_irradiance():
    """Feeding an already-radiance value into the 'irradiance' slot must
    be caught -- exactly the swapped-argument mistake a plain float
    signature could never catch."""
    _assert_raises(
        ValueError, checked_radiance_from_irradiance, Q(3, "mW/(m^2*sr)"), Q(0.055, "sr"),
    )


def test_checked_radiance_from_irradiance_rejects_length_as_solid_angle():
    _assert_raises(ValueError, checked_radiance_from_irradiance, Q(3, "mW/m^2"), Q(0.055, "m"))


def test_checked_irradiance_from_radiance_is_the_inverse():
    l = checked_radiance_from_irradiance(Q(3, "mW/m^2"), Q(0.055, "sr"))
    e = checked_irradiance_from_radiance(l, Q(0.055, "sr"))
    assert math.isclose(e.to("mW/m^2").magnitude, 3.0, rel_tol=1e-9)
    assert e.check(IRRADIANCE)


def test_iec62471_frame_input_quantity_and_string_payloads_match():
    """The same D.1.21 data, once built from pint.Quantity objects and
    once from Pint-formatted strings, must produce identical results --
    both are valid ways to state units explicitly."""
    base = _tmp_base()
    flow_quantity = IEC62471ClassificationFlow(base_dir=base, render_svg=False)
    flow_quantity.submit_input({
        "alpha_rad": Q(0.575, "rad"),
        "hazards": {
            "actinic_uv": {"applicable": True, "value": Q(30, "uW/m^2")},
            "near_uv": {"applicable": True, "value": Q(176, "mW/m^2")},
            "blue_light": {"applicable": True, "value": Q(55, "mW/(m^2*sr)")},
            "retinal_thermal": {"applicable": True, "value": Q(255, "mW/(m^2*sr)")},
            "ir": {"applicable": False, "value": None},
        },
    })

    flow_string = IEC62471ClassificationFlow(base_dir=base, render_svg=False)
    flow_string.submit_input(_D1_21_PAYLOAD)

    assert flow_quantity.result == flow_string.result == "Exempt"


def test_iec62471_frame_input_rejects_irradiance_where_radiance_expected():
    """The end-to-end version of the motivating case: a large source
    (alpha well above 11 mrad) given an irradiance for blue_light, where
    mpe_blue_light's own dispatch expects a radiance. Must be rejected
    before the FSM leaves frame_input."""
    base = _tmp_base()
    flow = IEC62471ClassificationFlow(base_dir=base, render_svg=False)
    bad = {
        "alpha_rad": "0.575 rad",
        "hazards": {
            "actinic_uv": {"applicable": False, "value": None},
            "near_uv": {"applicable": False, "value": None},
            "blue_light": {"applicable": True, "value": Q(55, "mW/m^2")},  # wrong: irradiance, not radiance
            "retinal_thermal": {"applicable": False, "value": None},
            "ir": {"applicable": False, "value": None},
        },
    }
    _assert_raises(ValueError, flow.submit_input, bad)
    assert flow.state == "frame_input"


def test_iec60825_1_frame_input_accepts_quantity_payload():
    base = _tmp_base()
    flow = IEC60825_1ClassificationFlow(base_dir=base, render_svg=False)
    flow.submit_input({
        "measured_power_W": Q(0.4, "mW"),
        "wavelength_nm": Q(632.8, "nm"),
    })
    direct = eye_safety.iec60825_1.classify_measurement(0.4e-3, 632.8)
    assert flow.result == direct


def test_iec60825_1_frame_input_rejects_dose_as_power():
    base = _tmp_base()
    flow = IEC60825_1ClassificationFlow(base_dir=base, render_svg=False)
    bad = {"measured_power_W": Q(0.4, "mJ"), "wavelength_nm": "632.8 nm"}
    _assert_raises(ValueError, flow.submit_input, bad)
    assert flow.state == "frame_input"


# ---------------------------------------------------------------------------
# Comparison explanations [KD4]
# ---------------------------------------------------------------------------

_SAMPLE_LIMIT = LimitResult(
    value=10.0, unit="W/m^2", wavelength_nm=0.0, duration_s=1.0, alpha_rad=0.0,
    region="x", time_regime="t", equation="Eq. 1", factors={}, notes="",
)


def test_explain_comparison_pass():
    exp = explain_comparison(5.0, "W/m^2", _SAMPLE_LIMIT)
    assert isinstance(exp, ComparisonExplanation)
    assert exp.verdict is True
    assert "pass" in exp.message and "FAIL" not in exp.message


def test_explain_comparison_fail():
    exp = explain_comparison(50.0, "W/m^2", _SAMPLE_LIMIT)
    assert exp.verdict is False
    assert "FAIL" in exp.message


def test_explain_comparison_rejects_other_comparator():
    _assert_raises(ValueError, explain_comparison, 5.0, "W/m^2", _SAMPLE_LIMIT, comparator=">=")


def test_explain_field_message_contains_all_parts():
    exp = explain_field("alpha_rad", "What is alpha_rad?", "citation X", 'e.g. "1 rad"')
    assert isinstance(exp, FieldExplanation)
    assert "What is alpha_rad?" in exp.message
    assert "citation X" in exp.message
    assert 'e.g. "1 rad"' in exp.message


def test_iec62471_eval_states_emit_comparison_field():
    base = _tmp_base()
    flow = IEC62471ClassificationFlow(base_dir=base, render_svg=False)
    flow.submit_input(_D1_21_PAYLOAD)
    events = {(e["hazard"], e["group"]): e for e in read_events(base, flow.run_id) if "hazard" in e}
    e = events[("actinic_uv", "Exempt")]
    assert e["comparison"]["verdict"] is True
    assert e["result"]["region"] == "actinic_uv"
    # inapplicable hazard: no comparison recorded, all three groups
    for group in ("Exempt", "RG1", "RG2"):
        assert "comparison" not in events[("ir", group)]


def test_iec62471_comparison_verdicts_match_classify_measurement_decision():
    """C-EYE-05 extension: every ComparisonExplanation.verdict
    recorded along the way must agree with what classify_measurement's own
    ascending-severity loop actually decided for that hazard/group -- if
    they ever disagreed, that would itself be a C-EYE-05-class regression."""
    order = ["Exempt", "RG1", "RG2"]

    def _check(base_payload):
        base = _tmp_base()
        flow = IEC62471ClassificationFlow(base_dir=base, render_svg=False)
        flow.submit_input(base_payload)
        by_group = {"Exempt": [], "RG1": [], "RG2": []}
        for e in read_events(base, flow.run_id):
            if "comparison" in e:
                by_group[e["group"]].append(e["comparison"]["verdict"])
        won_index = order.index(flow.result) if flow.result in order else len(order)
        for i, group in enumerate(order):
            verdicts = by_group[group]
            if i < won_index:
                assert not all(verdicts), f"{group} should have a failing comparison (result={flow.result})"
            elif i == won_index:
                assert all(verdicts), f"{group} was the winning group but has a failing comparison"

    _check(_D1_21_PAYLOAD)  # Exempt
    _check({  # RG3 -- every group must show at least one failure
        "alpha_rad": "0.001 rad",
        "hazards": {
            "actinic_uv": {"applicable": False, "value": None},
            "near_uv": {"applicable": False, "value": None},
            "blue_light": {"applicable": True, "value": "500.0 W/m^2"},
            "retinal_thermal": {"applicable": False, "value": None},
            "ir": {"applicable": False, "value": None},
        },
    })


def test_iec62471_explain_current_state_matches_last_event_message():
    """summarize_margins runs last, after every ComparisonExplanation
    -- explain_current_state() reflects its MarginSummary, the true last
    explanation set for a completed run."""
    base = _tmp_base()
    flow = IEC62471ClassificationFlow(base_dir=base, render_svg=False)
    flow.submit_input(_D1_21_PAYLOAD)
    events = read_events(base, flow.run_id)
    last_summary_event = next(e for e in reversed(events) if e["state"] == "summarize_margins")
    assert flow.explain_current_state() == last_summary_event["message"]


def test_iec60825_1_eval_states_emit_comparison_field():
    base = _tmp_base()
    flow = IEC60825_1ClassificationFlow(base_dir=base, render_svg=False)
    flow.submit_input(_HENE_PAYLOAD)
    events = {e["ael_class"]: e for e in read_events(base, flow.run_id) if "ael_class" in e}
    assert "comparison" in events["class_1_1m"]
    assert events["class_1_1m"]["comparison"]["verdict"] is False  # HeNe exceeds Class 1/1M
    assert events["class_2_2m"]["comparison"]["verdict"] is True


def test_iec60825_1_explain_current_state_matches_last_event_message():
    base = _tmp_base()
    flow = IEC60825_1ClassificationFlow(base_dir=base, render_svg=False)
    flow.submit_input(_HENE_PAYLOAD)
    events = read_events(base, flow.run_id)
    last_summary_event = next(e for e in reversed(events) if e["state"] == "summarize_margins")
    assert flow.explain_current_state() == last_summary_event["message"]


# ---------------------------------------------------------------------------
# Margin/headroom calculation
# ---------------------------------------------------------------------------

def test_margin_ratio_pass_below_one():
    exp = explain_comparison(5.0, "W/m^2", _SAMPLE_LIMIT)  # threshold 10.0
    assert math.isclose(exp.margin_ratio, 0.5)
    assert "50.0% headroom" in exp.message


def test_margin_ratio_fail_above_one():
    exp = explain_comparison(15.0, "W/m^2", _SAMPLE_LIMIT)  # threshold 10.0
    assert math.isclose(exp.margin_ratio, 1.5)
    assert "exceeds by 50.0%" in exp.message


def test_summarize_margins_picks_highest_ratio():
    summary = summarize_margins("Exempt", {"a": 0.2, "b": 0.9, "c": 0.5})
    assert summary.tightest_criterion == "b"
    assert math.isclose(summary.tightest_margin_ratio, 0.9)
    assert "b" in summary.message and "10.0% headroom" in summary.message


def test_summarize_margins_single_criterion_message_shape():
    summary = summarize_margins("Class 2 or 2M", {"class_2_2m": 0.4})
    assert summary.message == "Class 2 or 2M: class_2_2m at 40.0% of its limit (60.0% headroom)"


def test_summarize_margins_over_limit():
    summary = summarize_margins("RG2", {"blue_light": 1.25})
    assert "exceeds its limit by 25.0%" in summary.message


def test_summarize_margins_empty():
    summary = summarize_margins("Exempt", {})
    assert summary.tightest_criterion is None
    assert summary.tightest_margin_ratio is None
    assert "no applicable criteria" in summary.message


def test_iec62471_summarize_margins_state_reports_tightest_in_winning_group():
    """Worked example D.1.21: every applicable hazard passes Exempt, so the
    summary is scoped to Exempt and names whichever one came closest."""
    base = _tmp_base()
    flow = IEC62471ClassificationFlow(base_dir=base, render_svg=False)
    flow.submit_input(_D1_21_PAYLOAD)
    assert flow.result == "Exempt"
    events = read_events(base, flow.run_id)
    summary_event = next(e for e in events if e["state"] == "summarize_margins")
    assert summary_event["winning_group"] == "Exempt"
    assert summary_event["tightest_criterion"] in summary_event["margins_by_group"]["Exempt"]
    # the reported tightest ratio really is the max among Exempt's own applicable hazards
    exempt_margins = summary_event["margins_by_group"]["Exempt"]
    assert math.isclose(
        summary_event["tightest_margin_ratio"], max(exempt_margins.values()),
    )
    # every hazard checked in the winning group must have actually passed
    assert all(v <= 1.0 for v in exempt_margins.values())


def test_iec62471_summarize_margins_state_rg3_falls_back_to_rg2():
    base = _tmp_base()
    flow = IEC62471ClassificationFlow(base_dir=base, render_svg=False)
    flow.submit_input({
        "alpha_rad": "0.001 rad",
        "hazards": {
            "actinic_uv": {"applicable": False, "value": None},
            "near_uv": {"applicable": False, "value": None},
            "blue_light": {"applicable": True, "value": "500.0 W/m^2"},
            "retinal_thermal": {"applicable": False, "value": None},
            "ir": {"applicable": False, "value": None},
        },
    })
    assert flow.result == "RG3"
    events = read_events(base, flow.run_id)
    summary_event = next(e for e in events if e["state"] == "summarize_margins")
    assert summary_event["winning_group"] == "RG2"
    assert summary_event["tightest_criterion"] == "blue_light"
    assert summary_event["tightest_margin_ratio"] > 1.0  # genuinely failing


def test_iec60825_1_summarize_margins_state_reports_winning_class_only():
    """The HeNe example fails Class 1/1M (margin > 1) but passes Class
    2/2M -- the summary must report Class 2/2M's own margin, not the
    numerically larger (but not-actually-relevant) Class 1/1M one."""
    base = _tmp_base()
    flow = IEC60825_1ClassificationFlow(base_dir=base, render_svg=False)
    flow.submit_input(_HENE_PAYLOAD)
    assert flow.result == "Class 2 or 2M"
    events = read_events(base, flow.run_id)
    summary_event = next(e for e in events if e["state"] == "summarize_margins")
    assert summary_event["winning_ael_class"] == "class_2_2m"
    assert summary_event["tightest_criterion"] == "class_2_2m"
    assert summary_event["margins_by_class"]["class_1_1m"] > 1.0  # failed, but not the winner
    assert summary_event["tightest_margin_ratio"] < 1.0


def test_iec60825_1_summarize_margins_state_above_class_3r_uses_class_3r_margin():
    base = _tmp_base()
    flow = IEC60825_1ClassificationFlow(base_dir=base, render_svg=False)
    flow.submit_input({"measured_power_W": Q(1.0, "W"), "wavelength_nm": Q(632.8, "nm")})
    assert flow.result == "above Class 3R (3B or 4)"
    events = read_events(base, flow.run_id)
    summary_event = next(e for e in events if e["state"] == "summarize_margins")
    assert summary_event["winning_ael_class"] == "class_3r"
    assert summary_event["tightest_margin_ratio"] > 1.0


# ---------------------------------------------------------------------------
# Global reset
# ---------------------------------------------------------------------------

def test_iec62471_flow_reset_from_done_returns_to_start():
    base = _tmp_base()
    flow = IEC62471ClassificationFlow(base_dir=base, render_svg=False)
    flow.submit_input(_D1_21_PAYLOAD)
    assert flow.state == "done"
    flow.reset()
    assert flow.state == "start"
    assert flow.attempt == 2
    flow.begin()
    flow.submit_input(_D1_21_PAYLOAD)
    assert flow.result == "Exempt"
    assert any(e.get("attempt") == 2 for e in read_events(base, flow.run_id))


def test_iec60825_1_flow_reset_from_mid_flow():
    base = _tmp_base()
    flow = IEC60825_1ClassificationFlow(base_dir=base, render_svg=False)
    assert flow.state == "frame_input"
    flow.reset()
    assert flow.state == "start"
    assert flow.attempt == 2


def test_reset_works_from_any_state_wildcard_source():
    """Confirms transitions' wildcard source="*" reset works uniformly,
    not just from the two states exercised above."""
    base = _tmp_base()
    flow = IEC62471ClassificationFlow(base_dir=base, render_svg=False)
    flow.reset()
    assert flow.state == "start" and flow.attempt == 2
    flow.reset()
    assert flow.state == "start" and flow.attempt == 3


# ---------------------------------------------------------------------------
# Intake flows
# ---------------------------------------------------------------------------

def test_iec62471_intake_flow_end_to_end_matches_d1_21():
    base = _tmp_base()
    class_base = _tmp_base()
    flow = IEC62471IntakeFlow(base_dir=base, classification_base_dir=class_base, render_svg=False)
    flow.provide_alpha_rad(Q(0.575, "rad"))
    flow.provide_actinic_uv_applicable(True)
    flow.provide_actinic_uv_value(Q(30e-6, "W/m^2"))
    flow.provide_near_uv_applicable(True)
    flow.provide_near_uv_value(Q(176e-3, "W/m^2"))
    flow.provide_blue_light_applicable(True)
    flow.provide_blue_light_value(Q(55e-3, "W/(m^2*sr)"))
    flow.provide_retinal_thermal_applicable(True)
    flow.provide_retinal_thermal_value(Q(255e-3, "W/(m^2*sr)"))
    flow.provide_ir_applicable(False)
    assert flow.state in IEC62471_INTAKE_TERMINAL_STATES
    assert flow.launched_result == "Exempt"
    result = read_result(base, flow.run_id)
    assert result["result"]["launched_run_id"] == flow.launched_run_id
    assert result["result"]["launched_result"] == "Exempt"


def test_iec62471_intake_flow_rejects_bare_float_field():
    base = _tmp_base()
    class_base = _tmp_base()
    flow = IEC62471IntakeFlow(base_dir=base, classification_base_dir=class_base, render_svg=False)
    _assert_raises(ValueError, flow.provide_alpha_rad, 0.575)
    assert flow.state == "awaiting_alpha_rad"


def test_iec62471_intake_flow_skips_value_question_when_not_applicable():
    base = _tmp_base()
    class_base = _tmp_base()
    flow = IEC62471IntakeFlow(base_dir=base, classification_base_dir=class_base, render_svg=False)
    flow.provide_alpha_rad(Q(0.575, "rad"))
    flow.provide_actinic_uv_applicable(False)
    assert flow.state == "awaiting_near_uv_applicable"  # auto-advanced past the value question
    skip_event = next(
        e for e in read_events(base, flow.run_id) if e.get("field") == "actinic_uv_value"
    )
    assert "not applicable" in skip_event["message"]


def test_iec62471_intake_flow_explain_current_state_has_question_and_example():
    base = _tmp_base()
    class_base = _tmp_base()
    flow = IEC62471IntakeFlow(base_dir=base, classification_base_dir=class_base, render_svg=False)
    msg = flow.explain_current_state()
    assert "alpha_rad" in msg or "angular subtense" in msg
    assert "e.g." in msg


def test_iec62471_intake_flow_reset():
    base = _tmp_base()
    class_base = _tmp_base()
    flow = IEC62471IntakeFlow(base_dir=base, classification_base_dir=class_base, render_svg=False)
    flow.provide_alpha_rad(Q(0.575, "rad"))
    flow.reset()
    assert flow.state == "start"
    assert flow.attempt == 2


def test_iec60825_1_intake_flow_end_to_end_matches_hene():
    base = _tmp_base()
    class_base = _tmp_base()
    flow = IEC60825_1IntakeFlow(base_dir=base, classification_base_dir=class_base, render_svg=False)
    flow.provide_measured_power_W(Q(0.0004, "W"))
    flow.provide_wavelength_nm(Q(632.8, "nm"))
    flow.provide_alpha_rad_provided(False)
    flow.provide_duration_s_class1_provided(False)
    assert flow.state in IEC60825_1_INTAKE_TERMINAL_STATES
    assert flow.launched_result == "Class 2 or 2M"


def test_iec60825_1_intake_flow_custom_alpha_and_duration():
    base = _tmp_base()
    class_base = _tmp_base()
    flow = IEC60825_1IntakeFlow(base_dir=base, classification_base_dir=class_base, render_svg=False)
    flow.provide_measured_power_W(Q(0.0004, "W"))
    flow.provide_wavelength_nm(Q(632.8, "nm"))
    flow.provide_alpha_rad_provided(True)
    flow.provide_alpha_rad_value(Q(1.5, "mrad"))
    flow.provide_duration_s_class1_provided(True)
    flow.provide_duration_s_class1_value(Q(100, "s"))
    assert flow.state in IEC60825_1_INTAKE_TERMINAL_STATES


def test_iec60825_1_intake_flow_rejects_bare_float_power():
    base = _tmp_base()
    class_base = _tmp_base()
    flow = IEC60825_1IntakeFlow(base_dir=base, classification_base_dir=class_base, render_svg=False)
    _assert_raises(ValueError, flow.provide_measured_power_W, 0.0004)
    assert flow.state == "awaiting_measured_power_W"


# ---------------------------------------------------------------------------
# Dashboard intake section
# ---------------------------------------------------------------------------

def test_dashboard_intake_section_lists_pending_question():
    from ray_tracing_shapely.optical_elements.eye_safety_classification_flow.dashboard import make_handler

    base = _tmp_base()
    class_base = _tmp_base()
    IEC62471IntakeFlow(base_dir=base, classification_base_dir=class_base, render_svg=False)
    handler_cls = make_handler(class_base, intake_base_dir=base)
    html = handler_cls._page_html.__get__(object.__new__(handler_cls))()
    assert "Intake runs" in html
    assert "angular subtense" in html


def test_dashboard_no_intake_section_without_intake_base_dir():
    from ray_tracing_shapely.optical_elements.eye_safety_classification_flow.dashboard import make_handler

    class_base = _tmp_base()
    handler_cls = make_handler(class_base)
    html = handler_cls._page_html.__get__(object.__new__(handler_cls))()
    assert "Intake runs" not in html


# ---------------------------------------------------------------------------
# SVG rendering -- skipped when `dot` is not on PATH
# ---------------------------------------------------------------------------

def test_graphviz_available_returns_bool():
    assert isinstance(graphviz_available(), bool)


def test_iec62471_flow_renders_svg_when_dot_available():
    if not graphviz_available():
        print("  SKIP (dot not on PATH)")
        return
    base = _tmp_base()
    flow = IEC62471ClassificationFlow(base_dir=base)  # render_svg=True default
    flow.submit_input(_D1_21_PAYLOAD)
    svg_path = run_dir(base, flow.run_id) / "state.svg"
    assert svg_path.exists()
    assert svg_path.stat().st_size > 0
    assert b"<svg" in svg_path.read_bytes()


def test_iec60825_1_flow_renders_svg_when_dot_available():
    if not graphviz_available():
        print("  SKIP (dot not on PATH)")
        return
    base = _tmp_base()
    flow = IEC60825_1ClassificationFlow(base_dir=base)
    flow.submit_input(_HENE_PAYLOAD)
    svg_path = run_dir(base, flow.run_id) / "state.svg"
    assert svg_path.exists()
    assert svg_path.stat().st_size > 0


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _run_all() -> int:
    tests = [
        test_make_run_id_includes_standard_and_pid,
        test_run_dir_creates_directory,
        test_write_inputs_and_read_result_roundtrip,
        test_append_event_assigns_sequential_seq,
        test_read_events_empty_for_unknown_run,
        test_append_manifest_and_latest_manifest_rows,
        test_update_heartbeat_upserts_single_row_per_run,
        test_is_stale_true_for_old_nonterminal_state,
        test_is_stale_false_for_terminal_state_regardless_of_age,
        test_is_stale_false_for_fresh_heartbeat,
        test_iec62471_flow_full_state_sequence,
        test_iec62471_flow_skipped_hazard_recorded_as_inapplicable,
        test_iec62471_flow_parity_with_classify_measurement_directly,
        test_iec62471_flow_parity_hazardous_case_is_rg3,
        test_iec62471_flow_writes_inputs_result_and_manifest,
        test_iec62471_frame_input_rejects_missing_alpha,
        test_iec62471_frame_input_rejects_negative_alpha,
        test_iec62471_frame_input_rejects_bare_float_alpha,
        test_iec62471_frame_input_rejects_missing_hazards_dict,
        test_iec62471_frame_input_rejects_missing_hazard_key,
        test_iec62471_frame_input_rejects_applicable_without_value,
        test_iec62471_frame_input_rejects_applicable_with_bare_float_value,
        test_iec62471_frame_input_rejects_inapplicable_with_value,
        test_iec62471_frame_input_valid_payload_advances_and_recovers,
        test_iec60825_1_flow_full_state_sequence_visible_wavelength,
        test_iec60825_1_flow_class_2_skipped_for_non_visible_wavelength,
        test_iec60825_1_flow_parity_with_classify_measurement_directly,
        test_iec60825_1_flow_parity_non_visible_wavelength,
        test_iec60825_1_flow_default_alpha_and_duration_applied,
        test_iec60825_1_frame_input_rejects_missing_power,
        test_iec60825_1_frame_input_rejects_negative_power,
        test_iec60825_1_frame_input_rejects_missing_wavelength,
        test_iec60825_1_frame_input_rejects_bare_float_power,
        test_iec60825_1_frame_input_rejects_bare_float_wavelength,
        test_iec60825_1_frame_input_rejects_bare_float_alpha_when_given,
        test_iec60825_1_frame_input_accepts_explicit_alpha_and_duration,
        test_expected_dimensionality_fixed_hazards,
        test_expected_dimensionality_blue_light_depends_on_alpha,
        test_expected_dimensionality_unknown_hazard_raises,
        test_checked_hazard_value_rejects_bare_float,
        test_checked_hazard_value_rejects_bare_int,
        test_checked_hazard_value_rejects_bool,
        test_checked_hazard_value_accepts_quantity_correct_family,
        test_checked_hazard_value_accepts_string,
        test_checked_hazard_value_rejects_wrong_radiometric_family,
        test_checked_hazard_value_rejects_dose_where_rate_expected,
        test_checked_scalar_rejects_bare_float,
        test_checked_scalar_rejects_bool,
        test_checked_scalar_accepts_quantity_and_converts,
        test_checked_scalar_accepts_string,
        test_checked_scalar_rejects_wrong_dimensionality,
        test_checked_scalar_angle_converts_degrees,
        test_checked_radiance_from_irradiance_matches_worked_example,
        test_checked_radiance_from_irradiance_accepts_strings,
        test_checked_radiance_from_irradiance_rejects_dose_as_irradiance,
        test_checked_radiance_from_irradiance_rejects_radiance_as_irradiance,
        test_checked_radiance_from_irradiance_rejects_length_as_solid_angle,
        test_checked_irradiance_from_radiance_is_the_inverse,
        test_iec62471_frame_input_quantity_and_string_payloads_match,
        test_iec62471_frame_input_rejects_irradiance_where_radiance_expected,
        test_iec60825_1_frame_input_accepts_quantity_payload,
        test_iec60825_1_frame_input_rejects_dose_as_power,
        test_explain_comparison_pass,
        test_explain_comparison_fail,
        test_explain_comparison_rejects_other_comparator,
        test_explain_field_message_contains_all_parts,
        test_iec62471_eval_states_emit_comparison_field,
        test_iec62471_comparison_verdicts_match_classify_measurement_decision,
        test_iec62471_explain_current_state_matches_last_event_message,
        test_iec60825_1_eval_states_emit_comparison_field,
        test_iec60825_1_explain_current_state_matches_last_event_message,
        test_margin_ratio_pass_below_one,
        test_margin_ratio_fail_above_one,
        test_summarize_margins_picks_highest_ratio,
        test_summarize_margins_single_criterion_message_shape,
        test_summarize_margins_over_limit,
        test_summarize_margins_empty,
        test_iec62471_summarize_margins_state_reports_tightest_in_winning_group,
        test_iec62471_summarize_margins_state_rg3_falls_back_to_rg2,
        test_iec60825_1_summarize_margins_state_reports_winning_class_only,
        test_iec60825_1_summarize_margins_state_above_class_3r_uses_class_3r_margin,
        test_iec62471_flow_reset_from_done_returns_to_start,
        test_iec60825_1_flow_reset_from_mid_flow,
        test_reset_works_from_any_state_wildcard_source,
        test_iec62471_intake_flow_end_to_end_matches_d1_21,
        test_iec62471_intake_flow_rejects_bare_float_field,
        test_iec62471_intake_flow_skips_value_question_when_not_applicable,
        test_iec62471_intake_flow_explain_current_state_has_question_and_example,
        test_iec62471_intake_flow_reset,
        test_iec60825_1_intake_flow_end_to_end_matches_hene,
        test_iec60825_1_intake_flow_custom_alpha_and_duration,
        test_iec60825_1_intake_flow_rejects_bare_float_power,
        test_dashboard_intake_section_lists_pending_question,
        test_dashboard_no_intake_section_without_intake_base_dir,
        test_graphviz_available_returns_bool,
        test_iec62471_flow_renders_svg_when_dot_available,
        test_iec60825_1_flow_renders_svg_when_dot_available,
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
        print("\nAll eye-safety classification flow tests passed.")
    return failures


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
