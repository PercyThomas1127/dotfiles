#!/usr/bin/env bash
# Install Hyprland + everything the dotfiles (~/.config/hypr, waybar, rofi, dunst, ...)
# expect, on Gentoo amd64 / systemd profile. Run as your user; it calls sudo.
# Safe to re-run. Every emerge uses --ask so you can review before anything builds.
set -euo pipefail

# --- 1. Overlays ---------------------------------------------------------------
# Hyprland is NOT in ::gentoo or ::guru. It lives in ::hyproverlay (needs gcc >= 15;
# you have 16). GURU provides nerdfonts, spotify-player, brightnessctl.
sudo emerge --ask --noreplace app-eselect/eselect-repository dev-vcs/git
sudo eselect repository enable hyproverlay guru
sudo emaint sync -r hyproverlay -r guru

# --- 2. Keywords (everything here is ~amd64 only) -------------------------------
sudo mkdir -p /etc/portage/package.accept_keywords /etc/portage/package.use /etc/portage/package.unmask
# /etc/portage/package.mask/guru masks all of GURU; unmask only what we use
# (own file, so the existing package.unmask/guru entry for lact is untouched).
sudo tee /etc/portage/package.unmask/hyprland >/dev/null <<'EOF'
media-fonts/nerdfonts::guru
media-sound/spotify-player::guru
EOF
sudo tee /etc/portage/package.accept_keywords/hyprland >/dev/null <<'EOF'
*/*::hyproverlay ~amd64
gui-apps/uwsm ~amd64
media-fonts/nerdfonts ~amd64
media-sound/spotify-player ~amd64
EOF

# --- 3. USE flags ----------------------------------------------------------------
sudo tee /etc/portage/package.use/hyprland >/dev/null <<'EOF'
# Your config logs in through uwsm (see README "Log in via the Hyprland (uwsm) session")
gui-wm/hyprland systemd uwsm
# Modules used in waybar/config: tray, network, pulseaudio, bluetooth, hyprland/*
gui-apps/waybar network pulseaudio tray mpris pipewire
# waybar[tray] -> libayatana-appindicator -> libdbusmenu[gtk3]
dev-libs/libdbusmenu gtk3
# gi.require_version('Playerctl') in waybar/scripts/mediaplayer.py (the music pill)
media-sound/playerctl introspection
x11-misc/dunst wayland
x11-misc/rofi wayland
# canberra-gtk-play, used by dunst/scripts/playNotificationSound.sh
media-libs/libcanberra gtk3
# Fonts the waybar/rofi/kitty/dunst configs ask for (Nerd Fonts v3)
media-fonts/nerdfonts jetbrainsmono iosevka
EOF

# --- 4. Packages -----------------------------------------------------------------
sudo emerge --ask --verbose --noreplace --changed-use \
    gui-wm/hyprland \
    gui-libs/xdg-desktop-portal-hyprland \
    gui-apps/uwsm \
    gui-apps/hyprlock gui-apps/hypridle gui-apps/hyprpicker gui-apps/hyprpaper \
    gui-apps/waybar \
    x11-misc/rofi \
    gui-apps/wmenu \
    x11-misc/dunst x11-libs/libnotify \
    gui-apps/swaybg \
    gui-apps/grim gui-apps/slurp gui-apps/wl-clipboard \
    media-sound/playerctl media-sound/pavucontrol \
    media-libs/libcanberra \
    media-gfx/imagemagick app-misc/jq net-misc/curl \
    dev-python/pygobject dev-python/requests \
    gnome-extra/nm-applet net-wireless/bluez \
    x11-terms/kitty app-shells/starship media-sound/cava \
    media-fonts/nerdfonts media-fonts/fontawesome \
    media-video/mpv gui-libs/gtk4-layer-shell   # build deps: libmpv for mpvpaper, gtk4-layer-shell for hyprwave

# --- 5. Optional (uncomment what you want) --------------------------------------
# sudo emerge --ask media-sound/spotify-player   # spotify-player config + waybar custom/spotify
# sudo emerge --ask kde-misc/kdeconnect          # autostarted by hyprland.lua; harmless if missing
# sudo emerge --ask sys-apps/flatpak && flatpak install flathub dev.vencord.Vesktop   # SUPER+SHIFT+D

# --- 6. Your own builds, from github.com/PercyThomas1127, into ~/.local/bin -----
# No sudo past this point. Sources live in ~/Developer, as the README expects.
mkdir -p ~/Developer ~/.local/bin
clone() { [ -d ~/Developer/"$2" ] || git clone "$1" ~/Developer/"$2"; }

# wlpause (Rust, no system deps)
clone https://github.com/PercyThomas1127/wlpause.git wlpause
( cd ~/Developer/wlpause && cargo build --release && install -Dm755 target/release/wlpause ~/.local/bin/wlpause )

# mpvpaper -- your fork, default branch fractional-scale (needs libmpv from step 4)
clone https://github.com/PercyThomas1127/mpvpaper.git mpvpaper
( cd ~/Developer/mpvpaper && { [ -d build ] || meson setup build --buildtype=release; } && ninja -C build \
    && install -Dm755 build/mpvpaper ~/.local/bin/mpvpaper )
[ -f ~/Videos/cherry-blossom-wallpaper.mp4 ] || echo "!! ~/Videos/cherry-blossom-wallpaper.mp4 is missing; mpvpaper will show nothing."

# hyprwave -- your PRIVATE fork (branch album-accent). Needs GitHub auth, e.g. a
# personal access token as the password, or `gh auth login`. hyprwave-autohide
# needs this fork: upstream has no SIGRTMIN+3/+4 handlers, and RTMIN+4 KILLS it.
if clone https://github.com/PercyThomas1127/hyprwave-album-accent.git hyprwave; then
    ( cd ~/Developer/hyprwave && git checkout album-accent \
        && { git remote get-url upstream >/dev/null 2>&1 || git remote add upstream https://github.com/shantanubaddar/hyprwave.git; } \
        && make )
    # First install only: lay down the data files (icons, themes, font). After
    # that, NEVER `make install` again -- it overwrites style.css (see README).
    if [ ! -d ~/.local/share/hyprwave ]; then
        ( cd ~/Developer/hyprwave && make install PREFIX="$HOME/.local" )
    else
        install -Dm755 ~/Developer/hyprwave/hyprwave ~/.local/bin/hyprwave
    fi
    systemctl --user daemon-reload
    systemctl --user enable hyprwave.service hyprwave-autohide.service
else
    echo "!! Could not clone hyprwave-album-accent (private). Authenticate and re-run."
fi

echo
echo "Done. Log out, and in SDDM pick the 'Hyprland (uwsm-managed)' session (NOT plain 'Hyprland')."
