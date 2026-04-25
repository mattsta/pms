"""Shared typed aliases for model serialization payloads."""

from __future__ import annotations

from datetime import datetime

type JsonPrimitive = str | int | float | bool | None
type JsonArray = list["JsonValue"]
type JsonObject = dict[str, "JsonValue"]
type JsonValue = JsonPrimitive | JsonArray | JsonObject

type ModelPrimitive = JsonPrimitive | datetime
type StringList = list[str]
type NestedStringList = list[StringList]
type IntMap = dict[str, int]
type FloatMap = dict[str, float]
type StringMap = dict[str, str]

type ModelArray = list["ModelValue"]
type ModelObject = dict[str, "ModelValue"]
type ModelTuple = tuple["ModelValue", ...]
type ModelValue = (
    ModelPrimitive
    | JsonValue
    | StringList
    | NestedStringList
    | IntMap
    | FloatMap
    | StringMap
    | ModelArray
    | ModelObject
    | ModelTuple
)
