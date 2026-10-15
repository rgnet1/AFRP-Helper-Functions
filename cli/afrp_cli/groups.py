"""Command groups for the AFRP Helper API."""

from __future__ import annotations

import json

import click

from afrp_cli.client import ApiError
from afrp_cli.context import (
    EVENT_HELP,
    Ctx,
    _download,
    _get,
    _parse_json,
    _send,
    exit_api,
    pass_ctx,
    resolve_event_id,
)

HELP_OPTS = {"help_option_names": ["-h", "--help"]}


def register(main: click.Group) -> None:
    main.add_command(seating_group)
    main.add_command(campaigns_group)
    main.add_command(badges_group)
    main.add_command(magazine_group)
    main.add_command(registration_group)
    main.add_command(membership_group)
    main.add_command(password_group)
    main.add_command(qr_group)
    main.add_command(event_group)


@click.group("seating", context_settings=HELP_OPTS)
def seating_group() -> None:
    """Seating charts, guests, and seat moves."""


@seating_group.command("events")
@pass_ctx
def seating_events(ctx: Ctx) -> None:
    """List open events and the sub-events that have tables."""
    _get(ctx, "/api/seating/events")


@seating_group.command("board")
@click.argument("event")
@click.option("--sketch", is_flag=True, help="Skip guest names so the floor plan returns faster")
@click.option("--contact", "contact_id", help="Mark this person's current table")
@pass_ctx
def seating_board(ctx: Ctx, event: str, sketch: bool, contact_id: str | None) -> None:
    """Show one banquet's floor plan and live seats."""
    event_id = resolve_event_id(ctx.client, event)
    params = {}
    if sketch:
        params["sketch"] = "1"
    if contact_id:
        params["contact_id"] = contact_id
    _get(ctx, f"/api/seating/{event_id}", params or None)


@seating_group.command("guests")
@click.argument("event")
@click.option("--query", "-q", "query", required=True, help="Name or email fragment")
@pass_ctx
def seating_guests(ctx: Ctx, event: str, query: str) -> None:
    """Search people signed up for a sub-event."""
    event_id = resolve_event_id(ctx.client, event)
    _get(ctx, f"/api/seating/{event_id}/guests", {"q": query})


@seating_group.command("questions")
@click.argument("event")
@click.option("--contact", "contact_id", help="Include this person's saved answers")
@click.option("--from-event", "from_event_id", help="Prefill matching answers from this banquet")
@pass_ctx
def seating_questions(ctx: Ctx, event: str, contact_id: str | None, from_event_id: str | None) -> None:
    """Meal questions for a banquet."""
    event_id = resolve_event_id(ctx.client, event)
    params = {}
    if contact_id:
        params["contact_id"] = contact_id
    if from_event_id:
        params["from_event_id"] = resolve_event_id(ctx.client, from_event_id)
    _get(ctx, f"/api/seating/{event_id}/questions", params or None)


@seating_group.command("move")
@click.argument("event")
@click.option("--contact", "contact_id", required=True)
@click.option("--table", "table_id", required=True)
@click.option("--from-event", "from_event_id", help=EVENT_HELP)
@click.option("--to-event", "to_event_id", help=EVENT_HELP)
@click.option("--data", help="Optional answers JSON array")
@pass_ctx
def seating_move(
    ctx: Ctx,
    event: str,
    contact_id: str,
    table_id: str,
    from_event_id: str | None,
    to_event_id: str | None,
    data: str | None,
) -> None:
    """Move one person. Add --from-event and --to-event to change banquets."""
    event_id = resolve_event_id(ctx.client, event)
    if from_event_id or to_event_id or data:
        move = {
            "contact_id": contact_id,
            "table_id": table_id,
            "from_event_id": resolve_event_id(ctx.client, from_event_id or event),
            "to_event_id": resolve_event_id(ctx.client, to_event_id or event),
        }
        if data:
            move["answers"] = _parse_json(data)
        _send(ctx, "POST", f"/api/seating/{event_id}/assign-batch", {"moves": [move]})
        return
    _send(ctx, "POST", f"/api/seating/{event_id}/assign", {"contact_id": contact_id, "table_id": table_id})


@click.group("campaigns", context_settings=HELP_OPTS)
def campaigns_group() -> None:
    """Open conventions and their sub-events."""


@campaigns_group.command("list")
@pass_ctx
def campaigns_list(ctx: Ctx) -> None:
    """List open conventions."""
    _get(ctx, "/api/campaigns/open")


@campaigns_group.command("sub-events")
@click.argument("campaign_id")
@pass_ctx
def campaigns_sub_events(ctx: Ctx, campaign_id: str) -> None:
    """List sub-events under one convention."""
    _get(ctx, f"/api/campaigns/{campaign_id}/sub-events")


@click.group("badges", context_settings=HELP_OPTS)
def badges_group() -> None:
    """Badge templates and generation jobs."""


@badges_group.command("templates")
@pass_ctx
def badges_templates(ctx: Ctx) -> None:
    """List saved badge templates."""
    _get(ctx, "/api/badge-templates")


@badges_group.command("start")
@click.option("--data", required=True, help="JSON body for pull-process-generate-async")
@pass_ctx
def badges_start(ctx: Ctx, data: str) -> None:
    """Start a badge job and print its id."""
    _send(ctx, "POST", "/api/badges/pull-process-generate-async", _parse_json(data))


@badges_group.command("job")
@click.argument("job_id")
@pass_ctx
def badges_job(ctx: Ctx, job_id: str) -> None:
    """Show badge job progress."""
    _get(ctx, f"/api/badges/jobs/{job_id}")


@badges_group.command("sizes")
@pass_ctx
def badges_sizes(ctx: Ctx) -> None:
    """List Avery badge sizes."""
    _get(ctx, "/api/avery-templates")


@badges_group.command("preprocessing")
@pass_ctx
def badges_preprocessing(ctx: Ctx) -> None:
    """List saved preprocessing templates."""
    _get(ctx, "/api/preprocessing-templates")


@badges_group.command("meals")
@click.option("--campaign", "campaign_id", required=True, help="Convention id")
@pass_ctx
def badges_meals(ctx: Ctx, campaign_id: str) -> None:
    """Meal columns for one convention."""
    _get(ctx, "/api/badges/meal-options", {"campaign_id": campaign_id})


@badges_group.command("download")
@click.argument("job_id")
@click.option("-o", "--output", required=True, type=click.Path(), help="Where to write the PDF")
@pass_ctx
def badges_download(ctx: Ctx, job_id: str, output: str) -> None:
    """Download a finished badge PDF."""
    _download(ctx, f"/api/badges/jobs/{job_id}/download", output)


@click.group("magazine", context_settings=HELP_OPTS)
def magazine_group() -> None:
    """Magazine download schedules."""


@magazine_group.command("schedules")
@pass_ctx
def magazine_schedules(ctx: Ctx) -> None:
    """List magazine download schedules."""
    _get(ctx, "/api/schedules")


@magazine_group.command("create")
@click.option("--frequency", required=True, type=click.Choice(["daily", "weekly", "monthly"]))
@click.option("--time", "at", required=True, help="Time like 09:30 AM")
@click.option("--day-of-week", type=int, help="0-6 when frequency is weekly")
@click.option("--day-of-month", type=int, help="1-31 when frequency is monthly")
@pass_ctx
def magazine_create(ctx: Ctx, frequency: str, at: str, day_of_week: int | None, day_of_month: int | None) -> None:
    """Create a magazine download schedule."""
    body = {"frequency": frequency, "time": at}
    if day_of_week is not None:
        body["day_of_week"] = day_of_week
    if day_of_month is not None:
        body["day_of_month"] = day_of_month
    _send(ctx, "POST", "/api/schedules", body)


@magazine_group.command("delete")
@click.argument("schedule_id")
@pass_ctx
def magazine_delete(ctx: Ctx, schedule_id: str) -> None:
    """Delete a magazine download schedule."""
    _send(ctx, "DELETE", "/api/schedules", params={"id": schedule_id})


def _person_params(email: str | None, first: str | None, last: str | None) -> dict[str, str]:
    params = {}
    if email:
        params["email"] = email
    if first:
        params["first_name"] = first
    if last:
        params["last_name"] = last
    if not params:
        raise click.ClickException("Pass --email, --first, or --last")
    return params


@click.group("registration", context_settings=HELP_OPTS)
def registration_group() -> None:
    """Event sign-ups, questions, and tables."""


@registration_group.command("events")
@pass_ctx
def registration_events(ctx: Ctx) -> None:
    """List conventions this account can register."""
    _get(ctx, "/api/registration/events")


@registration_group.command("search")
@click.option("--campaign", "campaign_id", help="Convention id. Required when you can open more than one.")
@click.option("--email")
@click.option("--first")
@click.option("--last")
@pass_ctx
def registration_search(ctx: Ctx, campaign_id: str | None, email: str | None, first: str | None, last: str | None) -> None:
    """Find a person and the sign-ups on one convention."""
    params = _person_params(email, first, last)
    if campaign_id:
        params["campaign_id"] = campaign_id
    _get(ctx, "/api/registration/contacts", params)


@registration_group.command("requirements")
@click.option("--campaign", "campaign_id", required=True)
@click.option("--event", "event_id", required=True, help=EVENT_HELP)
@click.option("--contact", "contact_id")
@pass_ctx
def registration_requirements(ctx: Ctx, campaign_id: str, event_id: str, contact_id: str | None) -> None:
    """Questions and tables for one event."""
    params = {"campaign_id": campaign_id, "event_id": event_id}
    if contact_id:
        params["contact_id"] = contact_id
    _get(ctx, "/api/registration/requirements", params)


@registration_group.command("add")
@click.option("--campaign", "campaign_id", required=True)
@click.option("--event", "event_id", required=True)
@click.option("--contact", "contact_id", required=True)
@click.option("--table", "table_id")
@click.option("--answers", help="JSON list of {question_id, response}")
@click.option("--skip-payment", is_flag=True, help="Record the sign-up without charging a card")
@pass_ctx
def registration_add(ctx: Ctx, campaign_id: str, event_id: str, contact_id: str, table_id: str | None, answers: str | None, skip_payment: bool) -> None:
    """Sign one person up for an event."""
    body = {
        "campaign_id": campaign_id,
        "event_id": event_id,
        "contact_id": contact_id,
        "skip_payment": skip_payment,
    }
    if table_id:
        body["table_id"] = table_id
    if answers:
        body["answers"] = _parse_json(answers)
    _send(ctx, "POST", "/api/registration/add", body)


@registration_group.command("move")
@click.option("--campaign", "campaign_id", required=True)
@click.option("--guest", "guest_id", required=True)
@click.option("--event", "event_id", required=True)
@click.option("--skip-payment", is_flag=True)
@pass_ctx
def registration_move(ctx: Ctx, campaign_id: str, guest_id: str, event_id: str, skip_payment: bool) -> None:
    """Move a sign-up to another event."""
    _send(ctx, "POST", "/api/registration/move", {
        "campaign_id": campaign_id,
        "guest_id": guest_id,
        "event_id": event_id,
        "skip_payment": skip_payment,
    })


@registration_group.command("remove")
@click.option("--campaign", "campaign_id", required=True)
@click.option("--guest", "guest_id", required=True)
@pass_ctx
def registration_remove(ctx: Ctx, campaign_id: str, guest_id: str) -> None:
    """Mark a sign-up inactive."""
    _send(ctx, "POST", "/api/registration/remove", {
        "campaign_id": campaign_id,
        "guest_id": guest_id,
    })


@click.group("membership", context_settings=HELP_OPTS)
def membership_group() -> None:
    """Yearly household memberships."""


@membership_group.command("years")
@pass_ctx
def membership_years_cmd(ctx: Ctx) -> None:
    """Years that can be purchased now."""
    _get(ctx, "/api/membership/years")


@membership_group.command("lookup")
@click.option("--contact", "contact_id")
@click.option("--year", type=int)
@click.option("--email")
@click.option("--first")
@click.option("--last")
@click.option("--buyer", "buyers", multiple=True, help="Contact id to include in the recommended split")
@pass_ctx
def membership_lookup(ctx: Ctx, contact_id: str | None, year: int | None, email: str | None, first: str | None, last: str | None, buyers: tuple[str, ...]) -> None:
    """Load a household, or search for a person."""
    params = {}
    if contact_id:
        params["contact_id"] = contact_id
    if year:
        params["year"] = str(year)
    if email or first or last:
        params.update(_person_params(email, first, last))
    if not params and not buyers:
        raise click.ClickException("Pass --contact or a name/email")
    query = [(key, value) for key, value in params.items()]
    for buyer in buyers:
        query.append(("buyer", buyer))
    try:
        ctx.show(ctx.client.json("GET", "/api/membership/lookup", params=query))
    except ApiError as exc:
        exit_api(exc)


@membership_group.command("purchase")
@click.option("--contact", "contact_id", required=True, help="Person the page was opened for")
@click.option("--year", required=True, type=int)
@click.option("--plan", "plans", multiple=True, required=True, help="contact_id:category_id, repeat for each plan")
@click.option("--spouse")
@click.option("--child", "children", multiple=True)
@click.option("--skip-payment", is_flag=True, help="Save the membership without charging a card")
@pass_ctx
def membership_purchase_cmd(ctx: Ctx, contact_id: str, year: int, plans: tuple[str, ...], spouse: str | None, children: tuple[str, ...], skip_payment: bool) -> None:
    """Buy one or more memberships. Confirms the coverage list."""
    parsed = []
    for item in plans:
        if ":" not in item:
            raise click.ClickException(f"Plan {item!r} must be contact_id:category_id")
        person, category = item.split(":", 1)
        parsed.append({"contact_id": person, "category_id": category})
    body = {
        "contact_id": contact_id,
        "year": year,
        "plans": parsed,
        "confirm_cover": True,
        "skip_payment": skip_payment,
        "child_ids": list(children),
    }
    if spouse:
        body["spouse_id"] = spouse
    _send(ctx, "POST", "/api/membership/purchase", body)


@click.group("password", context_settings=HELP_OPTS)
def password_group() -> None:
    """my.afrp.org portal passwords."""


@password_group.command("search")
@click.option("--email")
@click.option("--first")
@click.option("--last")
@pass_ctx
def password_search(ctx: Ctx, email: str | None, first: str | None, last: str | None) -> None:
    """Find a contact before setting a password."""
    _get(ctx, "/api/password-reset/contacts", _person_params(email, first, last))


@password_group.command("set")
@click.option("--contact", "contact_id", required=True)
@click.option("--password", required=True)
@pass_ctx
def password_set(ctx: Ctx, contact_id: str, password: str) -> None:
    """Set a portal password. Coordinators only during the event window."""
    _send(ctx, "POST", "/api/password-reset", {"contact_id": contact_id, "password": password})


@click.group("qr", context_settings=HELP_OPTS)
def qr_group() -> None:
    """QR code images."""


@qr_group.command("make")
@click.argument("data")
@click.option("-o", "--output", required=True, type=click.Path(), help="PNG path")
@pass_ctx
def qr_make(ctx: Ctx, data: str, output: str) -> None:
    """Write a QR code PNG for the given text."""
    from pathlib import Path
    try:
        resp = ctx.client.request("POST", "/api/qr", json_body={"data": data})
    except ApiError as exc:
        exit_api(exc)
    Path(output).write_bytes(resp.content)
    click.echo(json.dumps({"saved": output, "bytes": len(resp.content)}, indent=2))


@click.group("event", context_settings=HELP_OPTS)
def event_group() -> None:
    """Private event registration URLs."""


@event_group.command("url")
@click.argument("crm_url")
@pass_ctx
def event_url(ctx: Ctx, crm_url: str) -> None:
    """Turn a Dynamics campaign URL into the private registration and summary links."""
    _send(ctx, "POST", "/event", {"crmUrl": crm_url})
