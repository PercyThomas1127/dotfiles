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

- **A single OOM-killed app used to take down the entire desktop**, and the
  fix is `.config/systemd/user/wayland-wm@hyprland.desktop.service.d/oom.conf`.
  systemd's default `OOMPolicy=` for a service is **`stop`**: if any process in
  the unit is killed by the kernel OOM killer, systemd stops the whole unit —
  and the compositor, every autostart and every app launched from the session
  all live in `wayland-wm@hyprland.desktop.service`.

  Happened on 2026-09-15 19:17:29. RAM was exhausted (~8 MB free of 7.3 GB,
  2.03 GB **unevictable**, 2.09 GB shmem, kernel failing an *order-0*
  allocation inside `zswap_writeback_entry → shrink_slab`), and the OOM killer
  picked two **VS Code helper** processes of 32 MB and 11 MB — VS Code marks
  its children with `oom_score_adj=300`, making them first victims. systemd
  then stopped the unit, the session logged out, and the greeter came up.
  Reading it as "Hyprland crashed" is wrong and wastes time:
  - there was **no coredump and no Hyprland crash report**, because Hyprland
    was never the process that died;
  - `journalctl -b | grep -i 'oom'` finds it in one line:
    `wayland-wm@hyprland.desktop.service: The kernel OOM killer killed some
    processes in this unit`;
  - the end of the old session's `hyprland.log` shows only
    `SYN_DROPPED - some input events have been lost`, which is a *symptom* of
    the reclaim stall, not a cause.

  The unit also carries `OOMScoreAdjust=200` from uwsm, which makes everything
  in the session a **preferred** victim relative to system services. Left as-is
  for now.

- **Aftermath to check after any session teardown.** Orphans survive it and
  carry the dead `HYPRLAND_INSTANCE_SIGNATURE`, so they talk to the wrong
  compositor or fight the new session's copies:
  - `hyprwave` did **not** come back on its own; it needs starting by hand.
  - three `hyprwave-autohide` loops survived and ran alongside the new ones.
  - the dead session's log stays in `$XDG_RUNTIME_DIR`, which is **tmpfs, so it
    holds RAM** — 8 MB in that instance, on a machine that had just run out.
    `rm -rf $XDG_RUNTIME_DIR/hypr/<old-signature>` once nothing references it.

- **Hyprland's log is 99.5% libinput debug spam and there is no way to turn it
  off.** 65128 of 65440 lines in an 8 MB log; it grows ~2.7 MB/hour, or ~32 MB
  of RAM over a 12-hour session, because it lives in tmpfs. Checked and ruled
  out: `debug:disable_logs` is already `true` and does not suppress it (the
  lines come from **aquamarine**, not Hyprland's own logger), aquamarine
  exposes no log-level env var (only `AQ_DRM_DEVICES`, `AQ_NO_ATOMIC`,
  `AQ_NO_MODIFIERS`, `AQ_LIBINPUT_NO_PLUGINS`, `AQ_FORCE_LINEAR_BLIT`,
  `AQ_MGPU_NO_EXPLICIT`, `AQ_NO_KMS_REQUIREMENT`), and `Hyprland --help` has no
  log flag. Worth knowing because it **destroys the log history you need for
  anything else** — a real input/compositor bug scrolls out of the window fast.


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
  invisible — retaining that frame *is* the cleared state.

  **But the zombies did not disappear, they MOVED**, and the commit that made
  this change claimed otherwise. It said "zombies stay at 0" having measured
  only `waybar` zombies, never the `albumart-fade` animator it had just
  introduced — `_fade()` spawns it with `Popen` and never reaps, so they
  accumulated as `albumart-fade <defunct>` (3 observed at once). Fixed with
  `signal.signal(SIGCHLD, SIG_IGN)`, which makes the leak impossible rather
  than relying on remembering to reap. **When you remove one leak, count the
  thing you replaced it with.**

  **`has-art` must never control whether the pill is VISIBLE**, only its
  corner radius. Moving the background onto that class is what made the pill
  vanish on every track change: MPRIS senders routinely emit a new title with
  no `mpris:artUrl`, so the class dropped and the whole pill went with it.
  MEASURED from a `dbus-monitor` capture: **10 of 27** `Metadata` signals
  carried no `artUrl`, one of them a real Firefox track change, and the
  completing update followed **51–370 ms** later (median 251 ms, n=16).
  - `mpris:trackid` is **useless** as a track identity here: Firefox sends a
    constant `/org/mpris/MediaPlayer2/firefox` that does not change between
    tracks. Use `xesam:url`, falling back to `xesam:title`.
  - An absent `artUrl` is treated as *unknown*, not *gone*: `ART_PROBE_MS`
    (800 ms, just over 2x the worst gap observed) decides whether the track
    genuinely has no art, so a real art-less track still settles instead of
    pinning the previous cover.
  - `.config/waybar/scripts/tests/` has the harness that reproduces this on
    demand. The bug cannot be triggered by waiting for a player to misbehave,
    and a harness that reuses one art path silently tests nothing, because
    `_refresh_art` short-circuits when the url is unchanged. The image still
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
  `upstream` is `shantanubaddar/hyprwave`. Not the upstream build. Nine commits
  on top of upstream: the visualizer bars take their hue from the current album
  cover; GTK is no longer called from signal context (that was the crash that
  killed the bar on 2026-09-13); all five signals now arrive through a
  self-pipe, with two new ones added; and a 250ms keepalive timer, without
  which none of the signals arrive at all when the app is idle. The original upstream binary and data
  tree are backed up under `~/.local/share/hyprwave-backup-*/`, with a restore
  recipe in that directory.
  - **Signals are a self-pipe, and show/hide is idempotent.** Two things were
    wrong with upstream's signal handling, and `hyprwave-autohide` depends on
    both fixes:
    - **An idle main loop does not notice its own sources**, and the
      self-pipe did NOT fix this — only the 250ms keepalive did. MEASURED: a
      signal sat undispatched for **6.759s** with the process at 0% CPU in
      `poll()`, until some unrelated Wayland or D-Bus event woke the loop;
      with any periodic source attached, **0.002s**. That is why the autohide
      script looked like it did nothing, and it also made the hide look
      separately broken — `reveal_child` FALSE with `child_revealed` still
      TRUE 30s later reads like a stalled animation, when the handler had
      simply not run yet.

      **This invalidates the obvious test.** Signals work for a few seconds
      after a restart, because startup timers keep the loop turning, and stop
      working once the app settles. A fix verified right after launch will
      look correct and then "regress" hours later — which is exactly what
      happened here. Always test a settled instance. The clean demonstration:
      send a hide, watch nothing happen for 4s, then start any MPRIS player on
      the bus; the pending hide applies immediately.

      The keepalive is a **workaround** — a poll-based loop ought to wake on an
      fd in its own poll set, and the reason this one does not is unexplained.
      It costs nothing: idle CPU over 30s after a 30s settle was 2.80% with it,
      2.70% without, 2.63% with it again. Measure only settled instances;
      sampling 12s after startup gives 7-8% and is pure startup noise.
    - SIGUSR1 is a **blind toggle**, which cannot be reconciled against. A
      supervisor must then infer the current state, and its only readable proxy
      is the layer surface, which lags the ~300ms reveal animation. Pausing
      emits several MPRIS events in a row, so the supervisor re-entered
      mid-animation, read the stale surface and toggled twice — leaving the bar
      **inverted**, with play hiding it and pause showing it.

    So: `SIGRTMIN+3` = show, `SIGRTMIN+4` = hide, both idempotent, and the
    script asserts the state it wants without reading anything back.
    `SIGUSR1` still toggles, for `hyprwave-toggle`.

    - **Idempotent must mean "compare against reality", not "compare against a
      flag".** The first version of that setter returned early when its own
      `is_visible` boolean already matched the request. Something unmaps the
      window behind the app's back — seen across a 47-minute s2idle suspend —
      leaving `is_visible` TRUE with no surface, after which every assert-show
      returned early and **the bar was gone until the process was restarted**.
      A hide-then-show was the only manual recovery. It now compares the actual
      widgets, so a desync self-heals on the next heartbeat.

      Relatedly, `on_window_hide_complete` used to unmap purely because the
      revealer had collapsed. It fires on `notify::child-revealed` and re-reads
      the *current* value, so a show landing mid-animation could be clobbered
      by the collapse it had just reversed — instrumentation caught that window
      open for 155ms. It is now gated on `!is_visible`.

      The original trigger was never reproduced: DPMS off/on leaves the surface
      alone, and 40 randomised hide/show races found nothing. The fix targets
      recoverability instead, which is the property that actually matters. The other four handlers
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

    Measured on 2026-09-16, because a supervisor design depended on it: the
    second launch exits **0 with 0 bytes of stdout and 0 bytes of stderr** —
    completely silent — and the primary's `hyprwave-notification` layer
    surfaces went **1 → 2**, both owned by the primary's pid. So it is worse
    than a no-op *and* indistinguishable from success to anything watching
    exit status. That combination is why `hyprwave-launch` clears strays
    before exec'ing rather than trusting `Restart=` (which restarts on success
    too, so each cycle would graft another window onto a healthy instance).

- **hyprwave and hyprwave-autohide are systemd user units now**, not entries in
  `hyprland.lua`'s autostart chain:
  `~/.config/systemd/user/hyprwave.service` and `hyprwave-autohide.service`.
  Both are `WantedBy=` and `After=wayland-session@hyprland.desktop.target`.
  Manage with `systemctl --user {status,restart,stop} hyprwave`.

  **The bug they fix: autohide was SHOOTING hyprwave during its own startup.**
  `SIGRTMIN+3`/`+4` are real-time signals, and their default disposition is to
  *terminate* the target — unlike a segfault, **without a core dump**
  (`signal(7)`: "Term"). A process is signallable from `execve()` onward, i.e.
  during dynamic linking, before `main()` has installed anything.
  `hyprland.lua` launched hyprwave and autohide as simultaneous `&` siblings,
  and autohide's first action is `reconcile()`, which sends a hide. Whether the
  bar survived login was decided by the scheduler — hence "once in a while
  hyprwave wouldn't launch".

  Measured, sending `RTMIN+4` as soon as `pgrep` first saw the pid:
  **5 of 12 launches killed** (exit 166 = 128+38, stderr empty — dead before
  CSS even loads). With the readiness guard below: **0 of 12**, max wait 20ms.

  That is also why it went undiagnosed for so long. No core dump to find; no
  log line, because the `" & "` chain discards stdout, stderr *and* exit
  status for all 13 entries; and the killer was always still running while its
  victim was absent, so autohide looked like the innocent bystander that had
  merely failed to notice. Running hyprwave under systemd is what finally
  printed the answer:
  `hyprwave.service: Main process exited, code=killed, status=38/RTMIN+4`.

  Fixed at **both** ends, deliberately:
  - hyprwave installs its `sigaction` handlers at the top of `main()`
    (`install_signal_handlers()`), before `gtk_application_new`. Only the
    GSource attachment still waits for `activate()`, because `on_sig_pipe()`
    dispatches through `global_state`. Signals arriving in between are
    buffered in the self-pipe and drained on attach, so an early hide is
    applied *late* rather than fatally.
  - autohide (`signals_ready()`) refuses to signal a process whose
    `/proc/PID/status` `SigCgt` mask does not yet show `SIGRTMIN+4` (38)
    caught. That is the kernel's own answer, and it is race-free in the safe
    direction: the bit only ever goes unset→set, so observing it set means the
    signal cannot be fatal.

  **The in-process half cannot be sufficient by itself** — you cannot install a
  handler before your own first instruction runs — so the sender-side guard is
  the authoritative one. Do not remove it as an optimisation.

  What the units add on top:
  - **Ordering.** `wayland-session@.target` is itself
    `After=wayland-session-waitenv.service`, whose description is literally
    "Wait for WAYLAND_DISPLAY and other variables". On the failing boot
    `exec_cmd` fired at 07:58:18 and waitenv only finished at 07:58:19, so
    everything in that chain ran a second before the display was guaranteed.
    This also removes the dependence on `dbus-update-activation-environment`
    and `systemctl --user import-environment`, which were *themselves* racing
    siblings in the same chain; uwsm exports `WAYLAND_DISPLAY` and
    `HYPRLAND_INSTANCE_SIGNATURE` on its own (`systemctl --user
    show-environment`).
  - **`StartLimitIntervalSec=0`.** Not decoration: this box reports
    `DefaultStartLimitBurst=5`, so a stock `Restart=always` unit that failed
    five times quickly would enter `failed` and stay dead for the session —
    reproducing the original symptom with a unit to blame. Backoff
    (`RestartSec=1`, `RestartSteps`, `RestartMaxDelaySec=30`) is what keeps
    "retry forever" from meaning "hot loop".
  - **`OOMPolicy=continue`.** The default `stop` *stops* the unit when
    something in its cgroup is OOM-killed, and a unit systemd stopped is not
    one `Restart=` revives — exactly how the compositor came down on
    2026-09-15. This machine has 7.3 GiB and does OOM.
  - **A second recovery layer.** autohide's existing 10s heartbeat calls
    `systemctl --user start --no-block hyprwave.service` when `pgrep` finds
    nothing (throttled to 30s via a stamp in `$XDG_RUNTIME_DIR`). It goes
    through systemd precisely so there is still exactly **one** spawner — see
    the duplicate-bar measurement above. Verified: an explicit
    `systemctl stop` (which systemd will not itself undo) was recovered in 6s
    with one instance and no duplicate surfaces.
  - **Failure-only logging** to `~/.cache/hyprwave/last-failure.log`, written
    from `ExecStopPost` and capped at 400 lines. Gating on "stderr is
    non-empty" would not work — a *healthy* start emits four Gtk-WARNING theme
    parser lines. It logs when `SERVICE_RESULT != success`, or when a process
    that exited *on its own* (`EXIT_CODE=exited`) ran less than 5s, which is
    how the silent exit-0 case is caught. A systemd-initiated stop always
    reports `code=killed` and is never logged: without that clause, 15 rapid
    `systemctl restart` calls wrote 9 useless entries.
  - **`StandardOutput=null`.** hyprwave writes a per-frame animation trace to
    stdout (`TICK t=0.222 eased=0.044 req=258x63 ALLOC=258x64`, one line per
    frame). Measured over one 5s start: stdout 23 lines of chatter, stderr 8
    lines and nothing but diagnostics. Journalling stdout would mean disk
    writes every frame and buried the real error 40 lines deep the first time
    the log fired.
  - `hyprwave-autohide.service` needs **`KillSignal=SIGKILL` *and*
    `SuccessExitStatus=SIGKILL`**. `SIGTERM` does not stop that script — it
    lives blocked in `playerctl -a --follow status | while read`, and `sh`
    defers a trap until the current command finishes, which for that pipeline
    is never. Measured: `kill -TERM` left it running, and restarting it
    therefore *accumulated* instances (six processes across two copies at
    once). But `KillSignal=SIGKILL` alone makes every clean stop record
    "Failed with result 'signal'" and leave the unit `failed`, so the second
    directive is required to keep a normal logout from looking like a crash.

- **Two measurement traps cost real time on 2026-09-16; both produce a
  confident, wrong zero.**
  - `hyprctl layers` lines *end with the pid*
    (`..., namespace: hyprwave, pid: 37480`), so `grep 'namespace: hyprwave$'`
    never matches and reports the bar as absent while it is plainly on screen.
    Match `'namespace: hyprwave,'` — with the comma, which also excludes
    `hyprwave-notification`. This produced a whole false investigation into
    "show is broken"; the A/B against a pre-change build was identical, which
    is what exposed the instrument rather than the code.
  - `pactl list short source-outputs` **has no application-name column**, so
    grepping it for `hyprwave` cannot ever match. Count taps with
    `pactl list source-outputs | grep -c 'application.name = "HyprWave'`. The
    per-stream taps also report `Source: 4294967295`, which is correct — see
    the `pa_stream_set_monitor_stream` note.
  - Corollary, for both: when a detector says "zero", verify it against a
    state known to be non-zero before believing it.

- **`spotify_player` is a local patched build, and the patch is NOT backed up
  anywhere.** `~/.local/bin/spotify_player` is built from `~/Developer/spotify-player`,
  whose `origin` is **upstream** `aome510/spotify-player` — there is no fork of
  our own. The patch is one local commit, so a reclone, a hard reset or a
  `git pull --rebase` gone wrong loses it silently and the only symptom is that
  the media key feels sluggish again. If that matters, push it to a fork.
  - Built with
    `--no-default-features --features pulseaudio-backend,media-control,daemon`
    and installed stripped. Plain `cargo install` would pull the default
    features and a different backend. `daemon` was added so it can run headless
    (`spotify_player -d`) — the TUI needs a controlling terminal and refuses to
    start without one, and neither python's `pty.fork` nor `socat` would give
    it one, which made the state fix below impossible to test otherwise.
  - **What the patch does:** transport commands go straight to the local
    librespot `spirc` when playback is on this machine's own device, instead of
    out to the Web API. Every pause used to be a round trip to Spotify and
    back — MEASURED at **1507ms** and **1770ms** for one `Player(ResumePause)` —
    which is what made the media key feel like it had not registered.
  - It is **conditional on the active device id being ours**, and falls back to
    the Web API otherwise. That is not defensive padding: when playback is on a
    phone, a speaker or the web player, the Web API is the only way to reach it,
    and pausing our own idle device instead would silently do nothing.
  - **The audio stopping and the state being reported are two different
    problems.** Fixing the first left every MPRIS consumer — waybar's pause
    glyph, the hyprwave autohide script — showing "Playing" for ~1.6s after a
    local pause, because `media_control.rs` read the raw Web API snapshot
    rather than `buffered_playback`, the working copy that librespot's events
    and our own commands update instantly. Now ~0.2s.

    The same device test is load-bearing here too, in the opposite direction:
    `buffered_playback.is_playing` is only written for our own device, so for a
    remote one it would go stale forever. `retrieve_current_playback` adopts
    the API value into it for devices we do not drive, and deliberately not for
    ours, where the response is 1-3s old and would overwrite newer local state
    with older.
  - Separately, `client_id_command` in `.config/spotify-player/app.toml` is what
    stopped the `429`s; see the comments in that file. Both problems produced
    the same complaint ("it lags"), but they are unrelated — one was a shared
    API quota, the other a round trip.

- **`playerctl status` with no `-p` follows ONE arbitrary player**, and that
  silently broke `hyprwave-autohide` for a long time. Firefox registers an MPRIS
  player permanently once any tab has played media, and it sorts before
  `spotify_player`, so the script read *Firefox's* status: measured
  `playerctl -a status` printing `Paused\nPlaying` while plain
  `playerctl status` printed `Paused`. The bar stayed hidden through an entire
  album with no indication why. Use `playerctl -a status` and match any
  `Playing` line.
  - Worth knowing that hyprwave's own `preference = firefox,spotify,vlc` has
    the same shape of problem in reverse: with Firefox registered it *displays*
    Firefox even when Spotify is the one playing. That is a preference, not a
    bug — reorder it if the bar should favour Spotify.
  - Residual latency for the bar appearing is ~1.2s, and it is **not** in our
    code: hyprwave answers a signal in 0.022s and spotify_player's MPRIS
    property updates in 0.2s, but the D-Bus *change signal* that
    `playerctl --follow` waits for arrives ~1.0s late, which is souvlaki's
    1-second event cadence. `stdbuf -oL` makes no difference — it is not
    output buffering.

- **The visualizer has to FOLLOW the sink, not the default sink.** The waveform
  used to flatline the moment headphones were plugged in, and stay flat until
  they came out. hyprwave connected its capture stream once to
  `@DEFAULT_MONITOR@` and never moved.

  The reason is the audio graph on this machine: the speaker path is the
  `audio_effect.j313-convolver` *filter* sink (the speaker-protection
  convolver, which must never be bypassed) and the headphone jack is a separate
  real sink. Plugging in moves the playback streams to the headphone sink but
  leaves the **configured default sink still pointing at the convolver** — so
  the visualizer sat on a monitor with no audio on it, and restarting did not
  help because `@DEFAULT_MONITOR@` resolved to the same wrong sink.

  It now opens **one capture per playing sink-input**, restricted to that input
  with `pa_stream_set_monitor_stream()`, and **sums their energy**. Re-scans on
  `SINK_INPUT` / `SERVER` events.

  Summing is what removes the guesswork, and it is worth understanding why
  every simpler rule fails here:
  - the **default sink** is wrong, as above.
  - "the sink with the newest un-corked stream" works but is inference, and
    "any un-corked stream" picks wrong about half the time, because
    `speech-dispatcher-dummy` holds a permanently un-corked **silent** stream
    on the speaker path while Firefox sat *corked* on the headphone sink and
    spotify-player un-corked on it.
  - summed, a silent stream contributes exactly **zero energy**, so it needs no
    special case at all, and routing stops mattering because each stream is
    followed individually wherever it lands.

  Do **not** subscribe to `SINK` events; they fire on every volume tick.

  Per-stream is also cheaper, not just tidier: the idle speech-dispatcher
  source gets **zero** read callbacks and is skipped as stale, where a
  sink-wide capture had it delivering silence continuously. Amplitude is
  unaffected (`maxbin` 0.30-0.45 per-stream vs 0.22-0.44 sink-wide on the same
  track).

  **This samples PRE-DSP on the speaker path**, and that is a hard ceiling, not
  a shortcut: the convolver's monitor ports mirror its INPUT ports (verified
  with `pw-dump`) and its post-processing output node exposes no monitor at
  all, so the signal that actually reaches the speakers cannot be tapped.

  Useful commands: `pactl list source-outputs` shows what HyprWave is
  capturing, `pactl list sink-inputs` shows which sink each app plays to, and
  `pactl move-sink-input <id> <sink>` tests the following logic without
  touching hardware.

  **Rescans must be serialized, and must not depend on events.** Symptom: "the
  waveform only shows while pavucontrol is open." A rescan spans two async list
  queries — it clears `seen` at the start and acts on it at the end — so two in
  flight clobber each other's marks and the first to finish drops sources the
  other has not marked yet. Traced the same sink-input being dropped and
  instantly re-added, and every churn leaked a server-side stream, because a
  tap still in `PA_STREAM_CREATING` **cannot be disconnected**
  (`PA_ERR_BADSTATE`, rc `-15`) and only the unref releases it.

  The capture count reached **9 streams for 2 real inputs**, and
  `VIS_MAX_SOURCES` is **8** — so once the array filled, `add_source` refused
  to tap the music stream and the waveform went flat. pavucontrol
  continuously generates subscription events; the rescans those forced dropped
  the stale sources and freed a slot. Hence "only works while it is open".

  Fixed by serializing scans (a request arriving mid-scan is coalesced into one
  follow-up) **and** adding a 2s PulseAudio time event so the set is reconciled
  without needing an event at all. Use a PA time event, not a GLib timeout: it
  runs on the PA thread with the mainloop lock already held.
  - **The timer alone made it worse**, by making overlap more frequent. Both
    halves are needed; adding the watchdog without serializing pushed the
    capture count higher, not lower.
  - **History correction:** commit `d300046` says "serialize rescans, *and
    reconcile on a timer too*", and this entry described both — but only the
    serialization half actually shipped. The timer was lost to a
    `git checkout -- visualizer.c` used to clear instrumentation, and the
    commit message and this README were written as though it had survived. The
    capture set was therefore purely event-driven from `d300046` until
    2026-09-16, when the timer was restored (`reconcile_timer_cb`,
    `VIS_RECONCILE_INTERVAL_USEC`). Verified after restoring: 1 tap for 1
    playing stream held steady for 21s with no climb, and the tap was dropped
    cleanly when the stream ended.
  - Verified 8 of 8 pause/resume cycles with nothing else open, waveform alive
    every time and the count no longer climbing.

  **The bars are auto-gained, and that is load-bearing.** The waveform used to
  flicker on and off — looking like it jumped between zero and full — but only
  sometimes, which made it look like a timing bug. It was level. The bars were
  scaled by a hardcoded `* 10.0`, so the display depended on the ABSOLUTE
  signal level, and any bar below `h = 1/22` was snapped to **opacity 0** by a
  binary cliff, so it vanished outright instead of shrinking. Measured, same
  track, varying only the stream volume:

  | stream volume | frame peak | invisible bars |
  |---|---|---|
  | 100% | 0.774 | 0 / 55 |
  | 60% | 0.203 | 1.4 / 55 |
  | 30% | 0.019 | **55 / 55** |
  | 15% | 0.001 | **55 / 55** |

  It therefore "worked" whenever the audio happened to be loud. Now normalised
  against a peak that attacks instantly and releases over ~2s, with a floor
  that stops near-silence being amplified and a gate that lets the bars rest at
  zero, plus a 0.6 power curve to expand the low end. After: **zero** invisible
  bars at 100%, 50% and 20%.
  - A bigger fixed gain is the obvious fix and is wrong — it pins every bar at
    maximum on a loudly-mastered track. The range has to be adaptive.
  - `AGC_FLOOR` has to sit near the quietest level worth showing, not a typical
    one. The first attempt used `0.02` and still left 49 of 55 invisible at 30%.
  - This also answers a question left open by the per-stream change: a
    per-stream capture **does** include that stream's own volume.

  Two measurement traps, both of which fooled me:
  - "3 to 6 captures for 1 input" is **not** a leak — those are transient
    counts during churn plus stale server-side streams from hyprwave processes
    that were just killed. Compare at rest, and compare hyprwave's own count,
    not just `pactl`.
  - "the bars are frozen" can be a quiet passage: at `maxbin` around 0.15 the
    integer bar heights barely change. Compare amplitude at the same point of
    the same track.

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
