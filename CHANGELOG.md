# Changelog

All notable changes to `pota-mcp` are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- `--transport streamable-http` now says where it bound, and the help text says
  it too. It binds `127.0.0.1`, and FastMCP takes no host option, so it was
  never reachable from another machine or from outside a container — and nothing
  said so. The bind address is unchanged: loopback-only is deliberate for a
  server that holds credentials and has no authentication of its own.

## [0.4.2] — 2026-10-26

### Fixed

- `--version` and `--help` now print and exit. They were ignored, so the
  command started the MCP server on stdio and waited for JSON-RPC — leaving a
  FastMCP banner on screen and an apparently hung terminal. Seven servers in
  this fleet already behaved correctly; this brings the rest in line, and a
  test asserts it.

## [0.4.1] — 2026-10-26

- A release should appear on the Releases page
- Move every Node 20 action to its first Node 24 major
- The locked-dependency audit blocked every release
- Four upgrades arrived as 57 pull requests
- Nothing was auditing the lockfile
- Close every open security advisory in the lockfile
- A release is a workflow, not a merge
- Bump certifi from 2026.7.22 to 2026.10.19
- Make the publish gate's http:// check portable
- Assert that certifi is declared, not merely imported

## [0.4.0] — 2026-10-12

**Upgrading:** a tool that fails now returns `isError: true` instead of a successful result whose
payload contained an `error` key. Anything reading `result["error"]` should read the error flag.
No decision changed, and the three kinds of refusal are now distinguishable rather than identical:
a malformed park reference is refused before any request, a well-formed reference POTA holds no
park for is a failed lookup, and a filter matching nothing is still a successful answer with an
empty list.


- **`certifi` is carried, and the outbound call verifies against it** (#38, qso-graph-devel#73).
  The fetch used `urllib` with no context, so it trusted whichever root store the running Python
  was built against. On macOS that is `/etc/ssl/cert.pem`, a deliberately *reduced* OpenSSL file —
  128 roots against the system keychain's 158, and current rather than stale. A certificate
  chaining to one of the 30 it omits fails for Python while `curl` to the same URL succeeds, and
  the user is told only that the source could not be reached. That is what stopped `meteor-mcp`
  reaching NASA. **`api.pota.app` verifies fine against the reduced file today**, so this was
  latent rather than an outage: it would have surfaced the day a CA in the chain rotated.
- **Verification is never disabled.** `ssl.CERT_NONE` or `check_hostname = False` would also have
  made such a call "work", by accepting any certificate from anyone — a worse defect, and an
  invisible one. The fix is a complete root set, not a relaxed check. Three static checks hold it
  in `test_security.py` and two runtime ones in `test_tools.py`, split that way because the release
  gate runs the first file with the package **not installed**.
- **`tests/test_release_gate.py`** asserts that precondition rather than leaving it to be
  remembered: the gate suite may import nothing but the standard library and pytest. solar-mcp's
  0.3.0 publish failed on exactly that, from the same change.
- `ssl.SSLError` is handled alongside `URLError`, so a trust failure is a clean message rather than
  a traceback.

- **Tool execution errors are flagged `isError`** (#39). Every tool returned `{"error": "..."}` on
  failure, which reaches a client as a *successful* call whose payload happens to contain the word
  "error". The specification says why that matters: otherwise "the LLM would not be able to see that
  an error occurred and self-correct". They now raise `ToolError`, which `fastmcp` reports as
  `isError: true` with the message intact. **No decision changed — only how it is reported.** The
  three kinds of refusal are unchanged and now distinguishable: a malformed reference is refused
  before any request, a well-formed reference POTA holds no park for is a failed lookup, and a
  filter matching nothing is still a successful answer with an empty list.
- **Every tool declares all four annotation hints** (#39). Declaring nothing is not neutral: the
  defaults advertise a tool as `destructiveHint: true`, `openWorldHint: true` and not idempotent,
  and the specification tells clients to keep a human in the loop for operations like that — so a
  client was entitled to put a confirmation prompt in front of looking up a park. All eleven are
  read-only, non-destructive and idempotent; `openWorldHint` is read per tool, true for the ten
  that reach `api.pota.app` and false for `get_version_info`, which reports what the wheel carries.
  Annotations are a client's UX hint and never a security control; they replace no validation here.
- **A failed fetch now names what it could not reach.** Since the message is what a client now
  sees, `<urlopen error [Errno 61] Connection refused>` was not enough to tell a POTA outage from a
  defect here. It raises `POTA API request failed (<url>): <reason>`.
- **Reference validation moved above each tool's `try`.** It was raised inside it, where the
  generic handler would have re-wrapped it. The message would have survived — a `ToolError`'s `str`
  is its message, checked — but relying on that coincidence is worse than not nesting.
- **`tests/test_mcp_conformance.py`** asserts all of the above, so none of it can regress silently,
  following `adif-mcp`'s file of the same name.
- `urllib.error` is imported rather than relied on as a side effect of importing `urllib.request`.

## [0.3.0] — 2026-10-11

- **ruff and mypy run in CI** (qso-graph-devel#66), as a job the `ci-all-green` gate requires.
  Settings are copied from `adif-mcp`, the reference for every qso-graph Python repo, rather than
  invented here. They run once rather than per Python version: both read the source, and neither
  answer changes with the interpreter.
  - ruff found 24 things, all in this repo's own style — 19 lines over 95 characters, 4 unsorted
    import blocks, one unused import. Fixed rather than configured away.
  - mypy in strict mode found 12, and they were worth having. The mock constants were inferred as
    `dict[str, object]` from their literals, so every `.get()` on a mock was unusable; they are
    annotated as the JSON stand-ins they are. Eight returns handed back `Any` from the shared
    cache, so each cache read is now annotated with its own method's return type — stating, where
    it is known, what one dict holding every kind of answer gives back. And `mcp.run` was passed a
    `str` where fastmcp takes a literal; the literal is written out.
  - `uv.lock` changes here, unlike the other work in this release: ruff and mypy are new dev
    dependencies and CI installs with `--frozen`.

- **`pota_rare_parks_near`**, a new tool (#19): parks near a point, least activated first and
  nearest among equals, each flagged `never_activated`. Answers "which parks near me have never, or
  rarely, been activated?". POTA's `attempts` comes through untouched, because a park that has been
  tried and not finished is a different fact from one nobody has been to, and POTA carries both.
  - **It costs one request.** `/location/parks/{loc}` already returns each park's activations,
    attempts and qsos, so the per-park `/park/stats/{ref}` calls the issue planned for — and the
    candidate cap it wanted in order to respect POTA's servers — are not needed.
  - The candidate list is **not** capped by distance before being sorted by activations. A list cut
    to the twenty-five nearest cannot answer the question if the never-activated park is fortieth
    nearest. `nearby_parks` and this tool now share one uncapped candidate step and cap by
    different things.

- **`pota_park_activations`**, a new tool (#17): recent activations of a park, most recent first,
  with each activator's callsign, date, total QSOs and the CW, data and phone counts. Answers "when
  was this park last activated?" and "is it often on the air?". `count` is 1 to 50, default 10, and
  is part of the cache key so asking for more than was cached fetches rather than returning a
  shorter answer.
- **`pota_park_leaderboard`**, a new tool (#18): the three boards POTA publishes for a park — most
  activations, most QSOs as an activator, most QSOs as a hunter. Each row is a callsign and a count
  and nothing else, and the boards are named here rather than read off the response, so neither a
  field nor a board POTA adds later is passed on because nobody noticed. POTA's user endpoint
  already had to have `qth`, which can hold a street address, and `gravatar`, a hash of an email
  address, stripped out of it (#15). Rows per board are 1 to 25, default 10.
- **Park references are validated** before a request is made. A reference is an entity prefix, a
  hyphen and a number — loose about the prefix because POTA adds entities and a list of prefixes
  would reject a real park the day a new one appears, strict about the shape. Without it POTA
  answers 404 and the caller is told the park does not exist, which is a different fact from "that
  is not a reference".

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
- **`pota_spots` filtering by `location` now finds a park that spans regions** (#27). It compared
  POTA's whole `locationDesc` field for equality, so a park listed under more than one code never
  matched: on the live spot feed on 2026-10-10, five of 111 spots carried more than one code, the
  North Country Trail among them with eight states. Filtering by any of those eight missed it. The
  region test is now shared with `pota_scheduled` rather than written twice, which is how one tool
  came to be right and the other wrong. Both sides of the comparison are normalised too — only the
  filter was before, so a single-region park would also have failed to match had POTA returned the
  field in another case.
- **`pota_scheduled`'s `within_hours` filter could not read a single real activation.** It read
  `activityDate`, which POTA does not send, and required `startTime` to be four digits, which
  `14:00` is not. Against the live endpoint it kept **0 of 186** activations and reported all 186
  as having an unreadable start time. It now reads `startDate`/`startTime` as POTA sends them and
  keeps 8, 38 and 48 for windows of 6, 24 and 72 hours, with none unreadable.
- A POTA schedule entry is a **date range plus a daily UTC window**, not one date: the live feed
  carries entries running from February to October at the same `startTime` each day. "Starts within
  the next N hours" is now the next occurrence inside that range. A missing or backwards `endDate`
  is read as a single day, which is the narrower reading.
- **Every mock fixture is rebuilt from the live response, field for field** (#32). The schedule
  fixture had invented `scheduledActivationId`, `activityDate` and `comment`; the park list had
  `contacts` for `qsos`, `grid4`/`grid6` for one `grid`, a `parktypeDesc` this endpoint does not
  send, and nothing for `attempts`, `locationDesc`, `notes` or `website`. `attempts` is how
  `pota_rare_parks_near` tells a park nobody has finished from one nobody has tried, and
  `locationDesc` is what the region filter reads — both had to bring feeds of their own because
  the fixture could not stand in for the API.
- **A live check that makes the next drift a failure.** Run with `--live`, it compares each
  fixture's field set against the endpoint it stands in for, in both directions: a field POTA no
  longer sends, and a field POTA has added that no fixture carries. It is what found all of the
  above.
- The README lists all eleven tools (qso-graph-devel#69). `pota_park_activations`,
  `pota_park_leaderboard` and `pota_rare_parks_near` were shipped and undocumented, and
  `pota_scheduled`'s filters were not mentioned.
- **The published contact is `maintainers@qso-graph.io`** (qso-graph-devel#69). The `authors` field
  carried a personal address, and that field is what PyPI shows on the package page.
- **`fastmcp` is bounded: `>=4.0,<5`** (qso-graph-devel#60). It was `>=3.0` with no upper bound, and
  these servers are run with `uvx`, which resolves fresh — so a `fastmcp` 5.0 would have reached
  every user automatically, before anything here had been run against it. The floor rises to 4.0
  because that is what is actually tested: every lock in the fleet held a 4.x, and nothing in CI
  has ever exercised 3.x. Locked at 4.1.0, the current release.

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
