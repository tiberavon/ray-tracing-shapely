"""
Python-specific module: ObservableFlow -- the FSM wrapper

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
PYTHON-SPECIFIC MODULE: flow_base (ObservableFlow)
===============================================================================
Adapted, not copied wholesale, from a working prior implementation in a
sibling project (an unrelated LLM-classification community monitor,
`zm_monitor/fsm_base.py`'s `ObservableFSM`) -- see
dev_doc/architecture/components/eye_safety_classification_flow.md for the
verification that its exact `GraphMachine(..., graph_engine="graphviz",
after_state_change=...)` constructor call runs against this project's own
installed `transitions`/Graphviz.

One instance per *run* (a whole classify_measurement assessment), not per
hazard -- `states`/`transitions_list` are supplied by the caller (see
iec62471_flow.py/iec60825_1_flow.py), so "two FSMs" means two module-level
tables passed into this one generic wrapper, not two wrapper classes.

Two separate concerns, deliberately not conflated:
- `_on_transition` (the `after_state_change` hook): generic infrastructure
  that fires on every transition regardless of which state -- writes the
  heartbeat (`persistence.update_heartbeat`) and re-renders `state.svg`.
  Degrades gracefully if `dot` is missing (a one-time warning, not a
  per-transition one -- "a missing dot binary is an environment fact, not
  a per-call error worth repeating," in zm_monitor's own words); a
  classification run must never fail, or even change its actual output,
  because Graphviz isn't installed on the machine it happened to run on.
- `emit_event` (called explicitly from each state's own `on_enter_<state>`
  method, defined in the per-standard subclasses): the rich, domain-
  specific content for that state -- which hazard, what LimitResult, what
  message -- appended to `events.jsonl`. This is what makes a run
  auditable after the fact, not just "alive right now" (which the
  heartbeat alone answers).

**A shared global `reset`.** Every per-standard transition
table (`iec62471_flow.py`/`iec60825_1_flow.py`/`intake_flow.py`) adds its
own `{"trigger": "reset", "source": "*", "dest": "start", "before":
"_on_reset"}` entry -- `transitions` supports a wildcard `source`,
verified directly against this project's own installed version, firing
correctly from a mid-flow state *and* from a terminal one. The bookkeeping
that entry needs (`self.attempt`, an event marking the reset, clearing
per-attempt `detail`) lives here, once, rather than duplicated in three
transition tables. An evaluator that sees the results heading the wrong
way can reset the flow and restart with different parameters -- one run,
not a fresh run per attempt; `events.jsonl` (already append-only) accumulates every
attempt, tagged by `self.attempt`, and `result.json` always reflects the
*latest* attempt's outcome.

**A shared explain-yourself surface.** [KD10: every box in the fixed
diagram can say what it is doing or asking.] `set_explanation`/
`explain_current_state` let a caller ask "what did this state just do, or
what is it asking for?" the same way regardless of which FSM it's
talking to -- a classification `eval_*` state's `ComparisonExplanation`
and an intake `awaiting_<field>` state's `FieldExplanation`
(`explanations.py`) are both just objects with a `.message`; this class
only needs to remember the most recent one.
===============================================================================
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from transitions import Machine
from transitions.extensions import GraphMachine

from . import persistence

#: Printed once, not once per transition -- see module docstring.
_warned_no_graphviz = False


class ObservableFlow:
    """Wraps a `transitions.extensions.GraphMachine`: every transition (a)
    writes a heartbeat so a dashboard process can see current state
    without a live connection to this process, and (b) re-renders an SVG
    snapshot with the active state highlighted. Domain content per state
    is recorded separately via `emit_event`, called from each state's own
    `on_enter_<state>` method in a per-standard subclass.

    Args:
        name: The FSM's name (e.g. "iec62471", "iec60825_1") -- also the
            `state.svg` filename stem and the `run_id` prefix.
        states: A `transitions`-style state list.
        transitions_list: A `transitions`-style transition list.
        initial: The initial state name.
        base_dir: Where `P-CLASSIFICATION-RUN`'s run directories and
            top-level `manifest.jsonl`/`heartbeats.json` live.
        run_id: Explicit run id, or None to generate one via
            `persistence.make_run_id(name)`.
        render_svg: If True (default), use `GraphMachine` and re-render
            `state.svg` on every transition. If False, use plain
            `transitions.Machine` -- no Graphviz involvement at all, not
            even the graceful-degradation path. FSM transition-logic tests (state sequence, the
            C-EYE-05 parity check) should run everywhere, fast, with zero
            Graphviz dependency -- each `dot` subprocess invocation costs
            real wall-clock time (confirmed: ~0.8s/transition in this
            environment), which a 9-transition run cannot hide from a test
            suite that constructs many runs. Production callers that want
            the live diagram leave this at the default.
    """

    def __init__(
        self,
        name: str,
        states: List[Any],
        transitions_list: List[Dict[str, Any]],
        initial: str,
        base_dir: Path,
        run_id: Optional[str] = None,
        render_svg: bool = True,
    ) -> None:
        self.name = name
        self.base_dir = Path(base_dir)
        self.run_id = run_id or persistence.make_run_id(name)
        self.detail: Dict[str, Any] = {}
        self._started_at = time.time()
        self._render_svg_enabled = render_svg
        self.attempt = 1
        self._current_explanation: Optional[Any] = None

        machine_cls = GraphMachine if render_svg else Machine
        machine_kwargs: Dict[str, Any] = dict(
            model=self,
            states=states,
            transitions=transitions_list,
            initial=initial,
            after_state_change="_on_transition",
        )
        if render_svg:
            machine_kwargs.update(graph_engine="graphviz", title=name)
        self.machine = machine_cls(**machine_kwargs)

        persistence.append_manifest(
            self.base_dir, self.run_id, standard=name, started_at=self._started_at,
        )
        self._on_transition()  # persist + render the initial state too

    # -------------------------------------------------------------------
    # Infrastructure: heartbeat + SVG, on every transition
    # -------------------------------------------------------------------

    def _on_transition(self, *_args: Any, **_kwargs: Any) -> None:
        # `transitions` forwards a trigger call's own args/kwargs to every
        # callback in that transition (before/after/on_enter/on_exit)
        # uniformly, not just the one that declared them (e.g.
        # `submit_input(payload)`'s `payload` also reaches this
        # `after_state_change` hook) -- accepted and ignored here rather
        # than switching the whole machine to `send_event=True`, which
        # would ripple into every on_enter_<state> signature for no
        # benefit this class needs.
        persistence.update_heartbeat(
            self.base_dir, self.run_id, fsm_name=self.name,
            state=self.state, detail=self.detail,
        )
        if self._render_svg_enabled:
            self._render_svg()

    def _render_svg(self) -> None:
        global _warned_no_graphviz
        try:
            svg_path = persistence.run_dir(self.base_dir, self.run_id) / "state.svg"
            self.machine.get_graph().draw(str(svg_path), format="svg", prog="dot")
        except Exception as e:  # noqa: BLE001 -- see module docstring
            if not _warned_no_graphviz:
                print(
                    f"  [flow] WARN: could not render {self.name} diagram ({e}) -- "
                    f"install Graphviz (the `dot` executable, not just `pip install "
                    f"graphviz`) for live diagrams; heartbeat/event tracking still "
                    f"works without it."
                )
                _warned_no_graphviz = True

    def update_detail(self, **kwargs: Any) -> None:
        """Update per-run detail (e.g. "waiting on: alpha_rad") without a
        state transition, and write a fresh heartbeat -- what makes a
        long wait in FRAME_INPUT visibly "still alive" rather than
        indistinguishable from a stuck process."""
        self.detail.update(kwargs)
        self._on_transition()

    # -------------------------------------------------------------------
    # Domain content: one call per completed state, from on_enter_<state>
    # -------------------------------------------------------------------

    def emit_event(self, **kwargs: Any) -> int:
        """Append one event to `events.jsonl` for the current state.
        `kwargs` becomes the event's own fields (e.g. `hazard=`,
        `applicable=`, `result=`, `message=`) alongside the auto-assigned
        `seq`/`timestamp`, this call's `state=self.state`, and
        `attempt=self.attempt`, so a reader can group a run's events by
        attempt after one or more `reset()` calls."""
        return persistence.append_event(
            self.base_dir, self.run_id,
            {"state": self.state, "attempt": self.attempt, **kwargs},
        )

    def finish(self, result: Any) -> None:
        """Write `result.json`, append the final manifest row, and leave a
        last heartbeat -- called once, from the terminal state's own
        `on_enter_done`. `result.json` always reflects the *latest*
        attempt -- the full history across every attempt lives
        in `events.jsonl`, already append-only."""
        persistence.write_result(
            self.base_dir, self.run_id,
            {"result": result, "attempt": self.attempt, "wall_clock_s": time.time() - self._started_at},
        )
        persistence.append_manifest(
            self.base_dir, self.run_id, standard=self.name,
            started_at=self._started_at, finished_at=time.time(), result=result,
        )

    # -------------------------------------------------------------------
    # A shared global reset
    # -------------------------------------------------------------------

    def _on_reset(self, *_args: Any, **_kwargs: Any) -> None:
        """Shared `before` callback for every flow's global `reset`
        transition -- see module docstring. Runs *before* the transition
        to `start`, so `emit_event` here still tags the event with
        whichever state `reset()` was called from."""
        self.emit_event(
            message=f"reset: abandoning attempt {self.attempt}, "
                    f"starting attempt {self.attempt + 1}",
        )
        self.attempt += 1
        self.detail = {}
        self._current_explanation = None

    # -------------------------------------------------------------------
    # A shared explain-yourself surface
    # -------------------------------------------------------------------

    def set_explanation(self, explanation: Any) -> None:
        """Record the current state's explanation -- a
        `ComparisonExplanation` or `FieldExplanation` (`explanations.py`),
        or any object with a `.message` attribute -- so
        `explain_current_state` can answer "what are you doing/asking
        right now?" uniformly across every FSM this class backs."""
        self._current_explanation = explanation

    def explain_current_state(self) -> str:
        """What this state just did, or is currently asking for --
        the shared explain-yourself capability, for a caller (human or
        agent) without deep knowledge of the standard.
        Returns the most recent `set_explanation` call's `.message`, or a
        fallback noting none was recorded for the current state (e.g.
        `start`/`done`, which have nothing to explain)."""
        if self._current_explanation is None:
            return f"{self.state}: no explanation recorded for this state."
        return self._current_explanation.message


def graphviz_available() -> bool:
    """Whether the `dot` executable is on `PATH` -- used to skip
    SVG-content assertions in tests on a machine without Graphviz
    installed; production code degrades
    gracefully instead (see `ObservableFlow._render_svg`)."""
    return shutil.which("dot") is not None
