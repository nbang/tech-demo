#!/bin/bash
# Image the D905 box's EmuELEC SD card (read-only) straight to Google Drive, then
# verify the upload by re-reading the card and the remote copy and comparing hashes.
# The Mac has too little free disk to stage a 62.5 GB image locally.
#
#   ./d905-backup-sd.sh disk5
set -euo pipefail

DISK=${1:?usage: $0 diskN   (see: diskutil list external)}
DEST=gdrive:backups/d905
IMG=$DEST/sdcard-emuelec.img.zst

# macOS's fskit msdos driver spins forever on this card's dirty FAT and blocks
# diskutil; kill it so the card can be unmounted.
sudo pkill -9 -f com.apple.fskit.msdos || true
sleep 2
diskutil unmountDisk force "/dev/$DISK" || true

diskutil info "/dev/$DISK" | grep -E "Device / Media Name|Disk Size|Removable|Protocol"
diskutil list "/dev/$DISK"
read -r -p "Is this the 62.5 GB SD card? [y/N] " ok
[[ $ok == y ]] || exit 1

diskutil list "/dev/$DISK" | rclone rcat "$DEST/partitions.txt"

echo "== 1/3 imaging /dev/r$DISK -> $IMG"
sudo dd if="/dev/r$DISK" bs=4m status=progress \
  | zstd -T0 -3 \
  | rclone rcat --drive-chunk-size 64M "$IMG"

echo "== 2/3 hashing the card"
card=$(sudo dd if="/dev/r$DISK" bs=4m 2>/dev/null | shasum -a 256 | cut -d' ' -f1)

echo "== 3/3 hashing the uploaded image"
remote=$(rclone cat "$IMG" | zstd -dc | shasum -a 256 | cut -d' ' -f1)

echo "card:   $card"
echo "remote: $remote"
if [[ $card == "$remote" ]]; then
  echo "$card  sdcard-emuelec.img" | rclone rcat "$DEST/sdcard-emuelec.img.sha256"
  echo "OK — backup verified."
else
  echo "MISMATCH — backup is NOT good, do not modify the card." >&2
  exit 1
fi
