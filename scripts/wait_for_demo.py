from __future__ import annotations

import json
import time
from urllib.request import urlopen


SERVICES = {
    "RegressionForge": "http://localhost:4400/health",
    "ForgeCart": "http://localhost:4301/health",
    "Mailpit": "http://localhost:8025/api/v1/info",
}

for name, url in SERVICES.items():
    for attempt in range(90):
        try:
            with urlopen(url, timeout=2) as response:
                if response.status < 400:
                    print(f"{name}: ready")
                    break
        except Exception:
            if attempt == 89:
                raise RuntimeError(f"{name} did not become ready: {url}")
            time.sleep(1)

