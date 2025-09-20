from __future__ import annotations

from typing import Iterable

from django.core.management.base import BaseCommand, CommandError

from challenge.models import Participant

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

        for username in usernames:
            status = "FOUND" if username in found_usernames else "NOT FOUND"
            self.stdout.write(f"{username}: {status}")

    def _build_sql(self, usernames: Iterable[str]) -> str:
        """Build a safe SQL query for the provided usernames."""
        sanitized = [self._escape(username) for username in usernames]
        in_clause = ", ".join(sanitized)
        return "SELECT gu_name FROM globaluser WHERE gu_name IN (" + in_clause + ")"

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
