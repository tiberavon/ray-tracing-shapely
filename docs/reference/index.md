# Reference

What is true now. Two sub-sections, deliberately separate:

- The **API reference** is generated from the code's docstrings, one page
  per module. Where a docstring cites a concept — `[KA9: …]` — the citation
  is a link.
- The **architecture** is the hand-written map: the components, the ports
  between them, what each port is made of, and the contracts that state
  what must hold at each boundary. It is the same tree that lives at
  `dev_doc/architecture/` in the repository, included here at build.

Neither explains *why*. That is the [Explanation](../explanation/index) section.

```{toctree}
:maxdepth: 1

api/index
architecture/00_component_map
architecture/01_ports
architecture/03_alphabet
architecture/02_conventions
```

```{toctree}
:hidden:
:glob:

architecture/components/*
architecture/contracts/*
```
