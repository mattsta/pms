"""Shared database typing aliases."""

from __future__ import annotations

from typing import Protocol

from pms.models.json_types import ModelValue

type SqlParam = str | int | float | bool | bytes | None
type SqlParamTuple = tuple[SqlParam, ...]
type SqlNamedParams = dict[str, SqlParam]
type SqlParams = SqlParamTuple | SqlNamedParams

type DbValue = ModelValue
type DbRow = dict[str, DbValue]
type DbRows = list[DbRow]


class RowcountResult(Protocol):
    """Execution result supporting rowcount access."""

    rowcount: int


type ExecuteResult = RowcountResult | str | int
