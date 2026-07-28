"""Reconcile verified Hermes scheduled jobs with the dashboard world."""

from collections.abc import Sequence

from yume_api.contracts.events import WorldEvent, WorldSnapshot
from yume_api.contracts.factories import make_agent_removed, make_agent_spawned, make_agent_state
from yume_api.hermes.models import HermesJob

JOBS_EVENT_SOURCE = "hermes.jobs"


class JobSynchronizer:
    """Produce world events that make Hermes jobs persistent automation workers."""

    def reconcile(
        self, jobs: Sequence[HermesJob], snapshot: WorldSnapshot, sequence: int
    ) -> list[WorldEvent]:
        """Create ordered worker changes for one successful jobs response."""
        existing = {agent.agent_id: agent for agent in snapshot.agents if agent.kind == "scheduled"}
        incoming = {f"scheduled:{job.id}": job for job in jobs}
        events: list[WorldEvent] = []
        for agent_id, job in incoming.items():
            if agent_id not in existing:
                events.append(
                    make_agent_spawned(
                        agent_id=agent_id,
                        kind="scheduled",
                        display_name=job.name,
                        room="automation",
                        sequence=sequence + len(events),
                        status="idle",
                        next_run_at=job.next_run_at,
                        source=JOBS_EVENT_SOURCE,
                    )
                )
            elif existing[agent_id].next_run_at != job.next_run_at:
                events.append(
                    make_agent_state(
                        agent_id,
                        "idle",
                        "automation",
                        sequence + len(events),
                        next_run_at=job.next_run_at,
                        source=JOBS_EVENT_SOURCE,
                    )
                )
        for agent_id in sorted(existing.keys() - incoming.keys()):
            events.append(
                make_agent_removed(agent_id, sequence + len(events), source=JOBS_EVENT_SOURCE)
            )
        return events
