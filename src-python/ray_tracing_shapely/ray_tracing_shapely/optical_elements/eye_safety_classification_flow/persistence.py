"""
Python-specific module: P-CLASSIFICATION-RUN persistence

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
PYTHON-SPECIFIC MODULE: persistence
===============================================================================
Filesystem-only run bundle for a classification-flow run, matching
analysis_run_registry's own P-RUN-BUNDLE shape (one directory per run,
schema independent of package version) -- see
dev_doc/architecture/components/eye_safety_classification_flow.md for the
full design and its "adapted rather than copied" note on why this is a
JSON file, not the SQLite table zm_monitor's fsm_base.py uses for the
same heartbeat concept (no existing database to justify that dependency
here).

Layout, under `base_dir`:

    <run_id>/
        inputs.json     -- the FRAME_INPUT payload, verbatim
        events.jsonl    -- one line per completed state, append-only
        result.json     -- final classification + wall-clock time, written once
    manifest.jsonl      -- one row appended per run
    heartbeats.json     -- dict keyed by run_id, rewritten atomically per transition

Deliberately pure I/O, with no dependency on `transitions`/`graphviz` --
testable on its own: FSM logic and rendering are kept separable, and this
module is separable from both. [KC7: the code that records a run never
loads the machinery that ran it.]
===============================================================================
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


#: zm_monitor's own STALENESS_S constant, adopted directly -- a run whose
#: heartbeat is older than this and not in a terminal state is presumed
#: crashed or stuck (relevant here specifically because FRAME_INPUT waits
#: on an external actor and can hang indefinitely).
STALENESS_S: float = 90.0


def make_run_id(standard: str) -> str:
    """`{standard}-{pid}-{unix time}` -- matches zm_monitor's own
    `f"{name}-{os.getpid()}-{int(time.time())}"` scheme exactly: unique enough for this project's
    actual concurrency, sortable by construction, no new dependency.
    """
    return f"{standard}-{os.getpid()}-{int(time.time())}"


def run_dir(base_dir: Path, run_id: str) -> Path:
    """The directory for one run, created if it does not exist."""
    d = Path(base_dir) / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _atomic_write_json(path: Path, data: Any) -> None:
    """Write `data` as JSON to `path` atomically (temp file + rename), so a
    reader (the dashboard, polling concurrently) never observes a
    partially-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def write_inputs(base_dir: Path, run_id: str, inputs: Dict[str, Any]) -> None:
    """Persist the FRAME_INPUT payload verbatim, once, at run start."""
    _atomic_write_json(run_dir(base_dir, run_id) / "inputs.json", inputs)


def append_event(base_dir: Path, run_id: str, event: Dict[str, Any]) -> int:
    """Append one line to `events.jsonl`, auto-assigning `seq` (0-based,
    the line's position in the file) so a reader never has to guess
    ordering from timestamps alone.

    Returns:
        The assigned `seq`.
    """
    path = run_dir(base_dir, run_id) / "events.jsonl"
    seq = 0
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            seq = sum(1 for _ in f)
    record = {"seq": seq, "timestamp": time.time(), **event}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return seq


def read_events(base_dir: Path, run_id: str) -> List[Dict[str, Any]]:
    """Read every event recorded for a run, in order. Empty list if the
    run has recorded none yet (or does not exist)."""
    path = run_dir(base_dir, run_id) / "events.jsonl"
    if not path.exists():
        return []
    events = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def write_result(base_dir: Path, run_id: str, result: Dict[str, Any]) -> None:
    """Persist the final classification + wall-clock time, once, on DONE."""
    _atomic_write_json(run_dir(base_dir, run_id) / "result.json", result)


def read_result(base_dir: Path, run_id: str) -> Optional[Dict[str, Any]]:
    """Read `result.json`, or None if the run has not finished yet."""
    path = run_dir(base_dir, run_id) / "result.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def append_manifest(
    base_dir: Path,
    run_id: str,
    standard: str,
    started_at: float,
    finished_at: Optional[float] = None,
    result: Optional[str] = None,
) -> None:
    """Append one row to the top-level `manifest.jsonl` -- what the
    dashboard's run-history index and a future agentic "list runs" tool
    both read (one row per *call*, not per run -- call once at start with
    `finished_at=None`, and the dashboard/a future tool reads the last row
    for a given `run_id` as that run's current manifest entry; simpler
    than rewriting the row in place, and append-only matches
    `events.jsonl`'s own discipline)."""
    path = Path(base_dir) / "manifest.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "run_id": run_id,
        "standard": standard,
        "started_at": started_at,
        "finished_at": finished_at,
        "result": result,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def read_manifest(base_dir: Path) -> List[Dict[str, Any]]:
    """Read every manifest row. Where a run_id has multiple rows (start +
    finish), the caller wants the last one -- see `latest_manifest_rows`."""
    path = Path(base_dir) / "manifest.jsonl"
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def latest_manifest_rows(base_dir: Path) -> List[Dict[str, Any]]:
    """One row per run_id -- the most recent manifest entry for each,
    most-recently-started first."""
    by_run: Dict[str, Dict[str, Any]] = {}
    for row in read_manifest(base_dir):
        by_run[row["run_id"]] = row
    return sorted(by_run.values(), key=lambda r: r["started_at"], reverse=True)


def update_heartbeat(
    base_dir: Path,
    run_id: str,
    fsm_name: str,
    state: str,
    detail: Optional[Dict[str, Any]] = None,
) -> None:
    """Upsert this run's row in the top-level `heartbeats.json` -- the
    "is this run alive right now" half, adapted from zm_monitor's
    `fsm_runs` SQLite table into a single atomically-rewritten JSON file
    (adapted rather than copied: there is no existing database here to
    justify SQLite for one small record).
    """
    path = Path(base_dir) / "heartbeats.json"
    heartbeats: Dict[str, Any] = {}
    if path.exists():
        heartbeats = json.loads(path.read_text(encoding="utf-8"))
    now = time.time()
    row = heartbeats.get(run_id, {})
    heartbeats[run_id] = {
        "fsm_name": fsm_name,
        "pid": os.getpid(),
        "state": state,
        "detail": dict(detail or {}),
        "started_at": row.get("started_at", now),
        "updated_at": now,
    }
    _atomic_write_json(path, heartbeats)


def read_heartbeats(base_dir: Path) -> Dict[str, Any]:
    path = Path(base_dir) / "heartbeats.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def is_stale(
    heartbeat_row: Dict[str, Any],
    terminal_states: tuple,
    staleness_s: float = STALENESS_S,
) -> bool:
    """A run whose heartbeat hasn't updated in `staleness_s` seconds and
    whose state is not terminal is presumed crashed/stuck -- zm_monitor's
    own `_is_stale` check, directly relevant here since `FRAME_INPUT`
    waits on an external actor (human or agent) and can hang indefinitely
    if that actor never responds."""
    age_s = time.time() - heartbeat_row["updated_at"]
    return age_s > staleness_s and heartbeat_row["state"] not in terminal_states
