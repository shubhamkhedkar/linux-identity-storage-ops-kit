#!/usr/bin/env bash
# Format (only if blank), persist by UUID and mount a dedicated data volume.
#   volume.sh --device /dev/nvme1n1 --mountpoint /data [--label data] [--fs ext4]
#             [--owner 2101 --group 2001 --mode 2770] [--options defaults,nofail,...]
#             [--dry-run] [--unmount]
# --dry-run prints every command and touches nothing; it is what the test suite runs.
set -euo pipefail

DEVICE="" MOUNTPOINT="" LABEL="data" FS="ext4" OWNER="0" GROUP="0" MODE="0755"
OPTIONS="defaults,nofail,noatime,nodev,nosuid" DRY_RUN=0 UNMOUNT=0 FSTAB="${FSTAB:-/etc/fstab}"

usage() { sed -n '2,6p' "$0" >&2; exit 2; }
while [[ $# -gt 0 ]]; do
  case "$1" in
    --device) DEVICE="$2"; shift 2 ;;
    --mountpoint) MOUNTPOINT="$2"; shift 2 ;;
    --label) LABEL="$2"; shift 2 ;;
    --fs) FS="$2"; shift 2 ;;
    --owner) OWNER="$2"; shift 2 ;;
    --group) GROUP="$2"; shift 2 ;;
    --mode) MODE="$2"; shift 2 ;;
    --options) OPTIONS="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --unmount) UNMOUNT=1; shift ;;
    -h|--help) usage ;;
    *) echo "unknown argument: $1" >&2; usage ;;
  esac
done

[[ -n "$MOUNTPOINT" ]] || usage
[[ "$MOUNTPOINT" == /* && "$MOUNTPOINT" != "/" ]] || { echo "mountpoint must be absolute and not /" >&2; exit 2; }
case "$MOUNTPOINT" in
  /bin*|/boot*|/dev*|/etc*|/lib*|/proc*|/sbin*|/sys*|/usr*|/home|/var|/tmp|/root)
    echo "refusing protected mountpoint $MOUNTPOINT" >&2; exit 2 ;;
esac
[[ "$FS" == "ext4" || "$FS" == "xfs" ]] || { echo "fs must be ext4 or xfs" >&2; exit 2; }
[[ ",$OPTIONS," == *",nofail,"* ]] || { echo "options must include nofail (boot must not hang on a missing volume)" >&2; exit 2; }
[[ "$MODE" =~ ^[0-7]{3,4}$ ]] || { echo "mode must be octal" >&2; exit 2; }

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then printf 'DRY-RUN:'; printf ' %q' "$@"; printf '\n'; else "$@"; fi
}

if [[ "$UNMOUNT" -eq 1 ]]; then
  run umount "$MOUNTPOINT"
  run sed -i "\\# $MOUNTPOINT #d" "$FSTAB"
  run rmdir "$MOUNTPOINT"
  exit 0
fi

[[ -n "$DEVICE" ]] || usage
if [[ "$DRY_RUN" -eq 0 ]]; then
  [[ "$(id -u)" -eq 0 ]] || { echo "must run as root" >&2; exit 2; }
  [[ -b "$DEVICE" ]] || { echo "$DEVICE is not a block device" >&2; exit 2; }
  if findmnt -rn -S "$DEVICE" >/dev/null; then echo "$DEVICE is already mounted" >&2; exit 2; fi
fi

EXISTING=""
if [[ "$DRY_RUN" -eq 0 ]]; then EXISTING="$(blkid -o value -s TYPE "$DEVICE" || true)"; fi
if [[ -z "$EXISTING" ]]; then
  if [[ "$FS" == "ext4" ]]; then run mkfs.ext4 -q -L "$LABEL" "$DEVICE"; else run mkfs.xfs -q -L "$LABEL" "$DEVICE"; fi
elif [[ "$EXISTING" != "$FS" ]]; then
  echo "$DEVICE already has a $EXISTING filesystem; refusing to reformat" >&2; exit 1
else
  echo "$DEVICE already formatted as $FS; keeping data"
fi

UUID="<UUID-of-$DEVICE>"
if [[ "$DRY_RUN" -eq 0 ]]; then UUID="$(blkid -o value -s UUID "$DEVICE")"; fi
LINE="UUID=$UUID $MOUNTPOINT $FS $OPTIONS 0 2"

run install -d -m 0755 "$MOUNTPOINT"
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "DRY-RUN: append to $FSTAB: $LINE"
elif ! grep -q "^UUID=$UUID " "$FSTAB"; then
  cp -a "$FSTAB" "$FSTAB.bak.$(date +%s)"
  printf '%s\n' "$LINE" >> "$FSTAB"
fi
run mount "$MOUNTPOINT"
run chown "$OWNER:$GROUP" "$MOUNTPOINT"
run chmod "$MODE" "$MOUNTPOINT"
if [[ "$DRY_RUN" -eq 0 ]]; then df -h "$MOUNTPOINT"; fi
