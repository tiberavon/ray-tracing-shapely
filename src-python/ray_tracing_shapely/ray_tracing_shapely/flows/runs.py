"""
Python-specific module: runs -- the flows in this kernel, and every run on record

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
PYTHON-SPECIFIC MODULE: runs
===============================================================================
Two things:

- **The live runs:** the flows this process holds, by run id (`track`,
  `get_run`), so a tool can wait on one or cancel it by its id.
- **Every run on record:** `list_runs(base_dirs)` reads the run logs and
  heartbeats of each folder of runs, follows each run's job by its handle,
  and flags the runs whose record and reality disagree:

  | Flag | Means |
  |---|---|
  | `crashed` | the record says the run is going on; nothing is working on it: its process is gone and it has no job alive |
  | `uncollected` | its job ended, and no one has polled the run since: the run's record still says it is waiting |
  | `hung` | silent too long, or over its job's budget, while its process or its job is alive and started |
  | `not_started` | its job is still queued past its start limit: it cannot start (a remote container failing before the procedure runs); waiting on the run cancels it |
  | `never_finished` | the run log has a start and no finish, and the run is not alive |

Only the standard library [KC7]: listing runs needs neither the machine nor
the procedures they ran.
===============================================================================
"""

from __future__ import annotations

import time
import weakref
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from . import persistence
from .executors import Handle, executor_for, pid_alive

#: The ends every flow has (`flow_base.FAILURE_STATES`, repeated here so
#: that listing needs no state-machine library), and the common own end.
ENDS = ("done", "failed", "cancelled", "timed_out")

#: Every flow made in this process, by run id, held weakly: a flow is
#: registered when it is made, and drops out when its caller lets it go.
_LIVE: "weakref.WeakValueDictionary[str, Any]" = weakref.WeakValueDictionary()
#: Flows kept alive on purpose: those an agent started, which no Python
#: variable holds.
_HELD: Dict[str, Any] = {}


def track(flow: Any, *, keep: bool = False) -> Any:
    """Register ``flow`` by its run id, so tools can reach it; ``keep`` also
    holds it alive. Every `ObservableFlow` registers itself. Returns it."""
    _LIVE[flow.run_id] = flow
    if keep:
        _HELD[flow.run_id] = flow
    return flow


def untrack(run_id: str) -> None:
    _LIVE.pop(run_id, None)
    _HELD.pop(run_id, None)


def get_run(run_id: str) -> Any:
    """The live flow with this run id."""
    try:
        return _LIVE[run_id]
    except KeyError:
        raise KeyError(f"no live run {run_id!r} in this process; live: {sorted(_LIVE)}") from None


def live_runs() -> Dict[str, Any]:
    return dict(_LIVE)


def _job_status(job: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not job or "handle" not in job:
        return None
    try:
        handle = Handle.from_dict(job["handle"])
        return executor_for(handle).status(handle).to_dict()
    except Exception as e:  # noqa: BLE001 -- an unreachable executor is a row, not a crash of the listing
        return {"state": "unreachable", "error": f"{type(e).__name__}: {e}"}


def list_runs(base_dirs: Optional[Iterable[Path]] = None, *,
              staleness_s: float = persistence.STALENESS_S,
              now: Optional[float] = None) -> List[Dict[str, Any]]:
    """Every run on record under ``base_dirs`` (default: the folders of the
    live runs), most recent first, each reconciled with its process and its
    job.

    Returns:
        One dict per run: ``run_id``, ``flow``, ``base_dir``, ``state``,
        ``finished``, ``age_s`` (since its heartbeat), ``pid``, ``live`` (held by
        this process), ``job`` (executor, id, state, progress, budget, over
        budget) and ``flags``.
    """
    now = now or time.time()
    dirs = {Path(d).resolve() for d in (base_dirs if base_dirs is not None
                                         else [f.base_dir for f in _LIVE.values()])}
    rows: List[Dict[str, Any]] = []
    for base in sorted(dirs):
        heartbeats = persistence.read_heartbeats(base)
        manifest = persistence.read_manifest(base)
        finished = {r["run_id"] for r in manifest if r.get("finished_at") is not None}
        started: Dict[str, Dict[str, Any]] = {}
        for r in manifest:
            started.setdefault(r["run_id"], r)
        for run_id in sorted(set(started) | set(heartbeats)):
            hb = heartbeats.get(run_id, {})
            state = hb.get("state")
            terminal = hb.get("terminal", state in ENDS)
            age = now - hb["updated_at"] if "updated_at" in hb else None
            job = (hb.get("detail") or {}).get("job")
            js = _job_status(job)
            job_state = js["state"] if js else None
            job_alive = job_state in ("queued", "running")
            proc_alive = pid_alive(hb.get("pid"))
            live = run_id in _LIVE
            flags = []
            if not terminal and state is not None:
                if js and job_state not in ("queued", "running", "unreachable"):
                    flags.append("uncollected" if (live or proc_alive) else "crashed")
                elif not (job_alive or proc_alive or live):
                    flags.append("crashed")
                else:
                    over = bool(job and job.get("budget_s") is not None
                                and now - job.get("submitted_at", now) > job["budget_s"])
                    silent = age is not None and age > staleness_s and not job_alive
                    start_limit = (job or {}).get("start_limit_s")
                    if job_state == "queued":         # not started: never hung, only too long queued
                        if start_limit is not None and now - job.get("submitted_at", now) > start_limit:
                            flags.append("not_started")
                    elif over or silent:
                        flags.append("hung")
            if run_id in started and run_id not in finished and not (live or proc_alive or job_alive):
                flags.append("never_finished")
            rows.append({
                "run_id": run_id,
                "flow": hb.get("fsm_name") or started.get(run_id, {}).get("standard"),
                "base_dir": str(base),
                "state": state,
                "finished": bool(terminal),
                "age_s": age,
                "pid": hb.get("pid"),
                "live": live,
                "job": None if not job else {
                    "executor": job["handle"]["executor"], "job_id": job["handle"]["job_id"],
                    "procedure": job.get("procedure"), "label": job.get("label"),
                    "state": job_state, "progress": (js or {}).get("progress"),
                    "budget_s": job.get("budget_s"),
                    "over_budget": bool(job.get("budget_s") is not None
                                        and now - job.get("submitted_at", now) > job["budget_s"]),
                    "error": (js or {}).get("error"),
                },
                "flags": flags,
                "started_at": started.get(run_id, {}).get("started_at", hb.get("started_at")),
            })
    rows.sort(key=lambda r: r["started_at"] or 0.0, reverse=True)
    return rows
