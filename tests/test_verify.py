import os

from linuxops.spec import load
from linuxops.verify import verify
from tests.conftest import SPEC


def test_verify_reports_missing_everything(tmp_path):
    etc = tmp_path / "etc"
    etc.mkdir()
    for name in ("passwd", "group", "shadow"):
        (etc / name).write_text("root:x:0:0::/root:/bin/bash\n")
    problems = verify(load(SPEC), str(tmp_path))
    assert any("user opsadmin missing" in p for p in problems)
    assert any("/srv/ops missing" in p for p in problems)


def test_verify_detects_mode_drift(tmp_path):
    spec = load(SPEC)
    etc = tmp_path / "etc"
    etc.mkdir()
    (etc / "passwd").write_text("")
    (etc / "group").write_text("")
    (etc / "shadow").write_text("")
    d = tmp_path / "srv" / "ops"
    d.mkdir(parents=True)
    os.chmod(d, 0o755)  # noqa: S103
    problems = verify(spec, str(tmp_path))
    assert any("/srv/ops mode 0o755 != 2770" in p for p in problems)
