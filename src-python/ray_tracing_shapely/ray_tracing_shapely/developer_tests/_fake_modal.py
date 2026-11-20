"""
Python-specific module: a stand-in for the Modal client, for tests
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
FakeModal -- what ModalExecutor needs of the Modal client, without a network
===============================================================================
Put in place of the module (``sys.modules["modal"] = FakeModal``). A call to
the app "run" runs ``remote_run`` at once, as the deployed function would;
on "never" the call is never started (a container failing on import); on
"slow" it is started and never ends. ``container_errors`` is what the
function's statistics report. Used by the core's and the satellite's tests;
it imports no test library, so a bare install can import it.
===============================================================================
"""

from __future__ import annotations

import itertools
import time
import types

from ray_tracing_shapely.flows import modal_executor
from ray_tracing_shapely.flows.modal_executor import ModalExecutor, remote_run


class _Exc(types.SimpleNamespace):
    pass


class _ModalTimeout(Exception):
    pass


class _Cancelled(Exception):
    pass


class _Expired(Exception):
    pass


class _FnTimeout(Exception):
    pass


class FakeModal:
    """`Function.spawn` on app "run" runs the job at once; on "never" the call is never
    started; on "slow" it is started and never ends."""

    calls: dict = {}
    dicts: dict = {}
    container_errors = 0
    stats_calls = 0
    ids = itertools.count()
    exception = _Exc(TimeoutError=_ModalTimeout, OutputExpiredError=_Expired,
                     FunctionTimeoutError=_FnTimeout, InputCancellation=_Cancelled)

    class _Call:
        def __init__(self):
            self.object_id = f"fc-{next(FakeModal.ids)}"
            self.outcome, self.error, self.cancelled = None, None, False
            FakeModal.calls[self.object_id] = self

        def get(self, timeout=None):
            if self.error is not None:
                raise self.error
            if self.outcome is None:
                raise _ModalTimeout("not yet")
            return self.outcome

        def cancel(self, terminate_containers=False):
            self.cancelled = True
            self.error = _Cancelled("cancelled")

    class _Function:
        def __init__(self, app):
            self.app = app

        def get_current_stats(self):
            FakeModal.stats_calls += 1
            return types.SimpleNamespace(backlog=1, num_total_runners=0)

        def stats(self, since=None):
            FakeModal.stats_calls += 1
            return types.SimpleNamespace(container_started_count=FakeModal.container_errors,
                                         container_error_count=FakeModal.container_errors)

        def spawn(self, job_id, procedure, inputs, files):
            call = FakeModal._Call()
            state = FakeModal.Dict.from_name(modal_executor.STATE_DICT)
            if self.app == "run":
                call.outcome = remote_run(job_id, procedure, inputs, files, state)
            elif self.app == "slow":
                state[job_id] = {"started_at": time.time() - 100.0, "updated_at": time.time(), "progress": {}}
            return call

    class Function:
        @staticmethod
        def from_name(app, name):
            return FakeModal._Function(app)

    class FunctionCall:
        @staticmethod
        def from_id(call_id):
            return FakeModal.calls[call_id]

    class Dict:
        @staticmethod
        def from_name(name, create_if_missing=False):
            return FakeModal.dicts.setdefault(name, {})


def reset(fake=None) -> None:
    """Forget every call, Dict and cached status, as a new process would."""
    fake = fake or FakeModal
    fake.calls.clear()
    fake.dicts.clear()
    fake.container_errors = 0
    fake.stats_calls = 0
    for cache in (ModalExecutor._ended, ModalExecutor._outcomes, ModalExecutor._recent, ModalExecutor._queue_seen,
                  ModalExecutor._functions, ModalExecutor._just_sent, ModalExecutor._function_stats,
                  ModalExecutor._since_stats):
        cache.clear()


__all__ = ["FakeModal", "reset"]
