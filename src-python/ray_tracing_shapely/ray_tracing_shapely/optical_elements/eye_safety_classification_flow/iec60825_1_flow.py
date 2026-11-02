"""
Python-specific module: IEC 60825-1 classification flow

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
PYTHON-SPECIFIC MODULE: IEC 60825-1 classification flow
===============================================================================
Wraps (does not re-implement) `eye_safety.iec60825_1.classify_measurement`:
a short ascending AEL ladder, not a per-band gather -- see
dev_doc/architecture/components/eye_safety_classification_flow.md for why this state shape
differs from IEC 62471's (iec62471_flow.py).

    start -> frame_input -> validate_dimensions -> eval_class_1 -> eval_class_2 -> eval_class_3r -> summarize_margins -> done

`eval_class_2` is visited as a state for every input (one static diagram
[KD10: a diagram that varies with its input is a diagram nobody can
check]), but is skipped -- an event recorded, no
`ael_class_2` call made -- for a `wavelength_nm` outside `ael_class_2`'s
own `[400, 700)` visible-range domain (`iec60825_1.py:597-601`), rather
than letting that call raise.

`eval_class_1`/`eval_class_2`/`eval_class_3r` each call the *same* pure
AEL function `classify_measurement` itself calls internally, purely for
observability (the resulting LimitResult, not a pass/fail decision) --
no duplicated comparison logic exists here to drift from the function
being wrapped. `done` calls `classify_measurement` exactly once, unchanged,
and that string is the only thing `C-EYE-05`'s parity guarantee is about.

Each of those three states also builds a `ComparisonExplanation`
(`explanations.py`) against `measured_power_W` -- a self-contained
"measured X W <= AEL Y W [citation] -> pass/fail" record, not just the
bare `LimitResult`, so a reader without deep standard knowledge can
verify the run independently [KD4: the full comparison, not just the
verdict]. A global `reset` (`source: "*"`)
lands back at `start` from any state, including `done` -- see
`flow_base.py`'s module docstring for the shared bookkeeping. A
`summarize_margins` state, right before `done`, reports the margin
(`ComparisonExplanation.margin_ratio`) of whichever AEL class the source
was actually classified into -- "how close did this classification come
to needing the next class" -- computed from this run's own already-
recorded events, not a re-decision.
===============================================================================
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional

from . import persistence
from .flow_base import ObservableFlow
from .dimensional_checks import checked_scalar
from .explanations import explain_comparison, summarize_margins
from ..eye_safety import iec60825_1
from ..eye_safety.angular_subtense import ALPHA_MIN_IEC60825_1_RAD
from ..units import POWER, TIME, ANGLE

IEC60825_1_STATES = [
    "start",
    "frame_input",
    "validate_dimensions",
    "eval_class_1",
    "eval_class_2",
    "eval_class_3r",
    "summarize_margins",
    "done",
]

#: classify_measurement's own result strings -> the ael_class key
#: (the event field) whose ComparisonExplanation decided it --
#: "above Class 3R" has no class of its own, so class_3r's own (failing)
#: margin is the most informative one available.
_RESULT_TO_AEL_CLASS = {
    "Class 1 or 1M": "class_1_1m",
    "Class 2 or 2M": "class_2_2m",
    "Class 3R": "class_3r",
    "above Class 3R (3B or 4)": "class_3r",
}

IEC60825_1_TRANSITIONS = [
    {"trigger": "begin", "source": "start", "dest": "frame_input"},
    {"trigger": "submit_input", "source": "frame_input", "dest": "validate_dimensions",
     "before": "_validate_and_store_payload"},
    {"trigger": "_advance", "source": "validate_dimensions", "dest": "eval_class_1"},
    {"trigger": "_advance", "source": "eval_class_1", "dest": "eval_class_2"},
    {"trigger": "_advance", "source": "eval_class_2", "dest": "eval_class_3r"},
    {"trigger": "_advance", "source": "eval_class_3r", "dest": "summarize_margins"},
    {"trigger": "_advance", "source": "summarize_margins", "dest": "done"},
    {"trigger": "reset", "source": "*", "dest": "start", "before": "_on_reset"},
]

IEC60825_1_TERMINAL_STATES = ("done",)

#: ael_class_2's own visible-range domain (iec60825_1.py:597-601) -- the
#: concrete source of eval_class_2's "skipped state".
_CLASS_2_VISIBLE_RANGE_NM = (400.0, 700.0)


class IEC60825_1ClassificationFlow(ObservableFlow):
    """One instance per classification run. Construct, then call
    `submit_input(payload)` once; the run completes synchronously and
    `self.result` holds the final class string."""

    def __init__(
        self, base_dir: Path, run_id: Optional[str] = None, render_svg: bool = True,
    ) -> None:
        super().__init__(
            name="iec60825_1", states=IEC60825_1_STATES,
            transitions_list=IEC60825_1_TRANSITIONS, initial="start",
            base_dir=base_dir, run_id=run_id, render_svg=render_svg,
        )
        self.payload: Optional[Dict[str, Any]] = None
        self.result: Optional[str] = None
        self.begin()

    def _validate_and_store_payload(self, payload: Dict[str, Any]) -> None:
        """FRAME_INPUT's validation -- see iec62471_flow.py's own docstring
        for the same "validates rather than decides" principle, and for
        the "mandatory, not opt-in" rule. `duration_s_class1` stays
        optional, matching `classify_measurement`'s own default (`None`
        resolving to the standard-mandated time base per C-EYE-02) --
        *omitting* a field is still fine; *stating* one without units is
        not. `alpha_rad` is also optional (defaults to
        `ALPHA_MIN_IEC60825_1_RAD`, matching `classify_measurement`'s own
        default) for the same reason.

        `measured_power_W`/`wavelength_nm` are required and must
        each be a `pint.Quantity`/Pint-formatted string; `alpha_rad`/
        `duration_s_class1`, if given at all (not omitted), must be too.
        Pint's default registry treats radian as dimensionless, so a
        Quantity check on `alpha_rad` cannot distinguish radians from a
        solid angle or a bare number (see `dimensional_checks.py`'s module
        docstring) -- required anyway, for consistency with every other
        field here and because it still catches a wildly wrong type (a
        length, say) and gives free unit conversion (e.g. `"30 deg"`).
        """
        if payload.get("measured_power_W") is None:
            raise ValueError("FRAME_INPUT payload must include 'measured_power_W'.")
        measured_power_W = checked_scalar(
            payload["measured_power_W"], POWER, name="measured_power_W",
        )
        if measured_power_W < 0.0:
            raise ValueError("measured_power_W must be non-negative.")

        if payload.get("wavelength_nm") is None:
            raise ValueError("FRAME_INPUT payload must include 'wavelength_nm'.")
        # LENGTH's SI base unit is "m" -- wavelength_nm stays expressed in nm
        # downstream (every eye_safety function takes nanometres), so convert
        # via the nm-specific unit string, not LENGTH's own metre default.
        wavelength_nm = checked_scalar(payload["wavelength_nm"], "nm", name="wavelength_nm")

        if "alpha_rad" not in payload:
            alpha_rad = ALPHA_MIN_IEC60825_1_RAD
        else:
            alpha_rad = checked_scalar(payload["alpha_rad"], ANGLE, name="alpha_rad")

        raw_duration = payload.get("duration_s_class1")
        if raw_duration is None:
            duration_s_class1 = None
        else:
            duration_s_class1 = checked_scalar(raw_duration, TIME, name="duration_s_class1")

        self.payload = {
            "measured_power_W": measured_power_W,
            "wavelength_nm": wavelength_nm,
            "alpha_rad": alpha_rad,
            "duration_s_class1": duration_s_class1,
        }
        persistence.write_inputs(self.base_dir, self.run_id, self.payload)

    def on_enter_validate_dimensions(self, *_args, **_kwargs) -> None:
        """The dimensional check's own dedicated FSM step -- see
        `iec62471_flow.py`'s own `on_enter_validate_dimensions` for the
        full rationale (identical here: by the time this runs, every
        physical value has already been checked and converted by the
        `before` callback on the transition into this state)."""
        self.emit_event(
            message="dimensions validated: measured_power_W, wavelength_nm, "
                    "alpha_rad confirmed dimensionally consistent",
        )
        self._advance()

    def on_enter_eval_class_1(self, *_args, **_kwargs) -> None:
        result = iec60825_1.ael_class_1(
            self.payload["wavelength_nm"], self.payload["duration_s_class1"],
            self.payload["alpha_rad"],
        )
        explanation = explain_comparison(self.payload["measured_power_W"], "W", result)
        self.set_explanation(explanation)
        self.emit_event(
            ael_class="class_1_1m", result=asdict(result), comparison=asdict(explanation),
            message=explanation.message,
        )
        self._advance()

    def on_enter_eval_class_2(self, *_args, **_kwargs) -> None:
        wavelength_nm = self.payload["wavelength_nm"]
        lo, hi = _CLASS_2_VISIBLE_RANGE_NM
        if lo <= wavelength_nm < hi:
            result = iec60825_1.ael_class_2(wavelength_nm, self.payload["alpha_rad"])
            explanation = explain_comparison(self.payload["measured_power_W"], "W", result)
            self.set_explanation(explanation)
            self.emit_event(
                ael_class="class_2_2m", result=asdict(result), comparison=asdict(explanation),
                message=explanation.message,
            )
        else:
            self.emit_event(
                ael_class="class_2_2m", result=None,
                message=f"Class 2/2M: skipped, {wavelength_nm} nm is outside "
                        f"the visible range {_CLASS_2_VISIBLE_RANGE_NM}",
            )
        self._advance()

    def on_enter_eval_class_3r(self, *_args, **_kwargs) -> None:
        result = iec60825_1.ael_class_3r(
            self.payload["wavelength_nm"], self.payload["duration_s_class1"],
            self.payload["alpha_rad"],
        )
        explanation = explain_comparison(self.payload["measured_power_W"], "W", result)
        self.set_explanation(explanation)
        self.emit_event(
            ael_class="class_3r", result=asdict(result), comparison=asdict(explanation),
            message=explanation.message,
        )
        self._advance()

    def on_enter_summarize_margins(self, *_args, **_kwargs) -> None:
        """Reports the margin of whichever AEL class the source
        was actually classified into -- "how close did this classification
        come to needing the next class." `classify_measurement` is called
        here, exactly once (the same single call `C-EYE-05` requires,
        relocated from `on_enter_done` so `self.result` is known before
        this state needs to pick which class's own `ComparisonExplanation`
        to summarize); `on_enter_done` below only finishes the run with
        the result already decided here.
        """
        classification = iec60825_1.classify_measurement(
            self.payload["measured_power_W"], self.payload["wavelength_nm"],
            self.payload["alpha_rad"], self.payload["duration_s_class1"],
        )
        self.result = classification

        events = persistence.read_events(self.base_dir, self.run_id)
        margins: Dict[str, float] = {}
        for e in events:
            if "comparison" in e and "ael_class" in e:
                margins[e["ael_class"]] = e["comparison"]["margin_ratio"]
        winning_class = _RESULT_TO_AEL_CLASS.get(classification)
        scope_margins = {winning_class: margins[winning_class]} if winning_class in margins else {}
        summary = summarize_margins(classification, scope_margins)
        self.set_explanation(summary)
        self.emit_event(
            classification=classification, winning_ael_class=winning_class,
            margins_by_class=margins, tightest_criterion=summary.tightest_criterion,
            tightest_margin_ratio=summary.tightest_margin_ratio,
            message=summary.message,
        )
        self._advance()

    def on_enter_done(self, *_args, **_kwargs) -> None:
        self.finish(self.result)
        self.emit_event(message=f"classification: {self.result}", result=self.result)
