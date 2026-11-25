"""
Python-specific module: scene builder widget
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
The scene builder in a notebook cell
===============================================================================
``scene_builder(scene=None, path=None)`` shows a `SceneEditor` as an
``anywidget`` widget (the ``widgets`` extra). The page only draws: the SVG
the editor renders, the selection's handles, a palette and a property form.
It sends what the person does as the editor's own messages, and the editor's
new state comes back as ``state``. Hovering and the drag preview are the
page's; the drag itself is applied in Python, on release (24_p0 Decision 6).

The editor is ``widget.editor``; its scene ``widget.scene``. ``handle(msg)``
applies a message as the page would, so the widget is tested with no browser.
===============================================================================
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .editor import SceneEditor

_BUILDER_CLASS: Optional[type] = None


def _builder_class() -> type:
    """The widget class, made on first use, so importing this module needs no anywidget."""
    global _BUILDER_CLASS
    if _BUILDER_CLASS is not None:
        return _BUILDER_CLASS
    import anywidget  # noqa: PLC0415
    import traitlets  # noqa: PLC0415

    class SceneBuilder(anywidget.AnyWidget):
        """The scene builder. ``state`` is what the page draws."""

        _esm = _ESM
        _css = _CSS
        state = traitlets.Dict().tag(sync=True)

        def __init__(self, editor: SceneEditor, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.editor = editor
            self.on_msg(self._on_msg)
            self.refresh()

        @property
        def scene(self) -> Any:
            return self.editor.scene

        def _on_msg(self, _widget: Any, content: Any, _buffers: Any = None) -> None:
            self.handle(content)

        def handle(self, message: Dict[str, Any]) -> Dict[str, Any]:
            """Apply one message, as the page sends it (`SceneEditor.handle`); the new state."""
            if (message or {}).get("type") == "refresh":
                self.refresh()
                return self.state
            self.editor.handle(message or {})
            self.refresh()
            return self.state

        def refresh(self) -> None:
            from ..flows.widget import find_files  # noqa: PLC0415 -- the server serves this page without flows
            state = self.editor.state()
            state["files"] = find_files("*.scene.json")
            self.state = state

    _BUILDER_CLASS = SceneBuilder
    return SceneBuilder


def scene_builder(scene: Any = None, path: Optional[str] = None, **kwargs: Any) -> Any:
    """A scene builder widget over `scene`, or over the scene file at `path`.

    Keyword arguments go to `SceneEditor` (``width``, ``height``,
    ``quick_max_rays``). Needs the ``widgets`` extra.
    """
    return _builder_class()(SceneEditor(scene, path=path, **kwargs))


_ESM = r"""
const el = (tag, attrs = {}, ...kids) => {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "class") e.className = v;
    else if (v !== undefined && v !== null && v !== false) e.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids.flat(Infinity)) if (k !== null && k !== undefined && k !== false)
    e.append(k instanceof Node ? k : document.createTextNode(String(k)));
  return e;
};
const SVGNS = "http://www.w3.org/2000/svg";
const svgEl = (tag, attrs = {}) => {
  const e = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
};

// A number as shown: 12 significant digits, so 1e-15 of noise reads as 0.
const shown = (v) => (typeof v === "number" && Number.isFinite(v)) ? Number(v.toPrecision(12)) : v;

// A form field for a property (schema entry) or a recipe parameter; calls done(value).
function field(spec, value, done) {
  const t = spec.type || kindOf(spec.annotation);
  if (t === "boolean") {
    const c = el("input", {type: "checkbox"}); c.checked = !!value;
    c.addEventListener("change", () => done(c.checked)); return c;
  }
  if (t === "dropdown") {
    const s = el("select", {});
    for (const [v, label] of Object.entries(spec.options || {})) {
      const o = el("option", {value: v}, label); if (String(value) === v) o.selected = true; s.append(o);
    }
    s.addEventListener("change", () => { const n = Number(s.value); done(Number.isNaN(n) ? s.value : n); });
    return s;
  }
  if (t === "point") {
    const v = value || {x: 0, y: 0}, isList = Array.isArray(v);
    const xi = el("input", {type: "number", step: "any", value: shown(isList ? v[0] : v.x)});
    const yi = el("input", {type: "number", step: "any", value: shown(isList ? v[1] : v.y)});
    const go = () => done(isList || spec.annotation ? [Number(xi.value), Number(yi.value)]
                                                     : {x: Number(xi.value), y: Number(yi.value)});
    xi.addEventListener("change", go); yi.addEventListener("change", go);
    return el("span", {class: "rsb-point"}, "x", xi, "y", yi);
  }
  if (t === "number") {
    const i = el("input", {type: "number", step: "any", value: shown(value) ?? ""});
    i.addEventListener("change", () => done(i.value === "" ? null : Number(i.value))); return i;
  }
  const i = el("input", {type: "text", value: value === undefined || value === null ? "" :
                         (typeof value === "string" ? value : JSON.stringify(value))});
  i.addEventListener("change", () => { let v = i.value; try { v = JSON.parse(v); } catch (e) {} done(v); });
  return i;
}
function kindOf(annotation) {
  const a = String(annotation || "");
  if (/^(Optional\[)?(float|int)\]?$/.test(a)) return "number";
  if (/^(Optional\[)?bool\]?$/.test(a)) return "boolean";
  if (/Point|Tuple\[float, float\]/.test(a)) return "point";
  return "text";
}

function render({ model, el: root }) {
  const send = (m) => model.send(m);
  const memo = { recipe: null, args: {}, path: null };
  let drag = null;            // the page's own drag: start, current, the svg, the preview element

  const keys = (evt) => ({ ctrl: evt.ctrlKey || evt.metaKey, shift: evt.shiftKey, alt: evt.altKey });

  // The canvas is one element for the widget's life: its listeners and the pointer capture
  // survive every redraw, and during a drag only its drawing is replaced (paint).
  let canvasBox = null;
  const cur = () => model.get("state");
  const svgOf = () => canvasBox && canvasBox.querySelector("svg");
  const toSceneWith = (m, evt) => { const svg = svgOf(); const pt = svg.createSVGPoint();
    pt.x = evt.clientX; pt.y = evt.clientY; const p = pt.matrixTransform(m); return { x: p.x, y: -p.y }; };
  const toSceneNow = (evt) => toSceneWith(svgOf().getScreenCTM().inverse(), evt);
  const byUuid = () => Object.fromEntries((cur().objects || []).map((o) => [o.uuid, o]));

  function paint(s) {
    canvasBox.innerHTML = s.svg;
    const svg = svgOf();
    if (!svg) return;
    svg.removeAttribute("width"); svg.removeAttribute("height");
    const overlay = svgEl("g", { transform: "scale(1, -1)", class: "rsb-overlay" });
    svg.append(overlay);
    const sel = s.selected;
    if (sel) {
      for (const n of svg.querySelectorAll(`[data-uuid="${sel.uuid}"]`)) n.classList.add("rsb-selected");
      for (const h of sel.handles || [])
        overlay.append(svgEl("circle", { cx: h.x, cy: h.y, r: 4 / s.view.scale, class: "rsb-handle" }));
    }
    if (drag && !drag.pan) preview(svg, overlay, s);
  }

  // While an object is built its own rule draws it: the pointer's moves go to Python one at a
  // time, the newest kept, also between the clicks of a polygon.
  let moveBusy = false, moveNext = null;
  const building = () => { const st = cur(); return st && (st.constructing || (drag && st.tool && st.tool.kind === "primitive")); };
  const pushMove = (m) => { moveNext = m; if (!moveBusy) { moveBusy = true; const m2 = moveNext; moveNext = null; send(m2); } };
  model.on("change:state", () => {
    if (!moveBusy) return;
    if (moveNext) { const m2 = moveNext; moveNext = null; send(m2); } else moveBusy = false;
  });

  function canvas() {
    if (canvasBox) return canvasBox;
    const box = canvasBox = el("div", { class: "rsb-canvas" });
    box.addEventListener("pointermove", (evt) => {
      if (!svgOf()) return;
      if (drag && drag.pan) {
        const p = toSceneWith(drag.m0, evt), vb = drag.vb;
        drag.dx = p.x - drag.start.x; drag.dy = p.y - drag.start.y;
        svgOf().setAttribute("viewBox", `${vb[0] - drag.dx} ${-(vb[1] + vb[3]) + drag.dy} ${vb[2]} ${vb[3]}`);
        return;
      }
      if (building()) pushMove({ type: "move", ...toSceneNow(evt), ...keys(evt) });
      if (drag) {
        drag.now = toSceneNow(evt);
        const svg = svgOf(); preview(svg, svg.querySelector(".rsb-overlay"), cur());
        return;
      }
      for (const n of box.querySelectorAll(".rsb-hover")) n.classList.remove("rsb-hover");
      const hit = evt.target.closest && evt.target.closest("[data-uuid]");
      if (hit && byUuid()[hit.getAttribute("data-uuid")]) hit.classList.add("rsb-hover");
    });
    box.addEventListener("pointerdown", (evt) => {
      if (evt.button !== 0 || !svgOf()) return;
      box.setPointerCapture(evt.pointerId);
      const s = cur(), p = toSceneNow(evt);
      const hit = evt.target.closest && evt.target.closest("[data-uuid]");
      const uuid = hit ? hit.getAttribute("data-uuid") : null, o = uuid && byUuid()[uuid];
      drag = { start: p, now: p, uuid };
      if (!o && !s.tool && !s.constructing) {              // empty canvas: pan the view
        Object.assign(drag, { pan: true, m0: svgOf().getScreenCTM().inverse(), vb: s.view.viewbox, dx: 0, dy: 0 });
        return;
      }
      send({ type: "press", ...p, ...keys(evt), target: o ? o.name : undefined });
    });
    box.addEventListener("pointerup", (evt) => {
      if (!drag || !svgOf()) return;
      const s = cur();
      if (drag.pan) {
        const d = drag; drag = null;
        if (Math.hypot(d.dx, d.dy) * s.view.scale < 3) send({ type: "select", name: null });
        else send({ type: "view", pan: [-d.dx, -d.dy] });
        return;
      }
      const p = toSceneNow(evt), d = drag; drag = null;
      send({ type: "release", ...p, ...keys(evt) });
      const still = Math.hypot(p.x - d.start.x, p.y - d.start.y) * s.view.scale < 3;
      const o = d.uuid && byUuid()[d.uuid];
      if (still && o && !s.tool && (!s.selected || s.selected.name !== (o.owner || o.name)))
        send({ type: "select", name: o.name });
    });
    box.addEventListener("wheel", (evt) => {
      if (!svgOf()) return;
      evt.preventDefault();
      const p = toSceneNow(evt);
      send({ type: "view", zoom: evt.deltaY < 0 ? 1.15 : 1 / 1.15, x: p.x, y: p.y });
    }, { passive: false });
    return box;
  }

  // The drag preview: the whole object translated, or the handle following the pointer.
  function preview(svg, overlay, s) {
    const st = model.get("state"), info = st.drag;
    for (const n of overlay.querySelectorAll(".rsb-preview")) n.remove();
    if (!drag) return;
    const dx = drag.now.x - drag.start.x, dy = drag.now.y - drag.start.y;
    if (st.tool || st.constructing) {
      overlay.append(svgEl("line", { x1: drag.start.x, y1: drag.start.y, x2: drag.now.x, y2: drag.now.y,
                                     class: "rsb-preview rsb-rubber" }));
      return;
    }
    if (!info) return;
    const o = st.objects.find((x) => x.name === info.name);
    if (info.whole && o) {
      const owner = o.owner ? st.objects.filter((x) => x.owner === o.owner || x.name === o.owner) : [o];
      for (const part of owner)
        for (const n of svg.querySelectorAll(`[data-uuid="${part.uuid}"]`)) {
          if (n.dataset.t0 === undefined) n.dataset.t0 = n.getAttribute("transform") || "";
          n.setAttribute("transform", `translate(${dx} ${dy}) ${n.dataset.t0}`);
        }
    } else if (info.point) {
      overlay.append(svgEl("line", { x1: info.point.x, y1: info.point.y, x2: drag.now.x, y2: drag.now.y,
                                     class: "rsb-preview rsb-rubber" }));
      overlay.append(svgEl("circle", { cx: drag.now.x, cy: drag.now.y, r: 5 / s.view.scale,
                                       class: "rsb-preview rsb-handle" }));
    }
  }

  function palette(s) {
    const cur = s.tool && s.tool.name;
    const prims = s.palette.primitives.map((n) =>
      el("button", { class: "rsb-tool" + (cur === n ? " rsb-on" : ""),
                     onclick: () => { memo.recipe = null; send({ type: "tool", name: cur === n ? null : n }); } }, n));
    const select = el("select", {
      onchange: (e) => { memo.recipe = e.target.value || null; memo.args = {}; redraw(); } },
      el("option", { value: "" }, "Designed element…"),
      s.palette.recipes.map((r) => el("option", { value: r.name, selected: memo.recipe === r.name }, r.name)));
    const out = [el("div", { class: "rsb-row" },
      el("button", { class: "rsb-tool" + (!cur ? " rsb-on" : ""), onclick: () => send({ type: "tool", name: null }) }, "Select"),
      prims), el("div", { class: "rsb-row" }, select)];
    const r = memo.recipe && s.palette.recipes.find((x) => x.name === memo.recipe);
    if (r) {
      const rows = r.parameters.filter((p) => p.name !== "position").map((p) =>
        el("label", { class: "rsb-param" + (p.required ? " rsb-required" : "") }, p.name,
           field(p, memo.args[p.name] ?? p.default, (v) => { memo.args[p.name] = v; })));
      out.push(el("div", { class: "rsb-recipe" }, rows,
        el("button", { onclick: () => send({ type: "tool", name: r.name, args: memo.args }) },
           r.parameters.some((p) => p.name === "position") ? "Place: click on the canvas" : "Place")));
    }
    return out;
  }

  function inspector(s) {
    const sel = s.selected;
    if (!sel) return el("div", { class: "rsb-hint" }, s.tool ? `Placing ${s.tool.name}: click and drag on the canvas`
      : "Click an object to select it; drag it, or a handle, to change it. Shift snaps to directions, ctrl mirrors or copies, alt toggles the grid.");
    const rows = (sel.properties || sel.parameters || []).map((p) => {
      const key = p.key ?? p.name;
      return el("label", { class: "rsb-param" }, (p.label || p.name) + (p.unit ? ` (${p.unit})` : ""),
        field(p, p.value, (v) => send({ type: "set", name: sel.name, key, value: v })));
    });
    return el("div", {},
      el("div", { class: "rsb-title" }, `${sel.name}`, el("span", { class: "rsb-type" }, ` ${sel.recipe || sel.type}`)),
      rows,
      el("button", { class: "rsb-danger", onclick: () => send({ type: "delete", name: sel.name }) }, "Delete"));
  }

  function toolbar(s) {
    const hosted = s.host === "vscode";              // the host saves and opens the file itself
    const path = hosted ? null : el("input", { type: "text", list: "rsb-files", value: memo.path ?? s.path ?? "scene.scene.json",
                               oninput: (e) => { memo.path = e.target.value; } });
    return el("div", { class: "rsb-row rsb-bar" },
      el("button", { disabled: !s.can_undo, onclick: () => send({ type: "undo" }) }, "Undo"),
      el("button", { disabled: !s.can_redo, onclick: () => send({ type: "redo" }) }, "Redo"),
      el("button", { onclick: () => send({ type: "view", fit: true }) }, "Fit"),
      el("button", { onclick: () => send({ type: "view", zoom: 1.25 }) }, "+"),
      el("button", { onclick: () => send({ type: "view", zoom: 0.8 }) }, "−"),
      el("label", {}, (() => { const c = el("input", { type: "checkbox" }); c.checked = s.settings.snap_to_grid;
        c.addEventListener("change", () => send({ type: "settings", snap_to_grid: c.checked })); return c; })(), " grid"),
      el("input", { type: "number", class: "rsb-small", value: s.settings.grid_size, title: "grid size",
                    onchange: (e) => send({ type: "settings", grid_size: Number(e.target.value) }) }),
      !hosted && [path, el("datalist", { id: "rsb-files" }, (s.files || []).map((f) => el("option", { value: f }))),
        el("button", { onclick: () => send({ type: "save", path: path.value }) }, "Save"),
        el("button", { onclick: () => send({ type: "open", path: path.value }) }, "Open"),
        el("button", { title: "Write the scene in the web simulator's format (phydemo.app/ray-optics)",
                       onclick: () => send({ type: "export_web", path: path.value.replace(/(\.scene)?\.json$/, "") + ".web.json" }) },
           "Export for the web")]);
  }

  function redraw() {
    const s = model.get("state");
    if (!s || !s.svg) { root.replaceChildren(el("div", {}, "…")); return; }
    canvas();
    paint(s);
    if (drag) return;                                  // mid-drag: only the drawing changes
    const status = [s.error && el("span", { class: "rsb-error" }, s.error),
                    el("span", {}, `${s.objects.length} objects · ${s.trace.segments} ray segments`),
                    s.trace.note && el("span", { class: "rsb-note" }, s.trace.note),
                    s.notice && el("span", { class: "rsb-note" }, s.notice),
                    s.path && el("span", { class: "rsb-note" }, s.path)];
    root.replaceChildren(el("div", { class: "rsb" + (s.host === "vscode" ? " rsb-vscode" : "") },
      toolbar(s),
      el("div", { class: "rsb-main" },
        el("div", { class: "rsb-left" }, palette(s)),
        canvasBox,
        el("div", { class: "rsb-right" }, inspector(s))),
      el("div", { class: "rsb-status" }, status)));
  }
  model.on("change:state", redraw);
  redraw();
}
export default { render };
export { field, kindOf };
"""

_CSS = r"""
.rsb { font: 13px system-ui, sans-serif; color: #222; display: flex; flex-direction: column; gap: 6px; }
.rsb-row { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.rsb-bar input[type=text] { width: 16em; }
.rsb-small { width: 4.5em; }
.rsb-main { display: grid; grid-template-columns: 12em 1fr 16em; gap: 8px; align-items: start; }
.rsb-left .rsb-row { flex-direction: column; align-items: stretch; }
.rsb-tool { text-align: left; }
.rsb-on { background: #2b6cb0; color: white; border-color: #2b6cb0; }
.rsb-canvas { border: 1px solid #ccc; background: white; min-height: 300px; }
.rsb-canvas svg { width: 100%; height: auto; display: block; touch-action: none; cursor: crosshair; }
.rsb-canvas .rsb-hover { filter: drop-shadow(0 0 2px #2b6cb0); }
.rsb-canvas .rsb-selected { filter: drop-shadow(0 0 3px #d69e2e); }
.rsb-handle { fill: white; stroke: #d69e2e; stroke-width: 0.4; vector-effect: non-scaling-stroke; }
.rsb-rubber { stroke: #2b6cb0; stroke-dasharray: 2 2; fill: none; vector-effect: non-scaling-stroke; }
.rsb-param { display: grid; grid-template-columns: 1fr; gap: 2px; margin: 4px 0; }
.rsb-param input[type=number], .rsb-param input[type=text] { width: 100%; box-sizing: border-box; }
.rsb-point { display: flex; gap: 3px; align-items: center; }
.rsb-point input { width: 6em !important; }
.rsb-required { font-weight: 600; }
.rsb-recipe { border-top: 1px solid #ddd; padding-top: 4px; }
.rsb-title { font-weight: 600; margin-bottom: 4px; }
.rsb-type { font-weight: 400; color: #666; }
.rsb-hint { color: #555; }
.rsb-danger { color: #a00; margin-top: 6px; }
.rsb-status { display: flex; gap: 12px; color: #555; font-size: 12px; }
.rsb-error { color: #a00; }
.rsb-note { color: #777; }
.rsb-vscode { color: var(--vscode-foreground); }
.rsb-vscode .rsb-hint, .rsb-vscode .rsb-status, .rsb-vscode .rsb-type { color: var(--vscode-descriptionForeground); }
.rsb-vscode .rsb-error { color: var(--vscode-errorForeground); }
.rsb-vscode input, .rsb-vscode select { background: var(--vscode-input-background); color: var(--vscode-input-foreground);
  border: 1px solid var(--vscode-input-border, transparent); }
.rsb-vscode button { background: var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground);
  border: none; padding: 3px 8px; }
.rsb-vscode .rsb-on { background: var(--vscode-button-background); color: var(--vscode-button-foreground); }
"""

__all__ = ["scene_builder"]
