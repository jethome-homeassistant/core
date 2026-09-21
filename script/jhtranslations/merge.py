#!/usr/bin/env python3
"""Merge distributed component translations into a single JSON file per language."""
from __future__ import annotations

import json
import pathlib

from .develop import flatten_translations

UPSTREAM_DIR = pathlib.Path("build/upstream-components")
DOWNLOAD_DIR = pathlib.Path("build/translations-download")


def merge_language_files() -> dict[str, dict]:
    """Merge component translation files by language."""
    merged: dict[str, dict] = {}

    for component_dir in UPSTREAM_DIR.iterdir():
        translations_dir = component_dir / "translations"
        if not translations_dir.is_dir():
            continue

        component = component_dir.name
        for file in translations_dir.glob("*.json"):
            stem = file.name[: -len(".json")]
            if "." in stem:
                platform, lang = stem.rsplit(".", 1)
            else:
                platform, lang = None, stem

            if lang == "en":
                # Source English strings are generated from the repository by upload
                continue

            data = json.loads(file.read_text())
            target = merged.setdefault(lang, {"component": {}})
            parent = target["component"].setdefault(component, {})
            if platform:
                parent = parent.setdefault("platform", {}).setdefault(platform, {})
            parent.update(data)

    return merged


def prune_translations(translations, source_keys, path=()):
    """Drop untranslated strings and keys missing in the source."""
    result = {}
    for key, value in translations.items():
        if isinstance(value, dict):
            sub_dict = prune_translations(value, source_keys, (*path, key))
            if sub_dict:
                result[key] = sub_dict
        elif value != "" and "::".join((*path, key)) in source_keys:
            result[key] = value
    return result


def run():
    """Run the script."""
    if not UPSTREAM_DIR.is_dir():
        print(f"Missing {UPSTREAM_DIR}, extract upstream components first")
        return 1

    source_file = DOWNLOAD_DIR / "en.json"
    if not source_file.is_file():
        print("Missing build/translations-download/en.json, run upload first")
        return 1
    source_keys = set(flatten_translations(json.loads(source_file.read_text())))

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    for lang, data in merge_language_files().items():
        data = prune_translations(data, source_keys)
        DOWNLOAD_DIR.joinpath(f"{lang}.json").write_text(
            json.dumps(data, indent=4, sort_keys=True)
        )
        print(f"Merged {lang}")

    return 0
