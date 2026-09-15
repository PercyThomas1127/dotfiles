#!/usr/bin/env python3
import argparse
import logging
import sys
import signal
import subprocess
import gi
import json
import unicodedata
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

_last_art = None


def _art_url(player):
    try:
        md = player.props.metadata
        return str(md['mpris:artUrl']) if 'mpris:artUrl' in md.keys() else None
    except Exception:
        return None


def _refresh_art(player):
    """Tell waybar to re-read the artwork, but only when it actually changed.

    Deliberately NOT called from write_output: that runs on every marquee
    tick, several times a second, and firing pkill at that rate would cost
    far more than the polling this replaces.
    """
    global _last_art
    art = _art_url(player) if player is not None else None
    if art == _last_art:
        return
    had_art = _last_art is not None
    _last_art = art

    # -x matches the process name exactly throughout here. A bare pattern
    # would also match this script's own command line.
    if art is None and had_art:
        # Losing the artwork needs a RELOAD, not a refresh. waybar's image
        # module never clears: handed no path it just keeps drawing the last
        # cover it loaded, so closing a tab left the previous album sitting
        # there next to a collapsed pill. Nothing the script can emit fixes
        # it -- a transparent placeholder still occupies a sliver of pill.
        # Only destroying and recreating the module releases the pixbuf.
        #
        # Deliberately scoped to this one transition. It reloads the whole
        # bar, so it must not fire on ordinary track changes.
        subprocess.run(['pkill', '-SIGUSR2', '-x', 'waybar'], check=False)
    else:
        subprocess.run(['pkill', '-RTMIN+%d' % ART_SIGNAL, '-x', 'waybar'],
                       check=False)


def write_output(text, player, tooltip=''):
    logger.info('Writing output')

    output = {'text': text,
              'tooltip': tooltip or text,
              # has-art/no-art drives the merged-pill styling: with art the
              # title squares off its left edge to butt against the image,
              # without it the title must stay a normal rounded pill.
              'class': ['custom-' + player.props.player_name,
                        'has-art' if _art_url(player) else 'no-art'],
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
    # Clear the artwork too, or the last cover outlives the player.
    _refresh_art(None)
    _mq.update(body='', prefix='', player=None, offset=0, last=None)
    sys.stdout.write('\n')
    sys.stdout.flush()


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
