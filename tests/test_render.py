import json
import shutil
import subprocess

import pytest

from linuxops import render
from linuxops.cli import main
from linuxops.spec import load
from tests.conftest import ROOT, SPEC

SHELLCHECK = shutil.which("shellcheck")


@pytest.fixture(scope="module")
def spec():
    return load(SPEC)


def test_provision_has_guards(spec):
    text = render.provision(spec)
    assert text.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in text
    assert "LINUXOPS_APPLY" in text
    assert "visudo -cqf" in text
    assert text.count('usermod "${ROOT_ARGS[@]}" -L') == len(spec.users)


def test_provision_uses_numeric_ids(spec):
    text = render.provision(spec)
    assert "install -d -m 2770 -o 2101 -g 2001" in text


def test_no_password_material(spec):
    text = render.provision(spec) + render.teardown(spec)
    assert "chpasswd" not in text and "passwd --stdin" not in text


def test_sudoers_is_least_privilege(spec):
    text = render.sudoers_text(spec, "devops")
    assert "NOPASSWD" not in text
    assert "ALL=(root) NOEXEC: /usr/bin/systemctl restart nginx" in text
    assert "use_pty" in text and "log_output" in text


def test_teardown_removes_deepest_first(spec):
    text = render.teardown(spec)
    assert text.index("/srv/ops/runbooks") < text.index('rm -rf --one-file-system "$ROOT"/srv/ops\n')


def test_fstab_line(spec):
    assert render.fstab_line(spec, "abcd") == (
        "UUID=abcd /data ext4 defaults,nofail,noatime,nodev,nosuid 0 2"
    )


def test_plan_reports_locked_passwords(spec):
    data = json.loads(render.plan(spec))
    assert {u["password"] for u in data["users"]} == {"locked"}
    assert data["groups"]["opsadmin"] == 2101


def test_cli_rejects_bad_spec(tmp_path, capsys):
    bad = tmp_path / "bad.yaml"
    bad.write_text(SPEC.read_text().replace('mode: "1777"', 'mode: "0777"'))
    assert main(["validate", str(bad)]) == 1
    assert "LX004" in capsys.readouterr().err


def test_cli_render_to_file(tmp_path):
    out = tmp_path / "p.sh"
    assert main(["render", str(SPEC), "provision", "-o", str(out)]) == 0
    assert out.stat().st_mode & 0o777 == 0o750


@pytest.mark.skipif(SHELLCHECK is None, reason="shellcheck not installed")
@pytest.mark.parametrize("kind", ["provision", "teardown"])
def test_rendered_scripts_pass_shellcheck(tmp_path, spec, kind):
    out = tmp_path / f"{kind}.sh"
    out.write_text(render.provision(spec) if kind == "provision" else render.teardown(spec))
    subprocess.run([SHELLCHECK, str(out)], check=True)


def test_rendered_script_refuses_host_without_opt_in(tmp_path, spec):
    out = tmp_path / "p.sh"
    out.write_text(render.provision(spec))
    res = subprocess.run(["bash", str(out)], capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})
    assert res.returncode == 2
    assert "refusing" in res.stderr


def test_terraform_has_no_inbound_or_ssh_key():
    main_tf = (ROOT / "terraform" / "main.tf").read_text()
    assert "ingress" not in main_tf
    assert "key_name" not in main_tf
