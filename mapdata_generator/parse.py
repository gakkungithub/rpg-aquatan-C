import sys
import os
import clang.cindex
import subprocess
import uuid
from graphviz import Digraph
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = BASE_DIR + '/data'

def parseIndex(c_files):
    index = clang.cindex.Index.create()
    translation_units = {}
    for c_file in c_files:
        subprocess.run(['clang', '-E', c_file, '-o', 'preprocessed.c'], check=True)
        translation_units[c_file] = (index.parse('preprocessed.c', 
            args=['-I/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/usr/include','-std=c11']
        ))
    return translation_units

class ASTtoFlowChart:
    def __init__(self):
        self.dot = Digraph(comment='Control Flow')
        self.diag_list = []
        self.scanning_func = None
        self.gvar_candidate_crs = {}
        self.gvar_info = []
        self.func_info = {}
        self.loopBreaker_list = []
        self.switchBreaker_list = []
        self.findingLabel = None
        self.gotoLabel_list = {}
        self.gotoRoom_list = {}
        self.roomSizeEstimate = None
        self.roomSize_info = {}
        self.expNode_info = {}
        self.condition_move : dict[str, tuple[str, list[int | None]]] = {}
        self.switchEnd : dict[str, list[int]] = {}
        self.funcBeginLine = 1 #初期値
        self.funcNum = 0
    
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
                sys.exit(0)

    def check_cursor_error(self, cursor):
        for diag in self.diag_list:
            #エラーとなるワードは場合によってカーソルが作成されないことがあるので、同ファイルのあるワード数を超えたらにする
            if (cursor.location.file.name == diag.location.file.name and
            cursor.location.offset >= diag.location.offset-1): 
                print(f"{diag.spelling}")
                sys.exit(0)
        return True

    def write_ast(self, tu, programname):
        self.createErrorInfo(tu.diagnostics)
        for cursor in tu.cursor.get_children():
            self.check_cursor_error(cursor)
            if cursor.kind == clang.cindex.CursorKind.FUNCTION_DECL:
                self.parse_func(cursor)
                # gotoのLabelを登録する
                self.gotoRoom_list[self.scanning_func] = self.gotoLabel_list
                self.gotoLabel_list = {}
            elif cursor.kind == clang.cindex.CursorKind.VAR_DECL:
                self.gvar_candidate_crs[cursor.spelling] = cursor
            elif cursor.kind == clang.cindex.CursorKind.TYPEDEF_DECL:
                self.parse_typedef(cursor)
            elif cursor.kind == clang.cindex.CursorKind.STRUCT_DECL:
                self.parse_struct(cursor)
            elif cursor.kind == clang.cindex.CursorKind.UNION_DECL:
                self.parse_union(cursor)
            elif cursor.kind == clang.cindex.CursorKind.ENUM_DECL:
                self.parse_enum(cursor)
        output_dir = f'{DATA_DIR}/{programname}'
        os.makedirs(output_dir, exist_ok=True)
        print(self.condition_move)
        
        gv_dot_path = f'{output_dir}/{programname}'
        self.dot.render(gv_dot_path, format='dot')
        if os.path.exists(gv_dot_path):
            os.remove(gv_dot_path)

        gv_png_path = f'{output_dir}/fc_{programname}'
        self.dot.render(gv_png_path, format='png')
        if os.path.exists(gv_png_path):
            os.remove(gv_png_path)
            
    #関数の宣言or定義
    def parse_func(self, cursor):
        #引数あり/なし→COMPなし = 関数宣言, 引数あり/なし→COMPあり = 関数定義
        #引数とCOMPは同じ階層にある

        #現在のカーソルからこの関数の戻り値と引数の型を取得するかどうかは後で考える
        arg_list = []
        #ノードがなければreturnのノードはつけないようにするため、Noneを設定しておく
        nodeID = None

        for cr in cursor.get_children():
            self.check_cursor_error(cr)
            if cr.kind == clang.cindex.CursorKind.PARM_DECL:
                arg_list.append(cr.spelling)
            elif cr.kind == clang.cindex.CursorKind.COMPOUND_STMT:
                func_name = cursor.spelling
                #関数名を最初のノードの名前とする
                nodeID = self.createNode(func_name, 'ellipse')
                #関数の情報を取得し、ビットマップ描画時に取捨選択する
                self.scanning_func = func_name

                #関数の条件文の行遷移情報を取得する(これの合致で)
                self.funcBeginLine = cursor.location.line - 1

                self.func_info[func_name] = {"start": f'"{nodeID}"', "refs": set()}
                self.switchEnd[func_name] = []
                #関数の最初の部屋情報を作る
                self.roomSize_info[self.scanning_func] = {}
                self.createRoomSizeEstimate(nodeID)
                #引数のノードを作る
                for argname in arg_list:
                    argNodeID = self.createNode(argname, 'cylinder')
                    self.createEdge(nodeID, argNodeID)
                    nodeID = argNodeID
                nodeID = self.parse_comp_stmt(cr, nodeID)
                self.createRoomSizeEstimate(None)
        if nodeID:
            exitNodeID = self.createNode("", 'lpromoter')
            self.createEdge(nodeID, exitNodeID)

    #関数内や条件文内の処理
    def parse_comp_stmt(self, cursor, nodeID, edgeName=""):
        for cr in cursor.get_children():
            if self.condition_move.get(f'"{nodeID}"', None) and self.condition_move[f'"{nodeID}"'][1][-1] is None:
                self.condition_move[f'"{nodeID}"'][1][-1] = cr.location.line - self.funcBeginLine  
            nodeID = self.parse_stmt(cr, nodeID, edgeName)
            edgeName = ""
        return nodeID

    #色々な関数内や条件文内のコードの解析を行う
    def parse_stmt(self, cr, nodeID, edgeName=""):
        #ループのbreakやcontinueの情報を保管する
        def createLoopBreakerInfo():
            self.loopBreaker_list.append({"break":[], "continue":[]})
            if self.switchBreaker_list:
                self.switchBreaker_list[-1]["level"] += 1

        def downSwitchBreakerLevel():
            if self.switchBreaker_list:
                self.switchBreaker_list[-1]["level"] -= 1

        def addLoopBreaker(node, type):
            if self.switchBreaker_list and type == "break":
                if self.switchBreaker_list[-1]["level"]:
                    self.loopBreaker_list[-1][type].append(node)
                else:
                    self.switchBreaker_list[-1][type].append(node)
            else:
                self.loopBreaker_list[-1][type].append(node)

        self.check_cursor_error(cr)

        #break or continueの後なら何も行わない。ただし、ラベルを現在探索中でラベルを発見した時はラベルを見る
        if nodeID is None and cr.kind != clang.cindex.CursorKind.LABEL_STMT:
            return None
        
        #部屋のサイズを1上げる
        self.roomSizeEstimate[1] += 1

        if cr.kind == clang.cindex.CursorKind.DECL_STMT:
            for vcr in cr.get_children():
                self.check_cursor_error(vcr)
                nodeID = self.parse_var_decl(vcr, nodeID, edgeName)
        elif cr.kind == clang.cindex.CursorKind.RETURN_STMT:
            value_cursor = next(cr.get_children())
            self.check_cursor_error(value_cursor)
            returnNodeID = self.createNode(f"{cr.location.line - self.funcBeginLine}", 'lpromoter')
            self.createEdge(returnNodeID, self.get_exp(value_cursor))
            self.createEdge(nodeID, returnNodeID, edgeName)
            return None
        elif cr.kind == clang.cindex.CursorKind.IF_STMT:
            nodeID = self.parse_if_stmt(cr, nodeID, edgeName)
        elif cr.kind == clang.cindex.CursorKind.WHILE_STMT:
            createLoopBreakerInfo()
            nodeID = self.parse_while_stmt(cr, nodeID, edgeName)
            downSwitchBreakerLevel()
        elif cr.kind == clang.cindex.CursorKind.DO_STMT:
            createLoopBreakerInfo()
            nodeID = self.parse_do_stmt(cr, nodeID, edgeName)
            downSwitchBreakerLevel()
        elif cr.kind == clang.cindex.CursorKind.FOR_STMT:
            createLoopBreakerInfo()
            nodeID = self.parse_for_stmt(cr, nodeID, edgeName)
            downSwitchBreakerLevel()
        elif cr.kind == clang.cindex.CursorKind.SWITCH_STMT:
            nodeID = self.parse_switch_stmt(cr, nodeID, edgeName)
        elif cr.kind == clang.cindex.CursorKind.BREAK_STMT:
            breakNodeID = self.createNode("break")
            self.createEdge(nodeID, breakNodeID, edgeName)
            addLoopBreaker(breakNodeID, "break")
            return None
        elif cr.kind == clang.cindex.CursorKind.CONTINUE_STMT:
            continueNodeID = self.createNode("continue")
            self.createEdge(nodeID, continueNodeID, edgeName)
            addLoopBreaker(continueNodeID, "continue")
            return None
        elif cr.kind == clang.cindex.CursorKind.GOTO_STMT:
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
        elif cr.kind == clang.cindex.CursorKind.LABEL_STMT:
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
        elif cr.kind == clang.cindex.CursorKind.CALL_EXPR:
            nodeID, _ = self.parse_call_expr(cr, nodeID)
        else:
            expNodeID = self.get_exp(cr, 'rect')
            self.createEdge(nodeID, expNodeID, edgeName)
            nodeID = expNodeID
        return nodeID

    #変数の宣言
    def parse_var_decl(self, cursor, nodeID, edgeName=""):
        #この条件は配列の添字のノードを変えるためにある
        isArray = True if cursor.type.get_array_size() >= 1 else False
        #変数名を取得
        varNodeID = self.createNode(cursor.spelling, 'signature')
        self.createEdge(nodeID, varNodeID, edgeName)

        #配列
        if isArray:
            #配列の最初の要素数は必ず取得する
            arrNumNodeID = self.createNode(str(cursor.type.get_array_size()), 'box3d')

            for cr in cursor.get_children():
                self.check_cursor_error(cr)
                #配列の要素数はあえて解析を飛ばし、要素数は配列の初期値の数で取得する
                if cr.kind == clang.cindex.CursorKind.INIT_LIST_EXPR:
                    arrContNodeIDs = self.parse_arr_contents(cr.get_children())
                    for arrContNodeID in arrContNodeIDs:
                        self.createEdge(arrNumNodeID, arrContNodeID)

            self.createEdge(varNodeID, arrNumNodeID)

        #一つの変数/構造体系
        else:
            nodeID = None
            for cr in cursor.get_children():
                self.check_cursor_error(cr)
                #構造体系
                if cr.kind == clang.cindex.CursorKind.INIT_LIST_EXPR:
                    for member_cursor in cr.get_children():
                        self.check_cursor_error(member_cursor)
                        self.createEdge(nodeID, self.get_exp(member_cursor))
                #構造体の宣言でノードを作る
                elif cr.kind == clang.cindex.CursorKind.TYPE_REF:
                    nodeID = self.createNode("", 'tab')
                    self.createEdge(varNodeID, nodeID)
                #スカラー変数
                else:
                    nodeID = self.get_exp(cr)
                    self.createEdge(varNodeID, nodeID)
            #スカラー変数の初期化値が無い場合
            if nodeID is None:
                nodeID = self.createNode("", 'square')
                self.expNode_info[f'"{nodeID}"'] = ("?", [])
                self.createEdge(varNodeID, nodeID)

        return varNodeID

    #配列(多次元も含む)の要素を取得する
    def parse_arr_contents(self, cr_iter):
        arrContNodeIDs_list = []
        #要素を取得する
        for cr in cr_iter:
            self.check_cursor_error(cr)
            if cr.kind == clang.cindex.CursorKind.INIT_LIST_EXPR:
                arrContNodeIDs_list.append(self.parse_arr_contents(cr.get_children()))
            else:
                arrContNodeIDs_list.append([self.get_exp(cr)])
        
        if (maxNum := len(max(arrContNodeIDs_list, key=len))) == 1:
            return [arrContNodeID[0] for arrContNodeID in arrContNodeIDs_list]
        else:
            arrNumNodeIDs = []
            for arrContNodeIDs in arrContNodeIDs_list:
                arrNumNodeID = self.createNode(str(maxNum), 'box3d')
                contNum = len(arrContNodeIDs)
                for n in range(maxNum):
                    if contNum > n:
                        self.createEdge(arrNumNodeID, arrContNodeIDs[n])
                    else:
                        self.createEdge(arrNumNodeID, self.createNode('0', 'square'))
                arrNumNodeIDs.append(arrNumNodeID)
            return arrNumNodeIDs
        
    #必要なグローバル変数だけ取得
    def parse_gvar(self, varName):
        if (gvar_cursor := self.gvar_candidate_crs.pop(varName, None)):
            self.gvar_info.append(f'"{self.parse_var_decl(gvar_cursor, None)}"')
    
    #式(一つのノードexpNodeに内容をまとめる)
    def get_exp(self, cursor, shape='square', label=""):
        expNodeID = self.createNode(label, shape)
        references = []
        exp_terms = self.parse_exp_term(cursor, references, expNodeID)
        self.expNode_info[f'"{expNodeID}"'] = (exp_terms, references)
        return expNodeID

    def unwrap_unexposed(self, cursor):
        if cursor.kind == clang.cindex.CursorKind.UNEXPOSED_EXPR:
            cursor = next(cursor.get_children())
            self.check_cursor_error(cursor)
            if cursor.kind == clang.cindex.CursorKind.UNEXPOSED_EXPR:
                cursor = next(cursor.get_children())
                self.check_cursor_error(cursor)
        return cursor

    #式の項を一つずつ解析
    def parse_exp_term(self, cursor, references, inNodeID=None):
        cursor = self.unwrap_unexposed(cursor)

        exp_terms = ""
        #()で囲まれている場合
        if cursor.kind == clang.cindex.CursorKind.PAREN_EXPR:
            cr = next(cursor.get_children())
            self.check_cursor_error(cr)
            exp_terms = ''.join(["(", self.parse_exp_term(cr, references, inNodeID), ")"])
        #定数(関数の引数が変数であるかを確かめるために定数ノードの形は変える)
        elif cursor.kind == clang.cindex.CursorKind.INTEGER_LITERAL:
            exp_terms = f"int({next(cursor.get_tokens()).spelling})"
        elif cursor.kind == clang.cindex.CursorKind.FLOATING_LITERAL:
            exp_terms = f"float({next(cursor.get_tokens()).spelling})"
        elif (cursor.kind == clang.cindex.CursorKind.STRING_LITERAL or
              cursor.kind == clang.cindex.CursorKind.CHARACTER_LITERAL):
            exp_terms = next(cursor.get_tokens()).spelling
        #変数の呼び出し
        elif cursor.kind == clang.cindex.CursorKind.DECL_REF_EXPR:
            ref_spell = next(cursor.get_tokens()).spelling
            exp_terms = ref_spell
            self.parse_gvar(ref_spell)
            references.append(ref_spell)
        #配列
        elif cursor.kind == clang.cindex.CursorKind.ARRAY_SUBSCRIPT_EXPR:
            name_cursor, index_cursor = [cr for cr in list(cursor.get_children()) if self.check_cursor_error(cr)]
            exp_terms = ''.join([name_cursor.spelling, "[", self.parse_exp_term(index_cursor, references, inNodeID), "]"])
        #関数
        elif cursor.kind == clang.cindex.CursorKind.CALL_EXPR:
            exp_terms, refspell = self.parse_call_expr(cursor, inNodeID)
            references.append(refspell)
        #一項条件式
        elif cursor.kind == clang.cindex.CursorKind.UNARY_OPERATOR:
            #(++aでいうa)
            idf_cursor = next(cursor.get_children())
            self.check_cursor_error(idf_cursor)
            operator = next(cursor.get_tokens())
            #前置(++a)
            if operator.location.offset < idf_cursor.location.offset:
                exp_terms = ''.join([operator.spelling, self.parse_exp_term(idf_cursor, references, inNodeID)])
            #後置(a++)
            else:
                operator = next(reversed(list(cursor.get_tokens())))
                exp_terms = ''.join([self.parse_exp_term(idf_cursor, references, inNodeID), operator.spelling])
        #二項条件式と複合代入演算子("+="など)
        elif (cursor.kind == clang.cindex.CursorKind.BINARY_OPERATOR or
            cursor.kind == clang.cindex.CursorKind.COMPOUND_ASSIGNMENT_OPERATOR):
            exps = [cr for cr in list(cursor.get_children()) if self.check_cursor_error(cr)]
            first_end = exps[0].extent.end.offset
            operator_spell = ""
            for token in cursor.get_tokens():
                if first_end <= token.location.offset:
                    operator_spell = token.spelling
                    break
            exp_terms = ''.join([self.parse_exp_term(exps[0], references, inNodeID), operator_spell, self.parse_exp_term(exps[1], references, inNodeID)])
        #三項条件式(c? a : b)
        elif cursor.kind == clang.cindex.CursorKind.CONDITIONAL_OPERATOR:
            exps = [cr for cr in list(cursor.get_children()) if self.check_cursor_error(cr)]
            #まず、条件文を解析し、a : b の aかbを解析する
            exp_terms = ''.join([self.parse_exp_term(exps[0], references, inNodeID), " ? ", self.parse_exp_term(exps[1], references, inNodeID), " : ", self.parse_exp_term(exps[2], references, inNodeID)])
        #キャスト型
        elif cursor.kind == clang.cindex.CursorKind.CSTYLE_CAST_EXPR:
            cr = next(cursor.get_children())
            self.check_cursor_error(cr)
            exp_terms = ''.join(["(", cr.type.spelling, ") ", self.parse_exp_term(cr, references, inNodeID)])
        return exp_terms

    #関数の呼び出し(変数と関数の呼び出しは分ける)
    def parse_call_expr(self, cursor, inNodeID):
        children = list(cursor.get_children())
        if not children:
            raise ValueError("CALL_EXPR に子ノードがありません")

        # --- 関数名ノードの処理 ---
        func_cursor = self.unwrap_unexposed(children[0])
        self.check_cursor_error(func_cursor)

        ref_spell = next(func_cursor.get_tokens()).spelling
        self.func_info[self.scanning_func]["refs"].add(ref_spell)
        ref_spell_w_id = f"{ref_spell} {self.funcNum}"

        funcNodeID = self.createNode(ref_spell_w_id, 'oval')
        self.funcNum += 1

        # 呼び出し元とのエッジ
        self.createEdge(inNodeID, funcNodeID)

        # --- 引数ノードとのエッジ作成 ---
        for arg_cursor in children[1:]:
            self.check_cursor_error(arg_cursor)
            arg_node_id = self.get_exp(arg_cursor, 'egg')
            self.createEdge(funcNodeID, arg_node_id)

        return funcNodeID, ref_spell_w_id


    #typedefの解析
    def parse_typedef(self, cursor):
        print(f"{cursor.underlying_typedef_type.spelling} {cursor.spelling}")

    #構造体の解析(フローチャートには含めないが、アイテムには必要なので解析)
    def parse_struct(self, cursor):
        print(f"struct {cursor.spelling}")
        for cr in cursor.get_children():
            self.check_cursor_error(cr)
            print(f"    {cr.type.spelling} {cr.spelling}")

    #共用体の解析(フローチャートには含めないが、アイテムには必要なので解析)
    def parse_union(self, cursor):
        print(f"union {cursor.spelling}")
        for cr in cursor.get_children():
            self.check_cursor_error(cr)
            print(f"    {cr.type.spelling} {cr.spelling}")
    
    #列挙型の解析(フローチャートには含めないが、アイテムには必要なので解析)
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

    #分岐で新たな部屋情報を登録する
    def createRoomSizeEstimate(self, nodeID):
        if self.roomSizeEstimate:
            #部屋情報が完成したらroomSize辞書に移す
            self.roomSize_info[self.scanning_func][f'"{self.roomSizeEstimate[0]}"'] = self.roomSizeEstimate[1]
        #gotoのラベルを探っている最中は登録しない
        if nodeID:
            #部屋のサイズの初期値は9 (5*4などの部屋ができる)
            self.roomSizeEstimate = [nodeID, 9]

    #if文
    #現在ノードに全ての子ノードをくっつける。出口ノードを作成する
    #子ノード(現在のノードの条件が真/偽それぞれの場合の遷移先)を引数に関数を再帰する
    #その関数の戻り値は条件先の最後の処理を示すノードとし、この戻り値→出口ノードとなる矢印をつける
    #リファクタリング後はchildrenがない場合nodeIDを返すことになっている。これで支障をきたす場合、少し変えることを考える
    def parse_if_stmt(self, cursor, nodeID, edgeName=""):
        termNodeIDs = self.parse_if_branch(cursor, nodeID, edgeName)
        endNodeID = self.createNode("", 'circle')
        self.createRoomSizeEstimate(endNodeID)

        for termNodeID in termNodeIDs:
            # self.condition_move[f'"{termNodeID}"'][1][-1] = 
            self.createEdge(termNodeID, endNodeID)

        return endNodeID

    def parse_if_branch(self, cursor, nodeID, edgeName="", line_track: list[int] = []):
        def parse_if_branch_start(cursor, parentNodeID, line_track: list[int]):
            """if / else の本体（複合文または単一文）を処理する"""
            children = list(cursor.get_children())
            if cursor.kind == clang.cindex.CursorKind.COMPOUND_STMT:
                if len(children):
                    self.condition_move[f'"{parentNodeID}"'] = ('if', line_track + [children[0].location.line - self.funcBeginLine])
                else:
                    self.condition_move[f'"{parentNodeID}"'] = ('if', line_track + [line_track[-1]])
                return self.parse_comp_stmt(cursor, parentNodeID)
            else:
                self.condition_move[f'"{parentNodeID}"'] = ('if', line_track + [cursor.location.line - self.funcBeginLine])
                return self.parse_stmt(cursor, parentNodeID)
        # くっつけるノードをどんどん追加して返す。ifしかなくてもfalseのルートにノードを作ってtrue, falseの二つを追加して返す
        children = list(cursor.get_children())
        if not children:
            sys.exit(0)

        # --- 条件式処理 ---
        cond_cursor = children[0]
        self.check_cursor_error(cond_cursor)
        condNodeID = self.get_exp(cond_cursor, 'diamond')
        self.createEdge(nodeID, condNodeID, edgeName)

        line_track.append(cond_cursor.location.line - self.funcBeginLine)

        # --- then節の処理 ---
        then_cursor = children[1]
        self.check_cursor_error(then_cursor)

        trueNodeID = self.createNode("", 'circle')

        self.createEdge(condNodeID, trueNodeID, "True")
        self.createRoomSizeEstimate(trueNodeID)
        then_end = parse_if_branch_start(then_cursor, trueNodeID, line_track)

        # --- trueの後の処理の終点を作る (後でif構文の終点をまとめる) ---
        trueEndNodeID = self.createNode("", 'terminator')
        end_line = then_cursor.extent.end.line
        self.condition_move[f'"{trueEndNodeID}"'] = ('ifEnd', [end_line - self.funcBeginLine])
        self.createEdge(then_end, trueEndNodeID)

        # --- else節の処理（ある場合） ---
        if len(children) > 2:
            else_cursor = children[2]
            self.check_cursor_error(else_cursor)

            if else_cursor.kind == clang.cindex.CursorKind.IF_STMT:
                # else if の再帰処理
                nodeIDs = [trueEndNodeID] + self.parse_if_branch(else_cursor, condNodeID, edgeName="False", line_track=line_track)
            else:
                # else
                falseNodeID = self.createNode("", 'circle')
                self.createEdge(condNodeID, falseNodeID, "False")
                self.createRoomSizeEstimate(falseNodeID)
                nodeID = parse_if_branch_start(else_cursor, falseNodeID, line_track + [else_cursor.location.line - self.funcBeginLine]) 
                falseEndNodeID = self.createNode("", 'terminator')
                end_line = else_cursor.extent.end.line
                self.condition_move[f'"{falseEndNodeID}"'] = ('ifEnd', [end_line - self.funcBeginLine])
                self.createEdge(nodeID, falseEndNodeID)
                nodeIDs = [trueEndNodeID, falseEndNodeID]
        else:
            # elseがなくても終点を作る
            falseEndNodeID = self.createNode("", 'terminator')
            self.condition_move[f'"{falseEndNodeID}"'] = ('ifEnd', [cond_cursor.location.line - self.funcBeginLine])
            self.createEdge(condNodeID, falseEndNodeID, "False")
            nodeIDs = [trueEndNodeID, falseEndNodeID]
        
        return nodeIDs
    
    #while文
    #子ノード(真の条件先の最初の処理)を現在のノードに付ける
    #子ノードを引数とする関数を呼び出し、真の場合の最後の処理をこの関数の戻り値とする
    #その戻り値を現在ノードに付ける
    #現在のノードは次のノードに付ける
    def parse_while_stmt(self, cursor, nodeID, edgeName=""):
        children = list(cursor.get_children())
        if not children:
            return nodeID

        # --- 条件処理 ---
        cond_cursor = children[0]
        self.check_cursor_error(cond_cursor)
        condNodeID = self.get_exp(cond_cursor, 'pentagon', 'while')
        self.createRoomSizeEstimate(condNodeID)

        self.createEdge(nodeID, condNodeID, edgeName)

        # --- 条件True時の処理ノード ---
        trueNodeID = self.createNode("", 'circle')
        self.condition_move[f'"{condNodeID}"'] = ('whileIn', [cond_cursor.location.line - self.funcBeginLine])
        
        # 次のノードがwhileのtrueかを確認するためにエッジにラベルをつけておく(falseも同じ)
        self.createEdge(condNodeID, trueNodeID, "true")
        self.createRoomSizeEstimate(trueNodeID)

        # --- 本体処理 ---
        body_end = trueNodeID
        for cr in children[1:]:
            self.check_cursor_error(cr)
            if cr.kind == clang.cindex.CursorKind.COMPOUND_STMT:
                cr_true = list(cr.get_children())
                if len(cr_true):
                    self.condition_move[f'"{trueNodeID}"'] = ('whileTrue', [cond_cursor.location.line - self.funcBeginLine, cr_true[0].location.line - self.funcBeginLine])
                else:
                    self.condition_move[f'"{trueNodeID}"'] = ('whileTrue', [cond_cursor.location.line - self.funcBeginLine, cond_cursor.location.line - self.funcBeginLine])
                body_end = self.parse_comp_stmt(cr, body_end)
            else:
                self.condition_move[f'"{trueNodeID}"'] = ('whileTrue', [cond_cursor.location.line - self.funcBeginLine, cr.location.line - self.funcBeginLine])
                body_end = self.parse_stmt(cr, body_end)

        # --- ループを閉じる処理 ---
        loop_back_node = self.createNode("", 'parallelogram')  # 再評価への中継点

        self.createEdge(body_end, loop_back_node)
        self.createEdge(loop_back_node, condNodeID)

        # --- 条件False時の処理（脱出） ---
        endNodeID = self.createNode("", 'doublecircle')
        self.createEdge(condNodeID, endNodeID, "false")
        self.createRoomSizeEstimate(endNodeID)
        self.condition_move[f'"{endNodeID}"'] = ('whileFalse', [cond_cursor.location.line - self.funcBeginLine, None])

        return endNodeID

    #do-while文
    #まずは最初の処理を示す子ノードと現在ノードを接続する
    #Doノードの子ノードはCOMPOUNDと条件部しかなく、条件部は2つ目に読まれる
    #そこで読み込まれたノードを先頭ノードと次ノードをくっつける
    def parse_do_stmt(self, cursor, nodeID, edgeName=""):
        startNodeID = self.createNode("", 'circle')
        #ここで部屋情報を作る
        self.createRoomSizeEstimate(startNodeID)
        
        endNodeID = self.createNode("", 'circle')

        self.createEdge(nodeID, startNodeID)

        for cr in cursor.get_children():
            self.check_cursor_error(cr)
            if cr.kind == clang.cindex.CursorKind.COMPOUND_STMT:
                cr_in = list(cr.get_children())
                if len(cr_in):
                    self.condition_move[f'"{startNodeID}"'] = ('doWhileIn', [cursor.location.line - self.funcBeginLine, cr_in[0].location.line - self.funcBeginLine])
                    start_cr = cr_in[0]
                else:
                    self.condition_move[f'"{startNodeID}"'] = ('doWhileIn', [cursor.location.line - self.funcBeginLine, cursor.location.line - self.funcBeginLine])
                    start_cr = cursor
                nodeID = self.parse_comp_stmt(cr, startNodeID)
            else:
                if nodeID is None:
                    return None
                condNodeID = self.get_exp(cr, 'diamond')
                self.condition_move[f'"{condNodeID}"'] = ('doWhileTrue', [cr.location.line - self.funcBeginLine, start_cr.location.line - self.funcBeginLine])
                self.createEdgeForLoop(endNodeID, condNodeID)
                self.createEdge(nodeID, condNodeID)
                self.createEdge(condNodeID, startNodeID, "True")
                self.createEdge(condNodeID, endNodeID, "False")
        self.condition_move[f'"{endNodeID}"'] = ('doWhileFalse', [cr.location.line - self.funcBeginLine, None])
        #ここでdo_whileを抜けた後の部屋情報を作る
        self.createRoomSizeEstimate(endNodeID)
        return endNodeID

    #for文
    #まずは式1に対するノードを作成(for(式1; 式2; 式3))
    #あとは、ほぼWhileと同じ。式2の子ノード(真である場合の遷移先)の最後の処理が式3であることに注意
    def parse_for_stmt(self, cursor, nodeID, edgeName=""):
        #for(INIT; COND; CHANGE)
        #cursor.get_childrenの最後の要素は必ず処理部の最初のカーソルであるから、それ以外のカーソルが式1~式3の候補となる。
        initNodeID = None
        condNodeID = None
        changeNodeID = None
        changeExpr_cursor = None
        endNodeID = self.createNode("", 'doublecircle')
        *expr_cursors, exec_cursor = list(cursor.get_children())
        semi_offset = [token.location.offset for token in list(cursor.get_tokens()) if token.spelling == ';'][:2]

        for cr in expr_cursors:
            self.check_cursor_error(cr)
            if cr.location.offset < semi_offset[0]:
                initNodeID = self.get_exp(cr, 'invhouse')
                self.createEdge(nodeID, initNodeID, edgeName)
                edgeName = ""
            elif semi_offset[0] < cr.location.offset < semi_offset[1]:
                condNodeID = self.get_exp(cr, 'pentagon', 'for')
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
                
        self.condition_move[f'"{condNodeID}"'] = ('forIn', [cursor.location.line - self.funcBeginLine])
        self.check_cursor_error(exec_cursor)

        trueNodeID = self.createNode("", 'circle')
        self.createEdge(condNodeID, trueNodeID, "True")
        #ここで部屋情報を作る
        self.createRoomSizeEstimate(trueNodeID)

        if exec_cursor.kind == clang.cindex.CursorKind.COMPOUND_STMT:
            cr_true = list(exec_cursor.get_children())
            if len(cr_true):
                self.condition_move[f'"{trueNodeID}"'] = ('forTrue', [cursor.location.line - self.funcBeginLine, cr_true[0].location.line - self.funcBeginLine])
            else:
                self.condition_move[f'"{trueNodeID}"'] = ('forTrue', [cursor.location.line - self.funcBeginLine, cursor.location.line - self.funcBeginLine])
            nodeID = self.parse_comp_stmt(exec_cursor, trueNodeID)
        else:
            self.condition_move[f'"{trueNodeID}"'] = ('forTrue', [cursor.location.line - self.funcBeginLine, exec_cursor.location.line - self.funcBeginLine])
            nodeID = self.parse_stmt(exec_cursor, trueNodeID)

        #changeノードがある条件
        if self.loopBreaker_list[-1]["continue"] or nodeID:
            if changeExpr_cursor:
                changeNodeID = self.get_exp(changeExpr_cursor, shape='parallelogram')
            else:
                changeNodeID = self.createNode("", shape='parallelogram')

        self.createEdge(nodeID, changeNodeID)
        self.createEdge(changeNodeID, condNodeID)
        self.createEdgeForLoop(endNodeID, changeNodeID)
        
        self.createEdge(condNodeID, endNodeID, "False")
        #ここでforを抜けた後の部屋情報を作る
        self.createRoomSizeEstimate(endNodeID)

        self.condition_move[f'"{endNodeID}"'] = ('forFalse', [cursor.location.line - self.funcBeginLine, None])
        
        return endNodeID

    #switch文
    def parse_switch_stmt(self, cursor, nodeID, edgeName=""):
        #caseはbreakだけ適応させる
        #levelが0ならbreakノードを追加する。levelは繰り返し文が入ると1上がる。
        #それ以外ならloopBreaker_listに追加する。
        def createSwitchBreakerInfo():
            self.switchBreaker_list.append({"level":0, "break":[]})

        #switchのcaseのbreakノードを追加する。
        def createSwitchBreakerEdge(endNodeID):
            switchBreaker = self.switchBreaker_list.pop()
            break_list = switchBreaker["break"]
            for breakNodeID in break_list:
                self.createEdge(breakNodeID, endNodeID)

        cond_cursor, comp_exec_cursor = [cr for cr in cursor.get_children() if self.check_cursor_error(cr)]

        switchRoomSizeEstimate = self.roomSizeEstimate
        self.roomSizeEstimate = None

        #switchの構造はswitch(A)のようにAは必ず必要
        condNodeID = self.get_exp(cond_cursor, 'diamond')
        self.createEdge(nodeID, condNodeID, edgeName)

        createSwitchBreakerInfo()

        #switch(A){ B }の場合
        endNodeID = self.createNode("", 'doublecircle')
        last_line = None
        if comp_exec_cursor.kind == clang.cindex.CursorKind.COMPOUND_STMT:
            isNotBreak = False
            for cr in comp_exec_cursor.get_children():
                self.check_cursor_error(cr)
                if cr.kind == clang.cindex.CursorKind.CASE_STMT:
                    if last_line:
                        self.switchEnd[self.scanning_func].append(last_line)
                    while cr.kind == clang.cindex.CursorKind.CASE_STMT:
                        caseValue_cursor, cr = [case_cr for case_cr in cr.get_children() if self.check_cursor_error(case_cr)]
                        caseNodeID = self.get_exp(caseValue_cursor, 'invtriangle')
                        self.createEdge(condNodeID, caseNodeID)
                        if isNotBreak:
                            self.createEdge(nodeID, caseNodeID)
                        isNotBreak = True

                    #switchの元の部屋のサイズを+1する
                    switchRoomSizeEstimate[1] += 1
                    #ここで一つのcaseの部屋情報を作る
                    self.createRoomSizeEstimate(caseNodeID)
                    self.condition_move[f'"{caseNodeID}"'] = ('switchCase', [comp_exec_cursor.location.line - self.funcBeginLine, cr.location.line - self.funcBeginLine])

                    if cr.kind == clang.cindex.CursorKind.COMPOUND_STMT:
                        cr_true = list(exec_cursor.get_children())
                        if len(cr_true):
                            last_line = cr_true[0].location.line - self.funcBeginLine
                        else:
                            last_line = cr.location.line - self.funcBeginLine
                        nodeID = self.parse_comp_stmt(cr, caseNodeID)
                    else:
                        last_line = cr.location.line - self.funcBeginLine
                        nodeID = self.parse_stmt(cr, caseNodeID)

                elif cr.kind == clang.cindex.CursorKind.DEFAULT_STMT:
                    if last_line:
                        self.switchEnd[self.scanning_func].append(last_line)
                    defaultNodeID = self.createNode("default", 'invtriangle')
                    self.createEdge(condNodeID, defaultNodeID)
                    if isNotBreak:
                        self.createEdge(nodeID, defaultNodeID)
                    default_cursor = next(cr.get_children())
                    self.check_cursor_error(default_cursor)

                    #switchの元の部屋のサイズを+1する
                    switchRoomSizeEstimate[1] += 1
                    #ここでdefaultの部屋情報を作る
                    self.createRoomSizeEstimate(defaultNodeID)
                    self.condition_move[f'"{defaultNodeID}"'] = ('switchCase', [cond_cursor.location.line - self.funcBeginLine, cr.location.line - self.funcBeginLine + 1])
                    nodeID = self.parse_stmt(default_cursor, defaultNodeID)
                    last_line = default_cursor.location.line - self.funcBeginLine
                    isNotBreak = True
                elif cr.kind == clang.cindex.CursorKind.BREAK_STMT:
                    nodeID = self.parse_stmt(cr, nodeID)
                    last_line = cr.location.line - self.funcBeginLine
                    isNotBreak = False
                    #caseラベルと実行文の処理の階層は最初の実行文以外同じ
                # 一つのcaseに複数の処理がある場合はくっつける
                else:
                    if caseNodeID or defaultNodeID:
                        nodeID = self.parse_stmt(cr, nodeID)
                        last_line = cr.location.line - self.funcBeginLine
            self.createEdge(nodeID, endNodeID)

        #switch(A) Bの時、Bが case C: D なら A == C でDが行われる。
        elif comp_exec_cursor.kind == clang.cindex.CursorKind.CASE_STMT:
            caseValue_cursor, exec_cursor = [cr for cr in comp_exec_cursor.get_children() if self.check_cursor_error(cr)]
            caseNodeID = self.get_exp(caseValue_cursor, 'invtriangle')
            self.createEdge(condNodeID, caseNodeID)
            createSwitchBreakerInfo()

            #switchの元の部屋のサイズを+1する
            switchRoomSizeEstimate[1] += 1
            #ここでDのための部屋情報を作る
            self.createRoomSizeEstimate(caseNodeID)
            self.condition_move[f'"{caseNodeID}"'] = ('switchCase', [cr.location.line - self.funcBeginLine, cr.location.line - self.funcBeginLine + 1])
            
            nodeID = self.parse_stmt(exec_cursor, caseNodeID)
            last_line = exec_cursor.location.line - self.funcBeginLine
            self.switchEnd[self.scanning_func].append(exec_cursor.location.line - self.funcBeginLine)
            self.createEdge(nodeID, endNodeID)
        #しかし、B D なら D は無視される。Dは複数行でも良い。

        if defaultNodeID is None:
            self.createEdge(condNodeID, endNodeID)
        createSwitchBreakerEdge(endNodeID)
        #ここでswitchを抜けた後の部屋情報を作る
        self.createRoomSizeEstimate(endNodeID)
        self.condition_move[f'"{endNodeID}"'] = ('switchEnd', [None, None])

        self.switchEnd[self.scanning_func].append(last_line)
        self.roomSize_info[self.scanning_func][f'"{switchRoomSizeEstimate[0]}"'] = switchRoomSizeEstimate[1]
        return endNodeID

    #ループ処理のノードをくっつけていく
    def createEdgeForLoop(self, breakToNodeID, continueToNodeID):
        loopBreaker = self.loopBreaker_list.pop()
        break_list = loopBreaker["break"]
        continue_list = loopBreaker["continue"]
        for breakNodeID in break_list:
            self.createEdge(breakNodeID, breakToNodeID)
        for continueNodeID in continue_list:
            self.createEdge(continueNodeID, continueToNodeID)

    