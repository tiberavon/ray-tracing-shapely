# `flows`

A procedure drawn as a fixed diagram of boxes, which records every move it
makes and can be watched, questioned and restarted while it runs.

Some procedures are more than one call. They ask for several inputs, each
checked on its own; they reach a decision the caller must make; they have
steps long enough to be worth watching. A **flow** is such a procedure
written as a state machine: a table of boxes and the arrows between them.
Every move from box to box is written down as an event, the current box is
kept in a heartbeat file, and the diagram is redrawn with that box marked.
Any box can say what it is doing, or what it is waiting for.

A run always ends somewhere. Besides its own end, every flow has three
more: `failed`, `cancelled` and `timed_out`. A box with long work does not
run it inline: it hands it, as a **job** of plain data, to an **executor**,
and keeps the **handle** the executor returns in the run's heartbeat. The
flow follows the handle, never the process list. A run whose record and
reality disagree (its process gone, its job ended unseen) is flagged when
the runs are listed.

A box that asks a question states it as data, a `FlowField`: the kind of
answer, its unit, its default, and why it is asked. What the question is
answered from, such as a table to choose a limit from, comes with it as its
context. One verb, `answer`,
answers any box of any flow, so an agent can drive a flow it has never seen
through nine generic tools, starting from the list of flows that can be
started by name.

This component is the machine and the record. The flows themselves live
with the domain they belong to:
- the eye-safety classification and intake flows, in
  `eye_safety_classification_flow`;
- the rayfile slicing flow, in `nonimaging_design`;
- the targeted re-simulation flow and the parameter study, in
  `analysis_run_registry` (`targeted_resimulation`, `parameter_study`);
- the two comparison flows, in `optiland_scene_bridge`, registered as kinds
  by the satellite: 2D against 3D ray by ray (`compare_2d_3d`), and a
  rayfile's slice against its records in 3D (`compare_slice_3d`).

## Concepts this component realises

- **`KD10`:** the diagram never changes shape. A flow's boxes and arrows are
  a fixed table, given when the flow is built. A box that has nothing to do
  for this input is still entered, and says so. So one run's diagram can be
  checked against another's, and against the procedure it stands for.
- **`KA9`:** every answer is checked where it enters, once. The box's own
  check decides; a refusal leaves the flow where it was, says why, and
  gives an example. A later check that sends the flow back to an earlier
  question says so in the reply (`sent_back`).
- **`KA4`:** a run can be reset. `reset` goes back to `start` from any box,
  a finished one included, as a new attempt of the same run. Every event
  carries its attempt number, so the log keeps every attempt; the result
  holds the latest.
- **`KC7`:** the code that records a run never loads the machinery that ran
  it. Reading a run's folder, the jobs behind it, the run list and the
  dashboard need only the standard library. Only the machine needs the
  state-machine library.

## Modules

| File | What it holds |
|---|---|
| `flows/flow_base.py` | `ObservableFlow`: the machine. Takes a table of boxes and arrows; records every move as an event and a heartbeat; redraws `state.svg`; owns `reset`, `explain_current_state()`, `pending_field()`/`answer()`/`answer_default()`, and the long-step and failure-end methods: `submit_step` for one job, `submit_group` for several side by side, followed as one step (`C-FLOW-01`). Needs the `flows` extra. |
| `flows/persistence.py` | A run's folder: the inputs, the event log, the result, the run log, the heartbeats; and `is_stale`, a run silent too long while not finished. |
| `flows/fields.py` | `FlowField`: a box's question as data (kind, unit, default, why, example, the file `pattern` a path fits), how an answer of each kind is shaped from JSON; `FieldExplanation`: the question as a message; the form a json answer can be asked as, field by field (`FORM_KINDS`, `FORM_FIELD_KINDS`). |
| `flows/kinds.py` | The flows that can be started by name (`register_flow_kind`, by import path): the core's five, `rayfile_slicing`, `targeted_resimulation`, `parameter_study`, `iec62471_intake`, `iec60825_1_intake`. |
| `flows/executors.py`, `flows/worker.py` | `Job`, `Handle`, `JobStatus`; the executor interface (`submit`, `status`, `result`, `cancel`, `logs`); `InProcessExecutor` (in the calling thread) and `LocalProcessExecutor` (one low-priority worker process per job, with its own folder and heartbeat); `executor_for(handle)`, which follows a handle read back from a record. A job's `start_limit_s` bounds how long it may stay queued. |
| `flows/modal_executor.py` | `ModalExecutor`: jobs on a deployed Modal app's function, followed by the call's id from any process; progress, heartbeat and cancel requests through a `modal.Dict`; the hard limit enforced when the job is looked at; `logs` with the app's Modal logs, which hold a container's start-up failure, and the job's own output. `remote_run`, the deployed function's body. `submit_many(jobs)` sends a batch at once, in threads, and each flow's own `submit` of the same `Job` picks up its handle, so a batch of flows starts in about one round trip. A start limit of 3 minutes by default, and a queued job failed at once when its function's containers keep failing to start (Modal's function statistics). Telemetry in `JobStatus.telemetry`, copied into the run's record: the queue while queued; the commit the deployed code was built from, the run time and an estimated cost once ended. `workspace_spend` and `spend_summary` (and `python -m ray_tracing_shapely.flows.modal_executor spend [--summary]`) read the billed spend; a window over 7 days is read as days and then hours, the most Modal's hourly report spans. `modal` is imported only when an executor is made; it is the `modal` extra. |
| `flows/budgets.py` | Measured rates (seconds per 2D ray, per 3D ray), estimates from them, and the question an estimate over the limit becomes; a job's start-up by executor (`JOB_START_S`) and a Modal core's speed against this machine's (`MODAL_SPEED`). |
| `flows/runs.py` | The flows of this process by run id; `list_runs`, every run on record checked against its process and its job. |
| `flows/agentic.py` | The nine flow tools, added to the tool lists by an explicit `register()`: `flow_kinds`, `flow_start`, `flow_question`, `flow_answer`, `flow_reset`, `flow_result`; `flow_list`, `flow_wait`, `flow_cancel`. Runs an agent starts go under one root (`set_runs_root`). |
| `flows/widget.py` | `flow_form(flow)`: any flow as a form in a notebook cell (an `anywidget`, the `widgets` extra, imported only when a form is made). It draws the flow's `question_state()`: the diagram, the question by its kind, its context, the explanation, the last refusal, a send-back, a job's progress (polled while it runs), the result; and sends back what the person did as messages (`answer`, `default`, `reset`, `poll`, `browse`), which `FlowForm.handle` applies through the flow's own `answer`. A path question shows the working directory, the files under it that fit the field's `pattern` (`find_files`), and a folder browser (`list_folder`); a json question with a form (`question_form`) is asked field by field (dropdowns, numbers, checkboxes, a second axis added with a button), the page building the answer, with "Edit as JSON" beside it; one without a form gets "Use the example". All state is the flow's; another view can be drawn over the same messages. Its logic is `FlowFormModel`, with no widget library; the widget wraps it, and so does the `web` component's page. |
| `flows/transcript.py` | A run's record as a markdown page (`transcript_markdown`, `write_transcript`): the diagram, every box in order with what it asked, what was answered, refused or sent back, and what it did, then the result, its lists of rows as tables and the pictures it names. Every path written relative to the page. Standard library only: reading a record never loads the machine (`KC7`). |
| `flows/dashboard.py` | A small web page, served from the standard library on the local machine only (`python -m ray_tracing_shapely.flows.dashboard`, every folder under `flow_runs/` by default, rescanned on each reload, so a new experiment's folder appears without a restart). It reads the runs as `list_runs` does, whatever the job's executor: what needs attention, with the flags; each experiment's cases against the end each was meant to reach (`ObservableFlow.label_experiment`: a run meant to fail that fails is a pass); each live run's question, job, progress, time against budget, telemetry and last events; each run that ended badly, and was not meant to, with its reason first and its log tail folded; the history, filtered by state, folder or flag. Each run id opens the run's own page: every event, its result, its log tail and its state diagram. Money: each run's and experiment's estimated compute cost (the jobs' executor telemetry; a job on this machine is "local"), and a card with Modal's billed spend over the last 24 h and this month against the monthly credit, read every 10 minutes by a background thread that runs the `spend --summary` command, so the dashboard never imports Modal. A folder that does not exist is refused at start, with the ones that do. |

## What a job costs

**Before a job starts: its time.** `budgets.estimate_s` multiplies a count (rays,
segments, pencils) by a rate measured on the development machine
(`MEASURED_RATES_S`, each with where it was measured). On Modal:
- the rate is scaled by `MODAL_SPEED`: a Modal core takes 0.6–0.75 of the
  development machine's time;
- each job adds `JOB_START_S` (15 s for a new container and the imports);
- a group adds `MODAL_PER_JOB_S` (1.5 s) for each of its jobs, for submitting,
  polling and fetching.

A caller with a better rate passes its own. A flow that sends a long step away
shows this estimate before the step starts, and asks above a minute.

**Once a job has ended: an estimated cost.** `ModalExecutor` copies the job's run
time into its telemetry, and `cost_usd_est`: that time at the function's
resources (`cpu`, `memory_gib`) and Modal's published CPU and memory rates
(`CPU_USD_PER_CORE_S`, `MEMORY_USD_PER_GIB_S`). A flow's record and the dashboard
sum these per run and per experiment. A job on this machine shows "local".

**The bill.** `workspace_spend` and `spend_summary` read Modal's billing report
by app; the dashboard's spend card shows them against the monthly credit:

```bash
python -m ray_tracing_shapely.flows.modal_executor spend --summary
python -m ray_tracing_shapely.flows.modal_executor spend --hours 48
```

**The estimate is a floor, not the bill.** The bill also counts each container's
start and its idle time before it scales down, and the image build after a
deploy. On this project's runs the bill has been about two to three times the
jobs' estimate, most where there are many short jobs. Budget 2.5 times the
estimate, or send fewer, longer chunks: a minute's work or more each.

## What it produces

- **`P-FLOW-RUN`:** one folder per run, plus a run log and a heartbeat file
  beside the folders. The shape is the same for every flow; each flow
  documents only what its `result.json` holds. Four flows' results are
  ports of their own:
  - `P-CLASSIFICATION-RUN`;
  - `P-INTAKE-RUN`;
  - `P-SLICING-RUN`;
  - `P-COMPARISON-RUN`.

## What it needs from elsewhere

Nothing from this project, except that `agentic.register()` adds its tools
through `agentic_layer`'s `register_tool`. The machine uses `transitions`, and `graphviz`
for the picture. The picture is optional: without the `dot` program a run
goes on, unpictured.

## Promises this component makes and relies on

| Contract | This component's part |
|---|---|
| `C-FLOW-02` | **Owns** it. Every asking box has one question as data and one trigger; one verb answers any flow; a refusal moves nothing; nine generic tools drive every flow with JSON only. |
| `C-AGENT-07` | **Makes** it, with `analysis_run_registry`. A re-simulation's chunks are one group step, their results merged in order. |
| `C-FLOW-01` | **Owns** it. A run ends in its own end or a failure end, its long steps are followed by a handle kept in its record, and the run list flags what disagrees. |
| `C-EYE-05` | **Hosts** it. The classification flows' result equals the direct call; the machine only records it. |
| `C-SOURCE-03` | **Hosts** it, for the rayfile slicing flow. |

## How it is shipped

Core package, under `ray_tracing_shapely/flows/`, behind the `flows` extra
(`transitions`, `graphviz`). Every module but `flow_base` imports with no
extra installed. `modal_executor` needs the `modal` extra, imported only
when a `ModalExecutor` is made. A worker is started as `python -m
ray_tracing_shapely.flows.worker <job folder>`. The old module paths under
`optical_elements/eye_safety_classification_flow/` (`flow_base`,
`persistence`, `dashboard`) are the same modules, kept for one release.
