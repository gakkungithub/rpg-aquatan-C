'''変数の型情報'''
from typing import TypedDict, Literal

class BuiltinTypeInfo(TypedDict):
    kind: Literal["builtin"]
    type: str
    children: dict[str, "TypeInfo"]

class TypedefTypeInfo(TypedDict):
    kind: Literal["typedef"]
    type: str
    children: "TypeInfo"

class PointerTypeInfo(TypedDict):
    kind: Literal["pointer"]
    type: str
    children: "TypeInfo"

class ArrayTypeInfo(TypedDict):
    kind: Literal["array"]
    type: str
    size: int
    children: "TypeInfo"

class StructTypeInfo(TypedDict):
    kind: Literal["struct"]
    type: str
    children: dict[str, "TypeInfo"]

class UnionTypeInfo(TypedDict):
    kind: Literal["union"]
    type: str
    children: dict[str, "TypeInfo"]

class EnumTypeInfo(TypedDict):
    kind: Literal["enum"]
    type: str
    children: dict[str, int]

class FunctionTypeInfo(TypedDict):
    kind: Literal["function"]
    type: str
    children: dict[str, "TypeInfo"]

TypeInfo = (
    BuiltinTypeInfo
    | TypedefTypeInfo
    | PointerTypeInfo
    | ArrayTypeInfo
    | StructTypeInfo
    | UnionTypeInfo
    | EnumTypeInfo
    | FunctionTypeInfo
)