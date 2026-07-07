"""Sync database schema with SQLAlchemy models by adding missing columns."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any

import asyncpg


@dataclass
class ColumnDef:
    name: str
    type_: str
    nullable: bool = True
    default: str | None = None


# Define all model columns per table (taken from the SQLAlchemy models)
# Only listing columns that might be missing from the initial migration
TABLES: dict[str, list[ColumnDef]] = {
    "users": [
        ColumnDef("nin_verified", "BOOLEAN", default="FALSE"),
        ColumnDef("nin_verification_reference", "VARCHAR(128)"),
        ColumnDef("face_verified", "BOOLEAN", default="FALSE"),
    ],
    "devices": [
        ColumnDef("play_integrity_fail_count", "INTEGER", default="0"),
        ColumnDef("last_ip_address", "VARCHAR(45)"),
        ColumnDef("last_gps_lat", "FLOAT"),
        ColumnDef("last_gps_lng", "FLOAT"),
    ],
    "virtual_accounts": [
        ColumnDef("is_primary", "BOOLEAN", default="FALSE"),
    ],
    "identity_verifications": [
        ColumnDef("id_type", "VARCHAR(10)"),
        ColumnDef("id_number_encrypted", "VARCHAR(512)"),
        ColumnDef("provider", "VARCHAR(50)"),
        ColumnDef("provider_reference", "VARCHAR(128)"),
        ColumnDef("face_match_score", "FLOAT"),
        ColumnDef("face_verified", "BOOLEAN", default="FALSE"),
        ColumnDef("verified_at", "TIMESTAMPTZ"),
        ColumnDef("failure_reason", "VARCHAR(255)"),
    ],
}


async def get_existing_columns(conn: Any, table: str) -> set[str]:
    rows = await conn.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = $1
        """,
        table,
    )
    return {row["column_name"] for row in rows}


async def main() -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("ERROR: DATABASE_URL environment variable is required")
        return 1

    conn = await asyncpg.connect(dsn)
    try:
        total_added = 0
        for table, columns in TABLES.items():
            existing = await get_existing_columns(conn, table)
            for col in columns:
                if col.name in existing:
                    continue
                parts = [f"ADD COLUMN IF NOT EXISTS {col.name} {col.type_}"]
                if not col.nullable:
                    parts.append("NOT NULL")
                if col.default is not None:
                    parts.append(f"DEFAULT {col.default}")
                sql = f"ALTER TABLE {table} {' '.join(parts)}"
                await conn.execute(sql)
                print(f"  + {table}.{col.name} ({col.type_})")
                total_added += 1

        if total_added == 0:
            print("All columns already exist — schema is in sync.")
        else:
            print(f"\nAdded {total_added} missing column(s).")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(main()))
