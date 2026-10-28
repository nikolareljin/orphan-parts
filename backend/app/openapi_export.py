"""Print the OpenAPI document; the docs site embeds it."""

import json
import sys

from app.main import app

if __name__ == "__main__":
    json.dump(app.openapi(), sys.stdout, indent=2)
    sys.stdout.write("\n")
