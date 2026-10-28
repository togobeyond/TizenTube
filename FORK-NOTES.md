# Fork notes

This is a TV-specific fork of [reisxd/TizenTube](https://github.com/reisxd/TizenTube), maintained at
`togobeyond/TizenTube` for one TV. Upstream is tracked for reference only: nothing here is sent back,
and upstream changes are not merged automatically.

## The TV this is built for

| | |
|---|---|
| Model | Samsung QN65Q7FNA (2018 QLED) |
| OS | Tizen 4.0 |
| Build used | `standalone/` (TizenTubeOld — no Cobalt) |
| Install | Developer Mode + `0 vd_appinstall` over SDB (port 26101) |

## The setup that makes playback work

Developer mode **must stay on**, and **Host PC IP must be `127.0.0.1`**, followed by a reboot.

With any other Host PC IP, `getState` reports `canConnectToDaemon: false` and the app falls back to the
localhost proxy path. On this TV that path makes `POST /youtubei/v1/player` answer
`400 FAILED_PRECONDITION`, so browsing works but every video ends in "An error occurred". The
`127.0.0.1` value is what puts the app on the CDP injector path, where playback works.

To install anything from this Mac (including updates), temporarily set Host PC IP to `192.168.1.119`,
install, then set it back to `127.0.0.1` and reboot.

## Installing an update

Always install **over** the existing app; never uninstall first.

```bash
cd standalone
node service/build-service.js remove-cobalt-flags
tizenjs build . -t wgt -o release/TizenTubeOld.wgt \
  --author "$HOME/tizen-studio-data/keystore/author/author.p12" \
  --authorPwd "$(cat ~/tizen-studio-data/keystore/author/password)" \
  -p public --ignore "node_modules,/.*wgt$/,/userwidget/,/release/"
git checkout -- config.xml

cd ..
python3 tools/install.py 192.168.1.228
```

`tools/install.py` pushes the package and runs `0 vd_appinstall`, which updates in place and keeps
the app's data. Uninstalling wipes that data, which means the YouTube sign-in has to be done again.
The TV refuses an update signed with a different certificate, so keep the author certificate below
or the app has to be removed and reinstalled.

## Signing

- Author certificate: `~/tizen-studio-data/keystore/author/author.p12`
- Password: `~/tizen-studio-data/keystore/author/password`
- Distributor: `public` (passed with `-p public`)
- Certificate fingerprint (SHA-256 of the DER): `d2b5acb650b2425d6b3d3524fd26aa3ce78356526662c6ff39715716960b6ce4`
- The certificate was made while setting up a different app, so its subject still says
  `O=FreeMyTV, CN=Free My TV`. Only cosmetic: it signs every TizenTube build on this TV.
- It **expires on 2027-01-01**. Current installs keep working after that (the TV checks the
  signature when installing, not when launching), but updates need the replacement below.

The certificate lives in the Tizen CLI's default author slot, so the same file serves TizenTube
(`tizenjs --author`) and any Tizen CLI build. The CLI's active profile is a different project
(`jellyfin-tv`, pointing at `~/.jellyfin-tizen/certs/`), so the two do not interfere. This folder is
inside the weekly backup.

**Back these files up.** If the certificate is lost, updates cannot be installed in place; the app
has to be uninstalled and reinstalled, which also loses the YouTube login.

## Certificate renewal (prepared, not yet active)

Two replacements are staged in `~/tizen-studio-data/keystore/author/`. Both use the password in `password-2027`.

| File | Made with | Valid until | Notes |
|---|---|---|---|
| `author-2027.p12` | `tizenjs create-tizen-cert` | 2027-10-28 | preferred: a full year |
| `author-2027-cli.p12` | `tizen certificate` | 2027-01-01 | same shape as the cert in use (CA:FALSE) |

The Tizen CLI always writes an expiry of 2027-01-01, so it cannot extend past that; `tizenjs` issues
a year, but marks the author certificate CA:TRUE. Both chain to `Tizen Developers CA`, and both were
tested to produce a complete signature (`author-signature.xml` + `signature1.xml`).

To switch, at the first update after 2027-01-01:

1. Build with `--author "$HOME/tizen-studio-data/keystore/author/author-2027.p12" --authorPwd "$(cat ~/tizen-studio-data/keystore/author/password-2027)"`.
2. Remove TizenTube on the TV (Apps → TizenTube → Delete). Its data goes too.
3. `python3 tools/install.py <TV IP>`.
4. Sign in to YouTube once. Updates after this keep working in place with the new certificate.

Before relying on it, it is worth proving the new certificate is accepted: build a throwaway copy
with a different app id (so no uninstall is needed), install it, and delete it. If the TV rejects it,
use `author-2027-cli.p12` before its own expiry, or make a new certificate with the Tizen CLI and
switch then.

## What this fork changes

- **Local userscript.** The userscript built in `mods/` is packaged into the service and served from
  `http://localhost:8100/tizentube/userscript.js`, instead of downloading
  `@foxreis/tizentube` from jsDelivr on every page load.
- **New launch screen.** App mark, wordmark, one transform-animated accent line, a status line, and an
  inline error instead of a blocking `alert()`. Back always exits, including on the error screen.
- **Startup that suits this TV.** The service gets up to ~2 minutes on a cold boot, the launch request
  falling through to a `getState` probe when the TV refuses it, and the debugger is attached to the
  running app so startup does not drop out to the home screen. The live attach retries for 12 s
  because sdbd is still coming up right after a power cycle.
- **HQ thumbnails on by default**, with a one-time migration for installs that stored the old default.
  `hqdefault` plus `sddefault` are offered so the client picks the sharpest it can use; `maxres` is
  left out because it 404s on many videos.
- **Square app icon.** A 1024x1024 tile replaces the old 16:9 banner (`icon_16b9.png`, removed).
- **Theme panel** (Red key) restyled for 10-foot viewing; the dead notification CSS is gone.

## Useful details

- Package id `xvvl3S1TT1`, app id `xvvl3S1TT1.TizenTubeStandalone`, service `xvvl3S1TT1.StandaloneService`.
- A retail TV's sdbd only accepts file pushes: `ls`, `cat` and other shell reads are refused, so the
  app cannot be inspected from a computer beyond `0 vd_applist` / `0 debug`.
- To look inside the running app, `0 debug xvvl3S1TT1.TizenTubeStandalone` prints a CDP port that is
  reachable over the LAN (`http://<tv-ip>:<port>/json/list`). The bundled Chromium predates
  `chrome-remote-interface` protocol negotiation, so talk raw WebSocket to the target.
- Bump `version` in `standalone/config.xml` for every update.
- Tag `vX.Y.Z` only when a release build is wanted; the GitHub workflow then builds the three WGTs.
