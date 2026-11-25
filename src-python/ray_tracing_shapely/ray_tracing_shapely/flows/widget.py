"""
Python-specific module: widget -- a flow's form in a notebook cell
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
PYTHON-SPECIFIC MODULE: widget (the flow form)
===============================================================================
Any flow, shown in a notebook cell as a person answers it: its diagram with
the current box marked, the box's question drawn by the kind of answer it takes
(a path, a quantity with its unit, a whole number, a share range, a choice, yes
or no, JSON), the context it is answered from, the explanation, the last
refusal with its reason, a send-back, a job's progress, and the result once it
is done. Buttons answer, take the default, and reset.

    form = flow_form(flow)      # the widget; display it, or end a cell with it

Every piece of state and logic is the flow's, in Python. The page only draws
the flow's `question_state()` and sends back what the person did, as messages
(``{"kind": "answer", "value": ...}``, ``"default"``, ``"reset"``, ``"poll"``),
which `FlowForm.handle` applies through the flow's own `answer` -- the same
verb an agent's ``flow_answer`` uses. So the form can be driven, and tested,
without a browser, and another view (a VS Code editor, a solveit page) can be
drawn over the same messages.

Built on ``anywidget`` (the ``widgets`` extra), imported only when a form is
made: `flows` never imports it (KC7).
===============================================================================
"""

from __future__ import annotations

import fnmatch
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import persistence

_FORM_CLASS: Optional[type] = None


def _plain(value: Any) -> Any:
    """``value`` as JSON can carry it (numbers, strings, lists, dicts), anything else by ``str``."""
    return json.loads(json.dumps(value, default=str))


#: How deep, and how many entries, the search for a path question's files looks under the working directory.
SEARCH_DEPTH = 4
SEARCH_ENTRIES = 20_000
SUGGESTIONS = 20


def _shown(path: Path, cwd: Path) -> str:
    """A path as the page shows and answers it: relative to the working directory when under it."""
    try:
        return path.resolve().relative_to(cwd).as_posix()
    except ValueError:
        return str(path.resolve())


def find_files(pattern: Optional[str], cwd: Optional[Path] = None) -> List[str]:
    """The files under ``cwd`` that fit ``pattern``, newest first: a path question's suggestions.

    Looks `SEARCH_DEPTH` folders down, skipping hidden folders and ``__pycache__``, through at
    most `SEARCH_ENTRIES` entries, so a large tree costs a bounded time.
    """
    if not pattern:
        return []
    cwd = (cwd or Path.cwd()).resolve()
    found, seen = [], 0
    for root, dirs, files in os.walk(cwd):
        depth = len(Path(root).relative_to(cwd).parts)
        dirs[:] = [] if depth >= SEARCH_DEPTH else sorted(d for d in dirs if not d.startswith(".") and d != "__pycache__")
        seen += len(dirs) + len(files)
        found += [Path(root) / f for f in files if fnmatch.fnmatch(f, pattern)]
        if seen > SEARCH_ENTRIES:
            break
    found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [_shown(p, cwd) for p in found[:SUGGESTIONS]]


def list_folder(folder: Optional[str], pattern: Optional[str], cwd: Optional[Path] = None) -> Dict[str, Any]:
    """One folder as the page's browser shows it: its subfolders, and the files that fit ``pattern``
    (every file without one). A folder that does not exist shows the working directory instead."""
    cwd = (cwd or Path.cwd()).resolve()
    here = Path(folder).expanduser() if folder else cwd
    if not here.is_absolute():
        here = cwd / here
    here = here.resolve()
    if not here.is_dir():
        here = cwd
    try:
        entries = sorted(here.iterdir(), key=lambda p: p.name.lower())
    except OSError as exc:
        return {"dir": str(here), "parent": str(here.parent), "dirs": [], "files": [], "error": str(exc)}
    dirs = [p.name for p in entries if p.is_dir() and not p.name.startswith(".") and p.name != "__pycache__"]
    files = [p for p in entries if p.is_file() and (pattern is None or fnmatch.fnmatch(p.name, pattern))]
    others = sum(1 for p in entries if p.is_file()) - len(files)
    return {"dir": str(here), "parent": str(here.parent), "dirs": dirs, "pattern": pattern,
            "files": [{"name": p.name, "path": _shown(p, cwd)} for p in files], "others": others}


class FlowFormModel:
    """The flow form's model with no widget library: what the page draws (``state``,
    ``last``, ``browse``) and the messages it sends (`handle`). The ``anywidget``
    widget wraps it, and so does any other host (`ray_tracing_shapely.web`)."""

    def __init__(self, flow: Any) -> None:
        self.flow = flow
        self.state: Dict[str, Any] = {}
        self.last: Dict[str, Any] = {}
        self.browse: Dict[str, Any] = {}
        self.refresh()

    def traits(self) -> Dict[str, Any]:
        """What the page reads with ``model.get``."""
        return {"state": self.state, "last": self.last, "browse": self.browse}

    def handle(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Apply one message from the page, as the page sends it, and return what it now draws.

        ``{"kind": "answer", "value": v}`` answers the current question with ``v``
        (JSON, as an agent's ``flow_answer``); ``"default"`` takes its default;
        ``"reset"`` starts a new attempt at the first question; ``"poll"`` follows
        the run's job; ``"refresh"`` only redraws; ``{"kind": "browse", "dir": d}`` lists a
        folder for a path question (``browse``), its files filtered by the question's pattern.
        """
        kind = (message or {}).get("kind")
        flow = self.flow
        if kind == "answer":
            out = flow.answer(message.get("value"))
        elif kind == "default":
            out = flow.answer_default()
        elif kind == "reset":
            flow.reset()
            if "begin" in flow.machine.get_triggers(flow.state):
                flow.begin()
            out = {"accepted": True, "reset": True}
        elif kind == "poll":
            flow.poll()
            out = None
        elif kind == "refresh":
            out = None
        elif kind == "browse":
            question = self.state.get("question") or {}
            self.browse = _plain(list_folder(message.get("dir"), question.get("pattern")))
            return self.state
        else:
            out = {"accepted": False, "reason": f"unknown message kind {kind!r}"}
        if out is not None:
            self.last = _plain({k: out.get(k) for k in ("accepted", "reason", "sent_back", "reset")
                                if out.get(k) is not None})
        self.refresh()
        return self.state

    def refresh(self) -> None:
        """Read the flow again: its question, its diagram, its result once finished."""
        flow = self.flow
        state = flow.question_state()
        folder = persistence.run_dir(flow.base_dir, flow.run_id)
        svg = folder / "state.svg"
        state["diagram"] = svg.read_text(encoding="utf-8") if svg.exists() else None
        question = state.get("question") or {}
        if question.get("kind") == "path":
            state["files"] = {"cwd": str(Path.cwd().resolve()), "pattern": question.get("pattern"),
                              "matches": find_files(question.get("pattern"))}
        if flow.is_finished:
            saved = persistence.read_result(flow.base_dir, flow.run_id)
            state["result"] = (saved or {}).get("result")
            state["status"] = (saved or {}).get("status", flow.state)
        self.state = _plain(state)


def _form_class() -> type:
    """The widget class, made on first use, so importing this module needs no anywidget."""
    global _FORM_CLASS
    if _FORM_CLASS is not None:
        return _FORM_CLASS
    import anywidget  # noqa: PLC0415
    import traitlets  # noqa: PLC0415

    class FlowForm(anywidget.AnyWidget):
        """A flow's form. ``state`` is what the page draws; ``last`` the outcome of the last action."""

        _esm = _ESM
        _css = _CSS
        state = traitlets.Dict().tag(sync=True)
        last = traitlets.Dict().tag(sync=True)
        browse = traitlets.Dict().tag(sync=True)

        def __init__(self, flow: Any, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.model = FlowFormModel(flow)
            self.on_msg(self._on_msg)
            self._sync()

        @property
        def flow(self) -> Any:
            return self.model.flow

        def _on_msg(self, _widget: Any, content: Any, _buffers: Any = None) -> None:
            self.handle(content)

        def _sync(self) -> None:
            self.browse, self.last, self.state = self.model.browse, self.model.last, self.model.state

        def handle(self, message: Dict[str, Any]) -> Dict[str, Any]:
            """Apply one message from the page (`FlowFormModel.handle`); what it now draws."""
            out = self.model.handle(message)
            self._sync()
            return out

        def refresh(self) -> None:
            self.model.refresh()
            self._sync()

    _FORM_CLASS = FlowForm
    return FlowForm


def flow_form(flow: Any) -> Any:
    """A flow's form: an ``anywidget`` widget over ``flow``. Needs the ``widgets`` extra."""
    return _form_class()(flow)


# ---------------------------------------------------------------------------
# The page: draws `state`, sends messages. No state of its own beyond inputs.
# ---------------------------------------------------------------------------

_ESM = r"""
// The flow form's page. It draws the flow's question_state() and sends back what the person
// did; it keeps no state of the flow's, only what is being typed into the current question.

function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") e.className = v; else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "value") e.value = v; else if (k === "checked") e.checked = !!v;
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids.flat(Infinity)) if (k != null) e.append(k instanceof Node ? k : String(k));
  return e;
}

// ---- values, as tables -------------------------------------------------------------------

function flat(r) {
  const out = {};
  for (const [k, x] of Object.entries(r)) {
    if (x && typeof x === "object" && !Array.isArray(x) && Object.values(x).every(y => y === null || typeof y !== "object"))
      for (const [k2, y] of Object.entries(x)) out[k + "." + k2] = y;
    else out[k] = x;
  }
  return out;
}

function isRows(v) {
  return Array.isArray(v) && v.length > 0 && v.every(r => r && typeof r === "object" && !Array.isArray(r));
}

function cell(x) {
  if (x === null || x === undefined) return "";
  if (typeof x === "number") return Number.isInteger(x) ? String(x) : x.toPrecision(5);
  if (typeof x === "object") return JSON.stringify(x);
  return String(x);
}

function value(v, depth) {
  depth = depth || 0;
  if (isRows(v)) {
    const rows = v.map(flat);
    const keys = [...new Set(rows.flatMap(r => Object.keys(r)))];
    const table = el("table", {class: "rts-table"}, el("tr", {}, ...keys.map(k => el("th", {}, k))));
    for (const r of rows.slice(0, 60)) table.append(el("tr", {}, ...keys.map(k => {
      const x = r[k];
      if (isRows(x) && depth < 2) return el("td", {}, value(x, depth + 1));
      return el("td", {class: typeof x === "number" ? "rts-num" : ""}, cell(x));
    })));
    if (v.length > 60) table.append(el("tr", {}, el("td", {colspan: keys.length}, `... ${v.length - 60} more`)));
    return table;
  }
  if (v && typeof v === "object" && !Array.isArray(v) && depth < 2) {
    const dl = el("dl", {class: "rts-dl"});
    for (const [k, x] of Object.entries(v)) dl.append(el("dt", {}, k), el("dd", {}, value(x, depth + 1)));
    return dl;
  }
  if (typeof v === "string" && v.includes("\n")) return el("pre", {}, v);
  return el("span", {}, cell(v));
}

// ---- forms: a json answer asked field by field (fields.py, FORM_KINDS) ---------------------

const choice = c => (c !== null && typeof c === "object" && "value" in c) ? c : {value: c, label: String(c)};
export function choicesOf(f, vals) {
  if (f.choices) return f.choices.map(choice);
  if (f.choices_by) return ((f.choices_by.map || {})[vals[f.choices_by.field]] || []).map(choice);
  return [];
}
export const visible = (f, vals) => !f.when || (f.when.is || []).includes(vals[f.when.field]);

export function initVals(spec) {
  if (spec.kind === "list") return Array.from({length: Math.max(1, spec.min || 1)}, () => initVals(spec.item));
  const vals = {};
  for (const f of spec.fields || []) {
    if (f.default !== undefined && f.default !== null) vals[f.name] = f.default;
    else if (f.kind === "bool") vals[f.name] = false;
  }
  settle(spec, vals);
  return vals;
}

// A choice whose choices changed (another field moved) takes the first one it still has.
export function settle(spec, vals) {
  for (const f of spec.fields || []) {
    if (f.kind !== "choice" || f.optional) continue;
    const cs = choicesOf(f, vals);
    if (cs.length && !cs.some(c => c.value === vals[f.name])) vals[f.name] = cs[0].value;
  }
}

// The answer a form's values make: what the page sends, the same as a typed answer.
export function assemble(spec, vals) {
  if (spec.kind === "list") return vals.map(v => assemble(spec.item, v));
  const out = {};
  for (const f of spec.fields || []) {
    if (f.local || !visible(f, vals)) continue;
    const v = vals[f.name];
    if (f.kind === "bool") { out[f.name] = !!v; continue; }
    if (v === undefined || v === null || (typeof v === "string" && v.trim() === "")) continue;
    if (f.kind === "number" || f.kind === "integer") out[f.name] = Number(v);
    else if (f.kind === "numbers") out[f.name] = Array.isArray(v) ? v.map(Number)
      : String(v).split(/[\s,;]+/).filter(Boolean).map(Number);
    else out[f.name] = v;
  }
  return out;
}

function fieldInput(f, vals, changed) {
  const set = (x, redraw) => { vals[f.name] = x; changed(redraw); };
  if (f.kind === "choice") {
    const cs = choicesOf(f, vals);
    const s = el("select", {class: "rts-input", onchange: () => set(cs[s.selectedIndex - (f.optional ? 1 : 0)]?.value ?? null, true)});
    if (f.optional) s.append(el("option", {}, ""));
    cs.forEach(c => s.append(el("option", {}, c.label)));
    const i = cs.findIndex(c => c.value === vals[f.name]);
    s.selectedIndex = i < 0 ? 0 : i + (f.optional ? 1 : 0);
    return s;
  }
  if (f.kind === "bool")
    return el("input", {type: "checkbox", checked: !!vals[f.name], onchange: e => set(e.target.checked, false)});
  const typed = f.kind === "number" || f.kind === "integer";
  return el("input", {type: typed ? "number" : "text", step: f.kind === "integer" ? "1" : "any",
    class: "rts-input" + (typed ? " rts-short" : ""), value: vals[f.name] ?? "",
    placeholder: f.kind === "numbers" ? "1.33, 1.40, 1.47" : (f.optional ? "blank" : ""),
    oninput: e => set(e.target.value, false)});
}

function formView(spec, vals, changed) {
  if (spec.kind === "list") {
    const box = el("div", {class: "rts-form-list"});
    vals.forEach((item, i) => {
      const fs = el("fieldset", {class: "rts-fieldset"}, el("legend", {}, `${spec.item_label || "item"} ${i + 1}`));
      fs.append(formView(spec.item, item, changed));
      if (vals.length > (spec.min || 1)) fs.append(el("button", {class: "rts-secondary",
        onclick: () => { vals.splice(i, 1); changed(true); }}, `remove ${spec.item_label || "item"} ${i + 1}`));
      box.append(fs);
    });
    if (vals.length < (spec.max || 1)) box.append(el("button", {class: "rts-secondary",
      onclick: () => { vals.push(initVals(spec.item)); changed(true); }}, spec.add_label || "add"));
    return box;
  }
  const grid = el("div", {class: "rts-form"});
  for (const f of spec.fields || []) {
    if (!visible(f, vals)) continue;
    const redraws = (spec.fields || []).some(g => (g.when && g.when.field === f.name) || (g.choices_by && g.choices_by.field === f.name));
    const input = fieldInput(f, vals, (redraw) => { if (redraws || redraw) settle(spec, vals); changed(redraws && redraw); });
    grid.append(el("label", {class: "rts-label"}, f.label || f.name), el("div", {}, input,
      f.help ? el("span", {class: "rts-help"}, " " + f.help) : null));
  }
  return grid;
}

// ---- a path: the working directory, the files that fit, a browser ---------------------------

function pathView(q, s, memo, send, model, redraw) {
  const files = s.files || {};
  const box = el("div", {class: "rts-path"});
  const inp = el("input", {type: "text", class: "rts-input rts-wide", value: memo.text ?? (q.default ?? ""),
    placeholder: q.example || "", oninput: e => { memo.text = e.target.value; }});
  const fill = (p) => { memo.text = p; inp.value = p; };
  box.append(el("div", {class: "rts-row"}, inp,
    el("button", {onclick: () => send({kind: "answer", value: inp.value})}, "Answer"),
    el("button", {class: "rts-secondary", onclick: () => { memo.browsing = !memo.browsing;
      if (memo.browsing) send({kind: "browse", dir: memo.dir || files.cwd}); else redraw(); }},
      memo.browsing ? "Close the browser" : "Browse...")));
  box.append(el("div", {class: "rts-help"}, "Working directory: ", el("code", {}, files.cwd || "?"),
    " (a relative path is read from here)", files.pattern ? ["; files that fit: ", el("code", {}, files.pattern)] : null));
  if ((files.matches || []).length) {
    const found = el("div", {class: "rts-found"}, el("span", {class: "rts-help"}, "Found here: "));
    files.matches.forEach(m => found.append(el("button", {class: "rts-chip", onclick: () => fill(m)}, m)));
    box.append(found);
  } else if (files.pattern) {
    box.append(el("div", {class: "rts-help"}, `No ${files.pattern} file under the working directory: browse for one.`));
  }
  const b = model.get("browse") || {};
  if (memo.browsing && b.dir) {
    memo.dir = b.dir;
    const panel = el("div", {class: "rts-browser"}, el("div", {class: "rts-help"}, el("code", {}, b.dir)));
    const list = el("div", {class: "rts-entries"});
    list.append(el("button", {class: "rts-entry", onclick: () => send({kind: "browse", dir: b.parent})}, "↑ .."));
    (b.dirs || []).forEach(d => list.append(el("button", {class: "rts-entry rts-dir",
      onclick: () => send({kind: "browse", dir: b.dir + "/" + d})}, "▸ " + d + "/")));
    (b.files || []).forEach(f => list.append(el("button", {class: "rts-entry rts-file",
      onclick: () => { fill(f.path); memo.browsing = false; redraw(); }}, f.name)));
    if (b.others) list.append(el("span", {class: "rts-help"}, ` (${b.others} other files hidden)`));
    panel.append(list);
    box.append(panel);
  }
  return box;
}

// ---- the question ------------------------------------------------------------------------

function example(q) {
  const text = (q.example || "").replace(/^e\.g\.\s*/, "");
  for (const start of ["{", "["]) {
    const i = text.indexOf(start);
    if (i >= 0) { try { return JSON.stringify(JSON.parse(text.slice(i)), null, 1); } catch (e) { /* not JSON */ } }
  }
  return text;
}

function questionView(q, s, memo, send, model, redraw) {
  const form = el("div", {class: "rts-question"});
  const asForm = q.kind === "json" && s.form && !memo.asJson;
  form.append(el("div", {class: "rts-q"}, (asForm && s.form.prompt) || q.question),
              el("div", {class: "rts-why"}, `${q.kind}${q.unit ? ", in " + q.unit : ""} - ${q.why}`));
  const err = el("div", {class: "rts-refused"});
  const go = (v) => send({kind: "answer", value: v});
  const row = el("div", {class: "rts-row"});
  const dflt = q.default === undefined ? null : q.default;
  if (q.kind === "path") {
    form.append(pathView(q, s, memo, send, model, redraw));
  } else if (q.kind === "bool") {
    row.append(el("button", {onclick: () => go(true)}, "Yes"), el("button", {onclick: () => go(false)}, "No"));
  } else if (q.kind === "json" && s.form && !memo.asJson) {
    if (memo.vals === undefined) memo.vals = initVals(s.form);
    form.append(formView(s.form, memo.vals, (again) => { if (again) redraw(); }));
    row.append(el("button", {onclick: () => go(assemble(s.form, memo.vals))}, "Answer"),
      el("button", {class: "rts-secondary", onclick: () => {
        memo.asJson = true; memo.json = JSON.stringify(assemble(s.form, memo.vals), null, 1); redraw(); }}, "Edit as JSON"));
  } else if (q.kind === "json") {
    if (memo.json === undefined) memo.json = dflt !== null ? JSON.stringify(dflt) : "";
    const t = el("textarea", {class: "rts-input rts-json", rows: "5", placeholder: q.example || "",
      oninput: e => { memo.json = e.target.value; }});
    t.value = memo.json;
    form.append(t);
    row.append(el("button", {onclick: () => {
      try { go(JSON.parse(memo.json)); } catch (e) { err.textContent = "Not JSON: " + e.message; }
    }}, "Answer"), el("button", {class: "rts-secondary", onclick: () => { memo.json = example(q); redraw(); }}, "Use the example"));
    if (s.form) row.append(el("button", {class: "rts-secondary", onclick: () => { memo.asJson = false; redraw(); }}, "Back to the form"));
  } else {
    let inp;
    if (q.kind === "choice") {
      const cs = (q.choices || []).map(choice);
      inp = el("select", {class: "rts-input"}, ...cs.map(c => el("option", {}, c.label)));
      const i = cs.findIndex(c => c.value === (memo.text ?? dflt));
      inp.selectedIndex = i < 0 ? 0 : i;
      inp.addEventListener("change", () => { memo.text = cs[inp.selectedIndex].value; });
      inp.read = () => cs[inp.selectedIndex].value;
    } else if (q.kind === "share_range") {
      const r = memo.text || (Array.isArray(dflt) ? dflt : ["", ""]);
      const a = el("input", {type: "number", step: "0.01", class: "rts-input rts-short", value: r[0]});
      const b = el("input", {type: "number", step: "0.01", class: "rts-input rts-short", value: r[1]});
      inp = el("span", {}, a, " to ", b);
      inp.read = () => (memo.text = [parseFloat(a.value), parseFloat(b.value)]);
    } else {
      const typed = q.kind === "integer";
      inp = el("input", {type: typed ? "number" : "text", step: "1", class: "rts-input" + (typed ? " rts-short" : ""),
        value: memo.text ?? dflt ?? "", placeholder: q.example || (q.unit ? `a number in ${q.unit}` : ""),
        oninput: e => { memo.text = e.target.value; }});
      inp.read = () => typed ? (inp.value === "" ? null : Number(inp.value)) : inp.value;
    }
    row.append(inp, el("button", {onclick: () => go(inp.read())}, "Answer"));
  }
  if (!q.required) row.append(el("button", {class: "rts-secondary", onclick: () => send({kind: "default"})},
    "Use the default " + JSON.stringify(q.default)));
  form.append(row, err, el("div", {class: "rts-example"}, q.example || ""));
  return form;
}

// ---- the page ----------------------------------------------------------------------------

function render({ model, el: root }) {
  let timer = null;
  let memo = {key: null};
  const send = (m) => model.send(m);
  function draw() {
    const s = model.get("state") || {};
    const last = model.get("last") || {};
    const q = s.question;
    const key = q ? `${s.run_id}|${s.attempt}|${s.state}|${q.name}` : null;
    if (key !== memo.key) memo = {key};
    root.replaceChildren();
    const box = el("div", {class: "rts-flow"});
    box.append(el("div", {class: "rts-head"},
      el("b", {}, s.flow || "flow"), " ", el("code", {}, s.state || ""),
      s.attempt > 1 ? ` (attempt ${s.attempt})` : "", s.finished ? " - finished" : ""));
    if (s.diagram) {
      const d = el("details", {class: "rts-diagram"}, el("summary", {}, "Diagram"));
      const pic = el("div", {}); pic.innerHTML = s.diagram; d.append(pic);
      box.append(d);
    }
    // while a question is open, the question itself says what the box wants
    if (s.explanation && !q) box.append(el("div", {class: "rts-explain"}, s.explanation));
    if (last.sent_back) box.append(el("div", {class: "rts-back"},
      `Accepted, then sent back to ${last.sent_back.to}: ${last.sent_back.reason}`));
    if (last.accepted === false && last.reason) box.append(el("div", {class: "rts-refused"}, "Refused: " + last.reason));
    const job = s.job;
    if (job) {
      const p = job.progress || {};
      const pct = p.total ? Math.round(100 * (p.done || 0) / p.total) : null;
      box.append(el("div", {class: "rts-job"}, `${job.label || job.procedure}: ${job.state}`,
        pct !== null ? ` - ${p.done} of ${p.total} ${p.note || ""}` : "",
        job.budget_s ? ` (estimated ${Math.round(job.budget_s)} s)` : "",
        pct !== null ? el("progress", {max: "100", value: String(pct)}) : null));
      if (!timer) timer = setInterval(() => send({kind: "poll"}), 1000);
    } else if (timer) { clearInterval(timer); timer = null; }
    if (q) {
      box.append(questionView(q, s, memo, send, model, draw));
      if (s.context) {
        const c = el("details", {class: "rts-context"}, el("summary", {}, s.form ? "All the options, as data" : "What it is answered from"));
        c.append(value(s.context));
        box.append(c);
      }
    }
    if (s.finished) {
      if (s.status && s.status !== "done") box.append(el("div", {class: "rts-refused"}, `Ended ${s.status}.`));
      if (s.result !== undefined && s.result !== null) {
        const r = el("details", {class: "rts-result", open: true}, el("summary", {}, "Result"));
        r.append(value(s.result));
        box.append(r);
      }
    }
    box.append(el("div", {class: "rts-row rts-foot"},
      el("button", {class: "rts-secondary", onclick: () => send({kind: "reset"})}, "Reset"),
      el("button", {class: "rts-secondary", onclick: () => send({kind: "refresh"})}, "Refresh"),
      el("span", {class: "rts-id"}, s.run_id || "")));
    root.append(box);
  }
  model.on("change:state", draw);
  model.on("change:last", draw);
  model.on("change:browse", draw);
  draw();
  return () => { if (timer) clearInterval(timer); };
}

export default { render };
"""

_CSS = r"""
.rts-flow { font-family: var(--jp-ui-font-family, sans-serif); font-size: 13px; border: 1px solid #c8c8c8;
  border-radius: 6px; padding: 10px 12px; max-width: 900px; }
.rts-head { margin-bottom: 6px; }
.rts-explain { color: #444; margin: 6px 0; white-space: pre-wrap; }
.rts-q { font-weight: 600; margin-bottom: 2px; }
.rts-why, .rts-example, .rts-id { color: #777; font-size: 12px; }
.rts-row { display: flex; gap: 6px; align-items: center; margin: 6px 0; flex-wrap: wrap; }
.rts-input { min-width: 260px; padding: 3px 5px; font-family: var(--jp-code-font-family, monospace); }
.rts-short { min-width: 80px; width: 90px; }
.rts-json { width: 100%; min-width: 420px; }
.rts-refused { color: #b3261e; margin: 4px 0; }
.rts-back { color: #8a5a00; margin: 4px 0; }
.rts-job progress { margin-left: 8px; vertical-align: middle; }
.rts-secondary { opacity: 0.8; }
.rts-table { border-collapse: collapse; margin: 4px 0; }
.rts-table th, .rts-table td { border: 1px solid #ddd; padding: 2px 6px; text-align: left; vertical-align: top; }
.rts-table td.rts-num { text-align: right; font-variant-numeric: tabular-nums; }
.rts-dl dt { font-weight: 600; } .rts-dl dd { margin: 0 0 4px 14px; }
.rts-diagram svg { max-width: 100%; height: auto; }
.rts-foot { margin-top: 10px; }
.rts-wide { min-width: 480px; }
.rts-form { display: grid; grid-template-columns: max-content 1fr; gap: 4px 10px; align-items: center; margin: 6px 0; }
.rts-label { font-weight: 500; }
.rts-help { color: #777; font-size: 12px; }
.rts-fieldset { border: 1px solid #ddd; border-radius: 4px; margin: 6px 0; padding: 4px 8px; }
.rts-found { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; margin: 4px 0; }
.rts-chip { font-family: var(--jp-code-font-family, monospace); font-size: 12px; border-radius: 10px; }
.rts-browser { border: 1px solid #ddd; border-radius: 4px; padding: 4px 8px; margin: 4px 0; max-height: 260px; overflow: auto; }
.rts-entries { display: flex; flex-direction: column; align-items: flex-start; }
.rts-entry { border: none; background: none; cursor: pointer; padding: 1px 4px; text-align: left; }
.rts-entry:hover { background: #eef; }
.rts-dir { font-weight: 500; } .rts-file { font-family: var(--jp-code-font-family, monospace); }
"""


__all__ = ["flow_form"]
