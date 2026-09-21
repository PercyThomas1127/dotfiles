# .bashrc

# Source global definitions
if [ -f /etc/bashrc ]; then
    . /etc/bashrc
fi

# User specific environment
if ! [[ "$PATH" =~ "$HOME/.local/bin:$HOME/bin:" ]]; then
    PATH="$HOME/.local/bin:$HOME/bin:$PATH"
fi
export PATH
export EDITOR='vim'
export VISUAL='vim'

# systemctl's pager. Set it to the empty string to turn auto-paging off, or to
# a pager to use that one instead. Commented out, so systemd's default applies.
#export SYSTEMD_PAGER='vim'
export MANPAGER='vim -M +MANPAGER -'

# User specific aliases and functions
if [ -d ~/.bashrc.d ]; then
    for rc in ~/.bashrc.d/*; do
        if [ -f "$rc" ]; then
            . "$rc"
        fi
    done
fi
unset rc
export PATH=~/.npm-global/bin:$PATH

# Bare dotfiles repo (github.com/PercyThomas1127/dotfiles).
# Files stay where they live; use `config` instead of `git`.
alias config='git --git-dir=$HOME/.dotfiles --work-tree=$HOME'
alias sdi='sudo dnf install'
alias v='vim'

# Interactive-only: greeting, ANSI art, prompt.
#
# This MUST stay guarded. Unguarded, `bash -lc anything` wrote 61,039 bytes of
# ANSI art to stdout -- .bash_profile sources this file, so every
# non-interactive login shell got the art. That is the shape of bug that
# breaks tools which parse a login shell's output.
#
# The `cat` is also guarded on the file existing: ansi-art.ans is tracked in
# this repo, but a partial restore would otherwise print a `cat: No such file`
# on every single shell start.
if [[ $- == *i* ]]; then
    echo "Bash is ran on rainbows :D"
    [ -r "$HOME/ansi-art.ans" ] && cat "$HOME/ansi-art.ans"
    echo 'This is an Orbital Strike Cannon :3'

    # Prompt. Config lives in ~/.config/starship.toml (tracked here too).
    command -v starship >/dev/null && eval "$(starship init bash)"
fi
