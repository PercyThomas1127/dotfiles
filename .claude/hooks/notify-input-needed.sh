#!/bin/sh
# Desktop notification when Claude Code wants my attention.
#
# Wired up from ~/.claude/settings.json for two hook events:
#   Notification  Claude needs permission, or the prompt has gone idle.
#   Stop          Claude finished its turn and is waiting for the next input.
#
# Claude Code feeds hooks a JSON object on stdin. Notification carries a
# .message; Stop does not, hence the defaults below. stdin is always read so
# the hook never leaves Claude Code writing into a closed pipe.

kind=${1:-Notification}
payload=$(cat)
msg=$(printf '%s' "$payload" | jq -r '.message // empty' 2>/dev/null)

case "$kind" in
    Stop)
        [ -n "$msg" ] || msg="Finished - waiting for you"
        # Times out like a normal notification; this one is informational.
        urgency=normal
        ;;
    *)
        [ -n "$msg" ] || msg="Needs your input"
        # dunst keeps critical notifications on screen until dismissed, which
        # is the point: this one is blocking real work.
        urgency=critical
        ;;
esac

# The stack tag makes a new notification replace the previous one instead of
# building a pile while I am away from the machine.
notify-send -a "Claude Code" -u "$urgency" -i dialog-question \
    -h string:x-dunst-stack-tag:claude-code \
    -- "Claude Code" "$msg"
