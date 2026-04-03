# STIG Checker Directory & Structure Recommendations

This document reviews the current `stig_checker/` layout and proposes pragmatic improvements.

## Current State (Observed)

- App logic is concentrated in one file: `stig_checker/stig_check_flask.py`.
- Golden baseline artifacts are grouped under `stig_checker/golden/`.
- Front-end files are split into Flask-standard `templates/` and `static/` directories.

The current structure works for a small codebase, but it couples web routes, device I/O, parsing, and validation in a single module.

## Recommended Changes

## 1) Split the monolithic app file into modules

Create a package layout like:

```text
stig_checker/
  app/
    __init__.py
    routes.py
    services/
      device_client.py
      loader.py
      validators.py
      reporting.py
    models/
      findings.py
  templates/
  static/
  data/
    golden/
```

Why:
- Easier testing of validation logic without Flask context.
- Cleaner ownership boundaries (I/O vs business rules vs rendering).
- Lower risk when changing one subsystem.

## 2) Rename `golden/` to `data/golden/`

Keep baseline artifacts in a data-specific path (`data/golden/`) to clearly separate code and mutable policy content.

Why:
- Better for future versioning/promotion of baselines (e.g., `data/golden/v1`, `v2`).
- Clearer path semantics for new contributors.

## 3) Add a `tests/` tree that mirrors modules

Suggested test layout:

```text
tests/
  validators/
    test_validate_rtr.py
    test_validate_sw.py
    test_validate_acls.py
    test_validate_interfaces.py
  services/
    test_loader.py
```

Why:
- The validator functions are deterministic and ideal for fast unit tests.
- Reduces regressions when STIG templates evolve.

## 4) Separate configuration from code

Add an explicit config module (or environment variables) for:
- File system paths (golden files)
- Connection defaults/timeouts
- Flask debug mode

Why:
- Avoid hard-coded relative paths.
- Enables deployment in containerized or service contexts.

## 5) Move static third-party assets to package management over time

Currently Bootstrap assets are committed in `static/`. For long-term maintainability, consider:
- Pinning front-end dependencies via a package manager, or
- Keeping vendored assets but documenting version/update process.

Why:
- Security and maintainability (clear upgrade path).

## 6) Add docs directory for operator playbooks

Create:

```text
docs/
  operations.md
  adding_stig_rules.md
  troubleshooting.md
```

Why:
- Captures onboarding and operational knowledge outside README.

## Priority Order

1. **High impact, low risk:** Add tests and split validators into a standalone module.
2. **High impact, medium risk:** Modularize Flask routes and device client code.
3. **Medium impact:** Move `golden/` to `data/golden/` with centralized path config.
4. **Nice-to-have:** Broader docs and static asset process.

## Minimal First Refactor Plan

- Phase 1:
  - Introduce `app/services/validators.py` and move validation functions there.
  - Add unit tests for validators.
- Phase 2:
  - Introduce `app/services/device_client.py` and `loader.py`.
  - Keep route handlers thin in `routes.py`.
- Phase 3:
  - Relocate golden files and add config-backed paths.

This phased approach keeps behavior stable while improving maintainability.
