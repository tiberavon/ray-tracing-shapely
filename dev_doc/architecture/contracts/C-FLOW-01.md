---
id: C-FLOW-01
title: A flow's run ends in its own end or in failed, cancelled or timed_out, its long steps are followed by a handle kept in its record, and the run list says which records disagree with what is running
parties:
  provides: flows (flow_base.ObservableFlow, executors, runs.list_runs, agentic)
  relies:   'whoever starts a flow, waits on it or lists runs: a person, a notebook, an agent through flow_list, flow_wait, flow_cancel'
port: P-FLOW-RUN
viewpoint: agentic
status: enforced
failure_mode: loud
checked_by: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_flow_executors.py::test_a_long_box_ends_done_with_its_result; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_flow_executors.py::test_failure_cancel_and_reset; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_flow_executors.py::test_local_process_failure_and_a_worker_that_dies; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_flow_executors.py::test_cancel_cooperative_and_not; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_flow_executors.py::test_a_hard_limit_times_out; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_flow_executors.py::test_the_run_list_flags_what_the_record_gets_wrong; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_modal_executor.py::test_a_job_that_never_starts_is_cancelled_at_its_start_limit; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_modal_executor.py::test_a_job_runs_there_and_its_handle_is_followed_from_here; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_modal_executor.py::test_a_running_job_past_its_limit_is_cancelled_and_timed_out; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_modal_executor.py::test_containers_failing_to_start_fail_the_job_before_its_start_limit; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_flow_executors.py::test_a_group_of_jobs_is_one_step; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_flow_executors.py::test_a_group_fails_with_its_first_failure_and_cancels_the_rest
witness: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_flow_executors.py::test_over_budget_is_flagged_and_the_run_goes_on; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_flow_executors.py::test_an_estimate_over_the_limit_is_asked_first; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_flow_executors.py::test_local_process_runs_at_low_priority_and_is_followed_from_its_handle; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_flow_executors.py::test_run_ids_do_not_repeat; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_modal_executor.py::test_wait_returns_once_when_a_job_goes_over_its_budget; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_modal_executor.py::test_a_queued_job_over_its_budget_is_not_hung
tracked_by: null
conflicts_with: null
refines: null
rationale: KD10
since: 0.3
---

# C-FLOW-01 — A run ends, or says why it has not

**Assumptions.** A flow is an `ObservableFlow`. A long box hands its work to
an executor through `submit_step` and does not run it inline. A job's
procedure is a module-level function, named by import path.

**Guarantees.**
- **Fixed ends.** Every flow has `failed`, `cancelled` and `timed_out` besides
  its own end, added to its diagram by the machine. Ending in one of them
  writes:
  - an event with the reason (for `failed`, the traceback);
  - `result.json` with `status`, `reason` and the state it ended from;
  - the run log's finish row.

  A finished run's heartbeat records `terminal: true`. `reset` leaves any end
  for a new attempt, and stops an abandoned attempt's job.
- **A handle, not a process name.** `submit_step` keeps the job's handle in
  the run's heartbeat. `poll` follows it through `executor_for(handle)`,
  which needs nothing but the handle, so a record is followed from another
  process or after a restart. `poll` acts on the job's end:
  - done fires the box's `on_done` trigger with the result;
  - failed, cancelled and timed out end the run in the same state;
  - a job its executor has no record of ends the run `failed`, as lost.

  `wait(timeout_s)` polls until the job ends or the timeout passes, and
  returns early when something needs attention: `attention: ["over_budget"]`
  the first time the job goes over its budget (it goes on), or
  `["failed"]` with `log_tail`, the executor's log, when the run failed.
- **A group of jobs is one step.** `submit_group` hands a box's work to an
  executor as several jobs side by side (a remote executor's sent together)
  and follows them as one step. Its record is a job's: its `handle` is the
  first job still going, its `progress` the jobs done of all, and `group`
  holds every handle, so the run list, the dashboard and `wait_all` read it
  as any other. When every job is done, `on_done` fires with their results
  in the jobs' order. The first job that fails, is cancelled or times out
  ends the run the same way, and the others are cancelled; so does a
  `cancel` or a `reset` of the run.
- **A job that cannot start is stopped.** A job's `start_limit_s`, or its
  executor's `default_start_limit_s`, bounds how long it may stay queued.
  Past it, `poll` cancels the job and ends the run `failed`, "did not start
  within ...", with the executor's log: a remote container that fails before
  the procedure runs is stopped, not waited on. An executor that can see
  why a job is not starting may end it sooner: `ModalExecutor` fails a
  queued job once its function's containers have failed to start three
  times since it was submitted.
- **The job's own ends.** An executor reports a job as `done`, `failed`,
  `cancelled` or `timed_out`, or `unknown` when it has no record of it. A
  local worker that dies without recording its end is reported `failed`. A
  cancel is cooperative first (`ctx.progress` raises `JobCancelled`); a worker
  still running after the grace period is terminated.
- **Budgets.** A job's `budget_s` is an estimate.
  - Over `ask_over_s` (default 60 s), `submit_step` submits nothing until the
    caller confirms, and the box's explanation says the estimate.
  - Past its budget, a running job is flagged over budget, as an event and in
    the heartbeat, and goes on.
  - Only a hard `limit_s`, which the caller sets, stops it, as `timed_out`.
- **Record against reality.** `list_runs` follows every run's job and
  process, and flags each disagreement:
  - `crashed`: not finished, and nothing working on it;
  - `uncollected`: its job ended, its record still waits;
  - `hung`: silent or over budget while alive and started;
  - `not_started`: still queued past its start limit (a queued job is
    never `hung`);
  - `never_finished`: a start in the run log, no finish, not alive.
- **Unique run ids.** No two run ids made in one process are equal.

**Invariants.** A run is in exactly one of: its own end, a failure end,
waiting for an answer or a confirmation, following a job, or flagged by
`list_runs`.

**Units and frames.** Seconds; Unix times.

**If the assumption is violated.** Loud. A procedure named without
`module:function`, or not importable, fails its job with the reason. A box
that runs long work inline is outside this contract: the run's heartbeat
goes silent, and `list_runs` flags it `hung` once it is stale.

**Checked by.**
- **Ends.** A long box run in process and in a worker ends `done` with the
  job's result. A failing job ends the run `failed` with its traceback, and
  `reset` runs it again. A cancel ends it `cancelled` and stops the worker. A
  reset stops an abandoned job. A group of three worker jobs ends `done`
  with their results in order; a group with a failing job ends `failed`
  naming it, and its other job is cancelled; a cancelled group stops every
  job.
- **Jobs.** A worker that exits without recording its end is reported
  `failed`; a hard limit gives `timed_out`. A worker that never reports
  progress is still stopped by a cancel, within the grace period.
- **The run list.** A run whose job ended unpolled is `uncollected`, and
  clean after a poll. A run whose process died mid-step is `crashed` and
  `never_finished`.
