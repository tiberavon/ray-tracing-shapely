"""
Python-specific module: developer_tests/conftest
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
SHARED PYTEST SCAFFOLDING
===============================================================================
Shared pytest scaffolding for the developer tests.

These files were written to be run two ways, and both still work: as a script
(`python test_x.py`), where a `main()` block builds a scene, calls
`set_context`, and passes objects to each test as ordinary arguments; and
under `pytest`, which supplies arguments only as fixtures. Under `pytest` the
second route was broken — 7 failed and 18 errors of 619 — so each test module
now declares its own fixtures, and this file holds the one thing they share.

**Why the fixtures are not here.** There is no shared scene to build one
from: each module has its own
`build_test_scene()` with its own geometry, and the second value it returns is
a prism in three modules and a detector in another. A single fixture would
have to serve four different scenes, so the fixtures live beside the builders
they call.

**What is here.** `set_context` registers the scene, the segments and
optionally the lineage in a module-level dictionary in
`analysis.agentic_tools`, and opens an in-memory SQLite database. That is
global state. The script runners got away with it by calling `set_context`
once and ordering the tests by hand — visibly so: one of them re-sets the
context mid-run with the comment *"since test 16 cleared it"*. Under `pytest`
a test may run alone, in any order, so the context has to be established per
test and torn down after. The autouse fixture below guarantees the teardown
for every test in this directory, whether its module remembers to or not.
"""
import pytest

from ray_tracing_shapely.analysis.agentic_tools import clear_context


@pytest.fixture(autouse=True)
def _agentic_context_is_never_inherited():
    """No test may see a context another test left behind.

    Clearing before as well as after matters: a test that fails part-way
    through its own setup would otherwise leak its context into the next one,
    and the failure would be reported against the wrong test.
    """
    clear_context()
    yield
    clear_context()
