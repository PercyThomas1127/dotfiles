#!/usr/bin/env python3
import argparse
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

_last_art = None
_last_text = ''
_blank_id = None


def _art_url(player):
    try:
        md = player.props.metadata
        return str(md['mpris:artUrl']) if 'mpris:artUrl' in md.keys() else None
    except Exception:
        return None


def _fade(mode):
    """Kick off albumart-fade in its own session.

    start_new_session detaches it from this process group, so it survives
    being called back-to-back and is only ever cancelled by the next
    invocation -- which does it by explicit pid, never a pkill pattern.
    """
    try:
        subprocess.Popen([FADE, mode],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError:
        logger.exception('could not start %s %s', FADE, mode)


def _refresh_art(player):
    """Drive the cover transition, but only when the art actually changed.

    Deliberately NOT called from write_output: that runs on every marquee
    tick, several times a second, and restarting the animator at that rate
    would cost far more than the polling this replaces.
    """
    global _last_art
    art = _art_url(player) if player is not None else None
    if art == _last_art:
        return
    had_art = _last_art is not None
    _last_art = art

    if art is None:
        # Losing the cover used to need a full waybar RELOAD: the image module
        # never clears, so handed no path it kept drawing the last cover, and
        # only destroying the module released the pixbuf. The reload forked a
        # child waybar never reaped, so every closed tab leaked a zombie.
        #
        # It is unnecessary now. The pill's left end lives inside the PNG
        # rather than in #media's background, so a fully transparent frame is
        # genuinely invisible and fading to it is enough.
        if had_art:
            _fade('out')
    elif had_art:
        _fade('change')   # dip through transparent, so covers never crossfade
    else:
        _fade('in')


def _emit_fading(player_name, text):
    """Re-emit the current title with the `fading` class, keeping has-art.

    Cannot go through write_output: that re-derives has-art from the player,
    and the player is already gone by the time this runs, so it would report
    no-art and drop the pill background instantly -- the very cut the fade
    exists to avoid.
    """
    sys.stdout.write(json.dumps({
        'text': text,
        'tooltip': text,
        'class': ['custom-' + player_name, 'has-art', 'fading'],
        'alt': player_name,
    }) + '\n')
    sys.stdout.flush()


def _blank_output():
    """Emit empty text, ending the module, AFTER the fade has run."""
    global _blank_id
    _blank_id = None
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

    output = {'text': text,
              'tooltip': tooltip or text,
              # has-art/no-art drives the merged-pill styling: with art the
              # title squares off its left edge to butt against the image,
              # without it the title must stay a normal rounded pill.
              'class': ['custom-' + player.props.player_name,
                        'has-art' if _art_url(player) else 'no-art',
                        *extra_classes],
              'alt': player.props.player_name}

    sys.stdout.write(json.dumps(output) + '\n')
    sys.stdout.flush()


def on_play(player, status, manager):
    logger.info('Received new playback status')
    on_metadata(player, player.props.metadata, manager)


def on_metadata(player, metadata, manager):
    logger.info('Received new metadata')
    track_info = ''

    if player.props.player_name == 'spotify' and \
            'mpris:trackid' in metadata.keys() and \
            ':ad:' in player.props.metadata['mpris:trackid']:
        track_info = 'AD PLAYING'
    elif player.get_artist() != '' and player.get_title() != '':
        track_info = '{artist} - {title}'.format(artist=player.get_artist(),
                                                 title=player.get_title())
    else:
        track_info = player.get_title()

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
