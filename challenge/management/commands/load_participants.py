from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
import pywikibot

from challenge.utils import (
    extract_usernames,
    write_output,
    fetch_user_wikis,
    fetch_unesco_pages,
)


class Command(BaseCommand):
    help = (
        "Load usernames from the Memory of the World challenge participants page"
    )

    def add_arguments(self, parser):
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

    def handle(self, *args, **options):
        site = pywikibot.Site("meta", "meta")
        if options["login"]:
            site.login()

        page = pywikibot.Page(site, options["page"])
        try:
            usernames = extract_usernames(page)
        except pywikibot.exceptions.APIError as e:
            if e.code in {"readapidenied", "permissiondenied"}:
                raise CommandError(
                    "Login is required to read this page. Use --login with valid credentials."
                )
            raise

        if options["wikis"]:
            wiki_map = fetch_user_wikis(site, usernames)
            lines = [f"{user}: {', '.join(wiki_map[user])}" for user in usernames]
            print("--")

            if options["unesco"]:
                all_wikis = sorted({w for wikis in wiki_map.values() for w in wikis})
                unesco_map = fetch_unesco_pages(all_wikis)
                lines.append("")
                lines.append("Pages linking to UNESCO Memory of the World:")
                for wiki in all_wikis:
                    pages = unesco_map.get(wiki, [])
                    listing = ", ".join(pages) if pages else "(none)"
                    lines.append(f"{wiki}: {listing}")

            write_output(lines, options["output"])
        else:
            write_output(usernames, options["output"])
