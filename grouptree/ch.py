"""Small Companies House API client with caching and rate limiting."""
import time
from urllib.parse import quote

import requests

API = "https://api.company-information.service.gov.uk"


class CompaniesHouse:
    """Talks to the Companies House public data API.

    The API allows 600 requests per 5 minutes, so we pause ~0.55s between calls
    and back off for a minute if we get a 429.
    """

    def __init__(self, api_key, pause=0.55):
        self.session = requests.Session()
        self.session.auth = (api_key, "")
        self.pause = pause
        self.cache = {}

    def _get(self, path):
        if path in self.cache:
            return self.cache[path]
        for _ in range(5):
            resp = self.session.get(API + path, timeout=30)
            time.sleep(self.pause)
            if resp.status_code == 429:
                print("  rate limited, waiting 60s...")
                time.sleep(60)
                continue
            if resp.status_code == 404:
                self.cache[path] = None
                return None
            resp.raise_for_status()
            self.cache[path] = resp.json()
            return self.cache[path]
        raise RuntimeError(f"Gave up on {path} after repeated rate limits")

    def profile(self, number):
        return self._get(f"/company/{number}")

    def pscs(self, number):
        data = self._get(f"/company/{number}/persons-with-significant-control?items_per_page=100")
        return (data or {}).get("items", [])

    def search(self, name):
        data = self._get(f"/search/companies?q={quote(name)}&items_per_page=5")
        return (data or {}).get("items", [])
