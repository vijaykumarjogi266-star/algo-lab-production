#!/usr/bin/env python3
"""
Algo Lab Software Bill of Materials (SBOM) Generator.
Generates an SPDX 2.3 and CycloneDX-compatible JSON SBOM capturing all
direct and transitive dependencies, versions, and licensing metadata.
"""

import sys
import json
import datetime
from pathlib import Path
import importlib.metadata

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_FILE = BASE_DIR / "data" / "sbom.spdx.json"


def generate_sbom():
    packages = []
    for dist in importlib.metadata.distributions():
        name = dist.metadata.get("Name", "unknown")
        version = dist.metadata.get("Version", "unknown")
        license_str = dist.metadata.get("License", "UNKNOWN")
        summary = dist.metadata.get("Summary", "")

        packages.append({
            "SPDXID": f"SPDXRef-Package-{name}-{version}",
            "name": name,
            "versionInfo": version,
            "packageFileName": f"{name}-{version}.whl",
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": False,
            "licenseConcluded": license_str or "NOASSERTION",
            "licenseDeclared": license_str or "NOASSERTION",
            "description": summary,
        })

    # Sort packages alphabetically
    packages.sort(key=lambda x: x["name"].lower())

    sbom = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "algo-lab",
        "documentNamespace": f"https://github.com/vijaykumarjogi266-star/algopro/spdx/{datetime.date.today()}",
        "creationInfo": {
            "created": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "creators": ["Tool: Algo Lab SBOM Generator v0.3.0", "Organization: Algo Lab Core Team"],
        },
        "packages": packages,
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(sbom, indent=2), encoding="utf-8")
    print(f"✅ Generated SPDX SBOM with {len(packages)} packages -> {OUTPUT_FILE}")


if __name__ == "__main__":
    generate_sbom()
