#!/usr/bin/env python3
"""Fetch challenge participants from Wikimedia and display or save them.

This script uses Pywikibot to read the usernames listed on the
"Memory of the World challenge" participants page.  Usernames can be
printed to standard output or written to a file.  Login is optional for
public pages but can be requested for private pages.  With the
``--wikis`` option the script also lists Wikipedia projects each user
edited recently, and ``--unesco`` reports which pages on those wikis
link to UNESCO's "Memory of the World" website.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Set

import pywikibot


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
    each project before adding it to the user's list.
    """

    cutoff = datetime.now(timezone.utc) - timedelta(days=32)
    result: Dict[str, List[str]] = {}
    for name in usernames:
        request = site.simple_request(
            action="query",
            meta="globaluserinfo",
            guiuser=name,
            guiprop="merged",
        )
        data = request.submit()
        wikis: List[str] = []
        for merged in data["query"]["globaluserinfo"].get("merged", []):
            url = merged.get("url", "")
            if merged.get("editcount", 0) == 0 or "wikipedia.org" not in url:
                continue

            lang = url.split("//")[-1].split(".")[0]
            wiki_site = pywikibot.Site(lang, "wikipedia")
            user = pywikibot.User(wiki_site, name)
            last_edit = next(user.contributions(total=1), None)
            if not last_edit:
                continue
            timestamp = last_edit[1].to_datetime() if hasattr(last_edit[1], "to_datetime") else last_edit[1]
            if timestamp >= cutoff:
                wikis.append(merged["wiki"])
        result[name] = wikis
    return result



def fetch_unesco_pages(wikis: Iterable[str]) -> Dict[str, List[str]]:
    """Return pages that link to the UNESCO Memory of the World site.

    *wikis* should be an iterable of database names such as ``"enwiki"``.
    For each wiki the function queries ``exturlusage`` and collects titles
    of pages that contain links whose URL includes ``memory-world`` either
    directly or with a language code such as ``/en/memory-world``.  The
    returned mapping uses the wiki database name as the key and a sorted
    list of page titles as the value.
    """

    # UNESCO publishes the Memory of the World site in these languages
    languages = ['', 'ar', 'en', 'es', 'fr', 'ru', 'zh']

    result: Dict[str, List[str]] = {}
    for wiki in wikis:
        wiki_site = pywikibot.site.APISite.fromDBName(wiki)
        pages: Set[str] = set()
        for lang in languages:
            suffix = f'/{lang}/memory-world' if lang else '/memory-world'
            query = f'www.unesco.org{suffix}'
            for page in wiki_site.exturlusage(query, protocol='https'):
                pages.add(page.title())
        result[wiki] = sorted(pages)
    return result

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Load usernames from the Memory of the World challenge participants page"
        )
    )
    parser.add_argument(
        "-o", "--output", type=Path, help="write the usernames to this file"
    )
    parser.add_argument(
        "--login", action="store_true", help="log in before reading the page"
    )
    parser.add_argument(
        "--page",
        default="Memory_of_the_World_challenge_2025/Participants",
        help="title of the participants page",
    )
    parser.add_argument(
        "--wikis",
        action="store_true",
        help="also fetch Wikipedia projects each user edited in the last 32 days",
    )
    parser.add_argument(
        "--unesco",
        action="store_true",
        help="list pages on those wikis that link to the UNESCO Memory of the World site",
    )
    args = parser.parse_args()

    site = pywikibot.Site("meta", "meta")
    if args.login:
        site.login()

    page = pywikibot.Page(site, args.page)
    try:
        usernames = extract_usernames(page)
    except pywikibot.exceptions.APIError as e:  # login required
        if e.code in {"readapidenied", "permissiondenied"}:
            pywikibot.error(
                "Login is required to read this page. Use --login with valid credentials."
            )
            return 1
        raise

    if args.wikis:
        wiki_map = fetch_user_wikis(site, usernames)
        lines = [f"{user}: {', '.join(wiki_map[user])}" for user in usernames]

        if args.unesco:
            all_wikis = sorted({w for wikis in wiki_map.values() for w in wikis})
            unesco_map = fetch_unesco_pages(all_wikis)
            lines.append("")
            lines.append("Pages linking to UNESCO Memory of the World:")
            for wiki in all_wikis:
                pages = unesco_map.get(wiki, [])
                listing = ", ".join(pages) if pages else "(none)"
                lines.append(f"{wiki}: {listing}")

        write_output(lines, args.output)
    else:
        write_output(usernames, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
