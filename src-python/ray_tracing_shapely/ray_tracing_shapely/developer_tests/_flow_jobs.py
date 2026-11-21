"""
Python-specific module: test jobs for the flow executors
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
Procedures named by import path, so a worker process can run them.
===============================================================================
"""

from __future__ import annotations

import os
import time


def count(inputs, ctx):
    """Count to ``n``, reporting progress, ``step_s`` apart; cancellable."""
    n, step = int(inputs["n"]), float(inputs.get("step_s", 0.0))
    for i in range(n):
        time.sleep(step)
        ctx.progress(i + 1, n, "counting")
    out = {"counted": n}
    # The process's niceness, read with getpriority: os.nice(0) returns the
    # C library's nice(), which on macOS is 0 on success, not the niceness.
    if hasattr(os, "getpriority"):
        out["nice"] = os.getpriority(os.PRIO_PROCESS, 0)
    return out


def boom(inputs, ctx):
    raise ValueError(inputs.get("why", "boom"))


def deaf(inputs, ctx):
    """Sleep without ever reporting progress: a cancel cannot reach it."""
    time.sleep(float(inputs["s"]))
    return "woke"


def vanish(inputs, ctx):
    """Leave without recording an end, as a killed worker would."""
    ctx.progress(1, 2)
    os._exit(3)
