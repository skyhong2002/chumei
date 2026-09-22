"""Separate mutable build inputs from the atomically published website."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def build_site_dir():
    """A publisher child writes only its private staging directory."""
    return Path(os.environ.get("CHUMEI_BUILD_DIR", ROOT / "site"))


def published_site_dir():
    """Keep the symlink unresolved so long-lived services follow later releases.

    Legacy installations work until their first publication. Restart readers once
    when activating publication; after that no restart is needed per release.
    A broken publication symlink deliberately does not fall back to draft data.
    """
    current = ROOT / "published" / "current"
    return current if current.is_symlink() else ROOT / "site"
