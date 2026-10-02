#!/usr/bin/env bash
# Write the Armbian image to an SD card on macOS, with guard rails.
#
#   ./flash-sd.sh <image.img|image.img.gz> <diskN>
#   ./flash-sd.sh armbian.img.gz disk4
#
# Refuses anything that is not an external, removable, <=128 GB disk, and
# makes you retype the disk id before it erases it. Needs sudo for dd.
set -euo pipefail

IMG=${1:?usage: $0 <image.img|image.img.gz> <diskN>}
DISK=${2:?usage: $0 <image.img|image.img.gz> <diskN>}
DISK=${DISK#/dev/}

[[ $DISK =~ ^disk[0-9]+$ ]] || { echo "disk must look like disk4, got '$DISK'"; exit 1; }
[[ -f $IMG ]] || { echo "no such image: $IMG"; exit 1; }

info=$(diskutil info "$DISK") || { echo "diskutil does not know $DISK"; exit 1; }
grep -q 'Device Location: *External' <<<"$info" || { echo "$DISK is not external — refusing"; exit 1; }
grep -q 'Removable Media: *Removable' <<<"$info" || { echo "$DISK is not removable — refusing"; exit 1; }
bytes=$(awk -F'[(]' '/Disk Size/{print $2}' <<<"$info" | awk '{print $1}')
(( bytes <= 128 * 1000**3 )) || { echo "$DISK is larger than 128 GB — refusing"; exit 1; }

diskutil list "$DISK"
read -r -p "Everything on /dev/$DISK will be erased. Retype the disk id to continue: " again
[[ $again == "$DISK" ]] || { echo "aborted"; exit 1; }

diskutil unmountDisk force "/dev/$DISK"
if [[ $IMG == *.gz ]]; then
  gunzip -c "$IMG" | sudo dd of="/dev/r$DISK" bs=4m status=progress
else
  sudo dd if="$IMG" of="/dev/r$DISK" bs=4m status=progress
fi
sync

# Worn-out or fake cards can go read-only and silently drop writes while dd
# reports success — or keep the partition table and lose the files behind it.
# A whole-disk checksum does not work: macOS auto-mounts the FAT BOOT partition
# the moment dd finishes and writes .fseventsd/.Spotlight-V100 into it. So:
# compare BOOT file by file, and everything outside BOOT (MBR, u-boot area,
# ext4 ROOTFS — which macOS cannot mount) byte for byte.
fail() { echo "VERIFY FAILED: $1"; echo "Bad card, fake card, or bad reader — try a different one."; exit 1; }

RAW=$IMG
if [[ $IMG == *.gz ]]; then
  RAW=$(mktemp -t armbian-img); trap 'rm -f "$RAW"' EXIT
  gunzip -c "$IMG" > "$RAW"
fi
size=$(stat -f%z "$RAW")

imgdev=$(hdiutil attach -readonly -nomount -imagekey diskimage-class=CRawDiskImage "$RAW" 2>/dev/null | awk 'NR==1{print $1}')
off() { diskutil info "$1" | awk -F'[: ]+' '/Partition Offset/{print $4}'; }
len() { diskutil info "$1" | awk -F'[(]' '/Disk Size/{print $2}' | awk '{print $1}'; }
p1=$(off "${imgdev}s1"); p1end=$((p1 + $(len "${imgdev}s1")))
(( p1 % 1048576 == 0 && p1end % 1048576 == 0 )) || fail "BOOT partition is not MiB-aligned; verify by hand"

echo "verifying BOOT files..."
imgmnt=$(mktemp -d); cardmnt=$(mktemp -d)
diskutil mount readOnly -mountPoint "$imgmnt" "${imgdev}s1" >/dev/null
diskutil unmountDisk force "/dev/$DISK" >/dev/null
diskutil mount readOnly -mountPoint "$cardmnt" "${DISK}s1" >/dev/null
bad=$(cd "$imgmnt" && find . -type f | while read -r f; do cmp -s "$f" "$cardmnt/$f" || echo "$f"; done | wc -l | tr -d ' ')
diskutil unmount "$cardmnt" >/dev/null; diskutil eject "$imgdev" >/dev/null
(( bad == 0 )) || fail "$bad BOOT files differ from the image"

(( size % 1048576 == 0 )) || fail "image size is not MiB-aligned; verify by hand"
M=1048576
echo "verifying $(( (size - p1end + p1) / M )) MiB outside BOOT..."
diskutil unmountDisk force "/dev/$DISK" >/dev/null
# region 1: MBR + u-boot area before BOOT; region 2: everything after BOOT
want=$( { head -c "$p1" "$RAW"; tail -c +$((p1end + 1)) "$RAW"; } | shasum -a 256)
got=$( { sudo dd if="/dev/r$DISK" bs=1m count=$((p1 / M)) status=none
         sudo dd if="/dev/r$DISK" bs=1m skip=$((p1end / M)) count=$(( (size - p1end) / M )) status=none; } | shasum -a 256)
[[ ${want%% *} == "${got%% *}" ]] || fail "data outside BOOT (MBR, u-boot or ROOTFS) differs from the image"
echo "verified: BOOT files and everything else match the image"

diskutil eject "/dev/$DISK"
echo "done — put the card in the box"
