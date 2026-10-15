"""Command groups for the AFRP Helper API."""

from __future__ import annotations

import click

from afrp_cli.context import (
    EVENT_HELP,
    Ctx,
    _download,
    _get,
    _parse_json,
    _send,
    pass_ctx,
    resolve_event_id,
)

HELP_OPTS = {"help_option_names": ["-h", "--help"]}


def register(main: click.Group) -> None:
    main.add_command(seating_group)
    main.add_command(campaigns_group)
    main.add_command(badges_group)
    main.add_command(magazine_group)


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
