# Concepts

This tree answers one question: **why is the codebase shaped this way?**

It is the third of three. `dev_doc/architecture/` says what is true *now* —
components, ports, and checkable contracts. This tree says *why*, in a form
that does not depend on when the decision was made or who made it. Neither is
a history and neither is a tutorial.

A concept is cited, not summarised. An architecture page or a code docstring
that needs a piece of reasoning links to the file holding it.

## Keys

Every concept has a key: `K`, a group letter, a number — `KA1`, `KC4`. The
key is the first thing in the filename, so the directory lists in catalogue
order, and it is the search string for finding where a concept is relied on:

```bash
grep -rn 'KA9' src-python/          # every docstring citing this concept
grep -rln 'KC4' dev_doc/architecture/
```

Keys are permanent. A withdrawn concept keeps its key and its file; the key
is never reissued, because a citation to it may exist in code that has not
been touched since.

## How to read a concept file

A screen or two of prose. Front matter carries the `key`, a `one_line`
summary, a `status` (`active` or `withdrawn`), and `informs:` — the component
pages, ports and contracts that rely on the reasoning. A **Read also**
section at the end lists close siblings, since the concepts are not
independent of each other.

Concept files carry no milestone references, no dates, and no development
narrative. Where a concept has a testable half, that half is a contract in
`dev_doc/architecture/contracts/`, and the concept links to it rather than
repeating the rule.

## Not here yet

A concept states reasoning. A reader who wants to *see* it run has nowhere
to go from the file. Linking each concept to an executed worked-example
notebook — and later to a published field note — is a planned addition, not
an oversight.

## The catalogue


### Working with an agent

| Key | Concept | In one line |
|---|---|---|
| **KA1** | [edges_carry_a_functional_and_a_cardinal_label](KA1_edges_carry_a_functional_and_a_cardinal_label.md) | Functional label (what it does optically) and cardinal label (where it points). |
| **KA2** | [every_query_tool_ships_a_list_or_describe_counterpart](KA2_every_query_tool_ships_a_list_or_describe_counterpart.md) | A tool taking a glass name is paired with one that lists the glass names. |
| **KA3** | [agent_tools_exchange_plain_dicts_and_strings](KA3_agent_tools_exchange_plain_dicts_and_strings.md) | The lowest common denominator is the only portable wire format across frameworks. |
| **KA4** | [agent_tools_return_errors_as_values_not_exceptions](KA4_agent_tools_return_errors_as_values_not_exceptions.md) | The boundary returns a structured result; the layer beneath it still raises. |
| **KA5** | [live_objects_reach_tools_through_an_explicit_registry](KA5_live_objects_reach_tools_through_an_explicit_registry.md) | A library module's `globals()` is not the caller's, so the context is passed, not found. |
| **KA6** | [agents_query_a_database_not_a_function_per_question](KA6_agents_query_a_database_not_a_function_per_question.md) | Composable queries over a described schema, rather than a wrapper per question. |
| **KA7** | [a_tool_is_registered_in_three_places_or_it_is_unreachable](KA7_a_tool_is_registered_in_three_places_or_it_is_unreachable.md) | `agentic_tools`, `tool_registry`, `mcp_server._EXPOSED_TOOLS` — two of three is unreachable. |
| **KA8** | [tool_output_is_budgeted_against_the_context_window](KA8_tool_output_is_budgeted_against_the_context_window.md) | Summarise and filter by construction; return a descriptor, not the payload. |
| **KA9** | [every_argument_is_parsed_and_checked_at_the_agent_boundary](KA9_every_argument_is_parsed_and_checked_at_the_agent_boundary.md) | Quantities parsed and dimension-checked, names resolved, SQL keyword-filtered. |

### Representing and analysing a simulation

| Key | Concept | In one line |
|---|---|---|
| **KB1** | [ray_lineage_is_a_graph_not_a_hand_rolled_tree](KB1_ray_lineage_is_a_graph_not_a_hand_rolled_tree.md) | Reachability, path enumeration and structural comparison as library calls. |
| **KB2** | [tracing_runs_forward_from_sources_and_backward_from_the_detector](KB2_tracing_runs_forward_from_sources_and_backward_from_the_detector.md) | For systems where only a tiny fraction of source rays ever arrive. |
| **KB3** | [runs_are_compared_by_ordered_interaction_lists](KB3_runs_are_compared_by_ordered_interaction_lists.md) | A path becomes a tuple of `(surface, edge, interaction)`; a run, a distribution over those. |
| **KB4** | [quantities_computed_while_tracing_are_recorded_not_discarded](KB4_quantities_computed_while_tracing_are_recorded_not_discarded.md) | With the identity of the path that produced them — opt-in where it costs. |
| **KB5** | [shapely_provides_the_2d_geometry_predicates](KB5_shapely_provides_the_2d_geometry_predicates.md) | Containment, intersection and interpolation come from a library. |
| **KB6** | [rendered_svg_elements_carry_their_simulation_identity](KB6_rendered_svg_elements_carry_their_simulation_identity.md) | One artefact serves an editor, a highlight query, and an agent's answer. |
| **KB7** | [optiland_verifies_2d_designs_in_3d_and_hands_them_back](KB7_optiland_verifies_2d_designs_in_3d_and_hands_them_back.md) | Three named reasons, and a bridge that runs both ways. |
| **KB8** | [a_run_bundle_records_its_schema_version_and_parameter_split](KB8_a_run_bundle_records_its_schema_version_and_parameter_split.md) | Schema version, physical/numerical parameter split, name-topology fingerprint. |

### Modelling, layering and units

| Key | Concept | In one line |
|---|---|---|
| **KC1** | [physics_and_rendering_are_layers_above_core_never_inside_it](KC1_physics_and_rendering_are_layers_above_core_never_inside_it.md) | The simulator stays a geometry hot loop; everything physical sits above. |
| **KC2** | [elements_are_built_from_optical_requirements_not_vertices](KC2_elements_are_built_from_optical_requirements_not_vertices.md) | Constructors take the requirement and compute the geometry. |
| **KC3** | [physical_and_numerical_parameters_are_stored_separately](KC3_physical_and_numerical_parameters_are_stored_separately.md) | Geometry and index in one section, ray density and mesh resolution in another. |
| **KC4** | [physical_quantities_are_unit_checked_not_docstring_documented](KC4_physical_quantities_are_unit_checked_not_docstring_documented.md) | Correctness that depends on a docstring being read is unchecked. |
| **KC5** | [every_exposure_limit_in_the_standard_is_implemented](KC5_every_exposure_limit_in_the_standard_is_implemented.md) | Every limit the standard defines, not the subset the examples exercise. |
| **KC6** | [when_two_standards_coexist_neither_gets_the_bare_name](KC6_when_two_standards_coexist_neither_gets_the_bare_name.md) | The easiest-to-type name silently privileges whichever holds it. |
| **KC7** | [headless_components_never_import_the_visualization_ones](KC7_headless_components_never_import_the_visualization_ones.md) | Batch assembly must stay usable without an interactive dependency. |

### How this project works on itself

| Key | Concept | In one line |
|---|---|---|
| **KD1** | [every_claim_is_marked_read_verified_or_unchecked](KD1_every_claim_is_marked_read_verified_or_unchecked.md) | A claim confirmed by running code is marked differently from one read. |
| **KD2** | [divergences_from_the_plan_are_written_down_with_their_reason](KD2_divergences_from_the_plan_are_written_down_with_their_reason.md) | What was scoped, what was built, and what was found in between. |
| **KD3** | [assertions_go_where_a_failure_would_be_silent](KD3_assertions_go_where_a_failure_would_be_silent.md) | Checks go where nothing would otherwise fire; unmapped cases raise. |
| **KD4** | [states_render_the_full_comparison_not_just_the_verdict](KD4_states_render_the_full_comparison_not_just_the_verdict.md) | Measured value, threshold, unit and citation — not just pass or fail. |
| **KD5** | [correctness_is_checked_against_an_external_number](KD5_correctness_is_checked_against_an_external_number.md) | A published table, or a recorded anomaly — never a case built to pass. |
| **KD6** | [three_doc_trees_current_state_reasoning_and_decisions](KD6_three_doc_trees_current_state_reasoning_and_decisions.md) | Current state, reasoning, decisions. Different staleness, different trees. |
| **KD7** | [human_agent_and_tools_share_one_live_kernel](KD7_human_agent_and_tools_share_one_live_kernel.md) | Which is why the tool host runs inside that process, not beside it. |
| **KD8** | [parameter_sweeps_run_as_disposable_headless_notebooks](KD8_parameter_sweeps_run_as_disposable_headless_notebooks.md) | The same notebook a human reads, run without one. |
| **KD9** | [transcribed_book_chapters_never_leave_the_private_repo](KD9_transcribed_book_chapters_never_leave_the_private_repo.md) | The reasoning derived from a source ships; the source text does not. |
| **KD10** | [classification_runs_as_a_state_machine_with_one_fixed_diagram](KD10_classification_runs_as_a_state_machine_with_one_fixed_diagram.md) | A diagram that varies with its input is a diagram nobody can check. |
| **KD11** | [component_boundaries_carry_assume_guarantee_contracts](KD11_component_boundaries_carry_assume_guarantee_contracts.md) | An obligation needs a named holder; a violation needs a named failure. |
| **KD12** | [the_tool_list_is_audited_before_it_is_extended](KD12_the_tool_list_is_audited_before_it_is_extended.md) | Inventory the surface before extending it; deprecate rather than remove. |

## Status

**All 36 written.** Every link resolves. Each file carries its key, a
`one_line`, an `informs:` list, and a `Read also` section pointing at close
siblings.
