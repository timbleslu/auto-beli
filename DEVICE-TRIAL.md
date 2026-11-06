# USB pilot acceptance gate — not passed yet

The session verified macOS 27.0.1 (26A434), Xcode 27.2 (27B52), and a physical
USB-connected iPhone 16 Pro. iOS version and installed Beli version have not been read yet.
Mac Photos access is blocked by macOS Full Disk Access pending a Codex restart.
No Beli rankings, uploads or existing app data have been changed.

## Next physical step

Restart Codex to apply the Full Disk Access change. Reopen this chat. The next assistant
should use the checkpoint in the outputs folder and recheck read-only Photos/device access.
Keep the iPhone connected and unlocked. Do not enter Apple/Beli passwords in chat.

## Tooling prepared

`device-tools/` contains a pinned local Appium/XCUITest install. The driver was registered in
its ignored private Appium home. No real-device session has been created, and WebDriverAgent
has not been signed or deployed. See SECURITY.md for unresolved bundled dependency advisories.
`beli-tool doctor` checks readiness. `beli_tool.device.inspect_session` reads source only from
an existing loopback Appium session; it neither creates a session nor performs taps.

Use Apple's Xcode directly for developer signing. Follow the official
[Appium device setup](https://github.com/appium/appium-xcuitest-driver/blob/master/docs/getting-started/device-setup.md)
and [provisioning guide](https://github.com/appium/appium-xcuitest-driver/blob/master/docs/getting-started/provisioning-profile/index.md).
Free and paid Apple accounts have different signing paths; automatic signing through Appium
must not be assumed available with a free account.

## Ordered real-device proof

Each physical/system action should be guided one at a time:

1. Verify trust/unlock, exact iOS and Beli versions, and local Mac geotagged pictures for
   October 30–November 5, 2026. Summarize counts without exposing coordinates or pictures.
2. Enable Developer Mode on the iPhone if needed, following its reboot/confirmation flow.
   Inspect required UI Automation settings. Do not enable unrelated Safari automation settings
   unless the observed native app flow actually needs webview automation.
3. In Xcode, sign only WebDriverAgent with the user's chosen team. User enters credentials
   in Xcode, never chat. Install this helper without reinstalling Beli or resetting Beli's data.
4. Start Appium on 127.0.0.1 and use USB forwarding only. Inspect the installed Beli bundle
   identity locally; do not guess it. Use noReset, avoid app/app reinstall capabilities, disable
   auto launch until the user opens Beli. Obtain read-only accessibility source locally first.
   Do not send private screens/source to external AI debugging services without permission.
5. Observe restaurant search, name/address identity, ranking screens, picker and saved views.
   Implement only observed unique accessibility locators with condition-based waits. Unexpected
   screens pause. Check actual Beli share links and the iPhone Shortcuts action catalog;
   website research found no documented restaurant-navigation contract or official Shortcuts
   action suitable for implementation. Do not infer absence from this limited research.
6. Ask the user to choose ONE restaurant and ONE approved photo from the batch. Prove iPhone
   availability (or explicitly test one transferred copy). A Mac UUID is not a picker identity.
7. Navigate the correct branch; pause for physical rating/comparison answers. Require a positive
   saved-ranking indicator, preferably after reopening the exact restaurant. App backgrounding
   or closing a modal does not count. Inspect an already-ranked restaurant without reranking it.
8. Prove the real picker can select that image, observe its actual attachment limits, save it,
   and verify the same saved attachment after reopening the restaurant. Capture minimal local
   evidence, not a private screenshot upload. Preserve an uncertain upload as pending reconciliation.
9. Only then implement and test several-restaurant advancement. Exercise pause, resume, stop,
   USB loss, restart, failed upload, ambiguous branches, duplicate prevention and stale UI actions.
   Save confirmed rankings separately; retry missing attachments only after reconciling saved results.
10. Audit private-file exclusion; record exact versions/evidence in TEST-RESULTS.md; commit and
    push the validated changes only to timbleslu/auto-beli's working branch after verifying remotes.

If positive evidence is unavailable, keep the visit pending. The current clearly labeled
manual “Done — next restaurant” path is an explicit fallback, not automatic Beli completion.
