"""
Python-specific module: test sculpt mode
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
The scene builder's sculpt mode: the messages, and the page in a browser
===============================================================================
On the Example 9.1 RR lens (Chaves) with a point source at E1 and a receiver
at R2's height:

- sculpt_start makes the lens a sculpted glass (undoable), cuts its light
  into tubes and aims its two edge bundles; its handles are listed;
- sculpt_preview estimates a move, traces nothing and changes nothing; past
  the edge's limit it is marked untrusted, and the drawing fades it;
- sculpt_apply records the edit, traces the light again, and learns the
  edge's limit from the estimate against the re-trace; an edit that breaks the
  outline is refused, reported as an event, the scene unchanged;
- events: a tube whose light the edit sends elsewhere is reported;
- sculpt_undo, and an undo past the start leaves the mode with the lens as
  it was; the settings; the refusals;
- the point source's marker is a few screen pixels, whatever the zoom;
- in headless Chrome, the page itself: Sculpt, a handle dragged previews,
  the release applies.
===============================================================================
"""

import http.server
import json
import math
import re
import shutil
import subprocess
import threading

import pytest

from ray_tracing_shapely.analysis import scene_file as sf
from ray_tracing_shapely.builder import SceneEditor
from ray_tracing_shapely.builder.widget import _CSS, _ESM
from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.light_source.point_source import PointSource
from ray_tracing_shapely.core.scene_objs.other.detector import Detector
from ray_tracing_shapely.optical_elements.prisms.rr_lens import RRLens


def _scene():
    scene = Scene()
    scene.ray_density = 2.0
    scene.add_object(RRLens(scene, (-1.0, 2.0), (1.0, 2.0), (-0.5, -2.0), (0.5, -2.0),
                            seed_n_angle_deg=303.3, seed_x_angle_deg=42.7, name="lens"))
    src = PointSource(scene, {"x": -1.0, "y": 2.0, "brightness": 0.5})
    src.name = "E1"
    scene.add_object(src)
    det = Detector(scene, {"p1": {"x": -0.6, "y": -2.0}, "p2": {"x": 0.6, "y": -2.0}})
    det.name = "R"
    scene.add_object(det)
    return scene


def _ok(e, message):
    s = e.handle(message)
    assert s["error"] is None, s["error"]
    return s


@pytest.fixture(scope="module")
def started():
    e = SceneEditor(_scene(), quick_max_rays=1000)
    s = _ok(e, {"type": "sculpt_start", "glass": "lens"})
    return e, s


def test_start_makes_a_sculpted_glass_and_cuts_its_light(started):
    e, s = started
    sc = s["sculpt"]
    assert sc["glass"] == "lens" and sc["receiver"] == "R"
    assert type(e._obj("lens")).__name__ == "SculptedGlass"
    assert e._obj("lens")._construction_args["base"]["recipe"] == "RRLens"
    assert len(sc["tubes"]) == 8 and [b["bundle_id"] for b in sc["bundles"]] == ["E1->R2", "E2->R1"]
    ids = {h["handle_id"] for h in sc["handles"]}
    assert "lens/N/12" in ids and "lens/X/20" in ids and len(ids) == len(sc["handles"])
    assert 'id="layer-sculpt"' in s["svg"] and "sculpt-bundle-ray" in s["svg"]
    assert s["trace"]["segments"] == 0                        # the rays are not drawn while sculpting
    assert s["can_undo"]


def test_a_preview_traces_nothing_and_changes_nothing(started):
    e, _ = started
    before = sf.scene_to_dict(e.scene)
    s = _ok(e, {"type": "sculpt_preview", "handle_id": "lens/X/20", "kind": "position", "delta": 1e-4})
    p = s["sculpt"]["preview"]
    assert p["trusted"] and p["ratio"] < p["limit"]
    assert set(p["bundles"]) == {"E1->R2", "E2->R1"} and len(p["tubes"]) == 8
    assert sf.scene_to_dict(e.scene) == before
    assert "sculpt-preview-outline" in s["svg"] and "sculpt-untrusted" not in s["svg"]
    s = _ok(e, {"type": "sculpt_preview", "handle_id": "lens/X/20", "kind": "position", "delta": 0.01})
    assert not s["sculpt"]["preview"]["trusted"] and "sculpt-untrusted" in s["svg"]
    s = _ok(e, {"type": "sculpt_preview", "clear": True})
    assert s["sculpt"]["preview"] is None and "sculpt-preview-outline" not in s["svg"]


def test_apply_records_the_edit_retraces_and_learns_the_limit():
    e = SceneEditor(_scene(), quick_max_rays=1000)
    _ok(e, {"type": "sculpt_start", "glass": "lens"})
    before = e.state()["sculpt"]["bundles"]
    s = _ok(e, {"type": "sculpt_apply", "handle_id": "lens/X/20", "kind": "position", "delta": 5e-4})
    assert list(e._obj("lens")._construction_args["edits"]) == [
        {"edge": "X", "index": 20, "kind": "position", "delta": 5e-4}]
    assert s["sculpt"]["bundles"][0]["spread"] != before[0]["spread"]
    limit = s["sculpt"]["limits"]["2"]
    assert limit["measured"] and limit["per_ratio"] > 0 and 0 < limit["limit"] <= 0.2
    assert s["sculpt"]["preview"] is None
    # an edit that breaks the outline: refused, reported, the scene as it was
    edited = sf.scene_to_dict(e.scene)
    s = e.handle({"type": "sculpt_apply", "handle_id": "lens/N/26", "kind": "position", "delta": -1.0})
    assert "no longer a simple closed curve" in s["error"]
    assert [ev["kind"] for ev in s["sculpt"]["events"]] == ["outline_refused"]
    assert sf.scene_to_dict(e.scene) == edited
    # undo the edit, then past the start: the lens as it was, the mode left
    s = _ok(e, {"type": "sculpt_undo"})
    assert list(e._obj("lens")._construction_args["edits"]) == []
    assert s["sculpt"]["bundles"][0]["spread"] == pytest.approx(before[0]["spread"], abs=1e-15)
    s = _ok(e, {"type": "undo"})
    assert s["sculpt"] is None and type(e._obj("lens")).__name__ == "RRLens"
    assert s["trace"]["segments"] > 0                         # the rays are back


def test_an_edit_that_sends_a_tube_s_light_elsewhere_is_an_event():
    e = SceneEditor(_scene(), quick_max_rays=1000)
    _ok(e, {"type": "sculpt_start", "glass": "lens", "bundles": False})
    s = _ok(e, {"type": "sculpt_apply", "handle_id": "lens/X/26", "kind": "normal", "delta": 25.0})
    kinds = {ev["kind"] for ev in s["sculpt"]["events"]}
    assert kinds & {"receiver_missed", "tube_split", "tir_switched"}, s["sculpt"]["events"]
    assert all(ev.get("tube_id", "").startswith("E1/T") for ev in s["sculpt"]["events"])
    _ok(e, {"type": "sculpt_repartition"})
    assert e.state()["sculpt"]["events"] == []


def test_settings_and_refusals(started):
    e, _ = started
    s = _ok(e, {"type": "sculpt_settings", "map": "B", "fine": 0.05, "opl_scale": 1e-3})
    assert (s["sculpt"]["map"], s["sculpt"]["fine"], s["sculpt"]["opl_scale"]) == ("B", 0.05, 1e-3)
    assert "sculpt-tube" in s["svg"] and "sculpt-bundle-ray" not in s["svg"]
    _ok(e, {"type": "sculpt_settings", "map": "A"})
    for message, reason in [
        ({"type": "sculpt_settings", "map": "C"}, "map is 'A', 'B' or 'both'"),
        ({"type": "sculpt_settings", "fine": 0}, "fine must be positive"),
        ({"type": "sculpt_preview", "handle_id": "lens/N/0", "kind": "position", "delta": 0.1}, "no handle"),
        ({"type": "sculpt_preview", "handle_id": "lens/N/3", "kind": "spin", "delta": 0.1}, "position or normal"),
        ({"type": "sculpt_preview", "handle_id": "lens/N/3"}, "needs handle_id and delta"),
    ]:
        assert reason in e.handle(message)["error"]
    other = SceneEditor(_scene(), quick_max_rays=0)
    assert "not sculpting" in other.handle({"type": "sculpt_preview", "clear": True})["error"]
    assert "not a designed element" in other.handle({"type": "sculpt_start", "glass": "R"})["error"]
    assert "needs a glass" in other.handle({"type": "sculpt_start"})["error"]


def test_a_point_source_is_drawn_a_few_pixels_wide_whatever_the_zoom():
    e = SceneEditor(_scene(), quick_max_rays=0)
    r = float(re.search(r'<circle class="point"[^>]* r="([^"]+)"', e.svg()).group(1))
    assert r * e.scene.scale == pytest.approx(5.0)


# --- the page in a browser ----------------------------------------------------------------

_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>%(css)s</style></head>
<body><div id="app" style="width:1100px"></div><pre id="result">pending</pre>
<script type="module">
const listeners = {};
let state = null;
const model = {
  get: (k) => state,
  on: (evt, cb) => (listeners[evt] = listeners[evt] || []).push(cb),
  send: async (m) => {
    const r = await fetch("/msg", { method: "POST", body: JSON.stringify(m) });
    state = await r.json();
    for (const cb of listeners["change:state"] || []) cb();
  },
};
const mod = await import("/esm.js");
state = await (await fetch("/state")).json();
mod.default.render({ model, el: document.getElementById("app") });
const out = {};
const until = async (test) => { for (let i = 0; i < 400; i++) { if (test(state)) return true;
  await new Promise((r) => setTimeout(r, 25)); } return false; };
try {
  [...document.querySelectorAll(".rsb-node")].find((n) => n.title === "lens").click();
  await until((s) => s.selected && s.selected.name === "lens");
  [...document.querySelectorAll("button")].find((b) => b.textContent === "Sculpt").click();
  out.started = await until((s) => s.sculpt && s.sculpt.handles.length > 0);
  const h = state.sculpt.handles.find((x) => x.handle_id === "lens/X/20");
  const canvas = document.querySelector(".rsb-canvas");
  const at = (x, y) => { const svg = canvas.querySelector("svg"), p = svg.createSVGPoint(); p.x = x; p.y = -y;
    const q = p.matrixTransform(svg.getScreenCTM()); return { clientX: q.x, clientY: q.y }; };
  const fire = (type, x, y) => canvas.dispatchEvent(new PointerEvent(type, { bubbles: true, button: 0,
    pointerId: 1, isPrimary: true, ...at(x, y) }));
  fire("pointerdown", h.x, h.y);
  out.overlay_handles = document.querySelectorAll(".rsb-sculpt-handle").length;
  const step = 0.02;
  for (let k = 1; k <= 3; k++) fire("pointermove", h.x + k * step * h.normal[0], h.y + k * step * h.normal[1]);
  out.previewed = await until((s) => s.sculpt.preview && s.sculpt.preview.handle_id === "lens/X/20");
  out.preview = state.sculpt.preview;
  out.outline_drawn = !!document.querySelector(".sculpt-preview-outline");
  out.panel_preview = !!document.querySelector(".rsb-sculpt-preview");
  fire("pointerup", h.x + 3 * step * h.normal[0], h.y + 3 * step * h.normal[1]);
  out.applied = await until((s) => s.sculpt && s.sculpt.limits && s.sculpt.limits["2"]);
  out.edits = state.sculpt && state.sculpt.preview === null;
} catch (err) { out.error = String(err && err.stack || err); }
document.getElementById("result").textContent = JSON.stringify(out);
</script></body></html>"""


def _serve(editor):
    page = (_PAGE % {"css": _CSS}).encode()

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, body, kind):
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/esm.js":
                self._send(_ESM.encode(), "text/javascript")
            elif self.path == "/state":
                self._send(json.dumps(editor.state()).encode(), "application/json")
            else:
                self._send(page, "text/html")

        def do_POST(self):
            message = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self._send(json.dumps(editor.handle(message)).encode(), "application/json")

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


_CHROME = next((c for c in ("google-chrome", "chromium", "chromium-browser") if shutil.which(c)), None)


@pytest.mark.skipif(_CHROME is None, reason="no Chrome or Chromium on this machine for the page test")
def test_the_page_previews_a_dragged_handle_and_applies_on_release(tmp_path):
    editor = SceneEditor(_scene(), width=800, height=520, quick_max_rays=500)
    server = _serve(editor)
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/"
        run = subprocess.run([_CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", f"--user-data-dir={tmp_path}",
                              "--window-size=1200,900", "--virtual-time-budget=60000", "--dump-dom", url],
                             capture_output=True, text=True, timeout=120)
    finally:
        server.shutdown()
    found = re.search(r'<pre id="result">(.*?)</pre>', run.stdout, re.S)
    assert found, run.stderr[-2000:]
    out = json.loads(found.group(1).replace("&quot;", '"').replace("&amp;", "&"))
    assert "error" not in out, out.get("error")
    assert out["started"] and out["overlay_handles"] == len(editor.state()["sculpt"]["handles"])
    assert out["previewed"] and out["outline_drawn"] and out["panel_preview"]
    p = out["preview"]
    assert p["kind"] == "position" and p["delta"] > 0                 # along the outward normal
    assert math.isclose(p["delta"], 0.06 * editor.state()["sculpt"]["fine"], rel_tol=1e-6)
    assert out["applied"] and out["edits"]
    assert list(editor._obj("lens")._construction_args["edits"])[0]["edge"] == "X"
