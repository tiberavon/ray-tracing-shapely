"""
Python-specific module: budgets -- how long a long step should take

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
PYTHON-SPECIFIC MODULE: budgets
===============================================================================
A long step states how long it should take, estimated from its inputs with a
rate measured on this project's own runs. Before a job is submitted, an
estimate over what a box may spend without asking becomes a question to the
caller ("about 17 minutes; sample 3,000 rays instead?"), not a stall. While
it runs, a job past its estimate is flagged over budget, and goes on until it
ends or is cancelled.

The rates are measurements, each with where it was measured. They are of one
machine and one scene, so an estimate is an order of magnitude, not a
promise; a caller with a better rate passes its own.
===============================================================================
"""

from __future__ import annotations

import math
from typing import Dict, Optional, Tuple

#: Seconds per unit of work, and where each was measured.
MEASURED_RATES_S: Dict[str, Tuple[float, str]] = {
    "simulate_2d_ray": (
        0.020,
        "2D Simulator, one ray, the R608 slice through the TIR collimator: 3,000 rays in "
        "about a minute on the development machine (pure Python, one thread)",
    ),
    "simulate_2d_segment": (
        7.5e-4,
        "2D Simulator, one segment with its hit recorded, a narrow cone through the TIR collimator: "
        "a 1,000-ray chunk, 17,348 segments, in 13.0 s on the development machine (pure Python, one "
        "thread). A flow that can measure its own scene (a pilot of its rays) uses that instead",
    ),
    "context_2d_segment": (
        2.0e-4,
        "after a 2D run, one segment into an agent context, here: merging the chunks, the context's "
        "database, grouping the paths, saving the bundle. 200,010 segments of a targeted "
        "re-simulation through the TIR collimator in 39 s on the development machine, the database "
        "nine tenths of it",
    ),
    "trace_3d_ray": (
        9.0e-4,
        "Optiland non-sequential trace, numpy backend, one rayfile record through the revolved "
        "TIR collimator: 100,000 records in 1 to 1.5 minutes on the development machine "
        "(the upper end taken)",
    ),
    "trace_3d_pencil_ray": (
        1.4e-4,
        "Optiland non-sequential trace, numpy backend, one ray of a pencil (the 2D-against-3D "
        "comparison's 3D job): 100,080 rays from the TIR collimator's focal point in 13.8 s on the "
        "development machine, paths recorded and split. A rayfile record costs more (trace_3d_ray): "
        "its source is sampled from the file, and its records are kept",
    ),
}

#: Seconds a job takes beyond its work, by executor: for a worker process, starting it, importing
#: the packages and building the scene, measured at about 6 s for a one-ray job on the development
#: machine; for Modal, a new container and the imports.
JOB_START_S: Dict[str, float] = {"local_process": 6.0, "in_process": 0.0, "modal": 15.0}

#: A Modal core's time per unit, against the development machine's (`MEASURED_RATES_S`): 0.6 for
#: the 3D pencils (0.081 ms against 0.138), 0.75 for the 2D (15 ms against 20), 0.6 for a 2D
#: segment (0.44 ms against 0.75, a targeted re-simulation's chunks), each measured on
#: one core; a rayfile's 3D records are taken to be like the pencils.
MODAL_SPEED: Dict[str, float] = {"simulate_2d_ray": 0.75, "simulate_2d_segment": 0.6,
                                 "trace_3d_pencil_ray": 0.6, "trace_3d_ray": 0.6}

#: Seconds a group of Modal jobs takes beyond its slowest job and `JOB_START_S`, for each job in it:
#: submitting, polling and fetching each result. Fitted on a 2D re-simulation sent as 21 chunks
#: (back 46 s after the slowest chunk's own run) and as 5 chunks (20 s); 15 s plus 1.5 s a chunk
#: gives 46.5 s and 22.5 s.
MODAL_PER_JOB_S: float = 1.5


#: What a box may spend without asking, by default: a minute, the line past
#: which a job is run through an executor and waited on, not run inline.
ASK_OVER_S: float = 60.0


def rate_s(kind: str, rates: Optional[Dict[str, float]] = None) -> float:
    """The seconds per unit for ``kind``: the caller's own rate if given, else
    the measured one."""
    if rates and kind in rates:
        return float(rates[kind])
    try:
        return MEASURED_RATES_S[kind][0]
    except KeyError:
        raise ValueError(f"no rate for {kind!r}; known: {sorted(MEASURED_RATES_S)}") from None


def estimate_s(kind: str, count: float, *, rates: Optional[Dict[str, float]] = None) -> float:
    """How long ``count`` units of ``kind`` should take, in seconds."""
    return rate_s(kind, rates) * float(count)


def affordable_count(kind: str, limit_s: float, *, rates: Optional[Dict[str, float]] = None) -> int:
    """The most units of ``kind`` that fit in ``limit_s``: the "instead" a
    question over budget offers."""
    return int(math.floor(limit_s / rate_s(kind, rates)))


def format_duration(seconds: float) -> str:
    """``"about 40 seconds"``, ``"about 17 minutes"``, ``"about 2.5 hours"``."""
    s = float(seconds)
    if s < 90:
        return f"about {max(1, round(s))} seconds"
    if s < 90 * 60:
        return f"about {round(s / 60)} minutes"
    return f"about {s / 3600:.1f} hours"


def over_budget_question(kind: str, count: float, *, limit_s: float = ASK_OVER_S,
                         rates: Optional[Dict[str, float]] = None) -> Optional[str]:
    """The question to ask before submitting ``count`` units of ``kind``, or
    None when the estimate is within ``limit_s``."""
    est = estimate_s(kind, count, rates=rates)
    if est <= limit_s:
        return None
    fit = affordable_count(kind, limit_s, rates=rates)
    unit = kind.split("_")[-1]
    return (f"{count:,.0f} x {kind} is estimated at {format_duration(est)}, over the "
            f"{format_duration(limit_s)} allowed without asking. Go ahead, or use {fit:,} {unit}s instead?")
