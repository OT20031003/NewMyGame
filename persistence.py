import json
import os
import sqlite3
from typing import Any

DB_PATH = os.path.join(os.path.dirname(__file__), "game_state.db")


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    return sqlite3.connect(db_path)


def init_db(db_path: str = DB_PATH) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS world_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                turn INTEGER NOT NULL,
                turn_year INTEGER NOT NULL,
                index_base_turn INTEGER,
                country_names_json TEXT NOT NULL,
                money_names_json TEXT NOT NULL,
                territory_map_json TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS country_state (
                name TEXT PRIMARY KEY,
                rows_json TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS money_state (
                name TEXT PRIMARY KEY,
                rows_json TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        world_columns = {row[1] for row in conn.execute("PRAGMA table_info(world_state)")}
        if "territory_map_json" not in world_columns:
            conn.execute("ALTER TABLE world_state ADD COLUMN territory_map_json TEXT")
        conn.commit()


def save_world_state(
    turn: int,
    turn_year: int,
    index_base_turn: int,
    country_names: list[str],
    money_names: list[str],
    territory_map: dict[str, Any] | None = None,
    conn: sqlite3.Connection | None = None,
    db_path: str = DB_PATH,
) -> None:
    if conn is None:
        init_db(db_path)
        with get_connection(db_path) as owned_conn:
            save_world_state(
                turn=turn,
                turn_year=turn_year,
                index_base_turn=index_base_turn,
                country_names=country_names,
                money_names=money_names,
                territory_map=territory_map,
                conn=owned_conn,
                db_path=db_path,
            )
            owned_conn.commit()
        return

    conn.execute(
        """
        INSERT INTO world_state (
            id, turn, turn_year, index_base_turn, country_names_json, money_names_json, territory_map_json, updated_at
        ) VALUES (1, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            turn=excluded.turn,
            turn_year=excluded.turn_year,
            index_base_turn=excluded.index_base_turn,
            country_names_json=excluded.country_names_json,
            money_names_json=excluded.money_names_json,
            territory_map_json=excluded.territory_map_json,
            updated_at=CURRENT_TIMESTAMP
        """,
        (
            turn,
            turn_year,
            index_base_turn,
            json.dumps(country_names, ensure_ascii=False),
            json.dumps(money_names, ensure_ascii=False),
            json.dumps(territory_map, ensure_ascii=False) if territory_map is not None else None,
        ),
    )


def load_world_state(db_path: str = DB_PATH) -> dict[str, Any] | None:
    init_db(db_path)
    with get_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT turn, turn_year, index_base_turn, country_names_json, money_names_json, territory_map_json
            FROM world_state
            WHERE id = 1
            """
        ).fetchone()

    if row is None:
        return None

    return {
        "turn": int(row[0]),
        "turn_year": int(row[1]),
        "index_base_turn": int(row[2]) if row[2] is not None else 50,
        "country_names": json.loads(row[3]) if row[3] else [],
        "money_names": json.loads(row[4]) if row[4] else [],
        "territory_map": json.loads(row[5]) if len(row) > 5 and row[5] else None,
    }


def save_country_state(
    name: str,
    rows: list[list[Any]],
    conn: sqlite3.Connection | None = None,
    db_path: str = DB_PATH,
) -> None:
    if conn is None:
        init_db(db_path)
        with get_connection(db_path) as owned_conn:
            save_country_state(name=name, rows=rows, conn=owned_conn, db_path=db_path)
            owned_conn.commit()
        return

    conn.execute(
        """
        INSERT INTO country_state (name, rows_json, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(name) DO UPDATE SET
            rows_json=excluded.rows_json,
            updated_at=CURRENT_TIMESTAMP
        """,
        (name, json.dumps(rows, ensure_ascii=False)),
    )


def load_country_state(name: str, db_path: str = DB_PATH) -> list[list[Any]] | None:
    init_db(db_path)
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT rows_json FROM country_state WHERE name = ?",
            (name,),
        ).fetchone()

    if row is None:
        return None

    return json.loads(row[0])


def save_money_state(
    name: str,
    rows: list[list[Any]],
    conn: sqlite3.Connection | None = None,
    db_path: str = DB_PATH,
) -> None:
    if conn is None:
        init_db(db_path)
        with get_connection(db_path) as owned_conn:
            save_money_state(name=name, rows=rows, conn=owned_conn, db_path=db_path)
            owned_conn.commit()
        return

    conn.execute(
        """
        INSERT INTO money_state (name, rows_json, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(name) DO UPDATE SET
            rows_json=excluded.rows_json,
            updated_at=CURRENT_TIMESTAMP
        """,
        (name, json.dumps(rows, ensure_ascii=False)),
    )


def load_money_state(name: str, db_path: str = DB_PATH) -> list[list[Any]] | None:
    init_db(db_path)
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT rows_json FROM money_state WHERE name = ?",
            (name,),
        ).fetchone()

    if row is None:
        return None

    return json.loads(row[0])
