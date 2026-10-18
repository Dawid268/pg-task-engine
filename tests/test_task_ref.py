from dataclasses import FrozenInstanceError
from typing import cast

import pytest

from pg_task_engine.task_ref import TaskRef


def test_task_ref_stores_name_and_version() -> None:
    task = TaskRef(name="generate_pdf", version=1)

    assert task.name == "generate_pdf"
    assert task.version == 1


@pytest.mark.parametrize(
    "invalid_name",
    ["", "   ", "\t"],
    ids=["empty", "spaces", "tab"],
)
def test_task_ref_rejects_blank_name(invalid_name: str) -> None:
    with pytest.raises(ValueError, match="name"):
        TaskRef(name=invalid_name, version=1)


def test_task_ref_rejects_postgresql_incompatible_null_character() -> None:
    with pytest.raises(ValueError, match="name"):
        TaskRef(name="generate\x00_pdf", version=1)


@pytest.mark.parametrize("invalid_version", [0, -1], ids=["zero", "negative"])
def test_task_ref_rejects_non_positive_version(invalid_version: int) -> None:
    with pytest.raises(ValueError, match="version"):
        TaskRef(name="generate_pdf", version=invalid_version)


@pytest.mark.parametrize("invalid_name", [123, None, False])
def test_task_ref_rejects_non_string_name(invalid_name: object) -> None:
    with pytest.raises(TypeError, match="name"):
        TaskRef(name=cast("str", invalid_name), version=1)


@pytest.mark.parametrize(
    "invalid_version",
    [True, 2.0, 1.5, "2", None],
    ids=["boolean", "integral-float", "fractional-float", "string", "none"],
)
def test_task_ref_rejects_non_integer_version(invalid_version: object) -> None:
    with pytest.raises(TypeError, match="version"):
        TaskRef(name="generate_pdf", version=cast("int", invalid_version))


def test_task_ref_is_immutable() -> None:
    task = TaskRef(name="generate_pdf", version=1)
    attribute = "name"

    with pytest.raises(FrozenInstanceError):
        setattr(task, attribute, "generate_html")


def test_task_ref_compares_by_value_and_is_hashable() -> None:
    first = TaskRef(name="generate_pdf", version=1)
    second = TaskRef(name="generate_pdf", version=1)

    assert first == second
    assert len({first, second}) == 1
    assert first != TaskRef(name="generate_pdf", version=2)
