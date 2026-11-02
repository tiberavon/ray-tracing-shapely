---
id: C-AGENT-02
title: A tool is reachable only if registered in all three of agentic_tools, tool_registry._REGISTRY, and mcp_server._EXPOSED_TOOLS
parties:
  provides: agentic_layer
  relies:   MCP clients / LLM agents
port: P-AGENTIC-ENVELOPE
viewpoint: agentic
status: documented
failure_mode: silent
checked_by: null
witness: null
tracked_by: null
conflicts_with: null
refines: null
rationale: KA7
since: 0.1
---

# C-AGENT-02 — A tool has to be registered in three places, or the assistant cannot see it

**Assumptions.** Whoever adds a tool adds it to all three: the file that
defines it (`agentic_tools`), the list that describes it
(`tool_registry._REGISTRY` and `get_agentic_tools()`), and the list the
server publishes (`mcp_server._EXPOSED_TOOLS`).

**Guarantees.** A tool in all three is callable by an AI assistant, appears
in the tool list an assistant is shown, and has a description and a
parameter list that the assistant can read.

**Invariants.** The three lists agree. The number of registered tools is a
known number, and it changes only when a tool is deliberately added or
retired.

**Units and frames.** Not applicable.

**If the assumption is violated.** Silent, and specifically confusing. A
tool in two of the three places exists, has a real name, and may even be
named in the instructions the assistant was given — and every call to it
fails as though it had never been written. This has happened: four tools
were listed in the paragraph a person pastes into the assistant's chat,
and none of them was in the server's list.

**Checked by.** Not yet. The natural check is a test that reads all three
lists and asserts they hold the same names. A test that asserts the
*count* exists, which catches an addition to one list but not a swap.
