"""
Python-specific module: IEC 62471 classification flow

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
PYTHON-SPECIFIC MODULE: IEC 62471 classification flow
===============================================================================
Wraps (does not re-implement) `eye_safety.iec62471.classify_measurement`:
`iec62471.classify_measurement` is a flat, per-band evaluation over up to
five independently-optional measured hazard values, each checked against
*three* different per-risk-group limits (Exempt/RG1/RG2, ascending
severity, first-to-pass-all wins) -- see
dev_doc/architecture/components/eye_safety_classification_flow.md for why this shape differs from
IEC 60825-1's
ascending AEL ladder (iec60825_1_flow.py).

    start -> frame_input -> validate_dimensions
           -> eval_actinic_uv_exempt -> eval_actinic_uv_rg1 -> eval_actinic_uv_rg2
           -> eval_near_uv_exempt -> eval_near_uv_rg1 -> eval_near_uv_rg2
           -> eval_blue_light_exempt -> eval_blue_light_rg1 -> eval_blue_light_rg2
           -> eval_retinal_thermal_exempt -> eval_retinal_thermal_rg1 -> eval_retinal_thermal_rg2
           -> eval_ir_exempt -> eval_ir_rg1 -> eval_ir_rg2
           -> determine_risk_group -> summarize_margins -> done

**Each hazard gets three atomic states, one per risk group, not one
state bundling all three** -- explicit, atomic states for each aspect,
rather than one state per hazard emitting three comparisons in a single
event. [KD10: the diagram must show what the underlying function actually
does, and it checks three limits per hazard.] Each of the 15 `eval_*` states calls the same `mpe_*`
function `classify_measurement` calls internally, at that group's own
reference duration (`iec62471.risk_group_reference_duration_s`, or
`iec62471.retinal_thermal_classification_limit` for the one hazard that
is not a duration lookup -- see that function's own docstring for the
`C-EYE-06` correction it represents), purely for observability: the
resulting `LimitResult` and a `ComparisonExplanation` (`explanations.py`)
against this run's own measured value, never a second, independent
pass/fail decision. `determine_risk_group` still calls
`iec62471.classify_measurement` exactly once, unchanged, and that string
remains the only thing `C-EYE-05`'s parity guarantee is about; a second
parity check additionally asserts every
`ComparisonExplanation.verdict` recorded along the way agrees with what
that same call implies for its hazard/group -- if the two ever
disagreed, that would itself be a `C-EYE-05`-class regression.

`frame_input` validates rather than decides: it demands a fully-specified payload -- `alpha_rad` plus,
for each of the five hazard bands, an explicit `applicable` bool and (if
applicable) a value -- and refuses to advance (raises `ValueError`,
blocking the transition) if anything required is missing. It does not
itself decide which hazards are inapplicable to a real source -- that is
a judgment about the real source, supplied by whoever calls
`submit_input` (today: a human or a script; `intake_flow.py` gathers that
payload field-by-field; an agentic wrapper is not built).

**Every value must be a `pint.Quantity` or a Pint-formatted string --
a bare number is rejected, not silently trusted** [KA9: a number with no
unit is not a measurement, and an assumed unit is how a wrong answer
stays plausible] (see
`dimensional_checks.py`'s module docstring for why an earlier, opt-in
version of this check defeated its own purpose). `validate_dimensions` is
this check's own dedicated state, immediately after `frame_input` --
`submit_input`'s payload is validated *and reduced to plain floats* by
the time this state's `on_enter` runs (the checking itself lives in the
`before` callback on the `frame_input -> validate_dimensions` transition,
so a malformed payload never leaves `frame_input` at all); the state
exists so this is a visible, self-contained step in the run -- its own
node in `state.svg`, its own `events.jsonl` entry -- not just an internal
function call nothing else can see. `eye_safety`'s
`angle_from_size_distance`/`radiance_from_irradiance` are available for a
caller to derive `alpha_rad`/a hazard's value from raw geometry/
measurements before calling `submit_input` -- this module does not call
them itself.

A global `reset` trigger (`source: "*"`, defined once per
transition table below, its bookkeeping shared in `flow_base.py`) lands
back at `start` from any state, including `done` -- an evaluator watching
a classification unfold can retry with different values without a fresh
run.

Once `submit_input` is called, the whole `validate_dimensions` ->
`eval_*` -> `determine_risk_group` -> `done` chain runs synchronously to
completion (each `on_enter_<state>` calls `_advance()` itself) -- none of
those states need external input, only `frame_input` does.
===============================================================================
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional

from . import persistence
from .flow_base import ObservableFlow
from .dimensional_checks import checked_hazard_value, checked_scalar, expected_dimensionality_for_hazard
from .explanations import explain_comparison, summarize_margins
from ..eye_safety import iec62471
from ..eye_safety.result import LimitResult
from ..units import ANGLE

#: Each of the five hazard bands gets three atomic states, one
#: per risk group, hand-enumerated (not generated) matching this
#: codebase's existing state-table convention.
IEC62471_STATES = [
    "start",
    "frame_input",
    "validate_dimensions",
    "eval_actinic_uv_exempt",
    "eval_actinic_uv_rg1",
    "eval_actinic_uv_rg2",
    "eval_near_uv_exempt",
    "eval_near_uv_rg1",
    "eval_near_uv_rg2",
    "eval_blue_light_exempt",
    "eval_blue_light_rg1",
    "eval_blue_light_rg2",
    "eval_retinal_thermal_exempt",
    "eval_retinal_thermal_rg1",
    "eval_retinal_thermal_rg2",
    "eval_ir_exempt",
    "eval_ir_rg1",
    "eval_ir_rg2",
    "determine_risk_group",
    "summarize_margins",
    "done",
]

IEC62471_TRANSITIONS = [
    {"trigger": "begin", "source": "start", "dest": "frame_input"},
    {"trigger": "submit_input", "source": "frame_input", "dest": "validate_dimensions",
     "before": "_validate_and_store_payload"},
    {"trigger": "_advance", "source": "validate_dimensions", "dest": "eval_actinic_uv_exempt"},
    {"trigger": "_advance", "source": "eval_actinic_uv_exempt", "dest": "eval_actinic_uv_rg1"},
    {"trigger": "_advance", "source": "eval_actinic_uv_rg1", "dest": "eval_actinic_uv_rg2"},
    {"trigger": "_advance", "source": "eval_actinic_uv_rg2", "dest": "eval_near_uv_exempt"},
    {"trigger": "_advance", "source": "eval_near_uv_exempt", "dest": "eval_near_uv_rg1"},
    {"trigger": "_advance", "source": "eval_near_uv_rg1", "dest": "eval_near_uv_rg2"},
    {"trigger": "_advance", "source": "eval_near_uv_rg2", "dest": "eval_blue_light_exempt"},
    {"trigger": "_advance", "source": "eval_blue_light_exempt", "dest": "eval_blue_light_rg1"},
    {"trigger": "_advance", "source": "eval_blue_light_rg1", "dest": "eval_blue_light_rg2"},
    {"trigger": "_advance", "source": "eval_blue_light_rg2", "dest": "eval_retinal_thermal_exempt"},
    {"trigger": "_advance", "source": "eval_retinal_thermal_exempt", "dest": "eval_retinal_thermal_rg1"},
    {"trigger": "_advance", "source": "eval_retinal_thermal_rg1", "dest": "eval_retinal_thermal_rg2"},
    {"trigger": "_advance", "source": "eval_retinal_thermal_rg2", "dest": "eval_ir_exempt"},
    {"trigger": "_advance", "source": "eval_ir_exempt", "dest": "eval_ir_rg1"},
    {"trigger": "_advance", "source": "eval_ir_rg1", "dest": "eval_ir_rg2"},
    {"trigger": "_advance", "source": "eval_ir_rg2", "dest": "determine_risk_group"},
    {"trigger": "_advance", "source": "determine_risk_group", "dest": "summarize_margins"},
    {"trigger": "_advance", "source": "summarize_margins", "dest": "done"},
    {"trigger": "reset", "source": "*", "dest": "start", "before": "_on_reset"},
]

IEC62471_TERMINAL_STATES = ("done",)

#: The five hazard bands `iec62471.classify_measurement` accepts, and the
#: FRAME_INPUT payload key each one maps to in `classify_measurement`'s
#: own kwargs.
_HAZARD_TO_KWARG = {
    "actinic_uv": "e_eff_w_m2",
    "near_uv": "e_uva_w_m2",
    "blue_light": "blue_light_value",
    "retinal_thermal": "l_r_w_m2_sr",
    "ir": "e_ir_w_m2",
}

#: hazard key -> `risk_group_reference_duration_s`'s own
#: duration-key spelling -- `retinal_thermal` is deliberately absent (see
#: `_compute_limit`).
_HAZARD_TO_DURATION_KEY = {
    "actinic_uv": "uv",
    "near_uv": "near_uv",
    "blue_light": "blue",
    "ir": "ir",
}


#: State-name group spelling ("exempt"/"rg1"/"rg2") -> `classify_measurement`'s
#: own group labels ("Exempt"/"RG1"/"RG2").
_GROUP_KEY_TO_LABEL = {"exempt": "Exempt", "rg1": "RG1", "rg2": "RG2"}


def _compute_limit(hazard_key: str, group: str, alpha_rad: float) -> LimitResult:
    """The `LimitResult` `classify_measurement` itself compares this
    hazard against for `group` -- called here purely for observability
    never a re-decision (see module docstring)."""
    group_label = _GROUP_KEY_TO_LABEL[group]
    if hazard_key == "retinal_thermal":
        return iec62471.retinal_thermal_classification_limit(group_label, alpha_rad)
    duration_s = iec62471.risk_group_reference_duration_s(
        group_label, _HAZARD_TO_DURATION_KEY[hazard_key],
    )
    if hazard_key == "actinic_uv":
        return iec62471.mpe_actinic_uv(duration_s)
    if hazard_key == "near_uv":
        return iec62471.mpe_near_uv(duration_s)
    if hazard_key == "blue_light":
        return iec62471.mpe_blue_light(duration_s, alpha_rad)
    if hazard_key == "ir":
        return iec62471.mpe_ir_eye(duration_s)
    raise ValueError(f"Unknown hazard key: {hazard_key!r}")


class IEC62471ClassificationFlow(ObservableFlow):
    """One instance per classification run. Construct, then call
    `submit_input(payload)` once with a fully-specified payload; the run
    completes synchronously and `self.result` holds the final
    Exempt/RG1/RG2/RG3 string."""

    def __init__(
        self, base_dir: Path, run_id: Optional[str] = None, render_svg: bool = True,
    ) -> None:
        super().__init__(
            name="iec62471", states=IEC62471_STATES,
            transitions_list=IEC62471_TRANSITIONS, initial="start",
            base_dir=base_dir, run_id=run_id, render_svg=render_svg,
        )
        self.payload: Optional[Dict[str, Any]] = None
        self.result: Optional[str] = None
        self.begin()

    def _validate_and_store_payload(self, payload: Dict[str, Any]) -> None:
        """FRAME_INPUT's validation. Raises ValueError (blocking the
        transition into `validate_dimensions` -- see flow_base.py's
        docstring / the `transitions` semantics this relies on) if the
        payload is incomplete, malformed, or dimensionally unclear. Does
        not decide which hazards are applicable -- only that the caller's
        own decision was fully and correctly stated.

        `alpha_rad` and every applicable hazard's `value` must
        be a `pint.Quantity` or a Pint-formatted string -- **mandatory**,
        not opt-in (see `dimensional_checks.py`'s module docstring for why
        an earlier version silently trusting a bare number defeated its
        own purpose). Each is validated against the correct expected
        dimensionality (`dimensional_checks.expected_dimensionality_for_
        hazard`, which accounts for `blue_light`'s alpha-dependent
        radiance-vs-irradiance dispatch) and reduced to a plain float in
        the expected SI unit before being stored. This is the one place a
        wrong-unit or wrong-radiometric-family mistake (an irradiance
        where a radiance is expected, or vice versa -- exactly the
        mistake plain dimensionality checking cannot catch, see
        `dimensional_checks.py`'s own docstring) gets caught, loudly,
        before it reaches `classify_measurement`.
        """
        if "alpha_rad" not in payload:
            raise ValueError("FRAME_INPUT payload must include 'alpha_rad'.")
        alpha_rad = checked_scalar(payload["alpha_rad"], ANGLE, name="alpha_rad")
        if alpha_rad < 0.0:
            raise ValueError("alpha_rad must be non-negative.")
        hazards = payload.get("hazards")
        if not isinstance(hazards, dict):
            raise ValueError("FRAME_INPUT payload must include a 'hazards' dict.")
        checked_hazards: Dict[str, Dict[str, Any]] = {}
        for key in _HAZARD_TO_KWARG:
            if key not in hazards:
                raise ValueError(f"FRAME_INPUT payload's 'hazards' is missing '{key}'.")
            entry = hazards[key]
            if not isinstance(entry, dict) or not isinstance(entry.get("applicable"), bool):
                raise ValueError(
                    f"hazards['{key}'] must be a dict with a boolean 'applicable'."
                )
            raw_value = entry.get("value")
            if entry["applicable"]:
                if raw_value is None:
                    raise ValueError(
                        f"hazards['{key}'] is applicable but has no 'value'."
                    )
                value = checked_hazard_value(key, raw_value, alpha_rad, name=f"hazards['{key}']['value']")
            else:
                if raw_value is not None:
                    raise ValueError(
                        f"hazards['{key}'] is not applicable but 'value' is not None -- "
                        "omit the value entirely for an inapplicable hazard."
                    )
                value = None
            checked_hazards[key] = {"applicable": entry["applicable"], "value": value}
        self.payload = {"alpha_rad": alpha_rad, "hazards": checked_hazards}
        persistence.write_inputs(self.base_dir, self.run_id, self.payload)

    def on_enter_validate_dimensions(self, *_args, **_kwargs) -> None:
        """The dimensional check's own dedicated FSM step. By the time this state's
        `on_enter` runs, `_validate_and_store_payload` (the `before`
        callback on the transition *into* this state) has already
        validated and converted every physical value -- a malformed
        payload never leaves `frame_input`, so reaching this state at all
        already means every dimension was stated clearly. This state's
        job is purely to make that fact visible: its own node in
        `state.svg`, its own `events.jsonl` entry, naming exactly what was
        confirmed -- not a second round of checking.
        """
        checked_count = sum(
            1 for entry in self.payload["hazards"].values() if entry["applicable"]
        )
        self.emit_event(
            message=f"dimensions validated: alpha_rad and {checked_count} hazard "
                    f"value(s) confirmed dimensionally consistent",
        )
        self._advance()

    def _record_hazard_group(self, hazard_key: str, group_key: str) -> None:
        """One hazard, one risk group -- computes the same
        `LimitResult` `classify_measurement` compares this hazard against
        for this group, and (if applicable) a `ComparisonExplanation`
        against this run's own measured value. Skipped hazards are still
        visited (matching `eval_class_2`'s own "skipped, not applicable"
        precedent) rather than shrinking the diagram."""
        entry = self.payload["hazards"][hazard_key]
        group_label = _GROUP_KEY_TO_LABEL[group_key]
        if not entry["applicable"]:
            self.emit_event(
                hazard=hazard_key, group=group_label, applicable=False, value=None,
                message=f"{hazard_key} ({group_label}): skipped, not applicable to this source",
            )
            self.update_detail(last_hazard=hazard_key, last_group=group_label)
            return
        limit = _compute_limit(hazard_key, group_key, self.payload["alpha_rad"])
        measured_unit = expected_dimensionality_for_hazard(hazard_key, self.payload["alpha_rad"])
        explanation = explain_comparison(entry["value"], measured_unit, limit)
        self.set_explanation(explanation)
        self.emit_event(
            hazard=hazard_key, group=group_label, applicable=True, value=entry["value"],
            result=asdict(limit), comparison=asdict(explanation),
            message=explanation.message,
        )
        self.update_detail(last_hazard=hazard_key, last_group=group_label)

    def on_enter_eval_actinic_uv_exempt(self, *_args, **_kwargs) -> None:
        self._record_hazard_group("actinic_uv", "exempt")
        self._advance()

    def on_enter_eval_actinic_uv_rg1(self, *_args, **_kwargs) -> None:
        self._record_hazard_group("actinic_uv", "rg1")
        self._advance()

    def on_enter_eval_actinic_uv_rg2(self, *_args, **_kwargs) -> None:
        self._record_hazard_group("actinic_uv", "rg2")
        self._advance()

    def on_enter_eval_near_uv_exempt(self, *_args, **_kwargs) -> None:
        self._record_hazard_group("near_uv", "exempt")
        self._advance()

    def on_enter_eval_near_uv_rg1(self, *_args, **_kwargs) -> None:
        self._record_hazard_group("near_uv", "rg1")
        self._advance()

    def on_enter_eval_near_uv_rg2(self, *_args, **_kwargs) -> None:
        self._record_hazard_group("near_uv", "rg2")
        self._advance()

    def on_enter_eval_blue_light_exempt(self, *_args, **_kwargs) -> None:
        self._record_hazard_group("blue_light", "exempt")
        self._advance()

    def on_enter_eval_blue_light_rg1(self, *_args, **_kwargs) -> None:
        self._record_hazard_group("blue_light", "rg1")
        self._advance()

    def on_enter_eval_blue_light_rg2(self, *_args, **_kwargs) -> None:
        self._record_hazard_group("blue_light", "rg2")
        self._advance()

    def on_enter_eval_retinal_thermal_exempt(self, *_args, **_kwargs) -> None:
        self._record_hazard_group("retinal_thermal", "exempt")
        self._advance()

    def on_enter_eval_retinal_thermal_rg1(self, *_args, **_kwargs) -> None:
        self._record_hazard_group("retinal_thermal", "rg1")
        self._advance()

    def on_enter_eval_retinal_thermal_rg2(self, *_args, **_kwargs) -> None:
        self._record_hazard_group("retinal_thermal", "rg2")
        self._advance()

    def on_enter_eval_ir_exempt(self, *_args, **_kwargs) -> None:
        self._record_hazard_group("ir", "exempt")
        self._advance()

    def on_enter_eval_ir_rg1(self, *_args, **_kwargs) -> None:
        self._record_hazard_group("ir", "rg1")
        self._advance()

    def on_enter_eval_ir_rg2(self, *_args, **_kwargs) -> None:
        self._record_hazard_group("ir", "rg2")
        self._advance()

    def on_enter_determine_risk_group(self, *_args, **_kwargs) -> None:
        kwargs = {}
        for hazard_key, kwarg_name in _HAZARD_TO_KWARG.items():
            entry = self.payload["hazards"][hazard_key]
            kwargs[kwarg_name] = entry["value"] if entry["applicable"] else None
        classification = iec62471.classify_measurement(self.payload["alpha_rad"], **kwargs)
        self.result = classification
        self.emit_event(
            classification=classification,
            message=f"risk group: {classification}",
        )
        self._advance()

    def on_enter_summarize_margins(self, *_args, **_kwargs) -> None:
        """Which applicable hazard, among the *winning* risk
        group's own checks, came closest to failing -- computed from this
        run's own already-recorded events (every `eval_*` state's
        `ComparisonExplanation` carries a `margin_ratio`), not a
        re-decision. Scoped to the winning group specifically: every
        hazard checked there passed (that is why it won), so the tightest
        one there is exactly "how close did this classification come to
        tipping into the next, stricter group". For the RG3 fallback (no group passed), RG2 -- the
        last, most permissive group actually checked -- is used instead,
        showing how far the worst-exceeding hazard actually went over.
        """
        events = persistence.read_events(self.base_dir, self.run_id)
        by_group: Dict[str, Dict[str, float]] = {"Exempt": {}, "RG1": {}, "RG2": {}}
        for e in events:
            if "comparison" in e:
                by_group[e["group"]][e["hazard"]] = e["comparison"]["margin_ratio"]
        winning_group = self.result if self.result in by_group else "RG2"
        summary = summarize_margins(winning_group, by_group[winning_group])
        self.set_explanation(summary)
        self.emit_event(
            winning_group=winning_group, margins_by_group=by_group,
            tightest_criterion=summary.tightest_criterion,
            tightest_margin_ratio=summary.tightest_margin_ratio,
            message=summary.message,
        )
        self._advance()

    def on_enter_done(self, *_args, **_kwargs) -> None:
        self.finish(self.result)
        self.emit_event(message="done", result=self.result)
