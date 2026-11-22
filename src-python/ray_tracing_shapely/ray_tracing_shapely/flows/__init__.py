"""
Python-specific package: flows

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
PYTHON-SPECIFIC PACKAGE: flows
===============================================================================
The observable flow: a procedure drawn as a fixed diagram of boxes, where
every move is an event and a heartbeat, every box can say what it is doing
or asking, and a run can be reset and tried again -- P-FLOW-RUN, see
dev_doc/architecture/components/flows.md.

    ObservableFlow     the machine (flow_base.py); needs the `flows` extra
    wait_all           follow many runs at once, their jobs' statuses asked in parallel
    persistence        a run's folder: events, result, run log, heartbeats
    FlowField          a box's question as data: kind, unit, default, why
    FieldExplanation   a question a flow is waiting on, as a message (fields.py)
    kinds              the flows that can be started by name
    executors          where a long step runs: Job, Handle, the in-process
                       and local-process executors (executors.py, worker.py)
    budgets            how long a step should take, from measured rates
    runs               the live flows by run id; every run on record, checked
                       against its process and its job (list_runs)
    agentic            the nine flow tools (flow_kinds ... flow_cancel), added by register()
    dashboard          a page showing runs as they happen
    transcript         a run's record as a markdown page (transcript_markdown)
    widget             a flow as a form in a notebook cell (flow_form; the widgets extra)

Everything but `flow_base` and `widget` needs nothing outside the standard library, so
reading a run's record never loads the machinery that ran it [KC7]. The
flows themselves live with their domain: the eye-safety classification and
intake flows, the rayfile slicing flow.
===============================================================================
"""

from . import persistence
from .budgets import ASK_OVER_S, MEASURED_RATES_S, estimate_s, format_duration, over_budget_question
from .executors import (InProcessExecutor, Job, JobCancelled, JobContext, JobStatus, Handle,
                        LocalProcessExecutor, executor_for, procedure_path, register_executor_kind)
from .fields import FIELD_KINDS, REQUIRED, FieldExplanation, FlowField, explain_field
from .kinds import FlowKind, get_flow_kind, register_flow_kind
from .runs import get_run, list_runs, track
from .persistence import (
    STALENESS_S,
    append_event,
    append_manifest,
    is_stale,
    latest_manifest_rows,
    make_run_id,
    read_events,
    read_heartbeats,
    read_manifest,
    read_result,
    run_dir,
    update_heartbeat,
    write_inputs,
    write_result,
)

__all__ = [
    'ObservableFlow',
    'wait_all',
    'graphviz_available',
    'FAILURE_STATES',
    'Job',
    'Handle',
    'JobStatus',
    'JobContext',
    'JobCancelled',
    'InProcessExecutor',
    'LocalProcessExecutor',
    'executor_for',
    'register_executor_kind',
    'procedure_path',
    'ASK_OVER_S',
    'MEASURED_RATES_S',
    'estimate_s',
    'format_duration',
    'over_budget_question',
    'list_runs',
    'get_run',
    'track',
    'persistence',
    'FieldExplanation',
    'explain_field',
    'FlowField',
    'FIELD_KINDS',
    'REQUIRED',
    'FlowKind',
    'register_flow_kind',
    'get_flow_kind',
    'STALENESS_S',
    'make_run_id',
    'run_dir',
    'write_inputs',
    'append_event',
    'read_events',
    'write_result',
    'read_result',
    'append_manifest',
    'read_manifest',
    'latest_manifest_rows',
    'update_heartbeat',
    'read_heartbeats',
    'is_stale',
]


def __getattr__(name):
    # The machine needs `transitions`; the record does not. Loading it on
    # first use lets `flows.persistence` be read where the extra is absent.
    if name in ('ObservableFlow', 'graphviz_available', 'FAILURE_STATES', 'wait_all'):
        from . import flow_base
        return getattr(flow_base, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
