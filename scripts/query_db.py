"""Small CLI for checking data loaded into PostgreSQL."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    # Allow running this script directly from the project checkout.
    sys.path.insert(0, str(SRC_ROOT))

from sagora_deeds.config import load_database_url
from sagora_deeds.db.queries import (
    find_company_mentions_by_enterprise_number,
    get_stats,
    search_companies_by_name,
)
from sagora_deeds.db.session import make_session_factory


def parse_args() -> argparse.Namespace:
    """Parse simple lookup options for manual verification."""

    parser = argparse.ArgumentParser(description="Query loaded Sagora deed data.")
    parser.add_argument("--enterprise-number", help="Find companies by enterprise number.")
    parser.add_argument("--company-name", help="Case-insensitive company name search.")
    parser.add_argument("--stats", action="store_true", help="Print row counts.")
    return parser.parse_args()


def print_company_rows(rows) -> None:
    """Print compact company/deed/document rows for terminal inspection."""

    for company, deed, document in rows:
        print(
            f"{company.enterprise_number or '-'} | "
            f"{company.company_name or '-'} | "
            f"{deed.deed_type or '-'} | "
            f"{document.file_name}"
        )


def main() -> int:
    """Run the selected query against the configured database."""

    args = parse_args()
    session_factory = make_session_factory(load_database_url())
    with session_factory() as session:
        if args.stats:
            for label, count in get_stats(session).items():
                print(f"{label}: {count}")
        if args.enterprise_number:
            print_company_rows(
                find_company_mentions_by_enterprise_number(
                    session,
                    args.enterprise_number,
                )
            )
        if args.company_name:
            print_company_rows(search_companies_by_name(session, args.company_name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
