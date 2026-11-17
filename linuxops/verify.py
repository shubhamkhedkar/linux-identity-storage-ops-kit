"""Verify a provisioned root (real host or sandbox) against the spec."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

from linuxops.spec import Spec, load


def _table(path: Path) -> dict[str, list[str]]:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            parts = line.split(":")
            rows[parts[0]] = parts
    return rows


def verify(spec: Spec, root: str) -> list[str]:
    base = Path(root)
    problems: list[str] = []
    passwd = _table(base / "etc/passwd")
    group = _table(base / "etc/group")
    shadow = _table(base / "etc/shadow")
    gids = spec.group_ids()
    uids = spec.user_ids()

    for name, gid in gids.items():
        if name not in group or int(group[name][2]) != gid:
            problems.append(f"group {name} missing or gid != {gid}")
    for u in spec.users:
        row = passwd.get(u.name)
        if row is None:
            problems.append(f"user {u.name} missing")
            continue
        if int(row[2]) != u.uid or int(row[3]) != gids[u.primary_group]:
            problems.append(f"user {u.name} uid/gid mismatch")
        if row[6] != u.shell:
            problems.append(f"user {u.name} shell {row[6]} != {u.shell}")
        if not shadow.get(u.name, ["", ""])[1].startswith("!"):
            problems.append(f"user {u.name} password is not locked")
        for g in u.groups:
            members = group.get(g, ["", "", "", ""])[3].split(",")
            if u.name not in members:
                problems.append(f"user {u.name} not in secondary group {g}")
        home = base / "home" / u.name
        if home.is_dir() and stat.S_IMODE(home.stat().st_mode) & 0o007:
            problems.append(f"home {home} is world-accessible")

    for e in [*spec.directories, *spec.files]:
        p = base / e.path.lstrip("/")
        if not p.exists():
            problems.append(f"{e.path} missing")
            continue
        st = os.stat(p)
        mode = stat.S_IMODE(st.st_mode)
        if mode != int(e.mode, 8):
            problems.append(f"{e.path} mode {oct(mode)} != {e.mode}")
        if st.st_uid != uids[e.owner] or st.st_gid != gids[e.group]:
            problems.append(f"{e.path} owner {st.st_uid}:{st.st_gid} mismatch")

    for g in dict.fromkeys(r.group for r in spec.sudo_rules):
        p = base / f"etc/sudoers.d/50-linuxops-{g}"
        if not p.exists():
            problems.append(f"sudoers drop-in for {g} missing")
        elif stat.S_IMODE(p.stat().st_mode) != 0o440:
            problems.append(f"sudoers drop-in for {g} is not 0440")
    return problems


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 2:
        print("usage: python -m linuxops.verify SPEC ROOT", file=sys.stderr)
        return 2
    problems = verify(load(args[0]), args[1])
    for p in problems:
        print(f"FAIL {p}")
    if not problems:
        print("verify: all users, groups, paths, modes and sudoers match the spec")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
