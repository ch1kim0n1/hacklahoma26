from datetime import datetime, timezone

def list_events_tool(service):
    async def list_events(max_results: int = 10):
        now = datetime.now(timezone.utc).isoformat()

        events = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=now,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )

        return [
            {
                "id": e["id"],
                "summary": e.get("summary"),
                "start": e["start"].get("dateTime", e["start"].get("date")),
                "end": e["end"].get("dateTime", e["end"].get("date")),
            }
            for e in events.get("items", [])
        ]

    return {
        "name": "calendar_list_events",
        "description": "List upcoming Google Calendar events",
        "fn": list_events,
    }


def create_event_tool(service):
    async def create_event(summary: str, start_iso: str, end_iso: str):
        event = {
            "summary": summary,
            "start": {"dateTime": start_iso},
            "end": {"dateTime": end_iso},
        }

        created = (
            service.events()
            .insert(calendarId="primary", body=event)
            .execute()
        )

        return {
            "id": created["id"],
            "htmlLink": created["htmlLink"],
        }

    return {
        "name": "calendar_create_event",
        "description": "Create a Google Calendar event",
        "fn": create_event,
    }


def delete_event_tool(service):
    async def delete_event(event_id: str):
        service.events().delete(
            calendarId="primary",
            eventId=event_id,
        ).execute()
        return {"deleted": True, "event_id": event_id}

    return {
        "name": "calendar_delete_event",
        "description": "Delete a Google Calendar event by ID",
        "fn": delete_event,
    }
