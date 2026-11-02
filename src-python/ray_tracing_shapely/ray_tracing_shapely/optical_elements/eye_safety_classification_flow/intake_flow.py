"""
Python-specific module: intake FSM -- gathers a payload field by field, then launches a classification flow

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
PYTHON-SPECIFIC MODULE: intake_flow
===============================================================================
Nothing existed upstream of `FRAME_INPUT` to actually gather a payload
from a human or agent field-by-field. This module builds the
*mechanical* two-thirds of that gap -- tracking what has and hasn't been
supplied, and asking for what's missing -- while leaving the genuine
domain judgment (which hazards apply to a real source, what duration a
scenario calls for) external, exactly where `FRAME_INPUT` already leaves
it: `FRAME_INPUT`'s own "validates, does not decide" principle, held one
step further upstream.

**Two intake FSMs, not one with an internal `select_standard` state.** A
`select_standard` first state inside one shared diagram was planned and
then dropped when building it revealed a direct conflict with the
principle of **one fixed diagram per standard, the same shape for every
run** [KD10: a diagram whose shape varies with its input is a diagram
nobody can check against the standard] -- the same reasoning behind the
per-risk-group atomic states and the fixed hazard-question order below.
[KD2: the plan said one diagram; the code says two, and this paragraph
says why.]
IEC 62471 and IEC 60825-1 intake genuinely ask for different fields --
forcing them into one diagram would make that diagram's actual shape vary
by which standard was selected, exactly the thing `eval_class_2`'s own
"visited and skipped" precedent exists to avoid. `IEC62471ClassificationFlow`/
`IEC60825_1ClassificationFlow` already resolve their own "which standard"
question the same way: two separate classes, with the choice of which one
to construct made by a plain external caller, never a state inside either
diagram. `IEC62471IntakeFlow`/`IEC60825_1IntakeFlow` do the same.

**Per-field states, hand-enumerated, not schema-generated** -- matching
this codebase's existing convention everywhere else (every other state
table in this package is a literal, hand-typed list). The field-schema
data (`_IEC62471_HAZARD_INFO` etc.) still exists, and each hand-written state's `on_enter` reads its
own entry from it for its `FieldExplanation` -- the schema drives each
state's *content*, it does not generate the state list itself.

**IEC 62471's five hazards are five fixed applicable?/value? question
pairs, always asked, in the same order every run -- Option 1, not a
dynamic checklist** -- for the same "one fixed diagram" reason: a checklist-then-conditional-followups design
would make intake's own diagram vary run to run. A hazard's own
`awaiting_<hazard>_value` state is still visited even when the caller
already said it's inapplicable -- it just auto-advances with a "not
applicable, no value needed" event instead of asking a question,
mirroring `eval_class_2`'s own precedent exactly.

    IEC 62471 intake:
      start -> awaiting_alpha_rad
             -> awaiting_actinic_uv_applicable -> awaiting_actinic_uv_value
             -> awaiting_near_uv_applicable -> awaiting_near_uv_value
             -> awaiting_blue_light_applicable -> awaiting_blue_light_value
             -> awaiting_retinal_thermal_applicable -> awaiting_retinal_thermal_value
             -> awaiting_ir_applicable -> awaiting_ir_value
             -> ready -> done

    IEC 60825-1 intake:
      start -> awaiting_measured_power_W -> awaiting_wavelength_nm
             -> awaiting_alpha_rad_provided -> awaiting_alpha_rad_value
             -> awaiting_duration_s_class1_provided -> awaiting_duration_s_class1_value
             -> ready -> done

`alpha_rad`/`duration_s_class1` are optional on the IEC 60825-1 side
(`classify_measurement`'s own standard-mandated defaults apply if
omitted) -- modelled the same way as an IEC 62471 hazard: a
`_provided`/`_value` state pair, so the diagram stays fixed whether or
not a caller wants to override the default, rather than the field simply
not existing in the graph.

**Per-field, incremental validation** -- each `provide_<field>` trigger's
`before` callback routes through `checked_scalar`/`checked_hazard_value`
(`dimensional_checks.py`) immediately, so a caller gets an
immediate, specific rejection for one wrong field. The *raw*
`pint.Quantity`/string a caller supplies is what gets stored and later
forwarded, unchanged, into the launched classification flow's own
`submit_input` payload -- intake's own eager validation is a fast-fail
convenience, not a second source of truth for whether a value is
acceptable; `FRAME_INPUT`'s own validation is still what actually decides
that, exactly once, when the assembled payload is submitted.

**Every `awaiting_<field>` state explains itself** via
`explain_field`/`FieldExplanation` (`explanations.py`) -- a question, why
it matters (a citation), and a worked example, surfaced through the same
`ObservableFlow.explain_current_state()` a classification flow's `eval_*`
states use for their own `ComparisonExplanation`s. Some examples are
generated dynamically rather than fixed strings -- `blue_light`'s expected
unit depends on `alpha_rad` (`expected_dimensionality_for_hazard`), which
is why `alpha_rad`'s own question is always asked first,
before any hazard question, in both intake diagrams above.

**Terminal action**: `ready` assembles the collected payload and
constructs + drives the corresponding classification flow's
`submit_input(payload)` -- *composing* the two existing FSMs, not merging
into them. Each classification flow keeps its own `state.svg`/
`events.jsonl`/run directory under its own `classification_base_dir`;
intake's own `result.json` records the classification `run_id` and result
it launched (`launched_run_id`/`launched_result`), a cross-reference
field, not a merged persistence shape (`P-INTAKE-RUN`).

**The shared global `reset`** (`flow_base.py`) applies here too
-- an evaluator partway through answering intake's questions can restart
from `start` with a fresh `begin()` and different answers, without losing
the run's own identity.
===============================================================================
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from .flow_base import ObservableFlow
from .dimensional_checks import checked_scalar, checked_hazard_value, expected_dimensionality_for_hazard
from .explanations import explain_field
from .iec62471_flow import IEC62471ClassificationFlow
from .iec60825_1_flow import IEC60825_1ClassificationFlow
from ..units import ANGLE, POWER, TIME

# ---------------------------------------------------------------------------
# Declarative field info (question/citation), consumed by the
# hand-enumerated states below -- data, not a second state-generation path.
# ---------------------------------------------------------------------------

_IEC62471_ALPHA_RAD_INFO: Dict[str, str] = {
    "question": "What is the source's angular subtense (alpha_rad), as seen by the eye?",
    "citation": "IEC 62471 Sec. 4.2/4.3(c) -- decides blue_light's radiance-vs-irradiance "
                "dispatch at the standard's own 11 mrad boundary",
    "example": 'e.g. "30 deg" or "0.524 rad"',
}

#: hazard key -> (plain-language label, citation).
IEC62471_HAZARD_ORDER = ("actinic_uv", "near_uv", "blue_light", "retinal_thermal", "ir")

_IEC62471_HAZARD_INFO: Dict[str, Dict[str, str]] = {
    "actinic_uv": {
        "label": "actinic UV (180-400 nm, S(lambda)-weighted)",
        "citation": "IEC 62471 Annex I (a) / Eq. 4.1",
    },
    "near_uv": {
        "label": "near-UV / UVA (315-400 nm, unweighted)",
        "citation": "IEC 62471 Annex I (b) / Eq. 4.3",
    },
    "blue_light": {
        "label": "blue light (300-700 nm, B(lambda)-weighted)",
        "citation": "IEC 62471 Annex I (c)-(f) / Eq. 4.5 & 4.7 -- radiance above 11 mrad, "
                    "irradiance below",
    },
    "retinal_thermal": {
        "label": "retinal thermal (380-1400 nm, R(lambda)-weighted)",
        "citation": "IEC 62471 Annex I (g)/(h) / Eq. 4.9",
    },
    "ir": {
        "label": "IR, cornea/lens (780-3000 nm, unweighted)",
        "citation": "IEC 62471 Annex I (m)/(n) / Eq. 4.11",
    },
}


def _explain_hazard_applicable(hazard_key: str):
    info = _IEC62471_HAZARD_INFO[hazard_key]
    return explain_field(
        f"{hazard_key}_applicable",
        f"Does this source emit a measurable {info['label']} hazard?",
        info["citation"],
        'answer true or false',
    )


def _explain_hazard_value(hazard_key: str, alpha_rad: float):
    info = _IEC62471_HAZARD_INFO[hazard_key]
    expected_unit = expected_dimensionality_for_hazard(hazard_key, alpha_rad)
    return explain_field(
        f"{hazard_key}_value",
        f"What is the measured {info['label']} value?",
        info["citation"],
        f'e.g. "55 {expected_unit}"',
    )


IEC62471_INTAKE_STATES = [
    "start",
    "awaiting_alpha_rad",
    "awaiting_actinic_uv_applicable",
    "awaiting_actinic_uv_value",
    "awaiting_near_uv_applicable",
    "awaiting_near_uv_value",
    "awaiting_blue_light_applicable",
    "awaiting_blue_light_value",
    "awaiting_retinal_thermal_applicable",
    "awaiting_retinal_thermal_value",
    "awaiting_ir_applicable",
    "awaiting_ir_value",
    "ready",
    "done",
]

IEC62471_INTAKE_TRANSITIONS = [
    {"trigger": "begin", "source": "start", "dest": "awaiting_alpha_rad"},
    {"trigger": "provide_alpha_rad", "source": "awaiting_alpha_rad",
     "dest": "awaiting_actinic_uv_applicable", "before": "_provide_alpha_rad"},

    {"trigger": "provide_actinic_uv_applicable", "source": "awaiting_actinic_uv_applicable",
     "dest": "awaiting_actinic_uv_value", "before": "_provide_actinic_uv_applicable"},
    {"trigger": "provide_actinic_uv_value", "source": "awaiting_actinic_uv_value",
     "dest": "awaiting_near_uv_applicable", "before": "_provide_actinic_uv_value"},
    {"trigger": "_advance", "source": "awaiting_actinic_uv_value", "dest": "awaiting_near_uv_applicable"},

    {"trigger": "provide_near_uv_applicable", "source": "awaiting_near_uv_applicable",
     "dest": "awaiting_near_uv_value", "before": "_provide_near_uv_applicable"},
    {"trigger": "provide_near_uv_value", "source": "awaiting_near_uv_value",
     "dest": "awaiting_blue_light_applicable", "before": "_provide_near_uv_value"},
    {"trigger": "_advance", "source": "awaiting_near_uv_value", "dest": "awaiting_blue_light_applicable"},

    {"trigger": "provide_blue_light_applicable", "source": "awaiting_blue_light_applicable",
     "dest": "awaiting_blue_light_value", "before": "_provide_blue_light_applicable"},
    {"trigger": "provide_blue_light_value", "source": "awaiting_blue_light_value",
     "dest": "awaiting_retinal_thermal_applicable", "before": "_provide_blue_light_value"},
    {"trigger": "_advance", "source": "awaiting_blue_light_value", "dest": "awaiting_retinal_thermal_applicable"},

    {"trigger": "provide_retinal_thermal_applicable", "source": "awaiting_retinal_thermal_applicable",
     "dest": "awaiting_retinal_thermal_value", "before": "_provide_retinal_thermal_applicable"},
    {"trigger": "provide_retinal_thermal_value", "source": "awaiting_retinal_thermal_value",
     "dest": "awaiting_ir_applicable", "before": "_provide_retinal_thermal_value"},
    {"trigger": "_advance", "source": "awaiting_retinal_thermal_value", "dest": "awaiting_ir_applicable"},

    {"trigger": "provide_ir_applicable", "source": "awaiting_ir_applicable",
     "dest": "awaiting_ir_value", "before": "_provide_ir_applicable"},
    {"trigger": "provide_ir_value", "source": "awaiting_ir_value",
     "dest": "ready", "before": "_provide_ir_value"},
    {"trigger": "_advance", "source": "awaiting_ir_value", "dest": "ready"},

    {"trigger": "_advance", "source": "ready", "dest": "done"},
    {"trigger": "reset", "source": "*", "dest": "start", "before": "_on_reset"},
]

IEC62471_INTAKE_TERMINAL_STATES = ("done",)


class IEC62471IntakeFlow(ObservableFlow):
    """Gathers an `IEC62471ClassificationFlow` payload field by field, then
    launches one. Construct, call `begin()` is done automatically, then
    call `provide_alpha_rad(value)`, `provide_<hazard>_applicable(bool)`,
    `provide_<hazard>_value(value)` (skipped automatically if the hazard
    was marked inapplicable) for each of the five hazards in order,
    following `explain_current_state()` at each step. `self.launched_run_id`/
    `self.launched_result` are set once `ready`/`done` complete.
    """

    def __init__(
        self,
        base_dir: Path,
        classification_base_dir: Path,
        run_id: Optional[str] = None,
        render_svg: bool = True,
    ) -> None:
        super().__init__(
            name="iec62471_intake", states=IEC62471_INTAKE_STATES,
            transitions_list=IEC62471_INTAKE_TRANSITIONS, initial="start",
            base_dir=base_dir, run_id=run_id, render_svg=render_svg,
        )
        self.classification_base_dir = Path(classification_base_dir)
        self._alpha_rad_float: Optional[float] = None
        self._alpha_rad_raw: Any = None
        self._applicable: Dict[str, bool] = {}
        self._hazard_raw: Dict[str, Any] = {}
        self.launched_run_id: Optional[str] = None
        self.launched_result: Optional[str] = None
        self.begin()

    # -- alpha_rad -----------------------------------------------------

    def on_enter_awaiting_alpha_rad(self, *_args, **_kwargs) -> None:
        explanation = explain_field(
            "alpha_rad", _IEC62471_ALPHA_RAD_INFO["question"],
            _IEC62471_ALPHA_RAD_INFO["citation"], _IEC62471_ALPHA_RAD_INFO["example"],
        )
        self.set_explanation(explanation)
        self.emit_event(field="alpha_rad", message=explanation.message)
        self.update_detail(waiting_on="alpha_rad")

    def _provide_alpha_rad(self, value: Any) -> None:
        alpha_rad = checked_scalar(value, ANGLE, name="alpha_rad")
        if alpha_rad < 0.0:
            raise ValueError("alpha_rad must be non-negative.")
        self._alpha_rad_float = alpha_rad
        self._alpha_rad_raw = value

    # -- shared per-hazard helpers ---------------------------------------

    def _ask_applicable(self, hazard_key: str) -> None:
        explanation = _explain_hazard_applicable(hazard_key)
        self.set_explanation(explanation)
        self.emit_event(field=f"{hazard_key}_applicable", message=explanation.message)
        self.update_detail(waiting_on=f"{hazard_key}_applicable")

    def _store_applicable(self, hazard_key: str, flag: Any) -> None:
        if not isinstance(flag, bool):
            raise ValueError(
                f"{hazard_key}_applicable must be a bool, got {type(flag).__name__}: {flag!r}"
            )
        self._applicable[hazard_key] = flag

    def _ask_value(self, hazard_key: str) -> None:
        if not self._applicable[hazard_key]:
            self.emit_event(
                field=f"{hazard_key}_value",
                message=f"{hazard_key}: not applicable, no value needed",
            )
            self._advance()
            return
        explanation = _explain_hazard_value(hazard_key, self._alpha_rad_float)
        self.set_explanation(explanation)
        self.emit_event(field=f"{hazard_key}_value", message=explanation.message)
        self.update_detail(waiting_on=f"{hazard_key}_value")

    def _store_value(self, hazard_key: str, value: Any) -> None:
        checked_hazard_value(hazard_key, value, self._alpha_rad_float, name=f"{hazard_key} value")
        self._hazard_raw[hazard_key] = value

    # -- actinic_uv --------------------------------------------------------

    def on_enter_awaiting_actinic_uv_applicable(self, *_args, **_kwargs) -> None:
        self._ask_applicable("actinic_uv")

    def _provide_actinic_uv_applicable(self, flag: Any) -> None:
        self._store_applicable("actinic_uv", flag)

    def on_enter_awaiting_actinic_uv_value(self, *_args, **_kwargs) -> None:
        self._ask_value("actinic_uv")

    def _provide_actinic_uv_value(self, value: Any) -> None:
        self._store_value("actinic_uv", value)

    # -- near_uv -------------------------------------------------------

    def on_enter_awaiting_near_uv_applicable(self, *_args, **_kwargs) -> None:
        self._ask_applicable("near_uv")

    def _provide_near_uv_applicable(self, flag: Any) -> None:
        self._store_applicable("near_uv", flag)

    def on_enter_awaiting_near_uv_value(self, *_args, **_kwargs) -> None:
        self._ask_value("near_uv")

    def _provide_near_uv_value(self, value: Any) -> None:
        self._store_value("near_uv", value)

    # -- blue_light ------------------------------------------------------

    def on_enter_awaiting_blue_light_applicable(self, *_args, **_kwargs) -> None:
        self._ask_applicable("blue_light")

    def _provide_blue_light_applicable(self, flag: Any) -> None:
        self._store_applicable("blue_light", flag)

    def on_enter_awaiting_blue_light_value(self, *_args, **_kwargs) -> None:
        self._ask_value("blue_light")

    def _provide_blue_light_value(self, value: Any) -> None:
        self._store_value("blue_light", value)

    # -- retinal_thermal ---------------------------------------------------

    def on_enter_awaiting_retinal_thermal_applicable(self, *_args, **_kwargs) -> None:
        self._ask_applicable("retinal_thermal")

    def _provide_retinal_thermal_applicable(self, flag: Any) -> None:
        self._store_applicable("retinal_thermal", flag)

    def on_enter_awaiting_retinal_thermal_value(self, *_args, **_kwargs) -> None:
        self._ask_value("retinal_thermal")

    def _provide_retinal_thermal_value(self, value: Any) -> None:
        self._store_value("retinal_thermal", value)

    # -- ir --------------------------------------------------------------

    def on_enter_awaiting_ir_applicable(self, *_args, **_kwargs) -> None:
        self._ask_applicable("ir")

    def _provide_ir_applicable(self, flag: Any) -> None:
        self._store_applicable("ir", flag)

    def on_enter_awaiting_ir_value(self, *_args, **_kwargs) -> None:
        self._ask_value("ir")

    def _provide_ir_value(self, value: Any) -> None:
        self._store_value("ir", value)

    # -- terminal ----------------------------------------------------------

    def on_enter_ready(self, *_args, **_kwargs) -> None:
        hazards = {
            key: (
                {"applicable": True, "value": self._hazard_raw[key]}
                if self._applicable[key] else
                {"applicable": False, "value": None}
            )
            for key in IEC62471_HAZARD_ORDER
        }
        payload = {"alpha_rad": self._alpha_rad_raw, "hazards": hazards}
        self.emit_event(message="payload assembled, launching IEC62471ClassificationFlow")
        classification_flow = IEC62471ClassificationFlow(
            base_dir=self.classification_base_dir, render_svg=self._render_svg_enabled,
        )
        classification_flow.submit_input(payload)
        self.launched_run_id = classification_flow.run_id
        self.launched_result = classification_flow.result
        self._advance()

    def on_enter_done(self, *_args, **_kwargs) -> None:
        result = {"launched_run_id": self.launched_run_id, "launched_result": self.launched_result}
        self.finish(result)
        self.emit_event(
            message=f"done: launched classification run {self.launched_run_id}, "
                    f"result={self.launched_result}",
            **result,
        )


# ---------------------------------------------------------------------------
# IEC 60825-1 intake
# ---------------------------------------------------------------------------

_IEC60825_1_MEASURED_POWER_INFO: Dict[str, str] = {
    "question": "What is the measured accessible-emission power, through the appropriate "
                "aperture for this measurement condition?",
    "citation": "IEC 60825-1 / Henderson & Schulmeister table 4.4",
    "example": 'e.g. "0.4 mW" or "4e-4 W"',
}
_IEC60825_1_WAVELENGTH_INFO: Dict[str, str] = {
    "question": "What is the laser's wavelength?",
    "citation": "IEC 60825-1 -- selects which AEL chain applies (UV/visible-near-IR)",
    "example": 'e.g. "632.8 nm"',
}
_IEC60825_1_ALPHA_RAD_INFO: Dict[str, str] = {
    "question": "Do you want to specify a non-default angular subtense (alpha_rad)? "
                "If not, the standard's own small-source default applies.",
    "citation": "IEC 60825-1 -- only affects the retinal-thermal AEL branch (the C6 factor)",
    "example": "answer true or false",
}
_IEC60825_1_ALPHA_RAD_VALUE_INFO: Dict[str, str] = {
    "question": "What is the source's angular subtense (alpha_rad)?",
    "citation": "IEC 60825-1 -- only affects the retinal-thermal AEL branch (the C6 factor)",
    "example": 'e.g. "30 deg" or "0.524 rad"',
}
_IEC60825_1_DURATION_PROVIDED_INFO: Dict[str, str] = {
    "question": "Do you want to specify a non-default exposure duration for the Class 1/1M "
                "(and, for non-visible wavelengths, Class 3R) comparison? If not, the "
                "standard's own time base for this wavelength band applies (C-EYE-02).",
    "citation": "IEC 60825-1 Table 4.3",
    "example": "answer true or false",
}
_IEC60825_1_DURATION_VALUE_INFO: Dict[str, str] = {
    "question": "What exposure duration should be used for the Class 1/1M comparison?",
    "citation": "IEC 60825-1 Table 4.3",
    "example": 'e.g. "100 s"',
}

IEC60825_1_INTAKE_STATES = [
    "start",
    "awaiting_measured_power_W",
    "awaiting_wavelength_nm",
    "awaiting_alpha_rad_provided",
    "awaiting_alpha_rad_value",
    "awaiting_duration_s_class1_provided",
    "awaiting_duration_s_class1_value",
    "ready",
    "done",
]

IEC60825_1_INTAKE_TRANSITIONS = [
    {"trigger": "begin", "source": "start", "dest": "awaiting_measured_power_W"},
    {"trigger": "provide_measured_power_W", "source": "awaiting_measured_power_W",
     "dest": "awaiting_wavelength_nm", "before": "_provide_measured_power_W"},
    {"trigger": "provide_wavelength_nm", "source": "awaiting_wavelength_nm",
     "dest": "awaiting_alpha_rad_provided", "before": "_provide_wavelength_nm"},

    {"trigger": "provide_alpha_rad_provided", "source": "awaiting_alpha_rad_provided",
     "dest": "awaiting_alpha_rad_value", "before": "_provide_alpha_rad_provided"},
    {"trigger": "provide_alpha_rad_value", "source": "awaiting_alpha_rad_value",
     "dest": "awaiting_duration_s_class1_provided", "before": "_provide_alpha_rad_value"},
    {"trigger": "_advance", "source": "awaiting_alpha_rad_value",
     "dest": "awaiting_duration_s_class1_provided"},

    {"trigger": "provide_duration_s_class1_provided", "source": "awaiting_duration_s_class1_provided",
     "dest": "awaiting_duration_s_class1_value", "before": "_provide_duration_s_class1_provided"},
    {"trigger": "provide_duration_s_class1_value", "source": "awaiting_duration_s_class1_value",
     "dest": "ready", "before": "_provide_duration_s_class1_value"},
    {"trigger": "_advance", "source": "awaiting_duration_s_class1_value", "dest": "ready"},

    {"trigger": "_advance", "source": "ready", "dest": "done"},
    {"trigger": "reset", "source": "*", "dest": "start", "before": "_on_reset"},
]

IEC60825_1_INTAKE_TERMINAL_STATES = ("done",)


class IEC60825_1IntakeFlow(ObservableFlow):
    """Gathers an `IEC60825_1ClassificationFlow` payload field by field,
    then launches one. `alpha_rad`/`duration_s_class1` are each a
    provided?/value? pair -- answer `False` to the "provided?" question to
    take the standard's own default, matching `FRAME_INPUT`'s own
    optional-field semantics."""

    def __init__(
        self,
        base_dir: Path,
        classification_base_dir: Path,
        run_id: Optional[str] = None,
        render_svg: bool = True,
    ) -> None:
        super().__init__(
            name="iec60825_1_intake", states=IEC60825_1_INTAKE_STATES,
            transitions_list=IEC60825_1_INTAKE_TRANSITIONS, initial="start",
            base_dir=base_dir, run_id=run_id, render_svg=render_svg,
        )
        self.classification_base_dir = Path(classification_base_dir)
        self._measured_power_W_raw: Any = None
        self._wavelength_nm_raw: Any = None
        self._alpha_rad_provided: bool = False
        self._alpha_rad_raw: Any = None
        self._duration_provided: bool = False
        self._duration_raw: Any = None
        self.launched_run_id: Optional[str] = None
        self.launched_result: Optional[str] = None
        self.begin()

    def on_enter_awaiting_measured_power_W(self, *_args, **_kwargs) -> None:
        explanation = explain_field(
            "measured_power_W", _IEC60825_1_MEASURED_POWER_INFO["question"],
            _IEC60825_1_MEASURED_POWER_INFO["citation"], _IEC60825_1_MEASURED_POWER_INFO["example"],
        )
        self.set_explanation(explanation)
        self.emit_event(field="measured_power_W", message=explanation.message)
        self.update_detail(waiting_on="measured_power_W")

    def _provide_measured_power_W(self, value: Any) -> None:
        checked_scalar(value, POWER, name="measured_power_W")
        self._measured_power_W_raw = value

    def on_enter_awaiting_wavelength_nm(self, *_args, **_kwargs) -> None:
        explanation = explain_field(
            "wavelength_nm", _IEC60825_1_WAVELENGTH_INFO["question"],
            _IEC60825_1_WAVELENGTH_INFO["citation"], _IEC60825_1_WAVELENGTH_INFO["example"],
        )
        self.set_explanation(explanation)
        self.emit_event(field="wavelength_nm", message=explanation.message)
        self.update_detail(waiting_on="wavelength_nm")

    def _provide_wavelength_nm(self, value: Any) -> None:
        checked_scalar(value, "nm", name="wavelength_nm")
        self._wavelength_nm_raw = value

    def on_enter_awaiting_alpha_rad_provided(self, *_args, **_kwargs) -> None:
        explanation = explain_field(
            "alpha_rad_provided", _IEC60825_1_ALPHA_RAD_INFO["question"],
            _IEC60825_1_ALPHA_RAD_INFO["citation"], _IEC60825_1_ALPHA_RAD_INFO["example"],
        )
        self.set_explanation(explanation)
        self.emit_event(field="alpha_rad_provided", message=explanation.message)
        self.update_detail(waiting_on="alpha_rad_provided")

    def _provide_alpha_rad_provided(self, flag: Any) -> None:
        if not isinstance(flag, bool):
            raise ValueError(f"alpha_rad_provided must be a bool, got {type(flag).__name__}: {flag!r}")
        self._alpha_rad_provided = flag

    def on_enter_awaiting_alpha_rad_value(self, *_args, **_kwargs) -> None:
        if not self._alpha_rad_provided:
            self.emit_event(
                field="alpha_rad_value",
                message="alpha_rad: using IEC 60825-1's own small-source default",
            )
            self._advance()
            return
        explanation = explain_field(
            "alpha_rad", _IEC60825_1_ALPHA_RAD_VALUE_INFO["question"],
            _IEC60825_1_ALPHA_RAD_VALUE_INFO["citation"], _IEC60825_1_ALPHA_RAD_VALUE_INFO["example"],
        )
        self.set_explanation(explanation)
        self.emit_event(field="alpha_rad_value", message=explanation.message)
        self.update_detail(waiting_on="alpha_rad_value")

    def _provide_alpha_rad_value(self, value: Any) -> None:
        checked_scalar(value, ANGLE, name="alpha_rad")
        self._alpha_rad_raw = value

    def on_enter_awaiting_duration_s_class1_provided(self, *_args, **_kwargs) -> None:
        explanation = explain_field(
            "duration_s_class1_provided", _IEC60825_1_DURATION_PROVIDED_INFO["question"],
            _IEC60825_1_DURATION_PROVIDED_INFO["citation"], _IEC60825_1_DURATION_PROVIDED_INFO["example"],
        )
        self.set_explanation(explanation)
        self.emit_event(field="duration_s_class1_provided", message=explanation.message)
        self.update_detail(waiting_on="duration_s_class1_provided")

    def _provide_duration_s_class1_provided(self, flag: Any) -> None:
        if not isinstance(flag, bool):
            raise ValueError(
                f"duration_s_class1_provided must be a bool, got {type(flag).__name__}: {flag!r}"
            )
        self._duration_provided = flag

    def on_enter_awaiting_duration_s_class1_value(self, *_args, **_kwargs) -> None:
        if not self._duration_provided:
            self.emit_event(
                field="duration_s_class1_value",
                message="duration_s_class1: using IEC 60825-1's own standard-mandated time base (C-EYE-02)",
            )
            self._advance()
            return
        explanation = explain_field(
            "duration_s_class1", _IEC60825_1_DURATION_VALUE_INFO["question"],
            _IEC60825_1_DURATION_VALUE_INFO["citation"], _IEC60825_1_DURATION_VALUE_INFO["example"],
        )
        self.set_explanation(explanation)
        self.emit_event(field="duration_s_class1_value", message=explanation.message)
        self.update_detail(waiting_on="duration_s_class1_value")

    def _provide_duration_s_class1_value(self, value: Any) -> None:
        checked_scalar(value, TIME, name="duration_s_class1")
        self._duration_raw = value

    def on_enter_ready(self, *_args, **_kwargs) -> None:
        payload: Dict[str, Any] = {
            "measured_power_W": self._measured_power_W_raw,
            "wavelength_nm": self._wavelength_nm_raw,
        }
        if self._alpha_rad_provided:
            payload["alpha_rad"] = self._alpha_rad_raw
        if self._duration_provided:
            payload["duration_s_class1"] = self._duration_raw
        self.emit_event(message="payload assembled, launching IEC60825_1ClassificationFlow")
        classification_flow = IEC60825_1ClassificationFlow(
            base_dir=self.classification_base_dir, render_svg=self._render_svg_enabled,
        )
        classification_flow.submit_input(payload)
        self.launched_run_id = classification_flow.run_id
        self.launched_result = classification_flow.result
        self._advance()

    def on_enter_done(self, *_args, **_kwargs) -> None:
        result = {"launched_run_id": self.launched_run_id, "launched_result": self.launched_result}
        self.finish(result)
        self.emit_event(
            message=f"done: launched classification run {self.launched_run_id}, "
                    f"result={self.launched_result}",
            **result,
        )
