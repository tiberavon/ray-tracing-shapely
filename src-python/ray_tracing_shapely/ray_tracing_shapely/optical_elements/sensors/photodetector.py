"""
Python-specific module: Photodetector -- a detector that reads the power it absorbs
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
PYTHON-SPECIFIC MODULE: Photodetector
===============================================================================
`Detector` is a flux probe: a line anywhere in a design whose `power` is the
light crossing it with the crossing's sign, so it tells how much light goes
one way and how much the other (C-DET-01). A sensor reads something else: the
light it absorbs on its front face, which is never negative, whichever way the
line is drawn.

`Photodetector` is that sensor, built on `Detector`. It is always one-sided:
`absorbingSide` says which face is its front (+1, the default, or -1) and
`twoSided` is false by default and refused if true. Every counted crossing adds its brightness to `power`
and to the bins with a plus sign. The hit records, the normal and shear forces
and the ray's passage are `Detector`'s: the ray goes on (C-CORE-02); a sensor
that also stops the light has a `Blocker` behind it.
===============================================================================
"""

from typing import Any, Dict, Optional

from ...core.scene_objs.other.detector import Detector


class Photodetector(Detector):
    """A one-sided detector whose `power` is the light absorbed on its front face.

    Args:
        scene: The scene it belongs to.
        json_obj: Its `serialize()` dict, as `Detector`'s; ``twoSided`` must be false.

    Raises:
        ValueError: ``twoSided`` is true, or ``absorbingSide`` is not +1 or -1.
    """

    type = 'Photodetector'
    serializable_defaults = {**Detector.serializable_defaults, 'twoSided': False}

    @classmethod
    def property_schema(cls, obj_data=None, scene=None):
        """Detector's, without two-sided: a Photodetector is one-sided always."""
        return [x for x in super().property_schema(obj_data, scene) if x['key'] != 'twoSided']

    def __init__(self, scene: Any, json_obj: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(scene, json_obj)
        if self.twoSided:
            raise ValueError("a Photodetector absorbs on one face: twoSided is not allowed (use Detector "
                             "for signed net flux)")
        if self.absorbingSide not in (1, -1):
            raise ValueError(f"absorbingSide is +1 or -1, got {self.absorbingSide!r}")

    def _counted(self, sign: int) -> int:
        """Every absorbed crossing counts as absorbed power, whichever way the line is drawn."""
        return 1
