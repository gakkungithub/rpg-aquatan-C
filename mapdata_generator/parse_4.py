from __future__ import annotations
import sys
import os
import uuid
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import import_lib

import_lib.ensure_package("clang", "clang.cindex")
import_lib.ensure_dot_for_graphviz()
import_lib.ensure_package("graphviz")

import clang.cindex as ci
from graphviz import Digraph

from typing import TypedDict, Literal
from collections.abc import Iterable

from rpg_aquatan_utils.types.types import *
from rpg_aquatan_utils.types.expr_descriptions import *
from rpg_aquatan_utils.types.execution_info import *
from rpg_aquatan_utils.types.map_data_generator import *

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = ROOT_DIR + '/mapdata_for_test'

class BreakerPos(TypedDict):
    nodeID: str
    line: int

BreakInSwitch = TypedDict(
    "BreakInSwitch",
    {
        "level": int,
        "break": list[BreakerPos]
    }
)

LoopBreaker = TypedDict(
    "LoopBreaker",
    {
        "continue": list[BreakerPos],
        "break": list[BreakerPos]
    }
)

unary_front_operator_descriptions = {
    '++': lambda expr: [expr, {"text": "を１増やしてから"}, expr, {"text": "の値を使います"}],
    '--': lambda expr: [expr, {"text": "を１減らしてから"}, expr, {"text": "の値を使います"}],
    '+': lambda expr: [expr, {"text": "の元の値を使います"}],
    '-': lambda expr: [expr, {"text": "の符号を反転した値を使います"}],
    '!': lambda expr: [expr, {"text": "が真なら偽、偽なら真です"}],
    '~': lambda expr: [expr, {"text": "を２進数で表し、各ビットを反転します"}],
    '&': lambda expr: [expr, {"text": "を格納しているアドレスを取得します"}],
    '*': lambda expr: [{"text": "アドレス"}, expr, {"text": "を格納しているアドレスを取得します"}],
}

unary_front_operator_descriptions_en = {
    '++': lambda expr: [{"text": "add 1 to"}, expr, {"text": ", then use value of"}, expr],
    '--': lambda expr: [{"text": "subtract 1 from"}, expr, {"text": ", then use value of"}, expr],
    '+': lambda expr: [{"text": "use value of"}, expr],
    '-': lambda expr: [{"text": "use negative value of"}, expr],
    '!': lambda expr: [{"false if"}, expr, {"text": "is correct, otherwise true"}],
    '~': lambda expr: [{"text": "flip all the bits in binary of"}, expr],
    '&': lambda expr: [{"text": "get address of variable"}, expr],
    '*': lambda expr: [{"text": "scan value of addres"}, expr],
}

unary_back_operator_descriptions = {
    '++': lambda expr: [expr, {"text": "の値を使います。その後、"}, expr, {"text": "を１増やします"}],
    '--': lambda expr: [expr, {"text": "の値を使います。その後、"}, expr, {"text": "を１減らします"}],
}

unary_back_operator_descriptions_en = {
    '++': lambda expr: [{"text": "use value of"}, expr, {"text": "then add 1 to"}, expr],
    '--': lambda expr: [{"text": "use value of"}, expr, {"text": "then subtract 1 from"}, expr],
}

# 環境依存は後で考える (環境を考えないならctypes.sizeofでOK)
sizeof_operator_size = {
    'int' : {
        frozenset() : 4,
        frozenset(['long']) : 4,
        frozenset(['long', 'long']) : 8,
        frozenset(['short']) : 2,
        frozenset(['unsigned']) : 4,
        frozenset(['unsigned', 'long']) : 4,
        frozenset(['unsigned', 'long', 'long']) : 8,
        frozenset(['unsigned', 'short']) : 2,
    },
    'char' : {
        frozenset() : 1,
    },
    'float' : {
        frozenset() : 4,
    },
    'double' : {
        frozenset() : 8,
        frozenset(['long']) : 16,
    },
    'other' : {
        frozenset() : None
    }
}

binary_operator_descriptions = {
    '+': lambda left, right: [left, {"text": "と"}, right, {"text": "の値を足します"}],
    '-': lambda left, right: [left, {"text": "から"}, right, {"text": "を引きます"}],
    '*': lambda left, right: [left, {"text": "と"}, right, {"text": "を掛けます"}],
    '/': lambda left, right: [left, {"text": "を"}, right, {"text": "で割ります"}],
    '%': lambda left, right: [left, {"text": "を"}, right, {"text": "で割った余りを求めます"}],
    '=': lambda left, right: [left, {"text": "に"}, right, {"text": "を代入します"}],
    '==': lambda left, right: [left, {"text": "と"}, right, {"text": "が等しいかどうかを比較します"}],
    '!=': lambda left, right: [left, {"text": "と"}, right, {"text": "が異なるかを比較します"}],
    '<': lambda left, right: [left, {"text": "が"}, right, {"text": "より小さいかを調べます"}],
    '<=': lambda left, right: [left, {"text": "が"}, right, {"text": "以下かを調べます"}],
    '>': lambda left, right: [left, {"text": "が"}, right, {"text": "より大きいかを調べます"}],
    '>=': lambda left, right: [left, {"text": "が"}, right, {"text": "以上かを調べます"}],
    '&&': lambda left, right: [left, {"text": "と"}, right, {"text": "の両方が真かを調べます"}],
    '||': lambda left, right: [left, {"text": "または"}, right, {"text": "のいずれかが真かを調べます"}],
    '&': lambda left, right: [left, {"text": "と"}, right, {"text": "を 2進数で表し、それぞれのビットが両方とも 1 のときに 1 になります"}],
    '|': lambda left, right: [left, {"text": "と"}, right, {"text": "を 2進数で表し、どちらかのビットが 1 であれば 1 になります"}],
    '^': lambda left, right: [left, {"text": "と"}, right, {"text": "を 2進数で表し、ビットが異なるときに１になります"}],
    '<<': lambda left, right: [left, {"text": "を左に"}, right, {"text": "ビット分シフトします。2進数で見ると桁が左にずれて、2の"}, right, {"text": "乗倍になります"}],
    '>>': lambda left, right: [left, {"text": "を右に"}, right, {"text": "ビット分シフトします。2進数で見ると桁が右にずれて、2の"}, right, {"text": "乗で割ったのと同じになります"}],
    ',': lambda left, right: [left, {"text": "を実行して次に"}, right, {"text": "を実行します"}],
}

binary_operator_descriptions_en = {
    '+': lambda left, right: [{"text": "add"}, left, {"text": "and"}, right],
    '-': lambda left, right: [{"text": "subtract"}, right, {"text": "from"}, left],
    '*': lambda left, right: [{"text": "multiply"}, left, {"text": "by"}, right],
    '/': lambda left, right: [{"text": "divide"}, left, {"text": "by"}, right],
    '+': lambda left, right: [{"text": "get remainder dividing"}, left, {"text": "by"}, right],
    '=': lambda left, right: [{"text": "assign"}, right, {"text": "to"}, left],
    '==': lambda left, right: [{"text": "true if"}, left, {"text": "and"}, right, {"text": "are same, otherwise false"}],
    '!=': lambda left, right: [{"text": "true if"}, left, {"text": "and"}, right, {"text": "are different, otherwise false"}],
    '<': lambda left, right: [{"text": "true if"}, left, {"text": "is smaller than"}, right, {"text": ", otherwise false"}],
    '<=': lambda left, right: [{"text": "true if"}, left, {"text": "is smaller or equal to"}, right, {"text": ", otherwise false"}],
    '>': lambda left, right: [{"text": "true if"}, left, {"text": "is bigger than"}, right, {"text": ", otherwise false"}],
    '>=': lambda left, right: [{"text": "true if"}, left, {"text": "is bigger or equal to"}, right, {"text": ", otherwise false"}],
    '&&': lambda left, right: [{"text": "true if both"}, left, {"text": "and"}, right, {"text": "are correct, otherwise false"}],
    '||': lambda left, right: [{"text": "true if either"}, left, {"text": "or"}, right, {"text": "are correct, otherwise false"}],
    '&': lambda left, right: [{"text": "compare each bit of"}, left, {"text": "and"}, right, {"text": ", then produce a number where each bit is 1 if both bits are 1, otherwise 0"}],
    '|': lambda left, right: [{"text": "compare each bit of"}, left, {"text": "and"}, right, {"text": ", then produce a number where each bit is 1 if either bits are 1, otherwise 0"}],
    '^': lambda left, right: [{"text": "compare each bit of"}, left, {"text": "and"}, right, {"text": ", then produce a number where each bit is 1 if both bits are different, otherwise 0"}],
    '<<': lambda left, right: [{"text": "shift"}, left, {"text": "left by"}, right, {"text": "bits. The value becomes"}, left, {"text": "multiplied by 2 to the power of"}, right],
    '>>': lambda left, right: [{"text": "shift"}, left, {"text": "right by"}, right, {"text": "bits. The value becomes"}, left, {"text": "divided by 2 to the power of"}, right],
    ',': lambda left, right: [{"text": "execute"}, left, {"text": "then, execute"}, right],
}

compound_assignment_operator_descriptions = {
    '+=': lambda left, right: [left, {"text": "に"}, right, {"text": "の値を足した結果を"}, left, {"text": "に代入します"}],
    '-=': lambda left, right: [left, {"text": "から"}, right, {"text": "の値を引いた結果を"}, left, {"text": "に代入します"}],
    '*=': lambda left, right: [left, {"text": "に"}, right, {"text": "の値を掛けた結果を"}, left, {"text": "に代入します"}],
    '/=': lambda left, right: [left, {"text": "を"}, right, {"text": "の値で割った結果を"}, left, {"text": "に代入します"}],
    '%=': lambda left, right: [left, {"text": "を"}, right, {"text": "で割った剰余を"}, left, {"text": "に代入します"}],
    '<<=': lambda left, right: [left, {"text": "を"}, right, {"text": "分左シフトした結果を"}, left, {"text": "に代入します"}],
    '>>=': lambda left, right: [left, {"text": "を"}, right, {"text": "分右シフトした結果を"}, left, {"text": "に代入します"}],
    '&=': lambda left, right: [left, {"text": "と"}, right, {"text": "のビットANDを"}, left, {"text": "に代入します"}],
    '|=': lambda left, right: [left, {"text": "と"}, right, {"text": "のビットORを"}, left, {"text": "に代入します"}],
    '^=': lambda left, right: [left, {"text": "と"}, right, {"text": "のビットXORを"}, left, {"text": "に代入します"}],
}

compound_assignment_operator_descriptions_en = {
    '+=': lambda left, right: [{"text": "add"}, right, {"text": "to"}, left, {"text": "then assign the result to"}, left],
    '-=': lambda left, right: [{"text": "subtract"}, right, {"text": "from"}, left, {"text": "then assign the result to"}, left],
    '*=': lambda left, right: [{"text": "multiply"}, left, {"text": "by"}, right, {"text": "then assign the result to"}, left],
    '/=': lambda left, right: [{"text": "divide"}, left, {"text": "by"}, right, {"text": "then assign the result to"}, left],
    '%=': lambda left, right: [{"text": "get remainder dividing"}, left, {"text": "by"}, right, {"text": "then assign the result to"}, left],
    '<<=': lambda left, right: [{"text": "shift"}, left, {"text": "left by"}, right, {"text": "bits, then assign the result to"}, left],
    '>>=': lambda left, right: [{"text": "shift"}, left, {"text": "right by"}, right, {"text": "bits, then assign the result to"}, left],
    '&=': lambda left, right: [{"text": "compare each bit of"}, left, {"text": "and"}, right, {"text": ", and produce a number where each bit is 1 if both bits are 1, otherwise 0, then assign the result to"}, left],
    '|=': lambda left, right: [{"text": "compare each bit of"}, left, {"text": "and"}, right, {"text": ", and produce a number where each bit is 1 if either bits are 1, otherwise 0, then assign the result to"}, left],
    '^=': lambda left, right: [{"text": "compare each bit of"}, left, {"text": "and"}, right, {"text": ", and produce a number where each bit is 1 if both bits are different, otherwise 0, then assign the result to"}, left],
}

# 計算式の情報(var_references, func_references, expr_descriptions)を格納する
class ExprInfo:
    def __init__(self, is_english: bool):
        self.is_english = is_english
        self.var_references: set[tuple[str, int]] = set()
        self.func_references: list[FuncReference] = []
        # 今は標準関数を入れ子にすることも同時に利用することも許可しないのをフラグ変数で管理する
        self.has_standard_func_reference = False
        self.expr_descriptions: list[Comment] = []
        self.id = -1
        # 自作関数の依存関係を適切に描画するためにカウントする必要がある
        self.custom_func_count = 0
    
    def add_var_reference(self, var_path: str, line: int):
        self.var_references.add((var_path, line))

    # 自作関数
    def append_custom_func_reference(self, func_name: str, custom_func_count_in_args: int, comment: FunctionComment, execution_condition: dict[int, bool]):
        if self.has_standard_func_reference:
            sys.exit("standard functions and custom functions cannot be mixed up in our game system")

        self.func_references.append(
            FuncReference(
                name = func_name,
                children = custom_func_count_in_args
            )
        )
        # 自作関数のカウントを1追加する
        self.custom_func_count += 1
        return self.append_function_comment(comment, execution_condition)
    
    # 標準ライブラリ関数
    def set_standard_func_reference(self, func_name: str, comment: FunctionComment, execution_condition: dict[int, bool], **kwargs):
        if self.has_standard_func_reference:
            sys.exit("an expression process cannot contain two or more standard functions")

        '''
        関数の結果はfunc_referencesに記録されている情報から取得でき、その結果をexpr_descriptionに反映する必要
        があるので、その橋渡しのためのexpr_descriptionのidをfunc_referencesに入れておく
        '''
        self.func_references.append(
            FuncReference(
                name = func_name
            )
        )
        self.has_standard_func_reference = True
        return self.append_function_comment(comment, execution_condition)

    def append_expr_description(self, description: list[ExprDescriptionPart], expr: list[ExprDescriptionPart], execution_condition: dict[int, bool]):
        '''
        descriptionは計算式の説明の文字列
        exprは計算式の文字列を構成する辞書
        この辞書のキーは、"text"、"expr_id"、(variable)"type"-"name" or "parent"、"func"-"args"がある
        "text"は埋め込み文字列、"expr_id"はlldbによる動的解析中に値が決まる途中式のid、
        "type"-"name" or "parent" は変数の参照である("name"は変数名、"parent"は構造体や配列の親の型の種類。"type"によっては"indexes"や"members"キーも存在する)
        "macro"はマクロの参照である("macro"はマクロ名、"replacement"はそのマクロの値)
        '''

        self.id += 1
        self.expr_descriptions.append(
            Comment(
                id = self.id,
                comment=ExprDescription(
                    description = description,
                    expr = expr
                ),
                execution_condition = execution_condition
            )
        )
        return ExprIdPart(expr_id = self.id)

    def append_function_comment(self, comment: FunctionComment, execution_condition: dict[int, bool]):
        self.id += 1
        self.expr_descriptions.append(
            Comment(
                id = self.id,
                comment = comment,
                execution_condition = execution_condition
            )
        )
        return ExprIdPart(expr_id = self.id)
    
    def get_unary_operator_description(self, operator_spell: str, operand_expr: ExprDescriptionPart, is_front: bool) -> list[ExprDescriptionPart]:
        if is_front:
            if operator_spell not in unary_front_operator_descriptions:
                sys.exit(f"unary front operator {operator_spell} is not accepted by our game")
            return unary_front_operator_descriptions_en[operator_spell](operand_expr) if self.is_english else unary_front_operator_descriptions[operator_spell](operand_expr)
        else:
            if operator_spell not in unary_back_operator_descriptions:
                sys.exit(f"unary back operator {operator_spell} is not accepted by our game")
            return unary_back_operator_descriptions_en[operator_spell](operand_expr) if self.is_english else unary_back_operator_descriptions[operator_spell](operand_expr)

    def get_sizeof_operator_description(self, type_name: str) -> ExprDescriptionPart:
        tokens = type_name.strip().split()
        non_size_modifiers = {'const', 'volatile', 'extern', 'static', 'register', 'inline'}

        size_tokens = [token for token in tokens if token not in non_size_modifiers]

        base_types = ['int', 'char', 'float', 'double', '_Bool', 'bool']

        base_type = None
        for t in tokens:
            if t in base_types:
                base_type = t
                break
        
        if base_type is not None:
            size_tokens.remove(base_type)
        else:
            base_type = 'int'

        size = sizeof_operator_size.get(base_type, {}).get(frozenset(size_tokens), None)
        if size:
            return {"text": f"get size of {type_name} ({size})" if self.is_english else f"{type_name}のサイズ({size})を取得します"}
        else:
            return {"text": f"get size of {type_name}" if self.is_english else f"{type_name}のサイズを取得します"}

    def get_binary_operator_description(self, operator_spell: str, left_expr: ExprDescriptionPart, right_expr: ExprDescriptionPart) -> list[ExprDescriptionPart]:
        if operator_spell not in binary_operator_descriptions:
            sys.exit(f"binary operator {operator_spell} is not accepted by our game")
        return binary_operator_descriptions_en[operator_spell](left_expr,right_expr) if self.is_english else binary_operator_descriptions[operator_spell](left_expr,right_expr)

    def get_compound_assignment_operator_description(self, operator_spell: str, left_expr: ExprDescriptionPart, right_expr: ExprDescriptionPart) -> list[ExprDescriptionPart]:
        if operator_spell not in compound_assignment_operator_descriptions:
            sys.exit(f"compound assignment operator {operator_spell} is not accepted by our game")
        return compound_assignment_operator_descriptions_en[operator_spell](left_expr,right_expr) if self.is_english else compound_assignment_operator_descriptions[operator_spell](left_expr,right_expr)

                                                                                                                                               
#        db        ad88888ba 888888888888 ad888888b, 88888888888 88                                           88                                         
#       d88b      d8"     "8b     88     d8"     "88 88          88                                           88                                  ,d     
#      d8'`8b     Y8,             88             a8P 88          88                                           88                                  88     
#     d8'  `8b    `Y8aaaaa,       88          ,d8P"  88aaaaa     88  ,adPPYba,  8b      db      d8  ,adPPYba, 88,dPPYba,  ,adPPYYba, 8b,dPPYba, MM88MMM  
#    d8YaaaaY8b     `"""""8b,     88        a8P"     88"""""     88 a8"     "8a `8b    d88b    d8' a8"     "" 88P'    "8a ""     `Y8 88P'   "Y8   88     
#   d8""""""""8b          `8b     88      a8P'       88          88 8b       d8  `8b  d8'`8b  d8'  8b         88       88 ,adPPPPP88 88           88     
#  d8'        `8b Y8a     a8P     88     d8"         88          88 "8a,   ,a8"   `8bd8'  `8bd8'   "8a,   ,aa 88       88 88,    ,88 88           88,    
# d8'          `8b "Y88888P"      88     88888888888 88          88  `"YbbdP"'      YP      YP      `"Ybbd8"' 88       88 `"8bbdP"Y8 88           "Y888  

class AST2Flowchart:
    def __init__(self, program_name: str, c_files: list[str], is_english: bool):
        # 後でcファイルを複数設定できるようにするが、今は簡易的にするために、ファイルは一つだけ許可する
        if len(c_files) != 1:
            sys.exit("number of c files has to be 1")

        self.c_files = c_files
        self.is_english = is_english

        self.dot = Digraph(comment='Control Flow')
        self.diag_list: list[ci.Diagnostic] = []
        self.scanning_func = None
        self.gvar_candidate_crs: dict[str, ci.Cursor] = {}
        self.gvar_info: list[str] = []
        self.func_info_dict: dict[str, FuncInfo] = {}
        self.loopBreaker_list: list[LoopBreaker] = []
        self.break_in_switch_list: list[BreakInSwitch] = []
        self.findingLabel = None
        self.gotoLabel_list = {}
        self.gotoRoom_list: dict[str, dict[str, GotoRoomInfo]] = {}
        self.room_size_estimate: tuple[str, int] | None = None
        self.room_size_info: dict[str, dict[str, int]] = {}
        self.var_info: dict[str, VarInfo] = {}
        self.expr_node_info: dict[str, ExprNodeInfo] = {}
        self.execution_info : dict[str, ExecutionInfo] = {}
        self.line_info_dict: dict[str, LineInfo] = {}
        self.struct_info: dict[str, list[tuple[str, list[int]]]] = {}
        self.macro_pos: dict[tuple[str, int, int], str] = {}

        index = ci.Index.create()
        # macOS の標準ライブラリパス（CommandLineTools SDK使用時）
        sdk_path = '/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk'
        include_path = f'{sdk_path}/usr/include'

        for c_file in c_files:
            tu = index.parse(
                c_file,
                args=[
                    f'-I{include_path}',         # ヘッダ検索パス
                    f'-isysroot', sdk_path,      # SDKルート
                    '-std=c11',                  # C11準拠で解析
                    '-ferror-limit=0',           # すべてのエラーを表示
                    '-fno-builtin',
                    '-D_FORTIFY_SOURCE=0',
                    # '-Wall'                      # 警告を出す（必要なら）
                    # '-Wno-unused-variable'       # unused警告は消去
                ],
                options=ci.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD
            )
            self.write_ast(tu)

        output_dir = f'{DATA_DIR}/{program_name}'
        os.makedirs(output_dir, exist_ok=True)
        
        gv_dot_path = f'{output_dir}/{program_name}'
        self.dot.render(gv_dot_path, format='dot')
        if os.path.exists(gv_dot_path):
            os.remove(gv_dot_path)

        gv_png_path = f'{output_dir}/fc_{program_name}'
        self.dot.render(gv_png_path, format='png')
        if os.path.exists(gv_png_path):
            os.remove(gv_png_path)

    def createNode(self, nodeLabel: str, shape='rect'):
        nodeID = str(uuid.uuid4())
        self.dot.node(nodeID, nodeLabel, shape=shape)
        return nodeID

    def createEdge(self, prev_nodeID, crnt_nodeID, edgeName=""):
        if prev_nodeID and crnt_nodeID:
            self.dot.edge(prev_nodeID, crnt_nodeID, label=edgeName)

    # そのままではAnyになってしまうのでラップメソッドを作る
    def get_cursor_location(self, cursor: ci.Cursor) -> ci.SourceLocation:
        return cursor.location
    
    def get_cursor_file(self, cursor: ci.Cursor):
        return self.get_cursor_location(cursor).file
    
    def get_cursor_line(self, cursor: ci.Cursor):
        return self.get_cursor_location(cursor).line
    
    def get_cursor_column(self, cursor: ci.Cursor):
        return self.get_cursor_location(cursor).column
    
    def get_cursor_offset(self, cursor: ci.Cursor):
        return self.get_cursor_location(cursor).offset

    def get_cursor_spelling(self, cursor: ci.Cursor) -> str:
        if not isinstance(cursor.spelling, str):
            sys.exit("error in type of cursor spell")
        return cursor.spelling
    
    def get_token_spelling(self, token: ci.Token) -> str:
        if not isinstance(token.spelling, str):
            sys.exit("error in type of token spell")
        return token.spelling
    
    def get_cursor_type(self, cursor: ci.Cursor) -> ci.Type:
        if not isinstance(cursor.type, ci.Type):
            sys.exit("error in type of cursor")
        return cursor.type

    def get_cursor_extent(self, cursor: ci.Cursor) -> ci.SourceRange:
        if not isinstance(cursor.extent, ci.SourceRange):
            sys.exit("type of cursor extent has to be ci.SourceRange")
        return cursor.extent
    
    def get_cursor_extent_start(self, cursor: ci.Cursor) -> ci.SourceLocation:
        extent = self.get_cursor_extent(cursor)
        if not isinstance(extent.start, ci.SourceLocation):
            sys.exit("type of cursor extent start has to be ci.SourceLocation")
        return extent.start
    
    def get_cursor_extent_end(self, cursor: ci.Cursor) -> ci.SourceLocation:
        extent = self.get_cursor_extent(cursor)
        if not isinstance(extent.end, ci.SourceLocation):
            sys.exit("type of cursor extent end has to be ci.SourceLocation")
        return extent.end
    
    def createErrorInfo(self, diagnostics: Iterable[ci.Diagnostic]):
        for diag in diagnostics:
            self.diag_list.append(diag)
            print(f"{diag.spelling}, {diag.location.offset}")
            if any(x in diag.spelling for x in ["expected '}'", "expected ';'"]):
                sys.exit("error in a given C program")

    def check_cursor_error(self, cursor: ci.Cursor):
        # カーソルがファイルに属していないならスキップ
        if (file := self.get_cursor_file(cursor)) is None:
            return True

        for diag in self.diag_list:
            # 同じファイルかつ、カーソルの位置が診断より後ろ（または近接）
            if (diag.location.file is not None and
                file.name == diag.location.file.name and
                self.get_cursor_offset(cursor) >= diag.location.offset - 1): 
                print(f"{diag.spelling}")
                sys.exit("error in a given C program")
        return True

    def register_execution_info(self, nodeID: str, execution_info: ExecutionInfo):
        if (key := f'"{nodeID}"') in self.execution_info:
            sys.exit(f"this nodeID {nodeID} is already registered")
        self.execution_info[key] = execution_info
        
    def write_ast(self, tu: ci.TranslationUnit):
        self.createErrorInfo(tu.diagnostics)
        for cr in tu.cursor.get_children():
            if cr.kind == ci.CursorKind.MACRO_INSTANTIATION:
                if self.get_cursor_file(cr):
                    self.macro_pos[(self.get_cursor_file(cr).name, self.get_cursor_line(cr), self.get_cursor_column(cr))] = self.get_cursor_spelling(cr)
                else:
                    sys.exit("error in finding location of macro instantation")
                
        for cursor in tu.cursor.get_children():
            self.check_cursor_error(cursor)
            if cursor.kind == ci.CursorKind.FUNCTION_DECL:
                self.parse_func(cursor)
                # gotoのLabelを登録する
                self.gotoRoom_list[self.scanning_func] = self.gotoLabel_list
                self.gotoLabel_list = {}
            elif cursor.kind == ci.CursorKind.VAR_DECL:
                self.gvar_candidate_crs[self.get_cursor_spelling(cursor)] = cursor
            elif cursor.kind == ci.CursorKind.TYPEDEF_DECL:
                self.parse_typedef(cursor)
            elif cursor.kind == ci.CursorKind.STRUCT_DECL:
                self.parse_struct(cursor)
            elif cursor.kind == ci.CursorKind.UNION_DECL:
                self.parse_union(cursor)
            elif cursor.kind == ci.CursorKind.ENUM_DECL:
                self.parse_enum(cursor)
            
    #関数の宣言or定義
    def parse_func(self, cursor: ci.Cursor):
        #引数あり/なし→COMPなし = 関数宣言, 引数あり/なし→COMPあり = 関数定義
        #引数とCOMPは同じ階層にある

        #現在のカーソルからこの関数の戻り値と引数の型を取得するかどうかは後で考える
        arg_list: list[tuple[str, ci.Type, tuple[int, int]]] = []
        #ノードがなければreturnのノードはつけないようにするため、Noneを設定しておく

        children: list[ci.Cursor] = list(cursor.get_children())
        for cr in children:
            self.check_cursor_error(cr)
            
            if cr.kind == ci.CursorKind.PARM_DECL:
                arg_list.append(
                    (
                        self.get_cursor_spelling(cr), 
                        self.get_cursor_type(cr), 
                        (
                            self.get_cursor_extent_start(cr).line, 
                            self.get_cursor_extent_end(cr).line
                        )
                    )
                )
            elif cr.kind == ci.CursorKind.COMPOUND_STMT:
                func_name = self.get_cursor_spelling(cursor)
                #関数名を最初のノードの名前とする
                nodeID = self.createNode(func_name, 'ellipse')
                #関数の情報を取得し、ビットマップ描画時に取捨選択する
                self.scanning_func = func_name

                self.func_info_dict[func_name] = FuncInfo(nodeID)
                self.line_info_dict[func_name] = LineInfo()

                #関数の最初の部屋情報を作る
                self.room_size_info[self.scanning_func] = {}
                self.create_room_size_estimate(nodeID)

                self.func_info_dict[self.scanning_func].args = [
                    VarInfo(
                        varNode = self.create_var_node(arg_name, self.get_var_type(arg_type)), 
                        start = arg_lines[0], 
                        end = arg_lines[1]
                    )
                    for (arg_name, arg_type, arg_lines) in arg_list
                ]

                nodeID = self.parse_comp_stmt(cr, nodeID)
                self.create_room_size_estimate(None)

                # 戻り値がある関数ならnodeIDはNoneになる
                if nodeID is None:
                    continue

                # つまり、ここからvoid関数の解析になる
                end_line = self.get_cursor_extent_end(cr).line
                self.func_info_dict[self.scanning_func].set_start(end_line)

                self.line_info_dict[self.scanning_func].set_start(end_line)
                self.line_info_dict[self.scanning_func].set_execution_line(end_line)
                return_nodeID = self.createNode(str(end_line), 'lpromoter')
                self.createEdge(nodeID, return_nodeID)
                self.register_execution_info(return_nodeID, create_return_execution_info(None))

    #関数内や条件文内の処理
    def parse_comp_stmt(self, cursor: ci.Cursor, nodeID: str | None, edgeName: str=""):
        # 次の処理の行数を取得するためにカーソルをlistとして取得する
        cursor_stmt_list: list[ci.Cursor] = list(cursor.get_children())
        for i, cr in enumerate(cursor_stmt_list):
            next_nodeID = self.parse_stmt(cr, nodeID, edgeName)
            if i != 0 and nodeID is not None and f'"{nodeID}"' in self.var_info:
                self.create_room_size_estimate(next_nodeID)
            nodeID = next_nodeID
            edgeName = ""

        return nodeID

    # ループのbreakやcontinueの情報を保管する
    def createLoopBreakerInfo(self):
        self.loopBreaker_list.append({"break":[], "continue":[]})
        # switchのブレーカーだけは特別扱い
        if len(self.break_in_switch_list):
            self.break_in_switch_list[-1]["level"] += 1

    def downSwitchBreakerLevel(self):
        if len(self.break_in_switch_list):
            self.break_in_switch_list[-1]["level"] -= 1

    def addLoopBreaker(self, nodeID: str, type: Literal["break"] | Literal["continue"], line: int):
        if len(self.break_in_switch_list) and type == "break":
            if self.break_in_switch_list[-1]["level"]:
                if len(self.loopBreaker_list) == 0:
                    sys.exit("length of loopBreaker_list has to be 1 or more")
                self.loopBreaker_list[-1][type].append(BreakerPos(nodeID=nodeID, line=line))
            else:
                self.break_in_switch_list[-1][type].append(BreakerPos(nodeID=nodeID, line=line))
        else:
            if len(self.loopBreaker_list) == 0:
                sys.exit("length of loopBreaker_list has to be 1 or more")
            self.loopBreaker_list[-1][type].append(BreakerPos(nodeID=nodeID, line=line))

    # 色々な関数内や条件文内のコードの解析を行う
    def parse_stmt(self, cr: ci.Cursor, nodeID: str | None, edgeName: str = "") -> str | None:
        self.check_cursor_error(cr)

        #break or continueの後なら何も行わない。ただし、ラベルを現在探索中でラベルを発見した時はラベルを見る
        if nodeID is None and cr.kind != ci.CursorKind.LABEL_STMT:
            return None
        
        #部屋のサイズを1上げる
        self.room_size_estimate = (self.room_size_estimate[0], self.room_size_estimate[1] + 1)

        # 変数や関数の宣言
        if cr.kind == ci.CursorKind.DECL_STMT:
            children: list[ci.Cursor] = list(cr.get_children())
            if len(children) == 0:
                sys.exit("number of child cursors of declaration statement has to be 1 or more")
            for vcr in children:
                self.check_cursor_error(vcr)
                nodeID = self.parse_var_decl(vcr, nodeID, edgeName)
        elif cr.kind == ci.CursorKind.IF_STMT:
            # 最初行番を変更
            self.line_info_dict[self.scanning_func].set_start(self.get_cursor_line(cr))
            self.func_info_dict[self.scanning_func].set_start(self.get_cursor_line(cr))
            nodeID = self.parse_if_stmt(cr, nodeID, edgeName)
        elif cr.kind == ci.CursorKind.WHILE_STMT:
            # 最初行番を変更
            self.line_info_dict[self.scanning_func].set_start(self.get_cursor_line(cr))
            self.func_info_dict[self.scanning_func].set_start(self.get_cursor_line(cr))
            nodeID = self.parse_while_stmt(cr, nodeID, edgeName=edgeName)
        elif cr.kind == ci.CursorKind.DO_STMT:
            # 最初行番を変更
            self.line_info_dict[self.scanning_func].set_start(self.get_cursor_line(cr))
            self.func_info_dict[self.scanning_func].set_start(self.get_cursor_line(cr))
            nodeID = self.parse_do_stmt(cr, nodeID, edgeName=edgeName)
        elif cr.kind == ci.CursorKind.FOR_STMT:
            # 最初行番を変更
            self.line_info_dict[self.scanning_func].set_start(self.get_cursor_line(cr))
            self.func_info_dict[self.scanning_func].set_start(self.get_cursor_line(cr))
            nodeID = self.parse_for_stmt(cr, nodeID, edgeName=edgeName)
        elif cr.kind == ci.CursorKind.SWITCH_STMT:
            # 最初行番を変更
            self.line_info_dict[self.scanning_func].set_start(self.get_cursor_line(cr))
            self.func_info_dict[self.scanning_func].set_start(self.get_cursor_line(cr))
            nodeID = self.parse_switch_stmt(cr, nodeID, edgeName)
        elif cr.kind == ci.CursorKind.BREAK_STMT:
            break_nodeID = self.createNode("break", "hexagon")
            self.createEdge(nodeID, break_nodeID, edgeName)
            self.addLoopBreaker(break_nodeID, "break", self.get_cursor_line(cr))
            self.line_info_dict[self.scanning_func].set_execution_line(self.get_cursor_line(cr))
            return None
        elif cr.kind == ci.CursorKind.CONTINUE_STMT:
            continue_nodeID = self.createNode("continue", "hexagon")
            self.createEdge(nodeID, continue_nodeID, edgeName)
            self.addLoopBreaker(continue_nodeID, "continue", self.get_cursor_line(cr))
            self.line_info_dict[self.scanning_func].set_execution_line(self.get_cursor_line(cr))
            return None
        elif cr.kind == ci.CursorKind.GOTO_STMT:
            # goto文は優先度が低い上に本システムでの分析が難しいので今は許可しない
            sys.exit("our game does not accept goto statement now")

            # 最初行番を変更
            self.line_info_dict[self.scanning_func].set_start(self.get_cursor_line(cr))
            self.func_info_dict[self.scanning_func].set_start(self.get_cursor_line(cr))
            cr = next(cr.get_children())
            self.check_cursor_error(cr)
            from_nodeID = self.createNode(self.get_cursor_spelling(cr), 'cds')
            self.createEdge(nodeID, from_nodeID, edgeName)
            #ラベルが既出の場合
            if self.get_cursor_spelling(cr) in self.gotoLabel_list:
                self.gotoLabel_list[self.get_cursor_spelling(cr)]["fromNodeID"].append(f'"{self.room_size_estimate[0]}"')
            #まだラベルが既出でない場合
            else:
                self.findingLabel = self.get_cursor_spelling(cr)
                self.gotoLabel_list[self.get_cursor_spelling(cr)] = {"to_nodeID": None, "fromNodeID": [f'"{self.room_size_estimate[0]}"']}
            return None
        elif cr.kind == ci.CursorKind.LABEL_STMT:
            # goto文は優先度が低い上に本システムでの分析が難しいので今は許可しない
            sys.exit("our game does not accept goto label now")

            # 最初行番を変更?
            self.line_info_dict[self.scanning_func].set_start(self.get_cursor_line(cr))
            self.func_info_dict[self.scanning_func].set_start(self.get_cursor_line(cr))
            children: list[ci.Cursor] = list(cr.get_children())
            if len(children) == 0:
                sys.exit("number of child cursors of label statement has to be 1 or more")
            exec_cr = children[0]
            self.check_cursor_error(exec_cr)
            if self.findingLabel:
                if self.findingLabel != self.get_cursor_spelling(cr):
                    return None
                else:
                    self.findingLabel = None
            to_nodeID = self.createNode(self.get_cursor_spelling(cr), 'note')
            self.createEdge(nodeID, to_nodeID)
            # gotoラベルが既出の場合
            if self.get_cursor_spelling(cr) in self.gotoLabel_list:
                self.gotoLabel_list[self.get_cursor_spelling(cr)]["to_nodeID"] = f'"{self.room_size_estimate[0]}"'
            # gotoラベルが既出でない場合
            else:
                self.gotoLabel_list[self.get_cursor_spelling(cr)] = {"to_nodeID": f'"{self.room_size_estimate[0]}"', "fromNodeID": []}
            nodeID = self.parse_stmt(exec_cr, to_nodeID)
        elif cr.kind == ci.CursorKind.RETURN_STMT:
            # 最初行番を変更
            # 今は複数行を許さないようにする
            if self.get_cursor_extent_start(cr).line != self.get_cursor_extent_end(cr).line:
                sys.exit("return statement has to be in one line")

            self.line_info_dict[self.scanning_func].set_start(self.get_cursor_line(cr))
            self.func_info_dict[self.scanning_func].set_start(self.get_cursor_line(cr))

            children = list(cr.get_children())
            if len(children) != 1:
                sys.exit("number of child cursors of return statement has to be 1")
            value_cursor = children[0]

            self.check_cursor_error(value_cursor)
            return_nodeID = self.get_expr(value_cursor, shape='lpromoter', label=f"{self.get_cursor_line(cr)}")

            if len(self.expr_node_info[f'"{return_nodeID}"']["funcs"]) and "children" not in self.expr_node_info[f'"{return_nodeID}"']["funcs"][0]:
                sys.exit("this game does not allow that return statement includes standard functions")

            self.line_info_dict[self.scanning_func].set_return(self.get_cursor_line(cr))
            self.line_info_dict[self.scanning_func].set_execution_line(self.get_cursor_line(cr))

            self.register_execution_info(return_nodeID, create_return_execution_info(self.get_cursor_line(cr)))

            self.createEdge(nodeID, return_nodeID, edgeName)
            return None
        # 関数単独の処理は「計算式」処理に含まれるので、elseで一緒に処理する
        else:
            # 最初行番を変更 
            self.line_info_dict[self.scanning_func].set_start(self.get_cursor_line(cr))
            self.func_info_dict[self.scanning_func].set_start(self.get_cursor_line(cr))
            # ここの計算式は計算式キャラクターに登録する
            expr_nodeID = self.get_expr(cr, shape='rect')
            # 関数に入る前で止まれるようにlineを登録しておく
            self.line_info_dict[self.scanning_func].set_execution_line(self.get_cursor_line(cr))
            self.register_execution_info(expr_nodeID, create_expression_execution_info(self.get_cursor_line(cr)))

            self.createEdge(nodeID, expr_nodeID, edgeName)
            nodeID = expr_nodeID

        return nodeID

    def get_type_spelling(self, type: ci.Type) -> str:
        return type.spelling
    
    # 変数の型情報を取得する
    def get_var_type(self, type: ci.Type) -> TypeInfo:
        """
        ci.Type を再帰的に解析し、
        typedef を含めて最終的な実体型まで全て展開した
        型情報の辞書を返す。
        現在、この型情報は変数宣言にしか使わないので全展開するが、
        今後、もし必要となれば展開しない方法を考える
        """

        # typedef 
        if type.kind == ci.TypeKind.TYPEDEF:
            # typedefを取り除いた実体型 (例: typedef int INT;なら、"int")
            original_type = type.get_canonical()

            return TypedefTypeInfo(
                kind = "typedef",
                type = self.get_type_spelling(type),
                children = self.get_var_type(original_type),
            )

        # ポインタ
        elif type.kind == ci.TypeKind.POINTER:
            # 本ポインタのアドレスが表す値を取得する
            pointee = type.get_pointee()

            return PointerTypeInfo(
                kind = "pointer",
                type = self.get_type_spelling(type),
                children = self.get_var_type(pointee),
            )

        # 配列
        elif type.kind in (ci.TypeKind.CONSTANTARRAY, ci.TypeKind.INCOMPLETEARRAY, ci.TypeKind.VARIABLEARRAY, ci.TypeKind.DEPENDENTSIZEDARRAY):
            # 現在のシステムでは定数長配列だけを扱う (配列長などに関してプログラムが複雑になるため)
            if type.kind != ci.TypeKind.CONSTANTARRAY:
                sys.exit("our game system only receives constant array (e.g. a[3])")

            # 次の階層の型を取得する
            elem_type = type.get_array_element_type()

            return ArrayTypeInfo(
                kind="array",
                type=self.get_type_spelling(type),
                size=type.element_count,
                children=self.get_var_type(elem_type),
            )

        # 構造体・共用体
        elif type.kind == ci.TypeKind.RECORD:
            # どちらの型であるかを判別するためのカーソル
            decl_cursor: ci.Cursor = type.get_decl_cursor()

            self.check_cursor_error(decl_cursor)

            if decl_cursor.kind == ci.CursorKind.STRUCT_DECL:
                # struct = 構造体である場合
                children: dict[str, TypeInfo] = {}

                field_cursor_list: list[ci.Cursor] = list(decl_cursor.get_children())

                if len(field_cursor_list) == 0:
                    sys.exit("number of field cursors has to be 1 or more")

                for field_cursor in field_cursor_list:
                    if field_cursor.kind != ci.CursorKind.FIELD_DECL:
                        continue

                    self.check_cursor_error(field_cursor)

                    children[self.get_cursor_spelling(field_cursor)] = self.get_var_type(self.get_cursor_type(field_cursor))

                return StructTypeInfo(
                    kind = "struct",
                    type = self.get_type_spelling(type),
                    children = children,
                )

            elif decl_cursor.kind == ci.CursorKind.UNION_DECL:
                children: dict[str, TypeInfo] = {}

                field_cursor_list: list[ci.Cursor] = list(decl_cursor.get_children())

                for field_cursor in field_cursor_list:
                    if field_cursor.kind != ci.CursorKind.FIELD_DECL:
                        continue
                    
                    self.check_cursor_error(field_cursor)

                    children[self.get_cursor_spelling(field_cursor)] = self.get_var_type(self.get_cursor_type(field_cursor))

                return UnionTypeInfo(
                    kind = "union",
                    type = self.get_type_spelling(type),
                    children = children,
                )

            else:
                # 構造体・共用体以外のRECORD型について、本ゲームは受け付けない
                raise NotImplementedError(f"Unsupported RECORD declaration: {self.get_type_spelling(type)}")

        # enum
        elif type.kind == ci.TypeKind.ENUM:
            decl_cursor: ci.Cursor = type.get_declaration()

            if not isinstance(decl_cursor, ci.Cursor):
                sys.exit("error in getting declaration cursor of enum")

            # enumの一つ一つの値を格納する辞書
            values: dict[str, int] = {}

            value_cursor_list: list[ci.Cursor] = list(decl_cursor.get_children())

            for value_cursor in value_cursor_list:
                self.check_cursor_error(value_cursor)
                if value_cursor.kind != ci.CursorKind.ENUM_CONSTANT_DECL:
                    sys.exit("Unexpected child cursor of enum declaration (other than ENUM_CONSTANT_DECL)")
                
                if not isinstance(value_cursor.enum_value, int):
                    sys.exit("enum value has to be integer")

                values[self.get_cursor_spelling(value_cursor)] = value_cursor.enum_value

            return EnumTypeInfo(
                kind = "enum",
                type = self.get_type_spelling(type),
                children = values,
            )

        # 基本型
        elif type.kind in (
            # void型
            ci.TypeKind.VOID,

            # bool型 (Cではあり得ないが)
            ci.TypeKind.BOOL,

            # char型
            ci.TypeKind.CHAR_S, ci.TypeKind.CHAR_U, ci.TypeKind.SCHAR, ci.TypeKind.UCHAR,

            # short型
            ci.TypeKind.SHORT, ci.TypeKind.USHORT,

            # int型
            ci.TypeKind.INT, ci.TypeKind.UINT,

            # long型
            ci.TypeKind.LONG, ci.TypeKind.ULONG,

            # long long型
            ci.TypeKind.LONGLONG, ci.TypeKind.ULONGLONG,

            # int128型 (clang特有の型)
            ci.TypeKind.INT128, ci.TypeKind.UINT128,

            # 浮動小数型
            ci.TypeKind.FLOAT, ci.TypeKind.DOUBLE, ci.TypeKind.LONGDOUBLE, ci.TypeKind.FLOAT128,
        ):
            children: dict[str, TypeInfo] = {}
            return BuiltinTypeInfo(
                kind = "builtin",
                type = self.get_type_spelling(type),
                children = children,
            )

        # 関数型 (ここを使うかは未定。現在、関数宣言・定義は個別の解析を行なっている。)
        elif type.kind in (ci.TypeKind.FUNCTIONPROTO, ci.TypeKind.FUNCTIONNOPROTO,):
            children: dict[str, TypeInfo] = {}

            # 戻り値
            return_type: ci.Type = type.get_result()

            if not isinstance(return_type, ci.Type):
                sys.exit("error in getting return type")

            children["return"] = self.get_var_type(return_type)

            # 引数
            for i in range(type.get_num_arg_types()):
                arg_type: ci.Type = type.get_arg_type(i)
                children[f"arg{i}"] = self.get_var_type(arg_type)

            return FunctionTypeInfo(
                kind = "function",
                type = self.get_type_spelling(type),
                children = children,
            )

        # その他
        else:
            sys.exit(f"Unsupported TypeKind: {type.kind}, spelling={self.get_type_spelling(type)}")

    def parse_var_decl(self, cursor: ci.Cursor, nodeID: str | None, edgeName: str = ""):
        #変数名を取得
        var_nodeID = self.createNode(self.get_cursor_spelling(cursor), 'signature')
        # もしstatic変数であれば、self.line_infoやself.func_info_dictの最初の行番が0である場合でも変えない
        isStatic = cursor.storage_class == ci.StorageClass.STATIC

        self.createEdge(nodeID, var_nodeID, edgeName)

        # 変数の型情報は、変数宣言のsignatureノードごとに取得する
        type_info = self.get_var_type(self.get_cursor_type(cursor))
        varNode = self.create_var_node(self.get_cursor_spelling(cursor), type_info)
        
        # 配列の場合
        if self.get_cursor_type(cursor).kind in (ci.TypeKind.CONSTANTARRAY, ci.TypeKind.INCOMPLETEARRAY, ci.TypeKind.VARIABLEARRAY, ci.TypeKind.DEPENDENTSIZEDARRAY):
            if self.get_cursor_type(cursor).kind != ci.TypeKind.CONSTANTARRAY:
                sys.exit("our system cannot receive variable-size array")

            tokens = list(cursor.get_tokens())
            type_info_for_array = type_info

            if "size" not in type_info_for_array:
                sys.exit("error in type_info")
            index_num: int = 0

            content_cursors: list[ci.Cursor] = list(cursor.get_children())
            if len(content_cursors) == 0:
                sys.exit("error in array contents")  

            index_expr_info = ExprInfo(self.is_english)

            for i, token in enumerate(tokens):
                if self.get_token_spelling(token) != '[':
                    continue

                if i+1 < len(tokens) and self.get_token_spelling(token[i+1]) == ']':
                    index_expr_info.append_expr_description(
                        description=[{"text": f"#1 index was automatically set {type_info_for_array["size"]}" if self.is_english else f"最初の添字は {type_info_for_array["size"]} に自動的に設定されます"}], 
                        expr=[{"text": ""}],
                        execution_condition={}
                    )
                    
                    # ここは必ずTypeInfoになるので型を固定する
                    type_info_for_array = type_info_for_array["children"]
                    index_num += 1
                    break
            
            while "size" in type_info_for_array:
                if len(content_cursors) == 0:
                    sys.exit("error in number of children cursors of array")
                expr_description = self.parse_expr(content_cursors.pop(0), index_expr_info, {})
                
                index_expr_info.append_expr_description(
                    description=[
                        {
                            "text": f"#{index_num+1} index was automatically set {type_info_for_array["size"]} (a result of the previous expression)"
                        }
                    ] 
                    if self.is_english else 
                    [
                        {
                            "text": f"{index_num+1}つ目の添字は {type_info_for_array["size"]} (前の計算式の結果) に自動的に設定されます"
                        }
                    ], 
                    expr=[expr_description],
                    execution_condition={}
                )
                type_info_for_array = type_info_for_array["children"]
                index_num += 1

            # 子カーソルの数がおかしい場合
            if len(content_cursors) >= 2:
                sys.exit("error in number of children cursors of array")

            varNode["comments"] = index_expr_info.expr_descriptions
            # 初期化子がある場合
            if len(content_cursors) == 1:
                self.apply_initializer(content_cursors[0], varNode)
            # 初期化子がない場合
            else:
                varNode["comments"].append(
                    Comment(
                        id = len(varNode["comments"])+1,
                        comment = ExprDescription(
                            description = [
                                TextPart(
                                    text = "all element values are indeterminate" if self.is_english else "変数すべての要素が不定値を持ちます"
                                )
                            ],
                            expr = [TextPart(text = "")]
                        ),
                        execution_condition={}
                    )
                )

        # 構造体や共用体
        elif self.get_cursor_type(cursor).get_canonical().kind == ci.TypeKind.RECORD:
            record_kind = self.get_cursor_type(cursor).get_declaration().kind
            if record_kind == ci.CursorKind.STRUCT_DECL:
                # 構造体
                struct_cursors: list[ci.Cursor] = list([cr for cr in cursor.get_children() if self.check_cursor_error(cr)])
                if len(struct_cursors) not in (1,2):
                    sys.exit("number of children cursors in struct variable has to be 1 of 2")

                if struct_cursors[0].kind != ci.CursorKind.TYPE_REF:
                    sys.exit("the first children cursor of struct variable has to be a TYPE_REF cursor")

                # 構造体の宣言の初期化が初期化子によるものなのか、他の構造体の代入によるものなのかでTYPE_REFを削るかどうかを決める
                if len(struct_cursors) == 2 and struct_cursors[1].kind != ci.CursorKind.INIT_LIST_EXPR:
                    struct_cursors.pop(0)

                if struct_cursors[0].kind == ci.CursorKind.TYPE_REF and len(struct_cursors) == 1:
                    # 未初期化の構造体宣言の場合 (struct_cursorsがTYPE_REFのカーソルのみを持つ)
                    varNode["comments"] = [
                        Comment(
                            id = 1,
                            comment = ExprDescription(
                                description = [
                                    TextPart(
                                        text = "this is an uninitialized part" if self.is_english else "初期化されていない要素です"
                                    )
                                ], 
                                expr = [TextPart(text = "")]
                            ),
                            execution_condition={}
                        )
                    ]
                else:
                    '''
                    構造体の初期化
                    struct Student student = {"Alice", {1,2}, 0}; のような初期化子を用いた場合は前者、
                    struct Student student = student1; のような代入を用いた場合は後者に分別される
                    '''
                    # 初期化子
                    if struct_cursors[-1].kind == ci.CursorKind.INIT_LIST_EXPR:
                        self.apply_initializer(struct_cursors[-1], varNode)
                    # 代入の場合
                    else:
                        struct_expr_info = ExprInfo(self.is_english)
                        self.parse_expr(struct_cursors[-1], struct_expr_info, {}, required_expr_description_type={"expr_id"})
                        if struct_expr_info.has_standard_func_reference:
                            sys.exit("this game does not allow that a struct part expression includes standarad functions")
                        varNode["comments"] = struct_expr_info.expr_descriptions
            
            elif record_kind == ci.CursorKind.UNION_DECL:
                # 共用体 (まだ未実装)
                sys.exit("our game cannot analyze union type variable yet")
            
            else:
                # struct, union以外typekindでRECORDを持つことはないが、念のため
                sys.exit("error in AST cursor of RECORD")

        # スカラー変数
        else:
            children: list[ci.Cursor] = list(cursor.get_children())
            if len(children):
                if len(children) == 2:
                    if children[0].kind != ci.CursorKind.TYPE_REF:
                        sys.exit("error in AST of a scalar variable")
                    children.pop(0)
                elif len(children) >= 3:
                    sys.exit("error in number of cursors in a scalar variable")

                self.apply_initializer(children[0], varNode)
            # 変数の初期値が無い場合
            else:
                varNode["comments"] = [
                    Comment(
                        id = 1,
                        comment = ExprDescription(
                            description = [
                                TextPart(
                                    text = "this is an uninitialized item" if self.is_english else "初期化されていないアイテムです"
                                )
                            ], 
                            expr = [TextPart(text = "")]
                        ),
                        execution_condition = {}
                    )
                ]
                
        start_line = self.get_cursor_extent_start(cursor).line
        end_line = self.get_cursor_extent_end(cursor).line

        '''
        今までは複数行にまたがる処理にて、特定の行で止まる場合はその行をcondition_move (現: self.execution_info)
        にそれぞれ含めていたが、これからは処理の最初の行〜最後の行の範囲で確かめる方針にすると良いかも?
        '''
        self.line_info_dict[self.scanning_func].set_start(start_line, isStatic)
        self.func_info_dict[self.scanning_func].set_start(start_line, isStatic)

        self.var_info[f'"{var_nodeID}"'] = VarInfo(
            varNode = varNode, 
            start = start_line, 
            end = end_line
        )

        return var_nodeID

    def create_var_node(self, name: str, type_info: TypeInfo) -> VarNode:
        """
        type_infoから、変数の構造を再帰的に生成する。

        例:
            int a[2][2]

        ↓

            a
            ├── a[0]
            │   ├── a[0][0]
            │   └── a[0][1]
            └── a[1]
                ├── a[1][0]
                └── a[1][1]
        """

        kind = type_info["kind"]
        node = VarNode(
            name = name,
            type = type_info["type"],
            children = [],
            comments = [],
            initialized = False,
        )

        # 配列
        if kind == "array":
            size = type_info["size"]
            child_type_info = type_info["children"]

            for i in range(size):
                child_name = f"{name}[{i}]"

                child_node = self.create_var_node(
                    child_name,
                    child_type_info,
                )

                node["children"].append(child_node)

            return node
        # struct
        elif kind == "struct":
            for field_name, field_type_info in type_info["children"].items():
                child_name = f"{name}.{field_name}"

                child_node = self.create_var_node(child_name, field_type_info)

                node["children"].append(child_node)

            return node
        # union
        elif kind == "union":
            for field_name, field_type_info in type_info["children"].items():
                child_name = f"{name}.{field_name}"

                child_node = self.create_var_node(child_name, field_type_info)

                node["children"].append(child_node)

            return node
        # それ以外の型
        # builtin, pointer, enum, typedef展開後の型 etc.
        else:
            return node
        
    # 変数の初期化の入り口
    def apply_initializer(self, initializer_cursor: ci.Cursor, node: VarNode) -> None:
        if initializer_cursor.kind == ci.CursorKind.INIT_LIST_EXPR:
            self._apply_init_list(initializer_cursor, node)
        else:
            self._apply_single_initializer(initializer_cursor, node)

    # 変数の初期化カーソルを振り分けていく
    def _apply_init_list(self, cursor: ci.Cursor, node: VarNode) -> None:
        initializers = list(cursor.get_children())
        current_index = 0

        for initializer in initializers:
            if current_index >= len(node["children"]):
                raise RuntimeError(
                    f"too many initializers for "
                    f"{node['name']}"
                )

            current_node = node["children"][current_index]

            # 明示的な { ... } 
            # この場合、{}の中を掘り進めていくためにapply_init_listを再帰的に実行する
            if initializer.kind == ci.CursorKind.INIT_LIST_EXPR:
                self._apply_init_list(initializer, current_node)
                current_index += 1
                continue

            # 通常の初期化子( = 単体の初期化子)
            # 一要素用の初期化カーソル振り分けメソッドを実行する
            if self._apply_single_initializer(initializer, current_node):
                current_index += 1

    # 通常の初期化子
    def _apply_single_initializer(self, cursor: ci.Cursor, node: VarNode) -> bool:
        # スカラーの場合は、通常の初期化子としてそのまま当てはめられる
        if len(node["children"]) == 0:
            expr_info = ExprInfo(self.is_english)

            # malloc, realloc, fopenの確認 (メソッド化するべきか?)
            cursor = self.unwrap_unexposed(cursor)
            var_info_for_func: dict[str, any] = {}

            if cursor.kind == ci.CursorKind.CSTYLE_CAST_EXPR:
                self.check_cursor_error(cursor)
                children: list[ci.Cursor] = list(cursor.get_children())
                if len(children) == 1 and self.unwrap_unexposed(children[0]).kind == ci.CursorKind.CALL_EXPR:
                    casted_cursor = self.unwrap_unexposed(children[0])
                    children: list[ci.Cursor] = list(casted_cursor.get_children())
                    if len(children) == 0:
                        sys.exit("number of child cursors of function call cursor has to be bigger than 0")
                    func_name = self.get_cursor_spelling(self.unwrap_unexposed(children[0]))
                    if func_name in ("malloc", "realloc"):
                        var_info_for_func["vartype"] = node["type"][:-1]
            elif cursor.kind == ci.CursorKind.CALL_EXPR:
                casted_cursor = self.unwrap_unexposed(cursor)
                children: list[ci.Cursor] = list(casted_cursor.get_children())
                if len(children) == 0:
                    sys.exit("number of child cursors of function call cursor has to be bigger than 0")
                func_name = self.get_cursor_spelling(self.unwrap_unexposed(children[0]))
                if func_name in ("malloc", "realloc"):
                    var_info_for_func["vartype"] = node["type"][:-1]
                elif func_name == "fopen":
                    var_info_for_func["varname"] = node["name"]

            self.parse_expr(cursor, expr_info, {}, var_info_for_func = var_info_for_func, required_expr_description_type = {"expr_id"})
            if expr_info.has_standard_func_reference and self.get_cursor_extent_start(cursor).line != self.get_cursor_extent_end(cursor).line:
                sys.exit("expression includes standarad functions has to be in a line")

            node["comments"] = expr_info.expr_descriptions
            node["initialized"] = True
            node["vars"] = [
                VarReference(
                    name=var_reference[0],
                    line=var_reference[1]
                )
                for var_reference in expr_info.var_references
            ]
            node["funcs"] = expr_info.func_references
            return True
        elif cursor.kind == ci.CursorKind.STRING_LITERAL:
            str_literals = self.get_cursor_spelling(cursor)
            if len(node["children"]) < len(str_literals):
                sys.exit("error in number of string")

            for i, child in enumerate(node["children"]):
                if len(child["children"]) != 0 or child["type"] != "char":
                    sys.exit("error in string literal initialization")

                child["comments"] = [
                    Comment(
                        id = 1,
                        comment = 
                        ExprDescription(
                            description = [TextPart(text=f"letter '{str_literals[i]}' was set" if self.is_english else f"文字 '{str_literals[i]}' を設定しました")],
                            expr = [TextPart(text=f"'{str_literals[i]}'")]
                        ) if i < len(str_literals) else
                        ExprDescription(
                            description = [TextPart(text="letter '\0' (null) was set" if self.is_english else f"文字 '\0' (ヌル文字) を設定しました")],
                            expr = [TextPart(text="'\0'")]
                        ),
                        execution_condition={} # ここは空辞書で良いのか?
                    )
                ]
                child["initialized"] = True
            node["initialized"] = True
            return True
        # 配列・struct・unionの場合は、そのメンバ、要素に一つずつ設定していく
        else:
            return self._apply_to_first_subobject(cursor, node)

    # 配列・struct・unionの要素にcursorを当てはめる
    # 子要素全てにcursorが当てられていることを確認できたらTrueを返す
    # 当てられていなければ、それを示すためにFalseを返す
    def _apply_to_first_subobject(self, cursor: ci.Cursor, node: VarNode) -> bool:
        for child in node["children"]:
            if self._is_fully_initialized(child):
                continue

            if self._apply_single_initializer(cursor, child):
                return self._is_fully_initialized(node)

            return False

        return True

    # 自分より下の要素が全て初期化されているかを確認する
    def _is_fully_initialized(self, node: VarNode) -> bool:
        # 葉ならその要素を確認するだけでOK
        if len(node["children"]) == 0:
            return node["initialized"]

        # 子がすべて初期化されているか確認
        for child in node["children"]:
            if not self._is_fully_initialized(child):
                return False

        return True

    #式(一つのノードexpNodeに内容をまとめる)
    def get_expr(self, cursor: ci.Cursor, shape='square', label="") -> str:
        expr_nodeID = self.createNode(label, shape)
        expr_info = ExprInfo(self.is_english)

        self.parse_expr(cursor, expr_info, {}, var_info_for_func = {}, required_expr_description_type={"expr_id"})
        if expr_info.has_standard_func_reference and self.get_cursor_extent_start(cursor).line != self.get_cursor_extent_end(cursor).line:
            sys.exit("expression includes standarad functions has to be in a line")

        self.expr_node_info[f'"{expr_nodeID}"'] = ExprNodeInfo(
            vars = expr_info.var_references,
            funcs = expr_info.func_references,
            comments = expr_info.expr_descriptions,
            line = self.get_cursor_line(cursor)
        )

        return expr_nodeID

    def unwrap_unexposed(self, cursor: ci.Cursor) -> ci.Cursor:
        self.check_cursor_error(cursor)
        while cursor.kind == ci.CursorKind.UNEXPOSED_EXPR:
            cursor = next(cursor.get_children())
            self.check_cursor_error(cursor)
        return cursor

    # 式の項を一つずつ解析
    # malloc, realloc, fopenが計算式に含まれる場合は特別な条件の下で解析を行う
    def parse_expr(self, cursor: ci.Cursor, expr_info: ExprInfo, execution_condition: dict[int, bool], var_info_for_func: dict[str, any] = {}, required_expr_description_type: set[Literal["expr_id", "text"]] | None = None) -> ExprDescriptionPart:
        cursor = self.unwrap_unexposed(cursor)

        # 現在の計算式がマクロならその情報を取得する
        if self.get_cursor_file(cursor) is not None and (macro := self.macro_pos.get((self.get_cursor_file(cursor).name, self.get_cursor_line(cursor), self.get_cursor_column(cursor)), None)) is not None:
            '''
            しかし、この条件だけだと、"TEST"といったマクロ単体と、"TEST + a + func(b)"のようなマクロが先頭に含まれる計算式を区別できない
            どちらも、TESTの先頭が位置するファイル、行番、列番が同じになってしまう
            そこで、この条件に加えて、先頭と末尾のcolumnをそれぞれ取得してその差分がマクロ単体の文字数と合致するかを確かめる
            合致するなら現在の計算式がマクロ単体であり、その場合はマクロを取得する
            '''
            if self.get_cursor_column(cursor) + len(macro) != self.get_cursor_extent_end(cursor).column:
                macro = None

        # ()で囲まれている場合
        if cursor.kind == ci.CursorKind.PAREN_EXPR:
            children = list(cursor.get_children())
            if len(children) != 1:
                sys.exit("number of child cursors of paren expression has to be 1")
            inside_paren_cursor = children[0]
            inside_expr_description = self.parse_expr(inside_paren_cursor, expr_info, execution_condition)
            if expr_info.has_standard_func_reference:
                sys.exit("this game does not allow standard function in paren expression")

            expr_description = expr_info.append_expr_description(
                description=[TextPart(text= "primarily calculate part closed with parens ( and )" if self.is_english else "( ) で囲まれている部分は先に計算します")], 
                expr=[TextPart(text = "(" ), inside_expr_description, TextPart(text = ")")],
                execution_condition=execution_condition
            )
        # 定数(関数の引数が変数であるかを確かめるために定数ノードの形は変える)
        elif cursor.kind in (ci.CursorKind.INTEGER_LITERAL, ci.CursorKind.FLOATING_LITERAL, ci.CursorKind.STRING_LITERAL, ci.CursorKind.CHARACTER_LITERAL):
            tokens = list(cursor.get_tokens())
            if len(tokens) != 1:
                sys.exit("number of child tokens of const value has to be 1")

            expr_description = TextPart(text = self.get_token_spelling(tokens[0]))
        # スカラー変数の呼び出し
        elif cursor.kind == ci.CursorKind.DECL_REF_EXPR:
            ref_expr_tokens = list(cursor.get_tokens())
            # マクロなど以外の変数なら、基本的にこのトークンリストの長さは1以上になる
            if len(ref_expr_tokens):
                expr_description = ScalarVariablePart(
                    name = self.get_token_spelling(ref_expr_tokens[0]), 
                    type = "scalar"
                )
                # グローバル変数ならグローバル変数のリファレンスを登録する
                if (gvar_cursor := self.gvar_candidate_crs.pop(expr_description["name"], None)):
                    self.gvar_info.append(f'"{self.parse_var_decl(gvar_cursor, None)}"')
            else:
                expr_description =  ScalarVariablePart(
                    name = self.get_cursor_spelling(cursor),
                    type = "scalar"
                )

            expr_info.add_var_reference(expr_description["name"], self.get_cursor_line(cursor.referenced))
        # 配列
        elif cursor.kind == ci.CursorKind.ARRAY_SUBSCRIPT_EXPR:
            index_list: list[ExprIdPart | TextPart] = []
            # 配列の参照は、添字→添字→・・・→配列名の順で取得する
            while True:
                array_children_cursors = [self.unwrap_unexposed(cr) for cr in list(cursor.get_children()) if self.check_cursor_error(cr)]
                # 子カーソルは、(次の添字または変数名カーソル, 配列の添字カーソル)となる。これを判別する
                if len(array_children_cursors) != 2:
                    sys.exit("length of children cursors of array has to be 2")
                
                index_expr_description = self.parse_expr(array_children_cursors[1], expr_info, execution_condition, required_expr_description_type={"expr_id", "text"})
                index_list.append(index_expr_description)
                if array_children_cursors[0].kind != ci.CursorKind.ARRAY_SUBSCRIPT_EXPR:
                    break

                cursor = array_children_cursors[0]

            parent_expr = self.parse_expr(array_children_cursors[0], expr_info, execution_condition)
            if expr_info.has_standard_func_reference:
                sys.exit("this game does not allow standard function in part of array variables")

            if "type" not in parent_expr or parent_expr["type"] == "array":
                sys.exit("error in array parent")
            
            expr_description = ArrayVariablePart(
                parent = parent_expr,
                indexes = list(reversed(index_list)), 
                type = "array"
            )
        # 構造体のメンバ
        elif cursor.kind == ci.CursorKind.MEMBER_REF_EXPR:
            member_chain: list[str] = []
            member_cursor = cursor
            while member_cursor.kind == ci.CursorKind.MEMBER_REF_EXPR:
                member_chain.append(self.get_cursor_spelling(member_cursor))
                children = list(member_cursor.get_children())
                if children:
                    member_cursor = children[0]
                else:
                    break
            member_cursor = self.unwrap_unexposed(member_cursor)
            # referenceはstudents[i].scores[0]のstudents[i]のようにカーソルのspellingだけでは取得できないものがある。それにも対応できるようにparse_exprメソッドを呼び出す。
            parent_expr = self.parse_expr(member_cursor, expr_info, execution_condition)
            if "type" not in parent_expr or parent_expr["type"] == "struct":
                sys.exit("error in struct reference")

            if expr_info.has_standard_func_reference:
                sys.exit("this game does not allow standard function in part of struct variable")

            expr_description = StructVariablePart(
                parent = parent_expr, 
                members = list(reversed(member_chain)), 
                type = "struct"
            )
        # 関数
        elif cursor.kind == ci.CursorKind.CALL_EXPR:
            expr_description = self.parse_call_expr(
                cursor, 
                expr_info, 
                execution_condition, 
                var_info_for_func
            )
        # 一項式
        elif cursor.kind == ci.CursorKind.UNARY_OPERATOR:
            # ++aでいうaのカーソル
            operand_cursor = next(cursor.get_children())

            child_tokens = list(cursor.get_tokens())

            if len(child_tokens) < 2:
                sys.exit("error in number of child tokens of unary operator")

            operand_expr = self.parse_expr(operand_cursor, expr_info, execution_condition)
            if expr_info.has_standard_func_reference:
                sys.exit("this game does not allow standard function in unary operator expression")

            potential_operator_offset: int = child_tokens[0].location.offset

            if not isinstance(potential_operator_offset, int):
                sys.exit("value of operator offset has to be integer")

            is_front = potential_operator_offset < self.get_cursor_offset(operand_cursor)

            if is_front:
                # ++ といった演算子
                operator_spell = self.get_token_spelling(child_tokens[0])
                expr = [TextPart(text = self.get_token_spelling(operator_spell)), operand_expr]
            else:
                operator_spell = self.get_token_spelling(child_tokens[-1])
                expr = [operand_expr, TextPart(text = self.get_token_spelling(operator_spell))]

            # 前置, 後置で分けてdescriptionを取得する
            description = expr_info.get_unary_operator_description(operator_spell, operand_expr, is_front)
            expr_description = expr_info.append_expr_description(description, expr, execution_condition)
        # c言語特有の一項条件式 (現在はsizeofのみに対応)
        elif cursor.kind == ci.CursorKind.CXX_UNARY_EXPR:
            expr_spell = ' '.join([self.get_token_spelling(t) for t in list(cursor.get_tokens())])
            if 'sizeof' in expr_spell:
                child_cursor_list = list(cursor.get_children())
                if child_cursor_list:
                    type_str = self.get_type_spelling(self.get_cursor_type(self.unwrap_unexposed(child_cursor_list[0])))
                else:
                    type_str = expr_spell.removeprefix("sizeof(").removesuffix(")")

                expr_description = expr_info.append_expr_description(
                    description = [expr_info.get_sizeof_operator_description(type_str)], 
                    expr = [TextPart(text = expr_spell)],
                    execution_condition = execution_condition
                )
            else:
                sys.exit("C unique unary expr operators other than sizeof are not accepted by our game")
        # 二項条件式(a + b)
        elif cursor.kind == ci.CursorKind.BINARY_OPERATOR:
            expr_crs: list[ci.Cursor] = [cr for cr in list(cursor.get_children()) if self.check_cursor_error(cr)]
            if len(expr_crs) != 2:
                sys.exit("number of child cursors of binary operator has to be 2")

            left_expr_end_offset = self.get_cursor_extent_end(expr_crs[0]).offset
            operator_spell: str = ""
            for token in cursor.get_tokens():
                # 前項の位置を最初に超えたtokenが演算子(+や-など)になる
                if left_expr_end_offset <= token.location.offset:
                    operator_spell = self.get_token_spelling(token)
                    break

            if operator_spell == "":
                sys.exit("binary operator is not found")

            left_expr = self.parse_expr(
                expr_crs[0], 
                expr_info, 
                execution_condition, 
                required_expr_description_type = {"expr_id"} if operator_spell in ("&&", "||") else None
            )

            if expr_info.has_standard_func_reference:
                sys.exit("this game does not allow that a standard function is mixed with binary operator expression")

            var_info_for_func = {}

            left_cursor = self.unwrap_unexposed(expr_crs[0])
            right_cursor = self.unwrap_unexposed(expr_crs[1])
            # malloc, realloc, fopenについては、特殊な場合として解析する
            if operator_spell == "=" and left_cursor.kind in (ci.CursorKind.ARRAY_SUBSCRIPT_EXPR, ci.CursorKind.MEMBER_REF_EXPR, ci.CursorKind.DECL_REF_EXPR):
                if right_cursor.kind == ci.CursorKind.CSTYLE_CAST_EXPR:
                    self.check_cursor_error(right_cursor)
                    children: list[ci.Cursor] = list(right_cursor.get_children())
                    if len(children) == 1 and self.unwrap_unexposed(children[0]).kind == ci.CursorKind.CALL_EXPR:
                        casted_cursor = self.unwrap_unexposed(children[0])
                        children: list[ci.Cursor] = list(casted_cursor.get_children())
                        if len(children) == 0:
                            sys.exit("number of child cursors of function call cursor has to be bigger than 0")
                        func_name = self.get_cursor_spelling(self.unwrap_unexposed(children[0]))
                        if func_name in ("malloc", "realloc"):
                            var_info_for_func["vartype"] = self.get_type_spelling(self.get_cursor_type(left_cursor))[:-1]
                elif cursor.kind == ci.CursorKind.CALL_EXPR:
                    casted_cursor = self.unwrap_unexposed(right_cursor)
                    children: list[ci.Cursor] = list(casted_cursor.get_children())
                    if len(children) == 0:
                        sys.exit("number of child cursors of function call cursor has to be bigger than 0")
                    func_name = self.get_cursor_spelling(self.unwrap_unexposed(children[0]))
                    if func_name in ("malloc", "realloc"):
                        var_info_for_func["vartype"] = self.get_type_spelling(self.get_cursor_type(right_cursor))[:-1]
                    elif func_name == "fopen" and left_cursor.kind == ci.CursorKind.DECL_REF_EXPR:
                        if (var_name := self.get_cursor_spelling(left_cursor)):
                          var_info_for_func["varname"] = var_name
                        else:
                          decl_ref_tokens = list(left_cursor.get_tokens())
                          if len(decl_ref_tokens) == 0:
                              sys.exit("number of declaration reference tokens has to be 1 or more")
                          var_name = self.get_token_spelling(decl_ref_tokens[0])
                          var_info_for_func["varname"] = var_name

            # 演算子が && または || の場合、左項 (left_expr) の結果によって右項 (right_expr) が計算されるか決まるので、left_expr を expr_id型に変換して、その id を right_expr を作る際に渡す
            # && の場合、左項が True なら右項は計算される
            # || の場合、左項が False なら右項は計算される
            right_expr = self.parse_expr(
                expr_crs[1], 
                expr_info, 
                {**execution_condition, left_expr["expr_id"]: operator_spell == "&&"} if operator_spell in ("&&", "||") else execution_condition, 
                var_info_for_func
            )

            # = 演算子の場合、このままのexprをEvaluateExpressionにかけると左項の値がlldbのメモリ上で変わってしまうので、lldbの動的解析の際にはright_exprの結果のみを使う
            expr: list[ExprDescriptionPart] = [left_expr, TextPart(text = operator_spell), right_expr]
            description = expr_info.get_binary_operator_description(operator_spell, left_expr, right_expr)
            expr_description = expr_info.append_expr_description(description, expr, execution_condition)
        # 複合代入演算子(a += b)
        elif cursor.kind == ci.CursorKind.COMPOUND_ASSIGNMENT_OPERATOR:
            expr_crs = [cr for cr in list(cursor.get_children()) if self.check_cursor_error(cr)]
            if len(expr_crs) != 2:
                sys.exit("number of child cursors of compound assignment operator has to be 2")
            left_expr_end_offset = self.get_cursor_extent_end(expr_crs[0]).offset
            operator_spell: str = ""
            for token in cursor.get_tokens():
                if left_expr_end_offset <= token.location.offset:
                    operator_spell = self.get_token_spelling(token)
                    break
            
            if operator_spell == "":
                sys.exit("compound assignment operator is not found")
                
            left_expr = self.parse_expr(expr_crs[0], expr_info, execution_condition)
            right_expr =  self.parse_expr(expr_crs[1], expr_info, execution_condition)

            # 複合代入演算子の場合、このままのexprをEvaluateExpressionにかけると左項の値がlldbのメモリ上で変わってしまうので、lldbの動的解析の際には代入しない (例 left_expr += right_expr の場合、left_expr + right_epxr の結果を使う)
            expr: list[ExprDescriptionPart] = [left_expr, TextPart(text = operator_spell), right_expr]
            description = expr_info.get_compound_assignment_operator_description(operator_spell, left_expr, right_expr)
            expr_description = expr_info.append_expr_description(description, expr, execution_condition)

            if expr_info.has_standard_func_reference:
                sys.exit("this game does not allow standard function in compound assignment expression")
        # 三項条件式(c ? a : b) (ここはmallocやrealloc、fopenを許さない)
        elif cursor.kind == ci.CursorKind.CONDITIONAL_OPERATOR:
            expr_crs = [cr for cr in list(cursor.get_children()) if self.check_cursor_error(cr)]
            #まず、条件文を解析し、a : b の aかbを解析する
                        # 三項条件式 (c ? a : b) について、c (condition_expr) の結果によって a (true_expr), b (false_expr) のどちらが計算されるか決まるので、binary operator と同じくをexpr_id型に変換して、その id を true_expr, false_expr を作る際に渡す
            condition_expr = self.parse_expr(
                expr_crs[0], 
                expr_info, 
                execution_condition, 
                required_expr_description_type = {"expr_id"}
            )
            
            # condition_expr が True なら true_expr を計算する
            # condition_expr が False なら false_expr を計算する
            true_expr = self.parse_expr(
                expr_crs[1], 
                expr_info, 
                {**execution_condition, condition_expr["expr_id"]: True}, 
                required_expr_description_type = {"expr_id"}
            )
            false_expr = self.parse_expr(
                expr_crs[2], 
                expr_info, 
                {**execution_condition, condition_expr["expr_id"]: False}, 
                required_expr_description_type = {"expr_id"}
            )
            
            expr = [condition_expr, TextPart(text="?"), true_expr, TextPart(text=":"), false_expr]
            description: list[ExprDescriptionPart] = (
                [TextPart(text = "if"), condition_expr, TextPart(text = "is true, get value of"), true_expr, TextPart(text = ", otherwise get value of"), false_expr] 
                if self.is_english else 
                [condition_expr, TextPart(text = "が真なら"), true_expr, TextPart(text = "、偽なら"), false_expr, TextPart(text = "の値を使います")]
            )
            expr_description = expr_info.append_expr_description(description, expr, execution_condition)
            if expr_info.has_standard_func_reference:
                sys.exit("this game does not allow standard function in conditional operator expression")
        # キャスト型
        elif cursor.kind == ci.CursorKind.CSTYLE_CAST_EXPR:
            children = list(cursor.get_children())
            if len(children) != 1:
                sys.exit("number of child cursors has to be 1")

            if expr_info.has_standard_func_reference:
                sys.exit("this game does not allow that standard function is mixed with cast expression")

            cr = children[0]
            casted_expr = self.parse_expr(cr, expr_info, execution_condition, var_info_for_func = var_info_for_func)
            expr = [TextPart(text = f"({self.get_type_spelling(self.get_cursor_type(cursor))})"), casted_expr]
            casted_expr_type: str = self.get_type_spelling(self.get_cursor_type(self.unwrap_unexposed(cr)))
            description = (
                [TextPart(text = "cast type of"), casted_expr, TextPart(text = f"from {casted_expr_type}"), TextPart(text = f"to {self.get_type_spelling(self.get_cursor_type(cursor))}")]
                if self.is_english else
                [casted_expr, TextPart(text = "の型を"), TextPart(text = f"{casted_expr_type}から{self.get_type_spelling(self.get_cursor_type(cursor))}"), TextPart(text = f"{self.get_type_spelling(self.get_cursor_type(cursor))} に変換します")]
            )
            expr_description = expr_info.append_expr_description(description, expr, execution_condition)
        else:
            sys.exit("error in expression type")

        # マクロ単体の計算式の場合、現在のexpr_descriptionをマクロ型に変換する
        if macro:
            if not ("expr_id" in expr_description or "text" in expr_description):
                expr_description = expr_info.append_expr_description([expr_description], [expr_description], execution_condition)
            expr_description = MacroPart(
                macro = macro, 
                replacement = expr_description
            )

        if required_expr_description_type is not None:
            if not any(t in expr_description for t in required_expr_description_type):
                expr_description = expr_info.append_expr_description([expr_description], [expr_description], execution_condition)

        return expr_description
    
    # 関数の呼び出し(変数と関数の呼び出しは分ける) 
    # 現在、関数を表すノードを生成しているが、他の計算項と同じように、作らないようにする方向でリファクタリングする(その方が楽)
    # 関数の呼び出しの計算コメントは{"name": name, "comment": comment, "args": [arg1, arg2,...]}のように辞書型にする
    # ここのexprやdescriptionのキーをどのように"func"にするかを考える
    def parse_call_expr(self, cursor: ci.Cursor, expr_info: ExprInfo, execution_condition: dict[int, bool], var_info_for_func: dict[str, any] = {}) -> ExprIdPart:
        children: list[ci.Cursor] = list(cursor.get_children())

        # --- 関数名ノードの処理 ---
        func_cursor = self.unwrap_unexposed(children[0])
        self.check_cursor_error(func_cursor)

        func_name = self.get_cursor_spelling(func_cursor)
        self.func_info_dict[self.scanning_func].set_func_reference(func_name)

        arg_expr_description_list: list[TextPart | ExprIdPart] = []

        custom_func_count_in_args: int = 0

        # --- 引数ノードとのエッジ作成 ---
        for arg_cursor in children[1:]:
            arg_expr_info = ExprInfo(self.is_english)
            arg_expr_info.id = expr_info.id
            arg_expr_description: TextPart | ExprIdPart = self.parse_expr(arg_cursor, arg_expr_info, execution_condition, required_expr_description_type={"expr_id", "text"})
            if arg_expr_info.has_standard_func_reference:
                sys.exit("any functions cannot contain standard functions in our game system")
            
            arg_expr_description_list.append(arg_expr_description)
            
            expr_info.var_references.update(arg_expr_info.var_references)
            # ここでfunc_referencesの差分を取るべき?
            expr_info.func_references.extend(arg_expr_info.func_references)
            expr_info.expr_descriptions.extend(arg_expr_info.expr_descriptions)
            expr_info.id = arg_expr_info.id

            custom_func_count_in_args += arg_expr_info.custom_func_count

        # 自作関数は入力されたcファイルまたはhファイルに含まれているので、その是非を確認して自作関数か標準関数かを判別する
        if self.is_custom_function(cursor):
            # 標準関数以外なら自作関数として登録する
            comment = FunctionComment(
                func_name=func_name,
                is_custom=True,
                description=arg_expr_description_list,
                expr=arg_expr_description_list
            )
            # 参照リストへの関数の追加は深さ優先+先がけになるようにここで行う
            return expr_info.append_custom_func_reference(func_name, custom_func_count_in_args, comment, execution_condition)
        else:
            # # 標準関数の引数に自作関数が含まれている場合はそのカウントを追加する(この標準関数が特定の自作関数の引数に含まれている場合に自作関数カウントを使えるようにするために登録する)
            # expr_info.custom_func_count += custom_func_count_in_args
            # しかし、今は本プログラムの複雑性より、標準関数内に自作関数が含まれている場合はエラーを出して終了する
            if custom_func_count_in_args:
                sys.exit("any standard functions cannot contain custom functions in our game system")

            # 標準関数は特別な形でfunc_referencesに登録する
            if func_name == "strcpy":
                if len(arg_expr_description_list) != 2:
                    sys.exit("number of arguments in strcpy has to be 2")

                if var_info_for_func:
                    sys.exit(f"strcpy cannot have {var_info_for_func.keys()} for args")

                var_info_for_func = {
                    "destination": arg_expr_description_list[0], 
                    "original": arg_expr_description_list[1]
                }

                comment = FunctionComment(
                    func_name = func_name, 
                    is_custom = False,
                    description = 
                        [
                            TextPart(text = "copy from"), var_info_for_func["original"], TextPart(text = "to"), var_info_for_func["destination"]
                        ] 
                        if self.is_english else
                        [
                            var_info_for_func["original"], TextPart(text = "の内容を"), var_info_for_func["destination"], TextPart(text = "にコピーします")
                        ],
                    expr = arg_expr_description_list
                )
            elif func_name == "scanf":
                if var_info_for_func:
                    sys.exit(f"scanf cannot have {var_info_for_func.keys()} for args")

                var_info_for_func = {
                    "format": [self.get_token_spelling(t) for t in children[1].get_tokens()][0]
                }

                comment = FunctionComment(
                    func_name = func_name, 
                    is_custom = False, 
                    description =
                        [
                            TextPart(text = f"input awaited... format is {var_info_for_func["format"]}")
                        ]
                        if self.is_english else
                        [
                            TextPart(text = f"入力待ちです、、、 フォーマットは {var_info_for_func["format"]} です")
                        ],
                    expr = arg_expr_description_list
                )

                self.line_info_dict[self.scanning_func].set_stdin(self.get_cursor_line(cursor))
            elif func_name == "fopen":
                if not var_info_for_func:
                    sys.exit("fopen cannot be used not for varialbe value assignment")
                
                var_info_for_func = {
                    **var_info_for_func,
                    "filename": [self.get_token_spelling(t) for t in children[1].get_tokens()][0]
                }

                comment = FunctionComment(
                    func_name=func_name, 
                    is_custom=False, 
                    description =
                        [
                            TextPart(text = f"open file \"{var_info_for_func["filename"]}\"")
                        ]
                        if self.is_english else
                        [
                            TextPart(text = f"ファイル「{var_info_for_func["filename"]}」を開きます")
                        ],
                    expr = arg_expr_description_list
                )
            elif func_name == "fclose":
                if var_info_for_func:
                    sys.exit(f"fclose cannot have {var_info_for_func.keys()} for args")
                var_info_for_func = {
                    "varname": arg_expr_description_list[0]
                }

                comment = FunctionComment(
                    func_name=func_name, 
                    is_custom=False, 
                    description =
                        [
                            TextPart(text = f"close file of address"), var_info_for_func["varname"]
                        ]
                        if self.is_english else
                        [
                            TextPart(text = f"アドレス"), var_info_for_func["varname"], TextPart(text = "が保存しているファイルを閉じます")
                        ],
                    expr = arg_expr_description_list
                )
            elif func_name == "malloc":
                if not var_info_for_func:
                    sys.exit("malloc cannot be used not for varialbe value assignment")

                var_info_for_func = {
                    **var_info_for_func,
                    "size": "".join([self.get_token_spelling(t) for t in children[1].get_tokens()])
                }

                comment = FunctionComment(
                    func_name=func_name, 
                    is_custom=False, 
                    description =
                        [
                            TextPart(text = f"reserve memory in size of {var_info_for_func["size"]}")
                        ]
                        if self.is_english else
                        [
                            TextPart(text = f"{var_info_for_func["size"]}が示すサイズ分のメモリを確保します")
                        ],
                    expr = arg_expr_description_list
                )
            elif func_name == "realloc":
                if not var_info_for_func:
                    sys.exit("realloc cannot be used not for varialbe value assignment")
                var_info_for_func = {
                    **var_info_for_func, 
                    "size": "".join([self.get_token_spelling(t) for t in children[2].get_tokens()]), 
                    "source_address": arg_expr_description_list[0]
                }
                comment = FunctionComment(
                    func_name=func_name, 
                    is_custom=False, 
                    description =
                        [
                            TextPart(text = f"reserve size {var_info_for_func["size"]} memory began with address"), var_info_for_func["source_address"]
                        ]
                        if self.is_english else
                        [
                            var_info_for_func["source_address"], TextPart(text = f"のアドレスを先頭にもつ、{var_info_for_func["size"]}が示すメモリを確保します")
                        ],
                    expr = arg_expr_description_list
                )
            elif func_name == "free":
                if var_info_for_func:
                    sys.exit(f"free cannot have {var_info_for_func.keys()} for args")
                var_info_for_func = {
                    "varname": arg_expr_description_list[0]
                }

                comment = FunctionComment(
                    func_name=func_name, 
                    is_custom=False, 
                    description =
                        [
                            TextPart(text = f"Liberate memory of address"), var_info_for_func["varname"]
                        ]
                        if self.is_english else
                        [
                            TextPart(text = "アドレス"), var_info_for_func["varname"], TextPart(text=f"が示すメモリを解放します")
                        ],
                    expr = arg_expr_description_list
                )
            elif func_name in ("setvbuf", "printf", "fprintf", "fgets", "fscanf"):
                if var_info_for_func:
                    sys.exit(f"{func_name} cannot have {var_info_for_func.keys()} for args")

                comment = FunctionComment(
                    func_name=func_name, 
                    is_custom=False, 
                    description =
                        [
                            TextPart(text = f"execute function {func_name}")
                        ]
                        if self.is_english else
                        [
                            TextPart(text = f"関数{func_name}を実行します")
                        ],
                    expr = arg_expr_description_list
                )
            else:
                sys.exit(f"standard function \"{func_name}\" cannot be analyzed by our system")

            return expr_info.set_standard_func_reference(func_name, comment, execution_condition, **var_info_for_func)

    def is_custom_function(self, cursor: ci.Cursor):
        callee: ci.Cursor | None = cursor.referenced

        if not isinstance(callee, ci.Cursor):
            sys.exit("function reference is not found")

        if callee.kind != ci.CursorKind.FUNCTION_DECL:
            sys.exit("non function cursor was given to \"is_custom_function\"")

        if (file := self.get_cursor_file(callee)) is None or not isinstance(file.name, str):
            sys.exit("file name is not found")

        return file.name in self.c_files

    # typedefの解析
    def parse_typedef(self, cursor: ci.Cursor):
        print(f"{self.get_type_spelling(cursor.underlying_typedef_type)} {self.get_cursor_spelling(cursor)}")

    # 構造体の解析 (メンバの型を取得しておいて、解析に用いる)
    def parse_struct(self, cursor: ci.Cursor):
        print(f"struct {self.get_cursor_spelling(cursor)}")
        self.struct_info[f"struct {self.get_cursor_spelling(cursor)}"] = []
        for cr in cursor.get_children():
            self.check_cursor_error(cr)
            print(f"    {self.get_type_spelling(self.get_cursor_type(cr))} {self.get_cursor_spelling(cr)}")
            # type = self.get_cursor_type(cr)
            # if type.kind in (ci.TypeKind.INCOMPLETEARRAY, ci.TypeKind.VARIABLEARRAY):
            #     sys.exit("our system cannot receive variable array member of a struct variable")
            
            # array_size: list[int] = []
            # if type.kind == ci.TypeKind.CONSTANTARRAY:
            #     while type.kind == ci.TypeKind.CONSTANTARRAY:
            #         array_size.append(type.element_count)
            #         type = type.element_type
            #         if not isinstance(type, ci.Type):
            #             sys.exit("type has to be ci.Type")
            #     print(f"    length = {array_size}")
            #     print(f"    type = {type.kind}")
            # else:
            #     print("    length = 1")
            #     print(f"    type = {type.kind}")

            # self.struct_info[f"struct {self.get_cursor_spelling(cursor)}"].append((self.get_cursor_spelling(cr), array_size))

    # 共用体の解析(フローチャートには含めないが、アイテムには必要なので解析)
    def parse_union(self, cursor):
        print(f"union {self.get_cursor_spelling(cursor)}")
        for cr in cursor.get_children():
            self.check_cursor_error(cr)
            print(f"    {self.get_type_spelling(self.get_cursor_type(cr))} {self.get_cursor_spelling(cr)}")
    
    # 列挙型の解析(フローチャートには含めないが、アイテムには必要なので解析)
    def parse_enum(self, cursor):
        print(f"enum {self.get_cursor_spelling(cursor)}")
        value = 0
        for cr in cursor.get_children():
            self.check_cursor_error(cr)
            if (int_cursor := next(cr.get_children(), None)):
                value = int(self.get_token_spelling(next(int_cursor.get_tokens())))
            print(f"    {self.get_type_spelling(self.get_cursor_type(cr))} {self.get_cursor_spelling(cr)} = {value}")
            value += 1

    # 分岐で新たな部屋情報を登録する
    def create_room_size_estimate(self, nodeID: str | None):
        if self.room_size_estimate:
            # 部屋情報が完成したらroomSize辞書に移す
            self.room_size_info[self.scanning_func][f'"{self.room_size_estimate[0]}"'] = self.room_size_estimate[1]
        
        # gotoのラベルを探っている最中は登録しない
        if nodeID is not None:
            #部屋のサイズの初期値は9 (5*4などの部屋ができる)
            self.room_size_estimate = (nodeID, 9)

    # if文
    # 現在ノードに全ての子ノードをくっつける。出口ノードを作成する
    # 子ノード(現在のノードの条件が真/偽それぞれの場合の遷移先)を引数に関数を再帰する
    # その関数の戻り値は条件先の最後の処理を示すノードとし、この戻り値→出口ノードとなる矢印をつける
    def parse_if_stmt(self, cursor: ci.Cursor, nodeID: str | None, edgeName: str = ""):
        term_nodeIDs = self.parse_if_branch(cursor, nodeID, self.get_cursor_line(cursor), 0, edgeName)
        end_nodeID = self.createNode("", 'circle')
        self.create_room_size_estimate(end_nodeID)

        for term_nodeID in term_nodeIDs:
            self.createEdge(term_nodeID, end_nodeID)

        return end_nodeID

    def parse_if_branch_start(self, cursor: ci.Cursor, parent_nodeID: str, first_line: int, condition_line: int, condition_index: int):
        """if / else の本体（複合文または単一文）を処理する"""
        self.register_execution_info(
            parent_nodeID, 
            create_if_execution_info(
                first_line, 
                condition_line, 
                condition_index
            )
        )

        if cursor.kind == ci.CursorKind.COMPOUND_STMT:
            return self.parse_comp_stmt(cursor, parent_nodeID, "if")
        # 混合文がない = {} で囲まれない単体文
        else:
            return self.parse_stmt(cursor, parent_nodeID)
            
    def parse_if_branch(self, cursor: ci.Cursor, nodeID: str, first_line: int, condition_index: int, edgeName=""):
        # くっつけるノードをどんどん追加して返す。ifしかなくてもfalseのルートにノードを作ってtrue, falseの二つを追加して返す
        children: list[ci.Cursor] = list(cursor.get_children())

        if len(children) < 2:
            sys.exit("number of child cursors of if statement has to be 2 or more")

        # 条件式処理
        cond_cursor = children[0]
        self.check_cursor_error(cond_cursor)

        if self.get_cursor_extent_start(cond_cursor).line != self.get_cursor_extent_end(cond_cursor).line:
            sys.exit("condition expression has to be in one line")

        cond_nodeID = self.get_expr(cond_cursor, shape='diamond', label='if')

        # ifの条件がtext単体でないことを確かめる (単体だとif()の()の行をスキップしてしまう)
        # if文に定数条件を使うことは無い(あまり意味がない)のでこの場合はsys.exit()で除外する
        if len(self.expr_node_info[f'"{cond_nodeID}"']["vars"]) == 0 and len(self.expr_node_info[f'"{cond_nodeID}"']["func"]) == 0:
            sys.exit("static condition cannot be set to if condition")

        self.createEdge(nodeID, cond_nodeID, edgeName)

        # if文の最初の条件文 (else ifやelseの()内の条件文ではなく、ifの()内の条件文) の部分は最初の行となり得るので、set_execution_lineする
        if edgeName != "False":
            self.line_info_dict[self.scanning_func].set_execution_line(self.get_cursor_line(cond_cursor))

        # then節 (条件が真になる時に実行される処理) の分析
        then_cursor = children[1]
        self.check_cursor_error(then_cursor)
        true_nodeID = self.createNode("", 'circle')

        self.createEdge(cond_nodeID, true_nodeID, "True")
        self.create_room_size_estimate(true_nodeID)

        # 後々 cond_nodeID による演算内容を設定する
        then_end_nodeID = self.parse_if_branch_start(
            then_cursor, 
            true_nodeID, 
            first_line,
            self.get_cursor_line(cond_cursor), 
            condition_index,
        )

        # trueの後の処理の終点を作る (後でif構文の終点をまとめる)
        trueEnd_nodeID = self.createNode("", 'terminator')
        end_line = self.get_cursor_extent_end(then_cursor).line

        self.createEdge(then_end_nodeID, trueEnd_nodeID)

        # else節の処理がある場合
        if len(children) > 2:
            else_cursor = children[2]
            self.check_cursor_error(else_cursor)

            if else_cursor.kind == ci.CursorKind.IF_STMT:
                # else if の再帰処理
                # 現在のifがFalseの場合に該当するので、edgeNameは"False"にする
                nodeIDs: list[str] = [
                    trueEnd_nodeID, 
                    *self.parse_if_branch(
                        else_cursor, 
                        cond_nodeID, 
                        first_line, 
                        condition_index+1, 
                        edgeName="False"
                    )
                ]
            else:
                # else
                falseEnd_nodeID = self.createNode("", 'terminator')
                in_else_cursor: list[ci.Cursor] = list(else_cursor.get_children())
                # 「elseが真の時」の処理がある場合
                if len(in_else_cursor):
                    # 後々 cond_nodeID による演算内容を設定する
                    false_nodeID = self.createNode("", 'doublecircle')
                    self.createEdge(cond_nodeID, false_nodeID, "False")
                    self.create_room_size_estimate(false_nodeID)
                    nodeID = self.parse_if_branch_start(
                        else_cursor, 
                        false_nodeID, 
                        first_line,
                        self.get_cursor_line(else_cursor)
                        -1, 
                    )
                    end_line = self.get_cursor_line(in_else_cursor[-1])
                    self.line_info_dict[self.scanning_func].set_execution_line(end_line)
                    self.createEdge(nodeID, falseEnd_nodeID)
                # 「elseが真の時」の処理がない場合
                else:
                    nodeID = cond_nodeID
                    # self.line_info_dict[self.scanning_func].set_execution_line(self.get_cursor_line(else_cursor))
                    # 現在の階層のif条件がFalse, else条件がTrueなのでそれら二つを追加する (parse_if_branch_startには入らないのでここで追加する必要がある)
                    self.register_execution_info(false_nodeID, create_if_execution_info(first_line, self.get_cursor_line(else_cursor), -1))
                    self.createEdge(nodeID, falseEnd_nodeID, "False")
                nodeIDs = [trueEnd_nodeID, falseEnd_nodeID]
        # elseがない場合
        else:
            # elseがなくても終点を作る
            falseEnd_nodeID = self.createNode("", 'terminator')
            self.register_execution_info(falseEnd_nodeID, create_if_execution_info(first_line, 0, -1))
            self.createEdge(cond_nodeID, falseEnd_nodeID, "False")
            nodeIDs = [trueEnd_nodeID, falseEnd_nodeID]
        
        return nodeIDs
    
    #while文
    #子ノード(真の条件先の最初の処理)を現在のノードに付ける
    #子ノードを引数とする関数を呼び出し、真の場合の最後の処理をこの関数の戻り値とする
    #その戻り値を現在ノードに付ける
    #現在のノードは次のノードに付ける
    def parse_while_stmt(self, cursor: ci.Cursor, nodeID, edgeName=""):
        self.createLoopBreakerInfo()
        
        children = list(cursor.get_children())

        self.line_info_dict[self.scanning_func].set_loop_start_and_goal(self.get_cursor_extent_start(cursor).line, self.get_cursor_extent_end(cursor).line)

        cond_cursor = children[0]
        self.check_cursor_error(cond_cursor)

        if self.get_cursor_extent_start(cond_cursor).line != self.get_cursor_extent_end(cond_cursor).line:
            sys.exit("condition expression has to be in one line")

        cond_nodeID = self.get_expr(cond_cursor, shape='pentagon', label='while')
        self.create_room_size_estimate(cond_nodeID)

        self.createEdge(nodeID, cond_nodeID, edgeName)

        true_nodeID = self.createNode("", 'circle')

        self.line_info_dict[self.scanning_func].set_execution_line(self.get_cursor_line(cond_cursor))
        
        # 次のノードがwhileのtrueかを確認するためにエッジにラベルをつけておく(falseも同じ)
        self.createEdge(cond_nodeID, true_nodeID, "true")
        self.create_room_size_estimate(true_nodeID)

        then_end_nodeID = true_nodeID
        content_cursor = children[1]
        self.check_cursor_error(content_cursor)
        self.register_execution_info(true_nodeID, create_while_execution_info(self.get_cursor_line(cond_cursor), True))

        if content_cursor.kind == ci.CursorKind.COMPOUND_STMT:
            then_end_nodeID = self.parse_comp_stmt(content_cursor, true_nodeID, "while")
        else:
            then_end_nodeID = self.parse_stmt(content_cursor, true_nodeID)

        # ループを閉じる処理
        loop_back_nodeID = self.createNode(str(self.get_cursor_line(cond_cursor)), 'parallelogram')

        self.createEdge(then_end_nodeID, loop_back_nodeID)
        self.createEdge(loop_back_nodeID, cond_nodeID)

        # 条件False時の処理（脱出
        end_nodeID = self.createNode("", 'doublecircle')
        self.createEdge(cond_nodeID, end_nodeID, "false")
        self.create_room_size_estimate(end_nodeID)

        self.register_execution_info(end_nodeID, create_while_execution_info(self.get_cursor_line(cond_cursor), False))

        self.createEdgeForLoop(end_nodeID, loop_back_nodeID)

        self.downSwitchBreakerLevel()
        return end_nodeID

    #do-while文
    #まずは最初の処理を示す子ノードと現在ノードを接続する
    #Doノードの子ノードはCOMPOUNDと条件部しかなく、条件部は2つ目に読まれる
    #そこで読み込まれたノードを先頭ノードと次ノードをくっつける
    def parse_do_stmt(self, cursor: ci.Cursor, nodeID, edgeName=""):
        self.createLoopBreakerInfo()

        init_nodeID = self.createNode(f"{self.get_cursor_line(cursor)}", 'invtrapezium')
        self.createEdge(nodeID, init_nodeID, edgeName)

        true_nodeID = self.createNode("", 'circle')
        self.createEdge(init_nodeID, true_nodeID)

        # ここで部屋情報を作る
        self.create_room_size_estimate(true_nodeID)
        
        false_nodeID = self.createNode("", 'doublecircle')

        children: list[ci.Cursor] = list(cr for cr in cursor.get_children() if self.check_cursor_error(cr))

        if len(children) != 2:
            sys.exit("number of child cursors of do-while statement has to be 2")
        if children[0].kind != ci.CursorKind.COMPOUND_STMT:
            sys.exit("the first child cursor of do-while statement has to be compound statement")

        comp_stmt_cursor, cond_cursor = children
        if self.get_cursor_extent_start(cond_cursor).line != self.get_cursor_extent_end(cond_cursor).line:
            sys.exit("condition expression has to be in one line")

        self.line_info_dict[self.scanning_func].set_execution_line(self.get_cursor_line(comp_stmt_cursor))
        nodeID = self.parse_comp_stmt(comp_stmt_cursor, true_nodeID, edgeName="do_while")

        # # 中身が途中で終わっているなら
        # if nodeID is None:
        #     return None
        
        cond_nodeID = self.get_expr(cond_cursor, shape='diamond', label='do')
        self.line_info_dict[self.scanning_func].set_loop_start_and_goal(self.get_cursor_line(cond_cursor), self.get_cursor_extent_start(cursor).line)

        # 今まではdo_whileだけ条件分岐の部屋を作っていなかったが、continueにも対応させるために作ることにする
        self.create_room_size_estimate(cond_nodeID)
        
        self.line_info_dict[self.scanning_func].set_execution_line(self.get_cursor_line(cond_cursor))
        self.createEdgeForLoop(false_nodeID, cond_nodeID)
        self.createEdge(nodeID, cond_nodeID)
        self.createEdge(cond_nodeID, true_nodeID, "True")
        self.createEdge(cond_nodeID, false_nodeID, "False")

        self.register_execution_info(true_nodeID, create_do_while_execution_info(self.get_cursor_line(cond_cursor), True))
        self.register_execution_info(false_nodeID, create_do_while_execution_info(self.get_cursor_line(cond_cursor), False))

        # ここでdo_whileを抜けた後の部屋情報を作る
        self.create_room_size_estimate(false_nodeID)

        self.downSwitchBreakerLevel()

        return false_nodeID

    #for文
    #まずは式1に対するノードを作成(for(式1; 式2; 式3))
    #あとは、ほぼWhileと同じ。式2の子ノード(真である場合の遷移先)の最後の処理が式3であることに注意
    def parse_for_stmt(self, cursor: ci.Cursor, nodeID: str, edgeName: str = ""):
        # for(INIT; COND; CHANGE)
        # cursor.get_childrenの最後の要素は必ず処理部の最初のカーソルであるから、それ以外のカーソルが式1~式3の候補となる。
        self.createLoopBreakerInfo()

        init_nodeID = None
        cond_nodeID = None
        change_nodeID = None
        change_expr_cursor = None
        end_nodeID = self.createNode("", 'doublecircle')

        children: list[ci.Cursor] = list(cursor.get_children())
        *expr_cursors, exec_cursor = children
        semi_offset = [token.location.offset for token in list(cursor.get_tokens()) if self.get_token_spelling(token) == ';'][:2]

        self.line_info_dict[self.scanning_func].set_loop_start_and_goal(self.get_cursor_extent_start(cursor).line, self.get_cursor_extent_end(cursor).line)
        for cr in expr_cursors:
            self.check_cursor_error(cr)
            if self.get_cursor_offset(cr) < semi_offset[0]:
                # もしかしたら変数の値の変更が2つ以上ある場合に対応できていない可能性がある。もしそうなら後で修正する
                if cr.kind == ci.CursorKind.DECL_STMT:
                    sys.exit("this game does not allow that variable initializers in for statement initializer now")
                    var_cr_list = list(cr.get_children())
                    init_nodeID = self.createNode(str(self.get_cursor_line(cursor)), 'invhouse')
                    var_nodeID = init_nodeID
                    for var_cr in var_cr_list:
                        self.check_cursor_error(var_cr)
                        var_nodeID = self.parse_var_decl(var_cr, var_nodeID, "")
                else:
                    init_nodeID = self.get_expr(cr, shape='invhouse')
                    self.register_execution_info(init_nodeID, create_for_initializer_execution_info(self.get_cursor_line(cursor)))
                self.create_room_size_estimate(init_nodeID)
                self.createEdge(nodeID, init_nodeID, edgeName)
                edgeName = ""
            elif semi_offset[0] < self.get_cursor_offset(cr) < semi_offset[1]:
                cond_nodeID = self.get_expr(cr, shape='pentagon', label='for')
                self.create_room_size_estimate(cond_nodeID)
                if init_nodeID:
                    self.createEdge(init_nodeID, cond_nodeID)
                else:
                    self.createEdge(nodeID, cond_nodeID, edgeName)
                    edgeName = ""
            elif semi_offset[1] < self.get_cursor_offset(cr):
                change_expr_cursor = cr
            else:
                sys.exit("error in analyzing contents inside parens of for statement")
            
            if self.get_cursor_line(cursor) != self.get_cursor_extent_end(cr).line:
                sys.exit("for statement initializer, condition, change expression have to be in one line")

        if cond_nodeID is None:
            cond_nodeID = self.createNode("for", 'pentagon')
            self.create_room_size_estimate(cond_nodeID)
            if init_nodeID:
                self.createEdge(init_nodeID, cond_nodeID)
            else:
                self.createEdge(nodeID, cond_nodeID, edgeName)

            # ここでexpr_node_infoを設定しないとgenerate_bit_map.pyにてfor文計算式情報を作れなくなる可能性があるので作る
            self.expr_node_info[f'"{cond_nodeID}"'] = ExprNodeInfo(
                vars = set(),
                funcs = [],
                comments = [],
                line = self.get_cursor_line(cursor)
            )

        self.line_info_dict[self.scanning_func].set_execution_line(self.get_cursor_line(cursor))
        self.check_cursor_error(exec_cursor)

        true_nodeID = self.createNode("", 'circle')
        self.createEdge(cond_nodeID, true_nodeID, "True")

        #ここで部屋情報を作る
        self.create_room_size_estimate(true_nodeID)

        self.register_execution_info(true_nodeID, create_for_execution_info(self.get_cursor_line(cursor), True))

        if exec_cursor.kind == ci.CursorKind.COMPOUND_STMT:
            nodeID = self.parse_comp_stmt(exec_cursor, true_nodeID, "for_w_change" if change_expr_cursor else "for_wo_change")
        else:
            nodeID = self.parse_stmt(exec_cursor, true_nodeID)

        #changeノードがある条件
        if (len(self.loopBreaker_list[-1]["continue"]) or nodeID) and change_expr_cursor:
            change_nodeID = self.get_expr(change_expr_cursor, shape='parallelogram', label=str(self.get_cursor_line(cursor)))
            # 更新式に関数がある場合は処理が複雑になるので今は対応させない
            if len(self.expr_node_info[f'"{change_nodeID}"']["funcs"]):
                sys.exit("functions are not allowed in a change expression of a for statement")
            self.register_execution_info(change_nodeID, create_for_change_execution_info(self.get_cursor_line(cursor)))
        else:
            change_nodeID = self.createNode(str(self.get_cursor_line(cursor)), shape='parallelogram')

        self.createEdge(nodeID, change_nodeID)
        self.createEdge(change_nodeID, cond_nodeID)
        self.createEdgeForLoop(end_nodeID, change_nodeID)
        
        self.createEdge(cond_nodeID, end_nodeID, "False")
        #ここでforを抜けた後の部屋情報を作る
        self.create_room_size_estimate(end_nodeID)

        self.register_execution_info(end_nodeID, create_for_execution_info(self.get_cursor_line(cursor), False))
        
        self.downSwitchBreakerLevel()
        return end_nodeID

    # switch文
    # caseノード(invtriangle型)は、次に遷移する行番を取得
    # これとエッジのラベルを組み合わせてワープのfromToを形成する
    # endノードについても、エッジとノードのラベルでfromToを形成する
    def parse_switch_stmt(self, cursor: ci.Cursor, nodeID: str, edgeName=""):
        #caseはbreakだけ適応させる
        #levelが0ならbreakノードを追加する。levelは繰り返し文が入ると1上がる。
        #それ以外ならloopBreaker_listに追加する。
        def createSwitchBreakerInfo():
            self.break_in_switch_list.append({"level": 0, "break":[]})

        #switchのcaseのbreakノードを追加する。
        def createSwitchBreakerEdge(end_nodeID: str):
            if len(self.break_in_switch_list) == 0:
                sys.exit("length of break_in_switch_list has to be 1 or more")
            break_in_switch = self.break_in_switch_list.pop(-1)
            break_pos_list = break_in_switch["break"]
            for breaker_pos in break_pos_list:
                self.createEdge(breaker_pos["nodeID"], end_nodeID)
                self.register_execution_info(breaker_pos["nodeID"], create_control_flow_info("break", breaker_pos["line"]))

        children: list[ci.Cursor] = [cr for cr in cursor.get_children() if self.check_cursor_error(cr)]

        if len(children) != 2:
            sys.exit("number of child cursors of switch statement has to be 2")
        
        cond_cursor, comp_exec_cursor = children

        if self.get_cursor_extent_start(cond_cursor).line != self.get_cursor_extent_end(cond_cursor).line:
            sys.exit("condition expression has to be in one line")

        if self.room_size_estimate is None:
            sys.exit("room size estimate is not found")

        switch_room_size_estimate = self.room_size_estimate
        self.room_size_estimate = None

        #switchの構造はswitch(A)のようにAは必ず必要
        cond_nodeID = self.get_expr(cond_cursor, shape='diamond', label='switch')
        self.createEdge(nodeID, cond_nodeID, edgeName)

        createSwitchBreakerInfo()

        end_nodeID = self.createNode(f"end", 'invtriangle')

        # defaultラベルがある場合はTrueになる (ない場合に条件ノードからendノードに繋げるためにこのフラグを用いる)
        has_default = False

        #switch(A){ B }の場合
        if comp_exec_cursor.kind == ci.CursorKind.COMPOUND_STMT:
            self.line_info_dict[self.scanning_func].set_execution_line(self.get_cursor_line(comp_exec_cursor))
            self.line_info_dict[self.scanning_func].set_execution_line(self.get_cursor_extent_end(comp_exec_cursor).line)

            comp_stmt_cursor_list: list[ci.Cursor] = list(comp_exec_cursor.get_children())

            cursor_list_by_case: list[tuple[list[tuple[ci.Cursor, ci.Cursor | None]], list[ci.Cursor]]] = []

            while len(comp_stmt_cursor_list):
                case_cursor_list: list[tuple[ci.Cursor, ci.Cursor | None]] = []

                cr = comp_stmt_cursor_list.pop(0)
                self.check_cursor_error(cr)

                while cr.kind in (ci.CursorKind.CASE_STMT, ci.CursorKind.DEFAULT_STMT):
                    children: list[ci.Cursor] = [case_cr for case_cr in cr.get_children() if self.check_cursor_error(case_cr)]
                    if cr.kind == ci.CursorKind.CASE_STMT:
                        if len(children) != 2:
                            sys.exit("number of child cursors of case cursor has to be 2")
                        case_value_cursor, next_cr = children
                    else: # ci.CursorKind.DEFAULT_STMT
                        if len(children) != 1:
                            sys.exit("number of child cursors of default cursor has to be 1")
                        if has_default:
                            sys.exit("default label cannot be overlapped")
                        next_cr = children[0]
                        case_value_cursor = None
                        has_default = True
                        
                    case_cursor_list.append((cr, case_value_cursor))
                    cr = next_cr

                comp_stmt_cursor_list.insert(0, cr)
                stmt_cursor_list_in_case: list[ci.Cursor] = []

                ''' comp_stmt_cursor_listの中から次のcase, defaultラベルを見つける
                そのラベルが次の段落の開始ラベルになる
                例: 
                case 1:
                    comp_stmt A
                    stmt B
                case 2:
                case 3:
                の場合、comp_stmt_cursor_listの中には (先程のinsertで追加した)comp_stmt A, stmt B, case 2, case 3を意味するカーソル (最後のcaseまたはdefaultカーソルまで) が含まれている
                このリストを辿っていって、次の段落の開始ラベル、すなわちcase 2を発見した時、stmt_cursorへの情報登録を止める
                '''
                while len(comp_stmt_cursor_list):
                    if comp_stmt_cursor_list[0].kind in (ci.CursorKind.CASE_STMT, ci.CursorKind.DEFAULT_STMT):
                        break

                    stmt_cursor_list_in_case.append(comp_stmt_cursor_list.pop(0))

                cursor_list_by_case.append((case_cursor_list, stmt_cursor_list_in_case))

            for case_index, (case_cursor_list, stmt_cursor_list_in_case) in enumerate(cursor_list_by_case):
                # まずはcaseノードをくっつけていく
                prev_nodeID = cond_nodeID

                case_nodeID = None

                for case_cursor, case_value_cursor in case_cursor_list:
                    if case_value_cursor and self.get_cursor_line(case_cursor) != self.get_cursor_extent_end(case_value_cursor).line:
                        sys.exit("case expression has to be in one line")

                    if case_value_cursor:
                        case_nodeID = self.get_expr(case_value_cursor, shape='invtriangle', label='case')
                    else:
                        case_nodeID = self.createNode(f'default,{self.get_cursor_line(case_cursor)}', shape='invtriangle')
                    
                    self.createEdge(prev_nodeID, case_nodeID)

                    prev_nodeID = case_nodeID

                if case_nodeID is None:
                    sys.exit("case cursor is not found")

                # breakなしで他のcaseに入る場合 (case_indexが0でない、かつnodeIDがNoneでない場合)
                if case_index and nodeID:
                    self.createEdge(nodeID, case_nodeID)

                # switchの元の部屋のサイズを+1する
                switch_room_size_estimate = (switch_room_size_estimate[0], switch_room_size_estimate[1] + 1)

                # ここで一つのcaseの部屋情報を作る
                self.create_room_size_estimate(case_nodeID)

                self.register_execution_info(case_nodeID, create_switch_case_executioin_info(self.get_cursor_line(cursor), case_index))
                
                nodeID = case_nodeID

                for stmt_cursor in stmt_cursor_list_in_case:
                    nodeID = self.parse_comp_stmt(stmt_cursor, nodeID) if stmt_cursor.kind == ci.CursorKind.COMPOUND_STMT else self.parse_stmt(stmt_cursor, nodeID)
        # switch(A) Bの時、Bが case C: D なら A == C でDが行われる。
        # しかし、Bが case C:でないなら D は無視される。Dは複数行でも良い。
        elif comp_exec_cursor.kind in (ci.CursorKind.CASE_STMT, ci.CursorKind.DEFAULT_STMT):
            children: list[ci.Cursor] = [cr for cr in comp_exec_cursor.get_children() if self.check_cursor_error(cr)]
            if comp_exec_cursor.kind == ci.CursorKind.CASE_STMT:
                if len(children) != 2:
                    sys.exit("number of child cursors of case cursor has to be 2")
                case_value_cursor, stmt_cursor = children
                if self.get_cursor_extent_start(comp_exec_cursor).line != self.get_cursor_extent_end(case_value_cursor).line:
                    sys.exit("case expression has to be in one line")
                case_nodeID = self.get_expr(case_value_cursor, shape='invtriangle')
            else: # ci.CursorKind.DEFAULT_STMT
                if len(children) != 1:
                    sys.exit("number of child cursors of case cursor has to be 2")
                stmt_cursor = children[0]
                case_value_cursor = None
                case_nodeID = self.createNode('default', shape='invtriangle')
                has_default = True

            self.createEdge(cond_nodeID, case_nodeID)
            createSwitchBreakerInfo()

            # switchの元の部屋のサイズを+1する
            switch_room_size_estimate = (switch_room_size_estimate[0], switch_room_size_estimate[1] + 1)
            self.create_room_size_estimate(case_nodeID)

            self.register_execution_info(case_nodeID, create_switch_case_executioin_info(self.get_cursor_line(cr), 0))

            nodeID = self.parse_stmt(stmt_cursor, case_nodeID)
             
            self.line_info_dict[self.scanning_func].set_execution_line(self.get_cursor_line(stmt_cursor))
            self.createEdge(nodeID, end_nodeID)
        else:
            sys.exit("impossible ast of switch statement is found")

        self.createEdge(nodeID, end_nodeID)

        if not has_default:
            self.createEdge(cond_nodeID, end_nodeID)
            self.register_execution_info(cond_nodeID, create_switch_case_executioin_info(self.get_cursor_line(cursor), -1))

        createSwitchBreakerEdge(end_nodeID)
        #ここでswitchを抜けた後の部屋情報を作る
        self.create_room_size_estimate(end_nodeID)

        self.room_size_info[self.scanning_func][f'"{switch_room_size_estimate[0]}"'] = switch_room_size_estimate[1]
        return end_nodeID 

    # ループ処理のノードをくっつけていく (switch文はbreakしか許されないので、switchはここに含めない)
    def createEdgeForLoop(self, breakTo_nodeID: str, continueTo_nodeID: str):
        if len(self.loopBreaker_list) == 0:
            sys.exit("length of loopBreaker_list has to be 1 or more")
        
        loopBreaker = self.loopBreaker_list.pop(-1)
        break_list = loopBreaker["break"]
        continue_list  = loopBreaker["continue"]

        for breaker_pos in break_list:
            self.createEdge(breaker_pos["nodeID"], breakTo_nodeID)
            self.register_execution_info(breaker_pos["nodeID"], create_control_flow_info("break", breaker_pos["line"]))
            self.line_info_dict[self.scanning_func].set_execution_line(breaker_pos["line"])
        for breaker_pos in continue_list:
            self.createEdge(breaker_pos["nodeID"], continueTo_nodeID)
            self.register_execution_info(breaker_pos["nodeID"], create_control_flow_info("continue", breaker_pos["line"]))
            self.line_info_dict[self.scanning_func].set_execution_line(breaker_pos["line"])
