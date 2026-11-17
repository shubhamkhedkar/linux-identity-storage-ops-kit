"""Guardrail rules evaluated before anything is rendered."""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass

from linuxops.spec import Spec

NAME_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
MODE_RE = re.compile(r"^[0-7]{3,4}$")
ID_MIN, ID_MAX = 1000, 59999
ALLOWED_SHELLS = {"/bin/bash", "/bin/sh", "/usr/bin/bash", "/usr/bin/zsh", "/usr/sbin/nologin"}
PROTECTED_PREFIXES = ("/bin", "/boot", "/dev", "/etc", "/lib", "/proc", "/sbin", "/sys", "/usr")
PROTECTED_EXACT = {"/", "/home", "/opt", "/root", "/run", "/srv", "/tmp", "/var"}  # noqa: S108 (path list, not a temp file)
# Binaries that hand out an interactive shell or arbitrary writes when run via sudo.
SUDO_ESCAPE_BINS = {
    "bash", "sh", "zsh", "dash", "su", "sudo", "vi", "vim", "nano", "less", "more",
    "env", "find", "awk", "python", "python3", "perl", "tee", "cp", "mv", "chmod", "chown",
}  # fmt: skip
REQUIRED_MOUNT_OPTS = {"nofail", "nodev"}
SUPPORTED_FS = {"ext4", "xfs"}


@dataclass(frozen=True)
class Finding:
    rule: str
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.rule} {self.where}: {self.message}"


def _mode_bits(mode: str) -> int:
    return int(mode, 8)


def _protected(path: str) -> bool:
    if path in PROTECTED_EXACT:
        return True
    return any(path == p or path.startswith(p + "/") for p in PROTECTED_PREFIXES)


def evaluate(spec: Spec) -> list[Finding]:
    out: list[Finding] = []

    def add(rule: str, where: str, message: str) -> None:
        out.append(Finding(rule, where, message))

    if spec.version != 1:
        add("LX000", "version", "only spec version 1 is supported")
    if not spec.host or not NAME_RE.match(spec.host):
        add("LX001", "host", "host must be a lowercase identifier")

    # Identity: names, ID ranges, uniqueness.
    seen_names: set[str] = set()
    for kind, items in (("group", spec.groups), ("user", spec.users)):
        for item in items:
            where = f"{kind}:{item.name}"
            if not NAME_RE.match(item.name):
                add("LX001", where, "name must match " + NAME_RE.pattern)
            key = f"{kind}:{item.name}"
            if key in seen_names:
                add("LX002", where, f"duplicate {kind} name")
            seen_names.add(key)
    for label, ids in (
        ("gid", [(g.name, g.gid) for g in spec.groups]),
        ("uid", [(u.name, u.uid) for u in spec.users]),
    ):
        used: dict[int, str] = {}
        for name, num in ids:
            if not ID_MIN <= num <= ID_MAX:
                add("LX002", name, f"{label} {num} outside {ID_MIN}-{ID_MAX} (no system IDs)")
            if num in used:
                add("LX002", name, f"{label} {num} already used by {used[num]}")
            used[num] = name

    groups = spec.group_ids()
    users = spec.user_ids()
    declared_groups = {g.name for g in spec.groups}
    for u in spec.users:
        where = f"user:{u.name}"
        if u.primary_group != u.name and u.primary_group not in declared_groups:
            add("LX003", where, f"primary group '{u.primary_group}' is not declared")
        if u.primary_group == u.name and u.uid in {g.gid for g in spec.groups}:
            add("LX002", where, "private group gid would collide with a declared gid")
        for g in u.groups:
            if g not in groups:
                add("LX003", where, f"secondary group '{g}' is not declared")
        if u.shell not in ALLOWED_SHELLS:
            add("LX013", where, f"shell {u.shell} is not in the allowed list")
        if u.system_like and u.shell != "/usr/sbin/nologin":
            add("LX013", where, "service accounts must use /usr/sbin/nologin")
        for key in u.extra:
            if "pass" in key or "secret" in key or "key" in key:
                add("LX007", where, f"'{key}' looks like a credential; accounts stay locked")
            else:
                add("LX000", where, f"unknown key '{key}'")

    # Paths.
    seen_paths: set[str] = set()
    dir_paths = {d.path for d in spec.directories}
    for kind, entries in (("dir", spec.directories), ("file", spec.files)):
        for e in entries:
            where = f"{kind}:{e.path}"
            norm = posixpath.normpath(e.path)
            if not e.path.startswith("/") or norm != e.path or ".." in e.path.split("/"):
                add("LX008", where, "path must be absolute and normalised")
            elif _protected(e.path):
                add("LX008", where, "path is a protected system location")
            if e.path in seen_paths:
                add("LX014", where, "duplicate path")
            seen_paths.add(e.path)
            if e.owner not in users:
                add("LX009", where, f"owner '{e.owner}' is not a declared user")
            if e.group not in groups:
                add("LX009", where, f"group '{e.group}' is not a declared group")
            if not MODE_RE.match(e.mode):
                add("LX004", where, f"mode '{e.mode}' is not octal")
                continue
            bits = _mode_bits(e.mode)
            if kind == "dir" and bits & 0o002 and not bits & 0o1000:
                add("LX004", where, "world-writable directory needs the sticky bit")
            if kind == "file":
                if bits & 0o002:
                    add("LX005", where, "world-writable files are not allowed")
                if bits & 0o6000:
                    add("LX011", where, "setuid/setgid files are not allowed")
                if bits & 0o111 and e.content is not None and "=" in e.content:
                    add("LX005", where, "config files must not be executable")
            parent = posixpath.dirname(e.path)
            if parent not in dir_paths and not _protected(parent) and parent not in PROTECTED_EXACT:
                add("LX009", where, f"parent directory {parent} is not declared")

    # sudo.
    for r in spec.sudo_rules:
        where = f"sudo:{r.group}"
        if r.group not in groups:
            add("LX006", where, "sudo group is not declared")
        if r.run_as != "root" and r.run_as not in users:
            add("LX006", where, f"run_as '{r.run_as}' is not a declared user")
        if not r.commands:
            add("LX006", where, "at least one command is required")
        for cmd in r.commands:
            binary = cmd.split()[0] if cmd.split() else ""
            if cmd.strip().upper() == "ALL" or "ALL" in cmd.split():
                add("LX006", where, "ALL is not allowed; list explicit commands")
            elif not binary.startswith("/"):
                add("LX006", where, f"'{cmd}' must use an absolute path")
            elif posixpath.basename(binary) in SUDO_ESCAPE_BINS:
                add("LX006", where, f"'{binary}' allows shell escape via sudo")
            if any(ch in cmd for ch in ",:\\=*?;|&`$"):
                add("LX006", where, f"'{cmd}' contains sudoers or shell metacharacters")

    # Storage.
    v = spec.volume
    if v is not None:
        where = f"volume:{v.label}"
        if not NAME_RE.match(v.label) or len(v.label) > 16:
            add("LX010", where, "label must be a short lowercase identifier (<=16 chars)")
        if v.filesystem not in SUPPORTED_FS:
            add("LX010", where, f"filesystem must be one of {sorted(SUPPORTED_FS)}")
        if not v.mountpoint.startswith("/") or _protected(v.mountpoint):
            add("LX010", where, "mountpoint must be a dedicated absolute path")
        missing = REQUIRED_MOUNT_OPTS - set(v.options)
        if missing:
            add("LX010", where, f"mount options missing {sorted(missing)}")
        if not 1 <= v.size_gib <= 16384:
            add("LX010", where, "size_gib must be 1-16384")
        if v.owner != "root" and v.owner not in users:
            add("LX009", where, f"owner '{v.owner}' is not a declared user")
        if v.group != "root" and v.group not in groups:
            add("LX009", where, f"group '{v.group}' is not a declared group")
        if not MODE_RE.match(v.mode):
            add("LX004", where, f"mode '{v.mode}' is not octal")
        elif _mode_bits(v.mode) & 0o002 and not _mode_bits(v.mode) & 0o1000:
            add("LX004", where, "world-writable mountpoint needs the sticky bit")

    return out
