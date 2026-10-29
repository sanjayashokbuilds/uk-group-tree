"""Usage:
    python -m grouptree --input companies.csv --out output/

The input CSV needs a column called company_number or company_name (or both).
Set your key first: export COMPANIES_HOUSE_API_KEY=...
"""
import argparse
import csv
import os
import sys
from collections import defaultdict

from .ch import CompaniesHouse
from .tree import normalise_number, owner_key, walk_up


def resolve(ch, row):
    """Work out the company number for an input row. Returns (number, note)."""
    num = normalise_number(row.get("company_number", ""))
    if num:
        return num, ""
    name = (row.get("company_name") or "").strip()
    if not name:
        return None, "empty row"
    hits = ch.search(name)
    if not hits:
        return None, "no match found"
    for h in hits:
        if h.get("title", "").lower() == name.lower():
            return h["company_number"], ""
    return hits[0]["company_number"], f"best guess match: {hits[0].get('title')}"


def main():
    ap = argparse.ArgumentParser(description="Map UK companies to their corporate families using Companies House PSC data.")
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", default="output")
    args = ap.parse_args()

    key = os.environ.get("COMPANIES_HOUSE_API_KEY")
    if not key:
        sys.exit("Set COMPANIES_HOUSE_API_KEY first.")
    ch = CompaniesHouse(key)
    os.makedirs(args.out, exist_ok=True)

    with open(args.input, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    results = []
    for i, row in enumerate(rows, 1):
        number, note = resolve(ch, row)
        label = row.get("company_name") or row.get("company_number")
        print(f"[{i}/{len(rows)}] {label}")
        if not number:
            results.append({"input": label, "note": note})
            continue
        r = walk_up(ch, number)
        r["input"] = label
        r["note"] = note
        results.append(r)

    groups = group_by_parent(results)
    write_csv(results, os.path.join(args.out, "families.csv"))
    write_tree(groups, os.path.join(args.out, "families.md"))
    shared = sum(1 for m in groups.values() if len(m) > 1)
    print(f"\nDone. {len(results)} companies, {len(groups)} families, {shared} families with 2+ of your companies.")
    print(f"See {args.out}/families.csv and {args.out}/families.md")


def group_by_parent(results):
    """Group companies by ultimate owner (see owner_key), so the same owner under
    slightly different names, or behind different UK holding companies, is one family."""
    groups = defaultdict(list)
    for r in results:
        if r.get("chain"):
            r["family_key"] = owner_key(r)
            groups[r["family_key"]].append(r)
    for members in groups.values():
        for m in members:
            m["family_size"] = len(members)
    return groups


def write_csv(results, path):
    cols = ["input", "company_number", "company_name", "status", "immediate_parent", "immediate_parent_number",
            "ultimate_uk_parent", "ultimate_uk_parent_number", "top_of_chain_type", "top_of_chain_name",
            "top_of_chain_country", "family_key", "family_size", "depth", "chain", "flags", "note"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in results:
            chain = r.get("chain") or []
            if not chain:
                w.writerow({"input": r["input"], "note": r.get("note", "")})
                continue
            parent = chain[1] if len(chain) > 1 else {"name": "", "number": ""}
            w.writerow({
                "input": r["input"],
                "company_number": chain[0]["number"],
                "company_name": chain[0]["name"],
                "status": chain[0]["status"],
                "immediate_parent": parent["name"],
                "immediate_parent_number": parent["number"],
                "ultimate_uk_parent": r["ultimate_uk"]["name"],
                "ultimate_uk_parent_number": r["ultimate_uk"]["number"],
                "top_of_chain_type": r["top"]["type"],
                "top_of_chain_name": r["top"]["name"],
                "top_of_chain_country": r["top"]["country"],
                "family_key": r.get("family_key", ""),
                "family_size": r.get("family_size", ""),
                "depth": len(chain) - 1,
                "chain": " > ".join(c["name"] for c in chain),
                "flags": "; ".join(r["flags"]),
                "note": r.get("note", ""),
            })


def write_tree(groups, path):
    order = sorted(groups.items(), key=lambda kv: -len(kv[1]))
    lines = ["# Corporate families", ""]
    for key, members in order:
        first = members[0]
        above = first["top"]
        if key.startswith("uk:"):
            lines.append(f"## {first['ultimate_uk']['name']} ({first['ultimate_uk']['number']})")
            lines.append(f"Top of chain: {above['type']}")
        else:
            lines.append(f"## {above['name']}")
            where = f", {above['country']}" if above["country"] else ""
            lines.append(f"Ultimate owner: {above['type']}{where}")
            names = sorted({m["top"]["name"] for m in members})
            if len(names) > 1:
                lines.append("Same owner recorded under different names: " + " / ".join(names) + " (matched on name, worth a check)")
            uk_parents = sorted({m["ultimate_uk"]["name"] for m in members})
            if len(uk_parents) > 1:
                lines.append("Reached through separate UK holding companies: " + ", ".join(uk_parents))
        lines.append("")
        for m in members:
            path_names = [c["name"] for c in reversed(m["chain"])]
            lines.append("- " + " → ".join(path_names))
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
