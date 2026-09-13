# dotfiles

Hyprland rice and configs for **Fedora Asahi Remix 44** on an **Apple Silicon MacBook Air (M1, 13")**.

Based on the [Balcony](https://github.com/1amSimp1e/dots/tree/balcony%F0%9F%9A%8A) rice by
[1amSimp1e](https://github.com/1amSimp1e), ported to Apple Silicon and to Hyprland's
new Lua config format.

## How this repo works

This is a **bare** git repository. The tracked files live where they normally
belong (`~/.config/hypr/…` and so on) — nothing is symlinked and nothing is
copied, so there is no way for the repo and the live config to drift apart.

The trade-off is that you don't use plain `git`. Use the `config` alias instead,
which is defined in the tracked `.bashrc`:

```bash
alias config='git --git-dir=$HOME/.dotfiles --work-tree=$HOME'
```

Day-to-day:

```bash
config status                            # only shows tracked files
config add .config/hypr/hyprland.lua
config commit -m "tweak blur passes"
config push
```

`status.showUntrackedFiles` is set to `no`, otherwise `config status` would try
to list your entire home directory.

## Restoring on a new machine

```bash
git clone --bare https://github.com/PercyThomas1127/dotfiles.git $HOME/.dotfiles
alias config='git --git-dir=$HOME/.dotfiles --work-tree=$HOME'
config config status.showUntrackedFiles no
config checkout          # will refuse if it would overwrite existing files
```

If `checkout` complains, move the offending files aside and run it again.

## What's here

| path | what |
|---|---|
| `.config/hypr/hyprland.lua` | the whole compositor config (ported from the rice's 259-line `hyprland.conf`) |
| `.config/hypr/hyprlock.conf`, `hypridle.conf`, `hyprpaper.conf` | lock screen, idle, wallpaper |
| `.config/hypr/scripts/` | volume / brightness / colour picker helpers |
| `.config/waybar/` | top bar: config, `style.css`, module scripts |
| `.config/dunst/` | notifications + the rice's icon assets |
| `.config/rofi/`, `.config/cava/`, `.config/kitty/` | launcher, audio visualiser, terminal |
| `.config/hyprwave/config.conf` | MPRIS music control bar |

## Dependencies

```bash
sudo dnf install waybar rofi dunst cava pamixer swaybg kitty mpvpaper \
                 hyprlock hypridle hyprpicker grim slurp \
                 playerctl brightnessctl jq fontawesome-fonts-all
```

Built from source into `~/.local/bin` (not packaged for Fedora):

- [hyprwave](https://github.com/shantanubaddar/hyprwave) — MPRIS music control bar

Fonts — **Nerd Fonts v3 or newer**, installed to `~/.local/share/fonts`:

```bash
for f in JetBrainsMono Iosevka; do
  curl -LO "https://github.com/ryanoasis/nerd-fonts/releases/download/v3.5.1/$f.zip"
  unzip -o "$f.zip" -d ~/.local/share/fonts/"$f"Nerd
done
fc-cache -fv
```

> The upstream rice pins Nerd Fonts v2.2.2. Don't. In v3 the Material Design
> icons moved from `U+F500–U+FD46` to `U+F0001+`, and the old range collides
> with real Unicode blocks — so v2 codepoints render as Tibetan and CJK
> characters. `waybar/config` here has been remapped to v3.

## Hardware-specific values

These differ from upstream because the rice was written for an Arch/Intel
laptop. If you reuse this on other hardware, these are the things to change:

| setting | value here | upstream |
|---|---|---|
| monitor | `2560x1600`, scale `1.6` | `1920x1080`, scale `1` |
| backlight device | `apple-panel-bl` | `intel_backlight` |
| keyboard backlight | `kbd_backlight` | `rgb:kbd_backlight` |
| battery | `macsmc-battery` | `BAT0` |
| lid switch | `Apple SMC power/lid events` | `Lid Switch` |
| `XDG_MENU_PREFIX` | `plasma-` (Fedora KDE) | `arch-` |
| brightness tool | `brightnessctl` | `brillo` + `light` |

Scale must divide the panel resolution evenly: `2560 / 1.6 = 1600`.

## Notes and gotchas

- **Log in via the `Hyprland (uwsm)` session.** The plain session never
  activates `graphical-session.target`, so `xdg-desktop-portal` fails and
  screen sharing and GTK file pickers silently break.
- **Blur is expensive here.** The rice's `size 13` / `passes 3` is heavy for
  the Asahi Mesa driver — an unblurred wallpaper renders at ~62 FPS where a
  blurred multi-layer one managed ~2. Lower values are commented in
  `hyprland.lua` if the desktop feels sluggish.
- **`.conf` is deprecated.** Hyprland loads `hyprland.lua` in preference to
  `hyprland.conf`, and `.conf` support is removed in 0.57. The old file is
  kept for reference only and is ignored.
- **The wallpaper is a looping video via `mpvpaper`**, not a static image.
  `~/Videos/cherry-blossom-wallpaper.mp4` — re-encoded from a 3840x2160 @60fps
  source down to 2560x1440 @15fps with the audio stripped (61MB → 7.4MB), which
  took decode from 2.90x to 11.19x realtime. There is **no hardware H.264
  decode** on this machine, so the source resolution mattered a lot.
  It costs a steady **~37% of one core** (~5% of 8). mpvpaper's `-p`/`-s`
  auto-pause flags are set but **do not work under Hyprland** — measured 37%
  visible vs 35% covered — because Hyprland keeps sending frame callbacks to
  the occluded background layer. Re-encode at 10fps or 1920 wide if battery
  matters more than smoothness.
  `swww` was evaluated and rejected: it caches every decoded frame, and the
  761-frame 4K GIF version of this wallpaper needed **23.5 GiB** of raw frames
  on a 7.3 GiB machine.
- **Do NOT "fix" the `!important` in hyprwave's stylesheet.**
  `~/.local/share/hyprwave/style.css` contains, in its `.no-transition` rule:
  ```css
  transition: none !important;
  animation:  none !important;
  ```
  GTK4 CSS does not support `!important` and rejects both declarations with
  *"Junk at end of value"*, so the rule never applies. That looks like an
  obvious bug — it is even commented "CRITICAL" upstream — but it is
  load-bearing *because* it is broken. hyprwave applies that class during its
  programmatic animations and does not reliably remove it, so making the rule
  work permanently disables its transitions and the bar renders frozen.
  Removing `!important` was tried on 2026-09-12 and had exactly that effect;
  the file is stock upstream and should stay that way.
  (The commit message on `c45c3a1` claims dropping `!important` "fixes it".
  That is wrong — this entry is the correction.)
- **Trackpad:** `clickfinger_behavior` is on and `tap_to_click` is off, so
  clicking is by finger count on a physical press — 1 left, 2 right, 3 middle.
  Without `clickfinger_behavior`, right-click only fires in the bottom-right
  corner and no context menu ever opens.
- **Right Cmd is the Compose key** (`kb_options = "compose:rwin"`), so it no
  longer acts as Super. Left Cmd still drives every `SUPER` bind.
- `hyprlock.conf` and `hyprpaper.conf` hardcode `/home/yijunchen`. Fix those
  before sharing this publicly.

## Credits

- [1amSimp1e/dots](https://github.com/1amSimp1e/dots) — Balcony rice
- [shantanubaddar/hyprwave](https://github.com/shantanubaddar/hyprwave)
- weather via [wttr.in](https://wttr.in)
