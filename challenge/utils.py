"""Utility functions for the Memory of the World challenge.

These helpers fetch challenge participants and related information from
Wikimedia using Pywikibot.  The module is used by the Django management
command ``load_participants``.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Set

import pywikibot
from pywikibot.data import sparql

from challenge.models import Participant, WikiActivity


UNESCO_PATTERN = re.compile(r"https://(www\.)?unesco\.org/(?:[a-z]{2}/)?memory-world/")
SKIP_TAGS = {"mw-reverted", "mw-manual-revert", "mw-undo", "mw-rollback"}

SPARQL_QUERY = (
    "SELECT DISTINCT ?item WHERE { ?item p:P1435 ?s. ?s ps:P1435 wd:Q16024238."
    " ?s prov:wasDerivedFrom/pr:P854 ?refurl. ?s pq:P580 ?date. }"
)

START_DATE = datetime(2025, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
END_DATE = datetime(2025, 10, 1, 23, 59, 59, tzinfo=timezone.utc)


def extract_usernames(page: pywikibot.Page) -> List[str]:
    """Return a sorted list of usernames linked on *page*.

    The function inspects user-page links and templates such as
    ``{{User|Example}}`` to collect participant names.
    """
    usernames: Set[str] = set()

    # Links to user pages
    for link in page.linkedPages():
        if link.namespace() == 2:  # User namespace
            usernames.add(link.title(with_ns=False))

    # ``{{User|Example}}`` templates
    for template, params in page.templatesWithParams():
        if template.title(with_ns=False).lower() == "user" and params:
            usernames.add(params[0].strip())

    return sorted(usernames)


def write_output(lines: Iterable[str], output: Path | None) -> None:
    """Write *lines* either to stdout or to *output* file."""
    if output is None:
        for line in lines:
            print(line)
    else:
        output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def fetch_user_wikis(
    site: pywikibot.Site, usernames: Iterable[str]
) -> Dict[str, List[str]]:
    """Return a mapping of username to recent Wikipedia projects.

    Only wikis where the user has edited within the last 32 days are
    included in the result.  The function queries the global user info
    to discover wikis and then checks the most recent contribution on
    each project before adding it to the user's list.  Edit counts and
    whether the wiki is active are stored in the database.
    """

    cutoff = datetime.now(timezone.utc) - timedelta(days=66)
    result: Dict[str, List[str]] = {}
    for name in usernames:
        request = site.simple_request(
            action="query",
            meta="globaluserinfo",
            guiuser=name,
            guiprop="merged",
        )
        print(name)

        data = request.submit()
        participant, _ = Participant.objects.get_or_create(username=name)
        wikis: List[str] = []
        for merged in data["query"]["globaluserinfo"].get("merged", []):
            url = merged.get("url", "")
            editcount = merged.get("editcount", 0)
            if editcount == 0 or ("wikipedia.org" not in url and "wikidata.org" not in url):
                continue

            wiki_db = merged["wiki"]
            activity, _ = WikiActivity.objects.get_or_create(
                participant=participant, wiki=wiki_db
            )

            if activity.editcount != editcount:
                lang = url.split("//")[-1].split(".")[0]
#                wiki_site = pywikibot.Site(lang, "wikipedia")
                wiki_site=pywikibot.site.APISite.fromDBName(wiki_db)
                user = pywikibot.User(wiki_site, name)
                last_edit = next(user.contributions(total=1), None)
                if last_edit:
                    ts = last_edit[2]
                    timestamp = ts.to_datetime() if hasattr(ts, "to_datetime") else ts
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                    active = timestamp >= cutoff
                else:
                    active = False
            else:
                active = activity.active

            activity.editcount = editcount
            activity.active = active
            activity.save()

            if active:
                wikis.append(wiki_db)
        result[name] = wikis
    return result


def fetch_unesco_pages(wikis: Iterable[str]) -> Dict[str, List[str]]:
    """Return pages that link to the UNESCO Memory of the World site.

    *wikis* should be an iterable of database names such as ``"enwiki"``.
    For each wiki the function queries ``exturlusage`` and collects titles
    of pages that contain links whose URL includes ``memory-world`` either
    directly or with a language code such as ``/en/memory-world``.  Pages
    are only included if their most recent edit occurred within the last
    66 days.  The returned mapping uses the wiki database name as the key
    and a sorted list of page titles as the value.
    """

    # UNESCO publishes the Memory of the World site in these languages
    languages = ["", "ar", "en", "es", "fr", "ru", "zh"]

    cutoff = datetime.now(timezone.utc) - timedelta(days=66)
    result: Dict[str, List[str]] = {}
    for wiki in wikis:
        wiki_site = pywikibot.site.APISite.fromDBName(wiki)
        pages: Set[str] = set()
        for lang in languages:
            suffix = f"/{lang}/memory-world" if lang else "/memory-world"
            query = f"www.unesco.org{suffix}"
            for page in wiki_site.exturlusage(query, protocol="https"):
                # Only consider pages edited recently
                latest = page.latest_revision.timestamp
                timestamp = (
                    latest.to_datetime() if hasattr(latest, "to_datetime") else latest
                )
                timestamp = timestamp.replace(tzinfo=timezone.utc)
                if timestamp >= cutoff:
                    pages.add(page.title())

        result[wiki] = sorted(pages)
    return result


@lru_cache(maxsize=1)
def fetch_unesco_items() -> Set[str]:
    """Fetch Wikidata items related to UNESCO Memory of the World."""

    endpoint = sparql.SparqlQuery()
    data = endpoint.select(SPARQL_QUERY)
    return {row["item"].split("/")[-1] for row in data}


def get_creator(page: pywikibot.Page) -> str:
    """Return the username that created *page* after START_DATE."""

    try:
        oldest_revision = page.oldest_revision
        creator = oldest_revision.user
        creation_time = oldest_revision.timestamp
        if creation_time.tzinfo is None:
            creation_time = creation_time.replace(tzinfo=timezone.utc)
        if creation_time > START_DATE:
            return creator
    except Exception:  # pragma: no cover - network interaction
        return ""
    return ""


def calculate_user_wiki_points(activity: WikiActivity, username: str) -> tuple[int, List[str]]:
    """Return the points and action log for *username* on *activity*.

    The function inspects user contributions between ``START_DATE`` and
    ``END_DATE`` on the wiki referenced by ``activity``.  Actions that add
    UNESCO Memory of the World links or labels are translated into points
    and human-readable descriptions that can be surfaced elsewhere.
    """

    site = pywikibot.site.APISite.fromDBName(activity.wiki)
    start_ts = pywikibot.Timestamp.set_timestamp(START_DATE)
    end_ts = pywikibot.Timestamp.set_timestamp(END_DATE)

    total_points = 0
    actions: List[str] = []
    pages_seen: Set[tuple[str, str]] = set()

    for contrib in site.usercontribs(user=username, start=end_ts, end=start_ts):
        timestamp = datetime.fromisoformat(contrib["timestamp"].replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        if timestamp < START_DATE:
            break
        if timestamp > END_DATE:
            continue

        revid = contrib["revid"]
        page_obj = pywikibot.Page(site, contrib["title"])

        if activity.wiki == "wikidatawiki":
            title = contrib["title"]
            comment = contrib.get("comment", "")

            if title in fetch_unesco_items() and (
                "wbsetlabel" in comment or "wbeditentity-update-languages" in comment
            ):
                revision = page_obj.get_revision(revid, content=True)
                if SKIP_TAGS & set(revision.tags):
                    continue

                parentid = revision.parentid
                new_text = revision.text or "{}"
                old_text = page_obj.getOldVersion(parentid) if parentid else "{}"
                try:
                    new_labels = json.loads(new_text).get("labels", {})
                    old_labels = json.loads(old_text).get("labels", {})
                except Exception:  # pragma: no cover - defensive parsing
                    continue

                added_languages = [lang for lang in new_labels if lang not in old_labels]
                num_labels = len(added_languages)
                if num_labels == 0:
                    continue

                item_link = "{{Q|" + title + "}}"
                rev_link = f"[[:d:Special:Diff/{revid}|{revid}]]"
                lang_links = ", ".join([f"{{{{{lang}}}}}" for lang in added_languages])
                actions.append(
                    f"* +{num_labels} points, on {activity.wiki} added label(s) {lang_links} "
                    f"to {item_link} (rev {rev_link})"
                )
                total_points += num_labels
            continue

        revision = page_obj.get_revision(revid, content=True)
        prefix = activity.wiki.replace("wiki", "")
        link = f"[[:{prefix}:{page_obj.title()}]]"
        rev_link = f"[[:{prefix}:Special:Diff/{revid}|{revid}]]"

        parentid = revision.parentid
        new_text = revision.text or ""
        old_text = page_obj.getOldVersion(parentid) if parentid else ""

        if not (
            UNESCO_PATTERN.search(new_text) and not UNESCO_PATTERN.search(old_text)
        ):
            continue

        if SKIP_TAGS & set(revision.tags):
            continue

        page_key = (activity.wiki, page_obj.title())
        if page_key in pages_seen:
            continue
        pages_seen.add(page_key)

        creator = get_creator(page_obj)
        points = 2
        action_desc = f"added UNESCO link in {link}"
        if creator == username:
            points = 5
            action_desc = f"created article {link} with UNESCO link in it"
            try:
                item = pywikibot.ItemPage.fromPage(page_obj)
                item.get()
                if any(
                    claim.getTarget().id == "Q13406463" for claim in item.claims.get("P31", [])
                ):
                    points = 25
                    action_desc = f"created list article {link} with UNESCO link in it"
            except Exception:  # pragma: no cover - network interaction
                pass

        actions.append(
            f"* +{points} points, on {activity.wiki} {action_desc} (rev {rev_link})"
        )
        total_points += points

    return total_points, actions
