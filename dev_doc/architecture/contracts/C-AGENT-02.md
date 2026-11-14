---
id: C-AGENT-02
title: The catalogue, the agentic list and the published list agree, the published list being derived as every agentic tool not withdrawn
parties:
  provides: agentic_layer (tool_registry, mcp_server)
  relies:   MCP clients / LLM agents; packages that add tools from outside the core
port: P-AGENTIC-ENVELOPE
viewpoint: agentic
status: enforced
failure_mode: silent
checked_by: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_tool_lists.py::test_the_three_lists_agree; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_tool_lists.py::test_exposed_is_agentic_minus_withdrawn_and_unchanged; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_tool_lists.py::test_the_mcp_server_publishes_exactly_the_exposed_tools; src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_tool_lists.py::test_the_paste_in_notes_announce_only_published_tools
witness: src-python/ray_tracing_shapely/ray_tracing_shapely/developer_tests/test_tool_lists.py::test_a_registered_tool_reaches_all_three
tracked_by: null
conflicts_with: null
refines: null
rationale: KA7
since: 0.1
---

# C-AGENT-02 — The assistant sees exactly the tools that are published, under one name each

**Assumptions.** A tool is defined (in `agentic_tools`, or in a package that
depends on the core) and catalogued in `tool_registry`. Core tools go in
`_REGISTRY` and `get_agentic_tools()`; a package outside the core calls
`register_tool`.

**Guarantees.**
- **Three lists, two kept by hand.**

  | List | What it holds |
  |---|---|
  | `_REGISTRY` | The catalogue of the Python API, agentic or not. |
  | `get_agentic_tools()` | The agent tools, each with a description and a JSON Schema. |
  | `get_exposed_tools()` | What the MCP server publishes. |

  The third is derived: every agentic tool, in order, except those in
  `withdrawn_tools()`, each withdrawal recorded with its reason. The server
  publishes that list and no other.
- **One name.** An agentic tool's name is its function's own `__name__`,
  the name MCP publishes, so an agent built from `get_agentic_tools()` and
  one connected over MCP call it by the same name.
- **The catalogue covers the agentic list.** Every agentic tool is in
  `_REGISTRY`.
- **Registration from outside.** `register_tool` writes a tool into all
  three at once, or not at all.
  - **Before the server starts:** a tool registered after the server module
    was imported is published at once.
  - **While it runs:** registration raises, since clients have read the list.
- **The announcement.** The paragraph generated for pasting into an
  assistant's chat names exactly the published tools.

**Invariants.** `check_tool_lists()` is empty. Withdrawn tools stay
callable from Python (`KD12`: deprecate rather than remove).

**Units and frames.** Not applicable.

**If the assumption is violated.** Silent, and specifically confusing.
- **A tool in two places of three** exists and has a real name, and may
  even be named in the instructions the assistant was given. Every call to
  it fails as though it had never been written.
- **This happened twice.**
  - The announcement named four tools the server did not publish, the
    withdrawn `find_rays_*_xml` tools, until it was generated from the
    published list.
  - Three tools were catalogued under their plain names
    (`path_surfaces`) and published under their function names
    (`path_surfaces_tool`).

  Both are now caught by the checks below.
- **A server that cannot start.** `mcp` 2.x renamed the server class, so
  the server cannot import under it. The `agentic` extra pins `mcp<2`, and
  where `mcp` is installed the server's own published list is compared
  with `get_exposed_tools()`. That is a failure, not an import skip.

**Checked by.**
- **No `mcp` needed:**
  - `check_tool_lists()` is empty;
  - the published list is the agentic list minus the four withdrawn tools,
    unchanged from the list kept by hand before;
  - both announcement generators name exactly the published tools;
  - a registered tool reaches all three lists;
  - registering while the server runs is refused, leaving nothing
    half-registered.
- **With `mcp` installed:** the running server publishes exactly
  `get_exposed_tools()`.
