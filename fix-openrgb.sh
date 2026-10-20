#!/usr/bin/env bash
# Let OpenRGB (running as you) reach the Wraith Prism cooler and the ASUS Aura
# motherboard controller. Both are USB HID devices; their /dev/hidraw* nodes were
# created at boot BEFORE /usr/lib/udev/rules.d/60-openrgb.rules was installed, so
# they never got the "uaccess" ACL and are still root-only.
set -euo pipefail

# 1. Re-run udev rules on the devices that already exist (no reboot needed).
sudo udevadm control --reload-rules
sudo udevadm trigger --action=change --subsystem-match=hidraw --subsystem-match=usb

# 2. SMBus access (silences OpenRGB's "I2C/SMBus interfaces failed" warning, and
#    is needed for any RGB RAM). Load now and on every boot.
echo i2c-dev | sudo tee /etc/modules-load.d/i2c-dev.conf >/dev/null
sudo modprobe i2c-dev

# 3. Check: a "+" after the permissions means the ACL for your user is in place.
sleep 1
for h in /sys/class/hidraw/hidraw*; do
    if grep -qiE 'HID_ID=0003:0000(0B05:000018F3|2516:00000051)' "$h/device/uevent"; then
        ls -l "/dev/$(basename "$h")"
    fi
done
ls -l /dev/i2c-0 2>/dev/null || echo "WARNING: /dev/i2c-0 still missing"
echo
echo "Now quit OpenRGB completely (including the tray icon) and start it again."
