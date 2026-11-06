# Security status and boundaries

Baseline reviewed again: `3cccf6a924fe34e3d7ca97489cc0f8907713ec23` in timbleslu/auto-beli.

## Repaired and tested

- External names, addresses, identifiers and photo references never become HTML or inline
  event handlers. UI construction uses `createElement`, `textContent` and event listeners.
  Chromium reproduces the old HTML-attribute-decoding payload and verifies the replacement
  with CSP both enabled and disabled. Punctuation and Unicode are preserved.
- CSP restricts scripts, styles, images and connections to this origin. No unsafe-inline,
  unsafe-eval, frames, external base URLs or objects. Responses use no-store, no-referrer
  and nosniff. API documentation endpoints are disabled.
- Authentication is mandatory. A 192-bit, ten-minute, single-use pairing secret is sent
  in a JSON POST; the URL contains no credential. It exchanges for an eight-hour random
  session cookie. Cookies are HttpOnly and SameSite=Strict; TLS uses Secure and __Host-.
  Login attempts are globally rate limited. Logout revokes the session. Restart revokes all sessions.
- Mutations require exact Origin, JSON, same-origin Fetch Metadata when present, and a
  separate CSRF header. Host is checked against the configured exact origin. Proxy headers
  are disabled. Phone launches require TLS and a private LAN bind address. No tunnels.
- The default service is loopback-only. The public shell/static code contains no private data.
  Photo routes require authentication, membership in the current queue/approved worklist,
  a trusted internal resolver, an allowed raster type and matching file signature. No path API exists.
- Runtime files, backups and exports are owner-only. The launcher sets a restrictive umask.
  Locations are cached locally, not uploaded to GitHub. Logs contain operational counts,
  not restaurant names, ratings or provider error bodies. HTTP access logs are disabled.
- Approvals are validated against server-side candidates and photo references. A batch commits
  atomically and reapproval preserves per-photo progress. Legacy rows stay intact; consistent
  SQLite backups are replaced atomically. A failed backup blocks startup.

## Dependency evidence

Python is locked in uv.lock, including the development tools. Build requirements are pinned.
The resolved Python dependency audit returned no known vulnerabilities during this session.
This is evidence at one time, not a guarantee against unknown vulnerabilities or malicious packages.
Actions are pinned to verified upstream commit IDs. The workflow builds a review artifact;
it has read-only repository permissions and does not publish unsigned releases automatically.
PyInstaller's ad-hoc bundle signature is not Developer ID signing or notarization.

The optional local device tools use Appium 3.9.0 and XCUITest 12.22.8 with npm integrity hashes.
Appium's root glob/minimatch copies are overridden to patched 14.0.2 / 11.0.1. The driver's
published package bundles older nested copies that npm overrides/dedupe do not replace.
`npm audit` still reports 18 affected dependency entries from TWO underlying moderate advisories:

- [GHSA-3g3m-2fjr-6pw4](https://github.com/advisories/GHSA-3g3m-2fjr-6pw4): glob cancellation
  may leave filesystem traversal running after timeout (patched in 14.0.2).
- [GHSA-g3hv-75wg-m249](https://github.com/advisories/GHSA-g3hv-75wg-m249): attacker-controlled
  patterns may amplify work in minimatch (patched in 11.0.1).

These are actual advisories, not merely theoretical supply-chain concerns. Their relevance
is availability under hostile traversal/pattern input. No external client is allowed to reach
Appium; Beli automation is not enabled. Resolving the bundled driver copies and verifying driver
compatibility remain pre-production work. Do not use npm audit fix --force: its proposed
Appium downgrade/driver upgrade is not a tested compatible pair. No clean Node audit is claimed.

## Remaining boundaries

This protects against external restaurant strings, untrusted browser origins and unauthenticated
LAN visitors. It does not protect against someone controlling this Mac or its unlocked user account.
Phone certificate trust must be explicitly established and checked in Safari. No certificate-warning
bypass is supported. Private CA keys must remain on the Mac; remove trial root trust when done.

No automatic Beli interactions exist yet. Manual statements are stored as user_confirmed and
user_finished, never verified. No browser endpoint can claim machine verification. A future device
worker must have a global exclusive phone lock, observed accessibility controls, expected-screen
checks, positive save evidence, separate attachment statuses and uncertain-upload reconciliation.
Those real-device checks are listed in DEVICE-TRIAL.md. Unknown states must pause.

No private screenshots, Photos pixels or library were uploaded for debugging. No Beli passwords,
reverse-engineered account APIs, speculative deep links, sync-setting changes, asset deletion,
Beli reinstall or ranking reset are used.
