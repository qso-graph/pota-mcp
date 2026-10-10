# Changelog

All notable changes to `pota-mcp` are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

- **`pota_scheduled` takes optional filters** (#20): `location`, `reference`, `activator` and
  `within_hours`. They combine with AND, and an unfiltered call returns exactly what it always
  did — the same two keys, no extra ones. When a filter is given the result also reports what was
  asked for and how many activations were available before filtering, so an empty answer can be
  told apart from an empty schedule.
  - `location` matches a park that spans regions: `US-MD` finds one POTA lists as `US-VA,US-MD`,
    because `locationDesc` is comma-separated for a park on a border.
  - `within_hours` means the start time falls between now and then. An activation already under
    way is not included; `pota_spots` is what reports the air now.
  - An activation POTA gave no readable start date and time for is **counted and reported**, not
    dropped: missing from a filtered list, it would look like one that was never scheduled.
  - Filtering is applied to the cached feed, so one fetch serves every combination of filters.

## [0.2.6] — 2026-10-09

- `pota_user_stats` returns only callsign, name, activator, attempts, hunter, awards and endorsements. POTA's `qth` (which can hold an address) and `gravatar` (a hash of the user's email address) are no longer passed through (#15).
- Release gate: the #15 security test reads the source instead of importing the package, because the gate runs `test_security.py` without installing it. The 0.2.6 publish failed on this; nothing was published.

## [0.2.5] — 2026-10-07

- LICENSE: the full GPL-3.0 text. The file held only its opening and a link, so GitHub detected no licence.

## [0.2.4] — 2026-10-06

- PyPI: the Documentation link goes to this package's own page, https://qso-graph.io/servers/pota/ (qso-graph/.github#15).
- CI: the release flow (qso-graph/.github TEMPLATES.md). Work lands on `develop`; a release is a
  PR from `develop` into `main`, and merging it publishes to PyPI and the MCP Registry, verifies both
  and tags the release. CI runs on `develop` too, and PRs into `main` must come from `develop` or a
  `security/` branch.

## [0.2.3] — 2026-09-28

### Added (CI hygiene)

- **MCP Registry sync** — `publish.yml` publishes to the [Official MCP Registry](https://registry.modelcontextprotocol.io)
  after each PyPI publish, using GitHub OIDC for auth. Triggered on
  `v*` tag push; no manual steps. The Registry job waits until PyPI
  serves the version, and retries. Pattern documented in
  [qso-graph/.github/TEMPLATES.md](https://github.com/qso-graph/.github/blob/main/TEMPLATES.md).
- **Registry version badge** in README — PyPI and Registry versions
  are visible side-by-side so any drift between publishing surfaces
  is immediately apparent.
- **Release gates** — the tag must match `pyproject.toml`, and a
  `verify` job fails the release unless PyPI and the MCP Registry
  both serve the new version.

### Fixed

- The Official MCP Registry listed pota-mcp at 0.1.1. This release brings it current.

## [0.2.2] — 2026-05-15

### Added
- New tool `get_version_info` — returns `{service_name, service_version, spec_version}`
  for fleet identity attestation. Lets agents detect version drift across MCP
  deployments without going outside the protocol. Tracks
  [IONIS-AI/ionis-devel#49](https://github.com/IONIS-AI/ionis-devel/issues/49)
  (fleet rollout).
- `__spec_version__` constant in package `__init__.py`, pinned to `pota-api-v1`.
- L2 unit tests POTA-L2-046 through POTA-L2-050 covering the new tool.
- `.github/workflows/ci.yml` — PR-gating CI workflow (py3.10-3.13 matrix,
  unit + security tests, ci-all-green aggregator).

### Changed
- `__init__.py` modernized to mirror the `adif-mcp`/`solar-mcp` pattern
  (`Final` types, explicit `PackageNotFoundError` handling).

## [0.2.1] — Previous release
- See git history for changes prior to the changelog being introduced.
