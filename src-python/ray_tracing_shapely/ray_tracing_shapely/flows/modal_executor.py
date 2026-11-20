"""
Python-specific module: modal_executor -- jobs on Modal, behind the executor interface

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
PYTHON-SPECIFIC MODULE: modal_executor
===============================================================================
`ModalExecutor` runs a `Job` on Modal (modal.com), with the five calls of
every executor (`executors`). Two halves:

- **Here:** `ModalExecutor.submit` sends the job to a function of a
  *deployed* Modal app, found by name, so its handle (the Modal call's id)
  is followed from any process, after a restart too. `status` asks Modal
  for the call's outcome without waiting, and reads the job's own record
  for its progress. `cancel` asks the job to stop and cancels the call.
  `logs` gives Modal's logs of the job (the call's, or the function's when
  the call never started: a container that fails before the procedure
  runs) and the job's captured output. While a job is queued, Modal's
  function statistics say whether its containers are failing to start;
  once ended, its telemetry is the code it ran and its estimated cost.
  `workspace_spend` reads the billed spend.
- **There:** `remote_run` is the body of the deployed function. It writes
  the job's files into the container, points the inputs at them, runs the
  procedure with a `JobContext`, keeps the job's record (started, progress,
  heartbeat) in a `modal.Dict`, honours a cancel request, and returns the
  outcome as plain data: a job's failure is its status, never an exception
  through Modal.

A deployed app's code is a snapshot: it runs the packages as they were when
it was deployed. `remote_run` reports the ``RTS_COMMIT`` its image was built
with, and the job's record keeps it.

A job that stays queued is not waited on forever: `default_start_limit_s`
becomes the job's start limit, and the flow following it cancels it past
that (`ObservableFlow.poll`).

`modal` is imported only when an executor is made, so the rest of `flows`
needs no Modal client [KC7].
===============================================================================
"""

from __future__ import annotations

import contextlib
import importlib
import io
import os
import sys
import tempfile
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from .executors import Handle, Job, JobCancelled, JobContext, JobStatus, resolve_procedure

#: The `modal.Dict` holding every job's record, by job id.
STATE_DICT = "rts-jobs-state"
#: How long a Modal job may stay queued, by default: a cold start and an image pull take
#: seconds; minutes mean its container cannot start.
DEFAULT_START_LIMIT_S = 180.0
#: How much of a job's output its result keeps.
LOG_TAIL_CHARS = 8000
#: Modal's published rates for a preemptible CPU function, for a job's cost estimate: per
#: physical core-second and per GiB-second of memory. Recheck them against the pricing page.
CPU_USD_PER_CORE_S = 0.0000131
MEMORY_USD_PER_GIB_S = 0.00000222
#: How often a queued job's queue is asked about (Modal's function statistics).
STATS_EVERY_S = 10.0
#: How long a running or queued job's status is reused before Modal is asked again. It must
#: outlast a `wait_all` round's fetching of every status, or the round's own polls ask again,
#: one after another (E4b: 52 runs, 16 threads, rounds of 10-20 s at 2 s).
STATUS_TTL_S = 5.0
#: How long a job is queued before its queue is asked about: a cold start takes seconds, and
#: asking at once would slow every submission for a question only a stuck job needs.
QUEUE_STATS_AFTER_S = 15.0


# ---------------------------------------------------------------------------
# There: the deployed function's body
# ---------------------------------------------------------------------------

def _repoint(value: Any, paths: Mapping[str, str]) -> Any:
    """``value`` with every string that is one of the job's local file paths replaced by
    where that file is in the container."""
    if isinstance(value, str):
        return paths.get(value, value)
    if isinstance(value, list):
        return [_repoint(v, paths) for v in value]
    if isinstance(value, dict):
        return {k: _repoint(v, paths) for k, v in value.items()}
    return value


def remote_run(job_id: str, procedure: str, inputs: Dict[str, Any], files: Dict[str, Dict[str, Any]],
               state: MutableMapping[str, Any]) -> Dict[str, Any]:
    """Run one job where it was sent. The body of the deployed function.

    Args:
        job_id: The job's id, the key of its record in ``state``.
        procedure, inputs: As in `Job`.
        files: ``{name: {"path": the path the inputs name it by, "data": bytes}}``.
        state: The jobs' records (a `modal.Dict`; any mapping in a test).
            ``state[job_id]`` is this job's; ``state["cancel:" + job_id]``,
            once set, asks it to stop.

    Returns:
        ``{"state": "done" | "failed" | "cancelled", "result", "error",
        "log_tail", "started_at", "finished_at", "commit"}``.
    """
    started = time.time()
    commit = os.environ.get("RTS_COMMIT")
    rec: Dict[str, Any] = {"started_at": started, "updated_at": started, "progress": {}, "commit": commit}
    state[job_id] = rec
    work = Path(tempfile.mkdtemp(prefix=f"job-{job_id}-"))
    paths: Dict[str, str] = {}
    for name, f in files.items():
        target = work / name / Path(f["path"]).name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f["data"])
        paths[f["path"]] = str(target)
    checked = [0.0, False]

    def cancelled() -> bool:            # one round trip to the Dict every 2 s at most
        now = time.time()
        if not checked[1] and now - checked[0] > 2.0:
            checked[0] = now
            checked[1] = bool(state.get(f"cancel:{job_id}", False))
        return checked[1]

    def on_progress(p: Dict[str, Any]) -> None:
        rec["progress"], rec["updated_at"] = p, p["at"]
        state[job_id] = rec

    out: Dict[str, Any] = {"state": "failed", "result": None, "error": None, "started_at": started,
                           "commit": commit}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            ctx = JobContext(work, {n: paths[f["path"]] for n, f in files.items()}, on_progress, cancelled)
            t_import = time.time()
            fn = resolve_procedure(procedure)
            out["import_s"] = time.time() - t_import            # a cold container pays its imports here
            out["result"] = fn(_repoint(inputs, paths), ctx)
            out["state"] = "done"
        except JobCancelled:
            out["state"] = "cancelled"
        except Exception:  # noqa: BLE001 -- a job's failure is its status, not Modal's exception
            out["error"] = traceback.format_exc()
            print(out["error"])
    out["finished_at"] = time.time()
    out["log_tail"] = buf.getvalue()[-LOG_TAIL_CHARS:]
    state[job_id] = {**rec, "updated_at": out["finished_at"], "ended": out["state"]}
    return out


# ---------------------------------------------------------------------------
# Here: the executor
# ---------------------------------------------------------------------------

class ModalExecutor:
    """Jobs on a deployed Modal app's function, whose body is `remote_run`.

    Args:
        app_name: The deployed app (``modal deploy``).
        function_name: Its function that calls `remote_run`.
        state_dict: The `modal.Dict` of the jobs' records (`STATE_DICT`).
        default_start_limit_s: The start limit of a job that gives none.
        cpu, memory_gib: The deployed function's resources, for a job's cost
            estimate.
        fail_after_container_errors: A queued job is failed at once, without
            waiting for its start limit, once the function's containers have
            failed to start this many times since the job was submitted
            (Modal's function statistics; they count the function's
            containers, whichever job they were for).
        modal_module: The Modal client (default: ``import modal``); a test's
            stand-in.

    A handle's ``where`` holds the call's id, the app, the function, the
    Dict, the resources and the job's hard limit, so `executor_for` rebuilds
    the executor from the handle alone. A hard limit is enforced here, when
    the job is looked at: past ``limit_s`` a running job is cancelled and
    reported ``timed_out``. The deployed function's own ``timeout`` is the
    backstop.

    **Telemetry** (`JobStatus.telemetry`, copied into the run's record):
    while queued, Modal's backlog and the containers started and failed
    since the job was submitted; once ended, the commit the deployed code
    was built from, the run time, and ``cost_usd_est``, the run time at the
    function's resources and `CPU_USD_PER_CORE_S` / `MEMORY_USD_PER_GIB_S`.
    That estimate leaves out a container's start and idle time, which Modal
    also bills: the workspace's billed spend is `workspace_spend`'s.
    """

    kind = "modal"
    #: Shared by every executor in this process, so a handle followed through a new executor
    #: (`executor_for`, as `poll` does) still finds what was learnt: ended jobs for good, a
    #: running or queued job's status for `STATUS_TTL_S`.
    _ended: Dict[str, JobStatus] = {}
    _outcomes: Dict[str, Dict[str, Any]] = {}
    _recent: Dict[str, Tuple[float, JobStatus]] = {}
    _queue_seen: Dict[str, Tuple[float, Dict[str, Any]]] = {}
    #: Modal's statistics are the function's, not a job's: kept per function (its backlog and
    #: runners) and per function and window of submission times (its containers since then),
    #: shared by every job of it, so many queued jobs ask Modal no more often than one does.
    _function_stats: Dict[Tuple[str, str], Tuple[float, Dict[str, Any]]] = {}
    _since_stats: Dict[Tuple[str, str, int], Tuple[float, Dict[str, Any]]] = {}
    _functions: Dict[Tuple[str, str], Any] = {}
    _just_sent: Dict[str, JobStatus] = {}

    def __init__(self, app_name: str, function_name: str = "run_job", *, state_dict: str = STATE_DICT,
                 default_start_limit_s: Optional[float] = DEFAULT_START_LIMIT_S, cpu: float = 1.0,
                 memory_gib: float = 2.0, fail_after_container_errors: Optional[int] = 3,
                 modal_module: Any = None) -> None:
        self.app_name = app_name
        self.function_name = function_name
        self.state_dict = state_dict
        self.default_start_limit_s = default_start_limit_s
        self.cpu, self.memory_gib = float(cpu), float(memory_gib)
        self.fail_after_container_errors = fail_after_container_errors
        self._modal = modal_module or importlib.import_module("modal")
        self._presubmitted: List[Tuple[Job, Handle]] = []

    # -- helpers ---------------------------------------------------------------

    def _state(self) -> Any:
        return self._modal.Dict.from_name(self.state_dict, create_if_missing=True)

    def _call(self, handle: Handle) -> Any:
        return self._modal.FunctionCall.from_id(handle.where["call_id"])

    def _function(self) -> Any:
        key = (self.app_name, self.function_name)
        if key not in self._functions:                  # a lookup is a round trip; once is enough
            self._functions[key] = self._modal.Function.from_name(*key)
        return self._functions[key]

    def _record(self, handle: Handle) -> Dict[str, Any]:
        try:
            return dict(self._state().get(handle.job_id) or {})
        except Exception:  # noqa: BLE001 -- a record we cannot read is no record, not a failure
            return {}

    def _forget(self, handle: Handle) -> None:
        """Drop the job's entries from the shared Dict once its outcome is here."""
        try:
            state = self._state()
            for key in (handle.job_id, f"cancel:{handle.job_id}"):
                state.pop(key, None)
        except Exception:  # noqa: BLE001 -- a leftover entry is untidy, not wrong
            pass

    # -- the interface ---------------------------------------------------------

    def submit(self, job: Job) -> Handle:
        """Send the job, or, if `submit_many` already sent it, hand back its handle at once."""
        for k, (sent, handle) in enumerate(self._presubmitted):
            if sent is job:
                del self._presubmitted[k]
                return handle
        return self._spawn(job)

    def _spawn(self, job: Job) -> Handle:
        job_id = f"{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"
        files = {name: {"path": path, "data": Path(path).read_bytes()} for name, path in job.files.items()}
        call = self._function().spawn(job_id, job.procedure, job.inputs, files)
        now = time.time()
        handle = Handle(self.kind, job_id, {"call_id": call.object_id, "app": self.app_name,
                                            "function": self.function_name, "state_dict": self.state_dict,
                                            "submitted_at": now, "limit_s": job.limit_s,
                                            "cpu": self.cpu, "memory_gib": self.memory_gib})
        # just sent, so queued: the first look (submit_step's own poll) needs no round trip to say so
        self._just_sent[job_id] = JobStatus("queued", updated_at=now)
        return handle

    def submit_many(self, jobs: Sequence[Job], max_workers: int = 16) -> List[Handle]:
        """Send many jobs at once, their uploads and round trips overlapping in threads.

        Each job's later `submit` (a flow's `submit_step`, with this very ``Job`` object) hands
        back the handle made here at once, so a batch of flows starts in about the time of one
        round trip, not one per flow. The handles, in order.
        """
        from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415

        self._function()                               # one lookup, before the threads share it
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            handles = list(pool.map(self._spawn, jobs))
        self._presubmitted.extend(zip(jobs, handles))
        return handles

    def status(self, handle: Handle) -> JobStatus:
        if handle.job_id in self._ended:
            return self._ended[handle.job_id]
        first = self._just_sent.pop(handle.job_id, None)
        if first is not None:
            return first
        recent = self._recent.get(handle.job_id)
        if recent and time.time() - recent[0] < STATUS_TTL_S:
            return recent[1]
        st = self._status(handle)
        if not st.ended:
            self._recent[handle.job_id] = (time.time(), st)
        return st

    def _status(self, handle: Handle) -> JobStatus:
        exc = self._modal.exception
        try:
            out = self._call(handle).get(timeout=0)
        except (TimeoutError, exc.TimeoutError):
            return self._still_going(handle)
        except exc.OutputExpiredError:
            return self._end(handle, JobStatus("unknown", error="Modal no longer keeps this job's result"))
        except exc.FunctionTimeoutError as e:
            return self._end(handle, JobStatus("timed_out", error=f"the deployed function's timeout: {e}"))
        except exc.InputCancellation:
            return self._end(handle, JobStatus("cancelled", error="cancelled on Modal"))
        except Exception as e:  # noqa: BLE001 -- anything else from Modal is the job's failure
            if "cancelled" in str(e):
                # a cancelled call, looked at later or from another process, raises RemoteError
                # ("Function call was cancelled by user or a failure"), not InputCancellation
                return self._end(handle, JobStatus("cancelled", error=f"cancelled on Modal: {e}"))
            return self._end(handle, JobStatus("failed", error=f"{type(e).__name__}: {e}"))
        self._outcomes[handle.job_id] = out
        rec = self._record(handle)
        self._forget(handle)
        run_s = (out.get("finished_at") or 0.0) - (out.get("started_at") or 0.0)
        cpu = float(handle.where.get("cpu", self.cpu))
        mem = float(handle.where.get("memory_gib", self.memory_gib))
        telemetry = {"commit": out.get("commit"), "run_s": round(run_s, 3),
                     "import_s": round(out["import_s"], 3) if out.get("import_s") is not None else None,
                     "cost_usd_est": round(run_s * (cpu * CPU_USD_PER_CORE_S + mem * MEMORY_USD_PER_GIB_S), 6),
                     "cpu": cpu, "memory_gib": mem}
        st = JobStatus(out["state"], progress=rec.get("progress", {}), error=out.get("error"),
                       started_at=out.get("started_at"), finished_at=out.get("finished_at"),
                       updated_at=out.get("finished_at"), telemetry=telemetry)
        return self._end(handle, st)

    def _queue(self, handle: Handle) -> Dict[str, Any]:
        """Modal's view of a queued job, at most every `STATS_EVERY_S`: the function's backlog and
        its containers started and failed since the job was submitted.

        The statistics are the function's, so they are asked for once per function (and, for the
        containers since a time, once per `STATS_EVERY_S` window of submission times) and shared
        by every queued job of it: Modal rate-limits these calls (5 a second), and a sweep of
        hundreds of queued jobs asking each for its own would wait on the limit, not on its jobs.
        A job's "since" is then the start of its window, at most `STATS_EVERY_S` before it was
        submitted, plus the 5 s margin.
        """
        now = time.time()
        seen = self._queue_seen.get(handle.job_id)
        if seen and now - seen[0] < STATS_EVERY_S:
            return seen[1]
        key = (self.app_name, self.function_name)
        submitted = handle.where.get("submitted_at", now)
        window = int(submitted // STATS_EVERY_S) if STATS_EVERY_S > 0 else int(submitted * 1000)
        out: Dict[str, Any] = {}
        try:
            fn = self._function()
            cur = self._function_stats.get(key)
            if cur is None or now - cur[0] >= STATS_EVERY_S:
                now_stats = fn.get_current_stats()
                cur = (now, {"backlog": getattr(now_stats, "backlog", None),
                             "runners": getattr(now_stats, "num_total_runners", None)})
                self._function_stats[key] = cur
            out.update(cur[1])
            since_key = (*key, window)
            got = self._since_stats.get(since_key)
            if got is None or now - got[0] >= STATS_EVERY_S:
                start = window * STATS_EVERY_S if STATS_EVERY_S > 0 else submitted
                st = fn.stats(since=datetime.fromtimestamp(start - 5.0, timezone.utc))
                got = (now, {"containers_started": getattr(st, "container_started_count", None),
                             "containers_failed": getattr(st, "container_error_count", None)})
                self._since_stats[since_key] = got
            out.update(got[1])
        except Exception as e:  # noqa: BLE001 -- telemetry missing is not the job failing
            out["unavailable"] = f"{type(e).__name__}: {e}"
        self._queue_seen[handle.job_id] = (now, out)
        return out

    def _still_going(self, handle: Handle) -> JobStatus:
        rec = self._record(handle)
        if not rec.get("started_at"):
            queued_s = time.time() - handle.where.get("submitted_at", time.time())
            queue = self._queue(handle) if queued_s >= QUEUE_STATS_AFTER_S else {}
            failed = queue.get("containers_failed") or 0
            if self.fail_after_container_errors is not None and failed >= self.fail_after_container_errors:
                self._stop(handle)
                return self._end(handle, JobStatus(
                    "failed", finished_at=time.time(), telemetry={"queue": queue},
                    error=f"not started: the function's containers failed to start {failed} times since "
                          "the job was submitted (Modal's function statistics); see the logs"))
            return JobStatus("queued", updated_at=handle.where.get("submitted_at"),
                             telemetry={"queue": queue} if queue else {})
        st = JobStatus("running", progress=rec.get("progress", {}), started_at=rec["started_at"],
                       updated_at=rec.get("updated_at"), telemetry={"commit": rec.get("commit")})
        limit = handle.where.get("limit_s")
        if limit is not None and (st.elapsed_s() or 0.0) > limit:
            self._stop(handle)
            return self._end(handle, JobStatus("timed_out", progress=st.progress, started_at=st.started_at,
                                               finished_at=time.time(), error=f"over the {limit} s limit"))
        return st

    def _end(self, handle: Handle, st: JobStatus) -> JobStatus:
        self._ended[handle.job_id] = st
        self._recent.pop(handle.job_id, None)
        return st

    def result(self, handle: Handle) -> Any:
        st = self.status(handle)
        if st.state != "done":
            raise RuntimeError(f"job {handle.job_id} has no result: {st.state}")
        return self._outcomes[handle.job_id]["result"]

    def _stop(self, handle: Handle) -> None:
        try:
            self._state()[f"cancel:{handle.job_id}"] = True     # the procedure stops at its next progress
        except Exception:  # noqa: BLE001
            pass
        self._call(handle).cancel(terminate_containers=True)    # and a call that never started is dropped

    def cancel(self, handle: Handle) -> JobStatus:
        st = self.status(handle)
        if not st.ended:
            self._stop(handle)
            st = self._end(handle, JobStatus("cancelled", progress=st.progress, started_at=st.started_at,
                                             finished_at=time.time(), error="cancel requested"))
        return st

    def logs(self, handle: Handle, tail: int = 4000) -> str:
        """Modal's logs of this job, then its own output if it ended. Modal's logs are the call's
        own, or, when it has none (it never started), the function's since it was submitted: a
        container that fails before the procedure runs shows only there. The job's output is
        last, kept whole within ``tail``, where a tail of this is read."""
        out = self._outcomes.get(handle.job_id) or {}
        own = out.get("log_tail") or ""
        if out.get("error") and out["error"] not in own:
            own += out["error"]
        own = own[-(tail * 2 // 3):] if own else ""
        modal_part = "--- Modal's logs ---\n" + self._modal_logs(handle)
        own_part = f"\n--- the job's output ---\n{own}" if own else ""
        return modal_part[-(tail - len(own_part)):] + own_part

    def _modal_logs(self, handle: Handle) -> str:
        since = datetime.fromtimestamp(handle.where.get("submitted_at", time.time()) - 30.0, timezone.utc)

        def text(entries: Any) -> str:
            lines = []
            for e in entries:
                t = getattr(e, "timestamp", None)
                stamp = t.strftime("%H:%M:%S") if hasattr(t, "strftime") else ""
                lines.append(f"[{stamp}] {getattr(e, 'message', e)}".rstrip())
            return "\n".join(lines)
        try:
            own = text(self._call(handle).logs.fetch(since=since))
            if own:
                return own
            return "(none from the call; the function's:)\n" + text(self._function().logs.fetch(since=since))
        except Exception as e:  # noqa: BLE001
            return f"(could not be read: {type(e).__name__}: {e})"


def workspace_spend(hours: Optional[float] = 24.0, modal_module: Any = None, *,
                    since: Optional[datetime] = None) -> Dict[str, Any]:
    """What the workspace was billed since ``since`` (default: the last ``hours``), by Modal's
    billing report at hourly resolution: the total and each app's or object's share, in US
    dollars. The report lags: the latest hour or so is not in it yet. Modal's hourly reports
    span at most 7 days, so a longer window is read as whole days up to the start of today
    (UTC), and hours since."""
    modal = modal_module or importlib.import_module("modal")
    now = datetime.now(timezone.utc)
    start = since or (now - timedelta(hours=float(hours or 24.0)))
    ws = modal.Workspace.from_context() if hasattr(modal.Workspace, "from_context") else modal.Workspace()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if now - start <= timedelta(days=7):
        rows = list(ws.billing.report(start=start, resolution="h"))
    else:
        rows = list(ws.billing.report(start=start, end=today, resolution="d"))
        rows += list(ws.billing.report(start=today, resolution="h"))
    by: Dict[str, float] = {}
    for r in rows:
        by[r.description] = by.get(r.description, 0.0) + float(r.cost)
    latest = max((r.interval_start for r in rows), default=None)
    return {"since": start.isoformat(timespec="minutes"), "total_usd": round(sum(by.values()), 6),
            "by_object": {k: round(v, 6) for k, v in sorted(by.items(), key=lambda kv: -kv[1])},
            "latest_hour": latest.isoformat(timespec="minutes") if latest else None}


def spend_summary(hours: float = 24.0, modal_module: Any = None) -> Dict[str, Any]:
    """The billed spend over the last ``hours`` and since the start of this calendar month (UTC),
    read once: what the dashboard's spend card shows."""
    now = datetime.now(timezone.utc)
    month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return {"read_at": now.isoformat(timespec="seconds"), "last_hours": hours,
            "recent": workspace_spend(hours, modal_module), "month": workspace_spend(None, modal_module, since=month)}


def from_handle(handle: Handle) -> ModalExecutor:
    """The executor that follows ``handle`` (`executors.executor_for`)."""
    w = handle.where
    return ModalExecutor(w["app"], w["function"], state_dict=w.get("state_dict", STATE_DICT),
                         cpu=w.get("cpu", 1.0), memory_gib=w.get("memory_gib", 2.0))


def main(argv: Optional[list] = None) -> int:
    """``python -m ray_tracing_shapely.flows.modal_executor spend [--hours 24]``: the billed spend."""
    import argparse
    import json
    p = argparse.ArgumentParser(description="Modal: the workspace's billed spend.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("spend", help="the billed spend over the last hours, by app")
    sp.add_argument("--hours", type=float, default=24.0)
    sp.add_argument("--summary", action="store_true",
                    help="the last hours and this calendar month (UTC) together, as the dashboard reads it")
    args = p.parse_args(argv)
    print(json.dumps(spend_summary(args.hours) if args.summary else workspace_spend(args.hours), indent=1))
    return 0


__all__ = ["CPU_USD_PER_CORE_S", "DEFAULT_START_LIMIT_S", "LOG_TAIL_CHARS", "MEMORY_USD_PER_GIB_S",
           "ModalExecutor", "STATE_DICT", "from_handle", "remote_run", "spend_summary", "workspace_spend"]


if __name__ == "__main__":
    sys.exit(main())
