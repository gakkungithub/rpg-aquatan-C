'''計算式コメントの型情報'''
from __future__ import annotations
from typing import TypedDict, Literal, NotRequired

type ExprDescriptionPart = (
    ExprIdPart
    | TextPart
    | ScalarVariablePart
    | StructVariablePart
    | ArrayVariablePart
    | MacroPart
    | UnaryExprPart
    | AssignmentExprPart
)

class FuncReference(TypedDict):
    name: str
    children: NotRequired[int]

class ExprIdPart(TypedDict):
    expr_id: int

class TextPart(TypedDict):
    text: str

class ScalarVariablePart(TypedDict):
    name: str
    type: Literal["scalar"]

class StructVariablePart(TypedDict):
    parent: ScalarVariablePart | ArrayVariablePart
    type: Literal["struct"]
    members: list[str]

class ArrayVariablePart(TypedDict):
    parent: ScalarVariablePart | StructVariablePart
    type: Literal["array"]
    indexes: list[ExprIdPart | TextPart]

class MacroPart(TypedDict):
    macro: str
    replacement: ExprIdPart | TextPart

class UnaryExprPart(TypedDict):
    operator: Literal["++", "--"]
    operand_id: int
    is_front_operator: bool

class AssignmentExprPart(TypedDict):
    operator: Literal[
        "=",
        "+=", "-=", "*=", "/=", "%=",
        "&=", "|=", "^=", "<<=", ">>="
    ]
    left_operand_id: int
    right_operand_id: int

'''
関数コメントはexprリスト, descriptionリストのどちらに含まれているか、is_customの真偽によってexpr_descriptionによるコメントの構築の仕方を変える
descriptionリストかつis_custom is Trueなら、self.is_englishによって、TextPart(text = f"execute function {func_name} with") + TextPart(text = f"for #{i+1} argument,"), TextPart(text = f"として関数{func_name}を実行します") + TextPart(text = f"を{i+1}個目の実引数,")のどちらかを加える
exprリストかつis_custom is Trueなら、TextPart(text=FunctionPart["func_name"]), TextPart("("), TextPart(")")といったPartを加える
is_custom is Falseについてもそれぞれのルールで構築する
'''
class FunctionComment(TypedDict):
    func_name: str
    is_custom: bool
    description: list[TextPart | ExprIdPart]
    expr: list[TextPart | ExprIdPart]

class Comment(TypedDict):
    id: int
    comment: ExprDescription | FunctionComment
    execution_condition: dict[int, bool]

class ExprDescription(TypedDict):
    description: list[ExprDescriptionPart]
    expr: list[ExprDescriptionPart]

class VarReference(TypedDict):
    name: str
    line: int

# 変数の初期化情報のためのクラス
class VarNode(TypedDict):
    name: str
    type: str
    children: list[VarNode]
    comments: list[Comment]
    # varsはset(tuple)からjsonデータとして使えるように変換する
    vars: list[VarReference]
    funcs: list[FuncReference]
    initialized: bool

class VarInfo(TypedDict):
    varNode: VarNode
    start: int
    end: int

class ExprNodeInfo(TypedDict):
    vars: set[tuple[str, int]]
    funcs: list[FuncReference]
    comments: list[Comment]
    line: int

type NonVarComment = (
    IfConditionsComment
    | WhileConditionComment
    | DoWhileConditionComment
    | ForComment
    | SwitchConditionComment
    | ControlFlowComment
    | ExpressionComment
    | ReturnComment
)

# # IfExecutionInfo 
# # 最初の if の行をキーとして登録する
# # 条件式を値として登録する
# # condition A ~ condition B の行情報も登録しておく
# # その行番内にあればスキップしない ( {} の最後の } で止まらないようにする )
class IfConditionsComment(TypedDict):
    type: Literal["if"]
    conditions: list[IfConditionComment]

class IfConditionComment(TypedDict):
    line: int
    comments: list[Comment]

# # WhileExecutionInfo
# # condition A の行をキーとして登録する 条件式を値として登録する?
class WhileConditionComment(TypedDict):
    type: Literal["while"]
    condition: list[Comment]

# # DoWhileExecutionInfo
# # condition A の行をキーとして登録する 条件式を値として登録する?
class DoWhileConditionComment(TypedDict):
    type: Literal["do_while"]
    condition: list[Comment]

# # ForExecutionInfo
# # condition A の行をキーとして登録する 条件式を値として登録する
class ForComment(TypedDict):
    type: Literal["for"]
    initializer: NotRequired[list[Comment]]
    var_initializer: NotRequired[list[VarInfo]]
    condition: list[Comment]
    change: NotRequired[list[Comment]]

# # SwitchCaseExecutionInfo
# # condition A の行をキーとして登録する
# # caseごとの条件を登録しておく
class SwitchConditionComment(TypedDict):
    type: Literal["switch"]
    condition: list[Comment]
    case_exprs: list[list[SwitchCaseComment]]
    default_index: NotRequired[int]

class SwitchCaseComment(TypedDict):
    comments: list[Comment]
    line: int

# # ControlFlowInfo
# # break, continueまたはgotoラベルの行番をキーとして登録する (gotoラベルはまだ対応していない。今後余裕があれば対応する)
class ControlFlowComment(TypedDict):
    type: Literal["break", "continue"]
    condition_line: int

# # ExpressionExecutionInfo
# # expressionの行番をキーとして登録する
# # その計算式を値として登録する
class ExpressionComment(TypedDict):
    type: Literal["expression"]
    expr: list[Comment]

class ReturnComment(TypedDict):
    type: Literal["return"]
    expr: list[Comment]
