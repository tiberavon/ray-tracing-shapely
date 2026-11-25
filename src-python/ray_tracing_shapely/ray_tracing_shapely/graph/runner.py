"""
Python-specific module: graph runner
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
GraphRunner -- the compiled notebook's cells, re-run only where stale
===============================================================================
A graph runs only as its compiled code (KA10). The runner keeps a namespace
of its own, the graph's store, never a named context, and executes in it the
compiled cell of each node that is stale (`compile.node_source`), in the
wires' order: what an edit changes is re-run, the rest kept. So a run after
an edit is the compiled notebook's code, less the cells whose result it
already holds.

**Stale.** A node's fingerprint is a hash of its cell's text (its block,
literals, wires and id), the fingerprints of the nodes feeding it, and, for a
literal naming a file (a rayfile, a trace's folder), that file's size and
modification time. A node whose fingerprint is not the one it ran under is
stale, and so is everything downstream of it. A change in the library's own
code is not seen: `forget()` drops the store.

**Long nodes.** A block may have an estimate (`ESTIMATES`; today the trace:
its segment limit, ``max_rays``, at the measured rate, an upper bound). A
node estimated over ``inline_limit_s`` (a minute) is not run in the kernel:
it is sent to an executor (`flows.executors`) as a job, its inputs in their
JSON form, and its outputs come back in theirs, parsed by their types. With
no executor it is refused before anything runs, the estimate given, so the
caller decides (an executor, or fewer rays). A job's result must have a JSON
form: a trace needs its ``runs_dir``.

`run(doc)` runs to the end, waiting on a job by its executor's status.
`start(doc)` and `advance()` run as far as they can without waiting, for a
view that polls.
===============================================================================
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..blocks import call_block, get_block, run_block
from ..blocks.types import ListOf, Optional_
from .compile import node_source
from .document import _reads_files, check_graph, is_wire, wire_source, wires_of

#: Seconds a node may be expected to take and still run in the kernel (`flows.budgets.ASK_OVER_S`).
INLINE_LIMIT_S = 60.0
#: The job procedure that runs one node in an executor.
NODE_PROCEDURE = "ray_tracing_shapely.graph.runner:run_node_job"


def _trace_estimate(inputs: Dict[str, Any]) -> float:
    from ..flows.budgets import estimate_s  # noqa: PLC0415
    max_rays = inputs.get("max_rays")
    if max_rays is None:
        max_rays = get_block("trace").inputs[1].default
    return estimate_s("simulate_2d_segment", float(max_rays))


#: A block's time estimate from its literal inputs, in seconds: an upper bound.
ESTIMATES: Dict[str, Callable[[Dict[str, Any]], float]] = {"trace": _trace_estimate}


class RunnerError(RuntimeError):
    """A graph the runner cannot run, or a node that failed, with the node and the reason."""


def run_node_job(inputs: Dict[str, Any], ctx: Any = None) -> Dict[str, Any]:
    """An executor's procedure: one block from its inputs' JSON, in the kernel's folder; its outputs' JSON."""
    import os  # noqa: PLC0415
    if inputs.get("cwd"):
        os.chdir(inputs["cwd"])           # a relative path in a literal means what it meant in the kernel
    return run_block(inputs["block"], inputs["inputs"])


@dataclass
class NodeRun:
    """What happened to one node in a run."""

    node: str
    state: str                       # "kept" | "ran" | "submitted" | "waiting" | "failed" | "skipped"
    seconds: Optional[float] = None
    estimate_s: Optional[float] = None
    where: str = "kernel"            # "kernel", the executor's kind, or "" when kept
    error: Optional[str] = None


@dataclass
class RunReport:
    """A run: each node in the order it runs, what happened to it, and whether the run is over."""

    order: List[str]
    nodes: Dict[str, NodeRun] = field(default_factory=dict)
    done: bool = False

    def ran(self) -> List[str]:
        return [n for n in self.order if self.nodes.get(n) and self.nodes[n].state == "ran"]

    def kept(self) -> List[str]:
        return [n for n in self.order if self.nodes.get(n) and self.nodes[n].state == "kept"]

    def failed(self) -> Optional[NodeRun]:
        return next((r for r in self.nodes.values() if r.state == "failed"), None)

    def to_dict(self) -> Dict[str, Any]:
        return {"order": self.order, "done": self.done,
                "nodes": {k: vars(v) for k, v in self.nodes.items()}}


def _stamp(value: Any) -> Any:
    """A file's size and modification time, so an edited rayfile makes its node stale."""
    if not isinstance(value, str):
        return None
    path = Path(value).expanduser()
    target = path / "readings.json" if path.is_dir() else path
    try:
        st = target.stat()
    except OSError:
        return "missing"
    return [st.st_size, st.st_mtime_ns]


class GraphRunner:
    """Runs a graph's compiled cells, only the stale ones, keeping each node's result.

    Args:
        executor: Where a long node goes (`flows.executors`); None: a long node is refused.
        inline_limit_s: A node estimated over this many seconds goes to the executor;
            None runs every node in the kernel.
        poll_s: How often `run` asks a job's status while it waits.
    """

    def __init__(self, executor: Any = None, inline_limit_s: Optional[float] = INLINE_LIMIT_S,
                 poll_s: float = 0.5) -> None:
        self.executor = executor
        self.inline_limit_s = inline_limit_s
        self.poll_s = poll_s
        self.namespace: Dict[str, Any] = {"call_block": call_block}
        self.fingerprints: Dict[str, str] = {}
        self._doc: Optional[Dict[str, Any]] = None
        self._report: Optional[RunReport] = None
        self._pending: Dict[str, Any] = {}        # node -> (handle, fingerprint, started)

    # --- what is stale -------------------------------------------------------------

    def _fingerprints(self, doc: Dict[str, Any], order: List[str]) -> Dict[str, str]:
        nodes = {n["id"]: n for n in doc["nodes"]}
        out: Dict[str, str] = {}
        for nid in order:
            node = nodes[nid]
            block = get_block(node["block"])
            types = {p.name: p.type for p in block.inputs}
            inputs = node.get("inputs") or {}
            upstream = sorted({wire_source(w)[0] for v in inputs.values() for w in wires_of(v)})
            files = {k: _stamp(v) for k, v in sorted(inputs.items())
                     if k in types and _reads_files(types[k]) and not any(True for _ in wires_of(v))}
            text = json.dumps([node_source(node), [out[u] for u in upstream], files], sort_keys=True)
            out[nid] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return out

    def stale(self, doc: Dict[str, Any]) -> List[str]:
        """The nodes a run of ``doc`` would run, in order; the graph must be finished."""
        order = check_graph(doc)
        prints = self._fingerprints(doc, order)
        nodes = {n["id"]: n for n in doc["nodes"]}
        stale: List[str] = []
        for nid in order:
            ups = {wire_source(w)[0] for v in (nodes[nid].get("inputs") or {}).values() for w in wires_of(v)}
            if self.fingerprints.get(nid) != prints[nid] or nid not in self.namespace or ups & set(stale):
                stale.append(nid)
        return stale

    def estimate_s(self, node: Dict[str, Any]) -> Optional[float]:
        """A node's time estimate, from its literal inputs, or None when its block has none."""
        estimate = ESTIMATES.get(node["block"])
        if estimate is None:
            return None
        inputs = node.get("inputs") or {}
        literal = {k: v for k, v in inputs.items() if not any(True for _ in wires_of(v))}
        return estimate(literal)

    def _long(self, node: Dict[str, Any]) -> Optional[float]:
        est = self.estimate_s(node)
        if est is None or self.inline_limit_s is None or est <= self.inline_limit_s:
            return None
        return est

    # --- running -------------------------------------------------------------------

    def forget(self) -> None:
        """Drop every kept result, so the next run runs every node."""
        self.namespace = {"call_block": call_block}
        self.fingerprints.clear()

    def start(self, doc: Dict[str, Any]) -> RunReport:
        """Begin a run of ``doc``: refuse a long node with no executor, drop what the graph no longer
        has, then run as far as possible without waiting (`advance`)."""
        if self._pending:
            raise RunnerError(f"a run is waiting on {', '.join(self._pending)}; advance() or wait for it")
        order = check_graph(doc)
        nodes = {n["id"]: n for n in doc["nodes"]}
        stale = self.stale(doc)
        if self.executor is None:
            for nid in stale:
                est = self._long(nodes[nid])
                if est is not None:
                    from ..flows.budgets import format_duration  # noqa: PLC0415
                    raise RunnerError(
                        f"{nid}: {nodes[nid]['block']} is estimated at {format_duration(est)} (an upper bound), "
                        f"over the {self.inline_limit_s:g} s a node may take in the kernel; give the runner an "
                        f"executor, or lower its work (a trace's max_rays)")
        for gone in [n for n in self.fingerprints if n not in nodes]:
            self.fingerprints.pop(gone)
            self.namespace.pop(gone, None)
        self._doc = doc
        self._report = RunReport(order=order)
        for nid in order:
            if nid not in stale:
                self._report.nodes[nid] = NodeRun(nid, "kept", where="")
        return self.advance()

    def _wired_live(self, node: Dict[str, Any]) -> Dict[str, Any]:
        out = {}
        for name, value in (node.get("inputs") or {}).items():
            if is_wire(value):
                src, port = wire_source(value)
                out[name] = self.namespace[src][port]
            elif isinstance(value, list) and any(is_wire(v) for v in value):
                out[name] = [self.namespace[wire_source(v)[0]][wire_source(v)[1]] for v in value]
        return out

    def _submit(self, node: Dict[str, Any], est: float) -> Any:
        """The node as a job: every input in its JSON form."""
        from ..flows.executors import Job  # noqa: PLC0415
        block = get_block(node["block"])
        types = {p.name: p.type for p in block.inputs}
        inputs = dict(node.get("inputs") or {})
        for name, live in self._wired_live(node).items():
            t = types[name]
            inputs[name] = [t.inner.format(v) for v in live] if isinstance(t, ListOf) else t.format(live)
        for p in block.outputs:
            if p.type.name == "trace" and not inputs.get("runs_dir"):
                raise RunnerError(f"{node['id']}: a trace run by an executor comes back as its run folder; "
                                  "give the node a runs_dir")
        return self.executor.submit(Job(NODE_PROCEDURE, {"block": block.name, "inputs": inputs, "cwd": str(Path.cwd())},
                                        budget_s=est, label=f"graph node {node['id']} ({block.name})"))

    def _collect(self, nid: str) -> bool:
        """Whether the node's job has ended; its outputs parsed into the store if it succeeded."""
        handle, print_, started = self._pending[nid]
        status = self.executor.status(handle)
        if not status.ended:
            return False
        del self._pending[nid]
        run = self._report.nodes[nid]
        run.seconds = time.time() - started
        if status.state != "done":
            run.state, run.error = "failed", f"{status.state}: {status.error or ''}".strip()
            self.fingerprints.pop(nid, None)
            self.namespace.pop(nid, None)
            return True
        node = next(n for n in self._doc["nodes"] if n["id"] == nid)
        result = self.executor.result(handle)
        outputs = {}
        for p in get_block(node["block"]).outputs:
            value = result.get(p.name)
            t = p.type.inner if isinstance(p.type, Optional_) and value is not None else p.type
            outputs[p.name] = None if value is None else t.parse(value, f"{nid}.{p.name}")
        self.namespace[nid] = outputs
        self.fingerprints[nid] = print_
        run.state = "ran"
        return True

    def advance(self) -> RunReport:
        """Run every stale node whose inputs are ready, sending long ones to the executor; the report.

        The run is ``done`` when every node is kept, ran, or one failed (what is downstream of it
        stays stale).
        """
        if self._report is None or self._doc is None:
            raise RunnerError("no run started; start(doc) first")
        report, nodes = self._report, {n["id"]: n for n in self._doc["nodes"]}
        for nid in list(self._pending):
            self._collect(nid)
        if report.failed() is None:
            prints = self._fingerprints(self._doc, report.order)
            for nid in report.order:
                if nid in report.nodes and report.nodes[nid].state in ("kept", "ran", "submitted"):
                    continue
                node = nodes[nid]
                ups = {wire_source(w)[0] for v in (node.get("inputs") or {}).values() for w in wires_of(v)}
                if any(report.nodes.get(u) is None or report.nodes[u].state not in ("kept", "ran") for u in ups):
                    report.nodes[nid] = NodeRun(nid, "waiting")
                    continue
                est = self._long(node)
                if est is not None:
                    try:
                        handle = self._submit(node, est)
                    except RunnerError as e:
                        report.nodes[nid] = NodeRun(nid, "failed", estimate_s=est, error=str(e))
                        break
                    self._pending[nid] = (handle, prints[nid], time.time())
                    report.nodes[nid] = NodeRun(nid, "submitted", estimate_s=est, where=handle.executor)
                    continue
                started = time.time()
                try:
                    exec(node_source(node), self.namespace)  # noqa: S102 -- the compiled notebook's own cell
                except Exception as e:  # noqa: BLE001 -- any failure of a block is the node's, reported
                    self.namespace.pop(nid, None)
                    self.fingerprints.pop(nid, None)
                    report.nodes[nid] = NodeRun(nid, "failed", time.time() - started, error=f"{type(e).__name__}: {e}")
                    break
                self.fingerprints[nid] = prints[nid]
                report.nodes[nid] = NodeRun(nid, "ran", time.time() - started)
        failed = report.failed()
        if failed is not None:                    # what was not reached is not run, and says why
            for nid in report.order:
                if report.nodes.get(nid) is None or report.nodes[nid].state == "waiting":
                    report.nodes[nid] = NodeRun(nid, "skipped", error=f"not run: {failed.node} failed")
        settled = all(report.nodes.get(n) and report.nodes[n].state in ("kept", "ran") for n in report.order)
        report.done = not self._pending and (settled or report.failed() is not None)
        return report

    def run(self, doc: Dict[str, Any], timeout_s: Optional[float] = None) -> RunReport:
        """Run ``doc``'s stale nodes to the end, waiting on any job by its executor's status.

        Raises:
            RunnerError: If a node fails (the report is ``self.report``), or the wait times out.
        """
        report = self.start(doc)
        deadline = None if timeout_s is None else time.time() + timeout_s
        while not report.done:
            if deadline is not None and time.time() > deadline:
                raise RunnerError(f"still waiting on {', '.join(self._pending)} after {timeout_s} s")
            time.sleep(self.poll_s)
            report = self.advance()
        failed = report.failed()
        if failed is not None:
            raise RunnerError(f"{failed.node}: {failed.error}")
        return report

    @property
    def report(self) -> Optional[RunReport]:
        """The last run's report."""
        return self._report

    @property
    def waiting(self) -> List[str]:
        """The nodes whose jobs a run is waiting on."""
        return list(self._pending)

    # --- what was computed ---------------------------------------------------------

    def outputs(self, node: str) -> Dict[str, Any]:
        """A node's outputs, live, as the compiled notebook names them (``node["output"]``)."""
        if node not in self.namespace or node == "call_block":
            raise RunnerError(f"no result for {node!r}; run the graph first")
        return self.namespace[node]

    def values(self, doc: Dict[str, Any], node: str) -> Dict[str, Any]:
        """A node's outputs in their JSON form (a trace as its folder, or None when not saved)."""
        found = next((n for n in doc["nodes"] if n["id"] == node), None)
        if found is None:
            raise RunnerError(f"no node {node!r}")
        live = self.outputs(node)
        out = {}
        for p in get_block(found["block"]).outputs:
            value = live.get(p.name)
            if value is None or (p.type.name == "trace" and getattr(value, "folder", None) is None):
                out[p.name] = None
            else:
                out[p.name] = p.type.format(value)
        return out


__all__ = ["ESTIMATES", "GraphRunner", "INLINE_LIMIT_S", "NODE_PROCEDURE", "NodeRun", "RunReport", "RunnerError",
           "run_node_job"]
