import sys
import os
import clang.cindex
import subprocess
import uuid
from graphviz import Digraph

def parseIndex(c_files):
    index = clang.cindex.Index.create()
    translation_units = {}
    for c_file in c_files:
        subprocess.run(['clang', '-E', c_file, '-o', 'preprocessed.c'], check=True)
        translation_units[c_file[:-2]] = index.parse('preprocessed.c', 
            args=['-I/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/usr/include','-std=c11']
        )
    print(translation_units)
    return translation_units

class ASTtoFlowChart:
    def __init__(self):
        self.dot = None
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
            if "expected '}'" in diag.spelling or "expected ';'" in diag.spelling:
                print(f"{diag.spelling}, {diag.location.offset}")
                sys.exit(0)
            print(f"{diag.spelling}, {diag.location.offset}")

    def check_cursor_error(self, cursor):
        for diag in self.diag_list:
            #エラーとなるワードは場合によってカーソルが作成されないことがあるので、同ファイルのあるワード数を超えたらにする
            if (cursor.location.file.name == diag.location.file.name and
            cursor.location.offset >= diag.location.offset-1): 
                print(f"{diag.spelling}")
                sys.exit(0)
        return True

    def write_ast_tree(self, cursor, indent=0):
        # if cursor.kind == clang.cindex.CursorKind.FUNCTION_DECL:
        #     print(cursor.type.spelling)
        # if cursor.kind == clang.cindex.CursorKind.VAR_DECL:
        #     print(f"    {cursor.type.get_array_size()}")
        print(f"{cursor.kind}, {cursor.spelling} {indent}")

        #子ノードを再帰的に辿る
        for child in cursor.get_children():
            self.write_ast_tree(child, indent + 1)

    def write_ast(self, tu, tu_bname):
        self.createErrorInfo(tu.diagnostics)
        self.dot = Digraph(comment='Control Flow')
        for cursor in tu.cursor.get_children():
            self.check_cursor_error(cursor)
            if cursor.kind == clang.cindex.CursorKind.FUNCTION_DECL:
                self.parse_func(cursor)
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
        os.makedirs(f'flowcharts/{tu_bname}', exist_ok=True)
        self.dot.render(f'flowcharts/{tu_bname}/{tu_bname}', format='dot')
        self.dot.render(f'flowcharts/{tu_bname}/{tu_bname}', format='png', view=True)
        return tu_bname

    #関数の宣言or定義
    def parse_func(self, cursor):
        #引数あり/なし→COMPなし = 関数宣言, 引数あり/なし→COMPあり = 関数定義
        #引数とCOMPは同じ階層にある
        #現在のカーソルからこの関数の戻り値と引数の型を取得するかどうかは後で考える
        arg_list = []
        nodeID = None
        func_name = cursor.spelling
        for cr in cursor.get_children():
            self.check_cursor_error(cr)
            if cr.kind == clang.cindex.CursorKind.PARM_DECL:
                arg_list.append(cr.spelling)
            elif cr.kind == clang.cindex.CursorKind.COMPOUND_STMT:
                #関数名を最初のノードの名前とする
                nodeID = self.createNode(func_name, 'ellipse')
                #関数の情報を取得し、ビットマップ描画時に取捨選択する
                self.scanning_func = func_name
                self.func_info[func_name] = {"start": f'"{nodeID}"', "refs": set()}
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
    
    #関数内や条件文の処理
    def parse_comp_stmt(self, cursor, nodeID, edgeName=""):
        for cr in cursor.get_children():
            nodeID = self.parse_stmt(cr, nodeID, edgeName)
            edgeName = ""
        return nodeID

    #色々な関数内や条件文内のコードの解析を行う
    def parse_stmt(self, cr, nodeID, edgeName=""):
        #break or continueの後なら何も行わない。
        self.check_cursor_error(cr)
        if (nodeID is None and 
             cr.kind != clang.cindex.CursorKind.LABEL_STMT):
            return None
        self.addSizeEstimate()
        if cr.kind == clang.cindex.CursorKind.DECL_STMT:
            for vcr in cr.get_children():
                self.check_cursor_error(vcr)
                nodeID = self.parse_var_decl(vcr, nodeID, edgeName)
        elif cr.kind == clang.cindex.CursorKind.RETURN_STMT:
            value_cursor = next(cr.get_children())
            self.check_cursor_error(value_cursor)
            returnNodeID = self.createNode("return", 'lpromoter')
            self.createEdge(returnNodeID, self.get_exp(value_cursor))
            self.createEdge(nodeID, returnNodeID, edgeName)
            return None
        elif cr.kind == clang.cindex.CursorKind.IF_STMT:
            nodeID = self.parse_if_stmt(cr, nodeID, edgeName)
        elif cr.kind == clang.cindex.CursorKind.WHILE_STMT:
            self.createLoopBreakerInfo()
            nodeID = self.parse_while_stmt(cr, nodeID, edgeName)
            self.downSwitchBreakerLevel()
        elif cr.kind == clang.cindex.CursorKind.DO_STMT:
            self.createLoopBreakerInfo()
            nodeID = self.parse_do_stmt(cr, nodeID, edgeName)
            self.downSwitchBreakerLevel()
        elif cr.kind == clang.cindex.CursorKind.FOR_STMT:
            self.createLoopBreakerInfo()
            nodeID = self.parse_for_stmt(cr, nodeID, edgeName)
            self.downSwitchBreakerLevel()
        elif cr.kind == clang.cindex.CursorKind.SWITCH_STMT:
            nodeID = self.parse_switch_stmt(cr, nodeID, edgeName)
        elif cr.kind == clang.cindex.CursorKind.BREAK_STMT:
            breakNodeID = self.createNode("break")
            self.createEdge(nodeID, breakNodeID, edgeName)
            self.addLoopBreaker(breakNodeID, "break")
            return None
        elif cr.kind == clang.cindex.CursorKind.CONTINUE_STMT:
            continueNodeID = self.createNode("continue")
            self.createEdge(nodeID, continueNodeID, edgeName)
            self.addLoopBreaker(continueNodeID, "continue")
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
            nodeID, refsepll = self.parse_call_exprEdit(cr, nodeID)
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
    def get_exp(self, cursor, shape='square'):
        expNodeID = self.createNode("", shape)
        references = []
        exp_terms = self.parse_expEdit(cursor, references, expNodeID)
        self.expNode_info[f'"{expNodeID}"'] = (exp_terms, references)
        return expNodeID

    #式の項を一つずつ解析
    def parse_expEdit(self, cursor, references, inNodeID=None):
        if cursor.kind == clang.cindex.CursorKind.UNEXPOSED_EXPR:
            cursor = next(cursor.get_children())
            self.check_cursor_error(cursor)
            if cursor.kind == clang.cindex.CursorKind.UNEXPOSED_EXPR:
                cursor = next(cursor.get_children())
                self.check_cursor_error(cursor)

        exp_terms = ""
        #()で囲まれている場合
        if cursor.kind == clang.cindex.CursorKind.PAREN_EXPR:
            cr = next(cursor.get_children())
            self.check_cursor_error(cr)
            exp_terms = ''.join(["(", self.parse_expEdit(cr, references, inNodeID), ")"])
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
            exp_terms = ''.join([name_cursor.spelling, "[", self.parse_expEdit(index_cursor, references, inNodeID), "]"])
        #関数
        elif cursor.kind == clang.cindex.CursorKind.CALL_EXPR:
            exp_terms, refspell = self.parse_call_exprEdit(cursor, inNodeID)
            references.append(refspell)
        #一項条件式
        elif cursor.kind == clang.cindex.CursorKind.UNARY_OPERATOR:
            #(++aでいうa)
            idf_cursor = next(cursor.get_children())
            self.check_cursor_error(idf_cursor)
            operator = next(cursor.get_tokens())
            #前置(++a)
            if operator.location.offset < idf_cursor.location.offset:
                exp_terms = ''.join([operator.spelling, self.parse_expEdit(idf_cursor, references, inNodeID)])
            #後置(a++)
            else:
                operator = next(reversed(list(cursor.get_tokens())))
                exp_terms = ''.join([self.parse_expEdit(idf_cursor, references, inNodeID), operator.spelling])
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
            exp_terms = ''.join([self.parse_expEdit(exps[0], references, inNodeID), operator_spell, self.parse_expEdit(exps[1], references, inNodeID)])
        #三項条件式(c? a : b)
        elif cursor.kind == clang.cindex.CursorKind.CONDITIONAL_OPERATOR:
            exps = [cr for cr in list(cursor.get_children()) if self.check_cursor_error(cr)]
            #まず、条件文を解析し、a : b の aかbを解析する
            exp_terms = ''.join([self.parse_expEdit(exps[0], references, inNodeID), " ? ", self.parse_expEdit(exps[1], references, inNodeID), " : ", self.parse_expEdit(exps[2], references, inNodeID)])
        #キャスト型
        elif cursor.kind == clang.cindex.CursorKind.CSTYLE_CAST_EXPR:
            cr = next(cursor.get_children())
            self.check_cursor_error(cr)
            exp_terms = ''.join(["(", cr.type.spelling, ") ", self.parse_expEdit(cr, references, inNodeID)])
        return exp_terms

    #関数の呼び出し(変数と関数の呼び出しは分ける)
    def parse_call_exprEdit(self, cursor, inNodeID):
        funcNodeID = None
        for cr in cursor.get_children():
            self.check_cursor_error(cr)
            if funcNodeID:
                self.createEdge(funcNodeID, self.get_exp(cr, 'egg'))
            else:
                if cr.kind == clang.cindex.CursorKind.UNEXPOSED_EXPR:
                    cr = next(cr.get_children())
                    self.check_cursor_error(cursor)
                    if cr.kind == clang.cindex.CursorKind.UNEXPOSED_EXPR:
                        cr = next(cr.get_children())
                        self.check_cursor_error(cr)
                ref_spell = next(cr.get_tokens()).spelling
                self.func_info[self.scanning_func]["refs"].add(ref_spell)
                ref_spell_w_id = f"{ref_spell} {self.funcNum}"
                funcNodeID = self.createNode(ref_spell_w_id, 'oval')
                self.funcNum += 1
        self.createEdge(inNodeID, funcNodeID)
        return funcNodeID, ref_spell_w_id
    
    #式の項を一つずつ解析
    def parse_exp(self, cursor, inNodeID=None):
        if cursor.kind == clang.cindex.CursorKind.UNEXPOSED_EXPR:
            cursor = next(cursor.get_children())
            self.check_cursor_error(cursor)
            if cursor.kind == clang.cindex.CursorKind.UNEXPOSED_EXPR:
                cursor = next(cursor.get_children())
                self.check_cursor_error(cursor)

        exp_terms = []
        #()で囲まれている場合
        if cursor.kind == clang.cindex.CursorKind.PAREN_EXPR:
            cr = next(cursor.get_children())
            self.check_cursor_error(cr)
            exp_terms = self.parse_exp(cr, inNodeID)
        #定数(関数の引数が変数であるかを確かめるために定数ノードの形は変える)
        elif cursor.kind == clang.cindex.CursorKind.INTEGER_LITERAL:
            exp_terms = ['int', next(cursor.get_tokens()).spelling]
        elif cursor.kind == clang.cindex.CursorKind.FLOATING_LITERAL:
            exp_terms = ['float', next(cursor.get_tokens()).spelling]
        elif cursor.kind == clang.cindex.CursorKind.STRING_LITERAL:
            exp_terms = ['string', next(cursor.get_tokens()).spelling]
            print(exp_terms)
        elif cursor.kind == clang.cindex.CursorKind.CHARACTER_LITERAL:
            exp_terms = ['chara', next(cursor.get_tokens()).spelling]
            print(exp_terms)
        #変数の呼び出し
        elif cursor.kind == clang.cindex.CursorKind.DECL_REF_EXPR:
            ref_spell = next(cursor.get_tokens()).spelling
            exp_terms.append(ref_spell)
            self.parse_gvar(ref_spell)
        #配列
        elif cursor.kind == clang.cindex.CursorKind.ARRAY_SUBSCRIPT_EXPR:
            name_cursor, index_cursor = [cr for cr in list(cursor.get_children()) if self.check_cursor_error(cr)]
            exp_terms = [name_cursor.spelling, '[]']
            exp_terms.extend(self.parse_exp(index_cursor, inNodeID))
        #関数
        elif cursor.kind == clang.cindex.CursorKind.CALL_EXPR:
            exp_terms.append(self.parse_call_expr(cursor, inNodeID))
        #一項条件式
        elif cursor.kind == clang.cindex.CursorKind.UNARY_OPERATOR:
            #(++aでいうa)
            idf_cursor = next(cursor.get_children())
            self.check_cursor_error(idf_cursor)
            operator = next(cursor.get_tokens())
            #前置(++a)
            if operator.location.offset < idf_cursor.location.offset:
                exp_terms = self.parse_exp(idf_cursor, inNodeID)
                exp_terms.append('@<')
                exp_terms.append(operator.spelling)
            #後置(a++)
            else:
                operator = next(reversed(list(cursor.get_tokens())))
                exp_terms = self.parse_exp(idf_cursor, inNodeID)
                exp_terms.append('@>')
                exp_terms.append(operator.spelling)
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
            for exp in exps:
                exp_terms.extend(self.parse_exp(exp, inNodeID))
            exp_terms.append(operator_spell)
        #三項条件式(c? a : b)
        elif cursor.kind == clang.cindex.CursorKind.CONDITIONAL_OPERATOR:
            exps = [cr for cr in list(cursor.get_children()) if self.check_cursor_error(cr)]
            #まず、条件文を解析し、a : b の aかbを解析する
            exp_terms = [*self.parse_exp(exps[0], inNodeID), *self.parse_exp(exps[1], inNodeID), *self.parse_exp(exps[2], inNodeID), "?", ":"]
        #キャスト型
        elif cursor.kind == clang.cindex.CursorKind.CSTYLE_CAST_EXPR:
            cr = next(cursor.get_children())
            self.check_cursor_error(cr)
            exp_terms = [*self.parse_exp(cr, inNodeID), '()', cr.type.spelling]
        return exp_terms

    #関数の呼び出し(変数と関数の呼び出しは分ける)
    def parse_call_expr(self, cursor, inNodeID):
        funcNodeID = None
        for cr in cursor.get_children():
            self.check_cursor_error(cr)
            if funcNodeID:
                self.createEdge(funcNodeID, self.get_exp(cr, 'egg'))
            else:
                if cr.kind == clang.cindex.CursorKind.UNEXPOSED_EXPR:
                    cr = next(cr.get_children())
                    self.check_cursor_error(cursor)
                    if cr.kind == clang.cindex.CursorKind.UNEXPOSED_EXPR:
                        cr = next(cr.get_children())
                        self.check_cursor_error(cr)
                ref_spell = next(cr.get_tokens()).spelling
                self.func_info[self.scanning_func]["refs"].add(ref_spell)
                funcNodeID = self.createNode(ref_spell, 'oval')
        self.createEdge(inNodeID, funcNodeID)
        return funcNodeID

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
            self.roomSize_info[self.scanning_func][f'"{self.roomSizeEstimate[0]}"'] = self.roomSizeEstimate[1]
        #gotoのラベルを探っている最中は登録しない
        if nodeID:
            #部屋情報が完成したらroomSize辞書に移す
            self.roomSizeEstimate = [nodeID, 9]

    #部屋情報の部屋の大きさを1上げる
    def addSizeEstimate(self):
        self.roomSizeEstimate[1] += 1

    #if文
    #現在ノードに全ての子ノードをくっつける。出口ノードを作成する
    #子ノード(現在のノードの条件が真/偽それぞれの場合の遷移先)を引数に関数を再帰する
    #その関数の戻り値は条件先の最後の処理を示すノードとし、この戻り値→出口ノードとなる矢印をつける
    def parse_if_stmt(self, cursor, nodeID, edgeName=""):
        trueNodeID = None
        falseNodeID = None
        endNodeID = self.createNode("", 'circle') #出口ノードを生成。ifの中, elseの中でくっつける
        cursors = cursor.get_children()
        for cr in cursors:
            self.check_cursor_error(cr)
            #if文の中の処理→else文の中 or else if文
            if cr.kind == clang.cindex.CursorKind.COMPOUND_STMT:
                nodeID = self.parse_comp_stmt(cr, trueNodeID)
                if (cr := next(cursors, None)) is None:
                    break
                self.check_cursor_error(cr)
                if cr.kind == clang.cindex.CursorKind.COMPOUND_STMT:
                    elseCondNodeID = self.createNode("", 'circle')
                    #ここでif条件偽のための部屋情報を作る
                    self.createRoomSizeEstimate(elseCondNodeID)
                    self.createEdge(condNodeID, elseCondNodeID, "False")
                    condNodeID = elseCondNodeID
                    falseNodeID = self.parse_comp_stmt(cr, condNodeID)
                #else if文
                elif cr.kind == clang.cindex.CursorKind.IF_STMT:
                    #ここでは作らない(ifにもう一度入ると上で作られる)
                    falseNodeID = self.parse_if_stmt(cr, condNodeID, edgeName="False")
            #条件式
            else:
                if trueNodeID is None:
                    condNodeID = self.get_exp(cr, 'diamond')
                    self.createEdge(nodeID, condNodeID, edgeName)
                    #条件式に遷移先のノードを付けて行くのでここでnodeIDに設定する
                    trueNodeID = self.createNode("", 'circle')
                    self.createEdge(condNodeID, trueNodeID, "True")
                    #ここでif条件真のための部屋情報を作る
                    self.createRoomSizeEstimate(trueNodeID)
                else:
                    nodeID = self.parse_stmt(cr, trueNodeID)
        self.createEdge(nodeID, endNodeID)
        if falseNodeID:
            self.createEdge(falseNodeID, endNodeID)
        else:
            self.createEdge(condNodeID, endNodeID, "False")
        #if条件を抜けた後の部屋情報を作る
        self.createRoomSizeEstimate(endNodeID)
        return endNodeID

    #while文
    #子ノード(真の条件先の最初の処理)を現在のノードに付ける
    #子ノードを引数とする関数を呼び出し、真の場合の最後の処理をこの関数の戻り値とする
    #その戻り値を現在ノードに付ける
    #現在のノードは次のノードに付ける
    def parse_while_stmt(self, cursor, nodeID, edgeName=""):
        trueNodeID = None
        endNodeID = self.createNode("", 'doublecircle')
        for cr in cursor.get_children():
            self.check_cursor_error(cr)
            if trueNodeID is None:
                condNodeID = self.get_exp(cr, 'pentagon')
                self.createRoomSizeEstimate(condNodeID)
                self.createEdge(nodeID, condNodeID, edgeName)
                trueNodeID = self.createNode("", 'circle')
                nodeID = trueNodeID
                self.createEdge(condNodeID, trueNodeID, "True")
                #ここで真の部屋情報を作る
                self.createRoomSizeEstimate(trueNodeID)
            else:
                if cr.kind == clang.cindex.CursorKind.COMPOUND_STMT:
                    nodeID = self.parse_comp_stmt(cr, trueNodeID)
                else:
                    nodeID = self.parse_stmt(cr, trueNodeID)
                self.createEdgeForLoop(endNodeID, condNodeID)
        whileNodeID = self.createNode("", 'parallelogram')
        self.createEdge(nodeID, whileNodeID)
        self.createEdge(whileNodeID, condNodeID)
        self.createEdge(condNodeID, endNodeID, "False")
        #ここでwhileを抜けた後の部屋情報を作る
        self.createRoomSizeEstimate(endNodeID)
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
                nodeID = self.parse_comp_stmt(cr, startNodeID)
            else:
                if nodeID is None:
                    return None
                condNodeID = self.get_exp(cr, 'diamond')
                self.createEdgeForLoop(endNodeID, condNodeID)
                self.createEdge(nodeID, condNodeID)
                self.createEdge(condNodeID, startNodeID, "True")
                self.createEdge(condNodeID, endNodeID, "False")
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
                condNodeID = self.get_exp(cr, 'pentagon')
                self.createRoomSizeEstimate(condNodeID)
                if initNodeID:
                    self.createEdge(initNodeID, condNodeID)
                else:
                    self.createEdge(nodeID, condNodeID, edgeName)
                    edgeName = ""
            elif semi_offset[1] < cr.location.offset:
                changeExpr_cursor = cr

        if condNodeID is None:
            condNodeID = self.createNode("", 'pentagon')
            self.createRoomSizeEstimate(condNodeID)
            if initNodeID:
                self.createEdge(initNodeID, condNodeID)
            else:
                self.createEdge(nodeID, condNodeID, edgeName)
                
        self.check_cursor_error(exec_cursor)

        trueNodeID = self.createNode("", 'circle')
        self.createEdge(condNodeID, trueNodeID, "True")
        #ここで部屋情報を作る
        self.createRoomSizeEstimate(trueNodeID)

        if exec_cursor.kind == clang.cindex.CursorKind.COMPOUND_STMT:
            nodeID = self.parse_comp_stmt(exec_cursor, trueNodeID)
        else:
            nodeID = self.parse_stmt(exec_cursor, trueNodeID)
            
        #changeノードがある条件
        if self.loopBreaker_list[-1]["continue"] or nodeID:
            if changeExpr_cursor:
                changeNodeID = self.get_exp(cr, shape='parallelogram')
            else:
                changeNodeID = self.createNode("", shape='parallelogram')

        self.createEdge(nodeID, changeNodeID)
        self.createEdge(changeNodeID, condNodeID)
        self.createEdgeForLoop(endNodeID, changeNodeID)
        
        self.createEdge(condNodeID, endNodeID, "False")
        #ここでforを抜けた後の部屋情報を作る
        self.createRoomSizeEstimate(endNodeID)
        return endNodeID

    #switch文
    def parse_switch_stmt(self, cursor, nodeID, edgeName=""):
        cond_cursor, comp_exec_cursor = [cr for cr in cursor.get_children() if self.check_cursor_error(cr)]

        switchRoomSizeEstimate = self.roomSizeEstimate
        self.roomSizeEstimate = None

        #switchの構造はswitch(A)のようにAは必ず必要
        condNodeID = self.get_exp(cond_cursor, 'diamond')
        self.createEdge(nodeID, condNodeID, edgeName)

        self.createSwitchBreakerInfo()

        #switch(A){ B }の場合
        endNodeID = self.createNode("", 'doublecircle')
        if comp_exec_cursor.kind == clang.cindex.CursorKind.COMPOUND_STMT:
            isNotBreak = False
            for cr in comp_exec_cursor.get_children():
                self.check_cursor_error(cr)
                if cr.kind == clang.cindex.CursorKind.CASE_STMT:
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

                    if cr.kind == clang.cindex.CursorKind.COMPOUND_STMT:
                        nodeID = self.parse_comp_stmt(cr, caseNodeID)
                    else:
                        nodeID = self.parse_stmt(cr, caseNodeID)

                elif cr.kind == clang.cindex.CursorKind.DEFAULT_STMT:
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
                    nodeID = self.parse_stmt(default_cursor, defaultNodeID)
                    isNotBreak = True
                elif cr.kind == clang.cindex.CursorKind.BREAK_STMT:
                    nodeID = self.parse_stmt(cr, nodeID)
                    isNotBreak = False
                    #caseラベルと実行文の処理の階層は最初の実行文以外同じ
                else:
                    if caseNodeID or defaultNodeID:
                        nodeID = self.parse_stmt(cr, nodeID)
            self.createEdge(nodeID, endNodeID)

        #switch(A) Bの時、Bが case C: D なら A == C でDが行われる。
        elif comp_exec_cursor.kind == clang.cindex.CursorKind.CASE_STMT:
            caseValue_cursor, exec_cursor = [cr for cr in comp_exec_cursor.get_children() if self.check_cursor_error(cr)]
            caseNodeID = self.get_exp(caseValue_cursor, 'invtriangle')
            self.createEdge(condNodeID, caseNodeID)
            self.createSwitchBreakerInfo()

            #switchの元の部屋のサイズを+1する
            switchRoomSizeEstimate[1] += 1
            #ここでDのための部屋情報を作る
            self.createRoomSizeEstimate(caseNodeID)
            nodeID = self.parse_stmt(exec_cursor, caseNodeID)
            self.createEdge(nodeID, endNodeID)
        #しかし、B D なら D は無視される。Dは複数行でも良い。

        if defaultNodeID is None:
            self.createEdge(condNodeID, endNodeID)
        self.createSwitchBreakerEdge(endNodeID)
        #ここでswitchを抜けた後の部屋情報を作る
        self.createRoomSizeEstimate(endNodeID)

        self.roomSize_info[self.scanning_func][f'"{switchRoomSizeEstimate[0]}"'] = switchRoomSizeEstimate[1]
        return endNodeID
        

    #ループのbreakやcontinueの情報を保管する
    def createLoopBreakerInfo(self):
        self.loopBreaker_list.append({"break":[], "continue":[]})
        if self.switchBreaker_list:
            self.switchBreaker_list[-1]["level"] += 1

    def addLoopBreaker(self, node, type):
        if self.switchBreaker_list and type == "break":
            if self.switchBreaker_list[-1]["level"]:
                self.loopBreaker_list[-1][type].append(node)
            else:
                self.switchBreaker_list[-1][type].append(node)
        else:
            self.loopBreaker_list[-1][type].append(node)

    #ループ処理のノードをくっつけていく
    def createEdgeForLoop(self, breakToNodeID, continueToNodeID):
        loopBreaker = self.loopBreaker_list.pop()
        break_list = loopBreaker["break"]
        continue_list = loopBreaker["continue"]
        for breakNodeID in break_list:
            self.createEdge(breakNodeID, breakToNodeID)
        for continueNodeID in continue_list:
            self.createEdge(continueNodeID, continueToNodeID)

    #caseはbreakだけ適応させる
    #levelが0ならbreakノードを追加する。levelは繰り返し文が入ると1上がる。
    #それ以外ならloopBreaker_listに追加する。
    def createSwitchBreakerInfo(self):
        self.switchBreaker_list.append({"level":0, "break":[]})

    def downSwitchBreakerLevel(self):
        if self.switchBreaker_list:
            self.switchBreaker_list[-1]["level"] -= 1

    #switchのcaseのbreakノードを追加する。
    def createSwitchBreakerEdge(self, endNodeID):
        switchBreaker = self.switchBreaker_list.pop()
        break_list = switchBreaker["break"]
        for breakNodeID in break_list:
            self.createEdge(breakNodeID, endNodeID)
    