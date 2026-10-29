from grouptree.tree import is_uk_registered, normalise_number, pick_parent, walk_up


class FakeCH:
    """Stands in for the API so the chain logic can be tested offline."""

    def __init__(self, companies):
        self.companies = companies

    def profile(self, number):
        c = self.companies.get(number)
        return {"company_name": c["name"], "company_status": c.get("status", "active")} if c else None

    def pscs(self, number):
        return self.companies.get(number, {}).get("pscs", [])


def corp(name, number, country="England And Wales", nature="ownership-of-shares-75-to-100-percent", ceased=None):
    p = {
        "kind": "corporate-entity-person-with-significant-control",
        "name": name,
        "natures_of_control": [nature],
        "identification": {"registration_number": number, "country_registered": country,
                           "place_registered": "Companies House"},
    }
    if ceased:
        p["ceased_on"] = ceased
    return p


def person(name, nature="ownership-of-shares-75-to-100-percent"):
    return {"kind": "individual-person-with-significant-control", "name": name,
            "natures_of_control": [nature], "country_of_residence": "England"}


def test_normalise_number():
    assert normalise_number("519500") == "00519500"
    assert normalise_number("SC 123456") == "SC123456"
    assert normalise_number("oc12345") == "OC012345"
    assert normalise_number("HRB 12345") is None
    assert normalise_number("") is None


def test_uk_detection_ignores_ukraine():
    assert is_uk_registered({"country_registered": "England And Wales"})
    assert is_uk_registered({"country_registered": "United Kingdom"})
    assert is_uk_registered({"place_registered": "Registrar of Companies for Scotland"})
    assert not is_uk_registered({"country_registered": "Ukraine"})
    assert not is_uk_registered({"country_registered": "Luxembourg", "place_registered": "RCS Luxembourg"})


def test_three_level_chain_to_foreign_parent():
    ch = FakeCH({
        "00000003": {"name": "OPCO LTD", "pscs": [corp("MIDCO LTD", "2")]},
        "00000002": {"name": "MIDCO LTD", "pscs": [corp("TOPCO LTD", "1")]},
        "00000001": {"name": "TOPCO LTD", "pscs": [corp("GLOBAL SARL", "B123", country="Luxembourg")]},
    })
    r = walk_up(ch, "00000003")
    assert [c["name"] for c in r["chain"]] == ["OPCO LTD", "MIDCO LTD", "TOPCO LTD"]
    assert r["ultimate_uk"]["number"] == "00000001"
    assert r["top"] == {"type": "foreign company", "name": "GLOBAL SARL", "country": "Luxembourg"}


def test_individual_owner_and_standalone():
    ch = FakeCH({
        "00000010": {"name": "SOLO LTD", "pscs": [person("Jane Smith")]},
        "00000011": {"name": "NOBODY LTD", "pscs": []},
    })
    assert walk_up(ch, "00000010")["top"]["type"] == "individual"
    assert walk_up(ch, "00000011")["top"]["type"] == "standalone (no corporate parent)"


def test_ceased_psc_ignored_and_majority_wins():
    pscs = [
        corp("OLD PARENT LTD", "5", ceased="2020-01-01"),
        corp("MINORITY LTD", "6", nature="ownership-of-shares-25-to-50-percent"),
        corp("MAJORITY LTD", "7", nature="ownership-of-shares-50-to-75-percent"),
    ]
    kind, p = pick_parent(pscs)
    assert kind == "corporate" and p["name"] == "MAJORITY LTD"


def test_loop_is_caught():
    ch = FakeCH({
        "00000020": {"name": "A LTD", "pscs": [corp("B LTD", "21")]},
        "00000021": {"name": "B LTD", "pscs": [corp("A LTD", "20")]},
    })
    r = walk_up(ch, "00000020")
    assert "ownership loop" in r["flags"]


def test_dissolved_parent_flagged():
    ch = FakeCH({
        "00000030": {"name": "CHILD LTD", "pscs": [corp("DEAD PARENT LTD", "31")]},
        "00000031": {"name": "DEAD PARENT LTD", "status": "dissolved", "pscs": []},
    })
    r = walk_up(ch, "00000030")
    assert any("dissolved" in f for f in r["flags"])
