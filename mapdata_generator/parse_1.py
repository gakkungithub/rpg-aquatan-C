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

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = ROOT_DIR + '/mapdata_for_test'

def parseIndex(c_files):
    index = ci.Index.create()
    translation_units = {}

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
        translation_units[c_file] = tu

    return translation_units

class FuncInfo:
    def __init__(self, nodeID: str):
        self.start_nodeID: str = f'"{nodeID}"'
        self.refs: set[str] = set()
        self.start: int = 0

    def setRef(self, ref: str):
        self.refs.add(ref)

    def setStart(self, line: int, not_to_set: bool = False):
        if self.start or not_to_set:
            return
        self.start = line

class LineInfo:
    def __init__(self):
        self.lines = set()
        self.loops = {}
        self.returns: dict[int, list[str | dict[str, any]]] = {}
        self.void_returns = []
        self.start = 0

    def setLine(self, line: int):
        self.lines.add(line)

    def setLoop(self, key: int, value: int):
        self.loops[key] = value

    def setReturn(self, line: int, funcs: list[str | dict[str, any]]):
        self.returns[line] = funcs

    def setVoidReturn(self, line: int):
        self.void_returns.append(line)

    def setStart(self, line: int, not_to_set: bool = False):
        if self.start or not_to_set:
            return
        self.start = line

# 計算式の情報(var_references, func_references, expr_descriptions)を格納する
class ExprInfo:
    def __init__(self):
        self.var_references: set[tuple[str, int]] = set()
        self.func_references: list[str | dict[str, any]] = []
        self.expr_descriptions: list[dict[str, any]] = []
        self.id = 0
        # 自作関数の依存関係を適切に描画するためにカウントする必要がある
        self.custom_func_count = 0
    
    def add_var_reference(self, var_path: str, line: int):
        self.var_references.add((var_path, line))

    # 標準ライブラリ関数は辞書型
    def append_standard_func_reference(self, func_name: str, **kwargs):
        self.func_references.append({"name": func_name, **kwargs})

    # 自作関数は文字列で登録する
    def append_custom_func_reference(self, func_name: str):
        self.func_references.append(func_name)

    def append_expr_description(self, description: list, expr: list[dict[str, any]]):
        '''
        descriptionは計算式の説明の文字列
        exprは計算式の文字列を構成する辞書
        この辞書のキーは、"text"、"expr_id"、"reference"、"func"-"args"がある
        "text"は埋め込み文字列、"expr_id"はlldbによる動的解析中に値が決まる途中式のid、"reference"は変数の参照である
        "func"-"args"は関数である("func"は関数名、"args"は引数の情報も必要である)
        '''

        self.id += 1
        self.expr_descriptions.append({"id": self.id, "description": description, "expr": expr})
        return {"expr_id": self.id}
    
    def get_sizeof_operator_description(self, type_name: str, en: bool) -> dict[str, any]:
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

        size = self.sizeof_operator_size.get(base_type, {}).get(frozenset(size_tokens), None)
        if size:
            return [{"text": f"get size of {type_name} ({size})" if en else f"{type_name}のサイズ({size})を取得します"}]
        else:
            return [{"text": f"get size of {type_name}" if en else f"{type_name}のサイズを取得します"}]

    unary_front_operator_description = {
        '++': lambda expr: [expr, {"text": "を１増やしてから"}, expr, {"text": "の値を使います"}],
        '--': lambda expr: [expr, {"text": "を１減らしてから"}, expr, {"text": "の値を使います"}],
        '+': lambda expr: [expr, {"text": "の元の値を使います"}],
        '-': lambda expr: [expr, {"text": "の符号を反転した値を使います"}],
        '!': lambda expr: [expr, {"text": "が真なら偽、偽なら真です"}],
        '~': lambda expr: [expr, {"text": "を２進数で表し、各ビットを反転します"}],
        '&': lambda expr: [expr, {"text": "を格納しているアドレスを取得します"}],
        '*': lambda expr: [{"text": "アドレス"}, expr, {"text": "を格納しているアドレスを取得します"}],
    }

    unary_front_operator_description_en = {
        '++': lambda expr: [{"text": "add 1 to"}, expr, {"text": ", then use value of"}, expr],
        '--': lambda expr: [{"text": "subtract 1 from"}, expr, {"text": ", then use value of"}, expr],
        '+': lambda expr: [{"text": "use value of"}, expr],
        '-': lambda expr: [{"text": "use negative value of"}, expr],
        '!': lambda expr: [{"false if"}, expr, {"text": "is correct, otherwise true"}],
        '~': lambda expr: [{"text": "flip all the bits in binary of"}, expr],
        '&': lambda expr: [{"text": "get address of variable"}, expr],
        '*': lambda expr: [{"text": "scan value of addres"}, expr],
    }

    unary_back_operator_description = {
        '++': lambda expr: [expr, {"text": "の値を使います。その後、"}, expr, {"text": "を１増やします"}],
        '--': lambda expr: [expr, {"text": "の値を使います。その後、"}, expr, {"text": "を１減らします"}],
    }

    unary_back_operator_description_en = {
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
        '+': lambda left, right: [left, {"text": "と"}, *right, {"text": "の値を足します"}],
        '-': lambda left, right: [left, {"text": "から"}, *right, {"text": "を引きます"}],
        '*': lambda left, right: [left, {"text": "と"}, *right, {"text": "を掛けます"}],
        '/': lambda left, right: [left, {"text": "を"}, *right, {"text": "で割ります"}],
        '%': lambda left, right: [left, {"text": "を"}, *right, {"text": "で割った余りを求めます"}],
        '=': lambda left, right: [left, {"text": "に"}, *right, {"text": "を代入します"}],
        '==': lambda left, right: [left, {"text": "と"}, *right, {"text": "が等しいかどうかを比較します"}],
        '!=': lambda left, right: [left, {"text": "と"}, *right, {"text": "が異なるかを比較します"}],
        '<': lambda left, right: [left, {"text": "が"}, *right, {"text": "より小さいかを調べます"}],
        '<=': lambda left, right: [left, {"text": "が"}, *right, {"text": "以下かを調べます"}],
        '>': lambda left, right: [left, {"text": "が"}, *right, {"text": "より大きいかを調べます"}],
        '>=': lambda left, right: [left, {"text": "が"}, *right, {"text": "以上かを調べます"}],
        '&&': lambda left, right: [left, {"text": "と"}, *right, {"text": "の両方が真かを調べます"}],
        '||': lambda left, right: [left, {"text": "または"}, *right, {"text": "のいずれかが真かを調べます"}],
        '&': lambda left, right: [left, {"text": "と"}, *right, {"text": "を 2進数で表し、それぞれのビットが両方とも 1 のときに 1 になります"}],
        '|': lambda left, right: [left, {"text": "と"}, *right, {"text": "を 2進数で表し、どちらかのビットが 1 であれば 1 になります"}],
        '^': lambda left, right: [left, {"text": "と"}, *right, {"text": "を 2進数で表し、ビットが異なるときに１になります"}],
        '<<': lambda left, right: [left, {"text": "を左に"}, *right, {"text": "ビット分シフトします。2進数で見ると桁が左にずれて、2の"}, *right, {"text": "乗倍になります"}],
        '>>': lambda left, right: [left, {"text": "を右に"}, *right, {"text": "ビット分シフトします。2進数で見ると桁が右にずれて、2の"}, *right, {"text": "乗で割ったのと同じになります"}],
    }
    
    binary_operator_descriptions_en = {
        '+': lambda left, right: [{"text": "add"}, left, {"text": "and"}, *right],
        '-': lambda left, right: [{"text": "subtract"}, *right, {"text": "from"}, left],
        '*': lambda left, right: [{"text": "multiply"}, left, {"text": "by"}, *right],
        '/': lambda left, right: [{"text": "divide"}, left, {"text": "by"}, *right],
        '+': lambda left, right: [{"text": "get remainder dividing"}, left, {"text": "by"}, *right],
        '=': lambda left, right: [{"text": "assign"}, *right, {"text": "to"}, left],
        '==': lambda left, right: [{"text": "true if"}, left, {"text": "and"}, *right, {"text": "are same, otherwise false"}],
        '!=': lambda left, right: [{"text": "true if"}, left, {"text": "and"}, *right, {"text": "are different, otherwise false"}],
        '<': lambda left, right: [{"text": "true if"}, left, {"text": "is smaller than"}, *right, {"text": ", otherwise false"}],
        '<=': lambda left, right: [{"text": "true if"}, left, {"text": "is smaller or equal to"}, *right, {"text": ", otherwise false"}],
        '>': lambda left, right: [{"text": "true if"}, left, {"text": "is bigger than"}, *right, {"text": ", otherwise false"}],
        '>=': lambda left, right: [{"text": "true if"}, left, {"text": "is bigger or equal to"}, *right, {"text": ", otherwise false"}],
        '&&': lambda left, right: [{"text": "true if both"}, left, {"text": "and"}, *right, {"text": "are correct, otherwise false"}],
        '||': lambda left, right: [{"text": "true if either"}, left, {"text": "or"}, *right, {"text": "are correct, otherwise false"}],
        '&': lambda left, right: [{"text": "compare each bit of"}, left, {"text": "and"}, *right, {"text": ", then produce a number where each bit is 1 if both bits are 1, otherwise 0"}],
        '|': lambda left, right: [{"text": "compare each bit of"}, left, {"text": "and"}, *right, {"text": ", then produce a number where each bit is 1 if either bits are 1, otherwise 0"}],
        '^': lambda left, right: [{"text": "compare each bit of"}, left, {"text": "and"}, *right, {"text": ", then produce a number where each bit is 1 if both bits are different, otherwise 0"}],
        '<<': lambda left, right: [{"text": "shift"}, left, {"text": "left by"}, *right, {"text": "bits. The value becomes"}, left, {"text": "multiplied by 2 to the power of"}, *right],
        '>>': lambda left, right: [{"text": "shift"}, left, {"text": "right by"}, *right, {"text": "bits. The value becomes"}, left, {"text": "divided by 2 to the power of"}, *right],
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

class ASTtoFlowChart:
    def __init__(self, is_english):
        self.dot = Digraph(comment='Control Flow')
        self.diag_list = []
        self.nextLines: list[tuple[int, bool]] = []
        self.scanning_func = None
        self.gvar_candidate_crs = {}
        self.gvar_info = []
        self.func_info_dict: dict[str, FuncInfo] = {}
        self.loopBreaker_list: dict[str, list[str]] = []
        self.switchBreaker_list = []
        self.findingLabel = None
        self.gotoLabel_list = {}
        self.gotoRoom_list = {}
        self.roomSizeEstimate = None
        self.roomSize_info = {}
        self.varNode_info: dict[str, dict] = {}
        self.expr_node_info: dict[str, tuple[dict[str, any], set[tuple[str, int]], list[str | dict[str, any]], list[dict[str, any]], int]] = {}
        self.condition_move : dict[str, tuple[str, list[int | dict[str, any]]]] = {}
        self.line_info_dict: dict[str, LineInfo] = {}
        self.macro_pos = {}

        # 英語モードにする
        self.is_english = is_english
    
    def createNode(self, nodeLabel, shape='rect'):
        nodeID = str(uuid.uuid4())
        self.dot.node(nodeID, nodeLabel, shape=shape)
        return nodeID

    def createEdge(self, prevNodeID, crntNodeID, edgeName=""):
        if prevNodeID and crntNodeID:
            self.dot.edge(prevNodeID, crntNodeID, label=edgeName)

    def createErrorInfo(self, diagnostics):
        for diag in diagnostics:
            self.diag_list.append(diag)
            print(f"{diag.spelling}, {diag.location.offset}")
            if any(x in diag.spelling for x in ["expected '}'", "expected ';'"]):
                sys.exit(-1)

    def check_cursor_error(self, cursor):
        # カーソルがファイルに属していないならスキップ
        if cursor.location.file is None:
            return True

        for diag in self.diag_list:
            # 同じファイルかつ、カーソルの位置が診断より後ろ（または近接）
            if (diag.location.file is not None and
                cursor.location.file.name == diag.location.file.name and
                cursor.location.offset >= diag.location.offset - 1): 
                print(f"{diag.spelling}")
                sys.exit(-2)
        return True

    def write_ast(self, tu: ci.TranslationUnit, programname):
        self.createErrorInfo(tu.diagnostics)
        for cr in tu.cursor.get_children():
            if cr.kind == ci.CursorKind.MACRO_INSTANTIATION:
                loc = cr.location
                self.macro_pos[(loc.file.name, loc.line, loc.column)] = cr.spelling
        for cursor in tu.cursor.get_children():
            self.check_cursor_error(cursor)
            if cursor.kind == ci.CursorKind.FUNCTION_DECL:
                self.parse_func(cursor)
                # gotoのLabelを登録する
                self.gotoRoom_list[self.scanning_func] = self.gotoLabel_list
                self.gotoLabel_list = {}
            elif cursor.kind == ci.CursorKind.VAR_DECL:
                self.gvar_candidate_crs[cursor.spelling] = cursor
            elif cursor.kind == ci.CursorKind.TYPEDEF_DECL:
                self.parse_typedef(cursor)
            elif cursor.kind == ci.CursorKind.STRUCT_DECL:
                self.parse_struct(cursor)
            elif cursor.kind == ci.CursorKind.UNION_DECL:
                self.parse_union(cursor)
            elif cursor.kind == ci.CursorKind.ENUM_DECL:
                self.parse_enum(cursor)
        output_dir = f'{DATA_DIR}/{programname}'
        os.makedirs(output_dir, exist_ok=True)
        
        gv_dot_path = f'{output_dir}/{programname}'
        self.dot.render(gv_dot_path, format='dot')
        if os.path.exists(gv_dot_path):
            os.remove(gv_dot_path)

        gv_png_path = f'{output_dir}/fc_{programname}'
        self.dot.render(gv_png_path, format='png')
        if os.path.exists(gv_png_path):
            os.remove(gv_png_path)
            
    #関数の宣言or定義
    def parse_func(self, cursor: ci.Cursor):
        #引数あり/なし→COMPなし = 関数宣言, 引数あり/なし→COMPあり = 関数定義
        #引数とCOMPは同じ階層にある

        #現在のカーソルからこの関数の戻り値と引数の型を取得するかどうかは後で考える
        arg_list: list[tuple[str, ci.Type, int]] = []
        #ノードがなければreturnのノードはつけないようにするため、Noneを設定しておく

        for cr in cursor.get_children():
            self.check_cursor_error(cr)
            if cr.kind == ci.CursorKind.PARM_DECL:
                arg_list.append((cr.spelling, cr.type, cr.location.line))
            elif cr.kind == ci.CursorKind.COMPOUND_STMT:
                func_name = cursor.spelling
                #関数名を最初のノードの名前とする
                nodeID = self.createNode(func_name, 'ellipse')
                #関数の情報を取得し、ビットマップ描画時に取捨選択する
                self.scanning_func = func_name

                self.func_info_dict[func_name] = FuncInfo(nodeID)
                self.line_info_dict[func_name] = LineInfo()

                #関数の最初の部屋情報を作る
                self.roomSize_info[self.scanning_func] = {}
                self.createRoomSizeEstimate(nodeID)
                #引数のノードを作る
                for arg in arg_list:
                    argname, argtype, argline = arg
                    argNodeID = self.createNode(f"{argname},{argline}", 'cylinder')
                    self.varNode_info[f'"{argNodeID}"'] = self.get_var_type(argtype)
                    self.createEdge(nodeID, argNodeID)
                    nodeID = argNodeID
                nodeID = self.parse_comp_stmt(cr, nodeID)
                self.createRoomSizeEstimate(None)
                # void型関数
                if nodeID:
                    # 最初行番を変更
                    self.line_info_dict[self.scanning_func].setStart(cr.extent.end.line)
                    self.func_info_dict[self.scanning_func].setStart(cr.extent.end.line)
                    self.line_info_dict[self.scanning_func].setLine(cr.extent.end.line)
                    self.line_info_dict[self.scanning_func].setVoidReturn(cr.extent.end.line)
                    returnNodeID = self.createNode(str(cr.extent.end.line), 'lpromoter')
                    self.createEdge(nodeID, returnNodeID)

    #関数内や条件文内の処理
    def parse_comp_stmt(self, cursor, nodeID, edgeName=""):
        # 次の処理の行数を取得するためにカーソルをlistとして取得する
        type_parent = edgeName
        # if type_parent in []:
        cursor_stmt_list: list[ci.Cursor] = list(cursor.get_children())
        for i, cr in enumerate(cursor_stmt_list):
            if (next_line := self.get_next_line_in_comp(cursor_stmt_list[i+1:])):
                self.nextLines.append((next_line, True))
            else:
                if type_parent == "if":
                    self.nextLines.append((cursor.extent.end.line, True))
                    edgeName = ""
                elif type_parent == "while":
                    self.nextLines.append((cursor.location.line, True))
                    edgeName = ""
                elif type_parent == "do_while":
                    self.nextLines.append((cursor.extent.end.line, True))
                    edgeName = ""
                elif type_parent == "for_w_change":
                    self.nextLines.append((cursor.extent.end.line, True))
                    edgeName = ""
                elif type_parent == "for_wo_change":
                    self.nextLines.append((cursor.location.line, True))
                    edgeName = ""
                else:
                    self.nextLines.append((cursor.extent.end.line, False))
            nextNodeID = self.parse_stmt(cr, nodeID, edgeName)
            if i != 0 and f'"{nodeID}"' in self.varNode_info:
                self.createRoomSizeEstimate(nextNodeID)
            nodeID = nextNodeID
            edgeName = ""
            self.nextLines.pop()
        return nodeID

    # self.condition_move用で、次の行が初期化なしまたは静的変数の変数宣言であるかどうかを確かめるための関数
    def get_next_line_in_comp(self, cursor_stmt_list) -> int | None:
        for cursor_stmt in cursor_stmt_list:
            if cursor_stmt.kind == ci.CursorKind.DECL_STMT:
                for vcr in cursor_stmt.get_children():
                    self.check_cursor_error(vcr)
                    isArray = True if vcr.type.kind in (
                        ci.TypeKind.CONSTANTARRAY,
                        ci.TypeKind.INCOMPLETEARRAY,
                        ci.TypeKind.VARIABLEARRAY,
                        ci.TypeKind.DEPENDENTSIZEDARRAY
                    ) else False
                    if vcr.storage_class == ci.StorageClass.STATIC:
                        continue
                    
                    if isArray:
                        for cr in vcr.get_children():
                            if cr.kind == ci.CursorKind.INIT_LIST_EXPR or cr.kind == ci.CursorKind.STRING_LITERAL:
                                return cursor_stmt.location.line
                    elif len(list(vcr.get_children())):
                        return cursor_stmt.location.line
            else:
                return cursor_stmt.location.line
        return None
    
    #ループのbreakやcontinueの情報を保管する
    def createLoopBreakerInfo(self):
        self.loopBreaker_list.append({"break":[], "continue":[]})
        if self.switchBreaker_list:
            self.switchBreaker_list[-1]["level"] += 1

    def downSwitchBreakerLevel(self):
        if self.switchBreaker_list:
            self.switchBreaker_list[-1]["level"] -= 1

    def addLoopBreaker(self, nodeID, type, line):
        if self.switchBreaker_list and type == "break":
            if self.switchBreaker_list[-1]["level"]:
                self.loopBreaker_list[-1][type].append((nodeID, line))
            else:
                self.switchBreaker_list[-1][type].append((nodeID, line))
        else:
            self.loopBreaker_list[-1][type].append((nodeID, line))

    # 色々な関数内や条件文内のコードの解析を行う
    def parse_stmt(self, cr: ci.Cursor, nodeID, edgeName=""):
        self.check_cursor_error(cr)

        #break or continueの後なら何も行わない。ただし、ラベルを現在探索中でラベルを発見した時はラベルを見る
        if nodeID is None and cr.kind != ci.CursorKind.LABEL_STMT:
            return None
        
        #部屋のサイズを1上げる
        self.roomSizeEstimate[1] += 1

        # 変数や関数の宣言
        if cr.kind == ci.CursorKind.DECL_STMT:
            for vcr in cr.get_children():
                self.check_cursor_error(vcr)
                nodeID = self.parse_var_decl(vcr, nodeID, edgeName)
        elif cr.kind == ci.CursorKind.RETURN_STMT:
            # 最初行番を変更
            self.line_info_dict[self.scanning_func].setStart(cr.location.line)
            self.func_info_dict[self.scanning_func].setStart(cr.location.line)
            value_cursor = next(cr.get_children())
            self.check_cursor_error(value_cursor)
            returnNodeID = self.get_expr(value_cursor, shape='lpromoter', label=f"{cr.location.line}")
            # returnによる行確認は個別に行う (step in, step outを残り関数の違いによって区別するため) 関数の遷移履歴、現在のframe_num、現在の行数で確認
            self.line_info_dict[self.scanning_func].setLine(cr.location.line)
            self.line_info_dict[self.scanning_func].setReturn(cr.location.line, self.expr_node_info[f'"{returnNodeID}"'][2])
            self.condition_move[f'"{returnNodeID}"'] = ('return', self.expr_node_info[f'"{returnNodeID}"'][2])
            self.createEdge(nodeID, returnNodeID, edgeName)
            return None
        elif cr.kind == ci.CursorKind.IF_STMT:
            # 最初行番を変更
            self.line_info_dict[self.scanning_func].setStart(cr.location.line)
            self.func_info_dict[self.scanning_func].setStart(cr.location.line)
            nodeID = self.parse_if_stmt(cr, nodeID, edgeName)
        elif cr.kind == ci.CursorKind.WHILE_STMT:
            # 最初行番を変更
            self.line_info_dict[self.scanning_func].setStart(cr.location.line)
            self.func_info_dict[self.scanning_func].setStart(cr.location.line)
            nodeID = self.parse_while_stmt(cr, nodeID, edgeName=edgeName)
        elif cr.kind == ci.CursorKind.DO_STMT:
            # 最初行番を変更
            self.line_info_dict[self.scanning_func].setStart(cr.location.line)
            self.func_info_dict[self.scanning_func].setStart(cr.location.line)
            nodeID = self.parse_do_stmt(cr, nodeID, edgeName=edgeName)
        elif cr.kind == ci.CursorKind.FOR_STMT:
            # 最初行番を変更
            self.line_info_dict[self.scanning_func].setStart(cr.location.line)
            self.func_info_dict[self.scanning_func].setStart(cr.location.line)
            nodeID = self.parse_for_stmt(cr, nodeID, edgeName=edgeName)
        elif cr.kind == ci.CursorKind.SWITCH_STMT:
            # 最初行番を変更
            self.line_info_dict[self.scanning_func].setStart(cr.location.line)
            self.func_info_dict[self.scanning_func].setStart(cr.location.line)
            nodeID = self.parse_switch_stmt(cr, nodeID, edgeName)
        elif cr.kind == ci.CursorKind.BREAK_STMT:
            breakNodeID = self.createNode("break", "hexagon")
            self.createEdge(nodeID, breakNodeID, edgeName)
            self.addLoopBreaker(breakNodeID, "break", cr.location.line)
            self.line_info_dict[self.scanning_func].setLine(cr.location.line)
            return None
        elif cr.kind == ci.CursorKind.CONTINUE_STMT:
            continueNodeID = self.createNode("continue", "hexagon")
            self.createEdge(nodeID, continueNodeID, edgeName)
            self.addLoopBreaker(continueNodeID, "continue", cr.location.line)
            self.line_info_dict[self.scanning_func].setLine(cr.location.line)
            return None
        elif cr.kind == ci.CursorKind.GOTO_STMT:
            # 最初行番を変更
            self.line_info_dict[self.scanning_func].setStart(cr.location.line)
            self.func_info_dict[self.scanning_func].setStart(cr.location.line)
            cr = next(cr.get_children())
            self.check_cursor_error(cr)
            fromNodeID = self.createNode(cr.spelling, 'cds')
            self.createEdge(nodeID, fromNodeID, edgeName)
            #ラベルが既出の場合
            if cr.spelling in self.gotoLabel_list:
                self.gotoLabel_list[cr.spelling]["fromNodeID"].append(f'"{self.roomSizeEstimate[0]}"')
            #まだラベルが既出でない場合
            else:
                self.findingLabel = cr.spelling
                self.gotoLabel_list[cr.spelling] = {"toNodeID": None, "fromNodeID": [f'"{self.roomSizeEstimate[0]}"']}
            return None
        elif cr.kind == ci.CursorKind.LABEL_STMT:
            # 最初行番を変更?
            self.line_info_dict[self.scanning_func].setStart(cr.location.line)
            self.func_info_dict[self.scanning_func].setStart(cr.location.line)
            exec_cr = next(cr.get_children())
            self.check_cursor_error(exec_cr)
            if self.findingLabel:
                if self.findingLabel != cr.spelling:
                    return None
                else:
                    self.findingLabel = None
            toNodeID = self.createNode(cr.spelling, 'note')
            self.createEdge(nodeID, toNodeID)
            #gotoラベルが既出の場合
            if cr.spelling in self.gotoLabel_list:
                self.gotoLabel_list[cr.spelling]["toNodeID"] = f'"{self.roomSizeEstimate[0]}"'
            #gotoラベルが既出でない場合
            else:
                self.gotoLabel_list[cr.spelling] = {"toNodeID": f'"{self.roomSizeEstimate[0]}"', "fromNodeID": []}
            nodeID = self.parse_stmt(exec_cr, toNodeID)
        elif cr.kind == ci.CursorKind.CALL_EXPR:
            expr_info = ExprInfo()
            expr_description = self.parse_call_expr(cr, expr_info)
            expNodeID = self.createNode("")
            self.createEdge(nodeID, expNodeID)
            # 最初行番を変更
            self.line_info_dict[self.scanning_func].setStart(cr.location.line)
            self.func_info_dict[self.scanning_func].setStart(cr.location.line)
            # 関数が単独で出た場合も、途中式に出てくる関数と同じ対応ができるように、仮のノードを作る
            # 関数が単独で出た場合は、計算式キャラクターに登録する (長方形ノードが現れたら作る)
            # 関数に入る前で止まれるようにlineを登録しておく
            self.line_info_dict[self.scanning_func].setLine(cr.location.line)
            self.expr_node_info[f'"{expNodeID}"'] = (expr_description, expr_info.var_references, expr_info.func_references, expr_info.expr_descriptions, cr.location.line)
            next_line = self.get_next_line()
            self.condition_move[f'"{expNodeID}"'] = ('exp', [cr.location.line, *self.expr_node_info[f'"{expNodeID}"'][2], next_line[0]] if len(self.expr_node_info[f'"{expNodeID}"'][2]) else [cr.location.line, next_line[0]])
            nodeID = expNodeID
        else:
            # 最初行番を変更 
            self.line_info_dict[self.scanning_func].setStart(cr.location.line)
            self.func_info_dict[self.scanning_func].setStart(cr.location.line)
            # ここの計算式は計算式キャラクターに登録する
            expNodeID = self.get_expr(cr, shape='rect')
            # 関数に入る前で止まれるようにlineを登録しておく
            self.line_info_dict[self.scanning_func].setLine(cr.location.line)
            next_line = self.get_next_line()
            self.condition_move[f'"{expNodeID}"'] = ('exp', [cr.location.line, *self.expr_node_info[f'"{expNodeID}"'][2], next_line[0]])
            self.createEdge(nodeID, expNodeID, edgeName)
            nodeID = expNodeID
        return nodeID

    # 変数の型を取得
    def get_var_type(self, type: ci.Type):
        # ポインタ型なら中身も
        if type.kind == ci.TypeKind.POINTER:
            pointee = type.get_pointee()
            return {"type": type.spelling, "children": self.get_var_type(pointee)}
        # 配列型なら要素型も
        elif type.kind in (ci.TypeKind.CONSTANTARRAY, ci.TypeKind.INCOMPLETEARRAY, ci.TypeKind.VARIABLEARRAY, ci.TypeKind.DEPENDENTSIZEDARRAY):
            elem = type.get_array_element_type()
            return {"type": type.spelling, "children": self.get_var_type(elem)}
        # 構造体の場合はフィールド列挙
        elif type.kind == ci.TypeKind.ELABORATED:
            struct_type_dict = {"type": type.spelling, "children": {}}
            for field in type.get_fields():
                field_type_dict = self.get_var_type(field.type)
                struct_type_dict["children"][field.spelling] = field_type_dict
            return struct_type_dict
        else:
            return {"type": type.spelling, "children": {}}

    # 変数の宣言 (まだ変数の情報をfopen, malloc, reallocにどう使うかを決められていない(ここで先にfopen/malloc/reallocかどうかを確かめてから使う))
    def parse_var_decl(self, cursor: ci.Cursor, nodeID, edgeName=""):
        #この条件は配列の添字のノードを変えるためにある
        isArray = True if cursor.type.kind in (
            ci.TypeKind.CONSTANTARRAY,
            ci.TypeKind.INCOMPLETEARRAY,
            ci.TypeKind.VARIABLEARRAY,
            ci.TypeKind.DEPENDENTSIZEDARRAY
        ) else False
        #変数名を取得
        varNodeID = self.createNode(cursor.spelling, 'signature')
        # もしstatic変数であれば、self.line_infoやself.func_info_dictの最初の行番が0である場合でも変えない
        isStatic = cursor.storage_class == ci.StorageClass.STATIC

        self.createEdge(nodeID, varNodeID, edgeName)

        # 変数の型名はこのcursorで分かる
        self.varNode_info[f'"{varNodeID}"'] = self.get_var_type(cursor.type)

        #配列
        if isArray:
            # 念の為、添字と配列の中身のカーソルを分けて取得する
            cr_index_list: list[ci.Cursor | int] = []
            cr_init_members = None

            arrTopNodeID = self.createNode("", 'box3d')
            self.createEdge(varNodeID, arrTopNodeID)

            for cr in cursor.get_children():
                if cr.kind == ci.CursorKind.INIT_LIST_EXPR:
                    cr_init_members = list(cr.get_children())
                elif cr.kind == ci.CursorKind.STRING_LITERAL:
                    # 文字列を格納する配列の場合
                    indexNodeID = self.createNode(cr.spelling, 'Mcircle')
                    self.expr_node_info[f'"{indexNodeID}"'] = (
                        str(len(cr.spelling)-2), [], [],
                        [
                            f"store each character of {cr.spelling} into the array in increasing index order",
                            f"array size is automatically set to {len(cr.spelling)-2}"
                        ] if self.is_english else
                        [
                            f"文字列 {cr.spelling} の各文字が添字の小さい順に配列へ格納されます",
                            f"配列サイズは {len(cr.spelling)-2} に自動的に設定されます"
                        ],
                        cursor.location.line
                    )
                    self.createEdge(arrTopNodeID, indexNodeID, "strCont")
                else:
                    cr_index_list.append(cr)

            arrCont_condition_move: list[int | tuple[str,int] | dict[str, any]] = []
            # 初期化する場合 (一番上の添字ノードはこのメソッドで作りくっつける)
            if cr_init_members is not None:
                arr_contents_list = self.get_arr_contents(cr_init_members, cr_index_list)
                arrContNodeID_list = self.parse_arr_contents(arr_contents_list, [cursor.spelling], arrCont_condition_move, cursor.location.line)
                for arrContNodeID in arrContNodeID_list:
                    self.createEdge(arrTopNodeID, arrContNodeID, "arrCont")
                # 一次元配列で添字がない場合
                if len(cr_index_list) == 0:
                    cr_index_list.append(len(arrContNodeID_list))

            nodeID = arrTopNodeID
            index_condition_move: list[int | tuple[str,int] | dict[str, any]] = []

            # Mcircleノードに添字の計算式または推定値を取得する
            for cr_index in cr_index_list:
                if isinstance(cr_index, int):
                    indexNodeID = self.createNode("", 'Mcircle')
                    self.expr_node_info[f'"{indexNodeID}"'] = (
                        str(cr_index), [], [], 
                        [f"array size is automatically set to {cr_index}" if self.is_english else f"添字は {cr_index} が自動的に設定されます"], 
                        cursor.location.line
                        )
                else:
                    indexNodeID = self.get_expr(cr_index, shape="Mcircle")
                    index_condition_move += self.expr_node_info[f'"{indexNodeID}"'][2]
                for func in self.expr_node_info[f'"{indexNodeID}"'][2]:
                    if isinstance(func, dict) and func["name"] in ["malloc", "realloc", "fopen"]:
                        sys.exit(-3)
                self.createEdge(nodeID, indexNodeID)
                nodeID = indexNodeID

            # self.line_infoの最初行番が0である場合、このcondition_moveを記録すると同時にself.line_infoを更新する
            # indexのcondition_moveがあるなら最初の添字の行数を取得する 
            if len(index_condition_move) != 0:
                array_condition_move: list[int | tuple[str,int] | dict[str, any]] = [*index_condition_move, *arrCont_condition_move]
                self.condition_move[f'"{arrTopNodeID}"'] = ('item', array_condition_move)
            # 中身のcondition_moveがあるなら中身の最初の行数を取得する
            elif len(arrCont_condition_move) != 0:
                # 最初の行数がない場合は最初の行数を追加する
                if arrCont_condition_move[0] != cr_init_members[0].location.line:
                    array_condition_move = [cr_init_members[0].location.line, *arrCont_condition_move]
                    self.condition_move[f'"{arrTopNodeID}"'] = ('item', array_condition_move)
                # なければ追加しない (構造体と同じ)
                else:
                    array_condition_move = arrCont_condition_move
                    self.condition_move[f'"{arrTopNodeID}"'] = ('item', array_condition_move)
            # 関数が計算式に含まれていないなら変数名の行数を追加する
            else:
                array_condition_move = [cursor.location.line]
                self.condition_move[f'"{arrTopNodeID}"'] = ('item', array_condition_move)

            self.line_info_dict[self.scanning_func].setStart(array_condition_move[0], isStatic)
            self.func_info_dict[self.scanning_func].setStart(array_condition_move[0], isStatic)

        # 一つの変数/構造体系
        else:
            not_array_cursors = list(cursor.get_children())
            if len(not_array_cursors):
                if len(not_array_cursors) == 2 and not_array_cursors[0].kind == ci.CursorKind.TYPE_REF and not_array_cursors[1].kind != ci.CursorKind.INIT_LIST_EXPR:
                    not_array_cursors.pop(0)
                for cr in not_array_cursors:
                    self.check_cursor_error(cr)
                    # 構造体の宣言でノードを作る
                    if cr.kind == ci.CursorKind.TYPE_REF:
                        nodeID = self.createNode("", 'tab')
                        self.createEdge(varNodeID, nodeID)
                        if len(not_array_cursors) == 1:
                            self.condition_move[f'"{nodeID}"'] = ('item', [cr.location.line])
                            self.line_info_dict[self.scanning_func].setStart(cr.location.line, isStatic)
                            self.func_info_dict[self.scanning_func].setStart(cr.location.line, isStatic)
                    # 構造体系の初期化
                    elif cr.kind == ci.CursorKind.INIT_LIST_EXPR:
                        members = list((f.spelling, f.type.spelling) for f in cursor.type.get_fields())
                        member_crs = list(cr.get_children())
                        memberNum = len(member_crs)
                        member_condition_move: list[int | tuple[str,int] | dict[str, any]] = []
                        isFunc = False
                        for i, member in enumerate(members):
                            if i < memberNum:
                                self.check_cursor_error(member_crs[i])
                                # varnameとvartype(メンバーの)をget_exprの引数に設定する
                                call_exp_cursor_list = None
                                value_cr = self.unwrap_unexposed(member_crs[i])
                                if value_cr.kind == ci.CursorKind.CSTYLE_CAST_EXPR:
                                    casted_exp_cursor = next(value_cr.get_children())
                                    casted_exp_cursor = self.unwrap_unexposed(casted_exp_cursor)
                                    if casted_exp_cursor.kind == ci.CursorKind.CALL_EXPR:
                                        call_exp_cursor_list = list(casted_exp_cursor.get_children())
                                        if call_exp_cursor_list[0].spelling in ["malloc", "realloc"]:
                                            memberNodeID = self.get_expr(casted_exp_cursor, var={"vartype": value_cr.type.spelling[:-1]})
                                            self.expr_node_info[f'"{memberNodeID}"'] = (f"({value_cr.type.spelling}) " + self.expr_node_info[f'"{memberNodeID}"'][0], *self.expr_node_info[f'"{memberNodeID}"'][1:5])
                                elif value_cr.kind == ci.CursorKind.CALL_EXPR:
                                    call_exp_cursor_list = list(value_cr.get_children())
                                    if call_exp_cursor_list[0].spelling in ["malloc", "realloc"]:
                                        memberNodeID = self.get_expr(value_cr, var={"vartype": member[1]})
                                    elif call_exp_cursor_list[0].spelling == "fopen":
                                        sys.exit(-4)
                                if call_exp_cursor_list is None or call_exp_cursor_list[0].spelling not in ["malloc", "realloc"]:
                                    memberNodeID = self.get_expr(member_crs[i], label=member[0], var={"vartype": member[1], "varname": cursor.spelling})
                                self.createEdge(nodeID, memberNodeID)

                                if len(self.expr_node_info[f'"{memberNodeID}"'][2]) != 0:
                                    for func in self.expr_node_info[f'"{memberNodeID}"'][2]:
                                        if isinstance(func, dict) and func["name"] in ["malloc", "realloc", "fopen"]:
                                            sys.exit(-5)
                                    member_condition_move += self.expr_node_info[f'"{memberNodeID}"'][2]
                                    isFunc = True
                            else:
                                memberNodeID = self.createNode(member[0], 'square')
                                self.expr_node_info[f'"{memberNodeID}"'] = ("?", [], [], ["this is an uninitialized part" if self.is_english else "初期化されていない要素です"], cursor.location.line)
                                self.createEdge(nodeID, memberNodeID)
                        if isFunc:
                            # 計算式に関数が含まれていて、なおかつ最初の関数が最初のメンバと同じ行番にない場合は最初のメンバの行数を追加する
                            if member_condition_move[0] != member_crs[0].location.line:
                                member_condition_move.insert(0, member_crs[0].location.line)
                        else:
                            member_condition_move.append(cursor.location.line)
                        # self.line_infoの最初行番をmember_condition_moveの最初の行番で変更する
                        self.condition_move[f'"{nodeID}"'] = ('item', member_condition_move)
                        self.line_info_dict[self.scanning_func].setStart(member_condition_move[0], isStatic)
                        self.func_info_dict[self.scanning_func].setStart(member_condition_move[0], isStatic)
                    # スカラー変数とポインタ
                    else:
                        call_exp_cursor_list = None
                        value_cr = self.unwrap_unexposed(cr)
                        if value_cr.kind == ci.CursorKind.CSTYLE_CAST_EXPR:
                            casted_exp_cursor = next(value_cr.get_children())
                            casted_exp_cursor = self.unwrap_unexposed(casted_exp_cursor)
                            if casted_exp_cursor.kind == ci.CursorKind.CALL_EXPR:
                                call_exp_cursor_list = list(casted_exp_cursor.get_children())
                                if call_exp_cursor_list[0].spelling in ["malloc", "realloc"]:
                                    nodeID = self.get_expr(casted_exp_cursor, var={"vartype": value_cr.type.spelling[:-1]})
                                    self.expr_node_info[f'"{nodeID}"'] = (f"({value_cr.type.spelling}) " + self.expr_node_info[f'"{nodeID}"'][0], *self.expr_node_info[f'"{nodeID}"'][1:5])
                        elif value_cr.kind == ci.CursorKind.CALL_EXPR:
                            call_exp_cursor_list = list(value_cr.get_children())
                            if call_exp_cursor_list[0].spelling in ["malloc", "realloc"]:
                                nodeID = self.get_expr(value_cr, var={"vartype": cursor.type.spelling[:-1]})
                            elif call_exp_cursor_list[0].spelling == "fopen":
                                nodeID = self.get_expr(value_cr, var={"varname": cursor.spelling})
                        if call_exp_cursor_list is None or call_exp_cursor_list[0].spelling not in ["malloc", "realloc", "fopen"]:
                            nodeID = self.get_expr(cr)

                        # 今は一行だが、複数行になる場合、関数の遷移前の行番を取得する必要がある。(関数がない場合は変数名の行数になる)
                        # -> expr_node_info[2]には関数だけでなくその行番も含めて追加する必要がある
                        # ここでもstaticでなければself.line_infoの最初行番を変更する
                        var_condition_move: list[int | tuple[str,int] | dict[str, any]] = [cr.location.line, *self.expr_node_info[f'"{nodeID}"'][2]] if len(self.expr_node_info[f'"{nodeID}"'][2]) else [cursor.location.line]
                        self.condition_move[f'"{nodeID}"'] = ('item', var_condition_move)
                        self.line_info_dict[self.scanning_func].setStart(var_condition_move[0], isStatic)
                        self.func_info_dict[self.scanning_func].setStart(var_condition_move[0], isStatic)
                        self.createEdge(varNodeID, nodeID)
            else:
                # 変数の初期値が無い場合
                nodeID = self.createNode("", 'square')
                self.expr_node_info[f'"{nodeID}"'] = ("?", [], [], ["this is an uninitialized item" if self.is_english else "初期化されていないアイテムです"], cursor.location.line)
                self.condition_move[f'"{nodeID}"'] = ('item', [cursor.location.line])
                self.line_info_dict[self.scanning_func].setStart(cursor.location.line, isStatic)
                self.func_info_dict[self.scanning_func].setStart(cursor.location.line, isStatic)
                self.createEdge(varNodeID, nodeID)
        
        return varNodeID
    
    def get_arr_contents(self, cr_iter: list[ci.Cursor], cr_index_list: list[ci.Cursor | int], depth: int = 1):
        not_init_list_expr = True
        arr_content_list = []
        for i, cr in enumerate(cr_iter):
            if cr.kind == ci.CursorKind.INIT_LIST_EXPR:
                # {3, 4, {2, 5}}となる場合、{{3,0}, {4,0}, {2,5}}}にする必要があるので、
                # まずはInit_list_expr = {}があるかどうかを確認して、そのチェックを後で行えるようにする
                not_init_list_expr = False
                break

        for i, cr in enumerate(cr_iter):
            self.check_cursor_error(cr)
            if cr.kind == ci.CursorKind.INIT_LIST_EXPR:
                # {}の場合は、その中の配列の要素を確かめる
                arr_content_list.append(self.get_arr_contents(list(cr.get_children()), cr_index_list, depth+1))
            # 子要素の中の要素が1つだけ
            else:
                arr_content_list.append([{"label": f"[{i}]" if not_init_list_expr else "[0]", "cursor": cr}])
        
        # 配列の子要素が全て1なら、その1つの要素を抽出する
        if (maxNum := len(max(arr_content_list, key=len))) == 1:
            return [arr_index[0] for arr_index in arr_content_list]
        # 配列の中に配列(子配列)がある場合は、子配列のノードを配列のノードにくっつけていく
        else:
            fixed_arr_contents_list = []
            # 未定の添字があったら配列の要素数を添字に設定する
            if depth > len(cr_index_list):
                cr_index_list.append(maxNum)
            for i, arr_content in enumerate(arr_content_list):
                fixed_arr_contents = []
                # 子要素の中にある要素数を取得する
                contNum = len(arr_content)
                # 子要素を一つずつ作っていく
                for n in range(maxNum):
                    # 初期化されている子要素はそのノードをくっつける
                    if contNum > n:
                        fixed_arr_contents.append(arr_content[n])
                    # 初期化されていない子要素は「値がない」ことを明示するノードを作ってくっつける
                    else:
                        fixed_arr_contents.append({"label": f"[{n}]"})
                fixed_arr_contents_list.append(fixed_arr_contents)
            return fixed_arr_contents_list

    # 配列(多次元も含む)の要素を取得する
    def parse_arr_contents(self, arr_content_list: list[list] | list[dict], index_list: list[str], arr_condition_move: list[int | tuple[str,int] | dict[str, any]], line: int):
        if len(arr_content_list) == 0:
            sys.exit(-6)
        
        if isinstance(arr_content_list[0], list):
            indexNodeID_list = []
            for i, arr_content in enumerate(arr_content_list):
                indexNodeID = self.createNode(f"[{i}]", "box3d")
                for contentNodeID in self.parse_arr_contents(arr_content, [*index_list, f"[{i}]"], arr_condition_move, line):
                    self.createEdge(indexNodeID, contentNodeID)
                indexNodeID_list.append(indexNodeID)
            return indexNodeID_list
                
        else:
            contentNodeID_list = []
            for arr_content in arr_content_list:
                if "cursor" in arr_content:
                    # varnameとvartypeをget_exprの引数に設定する
                    # [*index_list, arr_content["label"]]
                    # varnameとvartype(メンバーの)をget_exprの引数に設定する
                    call_exp_cursor_list = None
                    value_cr = self.unwrap_unexposed(arr_content["cursor"])
                    if value_cr.kind == ci.CursorKind.CSTYLE_CAST_EXPR:
                        casted_exp_cursor = next(value_cr.get_children())
                        casted_exp_cursor = self.unwrap_unexposed(casted_exp_cursor)
                        if casted_exp_cursor.kind == ci.CursorKind.CALL_EXPR:
                            call_exp_cursor_list = list(casted_exp_cursor.get_children())
                            if call_exp_cursor_list[0].spelling in ["malloc", "realloc"]:
                                contentNodeID = self.get_expr(casted_exp_cursor, var={"vartype": value_cr.type.spelling[:-1]})
                                self.expr_node_info[f'"{contentNodeID}"'] = (f"({value_cr.type.spelling}) " + self.expr_node_info[f'"{contentNodeID}"'][0], *self.expr_node_info[f'"{contentNodeID}"'][1:5])
                    elif value_cr.kind == ci.CursorKind.CALL_EXPR:
                        call_exp_cursor_list = list(value_cr.get_children())
                        if call_exp_cursor_list[0].spelling in ["malloc", "realloc"]:
                            contentNodeID = self.get_expr(value_cr, var={"vartype": arr_content["cursor"].type.spelling})
                        elif call_exp_cursor_list[0].spelling == "fopen":
                            sys.exit(-7)
                    if call_exp_cursor_list is None or call_exp_cursor_list[0].spelling not in ["malloc", "realloc"]:
                        contentNodeID = self.get_expr(arr_content["cursor"], shape="square", label=arr_content["label"], var={"vartype": arr_content["cursor"].type.spelling, "varname": index_list[0]})
                    
                    for func in self.expr_node_info[f'"{contentNodeID}"'][2]:
                        if isinstance(func, dict) and func["name"] in ["malloc", "realloc", "fopen"]:
                            sys.exit(-8)
                    if line != arr_content["cursor"].location.line:
                        arr_condition_move = [*arr_condition_move, arr_content["cursor"].location.line, *self.expr_node_info[f'"{contentNodeID}"'][2]]
                    else:
                        arr_condition_move = [*arr_condition_move, *self.expr_node_info[f'"{contentNodeID}"'][2]]
                else:
                    contentNodeID = self.createNode(arr_content["label"], "square")
                    self.expr_node_info[f'"{contentNodeID}"'] = (str(len(arr_content_list)), [], [], ["random value is set here" if self.is_english else "ランダムな値が設定されてます"], line)
                contentNodeID_list.append(contentNodeID)
            return contentNodeID_list

    #式(一つのノードexpNodeに内容をまとめる)
    def get_expr(self, cursor, shape='square', label="", var: dict | None = None) -> str:
        expNodeID = self.createNode(label, shape)
        expr_info = ExprInfo()
        expr_description = self.parse_expr(cursor, expr_info, var=var)
        self.expr_node_info[f'"{expNodeID}"'] = (expr_description, expr_info.var_references, expr_info.func_references, expr_info.expr_descriptions, cursor.location.line)
        return expNodeID

    def unwrap_unexposed(self, cursor: ci.Cursor) -> ci.Cursor:
        self.check_cursor_error(cursor)
        while cursor.kind == ci.CursorKind.UNEXPOSED_EXPR:
            cursor = next(cursor.get_children())
            self.check_cursor_error(cursor)
        return cursor

    # 式の項を一つずつ解析
    # malloc, realloc, fopenが計算式に含まれる場合は特別な条件の下で解析を行う
    def parse_expr(self, cursor: ci.Cursor, expr_info: ExprInfo, var: dict | None = None) -> dict[str, any]:
        cursor = self.unwrap_unexposed(cursor)
        # 現在の計算式がマクロならその情報を返す
        if (cursor.location.file.name, cursor.location.line, cursor.location.column) in self.macro_pos:
            return {"text": self.macro_pos[(cursor.location.file.name, cursor.location.line, cursor.location.column)]}
        expr_description: dict[str, any] = {"text": ""}

        # ()で囲まれている場合
        if cursor.kind == ci.CursorKind.PAREN_EXPR:
            cr = next(cursor.get_children())
            inside_expr_description = self.parse_expr(cr, expr_info)
            expr_description = expr_info.append_expr_description(description=[{"text": "primarily calculate part closed with parens ( and )" if self.is_english else "( ) で囲まれている部分は先に計算します"}], expr=[{"text": "("}, inside_expr_description, {"text": ")"}])
        # 定数(関数の引数が変数であるかを確かめるために定数ノードの形は変える)
        elif cursor.kind == ci.CursorKind.INTEGER_LITERAL:
            expr_description = {"text": next(cursor.get_tokens()).spelling}
        elif cursor.kind == ci.CursorKind.FLOATING_LITERAL:
            expr_description = {"text": next(cursor.get_tokens()).spelling}
        elif cursor.kind == ci.CursorKind.STRING_LITERAL:
            expr_description = {"text": next(cursor.get_tokens()).spelling}
        elif cursor.kind == ci.CursorKind.CHARACTER_LITERAL:
            expr_description = {"text": next(cursor.get_tokens()).spelling}
        # 変数の呼び出し
        elif cursor.kind == ci.CursorKind.DECL_REF_EXPR:
            ref_expr_tokens = list(cursor.get_tokens())
            if len(ref_expr_tokens):
                expr_description = {"reference": ref_expr_tokens[0].spelling}
                # グローバル変数ならグローバル変数のリファレンスを登録する
                if (gvar_cursor := self.gvar_candidate_crs.pop(expr_description["reference"], None)):
                    self.gvar_info.append(f'"{self.parse_var_decl(gvar_cursor, None)}"')
            else:
                expr_description = {"reference": cursor.spelling}
            expr_info.add_var_reference(expr_description["reference"], cursor.referenced.location.line)
        # 配列
        elif cursor.kind == ci.CursorKind.ARRAY_SUBSCRIPT_EXPR:
            index_list: list[str] = []
            # 配列の参照は、添字→添字→・・・→配列名の順で取得する
            while True:
                array_children = [self.unwrap_unexposed(cr) for cr in list(cursor.get_children()) if self.check_cursor_error(cr)]
                if len(array_children) != 2:
                    sys.exit(-9)
                index_list.append(list(self.parse_expr(array_children[1], expr_info).values)[0])
                if array_children[0].kind in (ci.CursorKind.DECL_REF_EXPR, ci.CursorKind.MEMBER_REF_EXPR):
                    name_spell = array_children[0].spelling
                    break
                if array_children[0].kind != ci.CursorKind.ARRAY_SUBSCRIPT_EXPR:
                    sys.exit(-10)
                cursor = array_children[0]
            # 配列の添字は静的に決まるものしか設定できない
            index_path = "][".join(list(reversed(index_list)))
            index_path = "[" + index_path[:-1]

            expr_info.add_var_reference(name_spell, array_children[0].referenced.location.line)
            expr_description = [{"reference": name_spell+index_path}]
        # 構造体のメンバ
        elif cursor.kind == ci.CursorKind.MEMBER_REF_EXPR:
            member_chain: list[str] = []
            member_cursor = cursor
            while member_cursor.kind == ci.CursorKind.MEMBER_REF_EXPR:
                member_chain.append(member_cursor.spelling)
                children = list(member_cursor.get_children())
                if children:
                    member_cursor = children[0]
                else:
                    break
            member_cursor = self.unwrap_unexposed(member_cursor)
            if member_cursor.kind == ci.CursorKind.DECL_REF_EXPR:
                member_chain.append(member_cursor.spelling)
                expr_info.add_var_reference(member_cursor.spelling, member_cursor.referenced.location.line)
                expr_description = [{"reference": ".".join(list(reversed(member_chain)))}]
        
        # 関数
        elif cursor.kind == ci.CursorKind.CALL_EXPR:
            expr_description = self.parse_call_expr(cursor, expr_info, var=var)
        
        # 一項式
        elif cursor.kind == ci.CursorKind.UNARY_OPERATOR:
            # ++aでいうaのカーソル
            operand_cursor = next(cursor.get_children())
            # ++といった演算子
            operator = next(cursor.get_tokens())

            operand_expr = self.parse_expr(operand_cursor, expr_info)
            # 前置(++a)
            if operator.location.offset < operand_cursor.location.offset:
                expr = [{"text": operator.spelling}, operand_expr]
                if self.is_english:
                    if operator.spelling in ExprInfo.unary_front_operator_description_en:
                        description = ExprInfo.unary_front_operator_description_en[operator.spelling](operand_expr)
                    else:
                        description = [{"text": "unresolved operator"}]
                else:
                    if operator.spelling in ExprInfo.unary_front_operator_description:
                        description = ExprInfo.unary_front_operator_description[operator.spelling](operand_expr)
                    else:
                        description = [{"text": "不明な演算子です"}]
            # 後置(a++)
            else:
                operator = next(reversed(list(cursor.get_tokens())))
                expr = [operand_expr, {"text": operator.spelling}]
                if self.is_english:
                    if operator.spelling in ExprInfo.unary_back_operator_description_en:
                        description = ExprInfo.unary_back_operator_description_en[operator.spelling](operand_expr)
                    else:
                        description = [{"text": "unresolved operator"}]
                else:
                    if operator.spelling in ExprInfo.unary_back_operator_description:
                        description = ExprInfo.unary_back_operator_description[operator.spelling](operand_expr)
                    else:
                        description = [{"text": "不明な演算子です"}]
            expr_description = expr_info.append_expr_description(description, expr)
        
        # c言語特有の一項条件式 (現在はsizeofのみに対応)
        elif cursor.kind == ci.CursorKind.CXX_UNARY_EXPR:
            expr_spell = ' '.join([t.spelling for t in list(cursor.get_tokens())])
            if 'sizeof' in expr_spell:
                child_cursor_list = list(cursor.get_children())
                if child_cursor_list:
                    type_str = self.unwrap_unexposed(child_cursor_list[0]).type.spelling
                else:
                    type_str = expr_spell.removeprefix("sizeof(").removesuffix(")")
                expr_description = expr_info.append_expr_description(description=ExprInfo.get_sizeof_operator_description(type_str, self.is_english), expr={"text": expr_spell})

        # 二項条件式(a + b)
        elif cursor.kind == ci.CursorKind.BINARY_OPERATOR:
            expr_crs = [cr for cr in list(cursor.get_children()) if self.check_cursor_error(cr)]
            left_expr_end_offset = expr_crs[0].extent.end.offset
            operator_spell: str = ""
            for token in cursor.get_tokens():
                # 前項の位置を最初に超えたtokenが演算子(+や-など)になる
                if left_expr_end_offset <= token.location.offset:
                    operator_spell = token.spelling
                    break
            left_expr = self.parse_expr(expr_crs[0], expr_info)
            right_expr_list: list[dict[str, any]] = []
            # malloc, realloc, fopenについては、特殊な場合として解析する
            if operator_spell == "=":
                left_cursor = self.unwrap_unexposed(expr_crs[0])
                right_cursor = self.unwrap_unexposed(expr_crs[1])
                if right_cursor.kind == ci.CursorKind.CSTYLE_CAST_EXPR:
                    casted_exp_cursor = next(right_cursor.get_children())
                    casted_exp_cursor = self.unwrap_unexposed(casted_exp_cursor)
                    if casted_exp_cursor.kind == ci.CursorKind.CALL_EXPR:
                        call_exp_cursor_list = list(right_cursor.get_children())
                        func_cursor = self.unwrap_unexposed(call_exp_cursor_list[0])
                        self.check_cursor_error(func_cursor)
                        if func_cursor.spelling in ["malloc", "realloc"]:
                            right_expr_list = [{"text": f"({right_cursor.type.spelling})"}, self.parse_call_expr(casted_exp_cursor, expr_info, var={"vartype": right_cursor.type.spelling[:-1]})]
                elif left_cursor.kind in [ci.CursorKind.ARRAY_SUBSCRIPT_EXPR, ci.CursorKind.MEMBER_REF_EXPR, ci.CursorKind.DECL_REF_EXPR]:
                    if right_cursor.kind == ci.CursorKind.CALL_EXPR:
                        call_exp_cursor_list = list(right_cursor.get_children())
                        func_cursor = self.unwrap_unexposed(call_exp_cursor_list[0])
                        self.check_cursor_error(func_cursor)
                        if func_cursor.spelling in ["malloc", "realloc"]:
                            right_expr_list = [self.parse_call_expr(right_cursor, expr_info, var={"vartype": left_cursor.type.spelling[:-1]})]
                    if left_cursor.kind == ci.CursorKind.DECL_REF_EXPR:
                        if right_cursor.kind == ci.CursorKind.CALL_EXPR:
                            call_exp_cursor_list = list(right_cursor.get_children())
                            func_cursor = self.unwrap_unexposed(call_exp_cursor_list[0])
                            self.check_cursor_error(func_cursor)
                            if call_exp_cursor_list[0].spelling == "fopen":
                                ref_expr_tokens = list(left_cursor.get_tokens())
                                if len(ref_expr_tokens):
                                    expr_description = ref_expr_tokens[0].spelling
                                    # グローバル変数ならグローバル変数のリファレンスを登録する
                                    if (gvar_cursor := self.gvar_candidate_crs.pop(expr_description, None)):
                                        self.gvar_info.append(f'"{self.parse_var_decl(gvar_cursor, None)}"')
                                    right_expr_list = [self.parse_call_expr(right_cursor, expr_info, var={"varname": ref_expr_tokens[0].spelling})]
                                else:
                                    right_expr_list = [self.parse_call_expr(right_cursor, expr_info, var={"varname": cursor.spelling})]
            
            if not len(right_expr_list):
                right_expr_list = [self.parse_expr(expr_crs[1], expr_info)]

            expr = [left_expr, {"text": operator_spell}, *right_expr_list]
            if self.is_english:
                if operator_spell in ExprInfo.binary_operator_descriptions_en:
                    description = ExprInfo.binary_operator_descriptions_en[operator_spell](left_expr,right_expr_list)
                else:
                    description = [{"text": "unresolved operator"}]
            else:
                if operator_spell in ExprInfo.binary_operator_descriptions:
                    description = ExprInfo.binary_operator_descriptions[operator_spell](left_expr,right_expr_list)
                else:
                    description = [{"text": "不明な演算子です"}]
            expr_description = expr_info.append_expr_description(description, expr)

        # 複合代入演算子(a += b)
        elif cursor.kind == ci.CursorKind.COMPOUND_ASSIGNMENT_OPERATOR:
            expr_crs = [cr for cr in list(cursor.get_children()) if self.check_cursor_error(cr)]
            left_expr_end_offset = expr_crs[0].extent.end.offset
            operator_spell = ""
            for token in cursor.get_tokens():
                if left_expr_end_offset <= token.location.offset:
                    operator_spell = token.spelling
                    break
                
            left_expr = self.parse_expr(expr_crs[0], expr_info)
            right_expr =  self.parse_expr(expr_crs[1], expr_info)

            expr = [left_expr, {"text": operator_spell}, right_expr]
            if self.is_english:
                if operator_spell in ExprInfo.compound_assignment_operator_descriptions_en:
                    description = ExprInfo.compound_assignment_operator_descriptions_en[operator_spell](left_expr,right_expr)
                else:
                    description = [{"text": "unresolved operator"}]
            else:
                if operator_spell in ExprInfo.compound_assignment_operator_descriptions:
                    description = ExprInfo.compound_assignment_operator_descriptions[operator_spell](left_expr,right_expr)
                else:
                    description = [{"text": "不明な演算子です"}]
            expr_description = expr_info.append_expr_description(description, expr)

        # 三項条件式(c? a : b) (ここはmallocやrealloc、fopenを許さない)
        elif cursor.kind == ci.CursorKind.CONDITIONAL_OPERATOR:
            expr_crs = [cr for cr in list(cursor.get_children()) if self.check_cursor_error(cr)]
            #まず、条件文を解析し、a : b の aかbを解析する
            condition_expr = self.parse_expr(expr_crs[0], expr_info)
            true_expr = self.parse_expr(expr_crs[1], expr_info)
            false_expr = self.parse_expr(expr_crs[2], expr_info)
            expr = [condition_expr, {"text": "?"}, true_expr, {"text": ":"}, false_expr]
            description = (
                [{"text": "if"}, condition_expr, {"text": "is true, get value of"}, true_expr, {"text": ", otherwise get value of"}, false_expr] 
                if self.is_english else 
                [condition_expr, {"text": "が真なら"}, true_expr, {"text": "、偽なら"}, false_expr, {"text": "の値を使います"}]
                )
            expr_description = expr_info.append_expr_description(description, expr)

        # キャスト型
        elif cursor.kind == ci.CursorKind.CSTYLE_CAST_EXPR:
            cr = next(cursor.get_children())
            casted_expr = self.parse_expr(cr, expr_info)
            expr = [{"text": f"({cursor.type.spelling})"}, casted_expr]
            casted_expr_type = self.unwrap_unexposed(cr).type.spelling
            if casted_expr_type:
                description = (
                    [{"text": "use value of"}, casted_expr, {"text": "casted from"}, casted_expr, {"text": f"to {cursor.type.spelling}"}]
                    if self.is_english else
                    [casted_expr, {"text": "の型を"}, casted_expr, {"text": f"から {cursor.type.spelling}"}, {"text": f"{cursor.type.spelling} に変換します"}]
                    )
            else:
                description = (
                    [{"text": "use value of"}, casted_expr, {"text": f"casted to {cursor.type.spelling}"}]
                    if self.is_english else
                    [casted_expr, {"text": f"の型を {cursor.type.spelling} に変換します"}]
                    )
            expr_description = expr_info.append_expr_description(description, expr)
        
        # 配列の要素や構造体のメンバの{}
        elif cursor.kind == ci.CursorKind.INIT_LIST_EXPR:
            for cr in cursor.get_children():
                self.parse_expr(cr, expr_info)
        
        return expr_description
    
    # 関数の呼び出し(変数と関数の呼び出しは分ける) 
    # 現在、関数を表すノードを生成しているが、他の計算項と同じように、作らないようにする方向でリファクタリングする(その方が楽)
    # 関数の呼び出しの計算コメントは{"name": name, "comment": comment, "args": [arg1, arg2,...]}のように辞書型にする
    def parse_call_expr(self, cursor, expr_info: ExprInfo, var: dict | None = None) -> dict[str, any]:
        children = list(cursor.get_children())

        # --- 関数名ノードの処理 ---
        func_cursor = self.unwrap_unexposed(children[0])
        self.check_cursor_error(func_cursor)

        ref_spell: str = func_cursor.spelling
        self.func_info_dict[self.scanning_func].setRef(ref_spell)

        arg_expr_description_list: list[dict[str,any]] = []

        custom_func_count_in_args: int = 0

        # --- 引数ノードとのエッジ作成 ---
        for arg_cursor in children[1:]:
            arg_expr_info = ExprInfo()
            arg_expr_info.id = expr_info.id
            arg_expr_description = self.parse_expr(arg_cursor, arg_expr_info)
            arg_expr_description_list.append(arg_expr_description)
            
            expr_info.var_references.update(arg_expr_info.var_references)
            expr_info.func_references.extend(arg_expr_info.func_references)
            expr_info.expr_descriptions.extend(arg_expr_info.expr_descriptions)
            expr_info.id = arg_expr_info.id

            custom_func_count_in_args += arg_expr_info.custom_func_count

        description: list[dict[str, any]] = []
        # 標準関数は特別な形でfunc_referencesに登録する
        if ref_spell == "strcpy":
            expr_info.append_standard_func_reference(ref_spell, copyTo=arg_expr_description_list[0], copyFrom=arg_expr_description_list[1])
            description = ([{"text": "copy from"}, arg_expr_description_list[1], {"text": "to"}, arg_expr_description_list[0]] 
                           if self.is_english else
                           [arg_expr_description_list[1], {"text": "の内容を"}, arg_expr_description_list[0], {"text": "にコピーします"}]
                           )
        elif ref_spell == "scanf":
            format = [t.spelling for t in children[1].get_tokens()][0]
            expr_info.append_standard_func_reference(ref_spell, format=format)
            description = ([{"text": f"input awaited... format is {format}"}]
                           if self.is_english else
                           [{"text": f"入力待ちです、、、 フォーマットは {format} です"}]
                           )
        elif ref_spell == "fopen":
            if var is None:
                sys.exit(-12)
            filename = [t.spelling for t in children[1].get_tokens()][0]
            expr_info.append_standard_func_reference(ref_spell, filename=filename, **var)
            description = ([{"text": f"open file \"{filename}\""}]
                           if self.is_english else
                           [{"text": f"ファイル「{filename}」を開きます"}]
                           )
        elif ref_spell == "fclose":
            varname = arg_expr_description_list[0]
            expr_info.append_standard_func_reference(ref_spell, varname=varname)
            description = ([{"text": f"close file of address"}, varname]
                           if self.is_english else
                           [{"text": f"アドレス"}, varname, {"text": "が保存しているファイルを閉じます"}]
                           )
        elif ref_spell == "malloc":
            if var is None:
                sys.exit(-13)
            size = "".join([t.spelling for t in children[1].get_tokens()])
            expr_info.append_standard_func_reference(ref_spell, size=size, **var)
            description = ([{"text": f"reserve memory in size of {size}"}]
                           if self.is_english else
                           [{"text": f"{size}が示すサイズ分のメモリを確保します"}]
                           )
        elif ref_spell == "realloc":
            if var is None:
                sys.exit(-14)
            size = "".join([t.spelling for t in children[2].get_tokens()])
            fromVar = arg_expr_description_list[0]
            expr_info.append_standard_func_reference(ref_spell, size=size, fromVar=fromVar, **var)
            description = ([{"text": f"reserve size {size} memory began with address"}, fromVar]
                           if self.is_english else
                           [fromVar, {"text": f"のアドレスを先頭にもつ、{size}が示すメモリを確保します"}]
                           )
        elif ref_spell == "free":
            varname = arg_expr_description_list[0]
            expr_info.append_standard_func_reference(ref_spell, varname=varname)
            description = ([{"text": f"Liberate memory of address"}, varname]
                           if self.is_english else
                           [{"text": "アドレス"}, varname, {"text": f"が示すメモリを解放します"}]
                           )
        elif ref_spell in ["setvbuf", "printf", "fprintf", "fgets", "fscanf"]:
            expr_info.append_standard_func_reference(ref_spell)
            description = ([{"text": f"execute function {ref_spell}"}]
                           if self.is_english else
                           [{"text": f"関数{ref_spell}を実行します"}]
                           )
        
        if len(description):
            # 標準関数の引数に自作関数が含まれている場合はそのカウントを追加する(この標準関数が特定の自作関数の引数に含まれている場合に自作関数カウントを使えるようにするために登録する)
            expr_info.custom_func_count += custom_func_count_in_args
        else:
            # 標準関数以外なら自作関数として登録する
            if self.is_english:
                if len(arg_expr_description_list):
                    arg_description_list: list[dict] = []
                    arg_expr_list: list[dict] = []
                    for i, item in enumerate(arg_expr_description_list):
                        arg_description_list.extend([item, {"text": f"for #{i+1} argument,"}])
                        arg_expr_list.extend([item, {"text": ","}])
                    arg_description_list.pop()
                    arg_expr_list.pop()
                    description = [{"text": f"execute function {ref_spell} with"}, *arg_expr_description_list]
                else:
                    description = [{"text": f"execute function {ref_spell} with no arguments"}]
            else:
                if len(arg_expr_description_list):
                    arg_description_list: list[dict] = []
                    arg_expr_list: list[dict] = []
                    for i, item in enumerate(arg_expr_description_list):
                        arg_description_list.extend([item, {"text": f"を{i+1}個目の実引数,"}])
                        arg_expr_list.extend([item, {"text": ","}])
                    arg_description_list.pop()
                    arg_expr_list.pop()
                    description = [*arg_expr_description_list, {"text": f"として関数{ref_spell}を実行します"}]
                else:
                    description = [{"text": f"引数なしで、関数{ref_spell}を実行します"}]

            # 参照リストへの関数の追加は深さ優先+先がけになるようにここで行う
            expr_info.append_custom_func_reference((ref_spell, custom_func_count_in_args))
            # 自作関数のカウントを1追加する
            expr_info.custom_func_count += 1

        expr: list[dict[str, any]] = [{"text": f"{ref_spell}("}, *arg_expr_description_list, {"text": ")"}]

        return expr_info.append_expr_description(description, expr)

    # typedefの解析
    def parse_typedef(self, cursor):
        print(f"{cursor.underlying_typedef_type.spelling} {cursor.spelling}")

    # 構造体の解析(フローチャートには含めないが、アイテムには必要なので解析)
    def parse_struct(self, cursor):
        print(f"struct {cursor.spelling}")
        for cr in cursor.get_children():
            self.check_cursor_error(cr)
            print(f"    {cr.type.spelling} {cr.spelling}")

    # 共用体の解析(フローチャートには含めないが、アイテムには必要なので解析)
    def parse_union(self, cursor):
        print(f"union {cursor.spelling}")
        for cr in cursor.get_children():
            self.check_cursor_error(cr)
            print(f"    {cr.type.spelling} {cr.spelling}")
    
    # 列挙型の解析(フローチャートには含めないが、アイテムには必要なので解析)
    def parse_enum(self, cursor):
        print(f"enum {cursor.spelling}")
        value = 0
        for cr in cursor.get_children():
            self.check_cursor_error(cr)
            if (int_cursor := next(cr.get_children(), None)):
                value = int(next(int_cursor.get_tokens()).spelling)
                print(f"    {cr.type.spelling} {cr.spelling} = {value}")
            else:
                print(f"    {cr.type.spelling} {cr.spelling} = {value}")
            value += 1

    # 分岐で新たな部屋情報を登録する
    def createRoomSizeEstimate(self, nodeID):
        if self.roomSizeEstimate:
            #部屋情報が完成したらroomSize辞書に移す
            self.roomSize_info[self.scanning_func][f'"{self.roomSizeEstimate[0]}"'] = self.roomSizeEstimate[1]
        #gotoのラベルを探っている最中は登録しない
        if nodeID:
            #部屋のサイズの初期値は9 (5*4などの部屋ができる)
            self.roomSizeEstimate = [nodeID, 9]

    # 条件文の終点から繋がる次の処理の行を探す関数
    def get_next_line(self):
        next_line = None
        for next_line in list(reversed(self.nextLines)):
            if next_line[1]:
                break
        if next_line is None:
            sys.exit(-15)
        
        return next_line
    
    #if文
    #現在ノードに全ての子ノードをくっつける。出口ノードを作成する
    #子ノード(現在のノードの条件が真/偽それぞれの場合の遷移先)を引数に関数を再帰する
    #その関数の戻り値は条件先の最後の処理を示すノードとし、この戻り値→出口ノードとなる矢印をつける
    #リファクタリング後はchildrenがない場合nodeIDを返すことになっている。これで支障をきたす場合、少し変えることを考える
    def parse_if_stmt(self, cursor, nodeID, edgeName=""):
        termNodeIDs = self.parse_if_branch(cursor, nodeID, [], edgeName)
        endNodeID = self.createNode("", 'circle')
        self.createRoomSizeEstimate(endNodeID)

        for termNodeID in termNodeIDs:
            self.createEdge(termNodeID, endNodeID)

        return endNodeID

    def parse_if_branch(self, cursor: ci.Cursor, nodeID, line_track: list[int | tuple[str,int] | dict[str, any]], edgeName=""):
        def parse_if_branch_start(cursor: ci.Cursor, parentNodeID, line_track: list[int | tuple[str,int] | dict[str, any]], type: str):
            """if / else の本体（複合文または単一文）を処理する"""
            children = list(cursor.get_children())
            if cursor.kind == ci.CursorKind.COMPOUND_STMT:
                if len(children):
                    self.condition_move[f'"{parentNodeID}"'] = (type, line_track + [children[0].location.line])
                else:
                    self.condition_move[f'"{parentNodeID}"'] = (type, line_track + [cursor.extent.end.line])
                return self.parse_comp_stmt(cursor, parentNodeID, type)
            # 混合文がない = {} で囲まれない単体文
            else:
                self.condition_move[f'"{parentNodeID}"'] = (type, line_track + [cursor.location.line])
                return self.parse_stmt(cursor, parentNodeID)
            
        # くっつけるノードをどんどん追加して返す。ifしかなくてもfalseのルートにノードを作ってtrue, falseの二つを追加して返す
        children = list(cursor.get_children())

        # --- 条件式処理 ---
        cond_cursor = children[0]
        self.check_cursor_error(cond_cursor)
        condNodeID = self.get_expr(cond_cursor, shape='diamond', label='if')
        self.createEdge(nodeID, condNodeID, edgeName)

        line_track.append(cond_cursor.location.line)
        line_track += self.expr_node_info[f'"{condNodeID}"'][2]

        if edgeName != "False":
            self.line_info_dict[self.scanning_func].setLine(cond_cursor.location.line)

        # --- then節の処理 ---
        then_cursor = children[1]
        self.check_cursor_error(then_cursor)

        trueNodeID = self.createNode("", 'circle')

        self.createEdge(condNodeID, trueNodeID, "True")
        self.createRoomSizeEstimate(trueNodeID)

        # 後々 condNodeID による演算内容を設定する
        then_end = parse_if_branch_start(then_cursor, trueNodeID, line_track, 'if')

        # trueの後の処理の終点を作る (後でif構文の終点をまとめる)
        trueEndNodeID = self.createNode("", 'terminator')
        end_line = then_cursor.extent.end.line

        next_line = self.get_next_line()

        # if len(list(then_cursor.get_children())):
        #     self.condition_move[f'"{trueEndNodeID}"'] = ('ifEnd',  [end_line, next_line[0]])

        self.createEdge(then_end, trueEndNodeID)

        # else節の処理がある場合
        if len(children) > 2:
            else_cursor = children[2]
            self.check_cursor_error(else_cursor)

            if else_cursor.kind == ci.CursorKind.IF_STMT:
                # else if の再帰処理
                nodeIDs = [trueEndNodeID] + self.parse_if_branch(else_cursor, condNodeID, line_track, edgeName="False")
            else:
                # else
                falseEndNodeID = self.createNode("", 'terminator')
                in_else_cursor = list(else_cursor.get_children())
                if len(in_else_cursor):
                    # 後々 condNodeID による演算内容を設定する
                    falseNodeID = self.createNode("", 'doublecircle')
                    self.createEdge(condNodeID, falseNodeID, "False")
                    self.createRoomSizeEstimate(falseNodeID)
                    nodeID = parse_if_branch_start(else_cursor, falseNodeID, line_track, 'else')
                    end_line = in_else_cursor[-1].location.line
                    self.line_info_dict[self.scanning_func].setLine(end_line)
                    self.createEdge(nodeID, falseEndNodeID)
                else:
                    nodeID = condNodeID
                    self.line_info_dict[self.scanning_func].setLine(else_cursor.location.line)
                    self.condition_move[f'"{falseEndNodeID}"'] = ('ifAllFalse', [*line_track, next_line[0]])
                    self.createEdge(nodeID, falseEndNodeID, "False")
                nodeIDs = [trueEndNodeID, falseEndNodeID]
        else:
            # elseがなくても終点を作る
            falseEndNodeID = self.createNode("", 'terminator')
            # elseがない場合は仮ifとしてcondition_moveを取得する
            self.condition_move[f'"{falseEndNodeID}"'] = ('ifAllFalse', [*line_track, cond_cursor.location.line, next_line[0]] if isinstance(line_track[-1], tuple) else [*line_track, next_line[0]])
            # print(end_line)
            # self.line_info_dict[self.scanning_func].setLine(end_line)
            self.createEdge(condNodeID, falseEndNodeID, "False")
            nodeIDs = [trueEndNodeID, falseEndNodeID]
        
        return nodeIDs
    
    #while文
    #子ノード(真の条件先の最初の処理)を現在のノードに付ける
    #子ノードを引数とする関数を呼び出し、真の場合の最後の処理をこの関数の戻り値とする
    #その戻り値を現在ノードに付ける
    #現在のノードは次のノードに付ける
    def parse_while_stmt(self, cursor: ci.Cursor, nodeID, edgeName="", isFinalStmtInSwitch=False):
        self.createLoopBreakerInfo()
        
        children = list(cursor.get_children())

        self.line_info_dict[self.scanning_func].setLoop(cursor.extent.start.line, cursor.extent.end.line)

        # --- 条件処理 ---
        cond_cursor = children[0]
        self.check_cursor_error(cond_cursor)
        condNodeID = self.get_expr(cond_cursor, shape='pentagon', label='while')
        self.createRoomSizeEstimate(condNodeID)

        self.createEdge(nodeID, condNodeID, edgeName)

        # --- 条件True時の処理ノード ---
        trueNodeID = self.createNode("", 'circle')
        self.condition_move[f'"{condNodeID}"'] = ('whileIn', [cond_cursor.location.line])
        self.line_info_dict[self.scanning_func].setLine(cond_cursor.location.line)
        
        # 次のノードがwhileのtrueかを確認するためにエッジにラベルをつけておく(falseも同じ)
        self.createEdge(condNodeID, trueNodeID, "true")
        self.createRoomSizeEstimate(trueNodeID)

        # --- 本体処理 ---
        body_end = trueNodeID
        content_cursor = children[1]
        self.check_cursor_error(content_cursor)
        if content_cursor.kind == ci.CursorKind.COMPOUND_STMT:
            cr_true = list(content_cursor.get_children())
            if len(cr_true):
                self.condition_move[f'"{trueNodeID}"'] = ('whileTrue', [cond_cursor.location.line, *self.expr_node_info[f'"{condNodeID}"'][2], cr_true[0].location.line])
            else:
                self.condition_move[f'"{trueNodeID}"'] = ('whileTrue', [cond_cursor.location.line, *self.expr_node_info[f'"{condNodeID}"'][2], cond_cursor.location.line])
            body_end = self.parse_comp_stmt(content_cursor, trueNodeID, "while")
        else:
            self.condition_move[f'"{trueNodeID}"'] = ('whileTrue', [cond_cursor.location.line, *self.expr_node_info[f'"{condNodeID}"'][2], content_cursor.location.line])
            self.nextLines.append((cond_cursor.location.line, True))
            body_end = self.parse_stmt(content_cursor, trueNodeID)
            self.nextLines.pop(-1)

        # --- ループを閉じる処理 ---
        loop_back_node = self.createNode("", 'parallelogram')  # 再評価への中継点

        self.createEdge(body_end, loop_back_node)
        self.createEdge(loop_back_node, condNodeID)

        # --- 条件False時の処理（脱出） ---
        endNodeID = self.createNode("", 'doublecircle')
        self.createEdge(condNodeID, endNodeID, "false")
        self.createRoomSizeEstimate(endNodeID)
        next_line = self.get_next_line()

        self.condition_move[f'"{endNodeID}"'] = ('whileFalse', [cond_cursor.location.line, *self.expr_node_info[f'"{condNodeID}"'][2], next_line[0]])

        self.createEdgeForLoop(endNodeID, loop_back_node, [cursor.location.line] if isFinalStmtInSwitch else [], [cond_cursor.location.line])

        self.downSwitchBreakerLevel()
        return endNodeID

    #do-while文
    #まずは最初の処理を示す子ノードと現在ノードを接続する
    #Doノードの子ノードはCOMPOUNDと条件部しかなく、条件部は2つ目に読まれる
    #そこで読み込まれたノードを先頭ノードと次ノードをくっつける
    def parse_do_stmt(self, cursor: ci.Cursor, nodeID, edgeName="", isFinalStmtInSwitch=False):
        self.createLoopBreakerInfo()

        initNodeID = self.createNode(f"{cursor.location.line}", 'invtrapezium')
        self.createEdge(nodeID, initNodeID, edgeName)

        trueNodeID = self.createNode("", 'circle')
        self.createEdge(initNodeID, trueNodeID)

        #ここで部屋情報を作る
        self.createRoomSizeEstimate(trueNodeID)
        
        falseNodeID = self.createNode("", 'doublecircle')

        self.line_info_dict[self.scanning_func].setLoop(cursor.extent.end.line, cursor.extent.start.line)

        for cr in cursor.get_children():
            self.check_cursor_error(cr)
            if cr.kind == ci.CursorKind.COMPOUND_STMT:
                cr_in = list(cr.get_children())
                self.line_info_dict[self.scanning_func].setLine(cr.location.line)
                nodeID = self.parse_comp_stmt(cr, trueNodeID, edgeName="do_while")
            else:
                if nodeID is None:
                    return None
                condNodeID = self.get_expr(cr, shape='diamond', label='do')
                # 今まではdo_whileだけ条件分岐の部屋を作っていなかったが、continueにも対応させるために作ることにする
                self.createRoomSizeEstimate(condNodeID)
                self.condition_move[f'"{condNodeID}"'] = ('doWhileIn', [cr.location.line])
                self.line_info_dict[self.scanning_func].setLine(cr.location.line)
                self.createEdgeForLoop(falseNodeID, condNodeID, [cursor.extent.end.line] if isFinalStmtInSwitch else [], [cr.location.line])
                self.createEdge(nodeID, condNodeID)
                self.createEdge(condNodeID, trueNodeID, "True")
                self.createEdge(condNodeID, falseNodeID, "False")
        if len(cr_in):
            self.condition_move[f'"{initNodeID}"'] = ('doWhileInit', [cursor.location.line, cr_in[0].location.line])
            # self.condition_move[f'"{initNodeID}"'] = ('doWhileInit', [None, cr_in[0].location.line])
            self.condition_move[f'"{trueNodeID}"'] = ('doWhileTrue', [cursor.extent.end.line, *self.expr_node_info[f'"{condNodeID}"'][2], cr_in[0].location.line])
        else:
            self.condition_move[f'"{initNodeID}"'] = ('doWhileInit', [cursor.location.line, cursor.location.line])
            # self.condition_move[f'"{initNodeID}"'] = ('doWhileInit', [None, cursor.location.line])
            self.condition_move[f'"{trueNodeID}"'] = ('doWhileTrue', [cursor.extent.end.line, *self.expr_node_info[f'"{condNodeID}"'][2], cursor.location.line])

        next_line = self.get_next_line()

        self.condition_move[f'"{falseNodeID}"'] = ('doWhileFalse', [cursor.extent.end.line, *self.expr_node_info[f'"{condNodeID}"'][2], next_line[0]])
        #ここでdo_whileを抜けた後の部屋情報を作る
        self.createRoomSizeEstimate(falseNodeID)

        self.downSwitchBreakerLevel()
        return falseNodeID

    #for文
    #まずは式1に対するノードを作成(for(式1; 式2; 式3))
    #あとは、ほぼWhileと同じ。式2の子ノード(真である場合の遷移先)の最後の処理が式3であることに注意
    def parse_for_stmt(self, cursor: ci.Cursor, nodeID, edgeName="", isFinalStmtInSwitch=False):
        #for(INIT; COND; CHANGE)
        #cursor.get_childrenの最後の要素は必ず処理部の最初のカーソルであるから、それ以外のカーソルが式1~式3の候補となる。
        self.createLoopBreakerInfo()

        initNodeID = None
        condNodeID = None
        changeNodeID = None
        changeExpr_cursor = None
        endNodeID = self.createNode("", 'doublecircle')
        *expr_cursors, exec_cursor = list(cursor.get_children())
        semi_offset = [token.location.offset for token in list(cursor.get_tokens()) if token.spelling == ';'][:2]

        self.line_info_dict[self.scanning_func].setLoop(cursor.extent.start.line, cursor.extent.end.line)
        for cr in expr_cursors:
            self.check_cursor_error(cr)
            if cr.location.offset < semi_offset[0]:
                # もしかしたら変数の値の変更が2つ以上ある場合に対応できていない可能性がある。もしそうなら後で修正する
                if cr.kind == ci.CursorKind.DECL_STMT:
                    var_cr_list = list(cr.get_children())
                    initNodeID = self.createNode(str(len(var_cr_list)), 'invhouse')
                    varNodeID = initNodeID
                    self.createRoomSizeEstimate(varNodeID)
                    for var_cr in var_cr_list:
                        self.check_cursor_error(var_cr)
                        varNodeID = self.parse_var_decl(var_cr, varNodeID, "")
                else:
                    initNodeID = self.get_expr(cr, shape='invhouse')
                self.createEdge(nodeID, initNodeID, edgeName)
                edgeName = ""
            elif semi_offset[0] < cr.location.offset < semi_offset[1]:
                condNodeID = self.get_expr(cr, shape='pentagon', label='for')
                self.createRoomSizeEstimate(condNodeID)
                if initNodeID:
                    self.createEdge(initNodeID, condNodeID)
                else:
                    self.createEdge(nodeID, condNodeID, edgeName)
                    edgeName = ""
            elif semi_offset[1] < cr.location.offset:
                changeExpr_cursor = cr

        if condNodeID is None:
            condNodeID = self.createNode("for", 'pentagon')
            self.createRoomSizeEstimate(condNodeID)
            if initNodeID:
                self.createEdge(initNodeID, condNodeID)
            else:
                self.createEdge(nodeID, condNodeID, edgeName)
                
        self.condition_move[f'"{condNodeID}"'] = ('forIn', [cursor.location.line])
        self.line_info_dict[self.scanning_func].setLine(cursor.location.line)
        self.check_cursor_error(exec_cursor)

        trueNodeID = self.createNode("", 'circle')
        self.createEdge(condNodeID, trueNodeID, "True")
        #ここで部屋情報を作る
        self.createRoomSizeEstimate(trueNodeID)

        if exec_cursor.kind == ci.CursorKind.COMPOUND_STMT:
            cr_true = list(exec_cursor.get_children())
            if len(cr_true):
                self.condition_move[f'"{trueNodeID}"'] = ('forTrue', [cursor.location.line, *self.expr_node_info[f'"{condNodeID}"'][2], cr_true[0].location.line])
            else:
                self.condition_move[f'"{trueNodeID}"'] = ('forTrue', [cursor.location.line, *self.expr_node_info[f'"{condNodeID}"'][2], cursor.location.line])
            nodeID = self.parse_comp_stmt(exec_cursor, trueNodeID, "for_w_change" if changeExpr_cursor else "for_wo_change")
        else:
            self.condition_move[f'"{trueNodeID}"'] = ('forTrue', [cursor.location.line, *self.expr_node_info[f'"{condNodeID}"'][2], exec_cursor.location.line])
            self.nextLines.append((cursor.location.line, True))
            nodeID = self.parse_stmt(exec_cursor, trueNodeID)
            self.nextLines.pop(-1)

        #changeノードがある条件
        if self.loopBreaker_list[-1]["continue"] or nodeID:
            if changeExpr_cursor:
                changeNodeID = self.get_expr(changeExpr_cursor, shape='parallelogram', label=str(exec_cursor.extent.end.line))
            else:
                changeNodeID = self.createNode(str(cursor.location.line), shape='parallelogram')
        else:
            changeNodeID = self.createNode(str(cursor.location.line), shape='parallelogram')

        self.createEdge(nodeID, changeNodeID)
        self.createEdge(changeNodeID, condNodeID)
        self.createEdgeForLoop(endNodeID, changeNodeID, [cursor.extent.end.line] if isFinalStmtInSwitch else [], [cursor.location.line])
        
        self.createEdge(condNodeID, endNodeID, "False")
        #ここでforを抜けた後の部屋情報を作る
        self.createRoomSizeEstimate(endNodeID)

        next_line = self.get_next_line()

        forFalse_condition_move = [cursor.location.line, *self.expr_node_info[f'"{condNodeID}"'][2], cursor.extent.end.line, next_line[0]] if isFinalStmtInSwitch else [cursor.location.line, *self.expr_node_info[f'"{condNodeID}"'][2], next_line[0]]
        self.condition_move[f'"{endNodeID}"'] = ('forFalse', forFalse_condition_move)
        
        self.downSwitchBreakerLevel()
        return endNodeID

    # switch文
    # caseノード(invtriangle型)は、次に遷移する行番を取得
    # これとエッジのラベルを組み合わせてワープのfromToを形成する
    # endノードについても、エッジとノードのラベルでfromToを形成する
    def parse_switch_stmt(self, cursor: ci.Cursor, nodeID, edgeName=""):
        #caseはbreakだけ適応させる
        #levelが0ならbreakノードを追加する。levelは繰り返し文が入ると1上がる。
        #それ以外ならloopBreaker_listに追加する。
        def createSwitchBreakerInfo():
            self.switchBreaker_list.append({"level": 0, "break":[]})

        #switchのcaseのbreakノードを追加する。
        def createSwitchBreakerEdge(endNodeID):
            switchBreaker = self.switchBreaker_list.pop()
            break_list = switchBreaker["break"]
            next_line = self.get_next_line()
            for breakNodeID, line in break_list:
                self.createEdge(breakNodeID, endNodeID)
                self.condition_move[f'"{breakNodeID}"'] = ('switchEnd', [line, next_line[0]])

        cond_cursor, comp_exec_cursor = [cr for cr in cursor.get_children() if self.check_cursor_error(cr)]

        switchRoomSizeEstimate = self.roomSizeEstimate
        self.roomSizeEstimate = None

        #switchの構造はswitch(A)のようにAは必ず必要
        condNodeID = self.get_expr(cond_cursor, shape='diamond', label='switch')
        self.createEdge(nodeID, condNodeID, edgeName)
        nodeID = None

        createSwitchBreakerInfo()

        endNodeID = self.createNode(f"end", 'invtriangle')

        isDefault = False
        #switch(A){ B }の場合
        if comp_exec_cursor.kind == ci.CursorKind.COMPOUND_STMT:
            self.line_info_dict[self.scanning_func].setLine(comp_exec_cursor.location.line)
            self.line_info_dict[self.scanning_func].setLine(comp_exec_cursor.extent.end.line)

            comp_stmt_cursor_list = list(comp_exec_cursor.get_children())
            cursor_list_by_case: list[tuple[list[tuple[ci.Cursor, ci.Cursor]], list[ci.Cursor]]] = []
            begin_line_list: list[int] = []

            # まずはcomp_stmt_cursor_list (B) の処理用にcaseの遷移先の行を取得する
            while len(comp_stmt_cursor_list):
                cr = comp_stmt_cursor_list.pop(0)
                self.check_cursor_error(cr)
                if cr.kind == ci.CursorKind.CASE_STMT:
                    if isDefault:
                        sys.exit(-30)
                    case_cursor_list: list[tuple[ci.Cursor, ci.Cursor]] = []
                    while cr.kind in (ci.CursorKind.CASE_STMT, ci.CursorKind.DEFAULT_STMT):
                        caseValue_cursor, next_cr = [case_cr for case_cr in cr.get_children() if self.check_cursor_error(case_cr)]
                        case_cursor_list.append((cr, caseValue_cursor))
                        cr = next_cr
                    first_line = None
                    comp_stmt_cursor_list.insert(0, cr)
                    stmt_cursor_list_in_case: list[ci.Cursor] = []
                    for i, stmt_cursor in enumerate(comp_stmt_cursor_list):
                        if stmt_cursor.kind in (ci.CursorKind.CASE_STMT, ci.CursorKind.DEFAULT_STMT, ci.CursorKind.BREAK_STMT):
                            break
                        elif stmt_cursor.kind == ci.CursorKind.COMPOUND_STMT:
                            first_line = first_line if first_line else self.get_next_line_in_comp(list(stmt_cursor.get_children())) 
                        else:
                            first_line = first_line if first_line else self.get_next_line_in_comp([stmt_cursor])
                        stmt_cursor_list_in_case.append(stmt_cursor)

                    if first_line:
                        begin_line_list.append(first_line)
                        if stmt_cursor.kind == ci.CursorKind.BREAK_STMT:
                            stmt_cursor_list_in_case.append(stmt_cursor)
                    else:
                        # 最後までcaseが出ない場合
                        if i == len(comp_stmt_cursor_list) - 1:
                            begin_line_list.append(comp_exec_cursor.extent.end.line)
                        # case, default, breakが途中で現れた場合
                        else:
                            if comp_stmt_cursor_list[i].kind == ci.CursorKind.BREAK_STMT:
                                begin_line_list.append(comp_stmt_cursor_list[i].location.line)
                                stmt_cursor_list_in_case.append(comp_stmt_cursor_list[i])
                            elif comp_stmt_cursor_list[i-1].kind == ci.CursorKind.COMPOUND_STMT:
                                begin_line_list.append(comp_stmt_cursor_list[i-1].extent.end.line)
                            else:
                                begin_line_list.append(comp_stmt_cursor_list[i-1].location.line)
                    
                    cursor_list_by_case.append((case_cursor_list, stmt_cursor_list_in_case))
                    if stmt_cursor.kind in (ci.CursorKind.CASE_STMT, ci.CursorKind.DEFAULT_STMT):
                        comp_stmt_cursor_list = comp_stmt_cursor_list[i:]
                    else:
                        comp_stmt_cursor_list = comp_stmt_cursor_list[i+1:]
                     
                elif cr.kind == ci.CursorKind.DEFAULT_STMT:
                    if isDefault:
                        sys.exit(-31)
                    cursor_in_default = next(cr.get_children())
                    self.check_cursor_error(cursor_in_default)
                    isDefault = True
                    # 混合文の中身を調べる
                    first_line = None
                    comp_stmt_cursor_list.insert(0, cursor_in_default)
                    stmt_cursor_list_in_case: list[ci.Cursor] = []
                    for i, stmt_cursor in enumerate(comp_stmt_cursor_list):
                        if stmt_cursor.kind == ci.CursorKind.BREAK_STMT:
                            break
                        elif stmt_cursor.kind == ci.CursorKind.COMPOUND_STMT:
                            first_line = first_line if first_line else self.get_next_line_in_comp(list(stmt_cursor.get_children()))
                        else:
                            first_line = first_line if first_line else self.get_next_line_in_comp([stmt_cursor])
                        stmt_cursor_list_in_case.append(stmt_cursor)

                    if first_line:
                        begin_line_list.append(first_line)
                    else:
                        # breakが出た場合
                        if comp_stmt_cursor_list[i].kind == ci.CursorKind.BREAK_STMT:
                            begin_line_list.append(comp_stmt_cursor_list[i].location.line)
                            stmt_cursor_list_in_case.append(comp_stmt_cursor_list[i])
                        else:
                            begin_line_list.append(comp_exec_cursor.extent.end.line)
                    comp_stmt_cursor_list = []
                    cursor_list_by_case.append(([(cr, cursor_in_default)], stmt_cursor_list_in_case))
                # 複合文や文が単独で出てくる場合は対応せずにプログラムを終了する
                else:
                    sys.exit(-22)
            
            # 最後のcase(default)が終わった後にbreakがない時、switchの末尾の } に遷移するので、その行番を先頭行番リストの末尾に登録しておく
            begin_line_list.append(comp_exec_cursor.extent.end.line)
            # 次は取得した最初の行番リストを用いてノードを作る
            comp_stmt_cursor_list = list(comp_exec_cursor.get_children())

            for i, (case_cursor_list, stmt_cursor_list_in_case) in enumerate(cursor_list_by_case):
                # まずはcaseノードをくっつけていく
                prevNodeID = condNodeID
                for j, (case_cursor, case_value_cursor) in enumerate(case_cursor_list):
                    if case_cursor.kind == ci.CursorKind.CASE_STMT:
                        caseNodeID = self.get_expr(case_value_cursor, shape='invtriangle', label='case')
                    else:
                        caseNodeID = self.createNode('default', shape='invtriangle')
                    
                    self.createEdge(prevNodeID, caseNodeID)
                    if j == 0 and nodeID:
                        middleCaseNodeID = self.createNode('switchMiddleCase', 'triangle')
                        self.createEdge(nodeID, middleCaseNodeID)
                        self.createEdge(middleCaseNodeID, caseNodeID)
                        self.condition_move[f'"{middleCaseNodeID}"'] = ('switchMiddleCase', [begin_line_list[i]])
                    prevNodeID = caseNodeID

                # switchの元の部屋のサイズを+1する
                switchRoomSizeEstimate[1] += 1
                # ここで一つのcaseの部屋情報を作る
                self.createRoomSizeEstimate(caseNodeID)
                # switchの条件式からcase直下の最初の行への遷移情報を登録する
                self.condition_move[f'"{caseNodeID}"'] = ('switchCase', [comp_exec_cursor.location.line, *self.expr_node_info[f'"{condNodeID}"'][2], begin_line_list[i]])
                
                nodeID = caseNodeID
                begin_line_list_by_stmt: list[int | None] = []

                for j, stmt_cursor in enumerate(stmt_cursor_list_in_case):
                    if stmt_cursor.kind == ci.CursorKind.BREAK_STMT:
                        begin_line_list_by_stmt.append(stmt_cursor.location.line)
                    elif stmt_cursor.kind == ci.CursorKind.COMPOUND_STMT:
                        begin_line_list_by_stmt.append(self.get_next_line_in_comp(list(stmt_cursor.get_children())))
                    else:
                        begin_line_list_by_stmt.append(self.get_next_line_in_comp([stmt_cursor]))

                for j, stmt_cursor in enumerate(stmt_cursor_list_in_case):
                    if stmt_cursor.kind == ci.CursorKind.BREAK_STMT:
                        nodeID = self.parse_stmt(stmt_cursor, nodeID)
                    elif stmt_cursor.kind == ci.CursorKind.COMPOUND_STMT:
                        cursor_list_in_comp_stmt = list(stmt_cursor.get_children())
                        for k, cursor_stmt_in_comp_stmt in enumerate(cursor_list_in_comp_stmt):
                            if (next_line := self.get_next_line_in_comp(cursor_list_in_comp_stmt[k+1:])):
                                self.nextLines.append((next_line, True))
                            else:
                                next_line = None
                                for next_line in begin_line_list_by_stmt[j+1:]:
                                    if next_line:
                                        break
                                if next_line:
                                    self.nextLines.append((next_line, True))
                                else:
                                    if i == len(cursor_list_by_case) - 1:
                                        self.nextLines.append((comp_exec_cursor.extent.end.line, True))
                                    else:
                                        if stmt_cursor_list_in_case[-1].kind == ci.CursorKind.COMPOUND_STMT:
                                            self.nextLines.append((stmt_cursor_list_in_case[-1].extent.end.line, True))
                                        else:
                                            self.nextLines.append((begin_line_list[i+1], True))
                            nodeID = self.parse_stmt(cursor_stmt_in_comp_stmt, nodeID)
                            if j != 0 or k != 0 and f'"{nodeID}"' in self.varNode_info:
                                self.createRoomSizeEstimate(nodeID)
                            self.nextLines.pop(-1)
                    else:
                        if j < len(stmt_cursor_list_in_case) - 1 and begin_line_list_by_stmt[j+1]:
                            self.nextLines.append((begin_line_list_by_stmt[j+1], True))
                        else:
                            next_line = None
                            for next_line in begin_line_list_by_stmt[j+1:]:
                                if next_line:
                                    break
                            if next_line:
                                self.nextLines.append((next_line, True))
                            else:
                                if i == len(cursor_list_by_case) - 1:
                                    self.nextLines.append((comp_exec_cursor.extent.end.line, True))
                                else:
                                    if stmt_cursor_list_in_case[-1].kind == ci.CursorKind.COMPOUND_STMT:
                                        self.nextLines.append((stmt_cursor_list_in_case[-1].extent.end.line, True))
                                    else:
                                        self.nextLines.append((begin_line_list[i+1], True))
                        if j == len(stmt_cursor_list_in_case) - 1:
                            if stmt_cursor.kind == ci.CursorKind.WHILE_STMT:
                                nodeID = self.parse_while_stmt(stmt_cursor, nodeID, isFinalStmtInSwitch=True)
                            elif stmt_cursor.kind == ci.CursorKind.DO_STMT:
                                nodeID = self.parse_do_stmt(stmt_cursor, nodeID, isFinalStmtInSwitch=True)
                            elif stmt_cursor.kind == ci.CursorKind.FOR_STMT:
                                nodeID = self.parse_for_stmt(stmt_cursor, nodeID, isFinalStmtInSwitch=True)
                            else:
                                nodeID = self.parse_stmt(stmt_cursor, nodeID)
                                if j != 0 and f'"{nodeID}"' in self.varNode_info:
                                    self.createRoomSizeEstimate(nodeID)
                        else:
                            nodeID = self.parse_stmt(stmt_cursor, nodeID)
                            if j != 0 and f'"{nodeID}"' in self.varNode_info:
                                self.createRoomSizeEstimate(nodeID)
                        self.nextLines.pop(-1)

            end_line = comp_exec_cursor.extent.end.line

        # switch(A) Bの時、Bが case C: D なら A == C でDが行われる。
        # しかし、Bが case C:でないなら D は無視される。Dは複数行でも良い。
        elif comp_exec_cursor.kind in (ci.CursorKind.CASE_STMT, ci.CursorKind.DEFAULT_STMT):
            caseValue_cursor, exec_cursor = [cr for cr in comp_exec_cursor.get_children() if self.check_cursor_error(cr)]
            if comp_exec_cursor.kind == ci.CursorKind.DEFAULT_STMT:
                isDefault = True

            caseNodeID = self.get_expr(caseValue_cursor, shape='invtriangle')
            self.createEdge(condNodeID, caseNodeID)
            createSwitchBreakerInfo()
            #switchの元の部屋のサイズを+1する
            switchRoomSizeEstimate[1] += 1
            #ここでDのための部屋情報を作る
            self.createRoomSizeEstimate(caseNodeID)
            if (next_line := self.get_next_line_in_comp([exec_cursor])):
                self.condition_move[f'"{caseNodeID}"'] = ('switchCase', [cr.location.line, *self.expr_node_info[f'"{condNodeID}"'][2], next_line])
            else:
                self.condition_move[f'"{caseNodeID}"'] = ('switchCase', [cr.location.line, *self.expr_node_info[f'"{condNodeID}"'][2], self.get_next_line()[0]])
            nodeID = self.parse_stmt(exec_cursor, caseNodeID)
             
            self.line_info_dict[self.scanning_func].setLine(exec_cursor.location.line)
            self.createEdge(nodeID, endNodeID)

            end_line = exec_cursor.location.line

        self.createEdge(nodeID, endNodeID)
        if not isDefault:
            self.createEdge(condNodeID, endNodeID)

        createSwitchBreakerEdge(endNodeID)
        #ここでswitchを抜けた後の部屋情報を作る
        self.createRoomSizeEstimate(endNodeID)
        next_line = self.get_next_line()
        
        self.condition_move[f'"{endNodeID}"'] = ('switchEnd', [end_line, next_line[0]])

        self.roomSize_info[self.scanning_func][f'"{switchRoomSizeEstimate[0]}"'] = switchRoomSizeEstimate[1]
        return endNodeID 

    # ループ処理のノードをくっつけていく (switch文はbreakしか許されないので、switchはここに含めない)
    def createEdgeForLoop(self, breakToNodeID: str, continueToNodeID: str, break_line_track: list[int], continue_line_track: list[int]):
        loopBreaker = self.loopBreaker_list.pop()
        break_list = loopBreaker["break"]
        continue_list  = loopBreaker["continue"]
        next_line = self.get_next_line()
        break_line_track.append(next_line[0])

        for breakNodeID, breakLine in break_list:
            self.createEdge(breakNodeID, breakToNodeID)
            self.condition_move[f'"{breakNodeID}"'] = ('break', [breakLine] + break_line_track)
            self.line_info_dict[self.scanning_func].setLine(breakLine)
        for continueNodeID, continueLine in continue_list:
            self.createEdge(continueNodeID, continueToNodeID)
            self.condition_move[f'"{continueNodeID}"'] = ('continue', [continueLine] + continue_line_track)
            self.line_info_dict[self.scanning_func].setLine(continueLine)