"""Load a baseline spec into typed objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class SpecError(ValueError):
    """Raised when the spec cannot be parsed into the expected shape."""


@dataclass(frozen=True)
class Group:
    name: str
    gid: int


@dataclass(frozen=True)
class User:
    name: str
    uid: int
    primary_group: str
    groups: tuple[str, ...] = ()
    shell: str = "/bin/bash"
    comment: str = ""
    system_like: bool = False
    extra: tuple[str, ...] = ()


@dataclass(frozen=True)
class PathEntry:
    path: str
    owner: str
    group: str
    mode: str
    content: str | None = None


@dataclass(frozen=True)
class SudoRule:
    group: str
    commands: tuple[str, ...]
    run_as: str = "root"


@dataclass(frozen=True)
class Volume:
    label: str
    mountpoint: str
    filesystem: str = "ext4"
    size_gib: int = 5
    device_hint: str = ""
    owner: str = "root"
    group: str = "root"
    mode: str = "0755"
    options: tuple[str, ...] = ("defaults", "nofail")


@dataclass
class Spec:
    version: int
    host: str
    groups: list[Group] = field(default_factory=list)
    users: list[User] = field(default_factory=list)
    directories: list[PathEntry] = field(default_factory=list)
    files: list[PathEntry] = field(default_factory=list)
    sudo_rules: list[SudoRule] = field(default_factory=list)
    volume: Volume | None = None

    def group_ids(self) -> dict[str, int]:
        """Every resolvable group, including per-user private groups."""
        ids = {g.name: g.gid for g in self.groups}
        for u in self.users:
            if u.primary_group == u.name and u.name not in ids:
                ids[u.name] = u.uid
        return ids

    def user_ids(self) -> dict[str, int]:
        return {u.name: u.uid for u in self.users}


_USER_KEYS = {"name", "uid", "primary_group", "groups", "shell", "comment", "system_like"}


def _req(d: dict[str, Any], key: str, where: str) -> Any:
    if key not in d:
        raise SpecError(f"{where}: missing required key '{key}'")
    return d[key]


def _list(raw: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = raw.get(key) or []
    if not isinstance(value, list) or not all(isinstance(i, dict) for i in value):
        raise SpecError(f"'{key}' must be a list of mappings")
    return value


def _mode(value: Any, where: str) -> str:
    if isinstance(value, int):
        raise SpecError(f'{where}: mode must be a quoted octal string, e.g. "0750"')
    return str(value)


def parse(raw: Any) -> Spec:
    if not isinstance(raw, dict):
        raise SpecError("spec root must be a mapping")
    spec = Spec(version=int(raw.get("version", 0)), host=str(raw.get("host", "")))
    for i, g in enumerate(_list(raw, "groups")):
        where = f"groups[{i}]"
        spec.groups.append(Group(str(_req(g, "name", where)), int(_req(g, "gid", where))))
    for i, u in enumerate(_list(raw, "users")):
        where = f"users[{i}]"
        spec.users.append(
            User(
                name=str(_req(u, "name", where)),
                uid=int(_req(u, "uid", where)),
                primary_group=str(_req(u, "primary_group", where)),
                groups=tuple(str(x) for x in u.get("groups", []) or []),
                shell=str(u.get("shell", "/bin/bash")),
                comment=str(u.get("comment", "")),
                system_like=bool(u.get("system_like", False)),
                extra=tuple(sorted(set(u) - _USER_KEYS)),
            )
        )
    for key, target in (("directories", spec.directories), ("files", spec.files)):
        for i, p in enumerate(_list(raw, key)):
            where = f"{key}[{i}]"
            target.append(
                PathEntry(
                    path=str(_req(p, "path", where)),
                    owner=str(_req(p, "owner", where)),
                    group=str(_req(p, "group", where)),
                    mode=_mode(_req(p, "mode", where), where),
                    content=p.get("content") if key == "files" else None,
                )
            )
    for i, s in enumerate(_list(raw, "sudo_rules")):
        where = f"sudo_rules[{i}]"
        spec.sudo_rules.append(
            SudoRule(
                group=str(_req(s, "group", where)),
                commands=tuple(str(c) for c in _req(s, "commands", where)),
                run_as=str(s.get("run_as", "root")),
            )
        )
    vol = raw.get("volume")
    if vol is not None:
        if not isinstance(vol, dict):
            raise SpecError("'volume' must be a mapping")
        spec.volume = Volume(
            label=str(_req(vol, "label", "volume")),
            mountpoint=str(_req(vol, "mountpoint", "volume")),
            filesystem=str(vol.get("filesystem", "ext4")),
            size_gib=int(vol.get("size_gib", 5)),
            device_hint=str(vol.get("device_hint", "")),
            owner=str(vol.get("owner", "root")),
            group=str(vol.get("group", "root")),
            mode=_mode(vol.get("mode", "0755"), "volume"),
            options=tuple(str(o) for o in vol.get("options", ["defaults", "nofail"])),
        )
    return spec


def load(path: str | Path) -> Spec:
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SpecError(f"invalid YAML: {exc}") from exc
    return parse(raw)
