"""
Python-specific module: test flow transcript
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
A run's record as a page
===============================================================================
The page names every box in order, every question, answer, refusal and
send-back, and the result, its rows as a table; it names no folder of the
machine it was written on; it says how a failed run ended and which attempts
were abandoned; written to a folder, it takes the diagram and the plot with it.
===============================================================================
"""
import pytest

pytest.importorskip("transitions")

from ray_tracing_shapely.analysis.parameter_study_flow import ParameterStudyFlow  # noqa: E402
from ray_tracing_shapely.analysis.scene_file import save_scene  # noqa: E402
from ray_tracing_shapely.core.scene import Scene  # noqa: E402
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay  # noqa: E402
from ray_tracing_shapely.core.scene_objs.mirror.mirror import Mirror  # noqa: E402
from ray_tracing_shapely.optical_elements.sensors.photodetector import Photodetector  # noqa: E402
from ray_tracing_shapely.flows import persistence  # noqa: E402
from ray_tracing_shapely.flows.flow_base import graphviz_available  # noqa: E402
from ray_tracing_shapely.flows.transcript import transcript_markdown, write_transcript  # noqa: E402


def _scene(tmp_path, with_detector=True):
    scene = Scene()
    objs = {"ray": SingleRay(scene, {"p1": {"x": 0, "y": 0}, "p2": {"x": 10, "y": 0}}),
            "mirror": Mirror(scene, {"p1": {"x": 90, "y": -10}, "p2": {"x": 110, "y": 10}})}
    if with_detector:
        objs["screen"] = Photodetector(scene, {"p1": {"x": 0, "y": 100}, "p2": {"x": 200, "y": 100},
                                               "absorbingSide": -1})
    for name, obj in objs.items():
        obj.name = name
        scene.add_object(obj)
    return save_scene(scene, tmp_path / ("s.scene.json" if with_detector else "bare.scene.json"))


def _study(tmp_path, render_svg=False):
    flow = ParameterStudyFlow(tmp_path / "runs", render_svg=render_svg)
    flow.answer(str(_scene(tmp_path, with_detector=False)))             # sent back: no detector
    flow.answer(str(tmp_path / "missing.scene.json"))                  # refused
    for value in (str(_scene(tmp_path)), {"object": "mirror", "parameter": "rotate_deg", "values": [0, 5]},
                  {"measure": "centroid", "save_runs": False}, "in_process"):
        assert flow.answer(value)["accepted"]
    assert flow.state == "done"
    return flow


def test_the_page_tells_the_run_in_order_with_its_answers_and_result(tmp_path):
    flow = _study(tmp_path)
    page = transcript_markdown(tmp_path / "runs", flow.run_id)
    boxes = ["### `awaiting_scene`", "### `loading`", "### `awaiting_parameters`", "### `checking_parameters`",
             "### `awaiting_measure`", "### `awaiting_executor`", "### `tracing`", "### `done`"]
    assert [page.index(b) for b in boxes] == sorted(page.index(b) for b in boxes)
    assert "**Sent back** to `scene_path`" in page and "no detector" in page
    assert "**Refused**: no file at" in page
    assert '**Answered** `parameters`: `{"object": "mirror", "parameter": "rotate_deg", "values": [0, 5]}`' in page
    assert "**Ended in** `done`" in page
    assert "| index | point.mirror.rotate_deg | ok | power |" in page and "| 1 | 5 | True | 1 |" in page


def test_the_page_names_no_folder_of_this_machine(tmp_path):
    flow = _study(tmp_path)
    out = tmp_path / "site" / "tutorial"
    page = write_transcript(tmp_path / "runs", flow.run_id, out).read_text()
    assert str(tmp_path) not in page
    assert "../../runs/" in page                              # the table, relative to the page


@pytest.mark.skipif(not graphviz_available(), reason="the diagram needs Graphviz")
def test_a_written_page_takes_its_diagram_and_plot_with_it(tmp_path):
    flow = _study(tmp_path, render_svg=True)
    out = tmp_path / "site"
    page = write_transcript(tmp_path / "runs", flow.run_id, out).read_text()
    assert (out / f"{flow.run_id}.svg").exists() and f"]({flow.run_id}.svg)" in page
    assert (out / f"{flow.run_id}_plot.svg").exists() and f"]({flow.run_id}_plot.svg)" in page


def test_a_failed_run_and_an_abandoned_attempt_are_said(tmp_path):
    flow = ParameterStudyFlow(tmp_path / "runs", render_svg=False)
    flow.answer(str(_scene(tmp_path)))
    flow.reset()
    flow.begin()
    flow.fail(RuntimeError("the disk is full"))
    page = transcript_markdown(tmp_path / "runs", flow.run_id)
    assert "Attempt 1 was abandoned (reset from `awaiting_parameters`)" in page
    assert "**Ended in** `failed`" in page and "RuntimeError: the disk is full" in page
    with pytest.raises(FileNotFoundError):
        transcript_markdown(tmp_path / "runs", "no-such-run")
    assert persistence.read_result(tmp_path / "runs", flow.run_id)["status"] == "failed"
