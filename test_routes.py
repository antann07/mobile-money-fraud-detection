"""Quick test: verify all key endpoints are reachable."""
import urllib.request, urllib.error

endpoints = [
    "/api/health",
    "/api/reviews/flagged",
    "/api/wallet",
    "/api/transactions",
    "/api/predictions",
    "/api/message-checks/history",
]

for ep in endpoints:
    url = f"http://127.0.0.1:5001{ep}"
    try:
        r = urllib.request.urlopen(urllib.request.Request(url))
        print(f"{ep}: {r.status}")
    except urllib.error.HTTPError as e:
        print(f"{ep}: {e.code}")
    except Exception as e:
        print(f"{ep}: ERROR - {e}")
