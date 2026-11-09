# Develop and contribute

The plugin is developed at ZBT by Jonas Fortmann. Contributions should preserve
measurement semantics, document new mappings and include focused validation.
See [contact](../contact.md) for ownership and upstream attribution.

## Development environment

```bash
git clone https://github.com/jonasdfortmann/pynxtools-xrm.git
cd pynxtools-xrm
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,docs]'
pynx-xrm definitions --output "$PWD/run/xrm-definitions"
export NEXUS_DEF_PATH="$PWD/run/xrm-definitions"
pre-commit install
```

For NOMAD integration use the distribution's development environment and install
this checkout there; use its NOMAD version pin. The optional `nomad` extra is
available when NOMAD is not already supplied. Do not import the package before
setting the definitions path in the Python process under test.

## Source map

| File | Responsibility |
|---|---|
| `src/pynxtools_xrm/zeiss.py` | ZEISS headers, frame iterator, RCP matching |
| `src/pynxtools_xrm/tiff_stack.py` | Numbered stack discovery and iteration |
| `src/pynxtools_xrm/metadata.py`, `elabftw.py` | Resolution, precedence, ELN labels and provenance |
| `src/pynxtools_xrm/mapping.py`, `geometry.py` | NeXus fields and coordinate transforms |
| `src/pynxtools_xrm/streaming_writer.py` | Metadata Writer, pixel streaming, validation and atomic output |
| `src/pynxtools_xrm/definitions.py` | Explicit full definitions overlay |
| `src/pynxtools_xrm/nomad/jobs.py` | Upload-relative paths and sidecar associations |
| `src/pynxtools_xrm/nomad/parsers/parser.py` | Binary owner conversion and generated file registration |
| `src/pynxtools_xrm/nomad/schema_packages/schema.py` | YAML adapter and TIFF jobs |

## Validation

Run checks applicable to the changed code:

```bash
ruff check src tests
ruff format --check src tests
pytest tests
```

Some integration tests require NOMAD and suitable data. Review the test's setup
before interpreting an unavailable integration environment as a plugin failure.
Add tests for new decoded manufacturer fields, unit handling, ambiguous sidecars,
orientation and actual output datasets. Do not substitute guessed metadata for
missing experimental values. Keep one-image-at-a-time pixel memory behavior.

## Documentation

```bash
python -m pip install -e '.[docs]'
mkdocs build --strict
mkdocs serve
```

Edit Markdown under `docs/` and navigation in `mkdocs.yaml`. Separate tutorials,
task guides, explanations and reference, following the
[NOMAD documentation structure](https://docs.nomad-lab.eu/). Keep repository
metadata in `README.md`, `pyproject.toml`, `CITATION.cff` and `docs/contact.md`
consistent. Use ZBT/Jonas Fortmann authorship; retain genuine upstream copyright
notices in derived template code. Do not copy upstream funding or maintenance
claims into this project's citation metadata.

Every example must state its path base and distinguish synthetic values from
measurement data. Validate YAML/JSON and check examples against the current
schema and sidecar behavior. Update supported targets, output paths and failure
instructions together when implementation changes.

Submit a focused pull request to the project repository with the problem,
behavior change and validation. For a mapping extension, explain why the source
field represents that quantity, including units and format/version limitations.
Coordinate changes to upstream pynxtools or NOMAD with their own maintainers.
