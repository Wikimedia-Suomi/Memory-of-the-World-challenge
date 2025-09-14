"""Utility functions for the Memory of the World challenge.

These helpers fetch challenge participants and related information from
Wikimedia using Pywikibot.  The module is used by the Django management
command ``load_participants``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Set

import pywikibot

from challenge.models import Participant, WikiActivity


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

    cutoff = datetime.now(timezone.utc) - timedelta(days=33)
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
            if editcount == 0 or "wikipedia.org" not in url:
                continue

            wiki_db = merged["wiki"]
            activity, _ = WikiActivity.objects.get_or_create(
                participant=participant, wiki=wiki_db
            )

            if activity.editcount != editcount:
                lang = url.split("//")[-1].split(".")[0]
                wiki_site = pywikibot.Site(lang, "wikipedia")
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
    33 days.  The returned mapping uses the wiki database name as the key
    and a sorted list of page titles as the value.
    """

    # UNESCO publishes the Memory of the World site in these languages
    languages = ["", "ar", "en", "es", "fr", "ru", "zh"]

    cutoff = datetime.now(timezone.utc) - timedelta(days=33)
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
