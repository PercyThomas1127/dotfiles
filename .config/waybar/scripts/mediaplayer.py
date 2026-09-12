#!/usr/bin/env python3
import argparse
import logging
import sys
import signal
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



def write_output(text, player, tooltip=''):
    logger.info('Writing output')

    output = {'text': text,
              'tooltip': tooltip or text,
              'class': 'custom-' + player.props.player_name,
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
