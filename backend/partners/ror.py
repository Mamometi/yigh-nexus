"""Research Organization Registry (ROR) v2 API client with a 30-day cache."""
from __future__ import annotations

import json
from datetime import timedelta
from urllib.parse import urlencode

from sqlalchemy import select

from .models import LookupCache
from .store import now

API = "https://api.ror.org/v2/organizations"
TTL = timedelta(days=30)


def _simplify(item: dict) -> dict:
    loc = (item.get("locations") or [{}])[0].get("geonames_details", {})
    names = [n["value"] for n in item.get("names", [])]
    display = next((n["value"] for n in item.get("names", []) if "ror_display" in n.get("types", [])), names[0] if names else None)
    site = next((l["value"] for l in item.get("links", []) if l.get("type") == "website"), None)
    return {"id": item["id"], "name": display, "names": names, "types": item.get("types", []), "country": loc.get("country_name"),
            "country_code": loc.get("country_code"), "website": site, "status": item.get("status"),
            "ror_modified": item.get("admin", {}).get("last_modified", {}).get("date")}


class Ror:
    def __init__(self, db, fetcher):
        self.db, self.fetcher = db, fetcher

    def _get(self, params: dict) -> dict:
        url = f"{API}?{urlencode(params)}"
        hit = self.db.scalar(select(LookupCache).filter_by(key=url))
        if hit and now() - hit.retrieved_at < TTL:
            return json.loads(hit.response)
        data = self.fetcher.get(url, min_interval=1.0, check_robots=False).json()  # official API
        if hit:
            hit.response, hit.retrieved_at = json.dumps(data), now()
        else:
            self.db.add(LookupCache(key=url, response=json.dumps(data), retrieved_at=now()))
        self.db.flush()
        return data

    def match_affiliation(self, text: str) -> dict | None:
        """ROR's affiliation matcher; only its confident ('chosen') match is accepted."""
        data = self._get({"affiliation": text[:300]})
        for it in data.get("items", []):
            if it.get("chosen"):
                return _simplify(it["organization"])
        return None

    def search(self, query: str, country_code: str | None = None, types: list[str] | None = None, rows: int = 5) -> list[dict]:
        filters = []
        if country_code:
            filters.append(f"locations.geonames_details.country_code:{country_code}")
        if types:
            filters.append(",".join(f"types:{t}" for t in types))
        params = {"query": query}
        if filters:
            params["filter"] = ",".join(filters)
        data = self._get(params)
        return [_simplify(i) for i in data.get("items", [])[:rows] if i.get("status") == "active"]
