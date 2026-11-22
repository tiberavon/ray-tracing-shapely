"""
Python-specific module: transcript -- a flow run's record as a page
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
PYTHON-SPECIFIC MODULE: transcript
===============================================================================
A finished (or stopped) run, read from its folder and written as markdown: the
flow's diagram, then every box in the order it was entered -- what it asked,
what was answered, what was refused and why, what a check sent back, what a
working box did and the numbers it recorded -- then the result. It is the
static rendering of a flow for a reader without a kernel (a documentation
page, a field note), and needs only the run's record: the standard library,
never the machine that ran it (KC7).

    transcript_markdown(base_dir, run_id)    the page, as text
    write_transcript(base_dir, run_id, out)  the page and its diagram, in a folder

Every path the record holds is written relative to the page's folder, so a
page published from one machine names no folder on it.
===============================================================================
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from . import persistence

#: Fields of an event the transcript reads itself; any other is shown under the event.
_KNOWN = {"seq", "timestamp", "state", "attempt", "message", "field", "answer", "refused", "reason",
          "sent_back", "to", "traceback", "log_tail"}
#: A list longer than this is shown with its first items and a count.
MAX_ITEMS = 12
#: A value's JSON longer than this is cut, with a note.
MAX_CHARS = 1500


#: An absolute path inside a text: from a root or a drive letter, up to a space or a quote.
_PATH_IN_TEXT = re.compile(r"(?:[A-Za-z]:[\\/]|/)[^\s'\"`,;()\[\]{}<>|]+")


def _relpath(path: str, base: Path) -> str:
    try:
        return os.path.relpath(path, base).replace(os.sep, "/")
    except ValueError:                               # another drive (Windows)
        return Path(path).name


def _relative(value: Any, base: Optional[Path]) -> Any:
    """Every absolute path in ``value`` written relative to ``base``: a value that is a path,
    and a path inside a text (a refusal's "no file at ...")."""
    if isinstance(value, str):
        if base is None or len(value) > 100_000:
            return value
        if os.path.isabs(value) and "\n" not in value and " " not in value:
            return _relpath(value, base)
        return _PATH_IN_TEXT.sub(lambda m: _relpath(m.group(0), base) if len(Path(m.group(0)).parts) > 2
                                 else m.group(0), value)
    if isinstance(value, dict):
        return {k: _relative(v, base) for k, v in value.items()}
    if isinstance(value, list):
        return [_relative(v, base) for v in value]
    return value


def _trimmed(value: Any) -> Any:
    """Long lists cut to their first `MAX_ITEMS` and a count, at any depth."""
    if isinstance(value, list):
        head = [_trimmed(v) for v in value[:MAX_ITEMS]]
        return head + [f"... {len(value) - MAX_ITEMS} more"] if len(value) > MAX_ITEMS else head
    if isinstance(value, dict):
        return {k: _trimmed(v) for k, v in value.items()}
    return value


def _json_block(value: Any) -> str:
    text = json.dumps(_trimmed(value), indent=1, default=str)
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + f"\n... ({len(text) - MAX_CHARS} more characters)"
    return f"```json\n{text}\n```"


def _inline(value: Any) -> str:
    text = json.dumps(value, default=str)
    if len(text) > 200 or "\n" in text:
        return "\n\n" + _json_block(value)
    return f" `{text}`"


def _field_line(event: Dict[str, Any]) -> str:
    extra = {k: v for k, v in event.items() if k not in _KNOWN and v not in (None, [], {}, "")}
    if not extra:
        return ""
    simple = all(isinstance(v, (str, int, float, bool)) and len(str(v)) <= 80 for v in extra.values())
    if simple:
        return "\n  " + "; ".join(f"{k}: `{v}`" for k, v in extra.items())
    return "\n\n" + _json_block(extra)


def _flat(row: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, dict) and all(not isinstance(x, (dict, list)) for x in v.values()):
            out.update(_flat(v, f"{prefix}{k}."))
        else:
            out[f"{prefix}{k}"] = v
    return out


def _cell(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:.6g}"
    if isinstance(v, (dict, list)):
        text = json.dumps(v, default=str)
        return text if len(text) <= 40 else text[:37] + "..."
    return "" if v is None else str(v).replace("|", "\\|").replace("\n", " ")


def _is_rows(value: Any) -> bool:
    return isinstance(value, list) and len(value) > 0 and all(isinstance(r, dict) for r in value)


def _md_table(rows: List[Dict[str, Any]], limit: int = 50) -> str:
    flat = [_flat(r) for r in rows]
    keys: List[str] = []
    for r in flat:
        keys += [k for k in r if k not in keys]
    lines = ["| " + " | ".join(keys) + " |", "|" + "---|" * len(keys)]
    lines += ["| " + " | ".join(_cell(r.get(k)) for k in keys) + " |" for r in flat[:limit]]
    if len(flat) > limit:
        lines.append(f"\n... {len(flat) - limit} more rows")
    return "\n".join(lines)


def _result_lines(result: Any) -> List[str]:
    """A result: its lists of rows as tables, the rest as JSON."""
    if not isinstance(result, dict):
        return [_json_block(result)]
    tables = {k: v for k, v in result.items() if _is_rows(v)}
    rest = {k: v for k, v in result.items() if k not in tables}
    out = [_json_block(rest)] if rest else []
    for k, rows in tables.items():
        out += ["", f"**{k}**", "", _md_table(rows)]
    return out


def _figures(result: Any) -> List[Path]:
    """The pictures a result names: existing ``.svg`` and ``.png`` files among its top-level values."""
    if not isinstance(result, dict):
        return []
    found = []
    for v in result.values():
        if isinstance(v, str) and v.lower().endswith((".svg", ".png")) and os.path.isabs(v) and Path(v).is_file():
            found.append(Path(v))
    return found


def _event_lines(events: List[Dict[str, Any]]) -> List[str]:
    """Each event as one or more lines of the page, under the box it happened in."""
    out: List[str] = []
    box = None
    for e in events:
        state = e.get("state")
        if state != box and "answer" not in e and not e.get("refused"):
            out.append(f"\n### `{state}`\n")
            box = state
        field = e.get("field")
        if "answer" in e:
            out.append(f"- **Answered** `{field}`:{_inline(e['answer'])}")
        elif e.get("refused"):
            out.append(f"- **Refused**: {e.get('reason', '')}")
        elif e.get("sent_back"):
            to = f" to `{e['to']}`" if e.get("to") else ""
            out.append(f"- **Sent back**{to}: {e.get('reason') or e.get('message', '')}")
        elif field is not None:
            out.append(f"- **Asked** `{field}`: {e.get('message', '')}")
        else:
            out.append(f"- {e.get('message', '')}{_field_line(e)}")
        if e.get("traceback") and state == "failed":
            out.append("\n```text\n" + str(e["traceback"]).strip()[-MAX_CHARS:] + "\n```")
    return out


def transcript_markdown(base_dir: Union[str, Path], run_id: str, *, relative_to: Optional[Union[str, Path]] = None,
                        diagram: Optional[str] = "state.svg", attempts: str = "last",
                        figures: Optional[Dict[str, str]] = None) -> str:
    """A run's record as a markdown page.

    Args:
        base_dir: The flow's runs folder (its ``base_dir``).
        run_id: The run.
        relative_to: The folder the page will be read from: every path in the
            record is written relative to it. None: the run's own folder.
        diagram: The diagram's link in the page, or None for none.
        attempts: ``"last"`` (the page is the latest attempt; earlier ones are
            named, with the box each was reset from) or ``"all"``.
        figures: The pictures the result names (a plot), by their path, each
            with its link in the page. None: linked where they are.

    Returns:
        The page.

    Raises:
        FileNotFoundError: No record of the run in ``base_dir``.
    """
    base_dir = Path(base_dir)
    folder = base_dir / run_id                       # not persistence.run_dir: that would create it
    if not folder.is_dir():
        raise FileNotFoundError(f"no run {run_id!r} in {base_dir}")
    events = persistence.read_events(base_dir, run_id)
    rel = Path(relative_to) if relative_to is not None else folder
    rel = rel.resolve()
    heartbeat = persistence.read_heartbeats(base_dir).get(run_id, {})
    result = persistence.read_result(base_dir, run_id)
    flow = heartbeat.get("fsm_name") or run_id.rsplit("-", 2)[0]
    last = max((e.get("attempt", 1) for e in events), default=1)
    shown = events if attempts == "all" else [e for e in events if e.get("attempt", 1) == last]
    shown = _relative(shown, rel)

    lines = [f"# `{flow}`: run `{run_id}`", ""]
    state = heartbeat.get("state") or (result or {}).get("status") or (shown[-1]["state"] if shown else "?")
    started = events[0]["timestamp"] if events else None
    facts = [f"**Ended in** `{state}`" if heartbeat.get("terminal", state in ("done", "failed", "cancelled",
                                                                             "timed_out"))
             else f"**Now in** `{state}` (not finished)"]
    if started is not None:
        facts.append("started " + time.strftime("%Y-%m-%d %H:%M", time.localtime(started)))
    if result and result.get("wall_clock_s") is not None:
        facts.append(f"{result['wall_clock_s']:.1f} s")
    if last > 1:
        facts.append(f"attempt {last}")
    lines += [", ".join(facts) + ".", ""]
    if last > 1 and attempts == "last":
        for k in range(1, last):
            resets = [e for e in events if e.get("attempt", 1) == k and "reset" in str(e.get("message", ""))]
            where = f" (reset from `{resets[-1]['state']}`)" if resets else ""
            lines.append(f"- Attempt {k} was abandoned{where}.")
        lines.append("")
    if diagram and (folder / "state.svg").exists():
        lines += [f"![The flow's diagram, its last box marked]({diagram})", ""]
    lines += ["## The run"] + _event_lines(shown)
    lines += ["", "## Result", ""]
    if result is None:
        lines.append("No result: the run has not finished.")
    elif result.get("status") in ("failed", "cancelled", "timed_out"):
        lines.append(f"Ended `{result['status']}` in `{result.get('from_state')}`: {result.get('reason')}")
    else:
        pictures = _figures(result.get("result"))
        for pic in pictures:
            link = (figures or {}).get(str(pic)) or _relative(str(pic), rel)
            lines += [f"![{pic.name}]({link})", ""]
        lines += _result_lines(_relative(result.get("result"), rel))
    return "\n".join(lines).rstrip() + "\n"


def write_transcript(base_dir: Union[str, Path], run_id: str, out_dir: Union[str, Path], *,
                     name: str = "transcript.md", attempts: str = "last") -> Path:
    """The run's page and its diagram, written into ``out_dir``.

    Returns:
        The page's path. The diagram, when the run has one, is copied beside it
        as ``<run_id>.svg``, and each picture the result names as
        ``<run_id>_<name>``, so the folder stands on its own.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    svg = Path(base_dir) / run_id / "state.svg"
    link = None
    if svg.exists():
        link = f"{run_id}.svg"
        shutil.copyfile(svg, out_dir / link)
    figures = {}
    for pic in _figures((persistence.read_result(Path(base_dir), run_id) or {}).get("result")):
        copied = f"{run_id}_{pic.name}"
        shutil.copyfile(pic, out_dir / copied)
        figures[str(pic)] = copied
    page = out_dir / name
    page.write_text(transcript_markdown(base_dir, run_id, relative_to=out_dir, diagram=link, attempts=attempts,
                                        figures=figures), encoding="utf-8")
    return page


__all__ = ["transcript_markdown", "write_transcript"]
