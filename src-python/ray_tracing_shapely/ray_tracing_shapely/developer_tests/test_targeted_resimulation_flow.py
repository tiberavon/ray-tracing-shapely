"""
Python-specific module: test targeted re-simulation flow
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
The targeted re-simulation flow, the live route
===============================================================================
On the glass slab of test_targeted_resimulation.py: the flow re-runs one ranked
path at a set number of rays, puts the result in a new named context (the run
it came from stays active and keeps its own detector hits), saves it as a
bundle that load_run_context reloads, and groups the rays that reached the
detector as rank_detector_paths over the new context does by hand.
===============================================================================
"""
import math
from collections import defaultdict

import pytest

from ray_tracing_shapely.analysis import targeted_resimulation_flow as trf
from ray_tracing_shapely.analysis.agentic_tools import (
    get_context,
    list_contexts,
    list_detectors,
    list_sources,
    load_run_context,
    rank_detector_paths,
    set_active_context,
    set_bidirectional_context,
    set_context_from_result,
)
from ray_tracing_shapely.analysis.targeted_resimulation import run_targeted_resimulation
from ray_tracing_shapely.analysis.targeted_resimulation_flow import (
    TargetedResimulationFlow,
    bounce_groups,
    density_for,
)
from ray_tracing_shapely.core.scene_objs.light_source.angle_source import AngleSource
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.flows import agentic as flow_tools

from test_targeted_resimulation import _build_scene, _run_bidirectional

RAYS = 300


@pytest.fixture(scope="module")
def run():
    scene, source, det = _build_scene()
    sim, bidir = _run_bidirectional(scene, det)
    result = Simulator(scene, max_rays=40000, record_surface_hits=True).run_with_result(name="broad")
    return scene, source, det, bidir, result


@pytest.fixture
def live(run):
    scene, source, det, bidir, result = run
    set_context_from_result(scene, result)
    set_bidirectional_context(bidir)
    return run


def _hits(name="det"):
    return {d["name"]: d["hit_count"] for d in list_detectors()["data"]}[name]


def _drive(tmp_path, options=None):
    flow = TargetedResimulationFlow(tmp_path, render_svg=False)
    for value in (None, 1, None, options or {"rays": RAYS}):
        out = flow.answer(value)
        assert out["accepted"], out
    return flow


def test_the_flow_makes_a_new_context_and_leaves_the_run_it_came_from(live, tmp_path):
    scene, source, det, bidir, result = live
    before = (_hits(), list(det.hit_records), scene.ray_density, scene.min_brightness_exp)
    flow = _drive(tmp_path)
    assert flow.state == "done", flow.question_state()
    out = flow.result
    assert out["context_name"] == "targeted_1" and out["source"] == "src" and out["detector"] == "det"
    assert RAYS <= out["roots"] <= RAYS + 2 and out["hits"] > 0 and out["groups"]
    assert sum(g["share"] for g in out["groups"]) == pytest.approx(1.0)

    assert list_contexts()["data"]["active"] == "default"                 # never switched (C-AGENT-04)
    assert (_hits(), list(det.hit_records), scene.ray_density, scene.min_brightness_exp) == before
    assert source in scene.objs and not any(o.name == "src_targeted" for o in scene.objs)

    set_active_context("targeted_1")
    assert _hits() == len(get_context()["detector_hits"][det.uuid]) != before[0]   # its own run's hits


def test_its_groups_are_rank_detector_paths_grouped_by_hand(live, tmp_path):
    out = _drive(tmp_path).result
    set_active_context(out["context_name"])
    by_hand = defaultdict(lambda: [0, 0.0])
    for p in rank_detector_paths("det", top_n=100_000)["data"]:
        by_hand[tuple(p["path_types"])][0] += 1
        by_hand[tuple(p["path_types"])][1] += p["energy"]
    assert {tuple(g["path_types"]): g["count"] for g in out["groups"]} == {k: v[0] for k, v in by_hand.items()}
    for g in out["groups"]:
        assert g["total_energy"] == pytest.approx(by_hand[tuple(g["path_types"])][1])


def test_the_bundle_reloads_after_the_kernel(live, tmp_path):
    out = _drive(tmp_path).result
    assert get_context(out["context_name"])["run_dir"] == out["bundle"]
    loaded = load_run_context(out["bundle"], "reloaded")
    assert loaded["status"] == "ok", loaded
    assert loaded["data"]["n_segments"] == out["segments"]
    assert loaded["data"]["params"]["numerical_params"]["rays"] == RAYS
    set_active_context("reloaded")
    from ray_tracing_shapely.analysis.agentic_tools import query_rays
    hits = query_rays("SELECT COUNT(DISTINCT ray_uuid) FROM detector_hits")["data"]["rows"][0][0]
    assert hits == out["hits"]                                            # the run's own hits, saved


def test_wrong_answers_are_refused(live, run, tmp_path):
    flow = TargetedResimulationFlow(tmp_path, render_svg=False)
    assert not flow.answer("nope")["accepted"]
    scene, *_ , result = run
    set_context_from_result(scene, result, context_name="forward_only")
    out = flow.answer("forward_only")
    assert not out["accepted"] and "bidirectional" in out["reason"]
    assert flow.answer(None)["accepted"]
    assert not flow.answer(10_000)["accepted"] and not flow.answer("first")["accepted"]
    assert flow.answer(1)["accepted"]
    assert not flow.answer("no_such_source")["accepted"]
    assert flow.answer("src")["accepted"]
    assert not flow.answer({"rayz": 10})["accepted"]
    assert not flow.answer({"cone_half_angle_deg": 0})["accepted"]
    assert not flow.answer({"context_name": "forward_only"})["accepted"]   # a name in use
    assert flow.state == "awaiting_options"


def test_a_saved_run_is_not_re_simulated(live, tmp_path):
    out = _drive(tmp_path).result
    load_run_context(out["bundle"], "reloaded")
    flow = TargetedResimulationFlow(tmp_path, render_svg=False)
    refused = flow.answer("reloaded")
    assert not refused["accepted"] and "no live scene" in refused["reason"]


def test_over_a_minute_is_asked_and_false_goes_back(live, tmp_path, monkeypatch):
    monkeypatch.setattr(trf, "ASK_OVER_S", 1e-3)
    flow = TargetedResimulationFlow(tmp_path, render_svg=False)
    for value in (None, 1, None, {"rays": RAYS}):
        flow.answer(value)
    assert flow.state == "awaiting_go_ahead"
    est = flow.question_state()["context"]
    assert est["rays"] == RAYS and "kernel" in est["where"] and est["other_sources_silenced"] == []
    assert flow.answer(False)["accepted"] and flow.state == "awaiting_options"
    flow.answer({"rays": RAYS})
    assert flow.answer(True)["accepted"] and flow.state == "done"


def test_the_density_starts_the_rays_asked(run):
    scene = run[0]
    for rays, emis in ((300, 2.0), (1000, 0.5), (7, 40.0)):
        src = AngleSource(scene, {"p1": {"x": 0, "y": 0}, "p2": {"x": 1, "y": 0}, "emis_angle": emis,
                                  "symmetric": True, "brightness": 1.0})
        kept = scene.ray_density
        scene.ray_density = density_for(rays, emis)
        try:
            started = len(src.on_simulation_start()["newRays"])
        finally:
            scene.ray_density = kept
        assert started >= rays, (rays, emis, started)
        if density_for(rays, emis) >= 1.0:            # below it, the colour mode raises the density itself
            assert started <= rays + 2, (rays, emis, started)


def test_list_sources_names_the_emitter_and_its_rays(live):
    (src,) = list_sources()["data"]
    assert (src["name"], src["type"], src["emis_angle"]) == ("src", "AngleSource", 40)
    assert src["root_rays"] > 0


def test_an_agent_starts_it_by_name(live, tmp_path):
    flow_tools.set_runs_root(tmp_path)
    try:
        kinds = {k["kind"]: k for k in flow_tools.flow_kinds()["data"]["kinds"]}
        assert [q["name"] for q in kinds["targeted_resimulation"]["questions"]] == \
            ["context_name", "path", "source", "options", "go_ahead"]
        started = flow_tools.flow_start("targeted_resimulation")["data"]
        assert started["question"]["name"] == "context_name"
        assert started["context"]["active"] == "default"
        run_id = started["run_id"]
        for value in (None, 1, None, {"rays": RAYS}):
            out = flow_tools.flow_answer(run_id, value)
        assert out["status"] == "ok" and out["data"]["state"] == "done", out
    finally:
        flow_tools.set_runs_root(None)


def test_two_runs_of_one_scene_keep_their_own_detector_hits(run):
    """The scene's detectors hold the last run's hits; each context keeps its own (C-AGENT-04)."""
    scene, source, det, _bidir, _result = run
    first = Simulator(scene, max_rays=40000).run_with_result()
    set_context_from_result(scene, first, context_name="a")
    kept = source.emis_angle
    source.emis_angle = 5
    try:
        second = Simulator(scene, max_rays=40000).run_with_result()
    finally:
        source.emis_angle = kept
    set_context_from_result(scene, second, context_name="b")
    set_active_context("a")
    assert _hits() == len(first.detector_hits[det.uuid])
    set_active_context("b")
    assert _hits() == len(second.detector_hits[det.uuid]) != len(first.detector_hits[det.uuid])


def _two_source_scene():
    """The slab with a second, wide source beside the first, and a narrow cone in place of the first."""
    scene, source, det = _build_scene()
    other = AngleSource(scene, {"p1": {"x": 20, "y": 30}, "p2": {"x": 20, "y": 29}, "emis_angle": 60,
                                "symmetric": True, "brightness": 1.0})
    other.name = "other"
    scene.add_object(other)
    narrow = AngleSource(scene, {"p1": dict(source.p1), "p2": dict(source.p2), "emis_angle": 2,
                                 "symmetric": True, "brightness": 1.0})
    narrow.name = "src_targeted"
    return scene, source, other, narrow, det


def test_the_other_sources_are_silenced_and_put_back():
    scene, source, other, narrow, det = _two_source_scene()
    started_before = len(other.on_simulation_start()["newRays"])
    result = run_targeted_resimulation(scene, source, narrow, max_rays=40000, ray_density=density_for(50, 2))
    roots = [s for s in result.segments if s.parent_uuid is None]
    assert roots and {s.source_uuid for s in roots} == {narrow.uuid}
    assert "on_simulation_start" not in vars(other)                       # its own method again
    assert len(other.on_simulation_start()["newRays"]) == started_before
    assert other in scene.objs and source in scene.objs and narrow not in scene.objs


def test_left_emitting_they_stay_out_of_the_summary():
    scene, source, other, narrow, det = _two_source_scene()
    result = run_targeted_resimulation(scene, source, narrow, max_rays=40000, ray_density=density_for(50, 2),
                                       silence_other_sources=False)
    roots = [s for s in result.segments if s.parent_uuid is None]
    assert {s.source_uuid for s in roots} == {narrow.uuid, other.uuid}
    everyone, own = bounce_groups(result, det.uuid), bounce_groups(result, det.uuid, narrow.uuid)
    assert own["roots"] == sum(s.source_uuid == narrow.uuid for s in roots) < everyone["roots"]
    by_uuid = {s.uuid: s for s in result.segments}
    own_hits = {r["ray_uuid"] for r in result.detector_hits[det.uuid] if by_uuid[r["ray_uuid"]].source_uuid == narrow.uuid}
    assert own["hits"] == len(own_hits) < everyone["hits"]


def test_the_segment_limit_is_sized_from_the_rays(live, tmp_path, monkeypatch):
    scene, source, det, bidir, result = live
    own = [s for s in result.segments if s.source_uuid == source.uuid]
    per_ray = len(own) / sum(1 for s in own if s.parent_uuid is None)
    flow = TargetedResimulationFlow(tmp_path, render_svg=False)
    for value in (None, 1, None, {"rays": RAYS}):
        assert flow.answer(value)["accepted"]
    assert flow.options["max_rays"] == max(1000, math.ceil(math.ceil(RAYS * per_ray) * trf.SEGMENTS_HEADROOM))
    assert flow.estimate["segments"]["per_ray"] == pytest.approx(per_ray) and not flow.estimate["segments"]["may_truncate"]

    monkeypatch.setattr(trf, "MAX_SEGMENTS", 5000)
    flow = TargetedResimulationFlow(tmp_path, render_svg=False)
    for value in (None, 1, None):
        assert flow.answer(value)["accepted"]
    refused = flow.answer({"rays": 10_000})
    fit = int(5000 / (per_ray * trf.SEGMENTS_HEADROOM))
    assert not refused["accepted"] and f"ask at most {fit:,} rays" in refused["reason"]
    given = flow.answer({"rays": 10_000, "max_rays": 50})                 # given: kept, and the estimate warns
    assert given["accepted"] and flow.options["max_rays"] == 50 and flow.estimate["segments"]["may_truncate"]
