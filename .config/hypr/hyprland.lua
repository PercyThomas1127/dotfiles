-- Hyprland Lua config -- "Balcony" rice by 1amSimp1e, ported to this machine and recolored to match the panel. The rice is a complete Hyprland config, not just a theme.
--   rice:    github.com/1amSimp1e/dots  (branch: balcony)
--   machine: Fedora Asahi Remix 44, Apple Silicon MacBook Air (M1, 13")
--
-- The upstream rice ships hyprland.conf. Hyprland loads hyprland.lua in
-- preference to hyprland.conf, and .conf support is removed in 0.57, so its
-- 259 lines were translated into the Lua API here rather than copied.
-- Hardware-specific values were corrected; see the notes inline.


------------------
---- MONITORS ----
------------------

-- The rice hardcodes "eDP-1,1920x1080@60,0x0,1" for the author's panel.
-- This machine is 2560x1600; scale must divide it evenly (2560/1.6 = 1600).
hl.monitor({
    output   = "",
    mode     = "preferred",
    position = "auto",
    scale    = "1.6",
})


---------------------
---- MY PROGRAMS ----
---------------------

local terminal    = "konsole"
local fileManager = "dolphin"
local menu        = "wmenu-run"
local browser     = "firefox"
local editor      = "code"
-- Vesktop is installed as a Flatpak (dev.vencord.Vesktop); there is no native
-- binary on PATH, so the bare name would not launch.
local chat        = "flatpak run dev.vencord.Vesktop"
-- Same command as waybar's launcher button (waybar/config on-click), so the
-- keybind and the button behave identically rather than adding a fourth
-- launcher look. ~/.config/rofi/config.rasi enables drun,run,filebrowser,window
-- so Tab cycles apps / commands / files / open windows from one prompt.
local appFinder   = "rofi -show drun"

-------------------
---- AUTOSTART ----
-------------------

-- From the rice: waybar, dunst, wallpaper, dbus/systemd env import.
-- Dropped (not installed / not applicable here):
--   fcitx5           -- input method, not installed
--   blueman-applet   -- not installed
--   startpage.sh     -- serves ~/Developer/Bento, which does not exist
--   screensharing.sh -- killalls the portals and restarts them by hand;
--                       Hyprland + xdg-desktop-portal-hyprland handle this
--                       via systemd now, so it does more harm than good.
-- Wallpaper: the rice calls swaybg; mpvpaper is used instead so the wallpaper
-- can be a looping video. Source was 3840x2160 @60fps H.264 High -- there is
-- NO hardware H.264 decode here (the installed VAAPI drivers are all
-- AMD/NVIDIA/virtio), so it is re-encoded to the panel's exact resolution,
-- 2560x1600 @15fps, audio stripped: 61MB -> 13MB. Regenerate with:
--   ffmpeg -i <source> -an -r 15 -vf "crop=3456:2160,scale=2560:1600:flags=lanczos" \
--          -c:v libx264 -crf 21 -preset medium -pix_fmt yuv420p out.mp4
-- The crop takes the 16:9 source to 16:10 before scaling, so the result is
-- 1:1 with the panel and is neither upscaled nor cropped at playback.
-- DO NOT "upgrade" this to 4K. Measured while playing: 4K costs 60% of a
-- core and 414MB resident versus 40% and 260MB here, and the panel is only
-- 2560x1600 so 55% of those pixels are thrown away. The memory is the real
-- cost -- it is held even while frozen, on a machine that already runs ~4GB
-- into swap. Quality gain is nil: 2560x1600 measures SSIM 0.961 / 38.0dB
-- against 4K downscaled to this same panel.
-- mpvpaper's own -p/-a MAX auto-pause is DELIBERATELY NOT USED: it cannot
-- work on a tiling compositor. Its two triggers are Wayland frame callbacks
-- (Hyprland keeps sending them to a fully covered background layer) and
-- zwlr_foreign_toplevel state (tiled windows report neither "fullscreen" nor
-- "maximized"). Measured: 37% of a core visible vs 35% covered, i.e. no
-- saving at all. Pausing is handled by wlpause below instead; leaving the
-- flags on as well would mean two things writing mpv's pause property.
--   input-ipc-server  the socket wlpause drives. It also lets wlpause find
--                     the socket on its own, by reading this command line.
--   panscan=1.0  a no-op now that the video is encoded at the panel's own
--                16:10 aspect, but kept so that a 16:9 replacement fills the
--                screen instead of showing letterbox bars.
--   hwdec=no   no working VAAPI driver, so don't waste startup failing over.
-- swww was considered and rejected: it caches every decoded frame, and the
-- 761-frame 4K GIF version needed 23.5 GiB of raw frames on a 7.3 GiB machine.
hl.on("hyprland.start", function ()
  hl.exec_cmd(table.concat({
    "waybar",
    "dunst",
    "mpvpaper -f -o 'no-audio loop-file=inf panscan=1.0 hwdec=no "
        .. "input-ipc-server=/tmp/mpvsocket' '*' "
        .. os.getenv("HOME") .. "/Videos/cherry-blossom-wallpaper.mp4",
    -- Pauses the wallpaper whenever it is actually covered, measuring real
    -- geometric coverage of the output rather than just counting windows, so
    -- a small floating window does not freeze a wallpaper you can still see.
    -- Written for this problem; see ~/Developer/wlpause.
    --   --freeze  also SIGSTOPs mpvpaper while hidden. Pausing mpv alone only
    --             stops DECODING; its video output keeps redrawing the same
    --             frame because Hyprland keeps handing it frame callbacks.
    --             Measured fully covered: 40% of a core with no pauser, 10%
    --             paused, 0% frozen. It is resumed on exit, and on any change
    --             to the set of outputs, so a frozen wallpaper cannot get
    --             stuck. Absolute path: Hyprland's exec does not reliably
    --             inherit the login PATH.
    os.getenv("HOME") .. "/.local/bin/wlpause --freeze",
    -- NOTE: hyprwave and hyprwave-autohide used to be two entries HERE, and
    -- were moved to systemd user units on 2026-09-16:
    --   ~/.config/systemd/user/hyprwave.service
    --   ~/.config/systemd/user/hyprwave-autohide.service
    -- Start/stop them with `systemctl --user {start,stop,status} hyprwave`.
    --
    -- They were moved because being entries in this list is what broke them.
    -- Everything below is joined with " & ": 13 commands launched at once,
    -- in no order, with exit status, stdout and stderr all discarded.
    --
    -- hyprwave intermittently did not come up at all, for an entire session,
    -- with nothing in any log. The cause was the two of them being SIBLINGS:
    -- autohide's first action is to send hyprwave SIGRTMIN+4 (hide), the
    -- default disposition of a real-time signal is to TERMINATE -- and to do
    -- it without a core dump -- and a process is signallable from execve()
    -- onward, before its own main() has installed any handler. So autohide
    -- shot hyprwave during startup, often enough to notice and rarely enough
    -- to look random. MEASURED: signalling as soon as pgrep saw the pid
    -- killed 5 of 12 launches. Nothing was logged because of the discarding
    -- above; there was no core dump to find either.
    --
    -- Both ends are now fixed (handlers installed first thing in main(), and
    -- autohide checks /proc/PID/status SigCgt before signalling), so this is
    -- no longer load-bearing -- but the units also give ordering after
    -- wayland-session@.target, a restart if either dies, and a real place for
    -- failures to be recorded. Do not move them back here.
    "dbus-update-activation-environment --systemd WAYLAND_DISPLAY XDG_CURRENT_DESKTOP",
    "systemctl --user import-environment WAYLAND_DISPLAY XDG_CURRENT_DESKTOP",
    -- kept from the previous setup: these are unrelated to the rice
    "hypridle",
    "kwalletd6",
    "kdeconnectd",
    "kdeconnect-indicator",
    "/usr/libexec/kf6/polkit-kde-authentication-agent-1",
    "XDG_MENU_PREFIX=plasma- kbuildsycoca6",
  }, " & "))
end)


-------------------------------
---- ENVIRONMENT VARIABLES ----
-------------------------------

hl.env("XCURSOR_THEME", "breeze_cursors")
hl.env("XCURSOR_SIZE", "24")
hl.env("HYPRCURSOR_SIZE", "24")

-- Qt apps (dolphin, konsole, the portal file dialog) otherwise fall back to
-- Qt's built-in Fusion look and ignore the configured Breeze Dark scheme.
-- NOTE: this only covers apps Hyprland launches. xdg-desktop-portal-kde is
-- D-Bus activated by systemd, so it needs the same variable in
-- ~/.config/environment.d/10-qt-theme.conf -- setting it here is not enough.
hl.env("QT_QPA_PLATFORMTHEME", "kde")


-----------------------
---- LOOK AND FEEL ----
-----------------------

hl.config({
    general = {
        layout      = "dwindle",
        gaps_in     = 11.8,
        gaps_out    = 15.5,
        border_size = 2,

        col = {
            active_border   = "0xff5e81ac",  -- nord blue
            inactive_border = "0x66333333",
        },
    },

    decoration = {
        rounding = 19,

        -- Software night-light. apple-drm exposes CTM but no GAMMA_LUT, so
        -- wlr-gamma-control (gammastep/hyprsunset/wlsunset) cannot work at all
        -- on this panel. Tint at composite time instead. Added 2026-09-18.
        -- screen_shader = "/home/yijunchen/.config/hypr/shaders/nightlight.frag",  -- disabled 2026-09-18; uncomment to re-enable

        -- PERFORMANCE WARNING (this machine specifically):
        -- These are the rice's values. size 13 x 3 passes is very heavy blur.
        -- The Asahi Mesa driver on this M1 already showed it struggles with
        -- multi-pass blur -- a blurred multi-layer wallpaper scene ran at ~2 FPS
        -- against ~62 FPS unblurred. If the desktop feels sluggish, swap in
        -- the commented values below; they keep the look and cost far less.
        blur = {
            enabled           = true,
            size              = 13,
            passes            = 3,
            new_optimizations = true,
            -- size   = 4,
            -- passes = 2,
        },

        shadow = {
            enabled        = true,
            range          = 30,
            color          = 0xffa7caff,
            color_inactive = 0x50000000,
        },
    },

    animations = {
        enabled = true,
    },

    -- dwindle.pseudotile was removed in Hyprland 0.56; SUPER+P (hl.dsp.window.pseudo)
    -- is the per-window equivalent and is bound below.
    dwindle = {
        force_split = 0,
    },

    master = {
        new_on_top = true,
    },

    misc = {
        disable_hyprland_logo    = false,
        disable_splash_rendering = false,
        mouse_move_enables_dpms  = true,
        -- Was unset (false), so only trackpad movement woke a DPMS-off display
        -- and a keystroke did nothing.
        key_press_enables_dpms   = true,
        -- misc.vfr was removed in Hyprland 0.56 (VFR is handled automatically now).
    },
})

-- The rice's animation set: one custom bezier, four animations.
hl.curve("overshot", { type = "bezier", points = { {0.13, 0.99}, {0.29, 1.1} } })

hl.animation({ leaf = "windows",    enabled = true, speed = 4,   bezier = "overshot", style = "slide" })
hl.animation({ leaf = "fade",       enabled = true, speed = 10,  bezier = "default" })
hl.animation({ leaf = "workspaces", enabled = true, speed = 8.8, bezier = "overshot", style = "slide" })
hl.animation({ leaf = "border",     enabled = true, speed = 14,  bezier = "default" })

-- Layer surfaces (waybar, hyprwave, mpvpaper). The rice never set these, so
-- they inherited defaults and came in with a different feel from how they
-- went out. Setting In and Out identically makes it symmetric. speed is in
-- units of ~100ms, so 4 roughly matches hyprwave's own ~400ms hide.
hl.animation({ leaf = "layersIn",  enabled = true, speed = 4, bezier = "default", style = "fade" })
hl.animation({ leaf = "layersOut", enabled = true, speed = 4, bezier = "default", style = "fade" })


-- Rice had "blurls=waybar" -- blur behind the bar.
hl.layer_rule({
    name  = "blur-waybar",
    match = { namespace = "^waybar$" },
    blur  = true,
})


---------------
---- INPUT ----
---------------

-- Input is deliberately NOT the rice's. These are your own pre-rice settings:
-- the rice sets natural_scroll = false and force_no_accel = true, both of which
-- feel wrong on a MacBook trackpad. force_no_accel in particular disables
-- pointer acceleration entirely.
hl.config({
    input = {
        kb_layout  = "us",
        kb_variant = "",
        kb_model   = "",
        -- Right Super (right Cmd) acts as the Compose key.
        -- Left Super still drives all the SUPER binds.
        kb_options = "compose:rwin",
        kb_rules   = "",

        follow_mouse = 1,

        sensitivity = 0, -- -1.0 - 1.0, 0 means no modification.

        touchpad = {
            natural_scroll       = true,
            disable_while_typing = false,
            -- This trackpad is a clickpad (one physical button). Without
            -- clickfinger_behavior, libinput uses "button areas": right-click
            -- only fires when you press the bottom-right CORNER, so a
            -- two-finger press (the macOS reflex) registers as a left click
            -- and no context menu ever opens.
            -- With it on: 1 finger = left, 2 = right, 3 = middle, anywhere.
            clickfinger_behavior = true,
            -- Physical presses only; light taps do nothing. Combined with
            -- clickfinger_behavior above, that means press with 1 finger for
            -- left, 2 for right, 3 for middle.
            -- (Note: hyprctl reports this as "tap-to-click", but the Lua
            -- config key is tap_to_click -- the hyphenated form is rejected.)
            tap_to_click = false,
        },
    },
})

hl.gesture({
    fingers   = 3,
    direction = "horizontal",
    action    = "workspace",
})


--------------------------------
---- WINDOWS AND WORKSPACES ----
--------------------------------

hl.window_rule({ name = "float-rofi",        match = { class = "(?i)rofi" },      float = true })
hl.window_rule({ name = "float-pavucontrol", match = { class = "pavucontrol" },   float = true })

hl.window_rule({ name = "size-float-kitty",  match = { title = "^(float_kitty)$" },  size  = "800 500" })
hl.window_rule({ name = "float-full-kitty",  match = { title = "^(full_kitty)$" },   float = true })
hl.window_rule({ name = "float-fly-kitty",   match = { title = "^(fly_is_kitty)$" }, float = true })

hl.window_rule({ name = "float-brave-save",  match = { class = "^(brave)$",   title = "^(Save File)$" },          float = true })
hl.window_rule({ name = "float-brave-open",  match = { class = "^(brave)$",   title = "^(Open File)$" },          float = true })
hl.window_rule({ name = "float-firefox-pip", match = { class = "^(firefox)$", title = "^(Picture-in-Picture)$" }, float = true })
hl.window_rule({ name = "float-blueman",     match = { class = "^(blueman-manager)$" },        float = true })
hl.window_rule({ name = "float-iwgtk",       match = { class = "^(org.twosheds.iwgtk)$" },     float = true })
hl.window_rule({ name = "float-blueberry",   match = { class = "^(blueberry.py)$" },           float = true })
hl.window_rule({ name = "float-portal-gtk",  match = { class = "^(xdg-desktop-portal-gtk)$" }, float = true })
hl.window_rule({ name = "float-geeqie",      match = { class = "^(geeqie)$" },                 float = true })
hl.window_rule({ name = "tile-neovide",      match = { class = "^(neovide)$" },                float = false })

-- Xwayland Video Bridge (KDE helper that lets X11 apps screen-share on Wayland).
-- It is started by /etc/xdg/autostart/org.kde.xwaylandvideobridge.desktop, which
-- only began running once uwsm activated graphical-session.target. It is meant to
-- be an invisible 1x1 helper, but with no rules it tiles as a large black window.
-- These are the rules the project documents for Hyprland.
hl.window_rule({
    name  = "hide-xwaylandvideobridge",
    match = { class = "^(xwaylandvideobridge)$" },
    opacity          = 0.0,
    max_size         = "1 1",
    no_anim          = true,
    no_initial_focus = true,
    no_focus         = true,
    no_blur          = true,
})

-- Transparency. The rice targets VSCodium; this machine has VS Code (class "code").
--
-- BREEZE-THEMED WINDOWS all sit at konsole's 0.87. That value is NOT configured
-- here: it lives in ~/.local/share/konsole/Amethyst.colorscheme (Opacity=0.87),
-- selected by Lyn.profile. Hyprland's own active/inactive/fullscreen_opacity are
-- all 1.0 and there is no konsole window rule, so konsole's translucency is
-- entirely its own doing -- worth knowing before hunting for it in this file.
--
-- One family rule covers every Qt/KDE app rather than naming them one by one,
-- so dolphin, systemsettings, kwallet and polkit prompts all match without
-- guessing classes for apps that are not running.
hl.window_rule({ name = "opacity-breeze-kde", match = { class = "^(org.kde..*)$" }, opacity = 0.87 })
-- ...EXCEPT konsole, which must be cancelled back to 1.0. Its 0.87 is a
-- BACKGROUND opacity applied inside the app; a compositor rule on top would
-- multiply with it (0.87 x 0.87 = 0.76) and also fade the text, which konsole's
-- own setting deliberately leaves solid. Later rules win, so this has to stay
-- after the family rule above.
hl.window_rule({ name = "opacity-konsole-own", match = { class = "^(org.kde.konsole)$" }, opacity = 1.0 })
-- The GTK side of Breeze: both of these use ~/.config/gtk-3.0/palette-overrides.css.
hl.window_rule({ name = "opacity-pavucontrol", match = { class = "^(org.pulseaudio.pavucontrol)$" }, opacity = 0.87 })
hl.window_rule({ name = "opacity-easyeffects", match = { class = "(?i)easyeffects" }, opacity = 0.87 })
-- Vesktop reports class "vesktop", not "discord", so a bare (?i)discord never
-- matched it and the window stayed fully opaque. The (?i) is inside the group
-- so the flag covers both alternatives rather than just the first.
-- Kept level with the VS Code rule below; both are Electron, so neither is
-- Breeze-themed and neither takes konsole's 0.87.
hl.window_rule({ name = "opacity-discord",  match = { class = "(?i)(discord|vesktop)" }, opacity = 0.77 })
hl.window_rule({ name = "opacity-code",     match = { class = "^(code)$" },            opacity = 0.77 })
hl.window_rule({ name = "opacity-obsidian", match = { class = "(?i)obsidian" },        opacity = 0.75 })
-- The portal file dialog (Save As / Upload File). Breeze-themed and Qt, so it
-- takes konsole's 0.87 with the rest of them -- but its class is
-- org.freedesktop.*, not org.kde.*, so the family rule above misses it.
-- Class is the KDE backend's, set in ~/.config/xdg-desktop-portal/portals.conf;
-- the rice's float-portal-gtk rule above matches the GTK backend and so never
-- fires.
hl.window_rule({ name = "opacity-portal",   match = { class = "^(org.freedesktop.impl.portal.desktop.kde)$" }, opacity = 0.87 })

-- Smart gaps: no gaps/border/rounding when a workspace holds one tiled window.
hl.workspace_rule({ workspace = "w[tv1]", gaps_out = 0, gaps_in = 0 })
hl.workspace_rule({ workspace = "f[1]",   gaps_out = 0, gaps_in = 0 })
hl.window_rule({ name = "no-gaps-wtv1", match = { float = false, workspace = "w[tv1]" }, border_size = 0, rounding = 0 })
hl.window_rule({ name = "no-gaps-f1",   match = { float = false, workspace = "f[1]" },   border_size = 0, rounding = 0 })


---------------------
---- KEYBINDINGS ----
---------------------

---- Window management ----
hl.bind("SUPER + SHIFT + Q", hl.dsp.window.close())
hl.bind("SUPER + F", hl.dsp.window.fullscreen({ action = "toggle" }))
hl.bind("SUPER + SHIFT + SPACE", hl.dsp.window.float({ action = "toggle" }))
hl.bind("SUPER + P", hl.dsp.window.pseudo())
hl.bind("SUPER + J", hl.dsp.layout("togglesplit"))

---- Launchers ----
hl.bind("SUPER + D", hl.dsp.exec_cmd(menu))
hl.bind("SUPER + RETURN", hl.dsp.exec_cmd(terminal))
hl.bind("SUPER + SHIFT + F", hl.dsp.exec_cmd(fileManager))
hl.bind("SUPER + SHIFT + G", hl.dsp.exec_cmd(browser))
hl.bind("SUPER + SHIFT + V", hl.dsp.exec_cmd(editor))
hl.bind("SUPER + SHIFT + D", hl.dsp.exec_cmd(chat))
hl.bind("SUPER + E", hl.dsp.exec_cmd(appFinder))

-- Clipboard history. The original used "clipvault", which is not installed here.
-- With cliphist (dnf install cliphist) this would be:
-- hl.bind("SUPER + V", hl.dsp.exec_cmd([[cliphist list | wofi -S dmenu | cliphist decode | wl-copy]]))
-- and the autostart block would need: wl-paste --watch cliphist store

---- Session ----
hl.bind("SUPER + L", hl.dsp.exec_cmd("hyprlock"))
hl.bind("SUPER + SHIFT + R", hl.dsp.exec_cmd("hyprctl reload"))

-- Recall the most recent dismissed notification. dunst has no notification
-- centre (unlike swaync) -- it keeps a history buffer instead, and this
-- re-displays entries from it one at a time. `dunstctl count history` shows
-- how many are stored.
hl.bind("SUPER + N", hl.dsp.exec_cmd("dunstctl history-pop"))
-- Dismiss everything: close any popups still on screen, then wipe the history
-- buffer. (dunstctl also has history-rm <ID> to drop a single entry, and
-- close-all on its own if you only want to clear what is visible.)
hl.bind("SUPER + SHIFT + N", hl.dsp.exec_cmd("dunstctl close-all && dunstctl history-clear"))
hl.bind("SUPER + ALT + M", hl.dsp.exec_cmd("XDG_MENU_PREFIX=plasma- kbuildsycoca6"))
hl.bind("SUPER + ALT + SHIFT + E", hl.dsp.exit())
hl.bind("SUPER + ALT + SHIFT + S", hl.dsp.exec_cmd("systemctl poweroff"))
hl.bind("SUPER + ALT + SHIFT + R", hl.dsp.exec_cmd("systemctl reboot"))
hl.bind("SUPER + ALT + SHIFT + H", hl.dsp.exec_cmd("systemctl hibernate"))

---- Focus ----
hl.bind("SUPER + left",  hl.dsp.focus({ direction = "left" }))
hl.bind("SUPER + right", hl.dsp.focus({ direction = "right" }))
hl.bind("SUPER + up",    hl.dsp.focus({ direction = "up" }))
hl.bind("SUPER + down",  hl.dsp.focus({ direction = "down" }))

---- Workspaces: SUPER + [0-9] to switch, + SHIFT to move the window there ----
for i = 1, 10 do
    local key = i % 10 -- 10 maps to key 0
    hl.bind("SUPER + " .. key,         hl.dsp.focus({ workspace = i}))
    hl.bind("SUPER + SHIFT + " .. key, hl.dsp.window.move({ workspace = i }))
end

-- Scroll through existing workspaces with SUPER + scroll
hl.bind("SUPER + mouse_down", hl.dsp.focus({ workspace = "e+1" }))
hl.bind("SUPER + mouse_up",   hl.dsp.focus({ workspace = "e-1" }))

-- Move/resize windows with SUPER + LMB/RMB and dragging
hl.bind("SUPER + mouse:272", hl.dsp.window.drag(),   { mouse = true })
hl.bind("SUPER + mouse:273", hl.dsp.window.resize(), { mouse = true })

-- Example special workspace (scratchpad)
-- hl.bind("SUPER + S",         hl.dsp.workspace.toggle_special("magic"))
-- hl.bind("SUPER + SHIFT + S", hl.dsp.window.move({ workspace = "special:magic" }))

---- Laptop multimedia keys ----
hl.bind("XF86AudioRaiseVolume", hl.dsp.exec_cmd("wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ 5%+"), { locked = true, repeating = true })
hl.bind("XF86AudioLowerVolume", hl.dsp.exec_cmd("wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-"),      { locked = true, repeating = true })
hl.bind("XF86AudioMute",        hl.dsp.exec_cmd("wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle"),     { locked = true, repeating = true })
hl.bind("XF86AudioMicMute",     hl.dsp.exec_cmd("wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle"),   { locked = true, repeating = true })

-- Backlight device here is "apple-panel-bl" (the original hardcoded "intel_backlight").
hl.bind("XF86MonBrightnessUp",
    hl.dsp.exec_cmd([[brightnessctl -d apple-panel-bl set +2% && notify-send "Brightness" "$(brightnessctl -m -d apple-panel-bl | awk -F, '{print substr($4, 0, length($4)-1)}')%"]]),
    { locked = true, repeating = true })
hl.bind("XF86MonBrightnessDown",
    hl.dsp.exec_cmd([[brightnessctl -d apple-panel-bl set 2%- && notify-send "Brightness" "$(brightnessctl -m -d apple-panel-bl | awk -F, '{print substr($4, 0, length($4)-1)}')%"]]),
    { locked = true, repeating = true })

-- Keyboard backlight (LED class device "kbd_backlight" on this machine).
--
-- SUPER + the display-brightness keys is the binding that actually works
-- here. This machine's function row has NO keyboard-backlight keys: the
-- Apple SPI Keyboard's capability bitmap advertises BRIGHTNESSUP/DOWN but
-- not KBDILLUMUP/DOWN, so the XF86KbdBrightness binds below can never fire
-- from the built-in keyboard. They are kept for an external keyboard that
-- does have those keys, and point at the same script.
--
-- brightnessctl reaches this LED through logind's D-Bus; the sysfs node is
-- root-owned, so no udev rule is needed and none should be added.
local brightness = os.getenv("HOME") .. "/.config/hypr/scripts/brightness"
hl.bind("SUPER + XF86MonBrightnessUp",
    hl.dsp.exec_cmd(brightness .. " up kbd"),   { locked = true, repeating = true })
hl.bind("SUPER + XF86MonBrightnessDown",
    hl.dsp.exec_cmd(brightness .. " down kbd"), { locked = true, repeating = true })
hl.bind("XF86KbdBrightnessUp",
    hl.dsp.exec_cmd(brightness .. " up kbd"),   { locked = true, repeating = true })
hl.bind("XF86KbdBrightnessDown",
    hl.dsp.exec_cmd(brightness .. " down kbd"), { locked = true, repeating = true })

-- Requires playerctl
hl.bind("XF86AudioNext",  hl.dsp.exec_cmd("playerctl next"),       { locked = true })
hl.bind("XF86AudioPause", hl.dsp.exec_cmd("playerctl play-pause"), { locked = true })
hl.bind("XF86AudioPlay",  hl.dsp.exec_cmd("playerctl play-pause"), { locked = true })
hl.bind("XF86AudioPrev",  hl.dsp.exec_cmd("playerctl previous"),   { locked = true })

---- Screenshots ----
-- Select a region, then pick: copy to clipboard, "Save as..." via a real file
-- dialog, or drop it in ~/Pictures/Screenshots. Every path also copies to the
-- clipboard. The old bind wrote the file immediately with no clipboard copy
-- and no way to change your mind.
--
-- The original rice used "hyprshot"; scripts/screenshots.sh used "grimblast".
-- Neither is installed. grim + slurp are, and spectacle cannot work here at
-- all -- it needs KWin's org.kde.KWin.ScreenShot2 interface, so under Hyprland
-- `spectacle -b -r -o FILE` exits 1 silently and writes nothing.
hl.bind("SUPER + CONTROL + 4", hl.dsp.exec_cmd("~/.config/hypr/scripts/screenshot-menu"))

---- Lid switch ----
-- Turn the internal panel off when the lid closes, back on when it opens.
-- The switch device on this machine is "Apple SMC power/lid events"
-- (the original said "Lid Switch", which is what it is called on most PCs).
-- Verify with `hyprctl devices` once Hyprland is running.
-- { locked = true } is NOT optional. Without it these behave like plain
-- `bind =` rather than `bindl =` and are suppressed whenever the session is
-- locked -- which is always the case around a suspend, because hypridle's
-- before_sleep_cmd runs `loginctl lock-session`. Previously both binds were
-- 2-argument calls with no options table, so neither had ever fired: the
-- Hyprland log showed the lid device being detected and zero dispatches.
--
-- Behaviour now lives in scripts/lid so it can depend on AC vs battery.
hl.bind("switch:on:Apple SMC power/lid events",
    hl.dsp.exec_cmd(os.getenv("HOME") .. "/.config/hypr/scripts/lid close"),
    { locked = true })
hl.bind("switch:off:Apple SMC power/lid events",
    hl.dsp.exec_cmd(os.getenv("HOME") .. "/.config/hypr/scripts/lid open"),
    { locked = true })
