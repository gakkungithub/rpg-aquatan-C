from __future__ import annotations
from typing import TypedDict, Literal
from rpg_aquatan_utils.types.expr_descriptions import *
from rpg_aquatan_utils.types.execution_info import *

class CommentWindowInfo(TypedDict):
    detail: list[list[str]]
    hover: list[list[ExprDescription]]
    func_groups: list[FuncWarpGroup | None]
    type: str

# typeは型情報, lineは引数の宣言位置
class ArgInfo(TypedDict):
    name: str
    type: str
    line: int

''' 
nameは関数の名前, x,yはワープ先の位置, argsは引数の名前をキー、その引数の情報を値とする辞書, lineは遷移元の行番, 
childrenは当関数に内包されている関数の数 (例: func1(func2+func3, func4)の場合は、引数に使われているfunc2~func4の総数の3になる) 
'''
class FuncWarp(TypedDict):
    name: str
    x: int
    y: int
    args: list[ArgInfo]
    line: int
    children: int

'''
変数の階層ごとに関数の情報を取得する
nameは階層の名前(変数名), funcは関数情報のリスト
'''
class FuncWarpGroup(TypedDict):
    name: str
    func_warps: list[FuncWarp]

class ExpressionDetail(TypedDict):
    expr: CommentWindowInfo
    execution_info: ExecutionInfo
    vars: list[VarReference]

class TreasureInfo(TypedDict):
    type: Literal["TREASURE"]
    x: int
    y: int
    name: str
    start: int
    end: int
    func_groups: list[FuncWarpGroup | None]
    func: str

class MoveEventInfo(TypedDict):
    type: Literal["MOVE"]
    x: int
    y: int
    func: str
    dest_x: int
    dest_y: int
    dest_map: str
    execution_info: ExecutionInfo | None
    detail: CommentWindowInfo | None
    mapchip: int

class CharaReturn(TypedDict):
    type: Literal["CHARARETURN"]
    name: str
    x: int
    y: int
    dir: int
    movetype: int
    message: str
    execution_info: ExecutionInfo
    detail: CommentWindowInfo
    func: str

class CharaCheckCondition(TypedDict):
    type: Literal["CHARACHECKCONDITION"]
    name: str
    x: int
    y: int
    dir: int
    moveDir: int
    movetype: int
    message: str
    func: str
    execution_info: ExecutionInfo
    detail: CommentWindowInfo

class CharaExpression(TypedDict):
    type: Literal["CHARAEXPRESSION"]
    name: str
    x: int
    y: int
    dir: int
    movetype: int
    message: str
    func: str
    comments: dict[int | str, ExpressionDetail]

class SendEvent(TypedDict):
    message: str
    status: Literal["ok", "ng", "rollback", "rollback_success", "rollback_fail"]
    first_func: NotRequired[str]
    line: NotRequired[int]
    from_line: NotRequired[int]
    is_end: NotRequired[Literal[True]]
    is_finished: NotRequired[Literal[True]]
    items: NotRequired[list[VariableInfo]]
    item: NotRequired[DeclaredVariableInfo]
    func: NotRequired[str]
    skip: NotRequired[Literal[True]]
    skipped_function_list: NotRequired[list[list[str]] | None]
    next_func: NotRequired[NextFunctionInfo]
    vars_w_value_changed: NotRequired[list[VariablePartWithValue]]
    vars_w_value_unchanged: NotRequired[list[VariablePartWithValue]]
    function_return_info: NotRequired[FunctionReturnInfo]
    gvars: NotRequired[list[VariableInfo]]
    vars: NotRequired[list[list[VariableInfo]]]
    std: NotRequired[list[str]]
    files: NotRequired[list[FileInfo]]
    memory: NotRequired[list[MemoryAllocation | MemoryFree]]
    str: NotRequired[list[StrcpyInfo]]
    removed: list[VariableDeclarationInfo]
    execution_and_result_str_list: list[ExecutionAndResultStr]

class DeclaredVariableInfo(TypedDict):
    value: VariableValueWComment | VariableValue
    line: int

class VariableValueWComment(TypedDict):
    value: str | None
    type: str
    comment: str
    children: dict[str, VariableValueWComment]
    initialized: bool
    
class VariableInfo(TypedDict):
    name: str
    line: int
    value: VariableValue

class VariableValue(TypedDict):
    value: str | None
    children: dict[str, VariableValue]

class VariablePartWithValue(TypedDict):
    item: VariableDeclarationInfo
    path: list[str]
    value: str | None

class VariableDeclarationInfo(TypedDict):
    name: str
    line: int

class NextFunctionInfo(TypedDict):
    name: str
    x: int
    y: int
    items: list[ArgumentItemInfo]

class ArgumentItemInfo(TypedDict):
    name: str
    line: int
    value: VariableValue
    type: ArgumentTypeInfo

class ArgumentTypeInfo(TypedDict):
    type: str
    children: list[ArgumentTypeInfo]

class FunctionReturnInfo(TypedDict):
    func_name: str
    index: int
    return_value: str

class ExecutionAndResultStr(TypedDict):
    execution: str
    result: str | None

class FileInfo(TypedDict):
    address: str

class MemoryAllocation(TypedDict):
    type: Literal["malloc", "realloc"]
    size: str
    vartype: str
    # ここは今後直す必要がある (アドレスを取得するために)
    source_address: TextPart | ExprIdPart | None

class MemoryFree(TypedDict):
    type: Literal["free"]
    varname: str
    address: str

class StrcpyInfo(TypedDict):
    value: str | None
    # ここは今後直す必要がある (アドレスを取得するために)
    original: TextPart | ExprIdPart
    # ここは今後直す必要がある (アドレスを取得するために)
    destination: TextPart | ExprIdPart

