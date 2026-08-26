"""
Python translation Copyright 2026 ray-tracing-shapely authors and contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

===============================================================================
ROLE VOCABULARY
===============================================================================
Shared, small, extensible vocabulary for tagging what a scene object (or one
of a BasePrism subclass's edges) does in a device, independent of its literal
name. This is the coarse layer structural path auditing needs to compare two
independently-built designs -- see
dev_doc/roadmap/done/15_p2_bidirectional_ray_tracing_rational.md §8-§9.

Two separate axes, kept separate rather than folded into one flat string:
- Role: *where* a surface sits in a device (entrance, wall, absorber, ...).
  Invariant across which mechanism a given design family uses there.
- Mechanism: *what* physical interaction happens there. Values are a typed
  alias for Ray.interaction_type's literal strings ('refract', 'reflect',
  'tir') -- not a fresh vocabulary. If these two ever drift apart, every
  comparison between a declared mechanism and a traced ray's actual
  interaction_type silently stops matching, with nothing to catch it.
===============================================================================
"""

from __future__ import annotations

from enum import Enum


class Role(Enum):
    """Where a surface sits in a device, independent of design family."""
    ENTRANCE = 'entrance'
    WALL = 'wall'
    ABSORBER = 'absorber'
    EXIT = 'exit'
    BLOCKER = 'blocker'
    SOURCE = 'source'
    SAMPLE_MEDIUM = 'sample_medium'


class Mechanism(Enum):
    """
    What physical interaction happens at a surface.

    Values MUST equal Ray.interaction_type's literal strings exactly
    (core/ray.py: self.interaction_type in {'source', 'reflect', 'refract',
    'tir'}) -- this enum is a typed alias, not an independent vocabulary.
    """
    REFRACT = 'refract'
    REFLECT = 'reflect'
    TIR = 'tir'


__all__ = ['Role', 'Mechanism']
