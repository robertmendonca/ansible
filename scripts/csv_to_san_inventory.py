#!/usr/bin/env python3
import sys
import re
from pathlib import Path
import yaml

def norm(s: str) -> str:
    return (s or "").strip()

def safe_host(hostname: str) -> str:
    # Preserve underscores (your pattern relies on them)
    h = norm(hostname)
    h = re.sub(r"\s+", "_", h)  # whitespace -> underscore
    h = re.sub(r"[^A-Za-z0-9_.-]", "", h)
    return h

def is_ip(s: str) -> bool:
    parts = s.split(".")
    if len(parts) != 4:
        return False
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return False
    return all(0 <= n <= 255 for n in nums)

def split_line(line: str):
    line = line.strip()
    if not line:
        return None
    # Try common separators: comma, semicolon, tab, or multi-space
    if "\t" in line:
        parts = [p.strip() for p in line.split("\t") if p.strip() != ""]
    elif "," in line:
        parts = [p.strip() for p in line.split(",") if p.strip() != ""]
    elif ";" in line:
        parts = [p.strip() for p in line.split(";") if p.strip() != ""]
    else:
        parts = re.split(r"\s{2,}", line)  # 2+ spaces
        parts = [p.strip() for p in parts if p.strip() != ""]
    if len(parts) < 2:
        return None
    return parts[0], parts[1]

def looks_like_header(h, ip):
    return (h.lower() in ("hostname", "host", "name") and ip.lower() in ("ip", "ipaddress", "address"))

def main():
    if len(sys.argv) < 5 or sys.argv[3] != "--customer":
        print("Usage: csv_to_san_inventory.py <hosts.txt/csv/tsv> <output_inventory.yml> --customer <CUSTOMER>")
        sys.exit(1)

    in_path = Path(sys.argv[1]).expanduser().resolve()
    out_path = Path(sys.argv[2]).expanduser().resolve()
    customer = norm(sys.argv[4])
    if not customer:
        raise SystemExit("Customer cannot be empty")

    lines = in_path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    parsed = []
    for ln in lines:
        res = split_line(ln)
        if not res:
            continue
        parsed.append(res)

    if not parsed:
        raise SystemExit("No valid hostname/ip lines found")

    # Drop header if present
    if looks_like_header(parsed[0][0], parsed[0][1]):
        parsed = parsed[1:]

    hosts = {}
    for hostname_raw, ip_raw in parsed:
        hostname = safe_host(hostname_raw)
        ip = norm(ip_raw)
        if not hostname or not ip:
            continue
        if not is_ip(ip):
            raise SystemExit(f"Invalid IP: {ip} (hostname={hostname_raw})")

        hosts[hostname] = {
            "ansible_host": ip,
            "customer": customer,
            "category": "SAN",
        }

    inventory = {
        "all": {
            "children": {
                "san_brocade": {
                    "hosts": hosts
                }
            }
        }
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(yaml.safe_dump(inventory, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"Wrote {len(hosts)} hosts to: {out_path}")

if __name__ == "__main__":
    main()
