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
The first audit found 18 affected dependency entries from TWO actual moderate advisories:
[glob cancellation](https://github.com/advisories/GHSA-3g3m-2fjr-6pw4) and
[minimatch pattern amplification](https://github.com/advisories/GHSA-g3hv-75wg-m249).
These were availability vulnerabilities, not merely theoretical supply-chain risks.

Both are now repaired across the resolved tree using glob 14.0.2 and minimatch 11.0.1.
The published driver bundled older nested copies that npm overrides/dedupe could not replace.
A deterministic repackaging step removes those dependency bundles and the bundleDependencies
manifest field. A separate two-line fix binds the fallback USB forwarder to loopback in source and
compiled JavaScript, with a real socket-binding regression test. The other 740 upstream files are unchanged. The official upstream
SHA512 is checked before repackaging. The generated archive is committed with provenance and
an independently tested checksum; normal npm locking now applies to every dependency copy.
See device-tools/vendor/README.md and tools/unbundle_driver.py. Only that explicit fallback loopback-binding change modifies executable driver code.
A fresh npm ci --ignore-scripts succeeded, and npm audit reported ZERO known vulnerabilities.
Driver import and registration also succeed. Real-device compatibility is separately tested;
a clean dependency audit does not prove Beli navigation or save detection works.

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

## Photo-first discovery update

The authenticated discovery endpoint exposes only visible still images in the configured
window. Food hints use existing local Photos labels; unlabelled and no-GPS images are available
for manual review. No matching request runs at startup. A selected group is validated against
the in-memory window before its coordinates/name query can reach OSM. External results remain
unconfirmed even for a single candidate. Unapproved groups persist in a new additive SQLite
table; approved selections cannot be removed or overwritten through draft editing. Photo UUIDs
are allowlisted before resolving image paths, including restored approved selections.
