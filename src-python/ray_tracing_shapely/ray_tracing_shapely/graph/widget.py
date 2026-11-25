"""
Python-specific module: graph editor widget
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
The graph editor in a notebook cell
===============================================================================
``graph_editor(doc=None, path=None)`` shows a `GraphEditor` as an
``anywidget`` widget (the ``widgets`` extra): a palette of blocks, the
canvas, and the selected node's inputs as a form. The page draws the nodes
and wires in SVG from ``state`` and sends what the person does as the
editor's messages; whether a wire is accepted, and why not, is the editor's
answer, so the page holds no rule. Panning, zooming and the drag previews
are the page's own.

The editor is ``widget.editor``, its document ``widget.document()``, its
runner ``widget.editor.runner``; **Run** runs the stale nodes, and a node's
computed scene opens in the scene builder with ``widget.open_scene(node)``.
``handle(msg)`` applies a message as the page would, so the widget is tested
with no browser.
===============================================================================
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .editor import GraphEditor

_GRAPH_CLASS: Optional[type] = None


def _graph_class() -> type:
    """The widget class, made on first use, so importing this module needs no anywidget."""
    global _GRAPH_CLASS
    if _GRAPH_CLASS is not None:
        return _GRAPH_CLASS
    import anywidget  # noqa: PLC0415
    import traitlets  # noqa: PLC0415

    class GraphCanvas(anywidget.AnyWidget):
        """The graph editor. ``state`` is what the page draws."""

        _esm = _ESM
        _css = _CSS
        state = traitlets.Dict().tag(sync=True)

        def __init__(self, editor: GraphEditor, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.editor = editor
            self.on_msg(self._on_msg)
            self.refresh()

        def document(self) -> Dict[str, Any]:
            """A copy of the graph document as it stands."""
            return self.editor.document()

        def open_scene(self, node: str, output: str = "scene", **kwargs: Any) -> Any:
            """The scene builder over a copy of a node's computed scene (an ``assemble`` node, once run).

            A copy, so an edit in the builder does not change the value the runner keeps; save it,
            and give the file to the graph, to use it.
            """
            from ..analysis import scene_file as sf  # noqa: PLC0415
            from ..builder.widget import scene_builder  # noqa: PLC0415
            live = self.editor.runner.outputs(node).get(output)
            if live is None:
                raise KeyError(f"{node} has no computed {output!r}")
            return scene_builder(sf.scene_from_dict(sf.scene_to_dict(live)), **kwargs)

        def _on_msg(self, _widget: Any, content: Any, _buffers: Any = None) -> None:
            self.handle(content)

        def handle(self, message: Dict[str, Any]) -> Dict[str, Any]:
            """Apply one message, as the page sends it (`GraphEditor.handle`); the new state."""
            if (message or {}).get("type") != "refresh":
                self.editor.handle(message or {})
            self.refresh()
            return self.state

        def refresh(self) -> None:
            from ..flows.widget import find_files  # noqa: PLC0415
            state = self.editor.state()
            state["files"] = find_files("*.graph.json")
            self.state = state

    _GRAPH_CLASS = GraphCanvas
    return GraphCanvas


def graph_editor(doc: Optional[Dict[str, Any]] = None, path: Optional[str] = None, runner: Any = None) -> Any:
    """A graph editor widget over the document `doc`, or over the graph file at `path`.

    `runner` is what **Run** uses (`GraphRunner`; give it an executor for long nodes). Needs the
    ``widgets`` extra.
    """
    return _graph_class()(GraphEditor(doc, path=path, runner=runner))


_ESM = r"""
const el = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "class") e.className = v;
    else if (k === "value") e.value = v;
    else if (v !== undefined && v !== null && v !== false) e.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids.flat(Infinity)) if (k !== null && k !== undefined && k !== false)
    e.append(k instanceof Node ? k : document.createTextNode(String(k)));
  return e;
};
const SVGNS = "http://www.w3.org/2000/svg";
const svgEl = (tag, attrs = {}, ...kids) => {
  const e = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  for (const k of kids) e.append(k instanceof Node ? k : document.createTextNode(String(k)));
  return e;
};

// --- the drawing's geometry: a node is a box, its shown inputs left, its outputs right ---
const W = 190, HEAD = 26, ROW = 18;
const shownInputs = (n) => n.inputs.filter((p) => p.shown);
function nodeHeight(n) { return HEAD + ROW * Math.max(1, shownInputs(n).length, n.outputs.length) + 6; }
function portAt(n, side, name) {
  const list = side === "in" ? shownInputs(n) : n.outputs;
  const i = list.findIndex((p) => p.name === name);
  return { x: n.at[0] + (side === "in" ? 0 : W), y: n.at[1] + HEAD + ROW * (Math.max(i, 0) + 0.5) };
}
function wirePath(a, b) {
  const dx = Math.max(40, Math.abs(b.x - a.x) / 2);
  return `M ${a.x} ${a.y} C ${a.x + dx} ${a.y}, ${b.x - dx} ${b.y}, ${b.x} ${b.y}`;
}
function typeText(t) {
  if (!t) return "";
  if (t.type === "quantity") return t.unit;
  if (t.type === "optional") return typeText(t.of) + "?";
  if (t.type === "list") return "[" + typeText(t.of) + "]";
  if (t.type === "choice") return t.options.join("|");
  return t.type;
}

// What a typed text field sends: the type's JSON form, or the text as it is, for Python to refuse.
function toValue(t, raw) {
  const s = String(raw ?? "").trim();
  if (s === "") return null;
  const k = t.type === "optional" ? t.of.type : t.type;
  if (k === "number" || k === "integer") { const n = Number(s); return Number.isNaN(n) ? s : n; }
  if (["quantity", "text", "rayfile", "profile", "trace", "rayfile_slice"].includes(k)) return s;
  try { return JSON.parse(s); } catch (e) { return s; }
}
const shownValue = (v) => v === null || v === undefined ? "" : (typeof v === "string" ? v : JSON.stringify(v));

// A form field for an input; calls done(value), null for "the block's default".
function field(p, done) {
  const t = p.type.type === "optional" ? p.type.of : p.type;
  const dflt = p.required ? "required" : `default: ${shownValue(p.default) || "none"}`;
  if (t.type === "bool" || t.type === "choice") {
    const opts = t.type === "bool" ? [true, false] : t.options;
    const s = el("select", {}, el("option", { value: "" }, `(${dflt})`),
      opts.map((o, i) => el("option", { value: String(i) }, String(o))));
    const at = opts.findIndex((o) => o === p.value);
    s.value = at < 0 ? "" : String(at);
    s.addEventListener("change", () => done(s.value === "" ? null : opts[Number(s.value)]));
    return s;
  }
  if (t.type === "position" || t.type === "direction") {
    const v = Array.isArray(p.value) ? p.value : ["", ""];
    const xi = el("input", { type: "number", step: "any", value: shownValue(v[0]), placeholder: "x" });
    const yi = el("input", { type: "number", step: "any", value: shownValue(v[1]), placeholder: "y" });
    const go = () => done(xi.value === "" && yi.value === "" ? null : [Number(xi.value), Number(yi.value)]);
    xi.addEventListener("change", go); yi.addEventListener("change", go);
    return el("span", { class: "rg-pair" }, xi, yi);
  }
  const long = ["list", "json", "glass_vertex", "scene_entry", "scene"].includes(t.type);
  const i = el(long ? "textarea" : "input", { type: long ? undefined : "text", rows: long ? 2 : undefined,
    value: shownValue(p.value), placeholder: t.type === "quantity" && p.required ? `in ${t.unit}` : dflt });
  i.addEventListener("change", () => done(toValue(p.type, i.value)));
  return i;
}

function render({ model, el: root }) {
  const send = (m) => model.send(m);
  const memo = { filter: "", path: null, notebook: "", wire: null, vb: null };
  let drag = null;
  let canvasBox = null, svg = null;
  const cur = () => model.get("state");
  const byId = () => Object.fromEntries((cur().nodes || []).map((n) => [n.id, n]));
  const toSvg = (evt, m) => { const pt = svg.createSVGPoint(); pt.x = evt.clientX; pt.y = evt.clientY;
    const p = pt.matrixTransform(m || svg.getScreenCTM().inverse()); return { x: p.x, y: p.y }; };

  function fit(s) {
    if (!s.nodes.length) return [0, 0, 900, 480];
    const xs = s.nodes.flatMap((n) => [n.at[0], n.at[0] + W]);
    const ys = s.nodes.flatMap((n) => [n.at[1], n.at[1] + nodeHeight(n)]);
    const x0 = Math.min(...xs) - 30, y0 = Math.min(...ys) - 30;
    const w = Math.max(Math.max(...xs) - x0 + 30, 400), h = Math.max(Math.max(...ys) - y0 + 30, 240);
    return [x0, y0, w, Math.max(h, w * 0.45)];
  }
  const setViewBox = () => svg.setAttribute("viewBox", memo.vb.join(" "));

  function canvas() {
    if (canvasBox) return canvasBox;
    canvasBox = el("div", { class: "rg-canvas", tabindex: "0" });
    svg = svgEl("svg", { preserveAspectRatio: "xMinYMin meet" });
    canvasBox.append(svg);
    canvasBox.addEventListener("pointerdown", (evt) => {
      if (evt.button !== 0) return;
      canvasBox.focus();
      canvasBox.setPointerCapture(evt.pointerId);
      const p = toSvg(evt), t = evt.target;
      const out = t.closest && t.closest(".rg-out"), wire = t.closest && t.closest(".rg-wire-hit"),
            node = t.closest && t.closest(".rg-node");
      if (out) {
        drag = { kind: "wire", from: out.dataset.end, start: portOf(out), now: p };
        const n = byId()[out.dataset.end.split(".")[0]];
        const port = n && n.outputs.find((o) => o.name === out.dataset.end.split(".")[1]);
        for (const e of svg.querySelectorAll(".rg-in"))
          if (port && port.targets.includes(e.dataset.end)) e.classList.add("rg-ok");
      } else if (wire) {
        memo.wire = { to: wire.dataset.to, index: wire.dataset.index === "" ? null : Number(wire.dataset.index),
                      from: wire.dataset.from };
        drag = null; redraw();
      } else if (node) {
        drag = { kind: "node", id: node.dataset.id, start: p, now: p, g: node };
      } else {
        drag = { kind: "pan", m0: svg.getScreenCTM().inverse(), start: p, vb: memo.vb.slice(), moved: 0 };
      }
    });
    canvasBox.addEventListener("pointermove", (evt) => {
      if (!drag) return;
      if (drag.kind === "pan") {
        const p = toSvg(evt, drag.m0), dx = p.x - drag.start.x, dy = p.y - drag.start.y;
        drag.moved = Math.hypot(dx, dy);
        memo.vb = [drag.vb[0] - dx, drag.vb[1] - dy, drag.vb[2], drag.vb[3]]; setViewBox(); return;
      }
      drag.now = toSvg(evt);
      if (drag.kind === "node") {
        drag.g.setAttribute("transform", `translate(${drag.now.x - drag.start.x} ${drag.now.y - drag.start.y})`);
      } else if (drag.kind === "wire") {
        let rubber = svg.querySelector(".rg-rubber");
        if (!rubber) { rubber = svgEl("path", { class: "rg-rubber" }); svg.append(rubber); }
        rubber.setAttribute("d", wirePath(drag.start, drag.now));
      }
    });
    canvasBox.addEventListener("pointerup", (evt) => {
      const d = drag; drag = null;
      if (!d) return;
      const scale = svg.getScreenCTM().a || 1;
      if (d.kind === "pan") {
        if (d.moved * scale < 3) { memo.wire = null; send({ type: "select", id: null }); }
        return;
      }
      if (d.kind === "node") {
        const dx = d.now.x - d.start.x, dy = d.now.y - d.start.y, n = byId()[d.id];
        if (Math.hypot(dx, dy) * scale < 3) { memo.wire = null; send({ type: "select", id: d.id }); }
        else send({ type: "move", id: d.id, at: [Math.round(n.at[0] + dx), Math.round(n.at[1] + dy)] });
        return;
      }
      if (d.kind === "wire") {
        const under = document.elementFromPoint(evt.clientX, evt.clientY);
        const input = under && under.closest && under.closest(".rg-in");
        redraw();                       // the rubber band and the lit inputs go, whatever the answer
        if (input) send({ type: "connect", from: d.from, to: input.dataset.end });
      }
    });
    canvasBox.addEventListener("wheel", (evt) => {
      evt.preventDefault();
      const p = toSvg(evt), f = evt.deltaY < 0 ? 1 / 1.15 : 1.15, vb = memo.vb;
      memo.vb = [p.x - (p.x - vb[0]) * f, p.y - (p.y - vb[1]) * f, vb[2] * f, vb[3] * f]; setViewBox();
    }, { passive: false });
    canvasBox.addEventListener("keydown", (evt) => {
      if (evt.key !== "Delete" && evt.key !== "Backspace") return;
      const s = cur();
      if (memo.wire) { send({ type: "disconnect", to: memo.wire.to, index: memo.wire.index }); memo.wire = null; }
      else if (s.selected) send({ type: "delete", id: s.selected });
    });
    return canvasBox;
  }
  const portOf = (e) => ({ x: Number(e.getAttribute("cx")), y: Number(e.getAttribute("cy")) });

  function paint(s) {
    if (!memo.vb) memo.vb = fit(s);
    setViewBox();
    svg.replaceChildren();
    const nodes = byId(), wires = svgEl("g", {}), boxes = svgEl("g", {});
    for (const w of s.wires) {
      const [src, out] = w.from.split("."), [dst, inp] = w.to.split(".");
      if (!nodes[src] || !nodes[dst]) continue;
      const d = wirePath(portAt(nodes[src], "out", out), portAt(nodes[dst], "in", inp));
      const on = memo.wire && memo.wire.to === w.to && memo.wire.index === w.index && memo.wire.from === w.from;
      wires.append(svgEl("path", { d, class: "rg-wire" + (on ? " rg-wire-on" : "") }));
      wires.append(svgEl("path", { d, class: "rg-wire-hit", "data-to": w.to, "data-from": w.from,
                                   "data-index": w.index === null ? "" : w.index }));
    }
    for (const n of s.nodes) {
      const g = svgEl("g", { class: "rg-node" + (s.selected === n.id ? " rg-selected" : ""), "data-id": n.id });
      const [x, y] = n.at, h = nodeHeight(n);
      g.append(svgEl("rect", { x, y, width: W, height: h, rx: 5, class: "rg-box rg-" + n.kind }));
      const bar = svgEl("rect", { x: x + 1, y: y + 1, width: W - 2, height: 4, class: "rg-run rg-run-" + n.status });
      bar.append(svgEl("title", {}, n.status + (n.error ? `: ${n.error}` : "")));
      g.append(bar);
      g.append(svgEl("text", { x: x + 8, y: y + 17, class: "rg-head" }, n.id));
      g.append(svgEl("text", { x: x + W - 8, y: y + 17, class: "rg-block" }, n.block === n.id ? "" : n.block));
      shownInputs(n).forEach((p) => {
        const at = portAt(n, "in", p.name), need = p.required && !p.wired.length && p.value === null;
        const c = svgEl("circle", { cx: at.x, cy: at.y, r: 5, class: "rg-in" + (p.list ? " rg-list" : "") +
                                    (need ? " rg-need" : ""), "data-end": `${n.id}.${p.name}` });
        c.append(svgEl("title", {}, `${p.name}: ${typeText(p.type)}` + (p.doc ? `\n${p.doc}` : "")));
        g.append(c, svgEl("text", { x: at.x + 9, y: at.y + 4, class: "rg-port" + (need ? " rg-need-text" : "") },
          p.name + (p.value !== null && !p.wired.length ? " = " + shownValue(p.value).slice(0, 14) : "")));
      });
      n.outputs.forEach((p) => {
        const at = portAt(n, "out", p.name);
        const c = svgEl("circle", { cx: at.x, cy: at.y, r: 5, class: "rg-out", "data-end": `${n.id}.${p.name}` });
        c.append(svgEl("title", {}, `${p.name}: ${typeText(p.type)}`));
        g.append(c, svgEl("text", { x: at.x - 9, y: at.y + 4, class: "rg-port rg-port-out" }, p.name));
      });
      boxes.append(g);
    }
    svg.append(wires, boxes);
  }

  function palette(s) {
    const list = el("div", { class: "rg-blocks" });
    const fill = () => {
      const f = memo.filter.toLowerCase();
      list.replaceChildren(...s.palette.map((group) => {
        const blocks = group.blocks.filter((b) => !f || b.name.toLowerCase().includes(f));
        return blocks.length ? el("div", {}, el("div", { class: "rg-group" }, group.kind + "s"),
          blocks.map((b) => el("button", { class: "rg-tool", title: b.doc, onclick: () => {
            const vb = memo.vb || [0, 0, 900, 480];
            send({ type: "add", block: b.name, at: [Math.round(vb[0] + vb[2] / 2 - W / 2), Math.round(vb[1] + vb[3] / 3)] });
          } }, b.name))) : null;
      }));
    };
    fill();
    return [el("input", { type: "search", placeholder: "Find a block", value: memo.filter,
                          oninput: (e) => { memo.filter = e.target.value; fill(); } }), list];
  }

  function inspector(s) {
    if (memo.wire) {
      const w = memo.wire;
      return el("div", {}, el("div", { class: "rg-title" }, "Wire"), el("div", {}, `${w.from} → ${w.to}`),
        el("button", { class: "rg-danger", onclick: () => { memo.wire = null; send({ type: "disconnect", to: w.to, index: w.index }); } },
           "Remove the wire"));
    }
    const n = s.selected && byId()[s.selected];
    if (!n) return el("div", {},
      el("div", { class: "rg-hint" }, "Add a block from the palette. Drag from an output (right) to an input (left) to wire them; " +
         "an input that accepts the wire lights up. Click a node for its inputs; Delete removes what is selected."),
      el("label", { class: "rg-param" }, "Notes",
         el("textarea", { rows: 4, value: s.notes || "", onchange: (e) => send({ type: "notes", text: e.target.value }) })));
    const rows = n.inputs.map((p) => {
      const label = el("span", { class: p.required ? "rg-required" : "", title: p.doc || "" },
                       p.name, el("span", { class: "rg-type" }, ` ${typeText(p.type)}`));
      const body = p.wired.length
        ? el("div", {}, p.wired.map((f, k) => el("div", { class: "rg-wired" }, `← ${f} `,
            el("button", { title: "remove the wire", onclick: () => send({ type: "disconnect", to: `${n.id}.${p.name}`,
                                                                          index: p.list ? k : null }) }, "×"))))
        : field(p, (v) => send({ type: "set", id: n.id, input: p.name, value: v }));
      return el("label", { class: "rg-param" }, label, body);
    });
    const name = el("input", { type: "text", value: n.id, onchange: (e) => send({ type: "rename", id: n.id, to: e.target.value }) });
    return el("div", {},
      el("label", { class: "rg-param" }, el("span", { class: "rg-title" }, "Node"), name),
      el("div", { class: "rg-type", title: n.origin || "" }, `${n.block} (${n.kind})`),
      el("div", { class: "rg-doc" }, n.doc || ""),
      el("div", { class: "rg-runline rg-run-text-" + n.status }, n.status === "running" ? `running (${n.where})` : n.status),
      n.error && el("div", { class: "rg-error" }, n.error),
      s.values && el("div", { class: "rg-values" }, el("div", { class: "rg-title" }, "Computed"),
        Object.entries(s.values).map(([k, v]) => el("div", {}, el("b", {}, k), " ", el("code", {}, v)))),
      rows,
      el("button", { class: "rg-danger", onclick: () => send({ type: "delete", id: n.id }) }, "Delete the node"));
  }

  function toolbar(s) {
    const hosted = s.host === "vscode";              // the host keeps the file: no New, Open or Save here
    const path = el("input", { type: "text", list: "rg-files", value: memo.path ?? s.path ?? "design.graph.json",
                               oninput: (e) => { memo.path = e.target.value; } });
    const nb = el("input", { type: "text", placeholder: "notebook: next to the graph", value: memo.notebook,
                             oninput: (e) => { memo.notebook = e.target.value; } });
    return el("div", { class: "rg-row rg-bar" },
      el("button", { disabled: !s.can_undo, onclick: () => send({ type: "undo" }) }, "Undo"),
      el("button", { disabled: !s.can_redo, onclick: () => send({ type: "redo" }) }, "Redo"),
      el("button", { onclick: () => { memo.vb = fit(s); setViewBox(); } }, "Fit"),
      !hosted && [
        el("button", { onclick: () => { memo.path = null; memo.vb = null; send({ type: "new" }); } }, "New"),
        path, el("datalist", { id: "rg-files" }, (s.files || []).map((f) => el("option", { value: f }))),
        el("button", { onclick: () => { memo.vb = null; send({ type: "open", path: path.value }); } }, "Open"),
        el("button", { onclick: () => send({ type: "save", path: path.value }) }, "Save")],
      nb,
      el("button", { disabled: !s.order, title: s.order ? "write the notebook that runs this graph" : "finish the graph first",
                     onclick: () => send({ type: "compile", path: nb.value || null }) }, "Compile"),
      el("button", { disabled: !s.order || s.waiting.length > 0, class: "rg-runbtn",
                     title: "run the nodes that are stale; the rest are kept", onclick: () => send({ type: "run" }) },
         s.waiting.length ? "Running…" : "Run"));
  }

  function redraw() {
    const s = cur();
    if (!s || !s.nodes) { root.replaceChildren(el("div", {}, "…")); return; }
    canvas();
    paint(s);
    const status = [s.error && el("span", { class: "rg-error" }, s.error),
      s.notice && el("span", { class: "rg-note" }, s.notice),
      el("span", {}, s.order ? `${s.nodes.length} nodes; runs as ${s.order.join(" → ")}`
                             : `${s.nodes.length} nodes; not finished: ${s.missing.join("; ")}`)];
    root.replaceChildren(el("div", { class: "rg" },
      toolbar(s),
      el("div", { class: "rg-main" }, el("div", { class: "rg-left" }, palette(s)), canvasBox,
         el("div", { class: "rg-right" }, inspector(s))),
      el("div", { class: "rg-status" }, status)));
  }
  let pollTimer = null;
  const poll = () => {                         // a job is out: ask again until the run takes it on
    const s = cur();
    if (pollTimer || !s || !s.waiting || !s.waiting.length) return;
    pollTimer = setTimeout(() => { pollTimer = null; send({ type: "poll" }); }, 1000);
  };
  model.on("change:state", () => {
    const s = cur();
    poll();
    if (memo.wire && !s.wires.some((w) => w.to === memo.wire.to && w.from === memo.wire.from)) memo.wire = null;
    redraw();
  });
  redraw();
}
export default { render };
export { field, nodeHeight, portAt, toValue, typeText, wirePath };
"""

_CSS = r"""
.rg { font: 13px system-ui, sans-serif; color: #222; display: flex; flex-direction: column; gap: 6px; }
.rg-row { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.rg-bar input[type=text] { width: 14em; }
.rg-main { display: grid; grid-template-columns: 13em 1fr 17em; gap: 8px; align-items: start; }
.rg-left { display: flex; flex-direction: column; gap: 4px; max-height: 560px; }
.rg-blocks { overflow-y: auto; display: flex; flex-direction: column; }
.rg-group { font-weight: 600; color: #555; margin: 6px 0 2px; text-transform: capitalize; }
.rg-tool { text-align: left; display: block; width: 100%; }
.rg-canvas { border: 1px solid #ccc; background: #fbfbfb; min-height: 360px; outline: none; }
.rg-canvas:focus { border-color: #2b6cb0; }
.rg-canvas svg { width: 100%; height: 520px; display: block; touch-action: none; user-select: none; }
.rg-box { fill: white; stroke: #888; stroke-width: 1; }
.rg-box.rg-function { fill: #eef5ff; }
.rg-box.rg-recipe { fill: #f3fbef; }
.rg-box.rg-primitive { fill: #fff8ec; }
.rg-node { cursor: move; }
.rg-selected .rg-box { stroke: #d69e2e; stroke-width: 2.5; }
.rg-head { font-weight: 600; font-size: 12px; }
.rg-block { font-size: 10px; fill: #666; text-anchor: end; }
.rg-port { font-size: 11px; fill: #333; }
.rg-port-out { text-anchor: end; }
.rg-in, .rg-out { fill: white; stroke: #2b6cb0; stroke-width: 1.5; cursor: crosshair; }
.rg-out { fill: #2b6cb0; }
.rg-list.rg-in { stroke-dasharray: 2 1.5; }
.rg-need { stroke: #c53030; }
.rg-need-text { fill: #c53030; }
.rg-ok { fill: #68d391; stroke: #2f855a; r: 7; }
.rg-wire { fill: none; stroke: #4a5568; stroke-width: 1.6; }
.rg-wire-on { stroke: #d69e2e; stroke-width: 3; }
.rg-wire-hit { fill: none; stroke: transparent; stroke-width: 10; cursor: pointer; }
.rg-rubber { fill: none; stroke: #2b6cb0; stroke-dasharray: 4 3; stroke-width: 1.6; pointer-events: none; }
.rg-param { display: grid; grid-template-columns: 1fr; gap: 2px; margin: 5px 0; }
.rg-param input, .rg-param select, .rg-param textarea { width: 100%; box-sizing: border-box; }
.rg-pair { display: flex; gap: 3px; }
.rg-pair input { width: 50% !important; }
.rg-required { font-weight: 600; }
.rg-type { font-weight: 400; color: #666; font-size: 11px; overflow-wrap: anywhere; }
.rg-title { font-weight: 600; }
.rg-doc { color: #555; font-size: 12px; margin: 4px 0; }
.rg-wired { color: #2b6cb0; }
.rg-hint { color: #555; }
.rg-danger { color: #a00; margin-top: 6px; }
.rg-status { display: flex; flex-wrap: wrap; gap: 12px; color: #555; font-size: 12px; }
.rg-error { color: #a00; }
.rg-note { color: #777; }
.rg-run { stroke: none; pointer-events: none; }
.rg-run-fresh { fill: #48bb78; }
.rg-run-stale { fill: #cbd5e0; }
.rg-run-running { fill: #4299e1; }
.rg-run-failed { fill: #e53e3e; }
.rg-runline { font-size: 11px; margin: 2px 0; text-transform: capitalize; }
.rg-run-text-fresh { color: #2f855a; }
.rg-run-text-failed { color: #c53030; }
.rg-run-text-running { color: #2b6cb0; }
.rg-values { margin: 4px 0; font-size: 11px; word-break: break-all; }
.rg-values code { font-size: 11px; }
"""

__all__ = ["graph_editor"]
