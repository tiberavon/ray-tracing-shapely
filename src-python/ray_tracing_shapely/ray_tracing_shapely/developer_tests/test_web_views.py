"""
Python-specific module: test web views
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
The flow form, the scene builder and the graph editor as pages
===============================================================================
With no browser, through Starlette's test client, as a solveit dialog's
FastHTML app would serve them:
- the slicing flow driven through the form's route to its table, equal to
  the flow answered directly (as the widget's own test does);
- the builder through its route: the page, its module (the widget's own),
  a mirror placed by messages;
- the graph editor through its route: its module, a node added, wired and
  run by messages, fresh after the run;
- the routes go ahead of an app's own catch-all; an unknown view and a body
  that is not JSON are refused.
===============================================================================
"""

import json

import pytest

pytest.importorskip("starlette")
pytest.importorskip("httpx")
pytest.importorskip("transitions")
pytest.importorskip("pint")

from starlette.applications import Starlette  # noqa: E402
from starlette.responses import PlainTextResponse  # noqa: E402
from starlette.routing import Route  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from ray_tracing_shapely.builder.widget import _ESM as BUILDER_ESM  # noqa: E402
from ray_tracing_shapely.developer_tests.test_flow_widget import ANSWERS, _four_dies  # noqa: E402
from ray_tracing_shapely.optical_elements.sources.rayfile_slicing_flow import RayfileSlicingFlow  # noqa: E402
from ray_tracing_shapely.web import Views  # noqa: E402


def _client(views):
    return TestClient(views.app())


def test_the_slicing_flow_through_the_form_s_route_ends_as_answer_does(tmp_path):
    path = str(_four_dies(tmp_path / "dies.TM25RAY"))
    direct = RayfileSlicingFlow(tmp_path / "direct", render_svg=False)
    for value in (path, *ANSWERS):
        assert direct.answer(value)["accepted"]
    direct.answer_default()

    views = Views()
    vid = views.flow(RayfileSlicingFlow(tmp_path / "form", render_svg=False))
    client = _client(views)
    page = client.get(f"/rts/{vid}/")
    assert page.status_code == 200 and 'import page from "./module.js"' in page.text
    assert '"name": "rayfile"' in page.text                   # the first question, inlined
    for value in (path, *ANSWERS):
        traits = client.post(f"/rts/{vid}/msg", json={"message": {"kind": "answer", "value": value}}).json()
        assert traits["last"] == {"accepted": True}, traits["last"]
    traits = client.post(f"/rts/{vid}/msg", json={"message": {"kind": "default"}}).json()
    assert traits["state"]["state"] == "done"
    assert traits["state"]["result"]["rows"] == json.loads(json.dumps(direct.result["rows"]))


def test_the_builder_through_its_route():
    views = Views()
    vid = views.builder(quick_max_rays=200)
    client = _client(views)
    assert client.get(f"/rts/{vid}/module.js").text == BUILDER_ESM
    assert client.get(f"/rts/{vid}/module.js").headers["content-type"].startswith("text/javascript")
    send = lambda m: client.post(f"/rts/{vid}/msg", json={"message": m}).json()["state"]  # noqa: E731
    send({"type": "tool", "name": "Mirror"})
    send({"type": "press", "x": 0, "y": 0})
    state = send({"type": "release", "x": 10, "y": 0})
    assert state["error"] is None and [o["name"] for o in state["objects"]] == ["Mirror1"]
    assert views[vid].scene.get_object_by_name("Mirror1").p2 == {"x": 10, "y": 0}
    assert send({"type": "refresh"})["objects"][0]["name"] == "Mirror1"


def test_the_routes_go_ahead_of_an_app_s_catch_all_and_refuse_what_they_cannot_read():
    async def catch_all(request):                             # as a FastHTML app's static route
        return PlainTextResponse("static", status_code=404)
    app = Starlette(routes=[Route("/{fname:path}.{ext}", catch_all)])
    views = Views(base_url="https://example.invalid/")
    vid = views.builder()
    views.mount(app)
    client = TestClient(app)
    assert client.get(f"/rts/{vid}/module.js").status_code == 200
    assert client.get("/rts/v999/").status_code == 404
    assert client.post(f"/rts/{vid}/msg", content=b"not json").status_code == 400
    assert views.url(vid) == f"https://example.invalid/rts/{vid}/"
    assert f'src="https://example.invalid/rts/{vid}/"' in views.iframe(vid)


def test_the_graph_editor_through_its_route():
    from ray_tracing_shapely.graph import GraphRunner
    from ray_tracing_shapely.graph.widget import _ESM as GRAPH_ESM
    views = Views()
    vid = views.graph(runner=GraphRunner(inline_limit_s=None))
    client = _client(views)
    assert client.get(f"/rts/{vid}/module.js").text == GRAPH_ESM
    assert '"palette"' in client.get(f"/rts/{vid}/").text            # the state, inlined
    send = lambda m: client.post(f"/rts/{vid}/msg", json={"message": m}).json()["state"]  # noqa: E731
    send({"type": "add", "block": "Detector"})
    for name, value in (("p1", [80, -40]), ("p2", [80, 40]), ("name", "det")):
        state = send({"type": "set", "id": "detector", "input": name, "value": value})
        assert state["error"] is None, state["error"]
    send({"type": "add", "block": "assemble"})
    state = send({"type": "connect", "from": "detector.entry", "to": "assemble.entries"})
    assert state["error"] is None and state["order"] == ["detector", "assemble"]
    state = send({"type": "run"})
    assert state["notice"] == "ran detector, assemble" and {n["status"] for n in state["nodes"]} == {"fresh"}
    assert views[vid].document()["nodes"][1]["inputs"]["entries"] == [{"from": "detector.entry"}]
