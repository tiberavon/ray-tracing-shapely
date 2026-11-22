"""
Python-specific module: test parameter study flow
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
A scene file with a parameter swept, traced at every point, read at a detector
===============================================================================
Checked against hand calculations (KD5): a mirror turned by theta sends a ray
2 theta further round, so it lands 100 tan(2 theta) along a screen 100 away; a
ray through a glass slab at normal incidence keeps (1 - R) / (1 + R) of its
power, every bounce counted. A point that cannot be built is recorded as failed
and the study ends done; a scene or a sweep end that does not build sends the
flow back, with the reason; the same study is driven by the generic flow tools
with JSON only.
===============================================================================
"""
import csv
import json
import math
from pathlib import Path

import pytest

from ray_tracing_shapely.analysis import parameter_study as ps
from ray_tracing_shapely.analysis import parameter_study_flow as psf
from ray_tracing_shapely.analysis import scene_file as sf
from ray_tracing_shapely.analysis.parameter_study_flow import ParameterStudyFlow
from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.glass.glass import Glass
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay
from ray_tracing_shapely.core.scene_objs.mirror.mirror import Mirror
from ray_tracing_shapely.core.scene_objs.other.detector import Detector
from ray_tracing_shapely.flows import agentic


def _scene(tmp_path, objects, name="s"):
    scene = Scene()
    for obj_name, obj in objects(scene).items():
        obj.name = obj_name
        scene.add_object(obj)
    return sf.save_scene(scene, tmp_path / f"{name}.scene.json")


def _mirror_scene(tmp_path):
    """A ray along +x, a mirror at 45 degrees at x = 100 sending it to +y, a screen at y = 100."""
    return _scene(tmp_path, lambda s: {
        "ray": SingleRay(s, {"p1": {"x": 0, "y": 0}, "p2": {"x": 10, "y": 0}}),
        "mirror": Mirror(s, {"p1": {"x": 90, "y": -10}, "p2": {"x": 110, "y": 10}}),
        "screen": Detector(s, {"p1": {"x": 200, "y": 100}, "p2": {"x": 0, "y": 100}}),
    }, "mirror")


def _slab_scene(tmp_path):
    """A ray along +x through a glass slab, a detector behind it."""
    slab = [(50, -20), (60, -20), (60, 20), (50, 20)]
    return _scene(tmp_path, lambda s: {
        "ray": SingleRay(s, {"p1": {"x": 0, "y": 0}, "p2": {"x": 10, "y": 0}}),
        "slab": Glass(s, {"path": [{"x": x, "y": y, "arc": False} for x, y in slab], "refIndex": 1.5}),
        "detector": Detector(s, {"p1": {"x": 100, "y": -50}, "p2": {"x": 100, "y": 50}}),
    }, "slab")


def _fresnel_scene(tmp_path):
    return _scene(tmp_path, lambda s: {
        "lens": sf.recipe_class("FresnelLens")(s, focal_distance=20.0, semi_diameter=10.0, zones=4, thickness=2.0),
        "ray": SingleRay(s, {"p1": {"x": 0, "y": -30}, "p2": {"x": 0, "y": -20}}),
        "detector": Detector(s, {"p1": {"x": -50, "y": 40}, "p2": {"x": 50, "y": 40}}),
    }, "fresnel")


def _run(tmp_path, scene_path, parameters, measure, executor="in_process"):
    flow = ParameterStudyFlow(base_dir=tmp_path / "runs", render_svg=False)
    for value in (str(scene_path), parameters, measure, executor):
        out = flow.answer(value)
        assert out["accepted"], out
    return flow


def test_a_turned_mirror_moves_the_spot_by_100_tan_2_theta(tmp_path):
    flow = _run(tmp_path, _mirror_scene(tmp_path),
                {"object": "mirror", "parameter": "rotate_deg", "from": -10, "to": 10, "steps": 5},
                {"measure": "centroid"})
    assert flow.state == "done"
    rows = flow.result["rows"]
    assert [r["point"]["mirror.rotate_deg"] for r in rows] == [-10, -5, 0, 5, 10]
    for r in rows:
        theta = math.radians(r["point"]["mirror.rotate_deg"])
        assert r["ok"] and r["hits"] == 1
        assert r["centroid"] == pytest.approx(100 + 100 * math.tan(2 * theta), abs=1e-9)
        assert r["power"] == pytest.approx(1.0) and r["share"] == pytest.approx(1.0)
    with open(flow.result["table"], newline="") as fh:
        table = list(csv.DictReader(fh))
    assert [float(t["mirror.rotate_deg"]) for t in table] == [-10, -5, 0, 5, 10]
    assert flow.result["plot"] and open(flow.result["plot"]).read().startswith("<?xml")


def test_each_point_is_saved_as_a_run_its_physical_and_numerical_parameters_apart(tmp_path):
    flow = _run(tmp_path, _mirror_scene(tmp_path),
                {"object": "mirror", "parameter": "rotate_deg", "values": [0, 5]},
                {"measure": "power", "ray_density": 0.5, "min_brightness_exp": 4})
    first, second = (json.loads((Path(r["run_dir"]) / "params.json").read_text()) for r in flow.result["rows"])
    assert first["physical_params"] == {"mirror.rotate_deg": 0} and second["physical_params"] == {"mirror.rotate_deg": 5}
    assert first["numerical_params"] == {"ray_density": 0.5, "min_brightness_exp": 4,
                                         "max_rays": flow.result["numerical"]["max_rays"]}
    assert first["name_topology"] == second["name_topology"]


def test_a_glass_slab_keeps_1_minus_r_over_1_plus_r_of_the_power(tmp_path):
    values = [1.3, 1.5, 1.8, 2.4]
    flow = _run(tmp_path, _slab_scene(tmp_path), {"object": "slab", "parameter": "refIndex", "values": values},
                {"measure": "share", "min_brightness_exp": 14, "save_runs": False})
    for n, r in zip(values, flow.result["rows"]):
        reflectance = ((n - 1) / (n + 1)) ** 2
        assert r["share"] == pytest.approx((1 - reflectance) / (1 + reflectance), rel=1e-9)
    assert flow.result["runs_dir"] is None and "run_dir" not in flow.result["rows"][0]


def test_a_point_that_does_not_build_is_recorded_failed_and_the_study_ends_done(tmp_path):
    flow = _run(tmp_path, _fresnel_scene(tmp_path),
                {"object": "lens", "parameter": "thickness", "values": [2.0, -1.0, 3.0]},
                {"save_runs": False})
    assert flow.state == "done"
    ok = [r["ok"] for r in flow.result["rows"]]
    assert ok == [True, False, True] and flow.result["failed"] == 1
    assert "thickness must be positive" in flow.result["rows"][1]["error"]


def test_a_recipe_point_is_the_constructor_called_with_that_argument(tmp_path):
    data = json.loads(_fresnel_scene(tmp_path).read_text())
    built = ps.build_point(data, [{"object": "lens", "parameter": "zones", "value": 6}])
    direct = sf.recipe_class("FresnelLens")(Scene(), focal_distance=20.0, semi_diameter=10.0, zones=6, thickness=2.0)
    lens = built.get_object_by_name("lens")
    assert json.dumps(lens.serialize(), sort_keys=True) == json.dumps(direct.serialize(), sort_keys=True)


def test_an_element_is_moved_with_its_parts(tmp_path):
    from ray_tracing_shapely.optical_elements.prisms.rxi import RXIOptic

    scene = Scene()
    rxi = RXIOptic(scene, n=1.5, phi_edge_deg=50.0, size=30.0, depth=45.0, s1_segments=16)
    rxi.name = "rxi"
    scene.add_object(rxi)
    data = sf.scene_to_dict(scene)
    before = ps.build_point(data, [])
    after = ps.build_point(data, [{"object": "rxi", "parameter": "move_x", "value": 7.0}])
    mirror_before, mirror_after = (s.get_object_by_name("rxi_s2_mirror") for s in (before, after))
    assert mirror_after.p1["x"] == pytest.approx(mirror_before.p1["x"] + 7.0)
    assert after.get_object_by_name("rxi").path[0]["x"] == pytest.approx(
        before.get_object_by_name("rxi").path[0]["x"] + 7.0)
    with pytest.raises(ps.StudyError, match="part of 'rxi'"):
        ps.current_value(data, "rxi_s2_mirror", "p1.x")


def test_parameters_that_cannot_be_swept_are_refused_with_what_there_is(tmp_path):
    data = json.loads(_mirror_scene(tmp_path).read_text())
    table = {o["object"]: [p["parameter"] for p in o["parameters"]] for o in ps.parameter_table(data)}
    assert {"p1.x", "p1.y", "rotate_deg", "move_x", "move_y"} <= set(table["mirror"])
    cases = [({"object": "lamp", "parameter": "x", "values": [1]}, "no object named 'lamp'"),
             ({"object": "mirror", "parameter": "tilt", "values": [1]}, "no parameter 'tilt'"),
             ({"object": "mirror", "parameter": "p1.x", "values": []}, "non-empty list"),
             ({"object": "mirror", "parameter": "p1.x", "from": 0, "to": 1, "steps": 1}, "at least 2"),
             ([{"object": "mirror", "parameter": "p1.x", "values": [1]}] * 2, "already an axis"),
             ([{"object": "mirror", "parameter": "p1.x", "from": 0, "to": 1, "steps": 30},
               {"object": "mirror", "parameter": "p1.y", "from": 0, "to": 1, "steps": 30}], "at most 400")]
    for spec, reason in cases:
        with pytest.raises(ps.StudyError, match=reason):
            ps.sweep_axes(data, spec)
    fresnel = json.loads(_fresnel_scene(tmp_path).read_text())
    with pytest.raises(ps.StudyError, match="whole number"):
        ps.sweep_axes(fresnel, {"object": "lens", "parameter": "zones", "values": [4, 4.5]})


def test_a_scene_without_a_detector_is_sent_back_with_the_reason(tmp_path):
    path = _scene(tmp_path, lambda s: {"ray": SingleRay(s, {"p1": {"x": 0, "y": 0}, "p2": {"x": 1, "y": 0}})})
    flow = ParameterStudyFlow(base_dir=tmp_path / "runs", render_svg=False)
    out = flow.answer(str(path))
    assert out["accepted"] and out["sent_back"]["to"] == "scene_path"
    assert "no detector" in out["sent_back"]["reason"] and flow.state == "awaiting_scene"
    refused = flow.answer(str(tmp_path / "missing.scene.json"))
    assert not refused["accepted"] and "no file" in refused["reason"]


def test_a_sweep_end_that_does_not_build_sends_the_flow_back_before_anything_is_traced(tmp_path):
    flow = ParameterStudyFlow(base_dir=tmp_path / "runs", render_svg=False)
    flow.answer(str(_fresnel_scene(tmp_path)))
    out = flow.answer({"object": "lens", "parameter": "thickness", "from": 2.0, "to": -1.0, "steps": 4})
    assert out["accepted"] and flow.state == "awaiting_parameters"
    assert "thickness must be positive" in out["sent_back"]["reason"]
    assert flow.answer({"object": "lens", "parameter": "thickness", "values": [2.0, 3.0]})["state"] == "awaiting_measure"


def test_an_estimate_over_the_limit_is_asked_and_false_goes_back_to_the_executor(tmp_path, monkeypatch):
    monkeypatch.setattr(psf, "ASK_OVER_S", 0.0)
    flow = ParameterStudyFlow(base_dir=tmp_path / "runs", render_svg=False)
    for value in (str(_mirror_scene(tmp_path)), {"object": "mirror", "parameter": "rotate_deg", "values": [0, 1]},
                  {"save_runs": False}, "in_process"):
        flow.answer(value)
    assert flow.state == "awaiting_go_ahead"
    context = flow.question_state()["context"]
    assert context["points"] == 2 and context["pilot"]["hits"] == 1
    assert flow.answer(False)["state"] == "awaiting_executor"
    flow.answer("in_process")
    assert flow.answer(True)["state"] == "done"


def test_the_estimate_warns_when_the_pilot_puts_nothing_on_the_detector(tmp_path):
    path = _scene(tmp_path, lambda s: {
        "ray": SingleRay(s, {"p1": {"x": 0, "y": 0}, "p2": {"x": 10, "y": 0}}),
        "detector": Detector(s, {"p1": {"x": 100, "y": 50}, "p2": {"x": 100, "y": -50},
                                 "twoSided": False}),   # one-sided, its back to the ray
    })
    flow = _run(tmp_path, path, {"object": "ray", "parameter": "p1.y", "values": [0, 1]}, {"save_runs": False})
    assert "absorbingSide" in flow.estimate["warning"]
    assert [r["power"] for r in flow.result["rows"]] == [0.0, 0.0]


def test_the_study_is_driven_by_the_generic_flow_tools_with_json_only(tmp_path):
    path = _mirror_scene(tmp_path)
    agentic.set_runs_root(tmp_path / "flow_runs")
    started = agentic.flow_start("parameter_study")
    assert started["status"] == "ok" and started["data"]["question"]["name"] == "scene_path"
    run_id = started["data"]["run_id"]
    for value in (str(path), {"object": "mirror", "parameter": "rotate_deg", "values": [0, 10]},
                  {"measure": "centroid", "save_runs": False}, "in_process"):
        out = agentic.flow_answer(run_id, value)
        assert out["status"] == "ok" and out["data"]["accepted"], out
        json.dumps(out)                                     # what an agent reads is JSON
    result = agentic.flow_result(run_id)["data"]
    assert result["state"] == "done"
    rows = result["result"]["result"]["rows"]
    assert rows[1]["centroid"] == pytest.approx(100 + 100 * math.tan(math.radians(20)))


def test_points_run_in_worker_processes_and_are_saved_where_the_flow_says(tmp_path, monkeypatch):
    path = _mirror_scene(tmp_path)
    monkeypatch.chdir(tmp_path)                 # a relative base folder: the workers start elsewhere
    flow = ParameterStudyFlow(base_dir="runs", render_svg=False)
    for value in (str(path), {"object": "mirror", "parameter": "rotate_deg", "values": [0, 5]},
                  {"measure": "centroid"}, "local_process"):
        assert flow.answer(value)["accepted"]
    out = flow.wait(120)
    assert out["state"] == "done", out
    assert [r["centroid"] for r in flow.result["rows"]] == pytest.approx([100.0, 100 + 100 * math.tan(math.radians(10))])
    run_folder = (tmp_path / "runs" / flow.run_id / "runs" / "points").resolve()
    for i, r in enumerate(flow.result["rows"]):
        assert Path(r["run_dir"]) == run_folder / f"point_{i:03d}"
        assert (Path(r["run_dir"]) / "rays.sqlite").exists()


def test_the_results_come_back_as_rows_arrays_and_a_table_live_or_from_the_folder(tmp_path):
    import numpy as np

    flow = _run(tmp_path, _mirror_scene(tmp_path),
                {"object": "mirror", "parameter": "rotate_deg", "values": [0, 5, 10]},
                {"measure": "centroid", "save_runs": False})
    a = ps.study_arrays(flow)
    expected = 100 + 100 * np.tan(np.radians(2 * np.array([0.0, 5.0, 10.0])))
    assert np.allclose(a["mirror.rotate_deg"], [0, 5, 10]) and np.allclose(a["centroid"], expected)
    assert a["ok"].all() and a["power"].shape == (3,)
    folder = tmp_path / "runs" / flow.run_id
    saved = np.load(folder / "arrays.npz")
    assert np.allclose(saved["centroid"], expected)               # written beside the table
    assert ps.study_rows(folder) == ps.study_rows(flow)           # read back from the run's folder
    table = ps.study_table_markdown(folder)
    assert table.splitlines()[0].startswith("| index | mirror.rotate_deg | power |")
    with pytest.raises(ps.StudyError, match="no result.json"):
        ps.study_result(tmp_path)


def test_a_grid_comes_back_shaped_as_the_grid_and_a_failed_point_as_nan(tmp_path):
    import numpy as np

    flow = _run(tmp_path, _fresnel_scene(tmp_path),
                [{"object": "lens", "parameter": "thickness", "values": [2.0, -1.0, 3.0]},
                 {"object": "ray", "parameter": "p1.x", "values": [0.0, 1.0]}],
                {"save_runs": False})
    a = ps.study_arrays(flow)
    assert a["lens.thickness"].tolist() == [2.0, -1.0, 3.0] and a["ray.p1.x"].tolist() == [0.0, 1.0]
    assert a["power"].shape == (3, 2) and a["ok"].tolist() == [[True, True], [False, False], [True, True]]
    assert np.isnan(a["power"][1]).all() and not np.isnan(a["power"][0]).any()
    flat = ps.study_arrays(flow, grid=False)
    assert flat["power"].shape == (6,) and flat["lens.thickness"].tolist() == [2, 2, -1, -1, 3, 3]
    assert "thickness must be positive" in ps.study_table_markdown(flow)
