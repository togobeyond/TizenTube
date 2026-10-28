#!/usr/bin/env python3
"""Installs TizenTube on a Samsung TV in Developer Mode over Wi-Fi, without Samsung's sdb.

    python3 tools/install.py 192.168.1.50                       # install or update, then open it
    python3 tools/install.py 192.168.1.50 --uninstall           # remove it
    python3 tools/install.py 192.168.1.50 path/to/package.wgt   # install a specific build

Installs OVER the existing app by default: uninstalling wipes the app data, which means the
YouTube sign-in has to be done again. The TV only updates in place when the new package is
signed with the same certificate as the installed one.

Before the first install, on the TV: open Apps, type 1 2 3 4 5, turn Developer mode on with this
computer's IP as Host PC IP, and restart the TV.

The SDB wire protocol client below is adapted from free-my-tv's tizen/install.py (MIT).
It needs only Python 3: no Tizen Studio, no Rosetta on Apple Silicon.
"""
import os
import re
import socket
import struct
import sys
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_WGT = os.path.join(ROOT, 'standalone', 'release', 'TizenTubeOld.wgt')
PORT = 26101
MAX_DATA = 4096
ON_TV = 'Apps, TizenTube, Delete'


class Sdb:
    """The pieces of the SDB wire protocol this needs: ADB's framing (a 24-byte header whose
    checksum is a byte sum), streams opened with OPEN, and every WRTE answered with OKAY."""

    def __init__(self, ip):
        self.sock = socket.create_connection((ip, PORT), timeout=15)
        self.buf = b''
        self.next_id = 1
        self.okay, self.inbox, self.closed = {}, {}, set()
        self.send(b'CNXN', 0x01000000, MAX_DATA, b'host::\0')
        cmd, _, max_data, data = self.read()
        if cmd != b'CNXN':
            raise ConnectionError('the TV answered %r instead of connecting' % cmd)
        self.max = min(max_data, MAX_DATA)
        self.banner = data.rstrip(b'\0').decode('utf-8', 'replace')

    def send(self, cmd, arg0, arg1, data=b''):
        c = struct.unpack('<I', cmd)[0]
        self.sock.sendall(struct.pack('<6I', c, arg0, arg1, len(data),
                                      sum(data) & 0xFFFFFFFF, c ^ 0xFFFFFFFF) + data)

    def _recv(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError('the TV closed the connection')
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def read(self):
        cmd, arg0, arg1, n, _, _ = struct.unpack('<6I', self._recv(24))
        return struct.pack('<I', cmd), arg0, arg1, self._recv(n) if n else b''

    def pump(self):
        cmd, remote, local, data = self.read()
        if cmd == b'OKAY':
            self.okay[local] = remote
        elif cmd == b'WRTE':
            self.inbox[local] = self.inbox.get(local, b'') + data
            self.send(b'OKAY', local, remote)
        elif cmd == b'CLSE':
            self.closed.add(local)

    def open(self, service):
        local, self.next_id = self.next_id, self.next_id + 1
        self.send(b'OPEN', local, 0, service.encode() + b'\0')
        while local not in self.okay:
            if local in self.closed:
                raise ConnectionError('the TV refused ' + service)
            self.pump()
        return local, self.okay.pop(local)

    def write(self, stream, data):
        local, remote = stream
        self.send(b'WRTE', local, remote, data)
        while local not in self.okay:
            if local in self.closed:
                raise ConnectionError('the TV closed the stream')
            self.pump()
        del self.okay[local]

    def read_until(self, stream, done, seconds):
        local = stream[0]
        end = time.time() + seconds
        while time.time() < end and local not in self.closed and not done(self.inbox.get(local, b'')):
            self.sock.settimeout(max(0.1, end - time.time()))
            try:
                self.pump()
            except socket.timeout:
                break
        self.sock.settimeout(15)
        return self.inbox.pop(local, b'')

    def shell(self, command, until=None, seconds=20):
        stream = self.open('shell:' + command)
        out = self.read_until(stream, lambda t: bool(until and re.search(until, t.decode('utf-8', 'replace'))), seconds)
        return out.decode('utf-8', 'replace')

    def capabilities(self):
        text = self.read_until(self.open('capability:'), lambda t: False, 5).decode('utf-8', 'replace')
        return dict(line.split(':', 1) for line in text.splitlines() if ':' in line)

    def push(self, path, data):
        stream = self.open('sync:')
        spec = ('%s,%d' % (path, 0o100644)).encode()
        self.write(stream, b'SEND' + struct.pack('<I', len(spec)) + spec)
        step = self.max - 8
        for i in range(0, len(data), step):
            part = data[i:i + step]
            self.write(stream, b'DATA' + struct.pack('<I', len(part)) + part)
        self.write(stream, b'DONE' + struct.pack('<I', int(time.time())))
        answer = self.read_until(stream, lambda t: len(t) >= 8, 60)
        if answer[:4] != b'OKAY':
            raise ConnectionError("the TV didn't take the file: " + answer[8:].decode('utf-8', 'replace'))
        self.send(b'WRTE', stream[0], stream[1], b'QUIT' + struct.pack('<I', 0))


def this_computer(ip):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((ip, PORT))
        return s.getsockname()[0]
    except OSError:
        return "this computer's IP"


def manifest_of(wgt):
    with zipfile.ZipFile(wgt) as z:
        if 'author-signature.xml' not in z.namelist():
            sys.exit('%s is not signed, and the TV only installs signed apps.' % os.path.basename(wgt))
        return z.read('config.xml').decode('utf-8')


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        sys.exit(__doc__)
    ip = args[0]
    wgt = args[1] if len(args) > 1 else DEFAULT_WGT
    uninstall = '--uninstall' in sys.argv

    if not os.path.exists(wgt):
        sys.exit('No package at %s. Build it first (see FORK-NOTES.md).' % wgt)
    manifest = manifest_of(wgt)
    tag = re.search(r'<tizen:application[^>]*>', manifest).group(0)
    app_id = re.search(r'\bid="([^"]+)"', tag).group(1)
    package = re.search(r'\bpackage="([^"]+)"', tag).group(1)

    try:
        sdb = Sdb(ip)
    except (OSError, ConnectionError) as e:
        sys.exit("Couldn't reach the TV on port %d (%s). On the TV: Apps, 1 2 3 4 5, Developer mode on "
                 "with Host PC IP %s, then restart the TV." % (PORT, e, this_computer(ip)))
    caps = sdb.capabilities()
    version = (sdb.banner.split(':')[2] if sdb.banner.count(':') >= 2 else sdb.banner)
    print('Connected: %s, Tizen %s.' % (version, caps.get('platform_version', '?')))

    if uninstall:
        out = sdb.shell('0 vd_appuninstall ' + package, r'spend time', 120).strip()
        if not re.search(r'uninstall completed', out):
            sys.exit(('The TV said:\n' + out if out else "The TV didn't answer.") +
                     '\nRemove it on the TV instead: ' + ON_TV + '.')
        print('Removed. App data went with it: the YouTube sign-in has to be done again.')
        return

    remote = caps.get('sdk_toolpath', '/home/owner/share/tmp/sdk_tools').rstrip('/') + '/' + os.path.basename(wgt)
    with open(wgt, 'rb') as f:
        data = f.read()
    print('Copying %d KB to the TV ...' % (len(data) // 1024))
    sdb.push(remote, data)
    print('Installing over the existing app (this keeps its data) ...')
    out = sdb.shell('0 vd_appinstall %s %s' % (package, remote), r'spend time', 120)
    if not re.search(r'install completed', out):
        hint = ''
        if 'different certificate' in out:
            hint = ('\nThe installed TizenTube was signed with another certificate. Remove it on the TV ('
                    + ON_TV + '), then run this again. That also drops the YouTube sign-in.')
        sys.exit("The TV didn't finish installing. It said:\n" + out.strip() + hint)
    sdb.shell('0 was_execute ' + app_id, r'launched|spend time', 20)
    print('Installed and open on the TV.')


if __name__ == '__main__':
    main()
