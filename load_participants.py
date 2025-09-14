#!/usr/bin/env python3
"""Fetch challenge participants from Wikimedia and display or save them.

This script uses Pywikibot to read the usernames listed on the
"Memory of the World challenge" participants page.  Usernames can be
printed to standard output or written to a file.  Login is optional for
public pages but can be requested for private pages.
"""
from __future__ import annotations

import argparse
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
    """Return a mapping of username to wiki codes they have edited."""
    result: Dict[str, List[str]] = {}
    for name in usernames:
        request = site._simple_request(
            action="query",
            meta="globaluserinfo",
            guiuser=name,
            guiprop="merged",
        )
        data = request.submit()
        wikis = [m["wiki"] for m in data["query"]["globaluserinfo"].get("merged", [])]
        result[name] = wikis
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
        help="also fetch the wikis each user has edited",
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
        write_output(lines, args.output)
    else:
        write_output(usernames, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
