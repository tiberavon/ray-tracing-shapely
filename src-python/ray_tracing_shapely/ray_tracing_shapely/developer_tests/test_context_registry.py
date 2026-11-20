"""
Python-specific module: test context registry
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
The agentic context registry: more than one run held at once
===============================================================================
Two runs of one prism, one ray each at different heights, are loaded into two
named contexts. The tools read the active one only; making a context never
switches to it; clearing one closes its own databases and leaves the others.
===============================================================================
"""
import sqlite3

import pytest

from ray_tracing_shapely.analysis.agentic_tools import (
    DEFAULT_CONTEXT_NAME,
    clear_context,
    get_context,
    get_extension_context,
    list_contexts,
    query_rays,
    set_active_context,
    set_context,
    set_extension_context,
)
from ray_tracing_shapely.analysis.tool_registry import check_tool_lists, get_agentic_tools, get_exposed_tools
from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.glass.glass import Glass
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay
from ray_tracing_shapely.core.simulator import Simulator


def _run(y: float):
    """A prism and one ray at height y: the scene and its segments."""
    scene = Scene()
    prism = Glass(scene)
    prism.path = [{'x': 200, 'y': 50, 'arc': False}, {'x': 250, 'y': 100, 'arc': False},
                  {'x': 150, 'y': 100, 'arc': False}]
    prism.refIndex = 1.5
    prism.name = 'prism'
    scene.add_object(prism)
    ray = SingleRay(scene)
    ray.p1, ray.p2, ray.brightness = {'x': 100, 'y': y}, {'x': 250, 'y': y}, 1.0
    scene.add_object(ray)
    return scene, Simulator(scene).run()


@pytest.fixture(scope="module")
def runs():
    return {"low": _run(90.0), "high": _run(70.0)}


def _first_ray_y():
    # the source ray's height: which run the tools are reading
    out = query_rays("SELECT p1_y FROM rays WHERE parent_uuid IS NULL")
    assert out["status"] == "ok", out
    return out["data"]["rows"][0][0]


def test_a_named_context_is_made_without_switching_to_it(runs):
    set_context(*runs["low"])
    set_context(*runs["high"], context_name="high")
    assert _first_ray_y() == pytest.approx(90.0)          # still the default
    listed = list_contexts()["data"]
    assert listed["active"] == DEFAULT_CONTEXT_NAME
    assert {c["name"]: c["active"] for c in listed["contexts"]} == {DEFAULT_CONTEXT_NAME: True, "high": False}
    assert all(c["origin"] == "live" and c["n_segments"] > 0 for c in listed["contexts"])


def test_switching_changes_what_the_tools_read(runs):
    set_context(*runs["low"])
    set_context(*runs["high"], context_name="high")
    assert set_active_context("high")["status"] == "ok"
    assert _first_ray_y() == pytest.approx(70.0)
    assert set_active_context(DEFAULT_CONTEXT_NAME)["status"] == "ok"
    assert _first_ray_y() == pytest.approx(90.0)


def test_an_unknown_name_is_an_error_naming_the_contexts_that_exist(runs):
    set_context(*runs["low"])
    set_context(*runs["high"], context_name="high")
    out = set_active_context("nope")
    assert out["status"] == "error"
    assert "'default'" in out["message"] and "'high'" in out["message"]
    assert list_contexts()["data"]["active"] == DEFAULT_CONTEXT_NAME


def test_clearing_one_context_closes_its_database_and_leaves_the_others(runs):
    set_context(*runs["low"])
    set_context(*runs["high"], context_name="high")
    db_high = get_context("high")["db"]
    set_active_context("high")
    clear_context("high")
    with pytest.raises(sqlite3.ProgrammingError):
        db_high.execute("SELECT 1")
    assert list_contexts()["data"]["active"] == DEFAULT_CONTEXT_NAME     # back to the default
    assert _first_ray_y() == pytest.approx(90.0)


def test_clearing_all_returns_to_one_empty_default(runs):
    set_context(*runs["low"])
    set_context(*runs["high"], context_name="high")
    set_active_context("high")
    clear_context()
    listed = list_contexts()["data"]
    assert listed["active"] == DEFAULT_CONTEXT_NAME
    assert [c["name"] for c in listed["contexts"]] == [DEFAULT_CONTEXT_NAME]
    assert query_rays("SELECT 1")["status"] == "error"


def test_an_extension_keeps_its_objects_in_each_context(runs):
    set_context(*runs["low"])
    set_context(*runs["high"], context_name="high")
    conn = sqlite3.connect(":memory:")
    set_extension_context("pkg.thing", {"db": conn, "tag": "high"}, context_name="high")
    with pytest.raises(RuntimeError, match="set it"):
        get_extension_context("pkg.thing", "set it")                   # not in the active context
    set_active_context("high")
    assert get_extension_context("pkg.thing", "set it")["tag"] == "high"
    assert [c["extensions"] for c in list_contexts()["data"]["contexts"] if c["name"] == "high"] == [["pkg.thing"]]
    clear_context("high")
    with pytest.raises(sqlite3.ProgrammingError):                      # closed with its context
        conn.execute("SELECT 1")


def test_re_setting_a_context_replaces_it_whole(runs):
    set_context(*runs["low"])
    old_db = get_context()["db"]
    get_context()                                                      # a copy: the registry is untouched
    set_context(*runs["high"])
    with pytest.raises(sqlite3.ProgrammingError):
        old_db.execute("SELECT 1")
    assert _first_ray_y() == pytest.approx(70.0)


def test_both_tools_are_in_the_lists():
    names = {t["name"] for t in get_agentic_tools()}
    exposed = {f.__name__ for f in get_exposed_tools()}
    assert {"list_contexts", "set_active_context"} <= names & exposed
    assert check_tool_lists() == []
