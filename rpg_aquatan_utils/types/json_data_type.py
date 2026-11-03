from __future__ import annotations
from typing import TypedDict, Literal
from rpg_aquatan_utils.types.expr_descriptions import *
from rpg_aquatan_utils.types.execution_info import *

class CommentWindowInfo(TypedDict):
    detail: list[list[str]]
    hover: list[list[ExprDescription]]
    func_groups: list[FuncWarpGroup]
    type: str

# typeは型情報, lineは引数の宣言位置
class ArgInfo(TypedDict):
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
    args: dict[str, ArgInfo]
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

# treasure_event = {
#     "type": "TREASURE", 
#     "x": int(treasure.local_pos[1]+self.offset["x"]), 
#     "y": int(treasure.local_pos[0]+self.offset["y"]),
#     "name": treasure.name,
#     "initializer": treasure.var_info["varNode"], 
#     "start": treasure.var_info["start"],
#     "end": treasure.var_info["end"], 
#     "funcWarp": func_warp, 
#     "func": treasure.func_name
# }
# class Treasure_Info

# move_event = {
#     "type": "MOVE", 
#     "x": int(move_event.local_from_pos[1]+self.offset["x"]), 
#     "y": int(move_event.local_from_pos[0]+self.offset["y"]),
#     "func": move_event.func_name,
#     "dest_x": int(move_event.local_to_pos[1]+self.offset["x"]), 
#     "dest_y": int(move_event.local_to_pos[0]+self.offset["y"]), 
#     "dest_map": program_name,
#     "execution_info": move_event.execution_info,
#     "detail": self.convert_to_comment_window_info(move_event.comment_window_info),
#     "mapchip": move_event.mapchip
# }

# chara_return = {
#     "type": "CHARARETURN", 
#     "name": "15161" if chara_return.func_name else "15084", 
#     "x": int(chara_return.local_pos[1]+self.offset["x"]), 
#     "y": int(chara_return.local_pos[0]+self.offset["y"]),
#     "dest_map": program_name,
#     "dir": 0, 
#     "movetype": 1, 
#     "message": ("Congraturations !! Here is A Goal !!" if self.is_english else "おめでとうございます!! ここがゴールです!!") if chara_return.func_name == "main" else (f"This is the end of function {chara_return.func_name} !!" if self.is_english else f"ここが {chara_return.func_name} の終了地点です!!"), 
#     "execution_info": chara_return.execution_info,
#     "detail": self.convert_to_comment_window_info(chara_return.comment_window_info),
#     "func": chara_return.func_name
# }

# chara_check_condition = {
#     "type": "CHARACHECKCONDITION", 
#     "name": str(color), 
#     "x": pos[1], 
#     "y": pos[0], 
#     "dir": chara_checkCondition.dir, 
#     "moveDir": move_dir,
#     "movetype": 1, 
#     "message": "Condition checked !! Get through here !!" if self.is_english else "条件文を確認しました！!　どうぞお通りください！!", 
#     "func": chara_checkCondition.func,
#     "execution_info": chara_checkCondition.execution_info, 
#     "detail": self.convert_to_comment_window_info(chara_checkCondition.comment_window_info)
# }

# detail_by_line[firstLine] = {
#     "expr": self.convert_to_comment_window_info(detail["expr"]), 
#     "execution_info": detail["execution_info"],
#     "vars": [
#         {
#             "name": var_reference[0], 
#             "line": var_reference[1]
#         } 
#         for var_reference in detail["vars"]
#     ]
# }

# chara_expression = {
#     "type": "CHARAEXPRESSION", 
#     "name": "15165", 
#     "x": int(chara_expression.local_pos[1]+self.offset["x"]), 
#     "y": int(chara_expression.local_pos[0]+self.offset["y"]), 
#     "dir": 0,
#     "movetype": 1, 
#     "message": "updated values of items !!" if self.is_english else "変数の値を新しい値で更新できました!!", 
#     "func": chara_expression.func, 
#     "comments": detail_by_line
# }

class SendEvent(TypedDict):
    message: str
    status: Literal["ok", "ng", "rollback", "rollback_success", "rollback_fail"]
    first_func: NotRequired[str]
    line: NotRequired[int]
    from_line: NotRequired[int]
    is_end: NotRequired[Literal[True]]
    is_finished: NotRequired[Literal[True]]
    items: NotRequired[dict[str, dict[int | str, VariableValue]]]
    item: NotRequired[DeclaredVariableInfo]
    func: NotRequired[str]
    skip: NotRequired[Literal[True]]
    skipped_function_list: NotRequired[list[list[str]] | None]
    next_func: NotRequired[NextFunctionInfo]
    vars_w_value_changed: NotRequired[list[VariablePartWithValue]]
    vars_w_value_unchanged: NotRequired[list[VariablePartWithValue]]
    function_return_info: NotRequired[FunctionReturnInfo]
    gvars: NotRequired[dict[str, dict[int | str, VariableValue]]]
    vars: NotRequired[list[dict[str, dict[int | str, VariableValue]]]]
    std: NotRequired[list[str]]
    files: NotRequired[list[FileInfo]]
    memory: NotRequired[list[MemoryAllocation | MemoryFree]]
    str: NotRequired[list[StrcpyInfo]]
    removed: list[VariableDeclarationInfo]
    execution_and_result_str_list: list[ExecutionAndResultStr]

class DeclaredVariableInfo(TypedDict):
    value: VariableValue
    line: int
    initialized: bool

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
    items: dict[str, dict[int | str, ArgumentItemInfo]]

class ArgumentItemInfo(TypedDict):
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

