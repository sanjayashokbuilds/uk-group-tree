"""Walk Companies House PSC records up to each company's ultimate parent."""
import re

UK_WORDS = ("england", "wales", "scotland", "northern ireland", "united kingdom", "uk", "great britain")
UK_PLACES = ("companies house", "register of companies", "registrar of companies")

# How strongly each nature of control points to a parent. Higher wins.
CONTROL_RANK = [
    ("ownership-of-shares-75-to-100-percent", 4),
    ("ownership-of-shares-more-than-50-percent", 3),
    ("ownership-of-shares-50-to-75-percent", 3),
    ("right-to-appoint-and-remove-directors", 2),
    ("voting-rights-75-to-100-percent", 2),
    ("ownership-of-shares-25-to-50-percent", 1),
    ("significant-influence-or-control", 1),
]

MAX_DEPTH = 12


def normalise_number(raw):
    """Turn a registration number as typed on a PSC record into a Companies House number.

    '519500' -> '00519500', 'SC 123456' -> 'SC123456'. Returns None if it doesn't look valid.
    """
    if not raw:
        return None
    s = re.sub(r"[^A-Za-z0-9]", "", str(raw)).upper()
    m = re.fullmatch(r"([A-Z]{2})(\d{1,6})", s)
    if m:
        return m.group(1) + m.group(2).zfill(6)
    if s.isdigit() and len(s) <= 8:
        return s.zfill(8)
    return None


UK_PATTERN = re.compile(r"\b(" + "|".join(UK_WORDS) + r")\b")


def is_uk_registered(ident):
    """PSC identification fields are free text, so we look for UK words as whole words
    (so 'Ukraine' doesn't count) or a mention of Companies House."""
    country = str(ident.get("country_registered") or "").lower().strip()
    if country:
        # A stated country wins over the other free-text fields.
        return bool(UK_PATTERN.search(country))
    text = " ".join(str(ident.get(k) or "") for k in ("place_registered", "legal_authority")).lower()
    return any(p in text for p in UK_PLACES) or bool(UK_PATTERN.search(text))


def control_score(psc):
    natures = psc.get("natures_of_control", [])
    best = 0
    for nature in natures:
        for key, rank in CONTROL_RANK:
            if nature.startswith(key):
                best = max(best, rank)
    return best


def active(pscs):
    return [p for p in pscs if not p.get("ceased_on") and not p.get("ceased")]


def pick_parent(pscs):
    """Return (kind, psc) for the controlling parent, or (None, None).

    kind is 'corporate', 'individual', 'legal' or None. Corporate parents win ties
    because that's the link that continues the chain.
    """
    candidates = []
    for p in active(pscs):
        kind = p.get("kind", "")
        if "corporate-entity" in kind:
            k = "corporate"
        elif "individual" in kind:
            k = "individual"
        elif "legal-person" in kind:
            k = "legal"
        else:
            continue
        candidates.append((control_score(p), k == "corporate", k, p))
    if not candidates:
        return None, None
    candidates.sort(key=lambda c: (c[0], c[1]), reverse=True)
    _, _, kind, psc = candidates[0]
    return kind, psc


def walk_up(ch, number):
    """Follow the controlling corporate PSC from `number` until we hit the top.

    Returns a dict describing the chain and who sits at the top.
    """
    chain = []
    flags = []
    seen = set()
    current = number
    top = {"type": "unknown", "name": "", "country": ""}

    for _ in range(MAX_DEPTH):
        if current in seen:
            flags.append("ownership loop")
            break
        seen.add(current)
        prof = ch.profile(current)
        if not prof:
            flags.append(f"{current} not found")
            break
        chain.append({
            "number": current,
            "name": prof.get("company_name", ""),
            "status": prof.get("company_status", ""),
        })
        if prof.get("company_status") not in (None, "active"):
            flags.append(f"{prof.get('company_name')} is {prof.get('company_status')}")

        kind, psc = pick_parent(ch.pscs(current))
        if kind is None:
            top = {"type": "no controlling PSC on register", "name": "", "country": ""}
            break
        if kind == "individual":
            top = {"type": "individual", "name": psc.get("name", ""), "country": psc.get("country_of_residence", "")}
            break
        if kind == "legal":
            top = {"type": "legal person", "name": psc.get("name", ""), "country": ""}
            break

        ident = psc.get("identification", {}) or {}
        parent_no = normalise_number(ident.get("registration_number"))
        if is_uk_registered(ident) and parent_no:
            current = parent_no
            continue
        top = {
            "type": "foreign company" if not is_uk_registered(ident) else "UK company (number missing)",
            "name": psc.get("name", ""),
            "country": ident.get("country_registered") or ident.get("place_registered", ""),
        }
        break
    else:
        flags.append("chain longer than limit")

    if len(chain) == 1 and top["type"] == "no controlling PSC on register":
        top["type"] = "standalone (no corporate parent)"

    ultimate_uk = chain[-1] if chain else {"number": "", "name": ""}
    return {"chain": chain, "ultimate_uk": ultimate_uk, "top": top, "flags": flags}
