"""
Python-specific module: the run-control tools an agent uses on flows

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
PYTHON-SPECIFIC MODULE: agentic (flows)
===============================================================================
Nine tools, the same for every flow, so an agent learns the pattern once and
a new flow needs no new tool:

    flow_kinds()                   the flows that can be started: purpose, questions in order
    flow_start(kind)               a new run: its id and its first question
    flow_question(run_id)          where the run is: its question, the last refusal, its job
    flow_answer(run_id, value)     answer the question (JSON), or take its default
    flow_reset(run_id)             back to the first question, as a new attempt
    flow_result(run_id)            the result once finished, and the last attempt's events

    flow_list(base_dir)            every run on record, with its job and its flags
    flow_wait(run_id, timeout_s)   wait for a live run's job, reading its record
    flow_cancel(run_id)            stop a live run's job and end the run

Runs an agent starts are written under one root folder (`set_runs_root`;
default `./flow_runs`), one folder per kind.

They are added to the core's tool lists by `register()`, called explicitly,
never at import (as the 3D tools are): importing `flows` in a batch job must
not change what an agent sees. Every tool answers `{"status": "ok", "data":
...}` or `{"status": "error", "message": ...}` and never raises.
===============================================================================
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from . import kinds, persistence, runs

#: The longest a single `flow_wait` call blocks: an agent calls it again
#: rather than holding one call open for a long job.
MAX_WAIT_S = 300.0


def _ok(data: Any) -> Dict[str, Any]:
    return {"status": "ok", "data": data}


def _error(message: str) -> Dict[str, str]:
    return {"status": "error", "message": message}


#: The longest event list `flow_result` returns: the latest are kept (KA8).
MAX_EVENTS = 40

_RUNS_ROOT: Optional[Path] = None


def set_runs_root(path: Any) -> Path:
    """Where runs started by an agent are written: ``<root>/<kind>/``. None
    restores the default, ``./flow_runs``."""
    global _RUNS_ROOT
    _RUNS_ROOT = None if path is None else Path(path).resolve()
    return runs_root()


def runs_root() -> Path:
    return _RUNS_ROOT if _RUNS_ROOT is not None else Path.cwd() / "flow_runs"


def _live(run_id: str) -> Any:
    flow = runs.get_run(run_id)
    if flow.job is not None:
        flow.poll()
    return flow


def flow_kinds() -> Dict[str, Any]:
    """The flows that can be started: each one's purpose and its questions, in order."""
    out = []
    for kind in kinds.flow_kinds():
        try:
            out.append(kind.describe())
        except Exception as e:  # noqa: BLE001 -- a kind whose package is not installed is listed as such
            out.append({"kind": kind.name, "unavailable": f"{type(e).__name__}: {e}"})
    return _ok({"kinds": out, "runs_root": str(runs_root())})


def flow_start(kind: str) -> Dict[str, Any]:
    """Start a run of ``kind``: its id, and its first question."""
    try:
        flow = kinds.get_flow_kind(kind).start(runs_root())
    except KeyError as e:
        return _error(str(e.args[0]))
    except Exception as e:  # noqa: BLE001
        return _error(f"could not start {kind}: {type(e).__name__}: {e}")
    return _ok(flow.question_state())


def flow_question(run_id: str) -> Dict[str, Any]:
    """Where a run is: its state, the question it waits on with its kind, unit,
    default and example, the last refused answer and why, and any job."""
    try:
        return _ok(_live(run_id).question_state())
    except KeyError as e:
        return _error(str(e.args[0]))
    except Exception as e:  # noqa: BLE001
        return _error(f"{type(e).__name__}: {e}")


def flow_answer(run_id: str, value: Any = None, use_default: bool = False) -> Dict[str, Any]:
    """Answer a run's current question with ``value`` (JSON), or with its
    default. A refused answer leaves the run where it was, with the reason."""
    try:
        flow = _live(run_id)
    except KeyError as e:
        return _error(str(e.args[0]))
    try:
        out = flow.answer_default() if use_default else flow.answer(value)
    except Exception as e:  # noqa: BLE001
        return _error(f"{type(e).__name__}: {e}")
    return _ok(out)


def flow_reset(run_id: str) -> Dict[str, Any]:
    """Back to the first question, as a new attempt of the same run: every
    earlier answer is dropped, and kept in the events."""
    try:
        flow = _live(run_id)
    except KeyError as e:
        return _error(str(e.args[0]))
    try:
        flow.reset()
        if "begin" in flow.machine.get_triggers(flow.state):
            flow.begin()
    except Exception as e:  # noqa: BLE001
        return _error(f"{type(e).__name__}: {e}")
    return _ok(flow.question_state())


def flow_result(run_id: str, base_dir: Optional[str] = None) -> Dict[str, Any]:
    """A run's ``result.json`` once it has finished, and its last attempt's
    events (the latest `MAX_EVENTS`). A run not in this kernel is read from
    ``base_dir``."""
    try:
        if base_dir is None:
            flow = _live(run_id)
            base, attempt, finished, state = flow.base_dir, flow.attempt, flow.is_finished, flow.state
        else:
            base = Path(base_dir)
            hb = persistence.read_heartbeats(base).get(run_id)
            if hb is None:
                return _error(f"no run {run_id!r} in {base}")
            events = persistence.read_events(base, run_id)
            attempt = max((e.get("attempt", 1) for e in events), default=1)
            finished, state = bool(hb.get("terminal", hb.get("state") in runs.ENDS)), hb.get("state")
    except KeyError as e:
        return _error(str(e.args[0]))
    result = persistence.read_result(base, run_id) if finished else None
    events = [e for e in persistence.read_events(base, run_id) if e.get("attempt", 1) == attempt]
    shown = [{k: e[k] for k in ("seq", "state", "message", "field", "refused", "reason") if k in e}
             for e in events[-MAX_EVENTS:]]
    return _ok({"run_id": run_id, "state": state, "finished": finished, "attempt": attempt,
                "result": result, "events": shown, "events_total": len(events)})


def flow_list(base_dir: Optional[str] = None) -> Dict[str, Any]:
    """Every run on record, most recent first, each checked against its
    process and its job; ``flags`` names the ones whose record and reality
    disagree (crashed, uncollected, hung, never_finished)."""
    try:
        rows = runs.list_runs([base_dir] if base_dir else None)
    except Exception as e:  # noqa: BLE001 -- the answer shape, not an exception
        return _error(f"could not list runs: {type(e).__name__}: {e}")
    if not rows and not base_dir:
        return _ok({"runs": [], "note": "no live flow in this kernel; pass base_dir to list a folder of runs"})
    return _ok({"runs": rows})


def flow_wait(run_id: str, timeout_s: float = 60.0) -> Dict[str, Any]:
    """Wait for a live run's job to end, up to ``timeout_s`` (at most
    `MAX_WAIT_S`), and say where the run is. Returns early when something
    needs attention (`ObservableFlow.wait`)."""
    try:
        flow = runs.get_run(run_id)
    except KeyError as e:
        return _error(str(e.args[0]))
    try:
        out = flow.wait(min(float(timeout_s), MAX_WAIT_S))
    except Exception as e:  # noqa: BLE001
        return _error(f"wait failed: {type(e).__name__}: {e}")
    out["run_id"] = run_id
    out["job"] = flow.job
    return _ok(out)


def flow_cancel(run_id: str, reason: str = "cancelled by an agent") -> Dict[str, Any]:
    """Cancel a live run: stop its job, if it has one, and end it as
    cancelled. A finished run is left as it is."""
    try:
        flow = runs.get_run(run_id)
    except KeyError as e:
        return _error(str(e.args[0]))
    try:
        state = flow.cancel(reason)
    except Exception as e:  # noqa: BLE001
        return _error(f"cancel failed: {type(e).__name__}: {e}")
    return _ok({"run_id": run_id, "state": state, "explanation": flow.explain_current_state()})


_RUN_ID = {"type": "string", "description": "The run's id, as flow_start or flow_list gives it."}

TOOLS = [
    (flow_kinds, "List the flows (step-by-step procedures) that can be started, each with its purpose and "
                 "its questions in the order they are asked: kind of answer, unit, default, example. Start "
                 "here to run a procedure.", {"type": "object", "properties": {}, "required": []}),
    (flow_start, "Start a run of a flow kind (from flow_kinds). Returns its run_id and its first question.",
     {"type": "object", "properties": {"kind": {"type": "string", "description": "The flow kind."}},
      "required": ["kind"]}),
    (flow_question, "Where a run is: its state, the question it waits on (kind, unit, default, example, why "
                    "it is asked), the last refused answer and why, and any long job it is following.",
     {"type": "object", "properties": {"run_id": _RUN_ID}, "required": ["run_id"]}),
    (flow_answer, "Answer a run's current question: value as JSON (a quantity as a string with its unit, "
                  'e.g. "7 mm"; a path as a string; true/false; a list for a range), or use_default=true '
                  "for its default. A refused answer leaves the run at the same question, with the reason and an "
                  "example. An accepted answer a later check rejects sends the run back to an earlier "
                  "question: the reply's sent_back says from where, to where and why. Returns the next "
                  "question, or the end.",
     {"type": "object", "properties": {"run_id": _RUN_ID,
                                       "value": {"description": "The answer, as JSON."},
                                       "use_default": {"type": "boolean", "default": False,
                                                       "description": "Answer with the question's default."}},
      "required": ["run_id"]}),
    (flow_reset, "Start a run again from its first question, as a new attempt; earlier answers are dropped "
                 "and kept in its record.",
     {"type": "object", "properties": {"run_id": _RUN_ID}, "required": ["run_id"]}),
    (flow_result, "A run's result once it has finished, and the events of its last attempt.",
     {"type": "object", "properties": {"run_id": _RUN_ID,
                                       "base_dir": {"type": "string", "description":
                                                    "For a run not in this kernel: its folder of runs."}},
      "required": ["run_id"]}),
    (flow_list, "List every flow run on record (a flow is a step-by-step procedure: a classification, a "
                "rayfile slicing, a comparison), most recent first: its state, its job (executor, progress, "
                "budget) and flags where the record and reality disagree: crashed, uncollected, hung, "
                "never_finished. Use this, never the process list, to see what is running.",
     {"type": "object", "properties": {"base_dir": {"type": "string", "description":
                                                    "A folder of runs; default: those of this kernel's flows."}},
      "required": []}),
    (flow_wait, "Wait for a run's long step (its job) to end, up to timeout_s seconds (at most 300), then "
                "say where the run is: its state, whether it is still waiting, its progress. It returns early "
                "when something needs attention: 'attention' lists it (over_budget: the job goes on; failed: "
                "the job failed or did not start in time, and log_tail holds its log). Read log_tail before "
                "starting the run again. Call again to keep waiting.",
     {"type": "object", "properties": {"run_id": _RUN_ID,
                                       "timeout_s": {"type": "number", "description": "Seconds to wait.",
                                                     "default": 60}},
      "required": ["run_id"]}),
    (flow_cancel, "Cancel a run: stop its job, if it has one, and end the run as cancelled.",
     {"type": "object", "properties": {"run_id": _RUN_ID,
                                       "reason": {"type": "string", "description": "Why, for the run's record."}},
      "required": ["run_id"]}),
]


def register() -> bool:
    """Add the nine flow tools to the core's tool lists, once. Call before the
    MCP server starts.

    Returns:
        True if they were added now, False if they already were.

    Raises:
        RuntimeError: If the MCP server is already running (`register_tool`).
    """
    from ..analysis.tool_registry import get_agentic_tools, register_tool

    present = {t["name"] for t in get_agentic_tools()}
    if all(fn.__name__ in present for fn, _, _ in TOOLS):
        return False
    for fn, description, schema in TOOLS:
        if fn.__name__ not in present:
            register_tool(fn, description, schema, module="ray_tracing_shapely.flows.agentic")
    return True
