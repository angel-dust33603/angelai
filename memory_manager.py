import sqlite3
from pathlib import Path


MEMORY_DIRECTORY = Path.home() / "AngelAI" / "memory"
DATABASE_FILE = MEMORY_DIRECTORY / "memory.db"


class MemoryManager:

    def __init__(self):

        MEMORY_DIRECTORY.mkdir(
            parents=True,
            exist_ok=True
        )

        self.connection = sqlite3.connect(
            DATABASE_FILE
        )

        self.connection.row_factory = sqlite3.Row

        self._create_tables()

    # ---------------------------------------------------------
    # DATABASE SETUP
    # ---------------------------------------------------------

    def _create_tables(self):

        cursor = self.connection.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                memory TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'general',
                importance INTEGER NOT NULL DEFAULT 5,
                created_at TIMESTAMP,
                updated_at TIMESTAMP
            )
            """
        )

        self.connection.commit()

    # ---------------------------------------------------------
    # NORMALIZE MEMORY
    # ---------------------------------------------------------

    def _normalize(self, text: str):

        return " ".join(
            text.lower().strip().split()
        )

    # ---------------------------------------------------------
    # CHECK FOR DUPLICATE
    # ---------------------------------------------------------

    def find_duplicate(self, memory: str):

        normalized_memory = self._normalize(memory)

        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM memories
            """
        )

        rows = cursor.fetchall()

        for row in rows:

            existing = self._normalize(
                row["memory"]
            )

            if existing == normalized_memory:

                return dict(row)

        return None

    # ---------------------------------------------------------
    # SAVE MEMORY
    # ---------------------------------------------------------

    def remember(
        self,
        memory: str,
        category: str = "general",
        importance: int = 5
    ):

        duplicate = self.find_duplicate(
            memory
        )

        cursor = self.connection.cursor()

        if duplicate:

            memory_id = duplicate["id"]

            cursor.execute(
                """
                UPDATE memories
                SET
                    category = ?,
                    importance = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    category,
                    importance,
                    memory_id
                )
            )

            self.connection.commit()

            return memory_id

        cursor.execute(
            """
            INSERT INTO memories (
                memory,
                category,
                importance,
                created_at,
                updated_at
            )
            VALUES (
                ?,
                ?,
                ?,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            )
            """,
            (
                memory,
                category,
                importance
            )
        )

        self.connection.commit()

        return cursor.lastrowid

    # ---------------------------------------------------------
    # UPDATE MEMORY
    # ---------------------------------------------------------

    def update(
        self,
        memory_id: int,
        memory: str,
        category: str = None,
        importance: int = None
    ):

        existing = self.get(
            memory_id
        )

        if existing is None:

            return False

        if category is None:

            category = existing["category"]

        if importance is None:

            importance = existing["importance"]

        cursor = self.connection.cursor()

        cursor.execute(
            """
            UPDATE memories
            SET
                memory = ?,
                category = ?,
                importance = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                memory,
                category,
                importance,
                memory_id
            )
        )

        self.connection.commit()

        return cursor.rowcount > 0

    # ---------------------------------------------------------
    # SEARCH
    # ---------------------------------------------------------

    def search(
        self,
        query: str,
        limit: int = 10
    ):

        cursor = self.connection.cursor()

        search_terms = [
            term
            for term in query.lower().split()
            if term
        ]

        if not search_terms:

            return []

        conditions = []
        parameters = []

        for term in search_terms:

            conditions.append(
                """
                (
                    LOWER(memory) LIKE ?
                    OR LOWER(category) LIKE ?
                )
                """
            )

            wildcard = f"%{term}%"

            parameters.extend(
                [
                    wildcard,
                    wildcard
                ]
            )

        sql = f"""
            SELECT *
            FROM memories
            WHERE {" AND ".join(conditions)}
            ORDER BY importance DESC, updated_at DESC
            LIMIT ?
        """

        parameters.append(
            limit
        )

        cursor.execute(
            sql,
            parameters
        )

        return [
            dict(row)
            for row in cursor.fetchall()
        ]

    # ---------------------------------------------------------
    # GET ALL
    # ---------------------------------------------------------

    def get_all(self):

        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM memories
            ORDER BY id ASC
            """
        )

        return [
            dict(row)
            for row in cursor.fetchall()
        ]

    # ---------------------------------------------------------
    # GET MEMORY
    # ---------------------------------------------------------

    def get(self, memory_id: int):

        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT *
            FROM memories
            WHERE id = ?
            """,
            (
                memory_id,
            )
        )

        row = cursor.fetchone()

        if row is None:

            return None

        return dict(row)

    # ---------------------------------------------------------
    # DELETE MEMORY
    # ---------------------------------------------------------

    def forget(self, memory_id: int):

        cursor = self.connection.cursor()

        cursor.execute(
            """
            DELETE FROM memories
            WHERE id = ?
            """,
            (
                memory_id,
            )
        )

        self.connection.commit()

        return cursor.rowcount > 0

    # ---------------------------------------------------------
    # CLOSE
    # ---------------------------------------------------------

    def close(self):

        if self.connection:

            self.connection.close()