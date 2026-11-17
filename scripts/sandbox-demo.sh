#!/usr/bin/env bash
# Provision the baseline into a throwaway root directory, verify it, tear it down.
# Uses `useradd --root`, so the host's own /etc/passwd is never touched.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SPEC="${1:-$ROOT_DIR/spec/baseline.yaml}"
PY="${PYTHON:-python3}"
SANDBOX="$(mktemp -d /tmp/linuxops-sandbox.XXXXXX)"
WORK="$(mktemp -d)"
cleanup() { sudo rm -rf --one-file-system "$SANDBOX"; rm -rf "$WORK"; }
trap cleanup EXIT

echo "==> sandbox root: $SANDBOX"
sudo install -d -m 0755 "$SANDBOX/etc" "$SANDBOX/home" "$SANDBOX/srv" "$SANDBOX/etc/skel"
printf 'root:x:0:0:root:/root:/bin/bash\n' | sudo tee "$SANDBOX/etc/passwd" >/dev/null
printf 'root:x:0:\n' | sudo tee "$SANDBOX/etc/group" >/dev/null
printf 'root:*:19000:0:99999:7:::\n' | sudo install -m 0640 /dev/stdin "$SANDBOX/etc/shadow"
printf 'root:*::\n' | sudo install -m 0640 /dev/stdin "$SANDBOX/etc/gshadow"
# Stub shells so useradd/usermod do not warn inside the sandbox.
sudo install -d -m 0755 "$SANDBOX/bin" "$SANDBOX/usr/sbin"
for sh in /bin/bash /usr/sbin/nologin; do sudo install -m 0755 /dev/null "$SANDBOX$sh"; done
if [[ -f /etc/login.defs ]]; then sudo cp /etc/login.defs "$SANDBOX/etc/login.defs"; fi

(cd "$ROOT_DIR" && "$PY" -m linuxops render "$SPEC" provision -o "$WORK/provision.sh")
(cd "$ROOT_DIR" && "$PY" -m linuxops render "$SPEC" teardown -o "$WORK/teardown.sh")

echo "==> provision (run twice to prove idempotency)"
sudo ROOT="$SANDBOX" bash "$WORK/provision.sh"
sudo ROOT="$SANDBOX" bash "$WORK/provision.sh" >/dev/null

echo "==> verify"
(cd "$ROOT_DIR" && sudo "$PY" -m linuxops.verify "$SPEC" "$SANDBOX")

echo "==> teardown"
sudo ROOT="$SANDBOX" bash "$WORK/teardown.sh"
if sudo grep -Eq '^(opsadmin|devops1|devops2|appsvc|dbadmin):' "$SANDBOX/etc/passwd"; then
  echo "teardown left users behind" >&2
  exit 1
fi
[[ ! -e "$SANDBOX/srv/ops" ]] || { echo "teardown left /srv/ops" >&2; exit 1; }
echo "sandbox demo passed"
