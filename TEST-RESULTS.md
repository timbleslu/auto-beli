# Test evidence — checkpoint, November 6, 2026 (America/New_York)

This is an implementation checkpoint. The requested end-to-end Beli experience is unfinished.
Baseline fork HEAD: `3cccf6a924fe34e3d7ca97489cc0f8907713ec23`.
Branch: `codex/secure-photos-assistant`, repository `timbleslu/auto-beli`.
Connected GitHub identity/owner `timbleslu` and admin/push permission were verified.
The shell’s active identity is `timstalily` (no fork write permission). The existing timbleslu
credential was privately verified with push permission and can be used per-command without changing
the active account. Recheck remotes and identity before every push.
Only origin exists, and both its URLs point to timbleslu/auto-beli.

## Environment actually observed

- macOS 27.0.1, build 26A434, Apple silicon.
- Python 3.13.15, Node 26.7.0, uv 0.12.5, Git 2.55.0.
- Xcode 27.2, build 27B52. System selection is still CommandLineTools; use
  DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer for this project.
- Physical USB iPhone 16 Pro, iOS 27.0.1, Developer Mode enabled. Installed Beli 10.7.0
  was identified read-only from the device (bundle identity is kept separate from OSM IDs).
- WebDriverAgent 16.17.7 built successfully with the user-selected Apple development team.
  First startup timed out; the diagnostic retry identified an untrusted Developer App certificate
  on the iPhone. After the user trusted it, an inspection session succeeded. Beli was activated
  and its uniquely observed Search button opened; the search screen exposed two input controls.
  No restaurant query, rating, comparison or upload was performed. That session was explicitly
  disconnected at the user's pause request; it remains disconnected during the discovery repairs.
- Full Disk Access works after the Codex restart. Dated/GPS metadata, existing local food
  labels and local preview availability were checked read-only. Library-specific counts,
  identifiers and coordinates stay in ignored private runtime state. Availability of the
  particular image chosen for the iPhone trial still requires verification.

## Checks completed

- Before changes: original 110 tests passed.
- Updated non-browser tests: 131 passed. Authentication, CSRF, queue validation, atomic
  approval, manual status distinctions, partial-photo persistence, restart/pause/stop,
  explicit photo waiver, separate visits, exclusive process lock, legacy migration,
  private backups, metadata stripping and thumbnail rejection are covered.
- Full current Python suite: **141 passed**, one upstream test-client deprecation warning.
- Real Chromium 156.0.8078.4 via Playwright 1.64.1: 9 tests passed. Includes isolated
  reproduction of the exact old entity-decoding XSS, followed by secure DOM rendering
  and batch/manual-flow tests with CSP ON and OFF, malicious strings, punctuation and Unicode.
- Real TLS test: 1 passed. A temporary private CA validates the server; an untrusted
  client rejects it. The encrypted endpoint rejects unauthenticated API access.
  This is loopback transport proof, not iPhone Safari/LAN proof.
- JavaScript syntax and launcher shell syntax checks passed.
- PyInstaller 6.22.3 produced an application bundle. Its ad-hoc signature is NOT Apple
  Developer ID signing or notarization. Packaged runtime/GUI usability are not verified.
- Locked Python dependency audit: no known vulnerabilities reported.
- Node audit: **zero known vulnerabilities** after removing dependency bundles from the
  checksum-verified upstream driver and applying glob/minimatch security overrides. Clean npm ci
  restored the dependency tree. See vendor provenance for the deterministic repackaging recipe.
- A further two-line driver patch binds the legacy USB forwarder to loopback, in source and compiled
  JavaScript. A real socket test passes (1 Node test); the RemoteXPC forwarder already defaults to
  loopback. Appium status was reached at 127.0.0.1:4723 and its actual binding verified.
- Overpass timed out/rejected public health queries. A bounded Nominatim search worked,
  with explicitly incomplete/review-only suggestions. The first GPS-cluster workflow was rejected
  by the user as poor: it mixed non-food pictures, omitted pictures, and suggested wrong restaurants.
- Photo-first discovery replaces automatic matching of the three latest location clusters.
  The new inventory includes the complete configured window of visible still images with existing local
  food-label hints. Discovery itself sends no coordinates. All images remain accessible through filters,
  including unlabelled/no-GPS pictures. Classification accuracy has NOT been measured against
  user ground truth; the labels are hints, not an assertion that all food was found.
- Tests prove no startup lookup, retention of no-GPS images, no six-photo truncation, explicit
  name corrections, persistence of unapproved groups, protection of approved groups, rejection
  of overlapping groups, and browser selection retention across filters/name corrections/reload.
- Missing-OSM-restaurant tests cover user-supplied names/addresses, a separate `user:`
  namespace, retained photo groups, CSRF protection, no automatic approval/provider call,
  unverified Beli state, injected text safety, and lookup/removal concurrency.
- Broader lookup investigation found that a user-confirmed restaurant was present in OSM:
  its full Unicode name plus city returned the correct branch, while the earlier bare-name
  search had missed it. The selected photo also contained a matching cached venue hint which
  the initial implementation ignored. A revised automatic lookup using Photos' venue/city
  hints returned the confirmed branch among two candidates. This is ONE real provider case,
  not a measured accuracy claim and not verification of the Beli entry.
- Synthetic regressions cover cached venue hints, city/location-biased name queries, canonical
  Unicode equivalents, missing-GPS name lookup, non-execution of venue text, suppression of
  cached home venue names, and rejection of stale/disconnected/wrong USB device state.
- The refreshed local review uses a native pairing dialog. Real previews are shown only to the
  user in their local browser; no private screenshot or photo was uploaded to AI debugging.

One upstream FastAPI/Starlette test-client deprecation warning remains. It is not a
vulnerability finding. Reproducible source locking does not imply bit-identical .app
binaries across different SDKs or operating systems.

## Not tested or implemented

Beli restaurant-specific navigation (beyond the observed Search button); physical rating pause/resume; positive ranking save
recognition; photo picker selection; transfer/import; saved-photo detection; automatic
multi-restaurant advancement; real upload failure/uncertainty/duplicate reconciliation;
real already-ranked handling; real branch selection; phone disconnect recovery;
iPhone certificate trust/LAN connectivity; signed/notarized distribution.
Only mock/manual worklist interruption and retry bookkeeping are tested.

No real-account write or photo upload occurred. No private photo/screenshot was used
in automated tests or uploaded for debugging. Review DEVICE-TRIAL.md before proceeding.
