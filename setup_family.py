"""Put this family's projects in the pool and register its health checks.

Run by the Setup workflow (Actions -> setup): the hub trusts this repo through its
OIDC token; no secrets. Safe to re-run: queue items that exist are kept."""
from scrape_hub_client import register_project, seed_queue, set_pool, set_probes

from family import FAMILY, PROBES, PROJECTS

print("health checks:", set_probes(FAMILY, PROBES))

for p in PROJECTS:
    items = p["items"]
    register_project(
        p["name"], title=p["title"],
        unit_label=p["unit_label"], record_label=p["record_label"],
        expected_units=len(items),
        expected_records=sum(i["payload"].get("expected", 0) for i in items),
    )
    kw = {}
    if p.get("proxy"):
        kw["proxy"] = p["proxy"]
    set_pool(p["name"], FAMILY, p["task"], target=p["target"], env=p["env"], probe=p["probe"], **kw)
    if items:
        print(p["name"], "queue:", seed_queue(p["name"], items))
    else:
        print(p["name"], "registered with empty queue (run discover.py, then Setup again)")
