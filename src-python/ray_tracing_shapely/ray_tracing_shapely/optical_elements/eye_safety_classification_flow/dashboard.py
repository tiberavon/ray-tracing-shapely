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

Live FSM state viewer for eye-safety classification runs.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

Adapted from a working prior implementation in a sibling project
(`zm_monitor/dashboard.py`) -- deliberately stdlib-only
(`http.server.BaseHTTPRequestHandler`), not FastHTML: that project
reserves FastHTML for a *separate* historical/trends dashboard, a
question this module has no equivalent of (see
dev_doc/architecture/components/eye_safety_classification_flow.md. The FSM
process itself writes `state.svg`/`events.jsonl`/`heartbeats.json`
(flow_base.py, persistence.py); this module only reads them -- no shared
in-memory state, no persistent connection, a `<meta http-equiv="refresh">`
full-page reload instead of a JavaScript polling loop.

Usage:
    python /path/to/eye_safety_classification_flow/dashboard.py \\
        --base-dir classification_runs --intake-base-dir intake_runs --port 8099
    # then open http://localhost:8099 in a browser on the same machine

Bound to 127.0.0.1 only -- a run-on-demand developer/reviewer tool, not a
service anyone needs to reach remotely (same reasoning as the prior art).

An optional `intake_base_dir` adds an "Intake runs" section
listing each in-progress `IEC62471IntakeFlow`/`IEC60825_1IntakeFlow` run
and its **current pending question** -- read the same way as everything
else here, straight off disk (the latest `events.jsonl` line for that
run, which is exactly the `FieldExplanation` message that state's own
`on_enter` already wrote -- no new persisted shape needed, and no live
connection to the running intake process; the dashboard still only
reads). This closes the loop `explain_current_state()` opened
for a caller *holding* the live object -- the dashboard is a caller that
never holds one, so it reads the same message back from `events.jsonl`
instead.
"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional

from . import persistence

_TERMINAL_STATES = frozenset({"done"})


def _is_stale(row: dict) -> bool:
    return persistence.is_stale(row, terminal_states=tuple(_TERMINAL_STATES))


def _detail_str(detail: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in (detail or {}).items()) or "&mdash;"


def _run_block_html(run_id: str, heartbeat: dict) -> str:
    flag = " &#9888; STALE (presumed crashed)" if _is_stale(heartbeat) else ""
    age_s = __import__("time").time() - heartbeat["updated_at"]
    svg_tag = (
        f'<img src="/svg/{run_id}.svg" style="max-width:640px;'
        f'border:1px solid #444;margin-top:4px" '
        f'onerror="this.style.display=\'none\'">'
    )
    return (
        f'<div style="margin-bottom:24px;padding:12px;border:1px solid #333">'
        f'<h2 style="margin:0 0 4px 0">{run_id} &mdash; {heartbeat["state"]}{flag}</h2>'
        f'<p style="margin:0;font-family:monospace;font-size:0.9em;color:#888">'
        f'pid={heartbeat["pid"]} | updated {age_s:.0f}s ago | '
        f'{_detail_str(heartbeat.get("detail"))}</p>'
        f'{svg_tag}'
        f'</div>'
    )


def _intake_block_html(run_id: str, heartbeat: dict, base_dir: Path) -> str:
    """One in-progress intake run -- its current state and the
    latest event's `message`, which for an `awaiting_<field>` state *is*
    that state's own `FieldExplanation` rendering (the question, why it
    matters, and a worked example) -- read straight off `events.jsonl`,
    no live connection to the intake process needed."""
    events = persistence.read_events(base_dir, run_id)
    pending = events[-1]["message"] if events else "(no events recorded yet)"
    flag = " &#9888; STALE (presumed crashed)" if _is_stale(heartbeat) else ""
    return (
        f'<div style="margin-bottom:16px;padding:12px;border:1px solid #333">'
        f'<h3 style="margin:0 0 4px 0">{run_id} &mdash; {heartbeat["state"]}{flag}</h3>'
        f'<p style="margin:0;font-family:monospace;font-size:0.9em">{pending}</p>'
        f'</div>'
    )


def _history_table_html(rows: list, heartbeats: dict) -> str:
    header = (
        '<tr style="text-align:left;border-bottom:1px solid #444">'
        '<th style="padding:4px 8px">run_id</th><th style="padding:4px 8px">standard</th>'
        '<th style="padding:4px 8px">state</th><th style="padding:4px 8px">result</th>'
        '<th style="padding:4px 8px">started</th><th style="padding:4px 8px">finished</th>'
        '</tr>'
    )
    lines = []
    for row in rows:
        heartbeat = heartbeats.get(row["run_id"], {})
        state = heartbeat.get("state", "?")
        flag = ' style="color:#e77"' if heartbeat and _is_stale(heartbeat) else ''
        lines.append(
            f'<tr{flag}><td style="padding:4px 8px">{row["run_id"]}</td>'
            f'<td style="padding:4px 8px">{row["standard"]}</td>'
            f'<td style="padding:4px 8px">{state}</td>'
            f'<td style="padding:4px 8px">{row.get("result") or "&mdash;"}</td>'
            f'<td style="padding:4px 8px">{row["started_at"]:.0f}</td>'
            f'<td style="padding:4px 8px">{row["finished_at"] or "&mdash;"}</td></tr>'
        )
    return (
        '<table style="border-collapse:collapse;width:100%;font-size:0.9em">'
        f'{header}{"".join(lines)}</table>'
    )


def _page_shell(title: str, body: str, refresh_s: int = 3) -> str:
    return (
        f"<html><head><title>eye_safety classification flow &mdash; {title}</title>"
        f"<meta http-equiv=\"refresh\" content=\"{refresh_s}\">"
        "<style>body{font-family:sans-serif;background:#1a1a1a;color:#ddd;"
        "max-width:900px;margin:24px auto;padding:0 16px}"
        "a{color:#6cf}code{background:#222;padding:1px 4px}"
        "table{margin-top:8px;border-collapse:collapse;width:100%;font-size:0.9em}"
        "th,td{padding:4px 8px;text-align:left}"
        "th{border-bottom:1px solid #444}</style>"
        f"</head><body>{body}</body></html>"
    )


def make_handler(base_dir: Path, intake_base_dir: Optional[Path] = None) -> type:
    """Build a `BaseHTTPRequestHandler` subclass bound to `base_dir` --
    a class factory rather than a module-level global, so tests can spin
    up a handler against an isolated `tmp_path` without process-wide
    state (matching this project's general test-isolation convention).

    Args:
        base_dir: Classification runs (`P-CLASSIFICATION-RUN`).
        intake_base_dir: Optional intake runs (`P-INTAKE-RUN`) --
            when given, the page also lists in-progress intake runs and
            each one's current pending question.
    """

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass  # quiet -- runs interactively, stdout noise isn't useful

        def _intake_section_html(self) -> str:
            if intake_base_dir is None:
                return ""
            intake_heartbeats = persistence.read_heartbeats(intake_base_dir)
            active = [
                (run_id, hb) for run_id, hb in intake_heartbeats.items()
                if hb.get("state") not in _TERMINAL_STATES
            ][:5]
            if not active:
                return ""
            body = "<h2>Intake runs (pending questions)</h2>"
            body += "".join(
                _intake_block_html(run_id, hb, intake_base_dir) for run_id, hb in active
            )
            return body

        def _page_html(self) -> str:
            manifest_rows = persistence.latest_manifest_rows(base_dir)
            heartbeats = persistence.read_heartbeats(base_dir)
            body = "<h1>eye_safety classification flow &mdash; live FSM state</h1>"
            body += self._intake_section_html()
            if not manifest_rows:
                body += (
                    "<p>No classification runs recorded yet &mdash; construct an "
                    "IEC62471ClassificationFlow/IEC60825_1ClassificationFlow and "
                    "call submit_input().</p>"
                )
                return _page_shell("FSM state", body)

            active = [
                r for r in manifest_rows
                if heartbeats.get(r["run_id"], {}).get("state") not in _TERMINAL_STATES
            ][:5]
            body += "".join(
                _run_block_html(r["run_id"], heartbeats[r["run_id"]])
                for r in active if r["run_id"] in heartbeats
            )
            body += "<h2>Run history</h2>"
            body += _history_table_html(manifest_rows, heartbeats)
            return _page_shell("FSM state", body)

        def do_GET(self):
            if self.path.startswith("/svg/"):
                name = self.path[len("/svg/"):]
                if "/" in name or ".." in name:
                    self.send_response(400)
                    self.end_headers()
                    return
                run_id = name[:-len(".svg")] if name.endswith(".svg") else name
                svg_path = persistence.run_dir(base_dir, run_id) / "state.svg"
                if svg_path.exists():
                    self.send_response(200)
                    self.send_header("Content-Type", "image/svg+xml")
                    self.end_headers()
                    self.wfile.write(svg_path.read_bytes())
                else:
                    self.send_response(404)
                    self.end_headers()
                return

            html = self._page_html().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html)

    return Handler


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-dir", type=Path, default=Path("classification_runs"))
    p.add_argument("--intake-base-dir", type=Path, default=None)
    p.add_argument("--port", type=int, default=8099)
    args = p.parse_args()
    print(
        f"eye_safety classification flow dashboard on "
        f"http://127.0.0.1:{args.port} (Ctrl-C to stop)"
    )
    handler = make_handler(args.base_dir, intake_base_dir=args.intake_base_dir)
    HTTPServer(("127.0.0.1", args.port), handler).serve_forever()


if __name__ == "__main__":
    main()
