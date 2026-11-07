"""Put this family's projects in the pool and register its health checks.

RESET_FAILED=true (Setup input reset_failed) puts failed queue items back to pending once, for example after a
fix in the task; otherwise failed items stay as they are.

Run by the Setup workflow (Actions -> setup): the hub trusts this repo through its
OIDC token; no secrets. Safe to re-run: queue items that exist are kept."""
import os

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
    if p.get("max_workers") is not None:
        kw["max_workers"] = p["max_workers"]
    if p.get("pool") is not None:
        kw["pool"] = p["pool"]
    if p.get("delay_ms") is not None:
        kw["delay_ms"] = p["delay_ms"]
    set_pool(p["name"], FAMILY, p["task"], target=p["target"], env=p["env"], probe=p["probe"], **kw)
    if items:
        reset = os.environ.get("RESET_FAILED", "").lower() == "true"
        print(p["name"], "queue:", seed_queue(p["name"], items, reset_failed=reset))
    else:
        print(p["name"], "registered with an empty queue")
