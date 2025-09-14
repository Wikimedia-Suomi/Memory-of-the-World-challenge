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
from typing import Iterable, List, Set

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


def write_output(usernames: Iterable[str], output: Path | None) -> None:
    """Write *usernames* either to stdout or to *output* file."""
    if output is None:
        for name in usernames:
            print(name)
    else:
        output.write_text("\n".join(usernames) + "\n", encoding="utf-8")


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

    write_output(usernames, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
