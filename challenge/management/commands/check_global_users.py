from __future__ import annotations

from typing import Iterable

from django.core.management.base import BaseCommand, CommandError

from django.db import transaction

from challenge.models import Participant, WikiActivity

from pywikibot.data.superset import SupersetQuery


class Command(BaseCommand):
    """Check whether usernames exist in the globaluser table."""

    help = (
        "Query centralauth_p.globaluser via the Superset API and report whether each "
        "Participant username exists."
    )

    def handle(self, *args, **options) -> None:  # pragma: no cover - side effects
        usernames: list[str] = list(
            Participant.objects.order_by("username").values_list("username", flat=True)
        )

        if not usernames:
            self.stdout.write(self.style.WARNING("No participants found."))
            return

        sql = self._build_sql(usernames)

        try:
            query = SupersetQuery(schema_name="centralauth_p")
            results = query.query(sql)
        except Exception as exc:  # pragma: no cover - network/IO errors
            raise CommandError(f"Failed to execute Superset query: {exc}") from exc

        found_usernames = self._extract_usernames(results)

        missing = [username for username in usernames if username not in found_usernames]

        for username in usernames:
            status = "FOUND" if username in found_usernames else "NOT FOUND"
            self.stdout.write(f"{username}: {status}")

        if missing:
            return

        active_wikis = (
            WikiActivity.objects.filter(active=True, participant__username__in=usernames)
            .values_list("wiki", flat=True)
            .distinct()
        )

        if not active_wikis:
            return

        for wiki in active_wikis:
            schema_name = f"{wiki}_p"
            activity_sql = self._build_activity_sql(usernames)

            try:
                activity_query = SupersetQuery(schema_name=schema_name)
                activity_results = activity_query.query(activity_sql)
            except Exception as exc:  # pragma: no cover - network/IO errors
                raise CommandError(
                    f"Failed to execute Superset query for {wiki}: {exc}"
                ) from exc

            counts = self._extract_activity_counts(activity_results)
            self._update_wiki_activity(wiki, usernames, counts)

    def _build_sql(self, usernames: Iterable[str]) -> str:
        """Build a safe SQL query for the provided usernames."""
        sanitized = [self._escape(username) for username in usernames]
        in_clause = ", ".join(sanitized)
        return "SELECT gu_name FROM globaluser WHERE gu_name IN (" + in_clause + ")"

    def _build_activity_sql(self, usernames: Iterable[str]) -> str:
        sanitized = [self._escape(username) for username in usernames]
        in_clause = ", ".join(sanitized)
        return (
            "select actor_name, count(distinct(rev_id)) as rev_ids, "
            "count(distinct(ar_id)) as ar_ids "
            " from revision_userindex LEFT JOIN change_tag ON ct_rev_id=rev_id "
            "LEFT JOIN change_tag_def ON ct_tag_id=ctd_id AND ctd_name IN ("
            "'mw-reverted', 'mw-manual-revert', 'mw-undo', 'mw-rollback'), actor "
            "LEFT JOIN archive_userindex ON ar_actor = actor_id AND ar_namespace =0 "
            "AND ar_timestamp > BINARY('20250801000000'), page "
            f"WHERE actor_name IN ({in_clause}) AND actor_id=rev_actor AND rev_page=page_id "
            "AND page_namespace=0 AND rev_timestamp > BINARY('20250801000000') "
            "AND ct_id IS NULL GROUP BY actor_name"
        )

    @staticmethod
    def _escape(value: str) -> str:
        """Escape a username for use inside a SQL string literal."""
        escaped = value.replace("'", "''")
        return f"'{escaped}'"

    @staticmethod
    def _extract_usernames(rows) -> set[str]:
        """Extract the gu_name values from Superset query rows."""
        found: set[str] = set()
        for row in rows:
            if isinstance(row, dict):
                candidate = row.get("gu_name")
            elif isinstance(row, (list, tuple)):
                candidate = row[0] if row else None
            else:
                candidate = None
            if isinstance(candidate, str):
                found.add(candidate)
        return found

    @staticmethod
    def _extract_activity_counts(rows) -> dict[str, tuple[int, int]]:
        counts: dict[str, tuple[int, int]] = {}
        for row in rows:
            if isinstance(row, dict):
                name = row.get("actor_name")
                rev_ids = row.get("rev_ids")
                ar_ids = row.get("ar_ids")
            elif isinstance(row, (list, tuple)):
                name = row[0] if len(row) > 0 else None
                rev_ids = row[1] if len(row) > 1 else None
                ar_ids = row[2] if len(row) > 2 else None
            else:
                name = rev_ids = ar_ids = None

            if isinstance(name, str):
                counts[name] = (
                    int(rev_ids) if isinstance(rev_ids, (int, float)) else 0,
                    int(ar_ids) if isinstance(ar_ids, (int, float)) else 0,
                )
        return counts

    def _update_wiki_activity(
        self, wiki: str, usernames: Iterable[str], counts: dict[str, tuple[int, int]]
    ) -> None:
        activities = list(
            WikiActivity.objects.filter(wiki=wiki, participant__username__in=usernames)
        )

        updates: list[WikiActivity] = []
        for activity in activities:
            username = activity.participant.username
            rev_ids, ar_ids = counts.get(username, (0, 0))
            if activity.rev_count != rev_ids or activity.ar_count != ar_ids:
                activity.rev_count = rev_ids
                activity.ar_count = ar_ids
                updates.append(activity)

        if updates:
            with transaction.atomic():
                WikiActivity.objects.bulk_update(updates, ["rev_count", "ar_count"])
