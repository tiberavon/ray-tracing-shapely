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
dev_doc/architecture/components/flows.md for the
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

**Fixed ends, and long steps.** Besides its own end (`done`), every flow has
three more, added to its diagram here so that no table repeats them:
`failed` (a step or its job raised; the traceback is an event), `cancelled`
and `timed_out` (a job's hard limit passed). A run ends in one of these, or
the run list (`runs.list_runs`) says why it has not. A long box hands its work
to an executor (`submit_step`), or several side by side (`submit_group`, followed
as one step), and keeps the handle in the heartbeat; `poll` follows the handle,
`wait` polls until the job ends or the timeout. Nothing
here looks for the work in the process list.

**Questions as data.** A box that asks a question has a `FlowField` (the
class's `FIELDS`, by state): the kind of answer, its unit, its default, the
question and why it is asked. `pending_field()` is the current one; `answer
(value)` fires the box's own `provide_*` trigger, found from the machine, so
a caller needs one verb, not a method name per question. A refused answer
leaves the flow where it is, and is recorded as an event and as
`last_refusal`, with its reason.

**A shared explain-yourself surface.** [KD10: every box in the fixed
diagram can say what it is doing or asking.] `set_explanation`/
`explain_current_state` let a caller ask "what did this state just do, or
what is it asking for?" the same way regardless of which FSM it's
talking to -- a classification `eval_*` state's `ComparisonExplanation`
and an intake `awaiting_<field>` state's `FieldExplanation`
(`eye_safety_classification_flow/explanations.py`, `flows/fields.py`) are both just objects with a `.message`; this class
only needs to remember the most recent one.
===============================================================================
"""

from __future__ import annotations

import shutil
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from transitions import Machine
from transitions.extensions import GraphMachine

from . import persistence, runs
from .budgets import ASK_OVER_S, format_duration
from .executors import Handle, Job, executor_for
from .fields import FlowField

#: The ends every flow has besides its own: added to each diagram by
#: `ObservableFlow`, reachable from any box through the `to_<state>` triggers.
FAILURE_STATES = ("failed", "cancelled", "timed_out")

#: Printed once, not once per transition -- see module docstring.
_warned_no_graphviz = False


_NO_ANSWER: Any = object()


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

    #: The question each asking box puts, by state, in the order they are
    #: asked. A subclass sets it; `flow_field` may refine one per run.
    FIELDS: Dict[str, FlowField] = {}
    #: What the flow is for, in a sentence, for a list of flows.
    PURPOSE: str = ""

    def __init__(
        self,
        name: str,
        states: List[Any],
        transitions_list: List[Dict[str, Any]],
        initial: str,
        base_dir: Path,
        run_id: Optional[str] = None,
        render_svg: bool = True,
        terminal_states: tuple = ("done",),
    ) -> None:
        self.name = name
        #: Every state the run does not leave: the flow's own, and `FAILURE_STATES`.
        self.terminal_states = tuple(terminal_states) + tuple(
            s for s in FAILURE_STATES if s not in terminal_states)
        names = {_state_name(st) for st in states}
        states = list(states) + [st for st in FAILURE_STATES if st not in names]
        self._job: Optional[Dict[str, Any]] = None
        self._group_results: Dict[int, Any] = {}
        self.job_result: Any = None
        #: The last refused answer: field, value, reason; None after an accepted one.
        self.last_refusal: Optional[Dict[str, Any]] = None
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
        runs.track(self)

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
            state=self.state, detail=self.detail, terminal=self.is_finished,
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

    def label_experiment(self, experiment: str, case: str, expected_end: str) -> None:
        """Mark this run as one case of an experiment, and the end it is meant to reach
        (``done``, ``failed``, ``cancelled``, ``timed_out``): a run meant to fail that fails
        is a pass. The dashboard shows each experiment's cases against what they expected."""
        self.update_detail(experiment={"name": experiment, "case": case, "expected": expected_end})

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
        if self._job is not None:           # an abandoned attempt's jobs are stopped, not left running
            for i, h in enumerate(self._job.get("group") or [self._job["handle"]]):
                if i not in self._group_results or "group" not in self._job:
                    handle = Handle.from_dict(h)
                    executor_for(handle).cancel(handle)
            self._job = None
            self._group_results = {}
        self.attempt += 1
        self.detail = {}
        self._current_explanation = None
        self.job_result = None
        self.last_refusal = None

    # -------------------------------------------------------------------
    # Fixed ends
    # -------------------------------------------------------------------

    @property
    def is_finished(self) -> bool:
        """Whether the run is in a state it does not leave (until `reset`)."""
        return self.state in self.terminal_states

    def end_run(self, state: str, message: str, **fields: Any) -> None:
        """End the run in one of `FAILURE_STATES`: move there, record why as an
        event, and write `result.json` and the run log's finish row, so a run
        that did not reach `done` is still a finished record, not a silent one."""
        if state not in FAILURE_STATES:
            raise ValueError(f"end_run is for {FAILURE_STATES}; {state!r} is the flow's own to reach")
        from_state = self.state
        self._job = None
        self.detail.pop("job", None)
        getattr(self, f"to_{state}")()
        self.emit_event(message=message, from_state=from_state, **fields)
        self.set_explanation(_Note(f"{state}: {message}"))
        persistence.write_result(
            self.base_dir, self.run_id,
            {"result": None, "status": state, "reason": message, "from_state": from_state,
             "attempt": self.attempt, "wall_clock_s": time.time() - self._started_at},
        )
        persistence.append_manifest(
            self.base_dir, self.run_id, standard=self.name,
            started_at=self._started_at, finished_at=time.time(), result=state,
        )

    def fail(self, error: Any) -> None:
        """End the run as `failed`. ``error`` is an exception (its traceback is
        recorded) or a reason."""
        if isinstance(error, BaseException):
            tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
            self.end_run("failed", f"{type(error).__name__}: {error}", traceback=tb)
        else:
            self.end_run("failed", str(error))

    # -------------------------------------------------------------------
    # Questions as data: one verb to answer any box
    # -------------------------------------------------------------------

    def flow_field(self, state: str) -> Optional[FlowField]:
        """The question the box ``state`` asks, or None. Override to make a
        field depend on earlier answers (an example in the unit they imply)."""
        return self.FIELDS.get(state)

    def pending_field(self) -> Optional[FlowField]:
        """The question the flow is waiting on now, or None at a box that is
        not asking (working, following a job, finished)."""
        if self.is_finished or self._job is not None:
            return None
        return self.flow_field(self.state)

    def _answer_trigger(self) -> str:
        triggers = [t for t in self.machine.get_triggers(self.state) if t.startswith("provide_")]
        if len(triggers) != 1:
            raise RuntimeError(f"{self.name}: box {self.state!r} has {len(triggers)} provide_ triggers, "
                               f"not one: {triggers}")
        return triggers[0]

    def answer(self, value: Any = _NO_ANSWER) -> Dict[str, Any]:
        """Answer the current question.

        The value is shaped for the box (`FlowField.coerce`) and handed to the
        box's own ``provide_*`` trigger, whose check decides. A refusal (a
        ``ValueError`` or ``TypeError`` from the check, the flow still in the
        same box) is recorded as an event and as `last_refusal`. An error once
        the flow has moved on is a failure of the step that raised it: the
        run ends `failed`. Every refusal's reason ends with the field's
        example, so the reason alone says what would be accepted.

        An accepted answer after which a check sends the flow back to this
        question or an earlier one (a footprint the rays do not fit) carries
        ``sent_back``: ``{"from", "to", "reason"}``, also recorded as an event.
        The reason is `send_back_reason()`, or else the box's explanation.

        Returns:
            ``accepted``, and the flow's `question_state` after the answer; for
            a refusal, also ``reason``; for a send-back, also ``sent_back``.
        """
        field = self.pending_field()
        if field is None:
            return {"accepted": False, "reason": f"{self.state}: nothing is being asked",
                    **self.question_state()}
        if value is _NO_ANSWER:
            return {"accepted": False, "reason": _with_example(f"{field.name}: no answer given", field),
                    **self.question_state()}
        before = self.state
        try:
            shaped = field.coerce(value)
            getattr(self, self._answer_trigger())(shaped)
        except (ValueError, TypeError) as e:
            if self.state != before or self.is_finished:
                self.fail(e)
                return {"accepted": False, "reason": f"the step after {field.name} failed: {e}",
                        **self.question_state()}
            reason = _with_example(str(e), field)
            self.last_refusal = {"field": field.name, "value": _short(value), "reason": reason}
            self.emit_event(field=field.name, refused=True, reason=reason,
                            message=f"{field.name}: answer refused: {reason}")
            self.set_explanation(_Note(f"refused: {reason} -- {field.explanation().message}"))
            return {"accepted": False, "reason": reason, **self.question_state()}
        except Exception as e:  # noqa: BLE001 -- a step that raised is the run's failure, recorded
            self.fail(e)
            return {"accepted": False, "reason": f"{type(e).__name__}: {e}", **self.question_state()}
        self.last_refusal = None
        out: Dict[str, Any] = {"accepted": True}
        back = self._sent_back(before, field)
        if back is not None:
            self.emit_event(field=field.name, sent_back=True, to=back["to"], reason=back["reason"],
                            message=f"{field.name}: accepted, then sent back to {back['to']}: {back['reason']}")
            out["sent_back"] = back
        return {**out, **self.question_state()}

    def send_back_reason(self) -> Optional[str]:
        """Why a check has just sent the flow back to an earlier question, in
        the flow's own words; None to use the box's explanation. Override in a
        flow whose checks send it back."""
        return None

    def _sent_back(self, before: str, answered: FlowField) -> Optional[Dict[str, str]]:
        """``{from, to, reason}`` if the flow now asks the question it just
        had answered, or one before it in `FIELDS`; else None."""
        now = self.pending_field()
        order = list(self.FIELDS)
        if now is None or before not in order or self.state not in order:
            return None
        if order.index(self.state) > order.index(before):
            return None
        return {"from": answered.name, "to": now.name,
                "reason": self.send_back_reason() or self.explain_current_state()}

    def answer_default(self) -> Dict[str, Any]:
        """Answer the current question with its default; refused when it has none."""
        field = self.pending_field()
        if field is not None and field.required:
            return {"accepted": False,
                    "reason": _with_example(f"{field.name} has no default: it must be answered", field),
                    **self.question_state()}
        return self.answer(field.default if field is not None else _NO_ANSWER)

    def question_context(self) -> Optional[Dict[str, Any]]:
        """What the current question is answered from, as JSON (a table to
        choose from), or None. Override in a flow whose question needs it."""
        return None

    def question_state(self) -> Dict[str, Any]:
        """Where the run is, as JSON: its state, the question it waits on (or
        None) and what it is answered from, what the box says, the last
        refusal, and any job it follows."""
        field = self.pending_field()
        return {"run_id": self.run_id, "flow": self.name, "state": self.state,
                "finished": self.is_finished, "question": field.to_dict() if field else None,
                "context": self.question_context() if field else None,
                "explanation": self.explain_current_state(), "last_refusal": self.last_refusal,
                "job": self._job, "attempt": self.attempt}

    # -------------------------------------------------------------------
    # Long steps: a job, an executor, a handle
    # -------------------------------------------------------------------

    def submit_step(self, executor: Any, job: Job, *, on_done: str,
                    ask_over_s: Optional[float] = ASK_OVER_S, confirmed: bool = False) -> Optional[Handle]:
        """Hand this box's work to ``executor`` and follow it.

        Args:
            executor: Anything with the executor interface (`executors`).
            job: The work, with its estimate in ``job.budget_s``.
            on_done: The trigger to fire with the job's result once it is done.
            ask_over_s: An estimate over this is not submitted until
                ``confirmed``: the run records the question and waits. None:
                never ask.
            confirmed: The caller has seen the estimate and goes ahead.

        Returns:
            The handle, or None if the step is waiting for the estimate to be
            confirmed.
        """
        est = job.budget_s
        if ask_over_s is not None and est is not None and est > ask_over_s and not confirmed:
            msg = (f"{self.state}: {job.label or job.procedure} is estimated at {format_duration(est)}, "
                   f"over the {format_duration(ask_over_s)} allowed without asking. Confirm to go ahead, "
                   f"or reduce the work.")
            self.emit_event(message=msg, budget_s=est, asked=True)
            self.set_explanation(_Note(msg))
            self.update_detail(waiting_on="confirmation of the estimate", budget_s=est)
            return None
        handle = executor.submit(job)
        now = time.time()
        start_limit = job.start_limit_s
        if start_limit is None:
            start_limit = getattr(executor, "default_start_limit_s", None)
        self._job = {"handle": handle.to_dict(), "on_done": on_done, "procedure": job.procedure,
                     "label": job.label, "budget_s": est, "limit_s": job.limit_s,
                     "start_limit_s": start_limit, "submitted_at": now, "state": "queued",
                     "over_budget": False}
        self.detail.pop("waiting_on", None)
        self.detail["job"] = self._job
        self.emit_event(message=f"submitted {job.label or job.procedure} to {handle.executor}",
                        job_id=handle.job_id, executor=handle.executor, budget_s=est)
        self._on_transition()
        self.poll()
        return handle

    def submit_group(self, executor: Any, jobs: Sequence[Job], *, on_done: str, label: str,
                     budget_s: Optional[float] = None) -> List[Handle]:
        """Hand this box's work to ``executor`` as several jobs at once, and follow them as one step.

        The jobs run side by side (a remote executor's are sent together, `submit_many`).
        The step's record is one job's, so a run list and a dashboard read it as they read
        any other: its ``handle`` is the first job still going, its ``progress`` the jobs
        done of all, and ``group`` holds every handle. When every job is done, the
        ``on_done`` trigger fires with their results, in the jobs' order. A job that fails,
        is cancelled or times out ends the run the same way, and the others are cancelled.

        Args:
            executor: Anything with the executor interface (`executors`).
            jobs: The work, one job per part, at least one.
            on_done: The trigger to fire with the list of results.
            label: The step's name in the record and the events.
            budget_s: The step's expected time, side by side (None: the jobs' longest).

        Returns:
            The handles, in the jobs' order.
        """
        if not jobs:
            raise ValueError("submit_group needs at least one job")
        submit_many = getattr(executor, "submit_many", None)
        if submit_many is not None:
            submit_many(list(jobs))          # sent together; each submit below hands back its handle
        handles = [executor.submit(job) for job in jobs]
        if budget_s is None:
            budgets = [j.budget_s for j in jobs if j.budget_s is not None]
            budget_s = max(budgets) if budgets else None
        start_limit = jobs[0].start_limit_s
        if start_limit is None:
            start_limit = getattr(executor, "default_start_limit_s", None)
        self._group_results: Dict[int, Any] = {}
        self._job = {"handle": handles[0].to_dict(), "on_done": on_done, "procedure": jobs[0].procedure,
                     "label": label, "budget_s": budget_s, "limit_s": jobs[0].limit_s,
                     "start_limit_s": start_limit, "submitted_at": time.time(), "state": "queued",
                     "over_budget": False, "progress": {"done": 0, "total": len(jobs), "note": "jobs done"},
                     "group": [h.to_dict() for h in handles]}
        self.detail.pop("waiting_on", None)
        self.detail["job"] = self._job
        self.emit_event(message=f"submitted {label}: {len(jobs)} jobs to {handles[0].executor}",
                        job_ids=[h.job_id for h in handles], executor=handles[0].executor, budget_s=budget_s)
        self._on_transition()
        self.poll()
        return handles

    def _poll_group(self) -> str:
        rec = self._job
        handles = [Handle.from_dict(h) for h in rec["group"]]
        results = self._group_results
        states = []
        for i, h in enumerate(handles):
            if i in results:
                continue
            ex = executor_for(h)
            st = ex.status(h)
            if st.state == "done":
                results[i] = ex.result(h)
            elif st.state in ("queued", "running"):
                states.append(st.state)
            else:
                for j, other in enumerate(handles):
                    if j != i and j not in results:
                        executor_for(other).cancel(other)
                self._job = None
                self.detail.pop("job", None)
                self.last_log_tail = ex.logs(h)[-2000:]
                reason = st.error or st.state
                if st.state == "unknown":
                    reason = f"the job is lost: {reason}"
                end = "failed" if st.state in ("failed", "unknown") else st.state
                self.end_run(end, f"{rec['label']}: job {i + 1} of {len(handles)} {st.state}: "
                                  f"{reason.strip().splitlines()[-1] if reason.strip() else st.state}; "
                                  "the others were cancelled", job_id=h.job_id, traceback=st.error,
                             log_tail=self.last_log_tail)
                return self.state
        elapsed = time.time() - rec["submitted_at"]
        rec["elapsed_s"] = elapsed
        rec["progress"] = {"done": len(results), "total": len(handles), "note": "jobs done"}
        if len(results) == len(handles):
            out = [results[i] for i in range(len(handles))]
            self._job = None
            self.detail.pop("job", None)
            self.job_result = out
            self.emit_event(message=f"{rec['label']}: {len(handles)} jobs done in {format_duration(elapsed)}",
                            elapsed_s=elapsed)
            getattr(self, rec["on_done"])(out)
            return self.state
        rec["state"] = "running" if "running" in states else "queued"
        rec["handle"] = next(h.to_dict() for i, h in enumerate(handles) if i not in results)
        if rec["budget_s"] is not None and elapsed > rec["budget_s"] and not rec["over_budget"]:
            rec["over_budget"] = True
            self.emit_event(message=f"over budget: {format_duration(elapsed)} so far, against "
                                    f"{format_duration(rec['budget_s'])} expected; {len(results)} of "
                                    f"{len(handles)} jobs done")
        start_limit = rec.get("start_limit_s")
        if states and all(s == "queued" for s in states) and not results and start_limit is not None \
                and elapsed > start_limit:
            for i, h in enumerate(handles):
                executor_for(h).cancel(h)
            self._job = None
            self.detail.pop("job", None)
            self.end_run("failed", f"{rec['label']}: no job started within {format_duration(start_limit)}; "
                                   "they were cancelled")
            return self.state
        self._on_transition()
        return self.state

    @property
    def job(self) -> Optional[Dict[str, Any]]:
        """The job this run is following, as recorded in its heartbeat, or None."""
        return self._job

    def poll(self) -> str:
        """Follow the job, if there is one: copy its state and progress into the
        heartbeat, and act on its end. A finished job fires the ``on_done``
        trigger with its result; a failed, cancelled or timed-out one ends the
        run the same way. A group of jobs (`submit_group`) is followed as one.
        Returns the run's state."""
        if self._job is None:
            return self.state
        if "group" in self._job:
            return self._poll_group()
        handle = Handle.from_dict(self._job["handle"])
        ex = executor_for(handle)
        st = ex.status(handle)
        rec = self._job
        rec["state"], rec["progress"] = st.state, st.progress
        if st.telemetry:
            rec["telemetry"] = st.telemetry
        elapsed = time.time() - rec["submitted_at"]
        rec["elapsed_s"] = elapsed
        if rec["budget_s"] is not None and elapsed > rec["budget_s"] and not rec["over_budget"]:
            rec["over_budget"] = True
            going = "still queued: not started yet" if st.state == "queued" else "still running"
            self.emit_event(message=f"over budget: {format_duration(elapsed)} so far, against "
                                    f"{format_duration(rec['budget_s'])} expected; {going}",
                            job_id=handle.job_id)
        start_limit = rec.get("start_limit_s")
        if st.state == "queued" and start_limit is not None and elapsed > start_limit:
            ex.cancel(handle)
            log_tail = ex.logs(handle)[-2000:]
            self.last_log_tail = log_tail
            self.end_run("failed", f"{rec['label'] or rec['procedure']} did not start within "
                                   f"{format_duration(start_limit)}; it was cancelled. See the log tail.",
                         job_id=handle.job_id, log_tail=log_tail)
            return self.state
        if st.state == "done":
            result = ex.result(handle)
            self._job = None
            self.detail.pop("job", None)
            self.job_result = result
            self.emit_event(message=f"{rec['label'] or rec['procedure']} done in {format_duration(elapsed)}",
                            job_id=handle.job_id, elapsed_s=elapsed, telemetry=st.telemetry or None)
            getattr(self, rec["on_done"])(result)
        elif st.state in ("failed", "unknown"):
            reason = st.error or "the job failed"
            if st.state == "unknown":
                reason = f"the job is lost: {reason}"
            self.last_log_tail = ex.logs(handle)[-2000:]
            self.end_run("failed", reason.strip().splitlines()[-1], job_id=handle.job_id,
                         traceback=st.error, log_tail=self.last_log_tail)
        elif st.state in ("cancelled", "timed_out"):
            self.end_run(st.state, st.error or st.state, job_id=handle.job_id)
        else:
            self._on_transition()
        return self.state

    def wait(self, timeout_s: float, poll_s: float = 0.5) -> Dict[str, Any]:
        """Poll until the job ends, something needs attention, or ``timeout_s``
        passes. The one way to wait for a run: it reads the run's own record,
        never the process list.

        It returns early, so a waiter sees a problem when it happens rather
        than at the end of its timeout:
        - the job went over its budget during this wait (``attention:
          ["over_budget"]``; the job goes on, and the next wait does not stop
          for it again);
        - the job failed, or did not start within its start limit (the run
          has ended ``failed``; ``log_tail`` holds the executor's log).

        Returns:
            ``state``, ``waiting`` (still following a job), ``finished``, the
            job's ``progress`` while it runs, ``attention`` (a list, empty when
            nothing needs it), and ``log_tail`` when the run failed.
        """
        deadline = time.time() + timeout_s
        was_over = bool((self._job or {}).get("over_budget"))
        attention: List[str] = []
        self.poll()
        while self._job is not None and time.time() < deadline:
            if self._job.get("over_budget") and not was_over:
                attention.append("over_budget")
                break
            time.sleep(min(poll_s, max(0.0, deadline - time.time())))
            self.poll()
        if self._job is not None and self._job.get("over_budget") and not was_over and not attention:
            attention.append("over_budget")
        out = {"state": self.state, "waiting": self._job is not None, "finished": self.is_finished,
               "progress": (self._job or {}).get("progress"), "attention": attention,
               "explanation": self.explain_current_state()}
        if self.state == "failed":
            out["attention"] = attention + ["failed"]
            out["log_tail"] = getattr(self, "last_log_tail", "")
        return out

    def cancel(self, reason: str = "cancel requested") -> str:
        """Cancel the run: stop its job if it has one, and end in `cancelled`.
        A finished run is left as it is. Returns the run's state."""
        if self.is_finished:
            return self.state
        if self._job is not None and "group" in self._job:
            for i, h in enumerate(self._job["group"]):
                if i not in self._group_results:
                    handle = Handle.from_dict(h)
                    executor_for(handle).cancel(handle)
            self._job = None
            self.detail.pop("job", None)
        elif self._job is not None:
            handle = Handle.from_dict(self._job["handle"])
            st = executor_for(handle).cancel(handle)
            if st.state == "done":          # it finished before the cancel reached it
                return self.poll()
        self.end_run("cancelled", reason)
        return self.state

    # -------------------------------------------------------------------
    # A shared explain-yourself surface
    # -------------------------------------------------------------------

    def set_explanation(self, explanation: Any) -> None:
        """Record the current state's explanation -- a
        `ComparisonExplanation` or `FieldExplanation` (`fields.py`),
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


class _Note:
    """An explanation with only a message: a box's own words."""

    def __init__(self, message: str) -> None:
        self.message = message


def _with_example(reason: str, field: FlowField) -> str:
    """A refusal's reason, ending with what the field would accept."""
    if not field.example or field.example in reason:
        return reason
    return f"{reason} -- {field.example}"


def _short(value: Any, n: int = 200) -> Any:
    """An answer as recorded: JSON values as they are, others by their repr, cut short."""
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    text = value if isinstance(value, str) else repr(value)
    return text if len(text) <= n else text[:n] + "..."


def _state_name(state: Any) -> str:
    if isinstance(state, str):
        return state
    if isinstance(state, dict):
        return state["name"]
    return state.name


def graphviz_available() -> bool:
    """Whether the `dot` executable is on `PATH` -- used to skip
    SVG-content assertions in tests on a machine without Graphviz
    installed; production code degrades
    gracefully instead (see `ObservableFlow._render_svg`)."""
    return shutil.which("dot") is not None


def wait_all(flows: Sequence["ObservableFlow"], timeout_s: float, poll_s: float = 1.0,
             on_change: Optional[Callable[["ObservableFlow", Dict[str, Any]], None]] = None,
             max_workers: int = 64) -> Dict[str, Dict[str, Any]]:
    """Follow many runs at once, until every one has stopped waiting or ``timeout_s`` passes.

    Each round asks every followed job's executor for its status in parallel (a remote
    executor's round trips overlap, and `ModalExecutor` keeps what it learns for a moment), then
    polls each run, which then reads that status. A run that needs attention, or ends, is
    reported once to ``on_change`` with what `wait` returns.

    Returns:
        ``{run_id: the last of wait's returns}``.
    """
    from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415

    deadline = time.time() + timeout_s
    last: Dict[str, Dict[str, Any]] = {}
    pending = list(flows)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        while pending:
            # every status at once (network waits, not work), so the round's polls find them fresh
            handles = [Handle.from_dict(h) for f in pending if f.job is not None
                       for h in f.job.get("group") or [f.job["handle"]]]
            list(pool.map(lambda h: executor_for(h).status(h), handles))
            still = []
            for f in pending:
                out = f.wait(0.0)
                last[f.run_id] = out
                if on_change is not None and (out["attention"] or not out["waiting"]):
                    on_change(f, out)
                if out["waiting"]:
                    still.append(f)
            pending = still
            if not pending or time.time() >= deadline:
                break
            time.sleep(min(poll_s, max(0.0, deadline - time.time())))
    return last
