"""
Python-specific module: explain-yourself capability for FSM states

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
PYTHON-SPECIFIC MODULE: explanations
===============================================================================
Three small records, one shared idea: a person or an AI assistant who does
not know the safety standards should be able to check what a
classification step just did, or understand what an intake step is asking
for, from one self-contained message -- without reading this codebase's
source.

`ComparisonExplanation`: one measured-value-versus-limit comparison,
written out in full. The limit itself (`eye_safety.LimitResult`) already
records where it came from -- the equation, the hazard region, the time
regime. This record adds the comparison against the measured value: both
numbers, both units, the comparison made, the verdict, and a citation.

    [KD4: writing the comparison out in full, rather than only its verdict,
    is what surfaced a unit on one limit that contradicted the standard's
    own table -- invisible while only the bare numbers were compared.]

**Guardrail, non-negotiable**: this module never decides anything.
`classify_measurement` (both standards) remains the only thing that
decides a run's classification; this module's `verdict` is asserted in
tests to agree with what that decision implies -- see `C-EYE-05`.

`FieldExplanation`: the intake flow's counterpart. Not a comparison but a
question a caller needs answered before a run can begin: what is being
asked, why it matters (a citation, the same shape as above), and a worked
example in the expected unit.

`MarginSummary` / `summarize_margins`: which of the criteria that passed
came closest to failing. `ComparisonExplanation` carries a `margin_ratio`
(measured over threshold -- dimensionless, so comparable across hazards
whose units differ); `summarize_margins` reduces a set of them to the
tightest one. Each classification flow has a `summarize_margins` state
that builds this from the run's own recorded events, just before `done`,
so that nobody has to work it out from the log by hand.

All three are reached through one method, `ObservableFlow.
explain_current_state()` (`flow_base.py`): one question -- "what are you
doing or asking right now?" -- whichever of this package's flows is asked.

    [KD10: every step of a classification is a box in a fixed diagram, and
    each box can explain itself. This module is what the boxes say.]
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from ..eye_safety.result import LimitResult


@dataclass
class ComparisonExplanation:
    """One measured-value-vs-threshold comparison, self-contained enough
    for an independent reader to verify without already knowing the
    standard.

    Args:
        measured_value: The measured value being checked, in `measured_unit`.
        measured_unit: Unit string for `measured_value`.
        threshold_value: The limit it was compared against, in `threshold_unit`.
        threshold_unit: Unit string for `threshold_value` (`LimitResult.unit`).
        comparator: The comparison performed -- always `"<="` in this
            package (both standards' `classify_measurement` compare a
            measured value against a limit uniformly this way).
        verdict: Whether the comparison passed.
        margin_ratio: `measured_value / threshold_value` -- dimensionless
            by construction (both are already in the same unit family),
            so it is comparable across hazards even though their units
            differ (W/m^2 vs W/(m^2*sr)). `1.0` is exactly at the limit;
            `< 1.0` is headroom remaining; `> 1.0` is already failing, by
            that fraction over. This is what `summarize_margins` ranks.
        citation: Where `threshold_value` comes from (equation + region +
            time regime), assembled from the `LimitResult` that produced it.
        message: A rendered, human-readable sentence combining all of the above.
    """

    measured_value: float
    measured_unit: str
    threshold_value: float
    threshold_unit: str
    comparator: str
    verdict: bool
    margin_ratio: float
    citation: str
    message: str


def explain_comparison(
    measured_value: float, measured_unit: str, limit: LimitResult, *, comparator: str = "<=",
) -> ComparisonExplanation:
    """Build a `ComparisonExplanation` from a measured value and the
    `LimitResult` it is being checked against.

    Args:
        measured_value: The measured value, already in `measured_unit`.
            The flow's `validate_dimensions` state reduced it to a plain
            float in the expected SI unit before any `eval_*` state runs
            [KA9: every input is checked at the boundary, once]; this
            function does no unit conversion itself.
        measured_unit: Unit string for `measured_value` -- expected to
            match `limit.unit` (both standards' `classify_measurement`
            never compares across mismatched units; if they ever
            disagreed here that would itself be a bug this function's
            caller should surface, not silently paper over).
        limit: The `LimitResult` just computed for this hazard/group (or
            AEL class).
        comparator: Only `"<="` is supported -- the one comparison both
            standards' `classify_measurement` ever performs.

    Returns:
        A `ComparisonExplanation` with `verdict`, `margin_ratio`, and a
        rendered `message`.

    Raises:
        ValueError: If `comparator` is not `"<="`.
    """
    if comparator != "<=":
        raise ValueError(
            f"explain_comparison only supports comparator '<=' (the one "
            f"comparison both classify_measurement implementations ever "
            f"perform); got {comparator!r}."
        )
    verdict = measured_value <= limit.value
    margin_ratio = measured_value / limit.value
    citation = f"{limit.equation} ({limit.region}, {limit.time_regime})"
    if margin_ratio <= 1.0:
        margin_note = f"{(1.0 - margin_ratio) * 100.0:.1f}% headroom"
    else:
        margin_note = f"exceeds by {(margin_ratio - 1.0) * 100.0:.1f}%"
    message = (
        f"{measured_value:.6g} {measured_unit} {comparator} "
        f"{limit.value:.6g} {limit.unit} [{citation}] -> "
        f"{'pass' if verdict else 'FAIL'} ({margin_note})"
    )
    return ComparisonExplanation(
        measured_value=measured_value, measured_unit=measured_unit,
        threshold_value=limit.value, threshold_unit=limit.unit,
        comparator=comparator, verdict=verdict, margin_ratio=margin_ratio,
        citation=citation, message=message,
    )


@dataclass
class MarginSummary:
    """Which criterion, among a set of `ComparisonExplanation`s, came
    closest to failing -- answering "how much headroom did we actually
    have" without a person or an assistant having to diff the event log
    by hand.

    Args:
        scope: What this summary is *of* -- a risk group (IEC 62471,
            e.g. `"Exempt"`) or a classification outcome (IEC 60825-1,
            e.g. `"Class 2 or 2M"`).
        tightest_criterion: The hazard/AEL-class key with the highest
            `margin_ratio` in `margins` (closest to, or already over, its
            limit), or `None` if `margins` is empty (nothing applicable
            was checked in this scope).
        tightest_margin_ratio: That criterion's own `margin_ratio`.
        margins: Every criterion's `margin_ratio` considered for this
            summary, not just the tightest one -- the full table, for a
            caller who wants more than the headline.
        message: A rendered sentence naming the tightest criterion and
            its headroom (or excess), or a fallback noting nothing was
            applicable.
    """

    scope: str
    tightest_criterion: Optional[str]
    tightest_margin_ratio: Optional[float]
    margins: Dict[str, float]
    message: str


def summarize_margins(scope: str, margins: Dict[str, float]) -> MarginSummary:
    """Build a `MarginSummary` from a `{criterion: margin_ratio}` table.

    Args:
        scope: See `MarginSummary.scope`.
        margins: `{criterion_key: margin_ratio}` -- the set of
            `ComparisonExplanation.margin_ratio` values to summarize
            (typically: every applicable hazard checked against the
            *winning* risk group, for IEC 62471; the single AEL class a
            source was actually classified into, for IEC 60825-1).

    Returns:
        A `MarginSummary` -- `tightest_criterion`/`tightest_margin_ratio`
        are `None` and `message` says so if `margins` is empty.
    """
    if not margins:
        return MarginSummary(
            scope=scope, tightest_criterion=None, tightest_margin_ratio=None,
            margins={}, message=f"no applicable criteria were checked for {scope}",
        )
    tightest_criterion, tightest_ratio = max(margins.items(), key=lambda kv: kv[1])
    if tightest_ratio <= 1.0:
        detail = f"at {tightest_ratio:.1%} of its limit ({(1.0 - tightest_ratio) * 100.0:.1f}% headroom)"
    else:
        detail = f"exceeds its limit by {(tightest_ratio - 1.0) * 100.0:.1f}%"
    if len(margins) == 1:
        message = f"{scope}: {tightest_criterion} {detail}"
    else:
        message = f"tightest criterion for {scope}: {tightest_criterion} {detail}"
    return MarginSummary(
        scope=scope, tightest_criterion=tightest_criterion, tightest_margin_ratio=tightest_ratio,
        margins=dict(margins), message=message,
    )


@dataclass
class FieldExplanation:
    """One intake question, self-contained enough for a caller who does
    not already know the standard to answer correctly.

    Args:
        field: The payload field this question fills (e.g. `"alpha_rad"`).
        question: The plain-language question being asked.
        citation: Why this field matters (a standard section/boundary, or
            which downstream dispatch it feeds).
        example: A worked example value in the expected unit.
        message: A rendered sentence combining all of the above.
    """

    field: str
    question: str
    citation: str
    example: str
    message: str


def explain_field(field: str, question: str, citation: str, example: str) -> FieldExplanation:
    """Build a `FieldExplanation` for one intake field."""
    message = f"{question} ({citation}) {example}"
    return FieldExplanation(
        field=field, question=question, citation=citation, example=example, message=message,
    )
