#!/usr/bin/env python3
"""Adversarial MPRIS player for testing the waybar media pill.

The pill's bug only appears when a player emits PARTIAL metadata -- a title
with no mpris:artUrl -- which real players do during a track change but not on
demand. Waiting for Spotify to do it is not a test, so this fakes it exactly.

Driven by a small command file so a test script can step it through a
sequence. Commands, one per line:

    track <name>        new track: new title/url, art present
    track_noart <name>  new track with NO mpris:artUrl at all
    partial             SAME track, but emit Metadata WITHOUT mpris:artUrl
    full                SAME track, re-emit complete Metadata
    notrackid           drop mpris:trackid from Metadata (Firefox does this
                        differently: it sends a CONSTANT trackid, see --static-trackid)
    status <s>          set PlaybackStatus to Playing/Paused
    quit                unregister and exit

--static-trackid makes mpris:trackid a fixed value regardless of track, which
is what Firefox actually does (verified: /org/mpris/MediaPlayer2/firefox), so
any track-identity logic must not rely on trackid varying.
"""
import argparse, os, sys
import dbus, dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

BUS = 'org.freedesktop.MediaPlayer2.fakeplayer'
IFACE = 'org.mpris.MediaPlayer2.Player'

ap = argparse.ArgumentParser()
ap.add_argument('--cmdfile', required=True)
ap.add_argument('--name', default='fakeplayer')
ap.add_argument('--static-trackid', action='store_true')
ap.add_argument('--art', default='/usr/share/icons/hicolor/48x48/apps/firefox.png')
args = ap.parse_args()


class Player(dbus.service.Object):
    def __init__(self, bus):
        super().__init__(bus, '/org/mpris/MediaPlayer2')
        self.title = 'Track One'
        self.n = 1
        self.status = 'Playing'
        self.send_art = True
        self.send_trackid = True

    # ---- metadata ----------------------------------------------------------
    def metadata(self):
        tid = ('/org/mpris/MediaPlayer2/fakeplayer' if args.static_trackid
               else f'/fake/track/{self.n}')
        md = {
            'xesam:title': dbus.String(self.title),
            'xesam:artist': dbus.Array(['Fake Artist'], signature='s'),
            'xesam:url': dbus.String(f'https://example.invalid/{self.n}'),
            'mpris:length': dbus.Int64(200_000_000),
        }
        if self.send_trackid:
            md['mpris:trackid'] = dbus.ObjectPath(tid)
        if self.send_art:
            md['mpris:artUrl'] = dbus.String('file://' + self.art_path())
        return dbus.Dictionary(md, signature='sv')

    def art_path(self):
        """A DIFFERENT art file per track when --art is a directory.

        Needed because mediaplayer.py short-circuits when the art url is
        unchanged, so a harness that reuses one path can never exercise the
        fade at all -- it silently tests nothing.
        """
        if os.path.isdir(args.art):
            files = sorted(f for f in os.listdir(args.art) if f.endswith('.png'))
            if files:
                return os.path.join(args.art, files[self.n % len(files)])
        return args.art

    def props(self, iface):
        if iface == 'org.mpris.MediaPlayer2':
            return {'Identity': args.name, 'CanQuit': False, 'CanRaise': False,
                    'HasTrackList': False, 'DesktopEntry': dbus.String('')}
        return {
            'PlaybackStatus': dbus.String(self.status),
            'Metadata': self.metadata(),
            'CanPlay': True, 'CanPause': True, 'CanGoNext': True,
            'CanGoPrevious': True, 'CanSeek': False, 'CanControl': True,
            'Position': dbus.Int64(0), 'Volume': dbus.Double(1.0),
            'Rate': dbus.Double(1.0), 'MinimumRate': dbus.Double(1.0),
            'MaximumRate': dbus.Double(1.0), 'Shuffle': False,
            'LoopStatus': dbus.String('None'),
        }

    @dbus.service.method('org.freedesktop.DBus.Properties',
                         in_signature='ss', out_signature='v')
    def Get(self, iface, prop):
        return self.props(iface).get(prop, '')

    @dbus.service.method('org.freedesktop.DBus.Properties',
                         in_signature='s', out_signature='a{sv}')
    def GetAll(self, iface):
        return self.props(iface)

    @dbus.service.signal('org.freedesktop.DBus.Properties',
                         signature='sa{sv}as')
    def PropertiesChanged(self, iface, changed, invalidated):
        pass

    # ---- control methods playerctl may call --------------------------------
    @dbus.service.method(IFACE)
    def Play(self):
        self.status = 'Playing'; self.emit_status()

    @dbus.service.method(IFACE)
    def Pause(self):
        self.status = 'Paused'; self.emit_status()

    @dbus.service.method(IFACE)
    def PlayPause(self):
        self.status = 'Paused' if self.status == 'Playing' else 'Playing'
        self.emit_status()

    # ---- emitters ----------------------------------------------------------
    def emit_metadata(self):
        self.PropertiesChanged(IFACE, {'Metadata': self.metadata()}, [])

    def emit_status(self):
        self.PropertiesChanged(IFACE, {'PlaybackStatus': dbus.String(self.status)}, [])


DBusGMainLoop(set_as_default=True)
bus = dbus.SessionBus()
name = dbus.service.BusName('org.mpris.MediaPlayer2.' + args.name, bus)
p = Player(bus)

log = lambda m: (sys.stderr.write(m + '\n'), sys.stderr.flush())
log(f'fakeplayer ready as org.mpris.MediaPlayer2.{args.name} '
    f'(static_trackid={args.static_trackid})')


def pump():
    """Read and execute any new commands, one per tick."""
    try:
        lines = open(args.cmdfile).read().split('\n')
    except OSError:
        return True
    done = pump.done
    for i, line in enumerate(lines):
        if i < done or not line.strip():
            continue
        pump.done = i + 1
        cmd, _, arg = line.strip().partition(' ')
        if cmd == 'track':
            p.n += 1; p.title = arg or f'Track {p.n}'
            p.send_art = True; p.send_trackid = True; p.emit_metadata()
        elif cmd == 'track_noart':
            p.n += 1; p.title = arg or f'Track {p.n}'
            p.send_art = False; p.send_trackid = True; p.emit_metadata()
        elif cmd == 'partial':
            p.send_art = False; p.emit_metadata()      # same track, art absent
        elif cmd == 'full':
            p.send_art = True; p.emit_metadata()
        elif cmd == 'notrackid':
            p.send_trackid = False; p.emit_metadata()
        elif cmd == 'status':
            p.status = arg or 'Playing'; p.emit_status()
        elif cmd == 'quit':
            log('quit'); loop.quit(); return False
        else:
            log(f'unknown command: {line!r}'); continue
        log(f'-> {line.strip()}')
        return True      # one command per tick, so the consumer sees each step
    return True


pump.done = 0
GLib.timeout_add(250, pump)
loop = GLib.MainLoop()
loop.run()
