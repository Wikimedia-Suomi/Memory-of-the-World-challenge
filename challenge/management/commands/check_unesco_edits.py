from __future__ import annotations

import re
import json
from datetime import datetime, timezone
from collections import defaultdict

import pywikibot
from pywikibot.data import sparql
from django.core.management.base import BaseCommand

from challenge.models import Participant

UNESCO_PATTERN = re.compile(r"https://(www\.)?unesco\.org/(?:[a-z]{2}/)?memory-world/")
SKIP_TAGS = {"mw-reverted", "mw-manual-revert", "mw-undo", "mw-rollback"}

SPARQL_QUERY = (
    "SELECT DISTINCT ?item WHERE { ?item p:P1435 ?s. ?s ps:P1435 wd:Q16024238."
    " ?s prov:wasDerivedFrom/pr:P854 ?refurl. ?s pq:P580 ?date. }"
)
# No longer relying on edit comments for label counts

metasite = pywikibot.Site("meta", "meta")
metasite.login()

def fetch_unesco_items() -> set[str]:
    """Fetch Wikidata items related to UNESCO Memory of the World."""
    endpoint = sparql.SparqlQuery()
    data = endpoint.select(SPARQL_QUERY)
    return {row["item"].split("/")[-1] for row in data}

def get_creator(page: pywikibot.Page):
    threshold_date = datetime(2025, 9, 1, 0, 0, 0, tzinfo=timezone.utc)
    try:
        oldest_revision = page.oldest_revision
        creator = oldest_revision.user
        creation_time = oldest_revision.timestamp
        if creation_time.tzinfo is None:
            creation_time = creation_time.replace(tzinfo=timezone.utc)

#        print(f"Page creator: {creator}")
#        print(f"Created on: {creation_time}")
        if creation_time > threshold_date:
            return creator;
    except Exception as e:
        print(f"Error: {e}")
    return ""

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
        items = fetch_unesco_items()

        start = datetime(2025, 9, 1, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(2025, 9, 30, 23, 59, 59, tzinfo=timezone.utc)
        start_ts = pywikibot.Timestamp.set_timestamp(start)
        end_ts = pywikibot.Timestamp.set_timestamp(end)

        participants = Participant.objects.all()
        points_by_user: defaultdict[str, int] = defaultdict(int)
        actions_by_user: defaultdict[str, list[str]] = defaultdict(list)
        pages_seen: defaultdict[str, set[tuple[str, str]]] = defaultdict(set)

        for participant in participants:
#            if participant.username != "Umar2z":
#                continue
            activities = participant.activities.filter(active=True)
            for activity in activities:
                print(activity)
                site = pywikibot.site.APISite.fromDBName(activity.wiki)                
                ucgen = site.usercontribs(
                    user=participant.username, start=end_ts, end=start_ts
                )
                for contrib in ucgen:
                    timestamp = datetime.fromisoformat(
                        contrib["timestamp"].replace("Z", "+00:00")
                    )
                    if timestamp.tzinfo is None:
                        timestamp = timestamp.replace(tzinfo=timezone.utc)

                    if timestamp < start:
                        break
                    if timestamp > end:
                        continue

                    revid = contrib["revid"]
                    page_obj = pywikibot.Page(site, contrib["title"])

                    if activity.wiki == "wikidatawiki":
                        title = contrib["title"]
                        comment = contrib.get("comment", "")
#                        print(title)
#                        print(comment)

                        if title in items and ("wbsetlabel" in comment or "wbeditentity-update-languages" in comment):
                            revision = page_obj.get_revision(revid, content=True)
                            if SKIP_TAGS & set(revision.tags):
                                self.stdout.write(
                                    f"SKIPPED:{revision.tags} : "
                                    f"{participant.username} on {activity.wiki} added UNESCO link in "
                                    f"{link} (rev {rev_link})"
                                )
                                continue

                            parentid = revision.parentid
                            new_text = revision.text or "{}"
                            old_text = page_obj.getOldVersion(parentid) if parentid else "{}"
                            try:
                                new_labels = json.loads(new_text).get("labels", {})
                                old_labels = json.loads(old_text).get("labels", {})
                            except Exception:
                                continue
                            added_languages = [lang for lang in new_labels if lang not in old_labels]
                            num_labels = len(added_languages)
                            if num_labels == 0:
                                continue
                            item_link = "{{Q|" + title + "}}"
                            rev_link = f"[[:d:Special:Diff/{revid}|{revid}]]"
                            lang_links = result = ", ".join([f"{{{{{added_lang}}}}}" for added_lang in added_languages])
                            actions_by_user[participant.username].append(
                                f"* +{num_labels} points, on {activity.wiki} added label(s) ({lang_links}) to {item_link} (rev {rev_link})",
                            )
                            points_by_user[participant.username] += num_labels
                        continue

                    revision = page_obj.get_revision(revid, content=True)
                    if SKIP_TAGS & set(revision.tags):
                        self.stdout.write(
                            f"SKIPPED:{revision.tags} : "
                            f"{participant.username} on {activity.wiki} added UNESCO link in "
                            f"{link} (rev {rev_link})"
                        )
                        continue

                    prefix = activity.wiki.replace("wiki", "")
                    link = f"[[:{prefix}:{page_obj.title()}]]"
                    rev_link = f"[[:{prefix}:Special:Diff/{revid}|{revid}]]"

                    parentid = revision.parentid
                    new_text = revision.text or ""
                    old_text = page_obj.getOldVersion(parentid) if parentid else ""

                    if UNESCO_PATTERN.search(new_text) and not UNESCO_PATTERN.search(
                        old_text
                    ):
                        page_key = (activity.wiki, page_obj.title())
                        if page_key in pages_seen[participant.username]:
                            continue
                        pages_seen[participant.username].add(page_key)

                        creator = get_creator(page_obj)
                        points = 2
                        action_desc = f"added UNESCO link in {link}"
                        if creator == participant.username:
                            points = 5
                            action_desc = (
                                f"created article {link} with UNESCO link in it"
                            )
                            try:
                                item = pywikibot.ItemPage.fromPage(page_obj)
                                item.get()
                                if any(
                                    claim.getTarget().id == "Q13406463"
                                    for claim in item.claims.get("P31", [])
                                ):
                                    points = 25
                                    action_desc = f"created list article {link} with UNESCO link in it"

                            except Exception:
                                pass

                        actions_by_user[participant.username].append(
                            f"* +{points} points, on {activity.wiki} {action_desc} (rev {rev_link})"
                        )
                        points_by_user[participant.username] += points

        if points_by_user:
            for user, pts in sorted(
                points_by_user.items(), key=lambda item: item[1], reverse=True
            ):
                self.stdout.write(
                    f"== [[USER:{user}|{user}]] (points: {pts}) =="
                )
                for line in actions_by_user[user]:
                    self.stdout.write(line)
