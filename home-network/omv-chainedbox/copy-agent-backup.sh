#!/bin/bash
# copy-agent-backup.sh — copy the backup folder off the failing sda (label "agent")
# onto sdb (label "data"). Run ON the OMV box as root (OMV=192.168.2.10):
#
#   scp copy-agent-backup.sh root@$OMV:/root/
#   ssh root@$OMV 'nohup bash /root/copy-agent-backup.sh > /root/copy.out 2>&1 &'
#   ssh root@$OMV 'tail -f /root/copy.out'
#
# Safe to re-run: rsync resumes and only copies what is missing/changed, and
# retries files that failed last time. Nothing on the destination is deleted.
# Override paths with env vars, e.g.  DST_ROOT=/srv/dev-disk-by-label-data bash copy-agent-backup.sh
set -u

SRC_ROOT="${SRC_ROOT:-/srv/dev-disk-by-label-agent}"
SRC="${SRC:-$SRC_ROOT/tmp/}"                       # trailing slash = copy contents
DST_ROOT="${DST_ROOT:-/srv/dev-disk-by-label-data}"
DST="${DST:-$DST_ROOT/bk/}"                 # fixed name so re-runs resume
LOG="/root/copy-agent-backup-$(date +%F_%H%M).log"

# Both disks must really be mounted, otherwise we'd copy into the root fs
mountpoint -q "$SRC_ROOT" || { echo "$SRC_ROOT not mounted"; exit 1; }
mountpoint -q "$DST_ROOT" || { echo "$DST_ROOT not mounted"; exit 1; }
[ -d "$SRC" ] || { echo "No source dir $SRC"; exit 1; }

mkdir -p "$DST"
need=$(du -sk "$SRC" | cut -f1)
have=$(du -sk "$DST" | cut -f1)
free=$(df -Pk "$DST_ROOT" | awk 'NR==2{print $4}')
echo "Source ${need}K, already copied ${have}K, free ${free}K"
[ $((free + have)) -gt "$need" ] || { echo "Not enough space on $DST_ROOT"; exit 1; }

# -aHAX keeps perms/owners/hardlinks/ACLs/xattrs. Unreadable files (bad sectors)
# are skipped and rsync carries on, then exits 23.
# name1 prints each file/folder as it is transferred; progress2 adds an overall %.
rsync -aHAX --partial -h --info=name1,progress2,stats2 "$SRC" "$DST" 2>&1 | tee "$LOG"
rc=${PIPESTATUS[0]}

echo "rsync exit code: $rc  (0 = OK, 23/24 = some files failed/vanished)" | tee -a "$LOG"
if grep -E "rsync: (read|send_files|failed)|Input/output error" "$LOG" > "${LOG%.log}.errors"; then
  echo "Failed files listed in ${LOG%.log}.errors — re-run to retry; persistent ones need ddrescue"
else
  rm -f "${LOG%.log}.errors"
fi
echo "Verify with: rsync -aHAXn --checksum --itemize-changes '$SRC' '$DST'   (should list nothing)"
exit "$rc"
