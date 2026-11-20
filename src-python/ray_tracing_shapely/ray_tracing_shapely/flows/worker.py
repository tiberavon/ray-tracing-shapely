"""
Python-specific module: worker -- runs one job in its own process

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
PYTHON-SPECIFIC MODULE: worker
===============================================================================
    python -m ray_tracing_shapely.flows.worker <job folder>

Started by `LocalProcessExecutor.submit`. Reads `job.json`, runs the
procedure, and writes `status.json` (with a heartbeat every few seconds),
`result.json` and, through its stdout and stderr, `log.txt`.
===============================================================================
"""

import sys

from .executors import run_worker

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python -m ray_tracing_shapely.flows.worker <job folder>", file=sys.stderr)
        sys.exit(2)
    sys.exit(run_worker(sys.argv[1]))
