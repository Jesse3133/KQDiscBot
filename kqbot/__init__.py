"""Fiesta KQ Bot: Discord reminders for Fiesta Online Kingdom Quests."""

import sys

if sys.version_info < (3, 11):  # noqa: UP036 (friendly error on old Pythons)
    raise SystemExit(
        f"Fiesta KQ Bot needs Python 3.11 or newer, but this is Python "
        f"{sys.version_info.major}.{sys.version_info.minor} ({sys.executable}). "
        "See 'Running it locally' in README.md."
    )
