# Local Beli shortlist integration

The matcher is implemented; real Beli list acquisition is a separate, unverified gate.
Normal users should not prepare a CSV or type coordinates. Connect the phone later so the
assistant can inspect the installed app's actual controls and establish a read-only capture.
No Beli account API, password, invented deep link or assumed export endpoint is used here.

## Capture contract for the later phone adapter

The adapter must observe the user's own list, distinguish Been from Want to Try, and collect
the exact branch name/address. It must not tap Save, rate, remove, follow, or change filters
without understanding their effects. An unexpected or ambiguous screen stops capture.
List captures can be partial; show the observed count, never imply the entire list is loaded.
No photo screenshots or pixels are needed. Keep any minimal accessibility capture private.

Use `SavedPlace` and `SavedPlaces(ledger).upsert(entries)` locally, or the existing authenticated
web session's `POST /api/saved-places`, with JSON and the session's `X-CSRF-Token` and exact
Origin. Pairing/session credentials never belong in URLs. Each batch is limited to 500 entries
over HTTP and is validated before any write. The API is a local ingestion seam, not a Beli API.

Synthetic request example (not real account data):

```json
{
  "entries": [{
    "name": "Example Café",
    "address": "1 Example Street, Test City",
    "list_status": "want_to_try",
    "lat": 40.006,
    "lon": -73.0,
    "location_source": "beli_ui"
  }]
}
```

`beli_id` is optional and may contain only an actual observed Beli identity. Never insert an
OSM/Google identifier there. If coordinates are unavailable, omit them and leave
`location_source` as `unlocated`. A later address-resolution step must present ambiguous
branches for confirmation before storing coordinates as `user_confirmed_address`. Do not
geocode a brand name and silently attach its first result. Status can also be `been` or
`unknown`; no numeric ratings, credentials or private user feed are required.

`GET /api/saved-places` requires the same session and returns entries plus aggregate counts.
`live_sync` is always false: no device-list synchronization has been implemented. The discovery
screen shows count, located count and list statuses. Repeated upserts are idempotent. Partial
captures never delete old rows; changed/stale membership needs an explicit recapture and
current Beli check. Capturing a shortlist never approves a visit, changes a rating or uploads.

## Matching behavior

When the local catalog is nonempty, `POST /api/discovery-match` searches it first. `radius_m`
is one of 250, 500, 1000 (default), 2000. A branch is eligible if any selected geotag lies in
range; both nearest and farthest distances are retained, with GPS disagreement flagged.
Matching venue names sort first, then distance. Addresses and same-name branches stay separate.
Saved membership and photo hints are evidence for review; all results remain ambiguous.

An explicit name/address query can find a saved branch beyond the radius, with a warning.
Without geotags/branch coordinates, exact venue hints or an explicit query can offer candidates
with distance unavailable; the whole saved list is never dumped into a no-GPS match.
Photo times bound one visit to three hours. List timestamps are not invented visit evidence.

With a loaded catalog, misses remain pending and make no network call unless
`include_external: true` is explicitly supplied (the UI checkbox). Extra provider candidates
stay in their own identity namespace; provider failures retain local candidates. No automatic
OSM/Beli identity merge occurs. When the catalog is empty, the prior OSM flow continues with a
visible “not loaded” notice. The wider shortlist radius does not expand external queries.

Approved work stores the candidate source/list status separately from manually confirmed
Beli identity and ranking. Been candidates warn against reranking just to attach photos.
No saved-list status completes a ranking or an attachment. Existing approvals are not rematched;
new shortlist data is used only on an explicit draft search.

## Storage, update and rollback

`assistant_saved_places` is added to the private ledger; old completion records are untouched.
The existing startup backup runs before the table is created. Payload extensions are additive
and old worklists remain readable. Older code ignores the new table/extra candidate fields.
To roll back, stop the launcher, retain the whole private data folder, and use the previous
source commit. For a data rollback use the matching startup backup as described in RUN-ME.md;
restoring it discards subsequent shortlist/progress changes, so keep the current database copy.
No local rollback changes Beli itself. Never commit the catalog or real captures to GitHub.

## Remaining device proof

Still needed: real-list capture (including scrolling/completeness), exact branch location
acquisition, reading existing rankings without changes, one approved photo's availability and
actual picker selection, save verification, then interruption and duplicate prevention on device.
Synthetic tests do not establish any of those capabilities or overall matching accuracy.
