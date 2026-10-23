# -*- coding: utf-8 -*-
"""Classic setuptools entry point — kept in sync with pyproject.toml on purpose.

Why both files exist:
Some skill-store / marketplace upload parsers keep only a whitelist of file
extensions and silently drop the rest. A real upload was observed to preserve
every ``.py`` / ``.json`` / ``.md`` / ``.txt`` file but discard
``pyproject.toml`` (``.toml``) and the extension-less ``LICENSE``.

Without ``pyproject.toml`` a modern ``pip install`` still works via this file,
so the ``book-to-comic`` command is always registered no matter which config
survives. Locally, pip prefers ``pyproject.toml`` (PEP 517); in a stripped
environment it falls back here. Metadata, dependencies and console_scripts are
identical in both — when you change a dependency, the version or a command
entry, update BOTH files.
"""
from pathlib import Path

from setuptools import setup

HERE = Path(__file__).parent


def _long_description() -> str:
    try:
        return (HERE / "README.md").read_text(encoding="utf-8")
    except OSError:
        return "Turn a book into a Chinese serialized comic. No model API key required."


setup(
    name="book-to-comic",
    version="5.13.6",
    description=(
        "Host-native Agent Skill that turns a book into a serialized comic "
        "(research, adaptation, paneling, lettering, delivery) in zh-CN or en with no model API key required."
    ),
    long_description=_long_description(),
    long_description_content_type="text/markdown",
    author="onebluecloud",
    license="MIT",
    python_requires=">=3.10",
    packages=["book_to_comic"],
    include_package_data=True,
    package_data={
        "book_to_comic": ["presets/*.json", "schemas/*.json", "prompt_templates/*.md"],
    },
    # Pillow floor excludes the GHSA-pwv6-vv43-88gr / GHSA-whj4-6x5x-4v2j range.
    # pypdf/python-docx ship by default: PDF/DOCX upload is a first-screen capability.
    install_requires=[
        "Pillow>=12.3,<13",
        "jsonschema>=4.18",
        "pypdf>=4.0",
        "python-docx>=1.1",
    ],
    extras_require={
        # Domestic (Cherry Studio / MCP) leg only. The Codex skill does not need this.
        "mcp": ["mcp>=1.27,<2"],
    },
    entry_points={
        "console_scripts": [
            "book-to-comic=book_to_comic.cli:main",
            "book-to-comic-mcp=book_to_comic.mcp_server:main",
        ],
    },
    keywords=["comic", "manga", "book-adaptation", "agent-skill", "codex", "claude", "chinese"],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Natural Language :: Chinese (Simplified)",
    ],
)
