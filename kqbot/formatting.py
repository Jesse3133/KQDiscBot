"""Message text. Kept separate from Discord code so it can be unit tested."""

from datetime import datetime

from kqbot.events import Event
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
        f"({ts(upcoming.start, 'R')}){moved_note(upcoming)}, "
        f"recruitment closes {ts(upcoming.end, 't')}"
    )


def moved_note(occ: Occurrence) -> str:
    return f" (moved from {ts(occ.normal_start, 't')})" if occ.shifted else ""


def roles_message(events: tuple[Event, ...], role_ids: dict[str, int]) -> str:
    lines = [
        "**Kingdom Quest pings**",
        "React below to get pinged 3 minutes before an event starts. Remove your reaction to stop.",
        "",
    ]
    for event in events:
        role_id = role_ids.get(event.key)
        role = f" → <@&{role_id}>" if role_id else ""
        lines.append(f"{event.emoji} {event.name}{role}")
    return "\n".join(lines)


def reminder_message(occ: Occurrence, role_id: int | None, test: bool = False) -> str:
    event = occ.event
    mention = f"<@&{role_id}> " if role_id else ""
    lines = [
        f"{mention}{event.emoji} **{event.name}** is starting soon!",
        f"Starts {ts(occ.start, 't')} ({ts(occ.start, 'R')}){moved_note(occ)} · "
        f"Recruitment closes {ts(occ.end, 't')}",
    ]
    if test:
        lines.insert(0, "🧪 **Test reminder**: not a real event, just checking pings.")
    return "\n".join(lines)


def describe_timing(event: Event) -> str:
    """Human summary, e.g. "every 2 hours at :03 (01:03, 03:03, 05:03, …)"."""
    mm = f"{event.minute:02d}"
    n = event.interval_hours
    if n == 1:
        return f"every hour at :{mm}"
    first = event.first_hour % n
    if n == 24:
        return f"daily at {first:02d}:{mm}"
    hours = ", ".join(f"{h:02d}:{mm}" for h in range(first, 24, n)[:3])
    return f"every {n} hours at :{mm} ({hours}, …)"


def describe_event(event: Event) -> str:
    return (
        f"{event.emoji} **{event.name}**: {describe_timing(event)}, "
        f"recruitment {event.duration_minutes} min"
    )
