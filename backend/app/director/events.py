"""
Director Event Collector — async, non-blocking pipeline hooks.

Usage in pipeline steps:
    import asyncio
    from app.director.events import director_events

    asyncio.create_task(director_events.emit(
        module="module_1",
        event="s05_discovery_completed",
        payload={...}
    ))

If the emit fails, pipeline continues silently.
"""

import asyncio
from typing import Any
from app.services.supabase_client import get_client


class DirectorEventCollector:
    async def emit(
        self,
        module: str,
        event: str,
        payload: dict[str, Any],
        session_id: str | None = None,
        channel_id: str | None = None,
    ) -> None:
        try:
            client = get_client()
            client.table("director_events").insert({
                "module_name": module,
                "event_type": event,
                "payload": payload,
                "session_id": session_id,
                "channel_id": channel_id,
            }).execute()
        except Exception as e:
            print(f"[DirectorEvents] Emit failed (non-critical): {e}")


director_events = DirectorEventCollector()
