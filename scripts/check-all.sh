#!/usr/bin/env bash
# Every offline check. Nothing here talks to AWS or changes this host.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
step() { printf '\n==> %s\n' "$1"; }

step "Spec policy (LX rules)"
python3 -m linuxops validate spec/baseline.yaml

step "Python lint + format + tests"
ruff check .
ruff format --check .
pytest -q

step "YAML lint"
yamllint spec terraform/cloud-init.yaml .yamllint

step "ShellCheck (scripts + rendered output)"
shellcheck scripts/*.sh
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
python3 -m linuxops render spec/baseline.yaml provision -o "$TMP/provision.sh"
python3 -m linuxops render spec/baseline.yaml teardown -o "$TMP/teardown.sh"
shellcheck "$TMP/provision.sh" "$TMP/teardown.sh"

step "Terraform fmt / validate / mocked tests"
terraform fmt -recursive -check terraform
(cd terraform && terraform init -backend=false -input=false >/dev/null && terraform validate && terraform test)

step "Checkov"
checkov -d terraform --framework terraform --quiet --compact

echo
echo "All checks passed. Optional: make sandbox (needs sudo, writes only under /tmp)."
