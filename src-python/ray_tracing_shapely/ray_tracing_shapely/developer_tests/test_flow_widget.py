"""
Python-specific module: test flow widget
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
The flow form, driven by its own messages, with no browser
===============================================================================
The rayfile slicing flow driven to its table through the form's message handler
ends where answer() ends, with the same table; a refusal, a default, a reset and
a send-back show in what the page draws; the page's state is plain JSON.
===============================================================================
"""
import json

import pytest

pytest.importorskip("anywidget")
pytest.importorskip("transitions")
pytest.importorskip("pint")

import numpy as np  # noqa: E402

from ray_tracing_shapely.flows.widget import flow_form  # noqa: E402
from ray_tracing_shapely.optical_elements.sources import write_tm25  # noqa: E402
from ray_tracing_shapely.optical_elements.sources.rayfile_slicing_flow import RayfileSlicingFlow  # noqa: E402


def _four_dies(path, n=8000, seed=7):
    """Four 0.8 mm dies at (+-0.6, +-0.6) mm, each Lambertian (as the slicing flow's own tests)."""
    rng = np.random.default_rng(seed)
    die = rng.integers(0, 4, n)
    cx = np.where(die % 2 == 0, -0.6, 0.6)
    cy = np.where(die < 2, -0.6, 0.6)
    pos = np.c_[cx + 0.8 * (rng.random(n) - 0.5), cy + 0.8 * (rng.random(n) - 0.5), np.zeros(n)]
    sin_t, phi = np.sqrt(rng.random(n)), 2 * np.pi * rng.random(n)
    dirs = np.c_[sin_t * np.cos(phi), sin_t * np.sin(phi), np.sqrt(1.0 - sin_t ** 2)]
    write_tm25(path, pos, dirs, np.full(n, 1.0 / n), name="four dies")
    return path

ANSWERS = ("3 mm", "3 mm", 10, [0.5, 0.75], 0.75)


def test_the_slicing_flow_driven_through_the_form_ends_as_answer_does(tmp_path):
    path = str(_four_dies(tmp_path / "dies.TM25RAY"))
    direct = RayfileSlicingFlow(tmp_path / "direct", render_svg=False)
    for value in (path, *ANSWERS):
        assert direct.answer(value)["accepted"]
    direct.answer_default()

    form = flow_form(RayfileSlicingFlow(tmp_path / "form", render_svg=False))
    assert form.state["question"]["name"] == "rayfile"
    for value in (path, *ANSWERS):
        form.handle({"kind": "answer", "value": value})
        assert form.last == {"accepted": True}, form.last
    assert form.state["question"]["name"] == "profile" and not form.state["question"]["required"]
    form.handle({"kind": "default"})
    assert form.state["state"] == "done" and form.state["finished"] and form.state["question"] is None
    assert form.state["result"]["rows"] == json.loads(json.dumps(direct.result["rows"]))
    json.dumps(form.state)                                   # what the page draws is JSON


def test_a_refusal_and_a_reset_show_in_what_the_page_draws(tmp_path):
    form = flow_form(RayfileSlicingFlow(tmp_path / "runs", render_svg=False))
    form.handle({"kind": "answer", "value": 42})                 # not a path: refused by its kind
    assert form.last["accepted"] is False and "path" in form.last["reason"]
    assert form.state["last_refusal"]["field"] == "rayfile"
    path = str(_four_dies(tmp_path / "dies.TM25RAY"))
    form.handle({"kind": "answer", "value": path})
    form.handle({"kind": "reset"})
    assert form.last == {"accepted": True, "reset": True}
    assert form.state["attempt"] == 2 and form.state["question"]["name"] == "rayfile"
    form.handle({"kind": "nonsense"})
    assert "unknown message kind" in form.last["reason"]


def test_a_send_back_is_drawn_with_its_reason(tmp_path):
    from ray_tracing_shapely.analysis.parameter_study_flow import ParameterStudyFlow
    from ray_tracing_shapely.analysis.scene_file import save_scene
    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay

    scene = Scene()
    ray = SingleRay(scene, {"p1": {"x": 0, "y": 0}, "p2": {"x": 1, "y": 0}})
    ray.name = "ray"
    scene.add_object(ray)
    path = save_scene(scene, tmp_path / "s.scene.json")
    form = flow_form(ParameterStudyFlow(tmp_path / "runs", render_svg=False))
    form.handle({"kind": "answer", "value": str(path)})
    assert form.last["accepted"] and "no detector" in form.last["sent_back"]["reason"]
    assert form.state["question"]["name"] == "scene_path"


def test_the_page_module_is_valid_javascript(tmp_path):
    import shutil
    import subprocess

    from ray_tracing_shapely.flows import widget

    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    module = tmp_path / "form.mjs"
    module.write_text(widget._ESM, encoding="utf-8")
    checked = subprocess.run([node, "--check", str(module)], capture_output=True, text=True)
    assert checked.returncode == 0, checked.stderr
    assert "export default { render }" in widget._ESM


def _study_form(tmp_path):
    from ray_tracing_shapely.analysis.parameter_study_flow import ParameterStudyFlow
    from ray_tracing_shapely.analysis.scene_file import save_scene
    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.core.scene_objs.glass.glass import Glass
    from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay
    from ray_tracing_shapely.optical_elements.sensors.photodetector import Photodetector

    scene = Scene()
    slab = [(50, -20), (60, -20), (60, 20), (50, 20)]
    objs = {"ray": SingleRay(scene, {"p1": {"x": 0, "y": 0}, "p2": {"x": 10, "y": 0}}),
            "slab": Glass(scene, {"path": [{"x": x, "y": y, "arc": False} for x, y in slab], "refIndex": 1.5}),
            "sensor": Photodetector(scene, {"p1": {"x": 100, "y": -50}, "p2": {"x": 100, "y": 50}})}
    for name, obj in objs.items():
        obj.name = name
        scene.add_object(obj)
    (tmp_path / "scenes").mkdir()
    save_scene(scene, tmp_path / "scenes" / "slab.scene.json")
    return flow_form(ParameterStudyFlow(tmp_path / "runs", render_svg=False))


def _page(script, tmp_path):
    """Run ``script`` in node with the page module importable as ./form.mjs; its stdout, as JSON."""
    import shutil
    import subprocess

    from ray_tracing_shapely.flows import widget

    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    (tmp_path / "form.mjs").write_text(widget._ESM, encoding="utf-8")
    (tmp_path / "run.mjs").write_text(script, encoding="utf-8")
    done = subprocess.run([node, str(tmp_path / "run.mjs")], capture_output=True, text=True, cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_a_path_question_shows_the_working_directory_and_the_files_that_fit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    form = _study_form(tmp_path)
    files = form.state["files"]
    assert files["cwd"] == str(tmp_path.resolve()) and files["pattern"] == "*.scene.json"
    assert files["matches"] == ["scenes/slab.scene.json"]
    form.handle({"kind": "browse", "dir": "scenes"})
    assert form.browse["files"] == [{"name": "slab.scene.json", "path": "scenes/slab.scene.json"}]
    form.handle({"kind": "browse", "dir": form.browse["parent"]})
    assert "scenes" in form.browse["dirs"] and form.browse["files"] == []
    form.handle({"kind": "answer", "value": files["matches"][0]})
    assert form.last == {"accepted": True} and form.state["question"]["name"] == "parameters"


def test_the_forms_answers_as_a_person_fills_them_are_accepted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    form = _study_form(tmp_path)
    form.handle({"kind": "answer", "value": "scenes/slab.scene.json"})
    sweep = form.state["form"]
    built = _page(f"""
import {{ initVals, settle, assemble }} from "./form.mjs";
const spec = {json.dumps(sweep)};
const vals = initVals(spec);
vals[0].object = "slab"; settle(spec.item, vals[0]);              // the person picks the slab...
const first = vals[0].parameter;                                   // ...its first parameter is its own number
vals[0].parameter = "refIndex"; vals[0].from = "1.4"; vals[0].to = "1.6"; vals[0].steps = "3";
vals.push(initVals(spec.item));                                    // a second axis: a list of values
vals[1].object = "sensor"; settle(spec.item, vals[1]);
vals[1].parameter = "move_x"; vals[1].mode = "values"; vals[1].values = "0, 5";
console.log(JSON.stringify({{first, answer: assemble(spec, vals)}}));
""", tmp_path)
    assert built["first"] == "refIndex"
    assert built["answer"] == [{"object": "slab", "parameter": "refIndex", "from": 1.4, "to": 1.6, "steps": 3},
                               {"object": "sensor", "parameter": "move_x", "values": [0, 5]}]
    form.handle({"kind": "answer", "value": built["answer"]})
    assert form.last == {"accepted": True} and form.state["question"]["name"] == "measure"
    assert len(form.flow.points) == 6

    measure = form.state["form"]
    defaults = _page(f"""
import {{ initVals, assemble }} from "./form.mjs";
const spec = {json.dumps(measure)};
console.log(JSON.stringify(assemble(spec, initVals(spec))));      // the person changes nothing
""", tmp_path)
    assert defaults == {"detector": "sensor", "measure": "power", "ray_density": form.flow.data["settings"]["ray_mode_density"],
                        "save_runs": True}
    form.handle({"kind": "answer", "value": defaults})
    assert form.last == {"accepted": True} and form.state["question"]["name"] == "executor"
