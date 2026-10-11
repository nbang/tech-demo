#!/bin/bash
# Rescue the D905 EmuELEC SD card (mmcblk1) to the Chainedbox via sshfs.
# Runs on the TX3 (192.168.2.9) as /root/d905-rescue.sh, inside tmux session d905.
# Re-run to resume: the mapfile records what has been read. See D905.md.
set -u
DEV=/dev/mmcblk1
OUT=/mnt/chainbox/sdcard-emuelec.img
MAP=/root/d905-sdcard.map
blockdev --setro $DEV
echo "== pass 1: fast copy, skip bad areas"; ddrescue -n    $DEV $OUT $MAP
echo "== pass 2: retry bad areas";           ddrescue -d -r3 $DEV $OUT $MAP
cp $MAP /mnt/chainbox/
echo "== result"; ddrescuelog -t $MAP
echo "== sha256"; sha256sum $OUT | tee /mnt/chainbox/sdcard-emuelec.img.sha256
echo DONE
