"""Compare src/skill_router/catalog.py with the skills installed on this machine. Report only, writes nothing.

    python -m src.tools.check_catalog

Reads SKILL.md files from installed plugins, ~/.claude/skills and the .claude/skills of this folder and its
parents. `missing` = installed but not in the catalog (never suggested). `unverified` = in the catalog but
not found on disk; built-in and remote skills (code-review, loop, anthropic-skills:*) legitimately show up
here, so check those by hand.
"""
import glob
import json
import os

from ..skill_router.catalog import SKILLS

HOME = os.path.join(os.path.expanduser("~"), ".claude")
PLUGIN_DIRS = [os.path.join(HOME, "plugins", "cache"), os.path.join(HOME, "plugins", "marketplaces")]


def installed_plugins() -> dict[str, str]:
    """{plugin name: install path}."""
    path = os.path.join(HOME, "plugins", "installed_plugins.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        plugins = json.load(f).get("plugins", {})
    return {key.split("@")[0]: entries[0]["installPath"] for key, entries in plugins.items() if entries}


def skill_names(skills_dir: str, prefix: str = "") -> set[str]:
    return {prefix + os.path.basename(os.path.dirname(p))
            for p in glob.glob(os.path.join(skills_dir, "*", "SKILL.md"))}


def installed() -> set[str]:
    found = skill_names(os.path.join(HOME, "skills"))
    for name, path in installed_plugins().items():
        found |= skill_names(os.path.join(path, "skills"), f"{name}:")
    folder = os.getcwd()
    while True:
        found |= skill_names(os.path.join(folder, ".claude", "skills"))
        parent = os.path.dirname(folder)
        if parent == folder:
            return found
        folder = parent


def main():
    catalog = {name for name, _ in SKILLS}
    found = installed()
    for label, names in (("missing from catalog", found - catalog), ("unverified (not on disk)", catalog - found)):
        print(f"\n{label}: {len(names)}")
        for name in sorted(names):
            print(f"  {name}")
    print(f"\ncatalog {len(catalog)}, installed on disk {len(found)}")


if __name__ == "__main__":
    main()
