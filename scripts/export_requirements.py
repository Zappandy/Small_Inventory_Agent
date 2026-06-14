from pathlib import Path
import tomllib

pyproject = tomllib.loads(Path("pyproject.toml").read_text())
deps = pyproject["project"]["dependencies"]

header = """# Generated from pyproject.toml.
# Do not edit by hand.
# Local development uses: uv sync
# Regenerate after dependency changes with:
#   python3 scripts/export_requirements.py

"""

Path("requirements.txt").write_text(header + "\n".join(deps) + "\n")
print("Wrote requirements.txt from pyproject.toml")
