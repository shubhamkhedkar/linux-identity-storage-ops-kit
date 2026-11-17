#!/usr/bin/env bash
# Read-only host audit: identity, permissions and storage posture.
#   audit.sh [--root DIR] [--find NAME] [--json]
# Exit 1 when a high-severity finding is present (usable as a CI/cron gate).
set -euo pipefail

ROOT="" FIND_NAME="" JSON=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT="${2%/}"; shift 2 ;;
    --find) FIND_NAME="$2"; shift 2 ;;
    --json) JSON=1; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
BASE="${ROOT:-/}"
HIGH=0
declare -a REPORT=()

note() { REPORT+=("$1|$2|$3"); if [[ "$1" == "HIGH" ]]; then HIGH=$((HIGH + 1)); fi; }

passwd="$ROOT/etc/passwd"
if [[ -r "$passwd" ]]; then
  while IFS=: read -r name _ uid _; do
    if [[ "$uid" == "0" && "$name" != "root" ]]; then note HIGH uid0 "non-root account with UID 0: $name"; fi
  done < "$passwd"
  dups="$(cut -d: -f3 "$passwd" | sort | uniq -d | paste -sd, -)"
  if [[ -n "$dups" ]]; then note HIGH duplicate-uid "duplicate UIDs: $dups"; fi
  note INFO last-passwd-entry "$(tail -n 1 "$passwd")"
fi

shadow="$ROOT/etc/shadow"
if [[ -r "$shadow" ]]; then
  while IFS=: read -r name hash _; do
    if [[ -z "$hash" ]]; then note HIGH empty-password "account without password hash: $name"; fi
  done < "$shadow"
fi

if [[ -d "$ROOT/etc/sudoers.d" ]]; then
  while IFS= read -r f; do
    if grep -Eq 'NOPASSWD:[[:space:]]*ALL|ALL=\(ALL(:ALL)?\)[[:space:]]+ALL' "$f" 2>/dev/null; then
      note MEDIUM sudo-broad "broad sudo grant in ${f#"$ROOT"}"
    fi
  done < <(find "$ROOT/etc/sudoers.d" -type f 2>/dev/null)
fi

while IFS= read -r d; do
  note HIGH world-writable-dir "no sticky bit: ${d#"$ROOT"}"
done < <(find "$BASE" -xdev -type d -perm -0002 ! -perm -1000 2>/dev/null | head -n 50)

while IFS= read -r f; do
  note MEDIUM world-writable-file "${f#"$ROOT"}"
done < <(find "$BASE" -xdev -type f -perm -0002 2>/dev/null | head -n 50)

suid_count="$(find "$BASE" -xdev -type f \( -perm -4000 -o -perm -2000 \) 2>/dev/null | wc -l)"
note INFO suid-sgid-files "$suid_count setuid/setgid files on the root filesystem"

top_files="$(find "$BASE" -maxdepth 1 -type f 2>/dev/null | wc -l)"
note INFO top-level-files "$top_files regular files directly under $BASE"

if [[ -n "$FIND_NAME" ]]; then
  hits="$(find "$BASE" -xdev -name "$FIND_NAME" 2>/dev/null | sed "s#^$ROOT##" | paste -sd' ' -)"
  note INFO find "$FIND_NAME: ${hits:-not found}"
fi

if [[ -z "$ROOT" ]] && command -v findmnt >/dev/null; then
  while read -r target opts; do
    if [[ "$opts" != *nodev* ]]; then note LOW mount-nodev "$target mounted without nodev"; fi
  done < <(findmnt -rn -o TARGET,OPTIONS -t ext4,xfs 2>/dev/null | awk '$1 != "/" && $1 !~ /^\/boot/')
fi

if [[ "$JSON" -eq 1 ]]; then
  printf '['
  sep=""
  for row in "${REPORT[@]}"; do
    IFS='|' read -r sev id msg <<< "$row"
    msg="${msg//\\/\\\\}"; msg="${msg//\"/\\\"}"
    printf '%s{"severity":"%s","check":"%s","detail":"%s"}' "$sep" "$sev" "$id" "$msg"
    sep=","
  done
  printf ']\n'
else
  for row in "${REPORT[@]}"; do
    IFS='|' read -r sev id msg <<< "$row"
    printf '%-6s %-20s %s\n' "$sev" "$id" "$msg"
  done
  echo "high-severity findings: $HIGH"
fi
[[ "$HIGH" -eq 0 ]]
