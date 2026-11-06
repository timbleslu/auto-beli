# Test evidence — checkpoint, November 5, 2026 (America/New_York)

This is an implementation checkpoint. The requested end-to-end Beli experience is unfinished.
Baseline fork HEAD: `3cccf6a924fe34e3d7ca97489cc0f8907713ec23`.
Branch: `codex/secure-photos-assistant`, repository `timbleslu/auto-beli`.
Connected GitHub identity/owner `timbleslu` and admin/push permission were verified.
The shell's current GitHub identity is `timstalily`; recheck/switch to timbleslu before pushing.
Only origin exists, and both its URLs point to timbleslu/auto-beli.

## Environment actually observed

- macOS 27.0.1, build 26A434, Apple silicon.
- Python 3.13.15, Node 26.7.0, uv 0.12.5, Git 2.55.0.
- Xcode 27.2, build 27B52. System selection is still CommandLineTools; use
  DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer for this project.
- Physical USB iPhone 16 Pro detected after the user connected/unlocked/trusted it.
  iOS version, Beli version and WebDriverAgent signing have NOT been verified.
- Photos library path exists, but a direct header read returned macOS PermissionError.
  User enabled Full Disk Access and needs to restart Codex. Relevant image counts,
  geotags and iPhone availability remain UNVERIFIED.

## Checks completed

- Before changes: original 110 tests passed.
- Updated non-browser tests: 106 passed. Authentication, CSRF, queue validation, atomic
  approval, manual status distinctions, partial-photo persistence, restart/pause/stop,
  explicit photo waiver, separate visits, exclusive process lock, legacy migration,
  private backups, metadata stripping and thumbnail rejection are covered.
- Real Chromium 156.0.8078.4 via Playwright 1.64.1: 7 tests passed. Includes isolated
  reproduction of the exact old entity-decoding XSS, followed by secure DOM rendering
  and batch/manual-flow tests with CSP ON and OFF, malicious strings, punctuation and Unicode.
- Real TLS test: 1 passed. A temporary private CA validates the server; an untrusted
  client rejects it. The encrypted endpoint rejects unauthenticated API access.
  This is loopback transport proof, not iPhone Safari/LAN proof.
- JavaScript syntax and launcher shell syntax checks passed.
- PyInstaller 6.22.3 produced an application bundle. Its ad-hoc signature is NOT Apple
  Developer ID signing or notarization. Packaged runtime/GUI usability are not verified.
- Locked Python dependency audit: no known vulnerabilities reported.
- Node audit: 18 moderate dependency entries, TWO root advisories, remain in bundled
  driver copies. Root glob/minimatch overrides applied; Appium --version succeeds.
  XCUITest 12.22.8 registers locally. No WebDriverAgent build or phone session ran.

One upstream FastAPI/Starlette test-client deprecation warning remains. It is not a
vulnerability finding. Reproducible source locking does not imply bit-identical .app
binaries across different SDKs or operating systems.

## Not tested or implemented

Actual Beli accessibility/navigation; physical rating pause/resume; positive ranking save
recognition; photo picker selection; transfer/import; saved-photo detection; automatic
multi-restaurant advancement; real upload failure/uncertainty/duplicate reconciliation;
real already-ranked handling; real branch selection; phone disconnect recovery;
iPhone certificate trust/LAN connectivity; signed/notarized distribution.
Only mock/manual worklist interruption and retry bookkeeping are tested.

No real-account write or photo upload occurred. No private photo/screenshot was used
in automated tests or uploaded for debugging. Review DEVICE-TRIAL.md before proceeding.
