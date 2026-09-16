#!/usr/bin/env python3
import argparse
import functools
import logging
import sys
import signal
import subprocess
import gi
import json
import os
import unicodedata
from pathlib import Path
gi.require_version('Playerctl', '2.0')
from gi.repository import Playerctl, GLib

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------- marquee ----
# waybar has no native scrolling text, so long titles are scrolled here by
# emitting a shifted window of the text on a GLib timer.
MAX_LENGTH = 44     # MUST match "max-length" in ~/.config/waybar/config
GAP        = '   '  # separator between loop repetitions
TICK_MS    = 250    # 4 cells/sec
HEAD_DWELL = 8      # ticks (~2s) held at the start of the title

# One state slot, deliberately: there is one GtkLabel, so there is one marquee.
# A module-level dict keeps the existing signal-handler signatures untouched.
_mq = {'body': '', 'prefix': '', 'player': None,
       'offset': 0, 'dwell': 0, 'source_id': None, 'last': None}


def _cells(ch):
    """Display width in cells. Character count is a bad proxy for pixel width:
    CJK and emoji are double-width, combining marks are zero-width."""
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ('W', 'F') else 1


def _width(s):
    return sum(_cells(c) for c in s)


def _take(s, start, budget):
    """Slice from `start` taking at most `budget` cells, then pad with spaces to
    exactly `budget` so the label width stays constant while scrolling."""
    out, used, i = [], 0, start
    while i < len(s) and used < budget:
        w = _cells(s[i])
        if used + w > budget:
            break
        out.append(s[i])
        used += w
        i += 1
    return ''.join(out) + ' ' * (budget - used)


def _window(prefix):
    # label budget, minus waybar's format prefix, minus our pause prefix,
    # minus 2 cells of slack for a wide glyph landing on the boundary.
    return MAX_LENGTH - 2 - _width(prefix) - 2


def _stop_marquee():
    if _mq['source_id'] is not None:
        GLib.source_remove(_mq['source_id'])
        _mq['source_id'] = None


def _emit(window):
    frame = _mq['prefix'] + window
    if frame == _mq['last']:
        return
    _mq['last'] = frame
    # tooltip carries the FULL untruncated text
    write_output(frame, _mq['player'], tooltip=_mq['prefix'] + _mq['body'])


def _on_tick():
    if _mq['source_id'] is None or _mq['player'] is None:
        return False
    if _mq['dwell'] > 0:
        _mq['dwell'] -= 1
        return True
    padded = _mq['body'] + GAP
    _mq['offset'] = (_mq['offset'] + 1) % len(padded)
    _emit(_take(padded + padded, _mq['offset'], _window(_mq['prefix'])))
    return True  # MUST be True; a bare return yields None and GLib drops the source


def _set_marquee(body, prefix, player):
    _mq['player'] = player
    # Idempotence guard. Players re-emit `metadata` for an unchanged track;
    # without this the offset resets on every emission and it never advances.
    if body == _mq['body'] and prefix == _mq['prefix']:
        return
    _stop_marquee()
    _mq.update(body=body, prefix=prefix, offset=0, dwell=HEAD_DWELL, last=None)
    if not body:
        write_output('', player)
        return
    w = _window(prefix)
    if _width(body) <= w:
        _emit(body)                    # fits: one write, no timer at all
        return
    if prefix:                         # paused: frozen head, no animation
        _emit(_take(body, 0, w - 1).rstrip() + '…')
        return
    _emit(_take(body, 0, w))
    _mq['source_id'] = GLib.timeout_add(TICK_MS, _on_tick)
# -----------------------------------------------------------------------------



# --------------------------------------------------------------- album art ---
# The artwork itself is drawn by waybar's own image module (see "image" in
# ~/.config/waybar/config), fed by scripts/albumart. This script's job is only
# to say WHEN it changed and WHETHER there is any, because it is already
# sitting on the MPRIS signals and waybar would otherwise have to poll.
ART_SIGNAL = 5      # MUST match "signal" in the image module's config

# The animator. It walks a pre-rendered alpha ramp, writing the current frame
# to a state file and signalling waybar once per frame, so the cover fades
# rather than cutting. Run detached: it sleeps for the length of the fade and
# must not block the MPRIS main loop, and it must outlive this call.
FADE = str(Path(__file__).with_name('albumart-fade'))

# Length of the cover fade. Keep in step with STEPS * DELAY in albumart-fade
# and with the opacity transition on #media #custom-spotify in style.css, so
# the two halves of the pill land together.
FADE_MS = 260

# How long to wait before believing that an absent mpris:artUrl means the track
# really has no art, rather than the update merely being partial.
#
# MEASURED from a dbus-monitor capture of real track changes: the completing
# update follows the art-less one by 51-370 ms (median 251 ms, n=16, Firefox).
# 800 ms is just over 2x the worst case observed -- enough headroom to not
# flip the class spuriously, short enough that a genuinely art-less track
# settles before anyone notices.
ART_PROBE_MS = 800

# How often the watchdog re-checks that waybar was told the truth.
WATCHDOG_S = 3

# Frame state lives in the runtime dir so it cannot outlive the boot; see the
# comment in albumart-fade. Clearing it here as well covers logging out and
# back in without rebooting, where the runtime dir can survive. Without it the
# image module's first exec of the new session would resolve a frame left over
# from the old one and paint a cover with no pill and no title behind it.
_RUN = Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp')) / 'waybar-albumart'


def _clear_frame_state():
    try:
        (_RUN / 'frame').write_text('')
    except OSError:
        pass

_last_art = None        # last CONFIRMED art url; None means confirmed art-less
_last_text = ''
_blank_id = None
_last_emit = None       # last payload written, for the watchdog below
_art_probe_id = None    # pending "is the art really absent?" re-check

# Sentinel for "this metadata carried no mpris:artUrl at all", which is NOT the
# same as "this track has no art".
_ART_MISSING = object()


def _art_url(player):
    """The art url, or `_ART_MISSING` when the key is absent entirely.

    The distinction is the whole bug. MPRIS senders emit a new title with NO
    mpris:artUrl partway through a track change -- MEASURED on this machine,
    10 of 27 captured Metadata signals, one of them a real Firefox track
    change. Collapsing that into None made it look like the art had gone, which
    faded the cover out and emitted `no-art`.
    """
    try:
        md = player.props.metadata
    except Exception:
        return _ART_MISSING
    try:
        if 'mpris:artUrl' not in md.keys():
            return _ART_MISSING
        return str(md['mpris:artUrl']) or None
    except Exception:
        return _ART_MISSING


def _track_identity(player):
    """Something stable that changes when the track does.

    Deliberately NOT mpris:trackid. Firefox sends a CONSTANT one --
    /org/mpris/MediaPlayer2/firefox, verified unchanged across a real track
    change -- so comparing trackids would treat every Firefox track change as
    the same track and pin the previous cover. xesam:url varies per track for
    both Firefox and spotify_player; title is the fallback.
    """
    try:
        md = player.props.metadata
        for key in ('xesam:url', 'xesam:title'):
            if key in md.keys():
                value = str(md[key])
                if value:
                    return value
    except Exception:
        pass
    return None


def _fade(mode):
    """Kick off albumart-fade in its own session.

    start_new_session detaches it from this process group, so it survives
    being called back-to-back and is only ever cancelled by the next
    invocation -- which does it by explicit pid, never a pkill pattern.
    """
    logger.info('fade: %s', mode)
    try:
        subprocess.Popen([FADE, mode],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError:
        logger.exception('could not start %s %s', FADE, mode)


def _apply_art(art):
    """Commit a CONFIRMED art state and drive the cover transition."""
    global _last_art
    if art == _last_art:
        return
    had_art = _last_art is not None
    _last_art = art

    if art is None:
        # Losing the cover used to need a full waybar RELOAD: the image module
        # never clears, so handed no path it kept drawing the last cover, and
        # only destroying the module released the pixbuf.
        #
        # It is unnecessary now. The pill's left end lives inside the PNG, so a
        # fully transparent frame is genuinely invisible and fading to it is
        # enough.
        if had_art:
            _fade('out')
    elif had_art:
        _fade('change')   # dip through transparent, so covers never crossfade
    else:
        _fade('in')

    # The class is derived from _last_art, so a change here has to reach
    # waybar even when the title did not change -- otherwise the marquee's
    # idempotence guard swallows it and the wrong class stands forever. That
    # is exactly how the pill's background went missing for a whole track.
    #
    # Deferred to idle on purpose: _refresh_art runs BEFORE _set_marquee, so
    # reconciling inline would emit the PREVIOUS track's text with the new
    # class. By the time idle runs the caller has finished and the marquee
    # state is current.
    _reconcile_soon()


def _cancel_art_probe():
    global _art_probe_id
    if _art_probe_id is not None:
        GLib.source_remove(_art_probe_id)
        _art_probe_id = None


def _art_probe(player, track):
    """Settle an absent artUrl: absent for the same track after a delay means
    the track genuinely has none, rather than the update merely being partial.
    """
    global _art_probe_id
    _art_probe_id = None
    if _track_identity(player) != track:
        return False          # moved on; a later event will settle it
    art = _art_url(player)
    _apply_art(None if art is _ART_MISSING else art)
    return False


def _refresh_art(player):
    """Drive the cover transition, but only when the art actually changed.

    Deliberately NOT called from write_output: that runs on every marquee
    tick, several times a second, and restarting the animator at that rate
    would cost far more than the polling this replaces.
    """
    if player is None:
        # The only caller that passes None is on_player_vanished, which is the
        # one case where art really is gone.
        _cancel_art_probe()
        _apply_art(None)
        return

    art = _art_url(player)
    if art is _ART_MISSING:
        # Absent, not gone. Do NOT fade out and do NOT flip the class; wait to
        # see whether the completing update brings art with it. A genuinely
        # art-less track settles when the probe fires.
        global _art_probe_id
        if _art_probe_id is None:
            _art_probe_id = GLib.timeout_add(
                ART_PROBE_MS, _art_probe, player, _track_identity(player))
        return

    _cancel_art_probe()
    _apply_art(art)


def _payload(text, player_name, has_art, tooltip='', extra_classes=()):
    """Build the module's JSON. THE only place classes and text are decided.

    There used to be three independent builders -- write_output, _emit_fading
    and _blank_output -- which is how _emit_fading ended up needing a comment
    explaining why it must not call write_output. One builder means one place
    to audit when this area changes again.

    `has_art` is passed in rather than read from the player, and callers pass
    the debounced `_last_art` state. Deriving it from a live
    `_art_url(player)` here was the bug: the fade decision and the CSS class
    were two separate reads of the same volatile property and could disagree.
    """
    return {
        'text': text,
        'tooltip': tooltip or text,
        # has-art squares the title's left edge to butt against the cover. It
        # no longer controls whether the pill has a background -- see the note
        # on `#media #custom-spotify` in style.css. Keep it that way.
        'class': ['custom-' + player_name,
                  'has-art' if has_art else 'no-art',
                  *extra_classes],
        'alt': player_name,
    }


def _write(payload):
    global _last_emit
    _last_emit = payload
    sys.stdout.write(json.dumps(payload) + '\n')
    sys.stdout.flush()


def _player_name(player):
    """The name, surviving a player that has already gone away."""
    try:
        name = player.props.player_name
        _mq['player_name'] = name
        return name
    except Exception:
        return _mq.get('player_name') or 'unknown'


def _emit_fading(player_name, text):
    """Re-emit the current title with the `fading` class, keeping has-art.

    has_art is forced True: the player is already gone by the time this runs,
    so asking it would report no-art and cut the pill instantly -- the very
    thing the fade exists to avoid.
    """
    _write(_payload(text, player_name, True, extra_classes=('fading',)))


def _blank_output():
    """Emit empty text, ending the module, AFTER the fade has run."""
    global _blank_id, _last_emit
    _blank_id = None
    _last_emit = None
    sys.stdout.write('\n')
    sys.stdout.flush()
    return False


def write_output(text, player, tooltip='', extra_classes=()):
    global _last_text, _blank_id
    logger.info('Writing output')
    _last_text = text

    # A fade-out may still be pending from a player that vanished moments ago.
    # Its timeout would blank whatever this call is about to emit, so a new
    # player appearing mid-fade cancels it.
    if _blank_id is not None:
        GLib.source_remove(_blank_id)
        _blank_id = None

    _write(_payload(text, _player_name(player), _last_art is not None,
                    tooltip, extra_classes))


def _reconcile_soon():
    """Reconcile once, after the current event finishes."""
    GLib.idle_add(lambda: (_watchdog(), False)[1])


def _watchdog():
    """Re-emit if what waybar was last told no longer matches our state.

    Everything in this script is event-driven, and waybar has
    `exec-on-event: false` and no `interval`, so a single wrong emission stands
    forever -- which is precisely how the pill's background stayed missing for
    an entire track. Every bug in this area so far has been state that went
    wrong with no way back, so assert it periodically as well as on events.

    Costs one dict comparison per tick; it emits only on a genuine difference,
    so the steady state is silent.
    """
    if _blank_id is not None:
        return True          # a fade-out is mid-flight; do not fight it
    if _mq['player'] is None or _mq['last'] is None or _last_emit is None:
        return True
    want = _payload(_mq['last'], _last_emit['alt'], _last_art is not None,
                    tooltip=_mq['prefix'] + _mq['body'])
    if want != _last_emit:
        logger.info('watchdog: output had drifted, re-asserting')
        _write(want)
    return True


def _guard(fn):
    """Stop one bad event from freezing the module forever.

    These run as GLib callbacks. An exception escaping one aborts the handler
    partway -- typically before the emit -- and because nothing re-polls this
    script, whatever was last written stands indefinitely. Log and carry on;
    the watchdog then repairs the output.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            logger.exception('%s failed; continuing', fn.__name__)
    return wrapper


@_guard
def on_play(player, status, manager):
    logger.info('Received new playback status')
    on_metadata(player, player.props.metadata, manager)


@_guard
def on_metadata(player, metadata, manager):
    logger.info('Received new metadata')
    track_info = ''

    # Index `metadata`, NOT player.props.metadata. The key was checked on the
    # signal payload but read from the live property, and if those disagree the
    # KeyError escapes into the GLib callback and aborts the handler BEFORE
    # _refresh_art and _set_marquee run -- freezing every bit of state with no
    # way back.
    if player.props.player_name == 'spotify' and \
            'mpris:trackid' in metadata.keys() and \
            ':ad:' in str(metadata['mpris:trackid']):
        track_info = 'AD PLAYING'
    else:
        # `or ''`: these getters return None, not '', when the field is absent,
        # so `!= ''` was true for None and the text could become "None - None".
        artist = player.get_artist() or ''
        title = player.get_title() or ''
        track_info = '{} - {}'.format(artist, title) if artist and title else title

    # The pause glyph is a PINNED prefix, not part of the scrolled string: a
    # status icon that scrolled off the edge and back would be bizarre, and
    # pinning it is what makes the width arithmetic exact.
    prefix = ' ' if (player.props.status != 'Playing' and track_info) else ''
    _refresh_art(player)
    _set_marquee(track_info, prefix, player)


def on_player_appeared(manager, player, selected_player=None):
    if player is not None and (selected_player is None or player.name == selected_player):
        init_player(manager, player)
    else:
        logger.debug("New player appeared, but it's not the selected player, skipping")


def on_player_vanished(manager, player):
    logger.info('Player has vanished')
    # Critical: without this the timer keeps firing against a dead player and
    # the module resurrects itself seconds after the player closed.
    _stop_marquee()
    # Read the name BEFORE _refresh_art: it is the last moment the vanished
    # player's properties are still readable.
    try:
        name = player.props.player_name
    except Exception:
        name = None
    # Clear the artwork too, or the last cover outlives the player.
    had_art = _last_art is not None
    _refresh_art(None)

    # Hiding is not transitionable: emit empty text now and the title half
    # vanishes instantly while the cover is still fading, so the two halves
    # come apart. Re-emit the SAME text with a `fading` class instead -- a
    # class change is a valid GTK transition trigger -- and only end the
    # module once the fade has finished.
    global _blank_id
    if had_art and _last_text and name:
        _emit_fading(name, _last_text)
        if _blank_id is not None:
            GLib.source_remove(_blank_id)
        _blank_id = GLib.timeout_add(FADE_MS + 60, _blank_output)
    else:
        _blank_output()
    _mq.update(body='', prefix='', player=None, offset=0, last=None)


def init_player(manager, name):
    logger.debug('Initialize player: {player}'.format(player=name.name))
    player = Playerctl.Player.new_from_name(name)
    player.connect('playback-status', on_play, manager)
    player.connect('metadata', on_metadata, manager)
    manager.manage_player(player)
    on_metadata(player, player.props.metadata, manager)


def signal_handler(sig, frame):
    logger.debug('Received signal to stop, exiting')
    _stop_marquee()
    sys.stdout.write('\n')
    sys.stdout.flush()
    # loop.quit()
    sys.exit(0)


def parse_arguments():
    parser = argparse.ArgumentParser()

    # Increase verbosity with every occurrence of -v
    parser.add_argument('-v', '--verbose', action='count', default=0)

    # Define for which player we're listening
    parser.add_argument('--player')

    return parser.parse_args()


def main():
    arguments = parse_arguments()

    # Initialize logging
    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG,
                        format='%(name)s %(levelname)s %(message)s')

    # Logging is set by default to WARN and higher.
    # With every occurrence of -v it's lowered by one
    logger.setLevel(max((3 - arguments.verbose) * 10, 0))

    # Log the sent command line arguments
    logger.debug('Arguments received {}'.format(vars(arguments)))

    manager = Playerctl.PlayerManager()
    loop = GLib.MainLoop()

    manager.connect('name-appeared', lambda *args: on_player_appeared(*args, arguments.player))
    manager.connect('player-vanished', on_player_vanished)

    _clear_frame_state()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)

    # Reap the fade animator automatically. _fade() spawns albumart-fade with
    # Popen and never waits, so they accumulated as `albumart-fade <defunct>`
    # -- MEASURED, 3 of them at once. The fade commit claimed "zombies stay at
    # 0", but that only ever measured WAYBAR zombies, never the animator it
    # had just introduced. SIG_IGN makes the leak impossible rather than
    # relying on remembering to reap.
    signal.signal(signal.SIGCHLD, signal.SIG_IGN)

    GLib.timeout_add_seconds(WATCHDOG_S, _watchdog)

    for player in manager.props.player_names:
        if arguments.player is not None and arguments.player != player.name:
            logger.debug('{player} is not the filtered player, skipping it'
                         .format(player=player.name)
                         )
            continue

        init_player(manager, player)

    loop.run()


if __name__ == '__main__':
    main()
