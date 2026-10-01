#!/bin/bash
# Single-read variant of d905-backup-sd.sh for a slow/failing card: hash the
# bytes while streaming them to Drive, so the card is read only once, and keep
# going past unreadable sectors (zero-filled, logged) instead of truncating.
#
#   ./d905-backup-sd-onepass.sh disk4
set -euo pipefail

DISK=${1:?usage: $0 diskN   (see: diskutil list external)}
DEST=gdrive:backups/d905
IMG=$DEST/sdcard-emuelec.img.zst
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

sudo pkill -9 -f com.apple.fskit.msdos || true
sleep 2
diskutil unmountDisk force "/dev/$DISK" || true

diskutil list "/dev/$DISK"
read -r -p "Is this the 62.5 GB SD card? [y/N] " ok
[[ $ok == y ]] || exit 1

mkfifo "$WORK/tap"
shasum -a 256 <"$WORK/tap" | cut -d' ' -f1 >"$WORK/card.sha256" &
hasher=$!

echo "== 1/2 imaging /dev/r$DISK -> $IMG (read errors: $WORK/dd.log)"
sudo dd if="/dev/r$DISK" bs=1m conv=noerror,sync status=progress 2> >(tee "$WORK/dd.log" >&2) \
  | tee "$WORK/tap" \
  | zstd -T0 -3 \
  | rclone rcat --drive-chunk-size 64M "$IMG"
wait "$hasher"
card=$(cat "$WORK/card.sha256")
rclone copyto "$WORK/dd.log" "$DEST/dd.log"

echo "== 2/2 hashing the uploaded image"
remote=$(rclone cat "$IMG" | zstd -dc | shasum -a 256 | cut -d' ' -f1)

echo "card:   $card"
echo "remote: $remote"
grep -i "error" "$WORK/dd.log" && echo "WARNING: some sectors were unreadable and zero-filled." >&2
if [[ $card == "$remote" ]]; then
  echo "$card  sdcard-emuelec.img" | rclone rcat "$DEST/sdcard-emuelec.img.sha256"
  echo "OK — upload verified."
else
  echo "MISMATCH — backup is NOT good, do not modify the card." >&2
  exit 1
fi
