// The TizenBrew-way of TizenTube. Uses CDP and SDB to inject the userscript.

const adbhost = require('adbhost');
const CDP = require('chrome-remote-interface');
const fetch = require('node-fetch');
const userscript = require('../userscript.js');


var isConnecting = false;
const isTizen3 = tizen.systeminfo.getCapability('http://tizen.org/feature/platform.version').startsWith('3.0');

// When a Player page was navigated to recently, a booting app is the relaunch
// from `0 debug`, not a fresh user launch: it must wait, never exit again.
var lastNavigateAt = 0;
var NAVIGATE_COOLDOWN_MS = 25000;

function markNavigated() {
    lastNavigateAt = Date.now();
}

function inNavigateCooldown() {
    return Date.now() - lastNavigateAt < NAVIGATE_COOLDOWN_MS;
}

function connectToDebugger(host, port, args) {
    fetch(`http://${host}:${port}`).then(_ => {
        CDP({ host, port, local: true }, client => {
            isConnecting = false;
            client.Runtime.enable();
            client.Page.enable();

            client.on('Runtime.executionContextCreated', m => {
                client.Runtime.evaluate({ expression: userscript.code, contextId: m.context.id });
            });

            markNavigated();
            client.Page.navigate({ url: `https://youtube.com/tv?additionalDataUrl=http%3A%2F%2Flocalhost%3A8085%2Fdial%2Fapps%2FYouTube${args ? `&${args}` : ''}` });

            client.Page.setBypassCSP({ enabled: true });
        })
    }).catch(e => {
        return setTimeout(() => connectToDebugger(host, port, args), 100);
    })
}

function canConnectToDaemon() {
    return fetch('http://127.0.0.1:8001/api/v2/').then(res => res.json())
        .then(json => {
            return { canConnectToDaemon: (json.device.developerIP === '127.0.0.1' || json.device.developerIP === '1.0.0.127') && json.device.developerMode === '1', ip: json.device.ip, isConnecting, cooldown: inNavigateCooldown() }
        }).catch(e => {
            return canConnectToDaemon();
        });
}

/**
 * Attaches the debugger to the RUNNING app, without exiting it first. The
 * `0 debug` dance used to require the app to be gone; on TVs whose sdbd
 * attaches to a live process this skips the drop-to-home entirely.
 * Resolves {port, ip} when a debug port answers, else null. Never throws.
 */
function tryAttachOnce(timeoutMs) {
    return canConnectToDaemon().then(res => {
        if (!res.canConnectToDaemon) return null;
        return new Promise(resolve => {
            let done = false;
            let buf = '';
            let client = null;
            const timer = setTimeout(() => finish(null), timeoutMs || 6000);
            function finish(result) {
                if (done) return;
                done = true;
                isConnecting = false;
                clearTimeout(timer);
                try { if (client) client._stream.end(); } catch (e) {}
                resolve(result);
            }
            try {
                client = adbhost.createConnection({ host: '127.0.0.1', port: 26101 });
            } catch (e) { finish(null); return; }
            try {
                client._stream.on('connect', () => {
                    isConnecting = true;
                    let shellCmd;
                    try {
                        const packageId = tizen.application.getAppInfo().packageId;
                        shellCmd = client.createStream(`shell:0 debug ${packageId}.TizenTubeStandalone${isTizen3 ? ' 0' : ''}`);
                    } catch (e) { finish(null); return; }
                    shellCmd.on('data', (data) => {
                        buf += data.toString();
                        if (buf.includes('debug')) {
                            const port = Number(buf.substr(buf.indexOf(':') + 1, 6).replace(' ', ''));
                            if (Number.isFinite(port) && port > 0 && port < 65536) {
                                finish({ port: port, ip: res.ip });
                            }
                        }
                    });
                    shellCmd.on('error', () => finish(null));
                });
                client._stream.on('error', () => finish(null));
            } catch (e) { finish(null); }
        });
    }).catch(() => null);
}

/**
 * Keeps trying for a while: on a cold boot the TV's sdbd is still coming up
 * when the first launch asks, and a single early "no" used to be enough to
 * drop out to the home screen.
 */
function tryAttachDebugger(totalMs) {
    const end = Date.now() + (totalMs || 14000);

    function attempt() {
        return tryAttachOnce(4000).then(found => {
            if (found) return found;
            if (Date.now() >= end) return null;
            return new Promise(resolve => setTimeout(resolve, 1200)).then(attempt);
        });
    }

    return attempt().catch(() => null);
}

function startDebugger(args) {
    return canConnectToDaemon().then(res => {
        if (!res.canConnectToDaemon) return false;
        const client = adbhost.createConnection({ host: '127.0.0.1', port: 26101 });

        client._stream.on('connect', () => {
            const packageId = tizen.application.getAppInfo().packageId;
            isConnecting = true;
            const shellCmd = client.createStream(`shell:0 debug ${packageId}.TizenTubeStandalone${isTizen3 ? ' 0' : ''}`);
            shellCmd.on('data', (data) => {
                const dataString = data.toString();
                if (dataString.includes('debug')) {
                    const port = Number(dataString.substr(dataString.indexOf(':') + 1, 6).replace(' ', ''));
                    connectToDebugger(res.ip, port, args);
                    setTimeout(() => client._stream.end(), 1000);
                }
            });
        });

        return true;
    });
}

module.exports = {
    startDebugger,
    canConnectToDaemon,
    tryAttachDebugger,
    connectToDebugger
};