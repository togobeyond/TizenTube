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
  --author "$HOME/.tizentube/author.p12" \
  --authorPwd "$(cat ~/.tizentube/password)" \
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

- Author certificate: `~/.tizentube/author.p12`
- Password: `~/.tizentube/password`
- Distributor: `public` (passed with `-p public`)
- Certificate fingerprint (SHA-256 of the DER): `d2b5acb650b2425d6b3d3524fd26aa3ce78356526662c6ff39715716960b6ce4`
- The certificate was made while setting up a different app, so its subject still says
  `O=FreeMyTV, CN=Free My TV`. Only cosmetic: it signs every TizenTube build on this TV.
- It **expires on 2027-01-01**. Before then, make a fresh certificate and plan one reinstall
  (uninstall + install), because the TV will not take an update signed with another key.

**Back both files up.** If the certificate is lost, updates cannot be installed in place; the app
has to be uninstalled and reinstalled, which also loses the YouTube login.

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
