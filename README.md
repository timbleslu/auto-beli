# Photos → Beli assistant (work in progress)

This fork is being converted into a Photos-only assistant. The secure photo-first review interface,
batch approvals, persistent manual worklist, and approved-original exporter are implemented.
**Automatic Beli navigation, iPhone picker selection and saved-result verification are not implemented or validated yet.**
Do not use this as an unattended uploader.

Start with [RUN-ME.md](RUN-ME.md). See [SECURITY.md](SECURITY.md) for the threat model,
[DEVICE-TRIAL.md](DEVICE-TRIAL.md) for the real-device acceptance gate, and
[TEST-RESULTS.md](TEST-RESULTS.md) for actual test evidence and limitations.

New installations use Apple Photos only, OpenStreetMap, a seven-day range and three visits.
No Google Takeout, CSV, Google key or billing account is needed. Discovery uses existing local
Apple Photos food labels and also exposes unlabelled/no-GPS images. You define each visit's
photo group before matching. Existing Photos venue/city names are used before generic nearby
search, with original Unicode spelling and location context preserved. Only that selected lookup sends coordinates or a name query
to external OSM services. Restaurant suggestions always require approval and can be corrected
by name. If OSM lacks the restaurant, you may supply its full name and branch address for
review; this remains separate from an observed Beli identity. Food labels and GPS are
suggestions, not proof of a restaurant visit.

A private, persistent Beli shortlist now provides the first candidate pool when loaded,
with selectable 250 m–2 km ranges, branch-specific addresses, Photos name hints, distance
ranges and separate Been/Want to Try labels. Matching the shortlist is local; extra OSM
suggestions are opt-in while a list is loaded. List membership never proves a photo visit.
Actual iPhone list capture is **not implemented or verified yet**; an empty list retains the
existing OSM flow with an explicit status notice. No export or CSV is required for normal use.
See RUN-ME.md and SAVED-PLACES.md for the pending device gate and local ingestion contract.

Old `handled` completion rows remain intact. They are local records, not evidence that
Beli saved anything. New photo visits are shown for reconciliation even when an old
Added row exists. New confirmations are stored separately and labeled `user_confirmed` /
`user_finished`, never machine verified. No web endpoint can set verified results.

## Development

Use Python 3.13 and uv 0.12.5. The tested macOS version is recorded in TEST-RESULTS.md.

```sh
uv sync --locked --extra dev
uv run --locked playwright install chromium
uv run --locked pytest -q
```

Only synthetic photos and mocked providers are used in tests. Real-device operations
require the separate trial gate and specific approved restaurant/photo selections.
`device-tools/package-lock.json` locks the optional project-local Appium tools; see
its README before running them. Installing those tools does not establish a Beli integration.

The original project is [kristenharim/beli-tool](https://github.com/kristenharim/beli-tool).
All changes for this assistant belong to [timbleslu/auto-beli](https://github.com/timbleslu/auto-beli).
