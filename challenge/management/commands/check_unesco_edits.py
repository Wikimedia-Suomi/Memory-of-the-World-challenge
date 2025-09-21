from __future__ import annotations

from datetime import datetime, timezone
from collections import defaultdict

import pywikibot
from django.core.management.base import BaseCommand

from challenge.models import Participant
from challenge.utils import calculate_user_wiki_points

metasite = pywikibot.Site("meta", "meta")
metasite.login()

class Command(BaseCommand):
    """Check participant edits adding UNESCO Memory of the World links."""

    help = (
        "List participant edits since a given date that add a link to the "
        "UNESCO Memory of the World website."
    )

    def add_arguments(self, parser) -> None:  # pragma: no cover - argparse boilerplate
        parser.add_argument(
            "--since",
            default="2025-08-01T00:00:00Z",
            help="ISO timestamp (UTC) of earliest edit to inspect",
        )

        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Do not write the results to metawiki.",
        )

    def handle(self, *args, **options) -> None:  # pragma: no cover - side effects
        participants = Participant.objects.all()
        points_by_user: defaultdict[str, int] = defaultdict(int)
        actions_by_user: defaultdict[str, list[str]] = defaultdict(list)

        for participant in participants:
            activities = participant.activities.filter(active=True)
            for activity in activities:
                points, actions = calculate_user_wiki_points(activity, participant.username)
                if points:
                    points_by_user[participant.username] += points
                if actions:
                    actions_by_user[participant.username].extend(actions)

       # Write results to Meta-wiki page
        if points_by_user:
            # Build the content for the Meta-wiki page
            page_content = []
#            page_content.append("This is an unofficial UNESCO Memory of the World Challenge results list updated by a bot. Please check the results and also update them manually on the [[Memory of the World challenge 2025/Participants|Participants]] page. ")
#            page_content.append("Detailed point calculation rules are at the end of the page. Please notify on the talk page if there are missing points so the code can be fixed.")
            page_content.append("{{/Header}}")
            page_content.append("== Results ==")
            page_content.append(f"Last updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n")
            
            for user, pts in sorted(
                points_by_user.items(), key=lambda item: item[1], reverse=True
            ):
                page_content.append(f"=== [[USER:{user}|{user}]] (points: {pts}) ===")
                for line in actions_by_user[user]:
                    page_content.append(line)
                page_content.append("")  # Add empty line between users
            
            page_content.append("{{/Info}}")

            # Join all content
            wiki_text = "\n".join(page_content)
            
            # Check if this is a dry run
            dry_run = options.get('dry_run', False)
          
            
            if dry_run:
                self.stdout.write("=== DRY RUN: Content that would be written to Meta-wiki ===")
                self.stdout.write(f"Page: Memory of the World challenge 2025/Participants/Results")
                self.stdout.write(f"Edit summary: Updating UNESCO Memory of the World Challenge results")
                self.stdout.write("--- PAGE CONTENT START ---")
                self.stdout.write(wiki_text)
                self.stdout.write("--- PAGE CONTENT END ---")
                self.stdout.write("=== DRY RUN COMPLETE (no changes made) ===")
            else:
                # Create the Meta-wiki page object
                leaderboard_page = pywikibot.Page(metasite, "Memory of the World challenge 2025/Participants/Results")
                
                # Save the page
                try:
                    leaderboard_page.text = wiki_text
                    leaderboard_page.save(
                        summary="Updating UNESCO Memory of the World Challenge results",
                        minor=False,
                        botflag=True
                    )
                    self.stdout.write(f"Successfully updated leaderboard page: {leaderboard_page.title()}")
                    
                    # Also print to console for debugging
                    self.stdout.write("\n=== Content written to Meta-wiki ===")
                    for user, pts in sorted(
                        points_by_user.items(), key=lambda item: item[1], reverse=True
                    ):
                        self.stdout.write(f"== [[USER:{user}|{user}]] (points: {pts}) ==")
                        for line in actions_by_user[user]:
                            self.stdout.write(line)
                            
                except Exception as e:
                    self.stdout.write(f"Error updating Meta-wiki page: {e}")
                    # Fall back to console output
                    self.stdout.write("\n=== Fallback to console output ===")
                    for user, pts in sorted(
                        points_by_user.items(), key=lambda item: item[1], reverse=True
                    ):
                        self.stdout.write(f"== [[USER:{user}|{user}]] (points: {pts}) ==")
                        for line in actions_by_user[user]:
                            self.stdout.write(line)
        else:
            dry_run = options.get('dry_run', False)
            if dry_run:
                self.stdout.write("=== DRY RUN: No points found for any participants (no page would be created) ===")
            else:
                self.stdout.write("No points found for any participants.")

