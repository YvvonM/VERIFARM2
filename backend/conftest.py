"""
Ensures the backend/ directory is on sys.path during pytest runs, so that
`from app.X import Y` resolves correctly regardless of which directory
pytest is invoked from. Without this, `app` is not importable as a
top-level package when running plain `pytest` (as opposed to
`python3 -m app.something`, which adds the current directory automatically).

Place this file directly in backend/, alongside main.py and requirements.txt.
pytest auto-discovers conftest.py files -- no import or registration needed.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

# The data-generation package is self-contained again: its synthetic identity/
# credit fixtures now live at `app.data_generation.synthetic_providers` (moved out
# of `app.verification`, which ships only the real, non-fabricating provider seam),
# so `test_data_generation.py` collects and runs without external services. Nothing
# is quarantined.
collect_ignore: list[str] = []