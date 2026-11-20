#!/usr/bin/env python3
"""
Python-specific module: dashboard
Copyright 2026 ray-tracing-shapely authors and contributors

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
PYTHON-SPECIFIC MODULE: dashboard -- every flow run, live, in a browser
===============================================================================
A page served on this machine that shows the runs on record, read the same
way `flow_list` reads them (`runs.list_runs`): each run reconciled with its
process and its job, whatever the job's executor (in process, a local
worker, Modal).

    python -m ray_tracing_shapely.flows.dashboard              # every folder under ./flow_runs,
                                                               # rescanned on each reload
    python -m ray_tracing_shapely.flows.dashboard --base-dir flow_runs/17p6c_e3 --port 8101
    # then open http://127.0.0.1:8101 in a browser on the same machine

The page, reloaded every few seconds:
- **Needs attention:** the runs `list_runs` flags (crashed, uncollected,
  hung, not_started, never_finished), with what each flag means.
- **Live runs:** each one's state, its pending question, its job (executor,
  state, progress, time against budget), its last events and its state
  diagram.
- **Ended runs:** for a failed one, the reason and the tail of its job's log.
- **History:** every run, most recent first, with its estimated cost.
- **Money:** each run's and each experiment's estimated compute cost (the
  jobs' executor telemetry; a job on this machine is "local"), and a card
  with Modal's billed spend over the last 24 h and this month against the
  monthly credit. The card is read every 10 minutes by a background thread
  running ``python -m ray_tracing_shapely.flows.modal_executor spend
  --summary``: this module never imports Modal.

A folder that does not exist is refused at start, with the folders that do.
The page only reads: the runs write their own records (`flow_base`,
`persistence`), and a cancel or an answer goes through the flow tools.
Bound to 127.0.0.1. Only the standard library [KC7].

``make_handler(base_dir, intake_base_dir=...)`` keeps the eye-safety intake
section: in-progress intake runs and each one's pending question.

Adapted from a working prior implementation in a sibling project
(`zm_monitor/dashboard.py`): `http.server`, no persistent connection, a
`<meta http-equiv="refresh">` reload instead of a polling script (see
dev_doc/architecture/components/flows.md).
===============================================================================
"""
from __future__ import annotations

import argparse
import difflib
import errno
import html
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse

from . import persistence
from .runs import list_runs

_TERMINAL_STATES = frozenset({"done", "failed", "cancelled", "timed_out"})
#: What each run-list flag means, for the page.
FLAG_MEANING = {
    "crashed": "not finished, and nothing is working on it: its process is gone and it has no job alive",
    "uncollected": "its job ended and nobody has polled the run since",
    "hung": "its job started and is silent, or over its budget",
    "not_started": "its job is still queued past its start limit: waiting on the run cancels it",
    "never_finished": "the run log has a start and no finish, and nothing is running it",
}
_E = html.escape


def run_folders(root: Path) -> List[Path]:
    """The folders of runs under ``root``: itself, if it holds runs, and each subfolder that does."""
    def holds_runs(d: Path) -> bool:
        return (d / "heartbeats.json").exists() or (d / "manifest.jsonl").exists()
    if not root.is_dir():
        return []
    found = [root] if holds_runs(root) else []
    found += sorted(d for d in root.iterdir() if d.is_dir() and holds_runs(d))
    return found


def _when(t: Optional[float]) -> str:
    return time.strftime("%H:%M:%S", time.localtime(t)) if t else "&mdash;"


def _secs(s: Optional[float]) -> str:
    if s is None:
        return "&mdash;"
    return f"{s:.0f} s" if s < 120 else f"{s / 60:.1f} min"


def _flags_html(flags: Sequence[str]) -> str:
    return " ".join(f'<span class="flag" title="{_E(FLAG_MEANING.get(f, ""))}">{_E(f)}</span>' for f in flags)


def _progress_html(job: Dict[str, Any]) -> str:
    p = job.get("progress") or {}
    done, total = p.get("done"), p.get("total")
    if done is None:
        return ""
    if total:
        pct = max(0.0, min(100.0, 100.0 * float(done) / float(total)))
        return (f'<div class="bar"><div style="width:{pct:.0f}%"></div></div>'
                f'<span class="dim">{_E(str(done))} of {_E(str(total))} {_E(p.get("note") or "")}</span>')
    return f'<span class="dim">{_E(str(done))} {_E(p.get("note") or "")}</span>'


def _last_events(base: Path, run_id: str, n: int = 4) -> List[Dict[str, Any]]:
    try:
        return persistence.read_events(base, run_id)[-n:]
    except (OSError, ValueError):
        return []


def _telemetry_html(t: Optional[Dict[str, Any]]) -> str:
    """An executor's telemetry: a queued job's queue, the code a job ran, its estimated cost."""
    if not t:
        return ""
    bits = []
    q = t.get("queue") or {}
    if q.get("unavailable"):
        bits.append(f"queue: {_E(q['unavailable'])}")
    elif q:
        bits.append(f"queue: backlog {_E(str(q.get('backlog')))}, containers started "
                    f"{_E(str(q.get('containers_started')))}, failed {_E(str(q.get('containers_failed')))}")
    if t.get("commit"):
        bits.append(f"code {_E(str(t['commit']))}")
    if t.get("cost_usd_est") is not None:
        bits.append(f"about ${float(t['cost_usd_est']):.5f} of compute ({_E(str(t.get('run_s')))} s)")
    return f'<p class="dim">{" | ".join(bits)}</p>' if bits else ""


def _job_html(job: Dict[str, Any], submitted_at: Optional[float], telemetry: Optional[Dict[str, Any]] = None) -> str:
    over = ' <span class="flag">over budget</span>' if job.get("over_budget") else ""
    elapsed = time.time() - submitted_at if submitted_at else None
    return (f'<p>job <b>{_E(job.get("label") or job.get("procedure") or "?")}</b> on '
            f'<code>{_E(job.get("executor", "?"))}</code>: <b>{_E(str(job.get("state")))}</b>{over} '
            f'<span class="dim">| {_secs(elapsed)} of a {_secs(job.get("budget_s"))} budget'
            f' | id {_E(str(job.get("job_id")))}</span></p>{_progress_html(job)}{_telemetry_html(telemetry)}')


def _live_block(row: Dict[str, Any], hb: Dict[str, Any]) -> str:
    base = Path(row["base_dir"])
    run_id = row["run_id"]
    events = _last_events(base, run_id)
    detail = hb.get("detail") or {}
    question = ""
    if str(row.get("state", "")).startswith("awaiting_") and events:
        question = f'<p class="q">{_E(events[-1].get("message", ""))}</p>'
    rec = detail.get("job") or {}
    job = _job_html(row["job"], rec.get("submitted_at"), rec.get("telemetry")) if row.get("job") else ""
    evs = "".join(f'<li><span class="dim">{_when(e.get("timestamp"))}</span> '
                  f'{_E(str(e.get("message", "")))}</li>' for e in events)
    svg = (f'<img src="/svg/{_E(base.name)}/{_E(run_id)}.svg" onerror="this.style.display=\'none\'">'
           if (persistence.run_dir(base, run_id) / "state.svg").exists() else "")
    return (f'<div class="run"><h3>{_run_link(base, run_id)} &mdash; {_E(str(row.get("state")))} '
            f'{_flags_html(row["flags"])}</h3>'
            f'<p class="dim">{_E(str(row.get("flow")))} | folder {_E(base.name)} | heartbeat '
            f'{_secs(row.get("age_s"))} ago | pid {_E(str(row.get("pid")))}</p>'
            f'{question}{job}<ul>{evs}</ul>{svg}</div>')


def _reason(base: Path, run_id: str) -> str:
    """Why a run ended: its result's reason, else its last event's message."""
    rec = persistence.read_result(base, run_id) or {}
    if rec.get("reason"):
        return str(rec["reason"])
    events = persistence.read_events(base, run_id)
    return str(events[-1].get("message", "")) if events else ""


def _log_tail(base: Path, run_id: str) -> str:
    return next((e["log_tail"] for e in reversed(persistence.read_events(base, run_id)) if e.get("log_tail")), "")


def _ended_block(row: Dict[str, Any], expected: Optional[str] = None) -> str:
    base = Path(row["base_dir"])
    run_id = row["run_id"]
    tail = _log_tail(base, run_id)
    tail_html = (f'<details><summary>log tail ({len(tail)} characters)</summary><pre>{_E(tail[-4000:])}</pre>'
                 '</details>') if tail else ""
    meant = ' <span class="ok">as expected</span>' if expected == row.get("state") else ""
    return (f'<div class="run ended"><h3>{_run_link(base, run_id)} &mdash; {_E(str(row.get("state")))}{meant}</h3>'
            f'<p><b>{_E(_reason(base, run_id))}</b></p>{tail_html}</div>')


def run_cost(base: Path, run_id: str) -> Dict[str, Any]:
    """A run's estimated compute cost: the sum of its jobs' ``cost_usd_est`` (their executors'
    telemetry), and where they ran. A job on this machine costs nothing billed."""
    executors, cost, known = set(), 0.0, False
    try:
        events = persistence.read_events(base, run_id)
    except (OSError, ValueError):
        events = []
    for e in events:
        if e.get("executor"):
            executors.add(e["executor"])
        t = e.get("telemetry") or {}
        if t.get("cost_usd_est") is not None:
            cost += float(t["cost_usd_est"])
            known = True
    return {"usd": cost if known else None, "executors": sorted(executors)}


def _cost_html(c: Dict[str, Any]) -> str:
    if c["usd"] is not None:
        return f"${c['usd']:.5f}"
    if c["executors"] and all(x in ("local_process", "in_process") for x in c["executors"]):
        return '<span class="dim">local</span>'
    return "&mdash;"


def _run_link(base: Path, run_id: str) -> str:
    return f'<a href="/run/{quote(base.name)}/{quote(run_id)}">{_E(run_id)}</a>'


def _history_html(rows: List[Dict[str, Any]], results: Dict[str, Any]) -> str:
    lines = []
    for r in rows:
        res = results.get(r["run_id"])
        res_txt = "&mdash;" if res is None else _E(str(res)[:120])
        cost = _cost_html(run_cost(Path(r["base_dir"]), r["run_id"]))
        lines.append(f'<tr><td>{_run_link(Path(r["base_dir"]), r["run_id"])}</td><td>{_E(str(r.get("flow")))}</td>'
                     f'<td>{_E(str(r.get("state")))}</td><td>{_flags_html(r["flags"])}</td>'
                     f'<td>{_when(r.get("started_at"))}</td><td>{cost}</td><td>{res_txt}</td></tr>')
    return ('<table><tr><th>run</th><th>flow</th><th>state</th><th>flags</th><th>started</th>'
            f'<th>est. cost</th><th>result</th></tr>{"".join(lines)}</table>')


_STYLE = ("body{font-family:sans-serif;background:#1a1a1a;color:#ddd;max-width:1000px;margin:24px auto;"
          "padding:0 16px}a{color:#6cf}code{background:#222;padding:1px 4px}h3{margin:0 0 4px 0}"
          "table{margin-top:8px;border-collapse:collapse;width:100%;font-size:0.85em}"
          "th,td{padding:4px 8px;text-align:left;vertical-align:top}th{border-bottom:1px solid #444}"
          ".run{margin-bottom:16px;padding:12px;border:1px solid #333}.ended{border-color:#733}"
          ".dim{color:#888;font-size:0.9em}.q{background:#223;padding:6px}"
          ".ok{background:#264;color:#dfd;padding:1px 6px;border-radius:3px;font-size:0.85em}"
          ".bad{background:#733;color:#fdd;padding:1px 6px;border-radius:3px;font-size:0.85em}"
          ".filters a{margin-right:10px}"
          ".card{border:1px solid #446;background:#1d2230;padding:10px 12px;margin:12px 0}"
          ".flag{background:#733;color:#fdd;padding:1px 6px;border-radius:3px;font-size:0.85em}"
          ".bar{background:#333;height:8px;width:300px;display:inline-block;margin-right:8px}"
          ".bar div{background:#4a8;height:8px}pre{background:#111;padding:8px;overflow-x:auto;"
          "font-size:0.8em;white-space:pre-wrap}img{max-width:640px;border:1px solid #444;margin-top:4px}"
          "ul{margin:4px 0;padding-left:20px;font-size:0.85em}")


def _page_shell(title: str, body: str, refresh_s: int = 5) -> str:
    refresh = f"<meta http-equiv=\"refresh\" content=\"{refresh_s}\">" if refresh_s else ""
    return (f"<html><head><title>{_E(title)}</title>{refresh}"
            f"<style>{_STYLE}</style></head><body>{body}</body></html>")


def _intake_block_html(run_id: str, heartbeat: dict, base_dir: Path) -> str:
    """One in-progress intake run: its state and the latest event's message, which for an
    ``awaiting_<field>`` state is that state's question."""
    events = persistence.read_events(base_dir, run_id)
    pending = events[-1]["message"] if events else "(no events recorded yet)"
    return (f'<div class="run"><h3>{_E(run_id)} &mdash; {_E(str(heartbeat["state"]))}</h3>'
            f'<p class="q">{_E(str(pending))}</p></div>')


def _experiment(hb: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    exp = (hb.get("detail") or {}).get("experiment")
    return exp if isinstance(exp, dict) and exp.get("name") else None


def _experiments_html(rows: List[Dict[str, Any]], heartbeats: Dict[str, Dict[str, Any]]) -> str:
    """Each experiment's cases against the end each was meant to reach: a run meant to fail that
    failed is a pass. The latest run of each case counts."""
    groups: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for r in sorted(rows, key=lambda r: r.get("started_at") or 0.0):     # later runs of a case win
        exp = _experiment(heartbeats.get(r["run_id"], {}))
        if exp:
            groups.setdefault(exp["name"], {})[exp.get("case", r["run_id"])] = {**r, "expected": exp.get("expected")}
    if not groups:
        return ""
    out = "<h2>Experiments</h2>"
    for name, cases in sorted(groups.items()):
        ended = [c for c in cases.values() if c["finished"]]
        good = [c for c in ended if c["state"] == c["expected"]]
        pending = len(cases) - len(ended)
        head = f"{len(good)} of {len(cases)} cases ended as expected" + (f", {pending} still running" if pending else "")
        costs = {case: run_cost(Path(c["base_dir"]), c["run_id"]) for case, c in cases.items()}
        total = sum(c["usd"] or 0.0 for c in costs.values())
        priced = any(c["usd"] is not None for c in costs.values())
        money = f' <span class="dim">| estimated compute ${total:.4f}</span>' if priced else ""
        mark = "ok" if len(good) == len(cases) else ("bad" if len(ended) > len(good) else "dim")
        lines = []
        for case, c in cases.items():
            verdict = ("&hellip; running" if not c["finished"] else
                       '<span class="ok">&#10003;</span>' if c["state"] == c["expected"] else '<span class="bad">&#10007;</span>')
            lines.append(f'<tr><td>{_E(case)}</td><td>{_E(str(c["expected"]))}</td><td>{_E(str(c["state"]))}</td>'
                         f'<td>{verdict}</td><td>{_cost_html(costs[case])}</td>'
                         f'<td>{_run_link(Path(c["base_dir"]), c["run_id"])}</td></tr>')
        out += (f'<h3>{_E(name)}: <span class="{mark}">{head}</span>{money}</h3><table><tr><th>case</th>'
                f'<th>meant to end</th><th>ended</th><th></th><th>est. cost</th><th>run</th></tr>{"".join(lines)}</table>')
    return out


class SpendWatcher:
    """Modal's billed spend, read every ``every_s`` in a background thread by running
    ``python -m ray_tracing_shapely.flows.modal_executor spend --summary``: the dashboard needs
    no Modal client of its own, and a page is never held up by the billing report."""

    def __init__(self, every_s: float = 600.0, hours: float = 24.0, command: Optional[List[str]] = None) -> None:
        import threading  # noqa: PLC0415
        self.every_s, self.hours = every_s, hours
        self.command = command or [sys.executable, "-m", "ray_tracing_shapely.flows.modal_executor", "spend",
                                   "--summary", "--hours", str(hours)]
        self.latest: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.checked_at: Optional[float] = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self) -> "SpendWatcher":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()

    def read_once(self) -> None:
        import json  # noqa: PLC0415
        import subprocess  # noqa: PLC0415
        try:
            proc = subprocess.run(self.command, capture_output=True, text=True, timeout=120)
            if proc.returncode != 0:
                lines = (proc.stderr or proc.stdout).strip().splitlines()
                raise RuntimeError(lines[-1] if lines else f"exit {proc.returncode}")
            self.latest, self.error = json.loads(proc.stdout), None
        except Exception as e:  # noqa: BLE001 -- no spend is a card that says why, not a dead page
            self.error = f"{type(e).__name__}: {e}"
        self.checked_at = time.time()

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.read_once()
            self._stop.wait(self.every_s)


def _spend_html(spend: Optional[SpendWatcher], monthly_credit: Optional[float],
                estimated_usd: float) -> str:
    """The spend card: Modal's billed spend over the last hours and this month, against the
    monthly credit, beside the runs' own estimate."""
    if spend is None:
        return ""
    est = f"runs shown here, estimated compute: ${estimated_usd:.4f}"
    if spend.latest is None:
        why = spend.error or "not read yet"
        return f'<div class="card"><b>Modal spend</b> <span class="dim">({_E(why)})</span><br>{est}</div>'
    d = spend.latest
    recent, month = d["recent"], d["month"]
    credit = ""
    if monthly_credit:
        left = monthly_credit - float(month["total_usd"])
        credit = (f' of the ${monthly_credit:.0f} monthly credit (<b>${left:.2f}</b> left, before the'
                  ' report\'s lag)')
    apps = ", ".join(f"{_E(k)} ${v:.4f}" for k, v in list(month.get("by_object", {}).items())[:5])
    return (f'<div class="card"><b>Modal spend</b>, billed: last {d.get("last_hours", 24):g} h '
            f'<b>${float(recent["total_usd"]):.4f}</b> | this month (UTC) <b>${float(month["total_usd"]):.4f}</b>'
            f'{credit}<br><span class="dim">by app this month: {apps or "none"} | latest billed hour '
            f'{_E(str(month.get("latest_hour") or recent.get("latest_hour") or "none"))} UTC (the report runs '
            f'behind by an hour or more) | read {_when(spend.checked_at)}</span><br><span class="dim">{est}; '
            'the bill also counts each '
            'container\'s start and idle time</span></div>')


def _read_all(base_dirs: Sequence[Path]) -> tuple:
    heartbeats: Dict[str, Dict[str, Any]] = {}
    results: Dict[str, Any] = {}
    for base in base_dirs:
        for run_id, hb in persistence.read_heartbeats(base).items():
            heartbeats[run_id] = hb
            rec = persistence.read_result(base, run_id)
            if rec is not None:
                results[run_id] = rec.get("result", rec.get("reason"))
    return heartbeats, results


def _filters_html(rows: List[Dict[str, Any]], query: Dict[str, str]) -> str:
    def link(label: str, **q: str) -> str:
        merged = {k: v for k, v in {**query, **q}.items() if v}
        return f'<a href="/?{urlencode(merged)}#history">{_E(label)}</a>'
    states = sorted({str(r.get("state")) for r in rows})
    folders = sorted({Path(r["base_dir"]).name for r in rows})
    parts = ["state: " + link("all", state="") + " ".join(link(s_, state=s_) for s_ in states)]
    if len(folders) > 1:
        parts.append("folder: " + link("all", folder="") + " ".join(link(f, folder=f) for f in folders))
    parts.append("flagged: " + link("only", flagged="1") + link("any", flagged=""))
    return '<p class="filters">' + " | ".join(parts) + "</p>"


def page_html(base_dirs: Sequence[Path], intake_base_dir: Optional[Path] = None,
              query: Optional[Dict[str, str]] = None, spend: Optional[SpendWatcher] = None,
              monthly_credit: Optional[float] = None) -> str:
    """The dashboard's page for these folders of runs. ``query`` filters the history:
    ``state``, ``folder``, ``flagged``."""
    query = query or {}
    rows = list_runs(base_dirs)
    heartbeats, results = _read_all(base_dirs)
    folders = ", ".join(f"<code>{_E(str(b))}</code>" for b in base_dirs)
    body = (f'<h1>Flow runs</h1><p class="dim">{len(rows)} runs in {folders} | {_when(time.time())} | '
            'each run id opens its own page</p>')
    body += _spend_html(spend, monthly_credit,
                        sum(run_cost(Path(r["base_dir"]), r["run_id"])["usd"] or 0.0 for r in rows))
    if intake_base_dir is not None:
        active = [(rid, hb) for rid, hb in persistence.read_heartbeats(intake_base_dir).items()
                  if hb.get("state") not in _TERMINAL_STATES][:5]
        if active:
            body += "<h2>Intake runs (pending questions)</h2>"
            body += "".join(_intake_block_html(rid, hb, intake_base_dir) for rid, hb in active)
    flagged = [r for r in rows if r["flags"]]
    if flagged:
        body += "<h2>Needs attention</h2><table><tr><th>run</th><th>flags</th><th>means</th></tr>"
        body += "".join(f'<tr><td>{_run_link(Path(r["base_dir"]), r["run_id"])}</td><td>{_flags_html(r["flags"])}</td>'
                        f'<td>{_E("; ".join(FLAG_MEANING.get(f, f) for f in r["flags"]))}</td></tr>'
                        for r in flagged) + "</table>"
    body += _experiments_html(rows, heartbeats)
    live = [r for r in rows if not r["finished"]][:10]
    body += "<h2>Live runs</h2>" + ("".join(_live_block(r, heartbeats.get(r["run_id"], {})) for r in live)
                                     or '<p class="dim">none</p>')
    bad = [r for r in rows if r["finished"] and r.get("state") in ("failed", "timed_out")]
    unexpected = [r for r in bad if (_experiment(heartbeats.get(r["run_id"], {})) or {}).get("expected") != r["state"]]
    if unexpected:
        body += "<h2>Ended badly</h2>" + "".join(_ended_block(r) for r in unexpected[:5])
    shown = [r for r in rows
             if (not query.get("state") or str(r.get("state")) == query["state"])
             and (not query.get("folder") or Path(r["base_dir"]).name == query["folder"])
             and (not query.get("flagged") or r["flags"])]
    body += (f'<h2 id="history">History ({len(shown)} of {len(rows)})</h2>' + _filters_html(rows, query)
             + (_history_html(shown, results) if shown else '<p class="dim">no runs match</p>'))
    return _page_shell("Flow runs", body)


def run_page_html(base: Path, run_id: str) -> str:
    """One run, whole: its state and flags, its experiment case, its job, every event, its
    result, its log tail and its state diagram."""
    row = next((r for r in list_runs([base]) if r["run_id"] == run_id), None)
    if row is None:
        return _page_shell(run_id, f'<p><a href="/">&larr; all runs</a></p><p>no run {_E(run_id)} in {_E(str(base))}</p>')
    hb = persistence.read_heartbeats(base).get(run_id, {})
    exp = _experiment(hb)
    body = (f'<p><a href="/">&larr; all runs</a></p><h1>{_E(run_id)}</h1>'
            f'<p><b>{_E(str(row.get("state")))}</b> {_flags_html(row["flags"])} '
            f'<span class="dim">| {_E(str(row.get("flow")))} | folder {_E(base.name)} | started '
            f'{_when(row.get("started_at"))}</span></p>')
    if exp:
        ok = row["finished"] and row["state"] == exp.get("expected")
        verdict = ('<span class="ok">as expected</span>' if ok else
                   '<span class="bad">not as expected</span>' if row["finished"] else "running")
        body += (f'<p>experiment <b>{_E(exp["name"])}</b>, case <b>{_E(str(exp.get("case")))}</b>, meant to end '
                 f'<b>{_E(str(exp.get("expected")))}</b>: {verdict}</p>')
    body += f'<p>estimated compute cost: {_cost_html(run_cost(base, run_id))}</p>'
    if row["finished"]:
        body += f'<p><b>{_E(_reason(base, run_id))}</b></p>'
    rec = (hb.get("detail") or {}).get("job") or {}
    if row.get("job"):
        body += "<h2>Job</h2>" + _job_html(row["job"], rec.get("submitted_at"), rec.get("telemetry"))
    events = persistence.read_events(base, run_id)
    ev_rows = []
    for e in events:
        extra = {k: v for k, v in e.items() if k not in ("seq", "timestamp", "state", "attempt", "message", "log_tail",
                                                        "traceback") and v is not None}
        ev_rows.append(f'<tr><td>{_when(e.get("timestamp"))}</td><td>{_E(str(e.get("state")))}</td>'
                       f'<td>{_E(str(e.get("message", "")))}</td><td class="dim">{_E(str(extra)[:300]) if extra else ""}</td></tr>')
    body += (f'<h2>Events ({len(events)})</h2><table><tr><th>time</th><th>state</th><th>message</th><th>details</th></tr>'
             f'{"".join(ev_rows)}</table>')
    result = persistence.read_result(base, run_id)
    if result is not None:
        import json
        body += f'<h2>Result</h2><pre>{_E(json.dumps(result, indent=1, default=str)[:6000])}</pre>'
    tail = _log_tail(base, run_id)
    if tail:
        body += f'<details><summary>log tail ({len(tail)} characters)</summary><pre>{_E(tail)}</pre></details>'
    if (persistence.run_dir(base, run_id) / "state.svg").exists():
        body += f'<h2>State diagram</h2><img src="/svg/{quote(base.name)}/{quote(run_id)}.svg">'
    return _page_shell(run_id, body, refresh_s=0 if row["finished"] else 5)


def make_handler(base_dir: Union[Path, Iterable[Path], None], intake_base_dir: Optional[Path] = None, *,
                 root: Optional[Path] = None, spend: Optional[SpendWatcher] = None,
                 monthly_credit: Optional[float] = None) -> type:
    """A `BaseHTTPRequestHandler` subclass bound to these folders of runs (a class factory, so
    tests use an isolated folder).

    Args:
        base_dir: A folder of runs, or several; None with ``root``.
        intake_base_dir: Optional eye-safety intake runs: the page then also lists each
            in-progress intake run's pending question.
        root: Look for folders of runs under it at every request, so a folder made after the
            dashboard started (a new experiment's) appears on the next reload.
        spend: Modal's billed spend, for the spend card (`SpendWatcher`); None: no card.
        monthly_credit: The plan's monthly credit, in US dollars, for the card.
    """
    fixed = ([] if base_dir is None else [Path(base_dir)] if isinstance(base_dir, (str, Path))
             else [Path(d) for d in base_dir])

    def current() -> List[Path]:
        if root is None:
            return fixed
        found = run_folders(Path(root))
        return fixed + [d for d in found if d not in fixed]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass  # quiet: it runs interactively, and request lines are noise

        def _page_html(self, query: Optional[Dict[str, str]] = None) -> str:
            dirs = current()
            if not dirs:
                return _page_shell("Flow runs", f'<h1>Flow runs</h1><p class="dim">no folders of runs under '
                                                f'{_E(str(root))} yet; this page reloads and will show them</p>'
                                   + _spend_html(spend, monthly_credit, 0.0))
            return page_html(dirs, intake_base_dir, query, spend, monthly_credit)

        def _send(self, code: int, body: bytes = b"", ctype: str = "text/html; charset=utf-8") -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            dirs = current()
            by_name = {d.name: d for d in dirs}
            if self.path.startswith("/svg/"):
                parts = self.path[len("/svg/"):].split("/")
                if len(parts) == 1 and dirs:
                    parts = [dirs[0].name] + parts
                if len(parts) != 2 or any(".." in p or not p for p in parts) or parts[0] not in by_name:
                    return self._send(400)
                run_id = parts[1][:-len(".svg")] if parts[1].endswith(".svg") else parts[1]
                svg = persistence.run_dir(by_name[parts[0]], run_id) / "state.svg"
                return self._send(200, svg.read_bytes(), "image/svg+xml") if svg.exists() else self._send(404)
            url = urlparse(self.path)
            if url.path.startswith("/run/"):
                parts = [unquote(p_) for p_ in url.path[len("/run/"):].split("/")]
                if len(parts) != 2 or parts[0] not in by_name or ".." in parts[1]:
                    return self._send(404, b"no such run")
                return self._send(200, run_page_html(by_name[parts[0]], parts[1]).encode())
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                body = self._page_html(query).encode()
            except Exception as e:  # noqa: BLE001 -- a record that cannot be read is shown, not a dead page
                body = _page_shell("Flow runs", f"<h1>Flow runs</h1><pre>{_E(type(e).__name__)}: "
                                                f"{_E(str(e))}</pre>").encode()
            self._send(200, body)

    return Handler


def _check_dirs(dirs: List[Path], root: Path) -> Optional[str]:
    """None if every folder exists; else what to say, with the folders that do."""
    missing = [d for d in dirs if not d.is_dir()]
    if not missing:
        return None
    known = run_folders(root)
    names = [str(k) for k in known]
    lines = []
    for d in missing:
        close = difflib.get_close_matches(str(d), names, n=3, cutoff=0.5)
        hint = f"; did you mean {' or '.join(close)}?" if close else ""
        lines.append(f"no folder {d}{hint}")
    lines.append("folders of runs under " + str(root) + ": " + (", ".join(names) if names else "none"))
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Every flow run, live, in a browser on this machine.")
    p.add_argument("--base-dir", type=Path, action="append", default=None,
                   help="a folder of runs (repeat for several); default: every folder under --root")
    p.add_argument("--root", type=Path, default=Path("flow_runs"), help="where to look for folders of runs")
    p.add_argument("--intake-base-dir", type=Path, default=None)
    p.add_argument("--port", type=int, default=8099)
    p.add_argument("--no-spend", action="store_true", help="no Modal spend card")
    p.add_argument("--spend-every", type=float, default=600.0, help="seconds between reads of Modal's billing")
    p.add_argument("--monthly-credit", type=float, default=30.0, help="the plan's monthly credit, US dollars")
    args = p.parse_args(argv)
    if args.base_dir:
        problem = _check_dirs(args.base_dir, args.root)
        if problem:
            print(problem, file=sys.stderr)
            return 2
    import importlib.util  # noqa: PLC0415
    spend = None
    if not args.no_spend and importlib.util.find_spec("modal") is not None:
        spend = SpendWatcher(every_s=args.spend_every).start()
    handler = make_handler(args.base_dir, intake_base_dir=args.intake_base_dir,
                           root=None if args.base_dir else args.root, spend=spend,
                           monthly_credit=args.monthly_credit)
    dirs = args.base_dir or [f"every folder under {args.root}, rescanned on each reload"]
    try:
        server = HTTPServer(("127.0.0.1", args.port), handler)
    except OSError as e:
        if e.errno == errno.EADDRINUSE:
            print(f"port {args.port} is in use; give another with --port", file=sys.stderr)
            return 2
        raise
    print(f"flow runs dashboard on http://127.0.0.1:{args.port}, reading {', '.join(map(str, dirs))} "
          "(Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
