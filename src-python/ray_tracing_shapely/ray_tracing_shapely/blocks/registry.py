"""
Python-specific module: block registry
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
Blocks: calls with typed inputs and outputs, declared, kept by name
===============================================================================
A block is one call into the library: its inputs and outputs are `Port`s,
each with a value type (`blocks.types`). Blocks are **declared**, not inferred
from annotations (an annotation says ``float`` where a wire needs a length in
millimetres, ``Point`` where it needs a position or a direction):

    @block(inputs={"slice": RAYFILE_SLICE, "power": Quantity("W")},
           outputs={"source": SCENE_ENTRY})
    def source_from_slice(slice, power): ...

The decorator registers the function and returns it unchanged: it stays an
ordinary function to call from a notebook. `run_block(name, inputs)` runs a
block from the JSON form of its inputs, parsed and checked at the boundary
(`KA9`), and gives the JSON form of its outputs; `call_block` does the same
with live values, for a kernel. `catalogue()` is every block, described as
JSON: what a graph editor's palette and an agent's tool list are made from.

The constructors (every designed element, every primitive) are blocks too,
generated from the recipe registry and the primitives' property schemas
(`blocks.library`) the first time the registry is read, so a satellite's
recipe registered later is a block as well.
===============================================================================
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union

from .types import BlockTypeError, ValueType, from_description

_MISSING = object()


@dataclass
class Port:
    """One input or output of a block."""

    name: str
    type: ValueType
    required: bool = True
    default: Any = None                     # the live default, when not required
    doc: str = ""

    def describe(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"name": self.name, "type": self.type.describe(), "required": self.required}
        if not self.required:
            out["default"] = None if self.default is None else self.type.format(self.default)
        if self.doc:
            out["doc"] = self.doc
        return out


@dataclass
class Block:
    """A call with typed inputs and outputs.

    ``call`` takes the live inputs by name and returns the live outputs by name.
    """

    name: str
    kind: str                               # "function", "recipe" or "primitive"
    inputs: List[Port]
    outputs: List[Port]
    call: Callable[[Dict[str, Any]], Dict[str, Any]]
    doc: str = ""
    origin: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def describe(self) -> Dict[str, Any]:
        return {"name": self.name, "kind": self.kind, "doc": self.doc, "origin": self.origin,
                "inputs": [p.describe() for p in self.inputs], "outputs": [p.describe() for p in self.outputs],
                **self.extra}

    def _inputs(self, given: Dict[str, Any],
                parse: Optional[Callable[[Port, Any, str], Any]] = None) -> Dict[str, Any]:
        """The live inputs: each given one parsed by its type (or by ``parse``), the rest defaulted."""
        if parse is None:
            def parse(port: Port, value: Any, where: str) -> Any:
                return port.type.parse(value, where)
        known = {p.name for p in self.inputs}
        unknown = sorted(set(given) - known)
        if unknown:
            raise BlockTypeError(f"{self.name}: no input {', '.join(map(repr, unknown))}; "
                                 f"inputs: {', '.join(p.name for p in self.inputs)}")
        live: Dict[str, Any] = {}
        from .types import Optional_  # noqa: PLC0415
        for port in self.inputs:
            if port.name in given and given[port.name] is not None:
                live[port.name] = parse(port, given[port.name], f"{self.name}.{port.name}")
            elif port.name in given and isinstance(port.type, Optional_):
                live[port.name] = None                # given, and null: what an optional allows
            elif port.required:
                raise BlockTypeError(f"{self.name}: input {port.name!r} ({port.type!r}) is required")
            else:
                live[port.name] = port.default
        return live

    def call_live(self, inputs: Dict[str, Any], wired: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Run with live (or JSON) inputs, each checked by its type; the live outputs.

        ``wired`` holds inputs that are another block's live outputs, taken as
        they are: a quantity's live form is a bare float, which its type would
        refuse as JSON. A graph checks each wire's type before it compiles
        (C-GRAPH-02); a call by hand is trusted.
        """
        wired = dict(wired or {})
        both = sorted(set(inputs) & set(wired))
        if both:
            raise BlockTypeError(f"{self.name}: {', '.join(map(repr, both))} given both as an input and wired")

        def parse(port: Port, value: Any, where: str) -> Any:
            return value if port.name in wired else port.type.parse(value, where)
        return self.call(self._inputs({**inputs, **wired}, parse))

    def run(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Run from the JSON form of the inputs; the JSON form of the outputs."""
        out = self.call_live(inputs)
        return {p.name: (None if out.get(p.name) is None else p.type.format(out[p.name])) for p in self.outputs}


_REGISTRY: Dict[str, Block] = {}
_GENERATED = False


def _ports(spec: Dict[str, Union[ValueType, Port, tuple]], signature: Optional[inspect.Signature] = None) -> List[Port]:
    ports = []
    for name, t in spec.items():
        if isinstance(t, Port):
            ports.append(t)
            continue
        doc = ""
        if isinstance(t, tuple):                      # (type, doc)
            t, doc = t
        param = signature.parameters.get(name) if signature else None
        has_default = param is not None and param.default is not inspect.Parameter.empty
        ports.append(Port(name, t, required=not has_default, default=param.default if has_default else None,
                          doc=doc))
    return ports


def block(name: Optional[str] = None, *, inputs: Dict[str, Union[ValueType, Port]],
          outputs: Dict[str, Union[ValueType, Port]], doc: Optional[str] = None) -> Callable:
    """Declare a function a block; it is returned unchanged.

    Args:
        name: The block's name (default: the function's).
        inputs: Its parameters' types, by name: every parameter a block passes,
            each a type, a ``(type, doc)`` pair, or a `Port`. A parameter with a
            default in the signature is optional.
        outputs: Its outputs' types. With one output the function returns the
            value; with several, a dict of them by name.
        doc: A one-line description (default: the docstring's first line).
    """
    def register(func: Callable) -> Callable:
        sig = inspect.signature(func)
        missing = [n for n in inputs if n not in sig.parameters]
        if missing:
            raise ValueError(f"{func.__name__}: no parameter {', '.join(missing)}")
        out_ports = _ports(outputs)
        single = out_ports[0].name if len(out_ports) == 1 else None

        def call(live: Dict[str, Any]) -> Dict[str, Any]:
            result = func(**live)
            return {single: result} if single else dict(result)

        add_block(Block(name or func.__name__, "function", _ports(inputs, sig), out_ports, call,
                        doc=doc or (inspect.getdoc(func) or "").split("\n")[0],
                        origin=f"{func.__module__}:{func.__qualname__}"))
        return func
    return register


def add_block(b: Block) -> Block:
    """Register a block (its name must be new)."""
    if b.name in _REGISTRY and _REGISTRY[b.name].origin != b.origin:
        raise ValueError(f"a block named {b.name!r} exists ({_REGISTRY[b.name].origin})")
    _REGISTRY[b.name] = b
    return b


def _ensure() -> None:
    global _GENERATED
    from . import chain, library  # noqa: F401, PLC0415 -- the declarations, and the constructors generated
    library.constructor_blocks(refresh=not _GENERATED)
    _GENERATED = True


def get_block(name: str) -> Block:
    """The block named `name`."""
    _ensure()
    if name not in _REGISTRY:
        raise BlockTypeError(f"no block {name!r}; blocks: {', '.join(sorted(_REGISTRY))}")
    return _REGISTRY[name]


def list_blocks(kind: Optional[str] = None) -> List[str]:
    """The blocks' names, sorted; of one kind (function, recipe, primitive) if given."""
    _ensure()
    return sorted(n for n, b in _REGISTRY.items() if kind is None or b.kind == kind)


def catalogue() -> List[Dict[str, Any]]:
    """Every block, described as JSON."""
    return [get_block(n).describe() for n in list_blocks()]


def run_block(name: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Run a block from its inputs' JSON form; its outputs' JSON form."""
    return get_block(name).run(inputs)


def call_block(name: str, inputs: Dict[str, Any], wired: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run a block with live (or JSON) inputs, and ``wired`` live outputs of other blocks; its live outputs."""
    return get_block(name).call_live(inputs, wired)


def wire_accepts(source: Dict[str, Any], target: Dict[str, Any]) -> bool:
    """Whether an output described as `source` may feed an input described as `target`."""
    return from_description(target).accepts(from_description(source))


__all__ = ["Block", "Port", "add_block", "block", "call_block", "catalogue", "get_block", "list_blocks",
           "run_block", "wire_accepts"]
