"""Message text. Kept separate from Discord code so it can be unit tested."""

from datetime import datetime

from kqbot.schedule import Occurrence


def ts(moment: datetime, style: str) -> str:
    """Discord timestamp markup; renders in each viewer's own time zone.

    Styles: ``t`` = short time (9:03 AM), ``R`` = relative (in 5 minutes).
    """
    return f"<t:{int(moment.timestamp())}:{style}>"


def next_line(upcoming: Occurrence, active: Occurrence | None) -> str:
    event = upcoming.event
    if active is not None:
        return (
            f"{event.emoji} **{event.name}**: recruiting now, closes "
            f"{ts(active.end, 't')} ({ts(active.end, 'R')}). "
            f"Next start {ts(upcoming.start, 't')}"
        )
    return (
        f"{event.emoji} **{event.name}**: starts {ts(upcoming.start, 't')} "
        f"({ts(upcoming.start, 'R')}), recruitment closes {ts(upcoming.end, 't')}"
    )
