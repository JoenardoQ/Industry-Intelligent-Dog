"""Export the deterministic local API contract without touching production data."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    with tempfile.TemporaryDirectory(prefix="intdog-openapi-") as temp:
        os.environ["DOMAIN_INTEL_DATA_ROOT"] = temp
        os.environ["INTDOG_PROJECT_ROOT"] = str(project_root)
        from DomainIntelWeb.api.main import app

        output = project_root / "DomainIntelWeb" / "openapi.json"
        output.write_text(
            json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(output)


if __name__ == "__main__":
    main()
