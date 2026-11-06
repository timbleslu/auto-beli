# Run me: Photos → Beli

## What you can use today

You can review photo-based restaurant suggestions, approve a batch, and keep a persistent
manual worklist. The tool cannot yet navigate Beli, attach photos, or detect saves automatically.
Use it with the assistant present for the first trial. Your ratings and comparisons always belong to you.

The default interface opens only on your Mac. Phone access needs the separate HTTPS setup below.
Appium and WebDriverAgent are separate local USB tools; neither is a public web service.

## First session — one step at a time

1. Open this folder in Finder. Double-click `Start.command`. A Terminal window opens.
   If macOS refuses the file, stop and ask for help. Do not disable Gatekeeper or remove quarantine.
   The launcher installs the exact versions in the lockfile; first launch needs internet.
2. If Photos access fails, open Photos and confirm your usual library. Allow Codex or the
   Terminal app you actually use in System Settings → Privacy & Security → Full Disk Access.
   The assistant can retry the read-only metadata check. Do not grant unrelated apps access.
3. First launch creates `~/Library/Application Support/beli-tool/config.toml`.
   Open it with a text editor if you need to change dates. Keep `provider = "osm"`,
   `photos_only = true` and `max_visits = 3`. Set `since` and `until` to a short range.
   Use [config.example.toml](config.example.toml) as an example. A range may cover at most 31 days.
   For multiple libraries, set `photos_library = "~/Pictures/Photos Library.photoslibrary"`
   to your actual chosen library. No library or synchronization setting is changed by this tool.
4. Read the privacy notice: matching sends GPS coordinates to OSM Overpass servers, or OSM Nominatim for incomplete bounded suggestions if Overpass fails.
   Discovery is local; selected-visit matching is not fully offline. No photo pixels go to OSM.
   A service outage can delay a lookup, but known Overpass outages are not retried for every
   photo group in the same batch. Cached lookups and saved groups survive restart.
5. A Mac pairing dialog appears. Click Copy code; the local browser page opens. Paste
   the code into its pairing field and click Connect. The address is normally `http://127.0.0.1:8000`.
   A command-line launch without `--pairing-dialog` prints the code in its terminal instead. It expires after ten minutes and can connect
   one browser once. A connected session lasts up to eight hours; restart to pair again.
   The code is never part of the web address. Keep the Terminal window private.
6. In “Choose photos from one visit,” start with the Likely food filter. These suggestions
   come from Apple Photos' existing local labels, not a new AI upload. Labels can be wrong or
   missing. Use All images, Other / unlabelled, or Without GPS to find omitted pictures.
   The inventory includes all visible still images in your chosen dates; hidden assets and videos
   are excluded. The three-visit limit does not truncate discovery.
7. Select pictures from ONE visit. Click “Find restaurants for selected photos.” This sends
   only the selected visit's coordinates to OSM. Photos themselves stay local. If the photos
   have no GPS, or suggestions are wrong, enter the restaurant name with city/address and
   request a name search. Groups spanning more than three hours must be split into separate visits.
8. Review the restaurant's full branch address. No restaurant is accepted automatically,
   including a single nearby result. OSM coverage is incomplete and may not contain your restaurant.
   Leave it pending if the correct branch cannot be identified. Use “Search this visit by name”
   to replace wrong suggestions without losing the group's selected photos.
9. Every selected image is shown in the group; there is no six-photo gallery cutoff. These
   user-selected pictures are checked in the draft approval so you don't need to select them twice.
   Uncheck any you do not want attached, or choose “Continue without photos.” Choose the correct
   restaurant, check “Include this visit,” then press “Approve selected mappings.” This final
   batch action approves uploads; discovery alone does not. Unchanged approvals survive restart.
   An unapproved group can be returned to discovery; an approved group's saved progress is protected.
10. Current Start/Pause/Resume/Stop controls manage a MANUAL worklist. No automatic Beli uploader
    is enabled yet. On your iPhone, search the approved restaurant and check its exact address.
    Make every rating/comparison choice yourself. Reopen it and check the ranking saved before
    recording “I checked that my ranking saved in Beli.” This is manual testimony, not machine proof.
11. Follow the one-photo procedure below. After checking that specific image is saved on the
    correct restaurant, record its manual confirmation. “Done — next restaurant (manual confirmation)”
    refuses to advance while requested photos remain pending. You can explicitly finish without
    remaining photos. Skip is a skip, not successful completion.

## Photos on the iPhone — prove one first

A Mac Photos UUID or file path cannot select an iPhone picker image. We have not verified
that your Mac images are on your phone. No photos will be attached automatically in this version.
Uploaded photos inherit Beli's applicable visibility settings; review them in Beli before uploading.
[Beli's privacy policy](https://beliapp.com/app-privacy-policy) describes user content and visibility.

1. Choose just one approved photo for the trial. Find it in the iPhone Photos app and compare
   its content and capture date with the approved Mac image. Do not assume iCloud synchronized it.
2. If it is only on the Mac, stop the review server with Control-C. From this folder run
   `uv run --locked beli-tool export-approved` (add `--config private/trial.toml` if that is your config).
   This reads approved originals and creates separate quality JPEG copies without EXIF/GPS,
   IPTC/XMP, captions or original filenames. It refuses thumbnail-sized inputs and missing originals.
   Originals are never edited. HEIC decoding uses Apple's local `sips` tool.
3. The command prints a NEW private export folder. Transfer only the one intended copy to
   your own unlocked iPhone using AirDrop. Accept it yourself. This transfer/import procedure
   has not yet been tested in this session. Confirm the actual image appears in iPhone Photos.
4. Optionally create a new iPhone Photos album containing only the approved trial image.
   Do not enable iCloud Photos or change sync settings. Do not assume Beli's picker supports albums;
   inspect its actual controls first. The exporter does not create an iPhone album.
5. In the correct restaurant in Beli, use its observed photo control and select that single
   image yourself for now. Check its preview before saving. Observe the app's real limits;
   no attachment count or format limit has been assumed.
6. Reopen the restaurant and verify the saved photo. If the result is uncertain, leave it
   pending and inspect before retrying. Repeating an uncertain upload can create duplicates.
   Confirmed ranking and photos remain recorded separately, so a failed photo does not require reranking.

## Pause, resume and shutdown

Pause stops local worklist changes; Resume continues the same visit. No phone worker exists yet.
Stop ends the review session but preserves approvals and confirmations. Control-C shuts down the server.
On restart, a previously running session becomes paused. Reconnect the browser and press Resume.
Only one normal launcher may use the same worklist at a time. Stop the first window before starting another.
Disconnect browser revokes its session. It does not clear worklist data or log you out of Beli.

## Phone web access with trusted HTTPS (optional)

Use Mac-only review until this has been set up and tested. No public tunnel is used.
The TLS helper creates a dedicated 30-day private CA and a 14-day server certificate.
Trusting a root certificate is a deliberate device trust change: keep its private key private,
and remove the trial CA from the iPhone when no longer needed. This setup is not automatic.

1. Find the Mac's Wi-Fi IPv4 address in System Settings → Wi-Fi → Details → TCP/IP.
2. In this folder, create certificates with your actual IP, for example:
   `python3 tools/make_phone_cert.py 192.168.1.42 private/phone-tls`
   The destination must be new. Transfer ONLY `ca.crt` to your own iPhone, using AirDrop.
   Never transfer `ca.key` or `server.key` or put them in GitHub.
3. Install that certificate profile in iPhone Settings. Then follow
   [Apple's certificate trust instructions](https://support.apple.com/en-us/102390):
   Settings → General → About → Certificate Trust Settings → enable trust for the dedicated
   “Auto Beli private trial CA.” Confirm the certificate came from your own generated folder.
4. Start with your real IP and certificate paths:
   `./Start.command --phone-host 192.168.1.42 --cert private/phone-tls/server.crt --key private/phone-tls/server.key`
   The server binds that private IP using TLS. Plain HTTP phone access is refused.
5. On the same Wi-Fi, open the exact printed `https://…:8000` address in Safari. It must load
   WITHOUT any certificate warning. Stop if it does not; do not bypass a warning.
   Enter the separate one-time code from the Mac. Verify unauthenticated photo/API access is rejected.
   A changed IP or expired certificate requires a new certificate and a fresh trust check.
6. When finished, stop the server. Remove the dedicated certificate profile in Settings →
   General → VPN & Device Management, and disable its trust. Delete only exported copies or trial
   certificate files if desired, never original Photos assets. No router port forwarding is needed.

A real TLS handshake and untrusted-certificate rejection are tested automatically; iPhone Safari
trust, LAN connectivity and firewall behavior still need the real-device trial.

## USB automation setup — continue with the assistant

Full Xcode, a trusted unlocked USB device, Developer Mode, and a signed WebDriverAgent helper
are required. See [DEVICE-TRIAL.md](DEVICE-TRIAL.md) for staged proof. Enter Apple credentials only
in Xcode/Apple interfaces and Beli credentials only in Beli. Do not reinstall Beli or reset its data.
The helper needs signing; free and paid Apple accounts have different setup constraints.
No signing or notarization credentials were supplied, so the .app artifact is unsigned and not notarized.
Use the source launcher while that remains unresolved; do not weaken macOS protections.

## Update or roll back safely

1. Stop the assistant. Copy the entire private data folder to another private folder as a backup.
   It includes the database, caches, exports and logs. Keep that backup outside GitHub.
2. Update only from `timbleslu/auto-beli`, then run `uv sync --locked` in the checked-out version.
   Do not run simultaneous old/new versions. Dates and existing approvals remain local.
3. New tables are additive. Old `handled` records are preserved, and the first existing-database
   startup makes `ledger.sqlite.pre-assistant.bak`; each later startup refreshes `ledger.sqlite.bak`.
   These are consistent SQLite snapshots, including committed WAL data. A backup failure blocks launch.
4. For rollback, stop every assistant process and copy the current database somewhere private first.
   Check out the recorded baseline commit from TEST-RESULTS.md. Restore a COPY of the pre-assistant
   snapshot to a DIFFERENT private filename and point the old config at that copy. Keep the new database
   intact to preserve later progress. Do not overwrite either snapshot or the current database.
   The old version has the reported security flaws: do not expose its web server on a network.
5. No local rollback can undo changes saved in Beli. Review uncertain saves before any retry.
