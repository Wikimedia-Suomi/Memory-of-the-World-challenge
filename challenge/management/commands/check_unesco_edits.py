from __future__ import annotations

import re
from datetime import datetime, timezone

import pywikibot
from django.core.management.base import BaseCommand

from challenge.models import Participant

UNESCO_PATTERN = re.compile(r"https://www\.unesco\.org/(?:[a-z]{2}/)?memory-world/")
SKIP_TAGS = {"mw-reverted", "mw-manual-revert", "mw-undo", "mw-rollback"}


class Command(BaseCommand):
    """Check participant edits adding UNESCO Memory of the World links."""

    help = (
        "List participant edits since a given date that add a link to the "
        "UNESCO Memory of the World website."
    )

    def add_arguments(self, parser) -> None:  # pragma: no cover - argparse boilerplate
        parser.add_argument(
            "--since",
            default="2025-09-01T00:00:00Z",
            help="ISO timestamp (UTC) of earliest edit to inspect",
        )

    def handle(self, *args, **options) -> None:  # pragma: no cover - side effects
        since = datetime.fromisoformat(options["since"].replace("Z", "+00:00"))
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)

        since_ts = pywikibot.Timestamp.set_timestamp(since)

        participants = Participant.objects.all()
        for participant in participants:
            activities = participant.activities.filter(active=True)
            for activity in activities:
                site = pywikibot.site.APISite.fromDBName(activity.wiki)
                ucgen = site.usercontribs(user=participant.username, end=since_ts)
                ucgen.request["ucprop"] += "|tags"
                for contrib in ucgen:
                    ts = contrib["timestamp"].to_datetime().replace(tzinfo=timezone.utc)
                    if ts < since:
                        break

                    if SKIP_TAGS & set(contrib.get("tags", [])):
                        continue

                    page_obj = pywikibot.Page(site, contrib["title"])
                    revid = contrib["revid"]
                    revision = page_obj.get_revision(revid, content=True)
                    parentid = revision.parentid
                    new_text = revision.text or ""
                    old_text = page_obj.getOldVersion(parentid) if parentid else ""

                    if UNESCO_PATTERN.search(new_text) and not UNESCO_PATTERN.search(
                        old_text
                    ):
                        self.stdout.write(
                            f"{participant.username} on {activity.wiki} added UNESCO link in "
                            f"[[{page_obj.title()}]] (rev {revid})"
                        )

