"""SQLite persistence for the pet state."""

import json
import sqlite3
from pathlib import Path

from .pet import PetState


class PetStore:
    """Persist one pet state in a small SQLite database."""

    def __init__(self, path: str | Path) -> None:
        """Create a store and initialize its schema."""

        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with sqlite3.connect(self.path) as connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS pet_state "
                    "(id INTEGER PRIMARY KEY CHECK (id = 1), payload TEXT NOT NULL)"
                )
        except sqlite3.Error as error:
            raise RuntimeError(f"Could not initialize pet database: {self.path}") from error

    def load(self) -> PetState | None:
        """Load the saved pet, or return None for a new installation."""

        try:
            with sqlite3.connect(self.path) as connection:
                row = connection.execute("SELECT payload FROM pet_state WHERE id = 1").fetchone()
        except sqlite3.Error as error:
            raise RuntimeError(f"Could not read pet database: {self.path}") from error
        if row is None:
            return None
        return PetState.from_dict(json.loads(row[0]))

    def save(self, state: PetState) -> None:
        """Save the current pet state atomically."""

        payload = json.dumps(state.to_dict())
        try:
            with sqlite3.connect(self.path) as connection:
                connection.execute(
                    "INSERT INTO pet_state (id, payload) VALUES (1, ?) "
                    "ON CONFLICT(id) DO UPDATE SET payload = excluded.payload",
                    (payload,),
                )
        except sqlite3.Error as error:
            raise RuntimeError(f"Could not save pet database: {self.path}") from error

