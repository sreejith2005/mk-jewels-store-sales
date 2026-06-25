from __future__ import annotations

import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from storage.db import Database  # noqa: E402


STORES = [
    ("Bandra", "bandra"),
    ("Andheri", "andheri"),
    ("Zaveri Bazaar", "zaveri-bazaar"),
    ("Sindhu Bhavan Road", "sindhu-bhavan-road"),
    ("CG Road", "cg-road"),
]

BANDRA_SALESPERSONS = [
    ("Uma Sehgal", "Senior Sales Executive"),
    ("Ashwani Wadhwani", "Sales Executive"),
    ("Chaya Kolekar", "Sales Executive"),
    ("Sanika Kadam", "Sales Assistant"),
    ("Neha Jaiswal", "Sales Manager"),
    ("Shraddha Chandlekar", "Sales Executive"),
    ("Deepa Bhosale", "Senior Sales Executive"),
    ("Archana Chavan", "Senior Sales Executive"),
    ("Mahesh Surve", "Senior Sales Executive"),
    ("Riya Mahto", "Sales Executive"),
    ("Sunita Pingle", "Sales Assistant"),
    ("Saurabh Dvivedi", "Sales Executive"),
    ("Bhavna Shinde", "Sales Executive"),
    ("Poonamdevi", "Sales Assistant"),
    ("Rajesh Kumar", "Sales Executive"),
]


def main() -> None:
    db = Database()
    try:
        seeded_stores = _seed_stores(db)
        seeded_salespersons = _seed_bandra_salespersons(db)
        _seed_default_bandra_pins(db)
    finally:
        db.close()

    print(f"Seeded {seeded_stores} stores, {seeded_salespersons} salespersons")
    print("Default PIN 0000 set for all salespersons. Change before production.")


def _seed_stores(db: Database) -> int:
    created_at = db._utc_now()
    seeded_count = 0

    with db._lock:
        if db._backend == "postgres":
            connection = db._pool.getconn()
            try:
                with connection.cursor() as cursor:
                    for name, slug in STORES:
                        cursor.execute(
                            """
                            INSERT INTO stores (name, slug, created_at)
                            VALUES (%s, %s, %s)
                            ON CONFLICT DO NOTHING
                            """,
                            (name, slug, created_at),
                        )
                        seeded_count += cursor.rowcount
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                db._pool.putconn(connection)
            return seeded_count

        cursor = db._connection.cursor()
        try:
            for name, slug in STORES:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO stores (name, slug, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (name, slug, created_at),
                )
                seeded_count += cursor.rowcount
            db._connection.commit()
        finally:
            cursor.close()

    return seeded_count


def _seed_bandra_salespersons(db: Database) -> int:
    created_at = db._utc_now()
    seeded_count = 0

    with db._lock:
        if db._backend == "postgres":
            connection = db._pool.getconn()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT id FROM stores WHERE slug = %s", ("bandra",))
                    row = cursor.fetchone()
                    if row is None:
                        raise RuntimeError("Bandra store must exist before seeding salespersons.")
                    store_id = row[0]

                    for name, designation in BANDRA_SALESPERSONS:
                        cursor.execute(
                            """
                            INSERT INTO salespersons (
                                store_id,
                                name,
                                designation,
                                is_active,
                                created_at
                            )
                            SELECT %s, %s, %s, 1, %s
                            WHERE NOT EXISTS (
                                SELECT 1
                                FROM salespersons
                                WHERE store_id = %s
                                    AND name = %s
                            )
                            ON CONFLICT DO NOTHING
                            """,
                            (
                                store_id,
                                name,
                                designation,
                                created_at,
                                store_id,
                                name,
                            ),
                        )
                        seeded_count += cursor.rowcount
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                db._pool.putconn(connection)
            return seeded_count

        cursor = db._connection.cursor()
        try:
            cursor.execute("SELECT id FROM stores WHERE slug = ?", ("bandra",))
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("Bandra store must exist before seeding salespersons.")
            store_id = row["id"]

            for name, designation in BANDRA_SALESPERSONS:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO salespersons (
                        store_id,
                        name,
                        designation,
                        is_active,
                        created_at
                    )
                    SELECT ?, ?, ?, 1, ?
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM salespersons
                        WHERE store_id = ?
                            AND name = ?
                    )
                    """,
                    (
                        store_id,
                        name,
                        designation,
                        created_at,
                        store_id,
                        name,
                    ),
                )
                seeded_count += cursor.rowcount
            db._connection.commit()
        finally:
            cursor.close()

    return seeded_count


def _seed_default_bandra_pins(db: Database) -> int:
    salesperson_ids = _get_bandra_salesperson_ids_without_pin(db)

    for salesperson_id in salesperson_ids:
        db.set_salesperson_pin(salesperson_id, "0000")

    return len(salesperson_ids)


def _get_bandra_salesperson_ids_without_pin(db: Database) -> list[int]:
    with db._lock:
        if db._backend == "postgres":
            connection = db._pool.getconn()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT salespersons.id
                        FROM salespersons
                        INNER JOIN stores ON stores.id = salespersons.store_id
                        WHERE stores.slug = %s
                            AND salespersons.pin_hash IS NULL
                        """,
                        ("bandra",),
                    )
                    return [row[0] for row in cursor.fetchall()]
            finally:
                db._pool.putconn(connection)

        rows = db._connection.execute(
            """
            SELECT salespersons.id
            FROM salespersons
            INNER JOIN stores ON stores.id = salespersons.store_id
            WHERE stores.slug = ?
                AND salespersons.pin_hash IS NULL
            """,
            ("bandra",),
        ).fetchall()

    return [row["id"] for row in rows]


if __name__ == "__main__":
    main()
