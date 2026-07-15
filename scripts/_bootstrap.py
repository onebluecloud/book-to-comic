from __future__ import annotations

import sys
from pathlib import Path


def add_project_root() -> None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "book_to_comic").is_dir():
            sys.path.insert(0, str(parent))
            return
