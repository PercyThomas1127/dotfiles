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

**This keyboard has no backlight keys.** The function row is display
brightness, not keyboard brightness — the `Apple SPI Keyboard` capability
bitmap advertises `BRIGHTNESSUP`/`BRIGHTNESSDOWN` but not
`KBDILLUMUP`/`KBDILLUMDOWN`, so any `XF86KbdBrightness*` bind is dead code on
the built-in keyboard no matter what it points at. Keyboard backlight is
therefore on **`SUPER` + the brightness keys**, handled by
`scripts/brightness up|down kbd`. The `XF86KbdBrightness*` binds are kept for
an external keyboard that does have those keys.

`brightnessctl` writes `kbd_backlight` through logind's D-Bus, so it works
unprivileged even though `/sys/class/leds/kbd_backlight/brightness` is
root-owned `0644`. No udev rule is needed; don't add one.

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
  source to **2560x1600 @15fps**, audio stripped (61MB → 13MB). There is **no
  hardware H.264 decode** on this machine, so source resolution matters a lot.
  2560x1600 is the panel's exact resolution, so the video is neither upscaled
  nor cropped at playback. Regenerate with:
  ```sh
  ffmpeg -i <source> -an -r 15 \
    -vf "crop=3456:2160,scale=2560:1600:flags=lanczos" \
    -c:v libx264 -crf 21 -preset medium -pix_fmt yuv420p out.mp4
  ```
  The crop takes the 16:9 source to 16:10 before scaling.
  **Don't "upgrade" this to 4K.** Measured while playing: 4K costs 60% of a
  core and 414MB resident, against 40% and 260MB here — and the panel is only
  2560x1600, so 55% of those pixels are decoded and thrown away. The memory is
  the real cost, because it is held even while the wallpaper is frozen, on a
  machine that already sits ~4GB into swap. There is no quality to gain:
  2560x1600 measures SSIM 0.961 / 38.0dB against a 4K source downscaled to
  this same panel (the previous 2560x1440 measured 32.7dB, which is what
  re-encoding actually fixed).
  Left alone it costs a steady **~40% of one core** (~5% of 8), forever.
  mpvpaper's own `-p`/`-a MAX` auto-pause **cannot work on a tiling
  compositor** and is deliberately not used: its two triggers are Wayland
  frame callbacks (Hyprland keeps sending them to a fully occluded background
  layer) and `zwlr_foreign_toplevel` state (tiled windows report neither
  `fullscreen` nor `maximized`). Measured 37% visible vs 35% covered, i.e. no
  saving at all.
  Pausing is instead handled by **`wlpause --freeze`** (`~/Developer/wlpause`,
  written for this problem), which measures how much of the output is actually
  covered and drives mpv over the IPC socket given by `input-ipc-server`.
  Measured while fully covered: **40% → 0%**, with wlpause itself at 0%.
  `--freeze` is what gets the last 10%: pausing mpv only stops *decoding*,
  while its video output keeps redrawing the same frame, so the process is
  also SIGSTOPped. It is resumed on exit and on any output change, so the
  wallpaper cannot get stuck frozen.
  Note the two settings are coupled: if you remove `input-ipc-server` from
  the mpvpaper line, wlpause has nothing to talk to and silently gives up
  after 30s.
  `swww` was evaluated and rejected: it caches every decoded frame, and the
  761-frame 4K GIF version of this wallpaper needed **23.5 GiB** of raw frames
  on a 7.3 GiB machine.
- **Lid, suspend, and the DCP.** Closing the lid does NOT suspend: logind is
  told to ignore the switch in `/etc/systemd/logind.conf.d/90-lid.conf`
  (outside this repo, it lives in `/etc`), so lid handling belongs entirely to
  `scripts/lid` via the Hyprland bind. On AC it blanks the panel with DPMS; on
  battery it suspends.
  This needs **kernel 7.1.13-402 or newer**. On 7.1.6-400 the display
  controller never reinitialised on resume — 9/9 cycles came back to a black
  screen needing a force power-off.
  **Do not diagnose a resume failure by grepping for `IOAVVideoInterface open
  failed`.** That line still appears on a perfectly good resume (3 times on
  the verified-working cycle) and `dcp_poweron() done` does not exist on this
  kernel at all, so the obvious greps both lie. The line that actually means
  success is:
  ```
  journalctl -b | grep 'dcp_set_power_state_req returned'
  # apple-dcp ...: dcp_set_power_state_req returned, 9930 ms remaining
  ```
  A large "ms remaining" means the controller came back fast (~70ms). No such
  line after a resume is the real failure.

- **The media pill is two waybar modules pretending to be one.** waybar cannot
  draw an image inside a custom module's text, so the album art is a separate
  `image` module grouped with `custom/spotify` as `group/media`. Three
  non-obvious constraints hold it together, each found by breaking it:
  - **`size` is not optional.** With it omitted the image is clamped to roughly
    16px whatever the file contains — a 36px and a 64px source both rendered at
    an identical 26 device px. `size` fits the image into a *square* box
    preserving aspect, which is why `scripts/albumart` centre-crops: a 16:9
    thumbnail left alone would render shorter than a square cover and the art
    height would jump between tracks.
  - **The background belongs on the group, the padding on the children.**
    Background on the children leaves an empty styled stub where the image
    would be when a player exposes no artwork; padding on the group leaves a
    bare pill floating at bar centre when nothing is playing at all.
  - **The `image` module never hides.** An empty one still paints any box CSS
    gives it, so it gets zero padding and zero margin, and the art's left inset
    is baked into the PNG as transparent pixels instead. The canvas is
    `(art + inset) x art`, so `size` must equal art + inset — currently
    `38 + 10 = 48`.

  Track changes are pushed, not polled: `mediaplayer.py` sends `SIGRTMIN+5` to
  waybar when the art URL changes, and deliberately not from `write_output`,
  which runs on every marquee tick.

- **hyprwave is a local fork now**, at `~/Developer/hyprwave` (branch
  `album-accent`), pushed to the private repo
  `PercyThomas1127/hyprwave` — `origin` is that fork, `upstream` is
  `shantanubaddar/hyprwave`. Not the upstream build. Two commits on top of upstream: the
  visualizer bars take their hue from the current album cover, and the SIGUSR1
  handler no longer calls GTK from a signal handler (that was the crash that
  killed the bar on 2026-09-13). The original upstream binary and data tree are
  backed up under `~/.local/share/hyprwave-backup-*/`, with a restore recipe in
  that directory.
  - **Never run `make install` for it.** It overwrites `style.css`,
    `style-layout.css`, all 12 icons, all 14 themes, the font (and runs
    `fc-cache`) and `hyprwave-toggle` — not just the binary. Install by hand:
    `install -Dm755 hyprwave ~/.local/bin/hyprwave`. None of the data files
    need to change.
  - **The visualizer colour is NOT in the stylesheet.** `.visualizer-bar` there
    is only the *template*: the accent is applied at runtime by a second
    `GtkCssProvider` at `PRIORITY_USER + 1`, because `load_css()` installs the
    theme at `PRIORITY_USER` and anything lower loads fine and silently never
    shows. Editing `style.css` still sets the fallback colour and the
    saturation/lightness the tint reuses.
  - **Launching hyprwave while it is already running does NOT no-op** — it is a
    GtkApplication, so the second launch activates the first instance, whose
    handler builds *another* bar. You get a duplicate pill stacked on the
    working one. Kill the old instance first. This is upstream behaviour, not
    something the fork introduced.

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
