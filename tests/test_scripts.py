import json
import subprocess

from tests.conftest import ROOT

VOLUME = ROOT / "scripts" / "volume.sh"
AUDIT = ROOT / "scripts" / "audit.sh"


def run(*args):
    return subprocess.run(["bash", *map(str, args)], capture_output=True, text=True)


def test_volume_dry_run_plan():
    res = run(VOLUME, "--device", "/dev/nvme1n1", "--mountpoint", "/data", "--dry-run")
    assert res.returncode == 0, res.stderr
    assert "mkfs.ext4 -q -L data /dev/nvme1n1" in res.stdout
    assert "defaults,nofail,noatime,nodev,nosuid 0 2" in res.stdout


def test_volume_refuses_protected_mountpoint():
    res = run(VOLUME, "--device", "/dev/x", "--mountpoint", "/etc", "--dry-run")
    assert res.returncode == 2


def test_volume_requires_nofail():
    res = run(VOLUME, "--device", "/dev/x", "--mountpoint", "/data", "--options", "defaults", "--dry-run")
    assert res.returncode == 2
    assert "nofail" in res.stderr


def test_volume_unmount_dry_run():
    res = run(VOLUME, "--mountpoint", "/data", "--unmount", "--dry-run")
    assert res.returncode == 0
    assert "umount /data" in res.stdout


def _fake_root(tmp_path, passwd):
    (tmp_path / "etc" / "sudoers.d").mkdir(parents=True)
    (tmp_path / "etc" / "passwd").write_text(passwd)
    (tmp_path / "etc" / "shadow").write_text("root:*:19000::::::\n")
    return tmp_path


def test_audit_clean_root(tmp_path):
    root = _fake_root(tmp_path, "root:x:0:0::/root:/bin/bash\nops:x:2101:2101::/home/ops:/bin/bash\n")
    res = run(AUDIT, "--root", root, "--json")
    assert res.returncode == 0, res.stdout
    checks = {r["check"]: r for r in json.loads(res.stdout)}
    assert checks["last-passwd-entry"]["detail"].startswith("ops:")


def test_audit_flags_uid0_empty_password_and_open_dir(tmp_path):
    root = _fake_root(tmp_path, "root:x:0:0::/root:/bin/bash\ntoor:x:0:0::/:/bin/sh\n")
    (root / "etc" / "shadow").write_text("root:*:1::::::\ntoor::1::::::\n")
    (root / "etc" / "sudoers.d" / "99-bad").write_text("toor ALL=(ALL) NOPASSWD: ALL\n")
    open_dir = root / "shared"
    open_dir.mkdir()
    open_dir.chmod(0o777)
    res = run(AUDIT, "--root", root, "--json")
    assert res.returncode == 1
    found = {r["check"] for r in json.loads(res.stdout)}
    assert {"uid0", "empty-password", "sudo-broad", "world-writable-dir"} <= found


def test_audit_find(tmp_path):
    root = _fake_root(tmp_path, "root:x:0:0::/root:/bin/bash\n")
    (root / "opt").mkdir()
    (root / "opt" / "f3").write_text("x")
    res = run(AUDIT, "--root", root, "--find", "f3")
    assert "/opt/f3" in res.stdout
