---
name: afrp-event-seating
description: Documents how AFRP Dynamics events, sub-events, seating tables, chairs, seat reservations, questionnaires, and seating-chart images relate. Use when changing registration, the Seating page, badge seating, form questions, table capacity, or any query against campaigns, aha_seatingtables, aha_tablereservations, or aha_eventformquestionses.
---

# Events, tables, seats, and questionnaires

A convention is a campaign. A banquet is another campaign whose parent is that convention. Tables, chairs, seat reservations, and questions hang off the banquet (or whichever campaign owns them), not off the convention.

```
Convention campaign          Convention 2025 - San Francisco
  _aha_parentcampaign_value is empty
        │
        └── Sub-event campaign     Grand Banquet, Secondary Banquet Room
              _aha_parentcampaign_value = convention
              ├── questions        aha_eventformquestionses
              │     └── answers    aha_eventformresponseses  (one per contact per question)
              ├── tables           aha_seatingtables         (aha_numberofchairs = space)
              │     └── seats      aha_tablereservations     (one person, one chair)
              ├── chart picture    aha_imageofseatingchat    (no coordinates)
              └── sign-up          crca7_eventguests         (not a seat)
```

A person can have a sign-up, answers, and a seat on the same sub-event. Those are three records. Creating one does not create the others.

Code: `utils/registration/desk.py` (`live_tables`, `_claim_table`, `event_requirements`) and `utils/registration/seating.py`.

## Events (`campaigns`)

| Record | How to recognize it |
|--------|---------------------|
| Main event | `_aha_parentcampaign_value` is empty. Example: `Convention 2025 - San Francisco`. |
| Sub-event | `_aha_parentcampaign_value` is the main event. Example: `Grand Banquet` under that convention. |

Sub-events of a banquet were not present in this org. Do not assume a third level.

Several sub-events of one convention each have their own tables. San Francisco has both `Grand Banquet` and `Secondary Banquet Room`. Names repeat across years (`Grand Banquet` is also Houston and Lexington). Show the parent name with the sub-event name.

`aha_requireaseatingchart` means the event asks for a chart. It does not mean a picture or tables exist.

## Tables (`aha_seatingtables`)

One row is one physical table on one event.

| Field | Meaning |
|-------|---------|
| `aha_seatingtableid` | Table GUID |
| `aha_name` | Label printed for staff, often `Table 12` or `Table 9 - VIP RESERVED` |
| `crca7_tablenumberint` | Integer table number. Match a chart label to this or to the digits in `aha_name`. |
| `_aha_event_value` | The campaign that owns the table. Usually the sub-event, not the convention. |
| `aha_numberofchairs` | Space on that table. This is the only capacity field. |
| `aha_isreservedforvips` | VIP or reserved. Staff may still seat someone here while a chair is open. |
| `statecode` | `0` = active. Inactive tables are not choices. |

The event’s display name is `_aha_event_value@OData.Community.Display.V1.FormattedValue`. The metadata column `aha_eventname` cannot be used in `$select`; that request returns 400 and the seating list looks empty.

Some active tables have an empty `_aha_event_value`. They belong to no event and must not appear in an event’s chart.

## Space on a table

Open chairs = `aha_numberofchairs` minus the number of active `aha_tablereservations` whose `_aha_table_value` is that table.

| Field | Use |
|-------|-----|
| `aha_numberofchairs` | Capacity. Trust this. |
| Count of active reservations | How many chairs are taken. Trust this. |
| `aha_numberofseatsfilled` | Rollup. It lags. Do not use it to decide whether a table is full. |
| `aha_numberofseatsreserved` | Separate reserved count. Not the live chair count. |

A table with no chair count has unknown space (`open_seats` is empty) and stays selectable. A table with chairs and `seated >= chairs` is full.

Staff rules in `_claim_table`:

- A VIP table stays selectable while `seated < chairs`.
- A full table is not selectable, except the person’s current seat.
- After the write, count again. If `seated > chairs`, delete the new reservation or patch it back, and refuse the move.

Filter reservations with `_aha_event_value eq {event} and statecode eq 0`, not with the rollup.

## Seats (`aha_tablereservations`)

One row is one person in one chair. It is not the sign-up and not the table.

| Lookup | Bind on create |
|--------|----------------|
| `_aha_contact_value` | `aha_Contact@odata.bind` → `/contacts({id})` |
| `_aha_event_value` | `aha_Event@odata.bind` → `/campaigns({id})` |
| `_aha_table_value` | `aha_Table@odata.bind` → `/aha_seatingtables({id})` |

Navigation names are case-sensitive: `aha_Contact`, `aha_Event`, `aha_Table`. A person already seated on that event has one active reservation; moving them is a PATCH of `aha_Table`, not a second row. Set `aha_name` to `Seat` on create.

`contacts.aha_seatingtablerole` is an engagement tag (`General`, `Board Seating`, …). It is not a table assignment.

## Questionnaires

Questions belong to one campaign, the same way tables do. A convention and a banquet each have their own set.

| | Questions | Answers |
|--|-----------|---------|
| Entity set | `aha_eventformquestionses` | `aha_eventformresponseses` |
| Id | `aha_eventformquestionsid` | `aha_eventformresponsesid` |
| Text / value | `aha_newcolumn` (not `aha_name`) | `aha_guestresponse` |
| Event | `_aha_campaign_value` | `_aha_campaign_value` |
| Person | — | `_aha_contact_value` |
| Question | — | `_aha_formquestion_value` |

Other question fields: `aha_choicelabels`, `aha_questiontype`, `aha_isrequiredquestion`, `aha_ismultilinetext`, `aha_displayorder`. Split choices on `~`, otherwise `;`, otherwise `,`.

Answer binds: `aha_Contact` → `/contacts({id})`, `aha_Campaign` → `/campaigns({id})`, `aha_FormQuestion` → `/aha_eventformquestionses({id})`. PATCH an existing answer even when the new text is blank. POST only when the text is not blank.

On a paid or free sign-up, write answers and the seat only after the guest row exists. Staff may change saved answers and the seat later without charging.

## Seating chart picture

The floor plan is a picture on the sub-event, not a list of coordinates.

| Source | Field |
|--------|--------|
| Preferred | `aha_imageofseatingchat` (rich text). The `<img>` points at `msdyn_richtextfiles({guid})`. Download `msdyn_imageblob/$value`, then `msdyn_fileblob/$value`. |
| Fallback | `campaigns({id})/aha_imageofseatingarrangement/$value`, with `aha_imageofseatingarrangement_timestamp`. |

`crca7_seatingchart` was empty on sampled events. Do not treat it as the picture.

Event coordinators can open seating at any time, only for the campaign assigned to their group. That list does not use the Open campaign filter and does not use the portal-password date window. Other conventions stay hidden. Admins still see open campaigns.

Helper reads the picture once, matches printed numbers to `aha_name` / `crca7_tablenumberint`, and saves the layout under `data/seating_layouts/` keyed by campaign and image timestamp. A new picture converts again. Tables the picture does not match stay in a list. Hover and click use live reservations, not the saved layout, for who is sitting and how full the table is.

## Queries that already failed

- `$select=aha_eventname` on `aha_seatingtables` returns 400. Use the formatted `_aha_event_value`.
- Counting `aha_numberofseatsfilled` shows tables as open after the last chair was taken.
- Listing only the parent convention hides Grand Banquet and Secondary Banquet Room. Start from tables, or from sub-events of the conventions the user may open.
- `urlencode` the whole `$filter`. A raw `+` is a space.
