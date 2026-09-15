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
    gives it, so it gets zero padding and zero margin, and the whole left end
    of the pill — colour, rounded corner, inset — is baked into the PNG.
  - **The image module's height cannot be set; it is derived.** `size` fits the
    image into a `size x size` box preserving aspect, so the rendered height is
    `size * H/W` of the canvas. The canvas is therefore `192x175`, not
    `192x152`: at `size: 48` that lands on **43.75 logical px**, which is what
    every pill in this bar actually measures. The cover itself stays 38 and is
    centred, so ~2.9px of pill colour bands it top and bottom.

    That 43.75 is worth spelling out, because guessing at it cost a lot of
    time. The title half does not *choose* its height — it fills what the group
    grants it, which is the bar (96 physical px) less `#media`'s 8.5px margins.
    Neither `min-height` nor padding changes it. An earlier attempt shrank the
    title half to 38 to match the image; that was backwards and would have left
    the media pill shorter than the weather and clock pills.

    Measure this with a **colour sentinel** rather than by inference: point the
    frame state at a solid `#FF00FF` canvas, give the pill rules throwaway
    colours, `grim` the screen and take bounding boxes. Reading the rendered
    file, or sweeping `size` and eyeballing, both produced nonsense. The
    sentinel gives image, title and weather all at `y 13..82` = 70 physical.

  **waybar's `image` module never releases its pixbuf.** Handed no path it
  keeps drawing the last cover it loaded. That used to be cleared by reloading
  waybar (`SIGUSR2`), because `#media` painted the pill background so an empty
  image still drew one — and that reload leaked a `waybar <defunct>` zombie
  every time (**15 accumulated in a single session**) and re-ran every module
  script, which is why `weather.py` had to be made resilient.

  **There is no reload any more.** The PNG paints its own end of the pill, so
  `#media` has no background and a fully transparent frame is genuinely
  invisible — retaining that frame *is* the cleared state. The image still
  occupies 48px when invisible, which is harmless only because `group/media`
  is alone in `modules-center`; adding another centre module would sit
  off-centre. Its width cannot be animated away: with `size: 48` waybar fits
  the image into a 48x48 box, so a landscape canvas always renders 48 wide.

  Fades come from two different mechanisms, deliberately:
  - **The cover** fades through eight pre-rendered alpha frames written by
    `scripts/albumart-fade`, which signals waybar per frame ~30ms apart.
    Verified that waybar does **not** coalesce signals at that spacing — 8 of 8
    produced an invocation. `scripts/albumart` is therefore only a state
    reader, ~2ms, because it runs once per frame; all the ImageMagick work is
    in the animator. Frames are built in ONE `magick` invocation (55ms against
    125ms for eight separate calls, bit-identical output).
  - **The title half** fades via CSS, because a class change *is* a valid GTK
    transition trigger: `mediaplayer.py` re-emits the text with a `fading`
    class and only blanks it after the transition, since hiding a module is
    not transitionable. `has-art` must be kept on that emit — the pill
    background hangs off it. This needs no Pango markup, so `escape: true` and
    the marquee's slice-then-escape ordering are untouched.

  On a track change the incoming cover is built **before** the dip, while the
  outgoing one is still displayed, so a slow art download cannot leave the pill
  empty. Two frame sets (`fa`/`fb`) alternate so both covers exist at once.

  The pill colour and radius are read from the `--pill-color` / `--pill-radius`
  marker comments in `style.css`, so the PNG cannot drift from the stylesheet
  and leave a seam at the join. One 1px seam remains at the join by
  construction — 48 logical px is 76.8 physical at this monitor's 1.6 scale, so
  it lands mid-pixel — but with both sides the same colour it blends between
  them and is invisible. A negative margin was tried and measured to have no
  effect: the gap is inside the image widget's own allocation.

  The frame state and the rendered frames live in **`$XDG_RUNTIME_DIR`**, not
  `~/.cache`, and only the composed-and-downloaded covers are cached. This is
  not tidiness: persisting "what is on screen now" meant logging out while a
  cover showed left a state file naming a valid frame, so the next login
  painted a stale cover with no pill and no title behind it.
  `mediaplayer.py` also clears the state at startup, which covers logging out
  and back in without a reboot.

  Track changes are pushed, not polled: `mediaplayer.py` sends `SIGRTMIN+5` to
  waybar when the art URL changes, and deliberately not from `write_output`,
  which runs on every marquee tick.

- **hyprwave is a local fork now**, at `~/Developer/hyprwave` (branch
  `album-accent`), pushed to the private repo
  `PercyThomas1127/hyprwave-album-accent` — deliberately NOT named
  `hyprwave`, so it cannot be mistaken for upstream. `origin` is that repo,
  `upstream` is `shantanubaddar/hyprwave`. Not the upstream build. Three commits
  on top of upstream: the visualizer bars take their hue from the current album
  cover; GTK is no longer called from signal context (that was the crash that
  killed the bar on 2026-09-13); and all five signals now arrive through a
  self-pipe, with two new ones added. The original upstream binary and data
  tree are backed up under `~/.local/share/hyprwave-backup-*/`, with a restore
  recipe in that directory.
  - **Signals are a self-pipe, and show/hide is idempotent.** Two things were
    wrong with upstream's signal handling, and `hyprwave-autohide` depends on
    both fixes:
    - `g_unix_signal_add` does **not wake an idle GLib main loop**. MEASURED: a
      SIGUSR1 sat undispatched for **6.759s**, with the process at 0% CPU in
      `poll()`, until some unrelated Wayland or D-Bus event woke the loop; with
      any periodic source attached the same signal dispatched in **0.002s**.
      That is why the autohide script looked like it did nothing. It also made
      the hide look separately broken — `reveal_child` FALSE with
      `child_revealed` still TRUE 30s later reads like a stalled animation,
      when in fact the handler had not run yet.
    - SIGUSR1 is a **blind toggle**, which cannot be reconciled against. A
      supervisor must then infer the current state, and its only readable proxy
      is the layer surface, which lags the ~300ms reveal animation. Pausing
      emits several MPRIS events in a row, so the supervisor re-entered
      mid-animation, read the stale surface and toggled twice — leaving the bar
      **inverted**, with play hiding it and pause showing it.

    So: `SIGRTMIN+3` = show, `SIGRTMIN+4` = hide, both idempotent, and the
    script asserts the state it wants without reading anything back.
    `SIGUSR1` still toggles, for `hyprwave-toggle`. The other four handlers
    were also still calling GTK (`handle_sigusr2`) or `g_idle_add` (the
    `SIGRTMIN` trio) from signal context — the same unsafety as the original
    crash — and all of them now go through the pipe.
  - **Never run `make install` for it.** It overwrites `style.css`,
    `style-layout.css`, all 12 icons, all 14 themes, the font (and runs
    `fc-cache`) and `hyprwave-toggle` — not just the binary. Install by hand:
    `install -Dm755 hyprwave ~/.local/bin/hyprwave`. None of the data files
    need to change.

    This rule got broken on 2026-09-15 (twice), so for the record: it did no
    damage, and the reason is worth knowing. All 28 overwritten files came back
    **byte-identical** to `hyprwave-backup-20260913-222137`, because the fork
    has never modified a data file — only `main.c`. The real risk is therefore
    losing local edits to those files, which do not currently exist; if you ever
    do customise `style.css` or a theme, the rule becomes load-bearing rather
    than precautionary. Verify with
    `diff -rq ~/.local/share/hyprwave-backup-*/share-hyprwave ~/.local/share/hyprwave`.
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

- **`spotify_player` is a local patched build, and the patch is NOT backed up
  anywhere.** `~/.local/bin/spotify_player` is built from `~/Developer/spotify-player`,
  whose `origin` is **upstream** `aome510/spotify-player` — there is no fork of
  our own. The patch is one local commit, so a reclone, a hard reset or a
  `git pull --rebase` gone wrong loses it silently and the only symptom is that
  the media key feels sluggish again. If that matters, push it to a fork.
  - Built with `--no-default-features --features pulseaudio-backend,media-control`
    and installed stripped. Plain `cargo install` would pull the default
    features and a different backend.
  - **What the patch does:** transport commands go straight to the local
    librespot `spirc` when playback is on this machine's own device, instead of
    out to the Web API. Every pause used to be a round trip to Spotify and
    back — MEASURED at **1507ms** and **1770ms** for one `Player(ResumePause)` —
    which is what made the media key feel like it had not registered.
  - It is **conditional on the active device id being ours**, and falls back to
    the Web API otherwise. That is not defensive padding: when playback is on a
    phone, a speaker or the web player, the Web API is the only way to reach it,
    and pausing our own idle device instead would silently do nothing.
  - Separately, `client_id_command` in `.config/spotify-player/app.toml` is what
    stopped the `429`s; see the comments in that file. Both problems produced
    the same complaint ("it lags"), but they are unrelated — one was a shared
    API quota, the other a round trip.

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
