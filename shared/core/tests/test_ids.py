"""Tests for core ID generation contracts."""

from shared.core.ids import IDPrefix, generate_id, generate_ulid
from shared.utils.id_generator import IDPrefix as CompatIDPrefix
from shared.utils.id_generator import generate_id as compat_generate_id


def test_generate_id_uses_prefix() -> None:
    value = generate_id(IDPrefix.EVENT)

    assert value.startswith("evt_")
    assert len(value.split("_", maxsplit=1)[1]) == 26


def test_generate_ulid_returns_plain_ulid() -> None:
    value = generate_ulid()

    assert len(value) == 26
    assert "_" not in value


def test_legacy_utils_id_generator_reexports_core_contracts() -> None:
    assert CompatIDPrefix is IDPrefix
    assert compat_generate_id is generate_id
