import pytest

from linuxops import policy
from linuxops.spec import SpecError, load, parse
from tests.conftest import SPEC


def rules(raw):
    return {f.rule for f in policy.evaluate(parse(raw))}


def test_shipped_baseline_is_clean():
    assert policy.evaluate(load(SPEC)) == []


def test_bad_username(raw):
    raw["users"][0]["name"] = "Ops Admin"
    assert "LX001" in rules(raw)


def test_system_uid_rejected(raw):
    raw["users"][1]["uid"] = 0
    assert "LX002" in rules(raw)


def test_duplicate_gid_rejected(raw):
    raw["groups"][1]["gid"] = raw["groups"][0]["gid"]
    assert "LX002" in rules(raw)


def test_unknown_secondary_group(raw):
    raw["users"][0]["groups"] = ["wheel"]
    assert "LX003" in rules(raw)


def test_world_writable_dir_needs_sticky(raw):
    raw["directories"][-1]["mode"] = "0777"
    assert "LX004" in rules(raw)


def test_integer_mode_is_a_parse_error(raw):
    raw["directories"][0]["mode"] = 750
    with pytest.raises(SpecError):
        parse(raw)


def test_world_writable_file(raw):
    raw["files"][0]["mode"] = "0666"
    assert "LX005" in rules(raw)


def test_setuid_file(raw):
    raw["files"][0]["mode"] = "4755"
    assert "LX011" in rules(raw)


@pytest.mark.parametrize(
    "cmd",
    ["ALL", "/bin/bash", "systemctl restart nginx", "/usr/bin/vim /etc/hosts",
     "/usr/bin/systemctl restart *", "/usr/bin/journalctl; id"],
)  # fmt: skip
def test_unsafe_sudo(raw, cmd):
    raw["sudo_rules"][0]["commands"] = [cmd]
    assert "LX006" in rules(raw)


def test_password_field_rejected(raw):
    raw["users"][0]["password"] = "hunter2"  # noqa: S105 (fixture proving the rule fires)
    assert "LX007" in rules(raw)


@pytest.mark.parametrize("path", ["/etc/app", "relative/dir", "/srv/../etc", "/usr/local/x"])
def test_protected_or_bad_paths(raw, path):
    raw["directories"][0]["path"] = path
    assert "LX008" in rules(raw)


def test_unknown_owner(raw):
    raw["directories"][0]["owner"] = "ghost"
    assert "LX009" in rules(raw)


def test_undeclared_parent(raw):
    raw["files"][0]["path"] = "/srv/elsewhere/notes.md"
    assert "LX009" in rules(raw)


def test_volume_requires_nofail_and_nodev(raw):
    raw["volume"]["options"] = ["defaults"]
    assert "LX010" in rules(raw)


def test_volume_protected_mountpoint(raw):
    raw["volume"]["mountpoint"] = "/var"
    assert "LX010" in rules(raw)


def test_service_account_must_be_nologin(raw):
    raw["users"][3]["shell"] = "/bin/bash"
    assert "LX013" in rules(raw)


def test_duplicate_path(raw):
    raw["directories"].append(dict(raw["directories"][0]))
    assert "LX014" in rules(raw)
