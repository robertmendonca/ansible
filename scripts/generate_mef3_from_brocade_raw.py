#!/usr/bin/env python3
import re
import sys
import zlib
from pathlib import Path
from datetime import datetime

FIELD_SEP = "|"

# MEF3 fixed fields
ASSET_CLASS = "S"
CATEGORY = "SAN"  # you requested SAN vs Storage separation

RE_KV = re.compile(r"^([^:]+):\s*(.*)$")
RE_PROMPT = re.compile(r":\S+>\s*$")

def norm(s: str) -> str:
    return (s or "").strip()

def parse_userconfig(text: str):
    """
    Parses Brocade `userconfig --show -a` output into list of dicts.
    """
    # remove device prompt line(s) if present
    lines = []
    for ln in text.splitlines():
        if RE_PROMPT.search(ln):
            continue
        lines.append(ln.rstrip("\n"))

    blocks = []
    cur = []
    for ln in lines:
        if ln.strip() == "" and cur:
            blocks.append(cur)
            cur = []
            continue
        if ln.strip() != "":
            cur.append(ln)
    if cur:
        blocks.append(cur)

    users = []
    for blk in blocks:
        data = {}
        for ln in blk:
            m = RE_KV.match(ln.strip())
            if not m:
                continue
            k = norm(m.group(1)).lower()
            v = norm(m.group(2))
            data[k] = v

        if "account name" not in data:
            continue

        username = data.get("account name", "")
        desc = data.get("description", "")
        enabled = data.get("enabled", "").lower()
        locked = data.get("locked", "").lower()
        role = data.get("role", "")

        status = "enable"
        if enabled not in ("yes", "true", "enabled") or locked in ("yes", "true", "locked"):
            status = "disable"

        users.append({
            "username": username,
            "description": desc,
            "status": status,
            "role": role,
        })
    return users

def mef3_line(customer, asset_id, username, identity, status, role):
    # 11 fields
    fields = [
        customer,                 # 1
        ASSET_CLASS,              # 2
        asset_id,                 # 3
        CATEGORY,                 # 4
        username,                 # 5
        "",                       # 6
        identity,                 # 7
        status,                   # 8
        "",                       # 9
        role,                     # 10
        role,                     # 11
    ]
    return FIELD_SEP.join(fields)

def write_mef3_for_raw_file(raw_file: Path, out_dir: Path):
    # raw file includes header lines we wrote (###)
    content = raw_file.read_text(encoding="utf-8", errors="replace")
    header = {}
    body_lines = []
    for ln in content.splitlines():
        if ln.startswith("### "):
            # ### KEY=VALUE
            kv = ln[4:].split("=", 1)
            if len(kv) == 2:
                header[kv[0].strip()] = kv[1].strip()
        else:
            body_lines.append(ln)

    customer = header.get("CUSTOMER", "").strip()
    asset_id = header.get("HOST", raw_file.stem).strip()
    ts = header.get("TS", datetime.utcnow().strftime("%Y%m%d%H%M%S")).strip()

    users = parse_userconfig("\n".join(body_lines))

    # Build lines
    lines = []
    for u in users:
        identity = re.sub(r"\s+", " ", (u["description"] or "").strip())
        lines.append(mef3_line(customer, asset_id, u["username"], identity, u["status"], u["role"]))

    # checksum over user lines only (stable)
    payload = ("\n".join(lines) + "\n").encode("utf-8")
    cksum = zlib.adler32(payload) & 0xFFFFFFFF

    # trailer (NOTaRealID)
    trailer_meta = f"000/V///{ts}:CKSUM={cksum}:SUDO=NotAvailable"
    trailer = mef3_line(customer, asset_id, "NOTaRealID", trailer_meta, "", f"--customer {customer}#")
    lines.append(trailer)

    # output file name
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{customer}-SAN_{asset_id}_{ts}.mef3"
    out_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_file, len(users)

def main():
    if len(sys.argv) < 3:
        print("Usage: generate_mef3_from_brocade_raw.py <raw_dir> <mef3_out_dir>")
        sys.exit(1)

    raw_dir = Path(sys.argv[1]).expanduser().resolve()
    out_dir = Path(sys.argv[2]).expanduser().resolve()

    raw_files = sorted(raw_dir.rglob("*.userconfig.txt"))
    if not raw_files:
        raise SystemExit(f"No raw files found under: {raw_dir}")

    total = 0
    for rf in raw_files:
        out_file, n_users = write_mef3_for_raw_file(rf, out_dir)
        print(f"OK  {rf}  ->  {out_file.name}  (users={n_users})")
        total += 1

    print(f"Generated {total} MEF3 file(s) into: {out_dir}")

if __name__ == "__main__":
    main()
