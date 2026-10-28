"""Print the OpenAPI document; the docs site embeds it."""

import json
import sys

if __name__ == "__main__":
    from app.main import app

    json.dump(app.openapi(), sys.stdout, indent=2)
    sys.stdout.write("\n")
