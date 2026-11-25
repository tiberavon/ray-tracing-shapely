"""
Python-specific package: blocks
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
The typed construction surface: value types, and blocks that use them
===============================================================================
`types` is the vocabulary of what a wire carries: each type with its JSON form
and its live form. `registry` keeps the blocks: calls with typed inputs and
outputs, declared with `@block`, run from JSON with every input checked.
`library` makes every designed element and every primitive a block, whose
output is its scene entry. `chain` declares the example chain, a rayfile to a
risk group. A graph editor's palette and an agent's construction tools are
both read from `catalogue()`.

Needs the ``radiometry`` extra (pint) for quantities. The core never imports
this package.
===============================================================================
"""

from .registry import Block, Port, block, call_block, catalogue, get_block, list_blocks, run_block, wire_accepts
from .types import BlockTypeError, ValueType, from_description, vocabulary

__all__ = ["Block", "BlockTypeError", "Port", "ValueType", "block", "call_block", "catalogue",
           "from_description", "get_block", "list_blocks", "run_block", "vocabulary", "wire_accepts"]
