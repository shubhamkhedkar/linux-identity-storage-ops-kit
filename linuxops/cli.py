"""Command line entry point: validate, plan, render, fstab."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from linuxops import policy, render
from linuxops.spec import SpecError, load


def _load_valid(path: str):
    spec = load(path)
    findings = policy.evaluate(spec)
    return spec, findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="linuxops", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("validate", "plan", "fstab"):
        p = sub.add_parser(name)
        p.add_argument("spec")
    p_render = sub.add_parser("render")
    p_render.add_argument("spec")
    p_render.add_argument("kind", choices=["provision", "teardown"])
    p_render.add_argument("-o", "--output", help="write to file (mode 0750) instead of stdout")
    sub.choices["fstab"].add_argument("--uuid", default="<UUID>")
    args = parser.parse_args(argv)

    try:
        spec, findings = _load_valid(args.spec)
    except (OSError, SpecError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if findings:
        for f in findings:
            print(f, file=sys.stderr)
        print(f"{len(findings)} policy finding(s); nothing rendered", file=sys.stderr)
        return 1

    if args.cmd == "validate":
        print(
            f"OK {args.spec}: {len(spec.users)} users, {len(spec.groups)} groups, "
            f"{len(spec.directories) + len(spec.files)} paths, {len(spec.sudo_rules)} sudo rules"
        )
        return 0
    if args.cmd == "plan":
        sys.stdout.write(render.plan(spec))
        return 0
    if args.cmd == "fstab":
        print(render.fstab_line(spec, args.uuid))
        return 0
    text = render.provision(spec) if args.kind == "provision" else render.teardown(spec)
    if args.output:
        out = Path(args.output)
        out.write_text(text, encoding="utf-8")
        out.chmod(0o750)
    else:
        sys.stdout.write(text)
    return 0
