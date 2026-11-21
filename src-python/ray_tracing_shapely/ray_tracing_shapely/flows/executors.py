"""
Python-specific module: executors -- where a flow's long step runs

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
PYTHON-SPECIFIC MODULE: executors
===============================================================================
A flow stays where its caller is; a long step is a **job** handed to an
**executor**, which returns a **handle**. The flow keeps the handle in its
run record and follows it. It never looks for the work in the process list.

    Job        plain data: a procedure named by import path ("pkg.mod:fn"),
               JSON inputs, files by reference, an expected time (budget_s)
               and an optional hard limit (limit_s)
    Handle     plain data: which executor, the job's id, and what that
               executor needs to find the job again -- so a handle written
               to disk is followed after a restart (`executor_for`)
    JobStatus  queued | running | done | failed | cancelled | timed_out,
               or unknown: the executor has no record of the job

The executor interface is five calls: `submit(job) -> Handle`,
`status(handle)`, `result(handle)`, `cancel(handle)`, `logs(handle)`.

A procedure is `fn(inputs: dict, ctx: JobContext) -> JSON-able`. It reports
progress with `ctx.progress(done, total)`, which also raises `JobCancelled`
once a cancel was asked for: cancelling is cooperative first, and the
local executor stops the process only if the procedure does not respond.

Two executors here:

- `InProcessExecutor`: runs the job at `submit`, in the calling thread. For
  tests and short steps. Its jobs live only as long as the process.
- `LocalProcessExecutor`: one worker process per job
  (`python -m ray_tracing_shapely.flows.worker <job folder>`), at low
  priority, writing `status.json` (with its own heartbeat), `result.json`
  and `log.txt` into the job's folder. Its handle survives a restart of the
  process that submitted it.

Remote executors implement the same five calls with the same `Job`:
`modal_executor.ModalExecutor` runs them on Modal. A remote job can fail to
start (its container failing before the procedure runs): ``start_limit_s``
bounds how long it may stay queued.

Only the standard library: a run's record, and the jobs behind it, are read
without the state-machine library [KC7].
===============================================================================
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import threading
import time
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional

#: The states a job can be in. `unknown`: the executor has no record of it.
JOB_STATES = ("queued", "running", "done", "failed", "cancelled", "timed_out", "unknown")
#: The states a job does not leave.
JOB_ENDED = ("done", "failed", "cancelled", "timed_out", "unknown")


class JobCancelled(Exception):
    """Raised inside a procedure, by `JobContext.progress` or
    `JobContext.check_cancelled`, once a cancel was asked for."""


@dataclass
class Job:
    """A unit of work, as plain data, so the same job runs in process, in a
    worker or remotely.

    Args:
        procedure: The function to run, by import path: ``"pkg.module:function"``.
        inputs: Its inputs, JSON only.
        files: Files it reads, by reference: ``{name: path}``.
        budget_s: The time it is expected to take (`budgets.estimate_s`). Past
            it, the run is flagged over budget and goes on.
        limit_s: A hard limit. Past it, the executor stops the job and it ends
            ``timed_out``. None (the default): no limit.
        label: A short name for listings.
        start_limit_s: How long the job may stay ``queued``. Past it, the
            flow following it cancels it and ends ``failed``, with the
            executor's log: a job that cannot start (a remote container
            failing on import, again and again) is stopped, not waited on.
            None: the executor's ``default_start_limit_s``, if it has one.
    """

    procedure: str
    inputs: Dict[str, Any] = field(default_factory=dict)
    files: Dict[str, str] = field(default_factory=dict)
    budget_s: Optional[float] = None
    limit_s: Optional[float] = None
    label: str = ""
    start_limit_s: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Job":
        d = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}   # fields this version does not know are dropped
        return cls(**d)


@dataclass
class Handle:
    """Where a submitted job is: the executor's kind, the job's id, and what
    that executor needs to find it again (``where``)."""

    executor: str
    job_id: str
    where: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Handle":
        return cls(**d)


@dataclass
class JobStatus:
    """A job's state as its executor sees it.

    Args:
        state: One of `JOB_STATES`.
        progress: The last ``ctx.progress`` report: ``done``, ``total``, ``note``.
        error: The traceback or reason, for ``failed``/``timed_out``/``unknown``.
        started_at, finished_at, updated_at: Unix times; ``updated_at`` is the
            job's own heartbeat.
        pid: The worker's process id, where there is one.
        telemetry: What the executor knows besides the state, as plain data:
            for a remote job, its queue, its estimated cost, the code it ran.
    """

    state: str
    progress: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    updated_at: Optional[float] = None
    pid: Optional[int] = None
    telemetry: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def ended(self) -> bool:
        return self.state in JOB_ENDED

    def elapsed_s(self, now: Optional[float] = None) -> Optional[float]:
        if self.started_at is None:
            return None
        return (self.finished_at or now or time.time()) - self.started_at


class JobContext:
    """What a procedure is given besides its inputs: where to write, its
    files, and the progress and cancel hooks."""

    def __init__(self, workdir: Path, files: Dict[str, str],
                 on_progress: Callable[[Dict[str, Any]], None],
                 is_cancelled: Callable[[], bool]) -> None:
        self.workdir = Path(workdir)
        self.files = dict(files)
        self._on_progress = on_progress
        self._is_cancelled = is_cancelled

    def cancelled(self) -> bool:
        return self._is_cancelled()

    def check_cancelled(self) -> None:
        if self._is_cancelled():
            raise JobCancelled("cancel requested")

    def progress(self, done: float, total: Optional[float] = None, note: str = "") -> None:
        """Report progress (rays traced, cells run). Raises `JobCancelled` if a
        cancel was asked for, so a loop that reports progress is cancellable."""
        self._on_progress({"done": done, "total": total, "note": note, "at": time.time()})
        self.check_cancelled()


def resolve_procedure(path: str) -> Callable[..., Any]:
    """The function named ``"pkg.module:function"``."""
    if ":" not in path:
        raise ValueError(f"a procedure is named 'package.module:function'; got {path!r}")
    mod_name, _, attr = path.partition(":")
    obj: Any = importlib.import_module(mod_name)
    for part in attr.split("."):
        obj = getattr(obj, part)
    if not callable(obj):
        raise ValueError(f"{path!r} is not callable")
    return obj


def procedure_path(fn: Callable[..., Any]) -> str:
    """The import path of a module-level function, for `Job.procedure`."""
    return f"{fn.__module__}:{fn.__qualname__}"


def pid_alive(pid: Optional[int]) -> bool:
    """Whether a process with this id exists. On Windows, through the process
    handle: `os.kill(pid, 0)` there would terminate the process."""
    if not pid:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":  # pragma: no cover - exercised on the Windows machine
        import ctypes
        kernel32 = ctypes.windll.kernel32
        h = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = kernel32.GetExitCodeProcess(h, ctypes.byref(code))
        kernel32.CloseHandle(h)
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


# ---------------------------------------------------------------------------
# In process
# ---------------------------------------------------------------------------

class InProcessExecutor:
    """Runs a job at `submit`, in the calling thread, and keeps its status and
    result in memory. A handle from another process, or from before a restart,
    is ``unknown``."""

    kind = "in_process"
    _jobs: Dict[str, Dict[str, Any]] = {}     # shared by every instance in a process

    def __init__(self, workdir: Optional[Path] = None) -> None:
        self.workdir = Path(workdir) if workdir else None

    def submit(self, job: Job) -> Handle:
        job_id = uuid.uuid4().hex[:12]
        rec: Dict[str, Any] = {"status": JobStatus("running", started_at=time.time(), pid=os.getpid()),
                               "result": None, "log": "", "cancel": False}
        rec["status"].updated_at = rec["status"].started_at
        self._jobs[job_id] = rec

        def on_progress(p: Dict[str, Any]) -> None:
            rec["status"].progress = p
            rec["status"].updated_at = p["at"]

        workdir = self.workdir / job_id if self.workdir else Path.cwd()
        if self.workdir:
            workdir.mkdir(parents=True, exist_ok=True)
        ctx = JobContext(workdir, job.files, on_progress, lambda: rec["cancel"])
        st = rec["status"]
        try:
            rec["result"] = resolve_procedure(job.procedure)(job.inputs, ctx)
            st.state = "done"
        except JobCancelled:
            st.state = "cancelled"
        except Exception:  # noqa: BLE001 -- a job's failure is its status, not the caller's exception
            st.state, st.error = "failed", traceback.format_exc()
        st.finished_at = st.updated_at = time.time()
        if (st.state == "done" and job.limit_s is not None and st.elapsed_s() > job.limit_s):
            st.state, st.error = "timed_out", f"took {st.elapsed_s():.1f} s, over the {job.limit_s} s limit"
        return Handle(self.kind, job_id, {"pid": os.getpid()})

    def _rec(self, handle: Handle) -> Optional[Dict[str, Any]]:
        if handle.where.get("pid") != os.getpid():
            return None
        return self._jobs.get(handle.job_id)

    def status(self, handle: Handle) -> JobStatus:
        rec = self._rec(handle)
        if rec is None:
            return JobStatus("unknown", error="an in-process job lives only in the process that ran it")
        return rec["status"]

    def result(self, handle: Handle) -> Any:
        rec = self._rec(handle)
        if rec is None or rec["status"].state != "done":
            raise RuntimeError(f"job {handle.job_id} has no result: {self.status(handle).state}")
        return rec["result"]

    def cancel(self, handle: Handle) -> JobStatus:
        rec = self._rec(handle)
        if rec is not None:
            rec["cancel"] = True
        return self.status(handle)

    def logs(self, handle: Handle) -> str:
        rec = self._rec(handle)
        return "" if rec is None else (rec["status"].error or "")


# ---------------------------------------------------------------------------
# A worker process on this machine
# ---------------------------------------------------------------------------

# How long a write or read of a job's JSON waits out a sharing violation. On
# Windows, replacing a file that another process holds open for reading fails
# with PermissionError, and so can opening one that is being replaced: the
# worker rewrites status.json on every progress report while the executor
# polls it, so the two collide now and then. Without the retry the collision
# surfaced in the worker's job as an error, and the job ended "failed".
_SHARING_RETRIES = 50
_SHARING_WAIT_S = 0.02


def _write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    for attempt in range(_SHARING_RETRIES):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if os.name != "nt" or attempt == _SHARING_RETRIES - 1:
                raise
            time.sleep(_SHARING_WAIT_S)


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    for attempt in range(_SHARING_RETRIES):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None
        except PermissionError:
            if os.name != "nt" or attempt == _SHARING_RETRIES - 1:
                raise
            time.sleep(_SHARING_WAIT_S)
    return None


class LocalProcessExecutor:
    """One worker process per job, at low priority, in a job folder under
    ``root``:

        <root>/<job_id>/job.json      the job, as submitted
                        status.json   the worker's status and heartbeat
                        result.json   the procedure's return value, once done
                        log.txt       the worker's stdout and stderr
                        cancel        present once a cancel was asked for

    Args:
        root: Where job folders are made.
        grace_s: After a cancel, how long the worker has to stop by itself
            before it is terminated.
        nice: How far to lower the worker's priority (POSIX ``nice``; on
            Windows, below-normal priority whenever it is not 0).
        python: The interpreter to run the worker with (default: this one).
    """

    kind = "local_process"
    _children: Dict[str, subprocess.Popen] = {}

    def __init__(self, root: Path, *, grace_s: float = 5.0, nice: int = 10,
                 python: Optional[str] = None) -> None:
        self.root = Path(root).resolve()   # the worker runs from its job folder: a relative root would not resolve there
        self.grace_s = grace_s
        self.nice = nice
        self.python = python or sys.executable

    def _dir(self, handle: Handle) -> Path:
        return Path(handle.where["job_dir"])

    def submit(self, job: Job) -> Handle:
        job_id = f"{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"
        d = self.root / job_id
        d.mkdir(parents=True, exist_ok=False)
        _write_json(d / "job.json", job.to_dict())
        _write_json(d / "status.json", JobStatus("queued", updated_at=time.time()).to_dict())
        kwargs: Dict[str, Any] = {}
        if os.name == "nt":  # pragma: no cover - exercised on the Windows machine
            if self.nice:
                kwargs["creationflags"] = 0x00004000  # BELOW_NORMAL_PRIORITY_CLASS
        else:
            kwargs["start_new_session"] = True
            if self.nice:
                n = self.nice
                kwargs["preexec_fn"] = lambda: os.nice(n)
        log = (d / "log.txt").open("w", encoding="utf-8")
        try:
            proc = subprocess.Popen([self.python, "-m", "ray_tracing_shapely.flows.worker", str(d)],
                                    stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                    cwd=str(d), **kwargs)
        finally:
            log.close()
        self._children[job_id] = proc
        return Handle(self.kind, job_id, {"job_dir": str(d.resolve()), "pid": proc.pid})

    def _alive(self, handle: Handle) -> bool:
        proc = self._children.get(handle.job_id)
        if proc is not None:                     # our own child: poll() also reaps it
            return proc.poll() is None
        return pid_alive(handle.where.get("pid"))

    def status(self, handle: Handle) -> JobStatus:
        d = self._dir(handle)
        raw = _read_json(d / "status.json")
        if raw is None:
            return JobStatus("unknown", error=f"no job folder at {d}")
        st = JobStatus(**raw)
        if st.ended:
            return st
        if not self._alive(handle):
            # the record says queued or running, and the worker is gone: it died
            # without writing its end (killed, out of memory, the machine restarted)
            raw = _read_json(d / "status.json") or raw   # it may have just finished
            st = JobStatus(**raw)
            if st.ended:
                return st
            st.state, st.finished_at = "failed", time.time()
            st.error = "the worker process ended without recording an end; see log.txt"
            _write_json(d / "status.json", st.to_dict())
            return st
        job = Job.from_dict(_read_json(d / "job.json") or {"procedure": "?"})
        if job.limit_s is not None and st.state == "running" and (st.elapsed_s() or 0.0) > job.limit_s:
            self._stop(handle, "timed_out", f"over the {job.limit_s} s limit")
            return JobStatus(**(_read_json(d / "status.json") or raw))
        return st

    def result(self, handle: Handle) -> Any:
        st = self.status(handle)
        if st.state != "done":
            raise RuntimeError(f"job {handle.job_id} has no result: {st.state}")
        return (_read_json(self._dir(handle) / "result.json") or {}).get("result")

    def _stop(self, handle: Handle, state: str, reason: str) -> None:
        d = self._dir(handle)
        (d / "cancel").write_text(reason, encoding="utf-8")
        deadline = time.time() + self.grace_s
        while self._alive(handle) and time.time() < deadline:
            time.sleep(0.05)
        if self._alive(handle):
            proc = self._children.get(handle.job_id)
            if proc is not None:
                proc.terminate()
                try:
                    proc.wait(timeout=self.grace_s)
                except subprocess.TimeoutExpired:
                    proc.kill()
            else:
                import signal
                try:
                    os.kill(handle.where["pid"], signal.SIGTERM)
                except (ProcessLookupError, OSError):
                    pass
        raw = _read_json(d / "status.json") or {}
        st = JobStatus(**raw) if raw else JobStatus(state)
        if st.state != "done":
            # the worker records "cancelled" when it stops by itself; a stop
            # for the limit is recorded as such whoever stopped it
            if state == "timed_out" or not st.ended:
                st.state, st.error = state, reason
            st.finished_at = st.finished_at or time.time()
            _write_json(d / "status.json", st.to_dict())

    def cancel(self, handle: Handle) -> JobStatus:
        st = self.status(handle)
        if not st.ended:
            self._stop(handle, "cancelled", "cancel requested")
        return self.status(handle)

    def logs(self, handle: Handle, tail: int = 4000) -> str:
        try:
            text = (self._dir(handle) / "log.txt").read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            return ""
        return text[-tail:]


#: Executors by kind, to follow a handle read back from a run record.
_EXECUTOR_KINDS: Dict[str, Callable[[Handle], Any]] = {
    InProcessExecutor.kind: lambda h: InProcessExecutor(),
    LocalProcessExecutor.kind: lambda h: LocalProcessExecutor(Path(h.where["job_dir"]).parent),
    "modal": lambda h: importlib.import_module(f"{__package__}.modal_executor").from_handle(h),
}


def register_executor_kind(kind: str, from_handle: Callable[[Handle], Any]) -> None:
    """Let `executor_for` follow handles of another executor (a remote one)."""
    _EXECUTOR_KINDS[kind] = from_handle


def executor_for(handle: Handle) -> Any:
    """An executor that can follow ``handle``: what a run record's handle is
    read back with, after a restart or from another process."""
    try:
        return _EXECUTOR_KINDS[handle.executor](handle)
    except KeyError:
        raise ValueError(f"no executor of kind {handle.executor!r} is registered") from None


def run_worker(job_dir: Path) -> int:
    """The worker's body (`python -m ray_tracing_shapely.flows.worker`): run the
    job in ``job_dir`` and record its status, heartbeat and result there."""
    d = Path(job_dir)
    job = Job.from_dict(json.loads((d / "job.json").read_text(encoding="utf-8")))
    now = time.time()
    st = JobStatus("running", started_at=now, updated_at=now, pid=os.getpid())
    lock = threading.Lock()

    def save() -> None:
        with lock:
            st.updated_at = time.time()
            _write_json(d / "status.json", st.to_dict())

    save()
    stop = threading.Event()

    def beat() -> None:   # the job's own heartbeat, so a slow job is not taken for a dead one
        while not stop.wait(5.0):
            save()

    threading.Thread(target=beat, daemon=True).start()

    def on_progress(p: Dict[str, Any]) -> None:
        st.progress = p
        save()

    ctx = JobContext(d, job.files, on_progress, lambda: (d / "cancel").exists())
    code = 0
    try:
        result = resolve_procedure(job.procedure)(job.inputs, ctx)
        _write_json(d / "result.json", {"result": result})
        st.state = "done"
    except JobCancelled:
        st.state = "cancelled"
    except Exception:  # noqa: BLE001 -- recorded as the job's status
        st.state, st.error = "failed", traceback.format_exc()
        print(st.error, file=sys.stderr)
        code = 1
    stop.set()
    st.finished_at = time.time()
    save()
    return code
