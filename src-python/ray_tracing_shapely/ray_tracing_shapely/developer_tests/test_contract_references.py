"""
Python-specific module: test contract references
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
CONTRACT REFERENCES -- every test a contract cites exists
(dev_doc/architecture/02_conventions.md, the contract's front matter)
===============================================================================

A contract's `checked_by` says which test fails when the contract breaks, and
its `witness` which test shows it holding. Both are only worth something if the
test is there: a renamed or deleted test leaves a contract claiming a check
nobody runs. Each reference is a repository path, `path::test_name` or a whole
file's `path`, and several are separated by `; `. This test reads every
contract and checks that each file exists and defines each test named; and
that an `enforced` contract names a `checked_by`.

The contracts live beside the code in the repository, not in the installed
package: outside a checkout this test is skipped.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


def _repo_root() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        if (parent / "dev_doc" / "architecture" / "contracts").is_dir():
            return parent
    return None


ROOT = _repo_root()
pytestmark = pytest.mark.skipif(ROOT is None, reason="not in a repository checkout: no contracts to read")


def _front_matter(path: Path) -> dict[str, str]:
    """The front matter's top-level `key: value` lines (the fields read here are single-line)."""
    text = path.read_text(encoding="utf-8")
    block = text.split("---", 2)[1]
    return {m.group(1): m.group(2).strip() for m in re.finditer(r"^(\w+):[ \t]*(.*)$", block, flags=re.M)}


def _contracts() -> list[Path]:
    return sorted((ROOT / "dev_doc" / "architecture" / "contracts").glob("C-*.md")) if ROOT else []


def _references(value: str) -> list[str]:
    if value in ("", "null", "~"):
        return []
    return [r.strip() for r in value.split(";") if r.strip()]


def _distribution_absent(path: str) -> bool:
    """Whether ``path`` lies in a distribution this checkout does not hold.

    The contracts cover all three distributions, and cite each one's tests by
    repository path (``src-python/<distribution>/...``). The development
    repository holds all three; a distribution's own repository holds only its
    own. A test in a distribution that is not here cannot be checked here, so
    it is not counted missing: it is checked where that distribution is.
    """
    parts = Path(path).parts
    return len(parts) > 2 and parts[0] == "src-python" and not (ROOT / parts[0] / parts[1]).is_dir()


@pytest.mark.parametrize("contract", _contracts(), ids=lambda p: p.stem)
def test_every_cited_test_exists(contract: Path):
    fm = _front_matter(contract)
    missing = []
    for key in ("checked_by", "witness"):
        for ref in _references(fm.get(key, "null")):
            path, _, name = ref.partition("::")
            if _distribution_absent(path):
                continue
            file = ROOT / path
            if not path.endswith(".py") or not file.is_file():
                missing.append(f"{key}: {ref!r} is not a repository path to a test file (path::test_name)")
                continue
            if name and not re.search(rf"^\s*def {re.escape(name)}\(", file.read_text(encoding="utf-8"), flags=re.M):
                missing.append(f"{key}: {path} defines no {name}")
    assert not missing, "\n".join(missing)


@pytest.mark.parametrize("contract", _contracts(), ids=lambda p: p.stem)
def test_an_enforced_contract_names_its_check(contract: Path):
    fm = _front_matter(contract)
    if fm.get("status") == "enforced":
        assert _references(fm.get("checked_by", "null")), "status enforced, but checked_by is null"


def test_the_contracts_are_found():
    assert len(_contracts()) > 0
