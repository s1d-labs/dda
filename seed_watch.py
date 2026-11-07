"""Put this week's change-watch item into project dda-watch (run by .github/workflows/watch.yml every week).

The key is the ISO week ('watch-2026-W45'), so a second run in the same week adds nothing. The hub then gives
the item to a pool worker with an India proxy (task 'watch', watch.py)."""
import time

from scrape_hub_client import seed_queue

week = time.strftime("%G-W%V", time.gmtime())
print("dda-watch queue:", seed_queue("dda-watch", [{"key": f"watch-{week}", "payload": {"type": "watch", "week": week,
                                                                                       "expected": 1}}]))
