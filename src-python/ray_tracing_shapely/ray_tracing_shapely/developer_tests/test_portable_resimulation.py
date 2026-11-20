"""
Python-specific module: test portable re-simulation
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
The targeted re-simulation's portable route
===============================================================================
The scene goes as plain data (portable_scene), the rays in chunks, a job each
(simulate_rays_2d_segments_job); the chunks come back as segments, merged
here and mapped back to the live scene by name (merge_segment_results). With
the brightness threshold fixed, the chunks merged are the one run, and the
portable route is the live route, segment for segment. A scene whose objects
cannot be mapped back is refused, by name.
===============================================================================
"""
import math

import pytest

from ray_tracing_shapely.analysis import targeted_resimulation_flow as trf
from ray_tracing_shapely.analysis.agentic_tools import (
    get_context,
    load_run_context,
    set_bidirectional_context,
    set_context_from_result,
)
from ray_tracing_shapely.analysis.portable_scene import NotPortable, build_portable_scene, portable_scene
from ray_tracing_shapely.analysis.ray_jobs import (
    chunk_rays,
    merge_segment_results,
    sample_source_rays,
    simulate_rays_2d_segments_job,
)
from ray_tracing_shapely.analysis.targeted_resimulation import run_targeted_resimulation
from ray_tracing_shapely.analysis.targeted_resimulation_flow import TargetedResimulationFlow, density_for
from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.light_source.angle_source import AngleSource
from ray_tracing_shapely.core.scene_objs.other.detector import Detector
from ray_tracing_shapely.core.simulator import Simulator
from ray_tracing_shapely.optical_elements.prisms.refractometer import RefractometerPrism

from test_targeted_resimulation import _build_scene, _run_bidirectional


class _Ctx:
    def progress(self, *_a, **_k):
        pass


CTX = _Ctx()


def _key(result):
    """A result's segments, without their uuids: ends, brightness, interaction, the object hit."""
    return sorted(((s.p1["x"], s.p1["y"], s.p2["x"], s.p2["y"], s.brightness_s, s.brightness_p,
                    s.interaction_type, s.hit_surface_uuid, s.parent_uuid is None) for s in result.segments),
                  key=repr)


def _hits(result, det):
    return sorted((r["position"], r["brightness_total"]) for r in result.detector_hits.get(det.uuid, []))


def _narrow(scene, source, emis=3.0):
    narrow = AngleSource(scene, {"p1": dict(source.p1), "p2": dict(source.p2), "emis_angle": emis,
                                 "symmetric": True, "brightness": 1.0})
    narrow.name = "src_narrow"
    return narrow


def _portable_run(scene, narrow, density, chunk=None):
    rays = sample_source_rays(narrow, density)
    inputs = {"scene": portable_scene(scene), "source_name": narrow.name, "min_brightness_exp": 6,
              "max_rays": 100_000}
    parts = chunk_rays(rays, chunk) if chunk else [rays]
    results = [simulate_rays_2d_segments_job({**inputs, "rays": c}, CTX) for c in parts]
    return merge_segment_results(results, scene, source=narrow, max_rays=100_000)


def test_chunks_merged_are_the_one_run():
    scene, source, det = _build_scene()
    narrow = _narrow(scene, source)
    density = density_for(60, 3.0)
    one, merged = _portable_run(scene, narrow, density), _portable_run(scene, narrow, density, chunk=17)
    assert len(one.segments) > 60 and _key(merged) == _key(one)
    assert _hits(merged, det) == _hits(one, det) != []
    hit_uuids = {r["ray_uuid"] for r in merged.detector_hits[det.uuid]}
    assert hit_uuids <= {s.uuid for s in merged.segments}                  # each hit names a merged segment
    assert all(merged.lineage.get_segment(s.uuid) is s for s in merged.segments)


def test_the_portable_route_is_the_live_route():
    scene, source, det = _build_scene()
    narrow = _narrow(scene, source)
    density = density_for(60, 3.0)
    live = run_targeted_resimulation(scene, source, narrow, max_rays=100_000, record_surface_hits=True,
                                     min_brightness_exp=6, ray_density=density)
    portable = _portable_run(scene, narrow, density, chunk=25)
    assert _key(portable) == _key(live) and _hits(portable, det) == _hits(live, det)
    assert {s.source_uuid for s in portable.segments} == {narrow.uuid}


def test_a_designed_element_travels_as_its_profile():
    scene = Scene()
    scene.color_mode = "linear"
    prism = RefractometerPrism.from_critical_ray_path(scene, n_prism=1.72, n_target=1.33, ray_path_length=20.0)
    prism.name = "prism"
    scene.add_object(prism)
    src = AngleSource(scene, {"p1": {"x": 0, "y": 30}, "p2": {"x": 0, "y": 29}, "emis_angle": 20,
                              "symmetric": True, "brightness": 1.0})
    src.name = "src"
    scene.add_object(src)
    det = Detector(scene, {"p1": {"x": -50, "y": -30}, "p2": {"x": 50, "y": -30}})
    det.name = "det"
    scene.add_object(det)
    described = portable_scene(scene)
    assert [("profile" in d, d["name"]) for d in described["objects"]] == [(True, "prism"), (False, "det")]
    rebuilt = build_portable_scene(described)
    assert [o.name for o in rebuilt.optical_objs] == ["prism", "det"]
    narrow = _narrow(scene, src, emis=20.0)
    live = run_targeted_resimulation(scene, src, narrow, max_rays=100_000, record_surface_hits=True,
                                     min_brightness_exp=6, ray_density=2.0)
    portable = _portable_run(scene, narrow, 2.0, chunk=40)
    assert len(portable.segments) > 100 and _key(portable) == _key(live)


def test_a_scene_that_cannot_be_mapped_back_is_refused():
    scene, source, det = _build_scene()
    det.name = None
    with pytest.raises(NotPortable, match="unnamed: Detector"):
        portable_scene(scene)
    det.name = "slab"
    with pytest.raises(NotPortable, match="shared: slab"):
        portable_scene(scene)


def test_the_job_needs_a_threshold_and_the_merge_known_names():
    scene, source, det = _build_scene()
    narrow = _narrow(scene, source)
    rays = sample_source_rays(narrow, density_for(10, 3.0))
    inputs = {"scene": portable_scene(scene), "rays": rays, "source_name": "s"}
    with pytest.raises(ValueError, match="min_brightness_exp is required"):
        simulate_rays_2d_segments_job(inputs, CTX)
    out = simulate_rays_2d_segments_job({**inputs, "min_brightness_exp": 6}, CTX)
    det.name = "renamed"
    with pytest.raises(ValueError, match="'det', which is not an object of the live scene"):
        merge_segment_results([out], scene, source=narrow, max_rays=1000)


# ---------------------------------------------------------------------------
# The flow
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def run():
    scene, source, det = _build_scene()
    _sim, bidir = _run_bidirectional(scene, det)
    result = Simulator(scene, max_rays=40000, record_surface_hits=True).run_with_result(name="broad")
    return scene, source, det, bidir, result


@pytest.fixture
def live(run):
    scene, source, det, bidir, result = run
    set_context_from_result(scene, result)
    set_bidirectional_context(bidir)
    return run


def _groups(out):
    return [(tuple(g["path_types"]), g["count"], round(g["total_energy"], 12)) for g in out["groups"]]


def _drive(tmp_path, options):
    flow = TargetedResimulationFlow(tmp_path, render_svg=False)
    for value in (None, 1, None, options):
        out = flow.answer(value)
        assert out["accepted"], out
    return flow


def test_the_flow_in_chunks_gives_the_kernels_result(live, tmp_path):
    kernel = _drive(tmp_path, {"rays": 300, "context_name": "k"}).result
    flow = _drive(tmp_path, {"rays": 300, "executor": "local_process", "chunk_rays": 100, "context_name": "p"})
    waited = flow.wait(300)
    assert flow.state == "done", waited
    out = flow.result
    assert out["executor"] == "local_process" and out["chunks"] >= 1 and not out["truncated"]
    assert _groups(out) == _groups(kernel) and out["hits"] == kernel["hits"] and out["roots"] == kernel["roots"]
    assert get_context("p")["run_dir"] == out["bundle"]
    assert load_run_context(out["bundle"], "p_reloaded")["status"] == "ok"
    in_process = _drive(tmp_path, {"rays": 300, "executor": "in_process", "chunk_rays": 70, "context_name": "i"})
    assert in_process.state == "done" and in_process.result["chunks"] == 5
    assert _groups(in_process.result) == _groups(kernel)


def test_an_unportable_scene_is_refused_for_the_executors_not_the_kernel(run, live, tmp_path):
    det = run[2]
    det.name = None
    try:
        flow = TargetedResimulationFlow(tmp_path, render_svg=False)
        for value in (None, 1, None):
            assert flow.answer(value)["accepted"]
        refused = flow.answer({"rays": 50, "executor": "local_process"})
        assert not refused["accepted"] and "unnamed: Detector" in refused["reason"] and "kernel" in refused["reason"]
        assert flow.answer({"rays": 50, "executor": "kernel"})["accepted"]
    finally:
        det.name = "det"


def test_a_failed_chunk_ends_the_run(live, tmp_path, monkeypatch):
    monkeypatch.setattr(trf, "SEGMENTS_JOB", "ray_tracing_shapely.analysis.ray_jobs:no_such_job")
    flow = _drive(tmp_path, {"rays": 100, "executor": "in_process", "chunk_rays": 40, "context_name": "f"})
    assert flow.state == "failed" and "job 1 of 3" in flow.explain_current_state()
    assert not get_context("f")


def test_the_modal_estimate_counts_chunks_and_cost(live, tmp_path, monkeypatch):
    monkeypatch.setattr(trf, "_modal_installed", lambda: True)
    monkeypatch.setattr(trf, "ASK_OVER_S", 1e-3)
    flow = _drive(tmp_path, {"rays": 5000, "executor": "modal", "chunk_rays": 1000})
    assert flow.state == "awaiting_go_ahead"
    est = flow.question_state()["context"]
    assert est["chunks"] == 5 and est["executor"] == "modal" and "Modal" in est["where"]
    pilot = est["pilot"]                       # the run's own rays, here: segments a ray, seconds a segment
    assert 0 < pilot["rays"] <= trf.PILOT_RAYS + 1 and pilot["per_ray"] > 1 and pilot["s_per_segment"] > 0
    segments = math.ceil(5000 * pilot["per_ray"])
    assert est["segments"]["expected_from_pilot"] == segments
    assert est["after_s"] == pytest.approx(segments * 2.0e-4, abs=0.06)   # here, once the rays are back
    per_chunk = 1000 * pilot["per_ray"] * pilot["s_per_segment"] * 0.6 + 15.0
    assert est["simulate_s"] == pytest.approx(per_chunk + 1.5 * 5, abs=0.06)
    assert est["cost_usd_est"] > 0 and est["total_s"] == pytest.approx(per_chunk + 1.5 * 5 + segments * 2.0e-4)
    assert flow.answer(False)["accepted"] and flow.state == "awaiting_options"
