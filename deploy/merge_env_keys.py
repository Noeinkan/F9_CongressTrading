#!/usr/bin/env python3
"""Merge POLYGON_API_KEY and OPENFIGI_API_KEY from a source .env into a
destination .env on the VPS, preserving all other lines (dashboard bind,
password, comments) and the file's existing perms.

Reads /tmp/keys_source.env and writes /opt/F9_CongressTrading/.env.
Intended to be run once during the API key setup, then deleted.
"""
from __future__ import annotations

import os
import pwd
import grp
import re
import sys

SRC = "/tmp/keys_source.env"
DST = "/opt/F9_CongressTrading/.env"
KEYS = ("POLYGON_API_KEY", "OPENFIGI_API_KEY")


def main() -> int:
    with open(SRC, encoding="utf-8") as f:
        src = f.read()

    new_values: dict[str, str] = {}
    for line in src.splitlines():
        line = line.strip()
        for k in KEYS:
            prefix = f"{k}="
            if line.startswith(prefix):
                new_values[k] = line[len(prefix):]
                break

    if not new_values:
        print("FAIL: no API keys found in source", file=sys.stderr)
        return 1

    with open(DST, encoding="utf-8") as f:
        dst = f.read()

    for k, v in new_values.items():
        pattern = re.compile(rf"^{re.escape(k)}=.*$", re.MULTILINE)
        replacement = f"{k}={v}"
        if pattern.search(dst):
            dst = pattern.sub(replacement, dst)
        else:
            dst = dst.rstrip("\n") + f"\n{replacement}\n"

    with open(DST, "w", encoding="utf-8") as f:
        f.write(dst)

    # Belt-and-suspenders: assert the file stays deploy:deploy 0600.
    uid = pwd.getpwnam("deploy").pw_uid
    gid = grp.getgrnam("deploy").gr_gid
    os.chmod(DST, 0o600)
    os.chown(DST, uid, gid)

    print("merged:", sorted(new_values.keys()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
