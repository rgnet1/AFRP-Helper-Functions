"""When event coordinators may set a my.afrp.org password."""

from datetime import date, timedelta


def password_window_status(today, days_before, events):
    """Return (allowed, message) for one coordinator.

    events is a list of {"name", "start", "end"} where start and end are
    datetime.date or None. Missing start dates do not open a window.
    Access runs from start minus days_before through end, inclusive.
    """
    days = max(0, int(days_before or 0))
    future = []
    saw_dated_event = False
    for event in events or []:
        start = event.get("start")
        if not isinstance(start, date):
            continue
        saw_dated_event = True
        end = event.get("end") if isinstance(event.get("end"), date) else start
        if end < start:
            end = start
        opens = start - timedelta(days=days)
        if opens <= today <= end:
            return True, ""
        if today < opens:
            future.append((opens, event.get("name") or "your event"))
    if future:
        opens, name = min(future)
        return False, f"Portal password for {name} opens on {opens.strftime('%b %d, %Y')}."
    if saw_dated_event:
        return False, "Portal password for your events is closed."
    return False, "Portal password is closed because your event has no start date."
