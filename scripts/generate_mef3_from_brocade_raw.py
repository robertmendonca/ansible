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
RE_GECOS_LIKE = re.compile(r"^[A-Z]{2}/[KF]/.+/.+/.+$")

def norm(s: str) -> str:
    return (s or "").strip()

def load_gecos_map(gecos_path: Path):
    """
    Builds lookup maps from gecos.txt.
    - by_user: maps the 3rd segment for PT/K/<id>/... (often the user id) -> full line
    - by_tail: maps the last segment (after last '/') -> full line
    """
    by_user = {}
    by_tail = {}
    if not gecos_path.exists():
        return by_user, by_tail

    for ln in gecos_path.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        parts = [p.strip() for p in ln.split("/")]
        if len(parts) < 5:
            continue

        tail = parts[-1].strip().lower()
        by_tail[tail] = ln

        # PT/K/<id>/ORG/Name
        if parts[1].strip().upper() == "K":
            user_id = parts[2].strip().lower()
            if user_id:
                by_user[user_id] = ln

    return by_user, by_tail

def resolve_identity(customer: str, username: str, description: str, by_user: dict, by_tail: dict) -> str:
    """
    Returns a normalized identity using gecos.txt when possible.
    Fallback keeps current behavior (description as identity).
    """
    u = (username or "").strip()
    # Brocade sometimes shows maintenance* etc.
    u_clean = u.rstrip("*").strip()
    u_key = u_clean.lower()

    d = (description or "").strip()
    d_key = d.lower()

    # 1) Direct by user id (PT/K/<id>/...)
    if u_key in by_user:
        return by_user[u_key]

    # 2) Match by "tail" token (e.g., root, superuser, autopuser...)
    if u_key in by_tail:
        return by_tail[u_key]

    # 3) Some environments put the tail in Description
    if d_key in by_tail:
        return by_tail[d_key]

    # 4) If device already has a gecos-like string, keep it
    if RE_GECOS_LIKE.match(d):
        return d

    # 5) Final fallback: keep current behavior
    return re.sub(r"\s+", " ", d).strip()


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

def format_ts_for_trailer(ts: str) -> str:
    ts = (ts or "").strip()
    # Esperado: 20260212213431 (YYYYmmddHHMMSS)
    if re.fullmatch(r"\d{14}", ts):
        return datetime.strptime(ts, "%Y%m%d%H%M%S").strftime("%Y-%m-%d-%H.%M.%S")
    return ts


def write_mef3_for_raw_file(raw_file: Path, out_dir: Path, by_user: dict, by_tail: dict):
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
    ts_raw = header.get("TS", datetime.utcnow().strftime("%Y%m%d%H%M%S")).strip()
    ts_trailer = format_ts_for_trailer(ts_raw)

    users = parse_userconfig("\n".join(body_lines))

    # Build lines
    lines = []
    for u in users:
        identity = resolve_identity(customer, u["username"], u["description"], by_user, by_tail)
        lines.append(mef3_line(customer, asset_id, u["username"], identity, u["status"], u["role"]))

     # trailer (NOTaRealID)
    out_path = r"C:\ansible\GTS\uidext\tricode_devicename_date.mef3"
    
    # 1) Linha 1 do trailer (apenas 7 campos)
    trailer_meta = (
        f"00/V///{ts_trailer}:FN=iam_extract.ps1:VER=V2.0.74:"
        f"CKSUM=3167295684|||#a:tricode#o:{out_path}"
    )
    
    trailer_line1 = FIELD_SEP.join([
        customer,                 # 1
        ASSET_CLASS,              # 2
        asset_id,                 # 3
        CATEGORY,                 # 4
        "NOTaRealID-Ansible",     # 5
        "",                       # 6
        trailer_meta,             # 7
    ])
    
    lines.append(trailer_line1)
    
    # 2) Linha 2 do trailer (FINAL_TS no formato pedido)
    final_ts = datetime.utcnow().strftime("%Y-%m-%d-%H.%M.%S")
    
    trailer_line2 = (
        f"#kyndrylonly #g:Ansible ### FINAL_TS={final_ts} "
        f"PROCNUM=1:PROCSPEED=2295:MEM=17179332608:NETWORK=10000000000 10000000000 10000000000|0|"
    )
    
    lines.append(trailer_line2)


    # output file name    
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{customer}-SAN_{asset_id}_{ts}.mef3"
    out_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # default gecos.txt at repo root (../gecos.txt relative to this script)
    gecos_path = (Path(__file__).resolve().parents[1] / "gecos.txt")
    by_user, by_tail = load_gecos_map(gecos_path)
    return out_file, len(users)

def main():
    if len(sys.argv) < 3:
        print("Usage: generate_mef3_from_brocade_raw.py <raw_dir> <mef3_out_dir>")
        sys.exit(1)

    raw_dir = Path(sys.argv[1]).expanduser().resolve()
    out_dir = Path(sys.argv[2]).expanduser().resolve() 
    
    # Carrega gecos.txt uma vez
    gecos_path = (Path(__file__).resolve().parents[1] / "gecos.txt")
    by_user, by_tail = load_gecos_map(gecos_path)

    raw_files = sorted(raw_dir.rglob("*.userconfig.txt"))
    if not raw_files:
        raise SystemExit(f"No raw files found under: {raw_dir}")

    total = 0
    for rf in raw_files:
        out_file, n_users = write_mef3_for_raw_file(rf, out_dir, by_user, by_tail)
        print(f"OK  {rf}  ->  {out_file.name}  (users={n_users})")
        total += 1

    print(f"Generated {total} MEF3 file(s) into: {out_dir}")

if __name__ == "__main__":
    main()
