"""Tests for SQLite persistence."""

from tamagodji.pet import PetState
from tamagodji.storage import PetStore


def test_store_round_trip(tmp_path) -> None:
    """A saved state can be restored in a fresh store instance."""

    path = tmp_path / "pet.db"
    expected = PetState(hunger=80, happiness=12, asleep=True, last_event="light_level")
    PetStore(path).save(expected)
    restored = PetStore(path).load()
    assert restored == expected

