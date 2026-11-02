"""
Python-specific package: eye_safety_classification_flow

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
PYTHON-SPECIFIC PACKAGE: eye_safety_classification_flow
===============================================================================
A supervised, observable state-machine layer over `eye_safety`'s
`classify_measurement` functions -- P-CLASSIFICATION-RUN, see
dev_doc/architecture/components/eye_safety_classification_flow.md and
dev_doc/architecture/contracts/C-EYE-05.md. Design rationale:
dev_doc/architecture/components/eye_safety_classification_flow.md.

Not folded into `eye_safety` itself: two new dependencies (`transitions`,
`graphviz`) that the pure-math `eye_safety` package -- and its own test
suite, which asserts exact numeric agreement with published worked
examples -- has no need to carry. This package only ever *calls*
`eye_safety.iec60825_1`/`eye_safety.iec62471`'s functions; it never
duplicates or modifies their formulas.
===============================================================================
"""

from .persistence import (
    STALENESS_S,
    make_run_id,
    run_dir,
    write_inputs,
    append_event,
    read_events,
    write_result,
    read_result,
    append_manifest,
    read_manifest,
    latest_manifest_rows,
    update_heartbeat,
    read_heartbeats,
    is_stale,
)
from .flow_base import ObservableFlow, graphviz_available
from .dimensional_checks import (
    expected_dimensionality_for_hazard,
    checked_hazard_value,
    checked_scalar,
    checked_radiance_from_irradiance,
    checked_irradiance_from_radiance,
)
from .explanations import (
    ComparisonExplanation,
    explain_comparison,
    FieldExplanation,
    explain_field,
    MarginSummary,
    summarize_margins,
)
from .iec62471_flow import (
    IEC62471ClassificationFlow,
    IEC62471_STATES,
    IEC62471_TRANSITIONS,
    IEC62471_TERMINAL_STATES,
)
from .iec60825_1_flow import (
    IEC60825_1ClassificationFlow,
    IEC60825_1_STATES,
    IEC60825_1_TRANSITIONS,
    IEC60825_1_TERMINAL_STATES,
)
from .intake_flow import (
    IEC62471IntakeFlow,
    IEC62471_INTAKE_STATES,
    IEC62471_INTAKE_TRANSITIONS,
    IEC62471_INTAKE_TERMINAL_STATES,
    IEC60825_1IntakeFlow,
    IEC60825_1_INTAKE_STATES,
    IEC60825_1_INTAKE_TRANSITIONS,
    IEC60825_1_INTAKE_TERMINAL_STATES,
)

__all__ = [
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
    'ObservableFlow',
    'graphviz_available',
    'expected_dimensionality_for_hazard',
    'checked_hazard_value',
    'checked_scalar',
    'checked_radiance_from_irradiance',
    'checked_irradiance_from_radiance',
    'ComparisonExplanation',
    'explain_comparison',
    'FieldExplanation',
    'explain_field',
    'MarginSummary',
    'summarize_margins',
    'IEC62471ClassificationFlow',
    'IEC62471_STATES',
    'IEC62471_TRANSITIONS',
    'IEC62471_TERMINAL_STATES',
    'IEC60825_1ClassificationFlow',
    'IEC60825_1_STATES',
    'IEC60825_1_TRANSITIONS',
    'IEC60825_1_TERMINAL_STATES',
    'IEC62471IntakeFlow',
    'IEC62471_INTAKE_STATES',
    'IEC62471_INTAKE_TRANSITIONS',
    'IEC62471_INTAKE_TERMINAL_STATES',
    'IEC60825_1IntakeFlow',
    'IEC60825_1_INTAKE_STATES',
    'IEC60825_1_INTAKE_TRANSITIONS',
    'IEC60825_1_INTAKE_TERMINAL_STATES',
]
