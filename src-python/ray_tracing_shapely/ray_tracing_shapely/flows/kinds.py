"""
Python-specific module: kinds -- the flows that can be started by name

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
PYTHON-SPECIFIC MODULE: kinds
===============================================================================
A **kind** is a flow class that can be started by name, with nothing but a
folder to write its runs in: so an agent can start one. Kinds are registered
as tools are, by import path, so this module imports none of the flows it
lists until one is started or described: `flows` stays below every package
whose flows it lists.

The core's kinds are registered here; another package registers its own
(`register_flow_kind`), as the satellite registers its tools.

A kind's runs go to `<root>/<kind>/`, and any other folder its constructor
needs to `<root>/<folder>/` (an intake's classification runs).
===============================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .executors import resolve_procedure


@dataclass(frozen=True)
class FlowKind:
    """A flow class that can be started by name.

    Args:
        name: The name agents start it by.
        target: The class, by import path (``"pkg.module:Class"``). Its
            constructor takes ``base_dir`` and ``render_svg``, and the folders
            in ``dirs``, and asks its first question once constructed.
        dirs: Other folders the constructor takes: ``{argument: folder under
            the root}``.
    """

    name: str
    target: str
    dirs: Dict[str, str] = field(default_factory=dict)

    def flow_class(self) -> Any:
        return resolve_procedure(self.target)

    def describe(self) -> Dict[str, Any]:
        """Its name, purpose and questions, in the order they are asked."""
        cls = self.flow_class()
        return {"kind": self.name, "purpose": getattr(cls, "PURPOSE", ""),
                "questions": [f.to_dict() for f in getattr(cls, "FIELDS", {}).values()]}

    def start(self, root: Path, *, render_svg: bool = False) -> Any:
        """A new run, its runs folder under ``root``; held alive for the tools."""
        from .runs import track
        root = Path(root)
        kwargs = {arg: root / folder for arg, folder in self.dirs.items()}
        flow = self.flow_class()(base_dir=root / self.name, render_svg=render_svg, **kwargs)
        return track(flow, keep=True)


_KINDS: Dict[str, FlowKind] = {}


def register_flow_kind(name: str, target: str, *, dirs: Optional[Dict[str, str]] = None) -> FlowKind:
    """Make a flow class startable by name. Registering a name again replaces it."""
    if ":" not in target:
        raise ValueError(f"target is 'package.module:Class', got {target!r}")
    kind = FlowKind(name, target, dict(dirs or {}))
    _KINDS[name] = kind
    return kind


def get_flow_kind(name: str) -> FlowKind:
    try:
        return _KINDS[name]
    except KeyError:
        raise KeyError(f"no flow kind {name!r}; known: {sorted(_KINDS)}") from None


def flow_kinds() -> List[FlowKind]:
    return [_KINDS[k] for k in sorted(_KINDS)]


# The core's own kinds. By import path: none is imported until it is used.
register_flow_kind("rayfile_slicing",
                   "ray_tracing_shapely.optical_elements.sources.rayfile_slicing_flow:RayfileSlicingFlow")
register_flow_kind("targeted_resimulation",
                   "ray_tracing_shapely.analysis.targeted_resimulation_flow:TargetedResimulationFlow")
register_flow_kind("iec62471_intake",
                   "ray_tracing_shapely.optical_elements.eye_safety_classification_flow:IEC62471IntakeFlow",
                   dirs={"classification_base_dir": "iec62471_classification"})
register_flow_kind("iec60825_1_intake",
                   "ray_tracing_shapely.optical_elements.eye_safety_classification_flow:IEC60825_1IntakeFlow",
                   dirs={"classification_base_dir": "iec60825_1_classification"})
