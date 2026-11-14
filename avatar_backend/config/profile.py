import os
import tomllib
from pathlib import Path


def load_profile():
    directory = os.getenv("ECA_CONFIG_DIR")
    if not directory:
        return {}, None
    root = Path(directory)
    with (root / "avatar.toml").open("rb") as stream:
        profile = tomllib.load(stream)
    return profile, root
