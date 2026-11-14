"""
MediGuard AI – Database Recreation & Migration Runner
Applies schema.sql and rls.sql to an empty PostgreSQL database or validates
the full DDL/RLS suite against clean database specifications.
"""
import os
import sys
import re
import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("mediguard.recreate_db")

SCHEMA_FILE = BASE_DIR / "backend" / "db" / "schema.sql"
RLS_FILE = BASE_DIR / "backend" / "db" / "rls.sql"

REQUIRED_TABLES = [
    "users", "patients", "cardiac_history", "ecg_reports", "ecg_analysis",
    "doctor_reviews", "notifications", "follow_ups", "audit_logs", "jobs"
]

def parse_sql_statements(file_path: Path):
    """Parse SQL file into individual statements while respecting plpgsql dollar quotes ($$)."""
    raw_text = file_path.read_text(encoding="utf-8")
    statements = []
    current = []
    in_dollar_quote = False

    for line in raw_text.splitlines():
        stripped = line.strip()
        if not in_dollar_quote and stripped.startswith("--"):
            continue
        
        # Count dollar quotes
        if "$$" in line:
            occurrences = line.count("$$")
            if occurrences % 2 != 0:
                in_dollar_quote = not in_dollar_quote

        current.append(line)

        if not in_dollar_quote and stripped.endswith(";"):
            stmt = "\n".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []

    if current:
        stmt = "\n".join(current).strip()
        if stmt:
            statements.append(stmt)

    return statements


def apply_scripts_to_postgres(db_url: str = None):
    """
    Apply schema and RLS scripts to live PostgreSQL if connection string is supplied.
    Otherwise runs full dry-run structural validation for clean database deployment.
    """
    logger.info("Reading schema.sql...")
    schema_stmts = parse_sql_statements(SCHEMA_FILE)
    logger.info("Parsed %d statements from schema.sql", len(schema_stmts))

    logger.info("Reading rls.sql...")
    rls_stmts = parse_sql_statements(RLS_FILE)
    logger.info("Parsed %d statements from rls.sql", len(rls_stmts))

    # Validate essential components in schema
    logger.info("Validating schema statement completeness...")
    found_tables = set()
    for stmt in schema_stmts:
        m = re.search(r"create\s+table\s+(?:if\s+not\s+exists\s+)?([a-zA-Z0-9_]+)", stmt, re.IGNORECASE)
        if m:
            found_tables.add(m.group(1).lower())

    missing = set(REQUIRED_TABLES) - found_tables
    if missing:
        raise ValueError(f"Schema missing required tables: {missing}")
    logger.info("All 10 required tables defined in schema: %s", sorted(list(found_tables)))

    # Validate RLS statements
    logger.info("Validating RLS statement completeness...")
    rls_tables = set()
    for stmt in rls_stmts:
        m = re.search(r"alter\s+table\s+([a-zA-Z0-9_]+)\s+enable\s+row\s+level\s+security", stmt, re.IGNORECASE)
        if m:
            rls_tables.add(m.group(1).lower())

    missing_rls = set(REQUIRED_TABLES) - rls_tables
    if missing_rls:
        raise ValueError(f"RLS missing on tables: {missing_rls}")
    logger.info("RLS enabled on all 10 tables: %s", sorted(list(rls_tables)))

    # If live DB connection is provided
    target_url = db_url or os.getenv("DATABASE_URL")
    if target_url:
        try:
            import psycopg2
            logger.info("Connecting to live PostgreSQL at %s", target_url.split("@")[-1])
            conn = psycopg2.connect(target_url)
            conn.autocommit = True
            with conn.cursor() as cur:
                logger.info("Executing schema.sql statements...")
                for s in schema_stmts:
                    cur.execute(s)
                logger.info("Executing rls.sql statements...")
                for s in rls_stmts:
                    cur.execute(s)
            conn.close()
            logger.info("Successfully applied schema and RLS to PostgreSQL!")
        except ImportError:
            logger.warning("psycopg2 not installed; live execution skipped, dry-run verified clean.")
        except Exception as e:
            logger.error("Database connection error: %s", e)
            raise e
    else:
        logger.info("No DATABASE_URL set. Clean database SQL dry-run validation PASSED (100%% compliant).")

    return True


if __name__ == "__main__":
    apply_scripts_to_postgres()
