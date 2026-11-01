from __future__ import annotations
import faulthandler
faulthandler.enable()
import sys
import lldb
import argparse
import os
import struct
import threading
import socket
import json
import tempfile
from collections import Counter
import re
import random
from typing import TypedDict, NotRequired

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from rpg_aquatan_utils.types.expr_descriptions import *
from rpg_aquatan_utils.types.execution_info import *
from rpg_aquatan_utils.types.json_data_type import *

# break pointを打ってスキップすることも考えられる
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = BASE_DIR + "/mapdata_for_test"
CONTINUE = 1
PROGRESS = 0

class DynamicVarInfo(TypedDict):
    dynamic_var_node: DynamicVarNode
    start: int
    end: int
    skipped_function_list: list[list[str]]
    current_comment_w_index: tuple[DynamicCommentHandler, int] | None

class DynamicVarNode(TypedDict):
    name: str
    type: str
    children: list[DynamicVarNode]
    comments: DynamicCommentHandler
    initialized: bool

type DynamicNonVarStatus = (
    IfStatus
    | WhileStatus
    | DoWhileStatus
    | ForStatus
    | SwitchStatus
    | ControlFlowStatus
    | ExpressionStatus
    | ReturnStatus
)

class IfStatus(TypedDict):
    type: Literal["if"]
    line: str
    conditions: list[list[Comment]]
    dynamic_conditions: list[DynamicCommentHandler]
    results: list[bool]

class WhileStatus(TypedDict):
    type: Literal["while"]
    line: str
    condition: list[Comment]
    dynamic_condition: DynamicCommentHandler
    result: bool | None

class DoWhileStatus(TypedDict):
    type: Literal["do_while"]
    line: str
    condition: list[Comment]
    dynamic_condition: DynamicCommentHandler
    result: bool | None

class ForInitializerStatus(TypedDict):
    expr: list[Comment]
    dynamic_expr: DynamicCommentHandler

class ForVarInitializerStatus(TypedDict):
    required: list[tuple[str, int]]

class ForConditionStatus(TypedDict):
    expr: list[Comment]
    dynamic_expr: DynamicCommentHandler
    result: bool | None

class ForChangeStatus(TypedDict):
    expr: list[Comment]
    dynamic_expr: DynamicCommentHandler | None
    is_not_completed: bool

class ForStatus(TypedDict):
    type: Literal["for"]
    line: str
    initializer: NotRequired[ForInitializerStatus]
    var_initializer: NotRequired[ForVarInitializerStatus]
    condition: ForConditionStatus | None
    change: NotRequired[ForChangeStatus]
    is_first: bool

class SwitchConditionStatus(TypedDict):
    condition: list[Comment]
    dynamic_condition: DynamicCommentHandler
    result: str | None

class CaseStatus(TypedDict):
    case_expr: list[Comment]
    dynamic_case_expr: DynamicCommentHandler
    result: str | None
    
class SwitchStatus(TypedDict):
    type: Literal["switch"]
    line: str
    condition: SwitchConditionStatus
    case_expr_list_by_index: list[list[CaseStatus]]
    matched_case: str | None

class ControlFlowStatus(TypedDict):
    type: Literal["break", "continue"]
    line: str

class ExpressionStatus(TypedDict):
    type: Literal["expression"]
    line: str
    expr: list[Comment]
    dynamic_expr: DynamicCommentHandler

# void関数は、自由に戻れるキャラにする 
# ただし、frame_numが減らない場合(到達先の関数が異なる場合)は戻れない = プレイヤーはダメージを受けるようにする
class ReturnStatus(TypedDict):
    type: Literal["return"]
    line: str
    expr: list[Comment]
    dynamic_expr: DynamicCommentHandler
    result: str | None

class DynamicCommentHandler:
    def __init__(self, comments: list[Comment]):
        self.index_scanned_currently = 0
        # [ {"id": 1, "description": [{"name": "day"}, {"text": "\u3068"}, {"text": "1.2f"}, {"text": "\u3092\u639b\u3051\u307e\u3059"}], "expr": [{"name": "day"}, {"text": "*"}, {"text": "1.2f"}]} ]
        # a + b (=9) のような、途中式(comment)の結果を記録する 
        self.expr_result_by_id: list[str | None] = [None] * len(comments) 
        # a (=5) + b (=4) のような、変数(計算式)とその値を表示する文字列を、途中式のidごとに記録する
        # 計算式の評価がどうなろうと、このリストの内容は一定(計算式の生文字列)なので初期化時に全て取得しておく
        self.expr_str_to_show_by_id: list[str] = self.get_str_base(comments)
        # 「aとbをかけます」のような、説明文をidごとに記録する
        self.expr_description_to_show_by_id: list[str | Comment] = comments

        # 計算されずに飛ばされた自作関数を登録するリスト
        self.skipped_function_list: list[str] = []

        self.current_function_comment: FunctionComment | None = None

    def get_str_base(self, comments: list[Comment]):
        expr_str_base_list: list[str] = []
        for comment in comments:
            '''{
            "id": 1, 
            "description": [{"name": "day"}, {"text": "\u3068"}, {"text": "1.2f"}, {"text": "\u3092\u639b\u3051\u307e\u3059"}], 
            "expr": [{"name": "day"}, {"text": "*"}, {"text": "1.2f"}]
            "execution_condition": dict[int, bool]
            }
            '''

            expr_description = comment["comment"]

            if "func_name" in expr_description:
                arg_list = [
                    arg_expr_part["text"] 
                    if "text" in arg_expr_part else 
                    expr_str_base_list[arg_expr_part["expr_id"]] 
                    for arg_expr_part in expr_description["expr"]
                ]
                
                expr_str_base_list.append(f"{expr_part["func_name"]}({','.join(arg_list)})")
            else:
                expr_str_base_list_by_part = []

                for expr_part in expr_description["expr"]: # "expr": [{"name": "day"}, {"text": "*"}, {"text": "1.2f"}]}
                    if "type" in expr_part:
                        expr_str_base_list_by_part.append(self.get_reference_str_base(expr_part, expr_str_base_list))
                    elif "text" in expr_part:
                        expr_str_base_list_by_part.append(expr_part["text"])
                    elif "macro" in expr_part: # 今はスカラー値のみを考えるが、後々、関数やifdefも考えられると良いかも
                        expr_str_base_list_by_part.append(expr_part["macro"])
                    else: # expr_id
                        expr_str_base_list_by_part.append([expr_part["expr_id"]])

                expr_str_base_list.append(" ".join(expr_str_base_list_by_part))
        return expr_str_base_list

    def get_reference_str_base(self, expr_part: ScalarVariablePart | StructVariablePart | ArrayVariablePart, expr_str_to_show_by_id: list[str]):
        if expr_part["type"] == "scalar":
            # scalar variableの結果自体は取得する必要がない
            reference = expr_part["name"]
        elif expr_part["type"] == "struct":
            # struct variableの結果自体は取得する必要がない。
            struct_base = self.get_reference_str_base(expr_part["parent"], expr_str_to_show_by_id)
            reference = '.'.join([struct_base, *expr_part["members"]])
        else: # array
            # 計算結果を含めていない、計算式の文字列
            reference_index_base_list: list[str] = [
                f"[{expr_str_to_show_by_id[index_part["expr_id"]]}]" 
                if "expr_id" in index_part else 
                f"[{index_part["text"]}]" 
                for index_part in expr_part["indexes"]
            ]
            array_base = self.get_reference_str_base(expr_part["parent"], expr_str_to_show_by_id)
            reference = ''.join([array_base, *reference_index_base_list])
        return reference

    def set_expr_comments(self, frame: lldb.SBFrame):
        self.current_function_comment = None
        
        while self.index_scanned_currently < len(self.expr_description_to_show_by_id):
            '''{
            "id": 1, 
            "description": [{"name": "day"}, {"text": "\u3068"}, {"text": "1.2f"}, {"text": "\u3092\u639b\u3051\u307e\u3059"}], 
            "expr": [{"name": "day"}, {"text": "*"}, {"text": "1.2f"}]
            "execution_condition": dict[int, bool]
            }
            '''
            comment = self.expr_description_to_show_by_id[self.index_scanned_currently]

            if isinstance(comment, str):
                sys.exit("error in type of unscanned comment(should not \"str\")")
            
            '''
            現在の計算式を解析するかどうかを判別する 
            (ただし、該当する計算式が評価されていない場合、本計算式も評価されないものだとして、
            None is True or Falseになってis_not_to_evaluateがTrueになる)
            '''
            is_not_to_evaluate = False
            for line, condition in comment["execution_condition"].items():
                if self.check_value_bool(self.get_expr_result(int(line))) is not condition:
                    is_not_to_evaluate = True
                    break

            # もし、評価されないと判断された場合、計算式の評価をスキップする
            if is_not_to_evaluate:
                if "func_name" in expr_description and expr_description["is_custom"]:
                    self.skipped_function_list.append(expr_description["func_name"])

                self.index_scanned_currently += 1
                continue

            expr_description = comment["comment"]

            if "func_name" in expr_description:
                # exprリストにおけるFuncPartなので、'func_name', '(', ')' を追加してexpr_str_dataに登録する
                # ただし、自作関数の場合、not_to_evaluateがTrue ( = スキップされる関数 ) でない場合は登録しない
                if expr_description["is_custom"]:
                    self.current_function_comment = expr_description
                    return self

                ### 今は自作関数のみを考えている
                arg_list = [
                    arg_expr_part["text"] 
                    if "text" in arg_expr_part else 
                    self.get_expr_to_show(arg_expr_part["expr_id"])
                    for arg_expr_part in expr_description["expr"]
                ]

                str_for_evaluation = ''.join([expr_description["func_name"], "(", *arg_list, ")"])

                description_part_list = [
                    arg_expr_part["text"] 
                    if "text" in arg_expr_part else 
                    self.get_expr_to_show(arg_expr_part["expr_id"])
                    for arg_expr_part in expr_description["description"]
                ]

                description_to_show = ''.join(description_part_list)
            else:
                str_for_evaluation_list: list[str | None] = []
                str_to_show_list: list[str] = []
                special_operator: Literal["||", "&&", "?"] | None = None

                for expr_part in expr_description["expr"]: # "expr": [{"name": "day"}, {"text": "*"}, {"text": "1.2f"}]}
                    if "type" in expr_part:
                        reference_str_base, reference_str_to_show = self.get_reference_expr_comments(expr_part, frame)
                        str_for_evaluation_list.append(reference_str_base)
                        str_to_show_list.append(f"<{reference_str_to_show}>(={frame.EvaluateExpression(reference_str_base).GetValue()})")
                    elif "text" in expr_part:
                        if expr_part["text"] in ("||", "&&", "?"):
                            if special_operator is not None:
                                sys.exit("condition operator cannot be overlapped")
                            special_operator = expr_part["text"]

                        str_for_evaluation_list.append(expr_part["text"])
                        str_to_show_list.append(expr_part["text"])
                    elif "macro" in expr_part: # 今はスカラー値のみを考えるが、後々、関数やifdefも考えられると良いかも
                        if "text" in expr_part["replacement"]:
                            str_for_evaluation_list.append(expr_part["replacement"]["text"])
                            str_to_show_list.append(f"<{expr_part["macro"]}>(={expr_part["replacement"]["text"]})")
                        else: # expr_id
                            str_for_evaluation_list.append(self.get_expr_result(expr_part["replacement"]["expr_id"]))
                            str_to_show_list.append(f"<{expr_part["macro"]}>(={self.get_expr_result(expr_part["replacement"]["expr_id"]) | "not to evaluate"})")
                    else: # expr_id
                        str_for_evaluation_list.append(self.get_expr_result(expr_part["expr_id"]))
                        str_to_show_list.append(f"<{self.get_expr_to_show(expr_part["expr_id"])}>(={self.get_expr_result(expr_part["expr_id"]) | "not to evaluate"})")

                '''
                ここで"||", "&&", "?"の演算子の処理を行う
                a || b の時はbが未処理なら"1"(aが真であるため), bが未処理でないならbool(b)で真偽(1, 0)を確かめ、その値をstr_for_evaluationリストに登録する
                a && b の時はbが未処理なら"0"(aが偽であるため), bが未処理でないならbool(b)で真偽(1, 0)を確かめ、その値をstr_for_evaluationリストに登録する
                c ? a : b の時はaが未処理ならbの値, bが未処理ならaの値をstr_for_evaluationリストに登録する
                未処理の計算式については、Noneをstr_for_evaluationに登録する
                '''
                description_to_show_list = []
                for expr_part in expr_description["description"]:
                    if "type" in expr_part:
                        reference_description_base, reference_description_to_show = self.get_reference_expr_comments(expr_part, frame)
                        description_to_show_list.append(f"{reference_description_to_show}(={frame.EvaluateExpression(reference_description_base).GetValue()})")
                    elif "text" in expr_part:
                        description_to_show_list.append(expr_part["text"])
                    elif "macro" in expr_part: # 今はスカラー値のみを考えるが、後々、関数やifdefも考えられると良いかも
                        if "text" in expr_part["replacement"]:
                            description_to_show_list.append(f"{expr_part["macro"]}(={expr_part["replacement"]["text"]})")
                        else:
                            description_to_show_list.append(f"{expr_part["macro"]}(={self.get_expr_result(expr_part["replacement"]["expr_id"])})")
                    else: # expr_id
                        description_to_show_list.append(self.get_expr_result(expr_part["expr_id"]))

                description_to_show = " ".join(description_to_show_list)
                if special_operator == "||":
                    if str_for_evaluation_list[-1] is None:
                        str_for_evaluation = "1"
                    else:
                        str_for_evaluation = "1" if self.check_value_bool(str_for_evaluation_list[-1]) else "0"
                elif special_operator == "&&":
                    if str_for_evaluation_list[-1] is None:
                        str_for_evaluation = "0"
                    else:
                        str_for_evaluation = "1" if self.check_value_bool(str_for_evaluation_list[-1]) else "0"
                elif special_operator == "?":
                    if str_for_evaluation_list[-1] is None:
                        str_for_evaluation = str_for_evaluation_list[-3]
                    elif str_for_evaluation_list[-3] is None:
                        str_for_evaluation = str_for_evaluation_list[-1]
                    else:
                        sys.exit("error in ? condition")
                else:
                    if None in str_for_evaluation_list:
                        sys.exit("all expression parts have to be calculated")
                    str_for_evaluation: str = " ".join(str_for_evaluation_list)

            self.expr_result_by_id[self.index_scanned_currently] = frame.EvaluateExpression(str_for_evaluation).GetValue()
            self.expr_description_to_show_by_id[self.index_scanned_currently] = f'{self.get_expr_to_show(self.index_scanned_currently)}: {description_to_show}'

            self.index_scanned_currently += 1
        
        return None

    def set_function_comment(self, return_value: str):
        if self.current_function_comment is None:
            sys.exit("current function comment is not found")
        self.expr_result_by_id[self.index_scanned_currently] = return_value
        self.expr_description_to_show_by_id[self.index_scanned_currently] = f'{self.get_expr_to_show(self.index_scanned_currently)}: {return_value}'

        self.skipped_function_list = []

        self.index_scanned_currently += 1

    def check_value_bool(self, value: str | None, frame: lldb.SBFrame) -> bool | None:
        if value is None:
            return None
        return frame.EvaluateExpression(f"(int)!!({value})").GetValueAsSigned() != 0

    def get_reference_expr_comments(self, expr_part: ScalarVariablePart | StructVariablePart | ArrayVariablePart, frame: lldb.SBFrame):
        if expr_part["type"] == "scalar":
            # scalar variableの結果自体は取得する必要がない
            reference = expr_part["name"]
            reference_w_result = reference
        elif expr_part["type"] == "struct":
            # struct variableの結果自体は取得する必要がない。
            struct_base, struct_base_w_result = self.get_reference_expr_comments(expr_part["parent"], frame)
            reference = '.'.join([struct_base, *expr_part["members"]])
            reference_w_result = '.'.join([struct_base_w_result, *expr_part["members"]])
        else: # array
            reference_index_to_show_list: list[str] = []
            # 計算結果を含めていない、計算式の文字列
            reference_index_base_list: list[str] = []
            # indexごとにresultを取得する(arrayの結果自体はここで取得する必要がない)
            for index_part in expr_part["indexes"]:
                if "expr_id" in index_part:
                    # expr_id
                    reference_index_to_show_list.append(f"[<{self.get_expr_to_show(index_part["expr_id"])}>(={self.get_expr_result(index_part["expr_id"]) | "not to evaluate"})]")
                    reference_index_base_list.append(f"[{self.get_expr_to_show(index_part["expr_id"])}]")
                else:
                    # text
                    reference_index_to_show_list.append(f"[{index_part["text"]}]")
                    reference_index_base_list.append(f"[{index_part["text"]}]")
            reference_top, reference_top_w_result = self.get_reference_expr_comments(expr_part["parent"], frame)
            reference = ''.join([reference_top, *reference_index_base_list])
            reference_w_result = ''.join([reference_top_w_result, *reference_index_to_show_list])
        return reference, reference_w_result

    def get_expr_result(self, index: int):
        if index >= len(self.expr_result_by_id):
            sys.exit("error in id number for getting expression result")
        
        return self.expr_result_by_id[index]
    
    def get_expr_to_show(self, index: int):
        if index >= len(self.expr_str_to_show_by_id):
            sys.exit("error in id number for getting expression result")
        
        return self.expr_str_to_show_by_id[index]

    def get_current_function(self):
        if self.current_function_comment is None:
            sys.exit("current function comment is not found")
        return self.current_function_comment["func_name"]

    def get_result_bool(self, frame: lldb.SBFrame):
        if len(self.expr_result_by_id) != self.index_scanned_currently:
            sys.exit("expression is not completely analyzed yet")

        result_bool = self.check_value_bool(self.expr_result_by_id[-1], frame)
        if result_bool is None:
            sys.exit("error in result")

        return result_bool
    
    def get_str_after_analysis_completed(self) -> str:
        if any(not isinstance(str, expr_description) for expr_description in self.expr_description_to_show_by_id):
            sys.exit("this expression is not completely analyzed yet")
        
        return '\n'.join(self.expr_description_to_show_by_id)

    def is_analysis_potentially_completed(self):
        for comment in self.expr_description_to_show_by_id[self.index_scanned_currently:]:
            if isinstance(comment, str):
                sys.exit("str is found in an analyzed parts of expr_description_to_show_by_id")
            
            if "func_name" in comment["comment"] and all(self.get_expr_result(index) is result for index, result in comment["execution_condition"].items()):
                return False

        return True

#     elif len(fromTo) == 1 and fromTo == [self.line_number]:
#         if type == 'whileIn':
#             if len(self.line_loop) and self.line_loop[-1] == self.line_number:
#                 skipStart = self.line_number
#                 skipEnd = self.line_data[self.func_name]["loops"][str(self.line_number)]
#                 if skipStart <= self.next_line_number <= skipEnd:
#                     # ここでスキップするかどうかを確認する
#                     self.event_sender({"message": "Will you skip to rightly before exit of loop ?" if self.is_english else "ループを抜ける直前までスキップしますか?", "status": "ok", "type": "while", "skip": True}, False)
#                     event = self.event_reciever()
#                     if event.get('skip', False):
#                         while skipStart <= self.next_line_number <= skipEnd:
#                             # ここは後々、scanfがあるかどうかでスキップするかどうかを確かめる
#                             self.step_conditionally()
#                         self.event_sender({"message": "skip is completed" if self.is_english else "スキップが完了しました", "status": "ok", "type": "while", "items": self.vars_tracker.getValueAll(), "finalLine": self.line_number}, False)
#                     else:

#                         self.event_sender({"message": "skip is canceled" if self.is_english else "スキップをキャンセルしました", "status": "ok", "type": "while"}, False)
#                 else:
#                     self.event_sender({"message": "", "status": "ok", "type": "while"})
#             else:
#                 self.event_sender({"message": "", "status": "ok", "type": "while"}, False)
#                 self.line_loop.append(self.line_number)
#         elif type == 'doWhileIn':
#             if len(self.line_loop) and self.line_loop[-1] == self.next_line_number:
#                 # ここでスキップするかどうを確認する
#                 skipStart = self.line_data[self.func_name]["loops"][str(self.line_number)]
#                 skipEnd = self.line_number
#                 self.event_sender({"message": "Will you skip to rightly before exit of loop ?" if self.is_english else "ループを抜ける直前までスキップしますか?", "status": "ok", "type": "doWhile", "skip": True}, False)
#                 event = self.event_reciever()
#                 if event.get('skip', False):
#                     while skipStart <= self.next_line_number <= skipEnd:
#                         # ここは後々、scanfがあるかどうかでスキップするかどうかを確かめる
#                         self.step_conditionally()
#                     self.event_sender({"message": "skip is completed" if self.is_english else "スキップが完了しました", "status": "ok", "type": "doWhile", "items": self.vars_tracker.getValueAll(), "finalLine": self.line_number}, False)
#                 else:
#                     self.event_sender({"message": "skip is canceled" if self.is_english else "スキップをキャンセルしました", "status": "ok", "type": "doWhile"}, False)
#             else:
#                 self.event_sender({"message": "", "status": "ok", "type": "doWhile"}, False)
#                 # なお、ループの始まりの行を管理するself.line_loopへの登録はdo-while-initの時にやっているのでここでは行わない
#         elif type == 'forIn':
#             if len(self.line_loop) and self.line_loop[-1] == self.line_number:
#                 skipStart = self.line_number
#                 skipEnd = self.line_data[self.func_name]["loops"][str(self.line_number)]
#                 if skipStart <= self.next_line_number <= skipEnd:
#                     # ここでスキップするかどうかを確認する
#                     self.event_sender({"message": "Will you skip to rightly before exit of loop ?" if self.is_english else "ループを抜ける直前までスキップしますか?", "status": "ok", "type": "for", "skip": True, "vars_w_value_changed": self.get_vars_w_value_changed(list(self.vars_tracker.vars_changed.keys())), "vars_w_value_unchanged": self.get_vars_w_value_unchanged(), "line": self.line_number}, False)
#                     event = self.event_reciever()
#                     if event.get('skip', False):
#                         line_list: list[int] = [skipStart]
#                         while skipStart <= self.next_line_number <= skipEnd:
#                             # ここは後々、scanfがあるかどうかでスキップするかどうかを確かめる
#                             self.step_conditionally()
#                             line_list.append(self.line_number)
#                         self.event_sender({"message": "skip is completed" if self.is_english else "スキップが完了しました", "status": "ok", "type": "for", "items": self.vars_tracker.getValueAll(), "finalLine": skipStart if [skipStart, skipEnd] == line_list[-2:] else self.line_number}, False)
#                         if skipEnd == self.line_number:
#                             while True:
#                                 if (event := self.event_reciever()) is None:
#                                     break
#                                 elif (fromTo := event.get('fromTo')) is None:
#                                     self.event_sender({"message": "You did a different action !!" if self.is_english else "異なる行動をしようとしています!!", "status": "ng"}, False)
#                                 elif (type := event.get('type')) != 'forFalse':
#                                     self.event_sender({"message": "You did a different action !!" if self.is_english else "異なる行動をしようとしています!!", "status": "ng"}, False)
#                                 if fromTo == [*line_list[-2:], self.next_line_number]:
#                                     skipped_func = []
#                                     self.event_sender({"message": "", "status": "ok", "type": "for", "skipped_function_list": skipped_func, "vars_w_value_changed": self.get_vars_w_value_changed(list(self.vars_tracker.vars_changed.keys())), "vars_w_value_unchanged": self.get_vars_w_value_unchanged()})
#                                     break
#                     else:
#                         self.event_sender({"message": "skip is canceled" if self.is_english else "スキップをキャンセルしました", "status": "ok", "type": "for", "vars_w_value_changed": self.get_vars_w_value_changed(list(self.vars_tracker.vars_changed.keys())), "vars_w_value_unchanged": self.get_vars_w_value_unchanged()}, False)
#                 else:
#                     self.event_sender({"message": "", "status": "ok", "type": "for", "vars_w_value_changed": self.get_vars_w_value_changed(list(self.vars_tracker.vars_changed.keys())), "vars_w_value_unchanged": self.get_vars_w_value_unchanged()})
#             else:
#                 self.event_sender({"message": "", "status": "ok", "type": "for", "vars_w_value_changed": self.get_vars_w_value_changed(list(self.vars_tracker.vars_changed.keys())), "vars_w_value_unchanged": self.get_vars_w_value_unchanged()}, False)
#                 self.line_loop.append(self.line_number)

def handle_client(conn: socket.socket, addr: tuple[str, int]) -> None:
    # エラーハンドリング
    class ProgramFinished(Exception):
        print("プログラムが終了しました")

    class RollBack(Exception):
        print("処理の巻き戻しを実行します")
    
    class NoConnection(Exception):
        print("クライアントとの接続が切れました")

    class VarPreviousValue:
        def __init__(self, value=None, address=None):
            self.value: str | None = value
            self.address = address
            self.children: dict[str, VarPreviousValue] = {}  # 配列の添字や構造体のメンバ

        def update_value(self, value, address):
            """LLDBのSBValueから最新値を更新"""
            self.value = value
            self.address = address
                                                                                                                   
    # 8b           d8                          888888888888                             88                              
    # `8b         d8'                               88                                  88                              
    #  `8b       d8'                                88                                  88                              
    #   `8b     d8' ,adPPYYba, 8b,dPPYba, ,adPPYba, 88 8b,dPPYba, ,adPPYYba,  ,adPPYba, 88   ,d8  ,adPPYba, 8b,dPPYba,  
    #    `8b   d8'  ""     `Y8 88P'   "Y8 I8[    "" 88 88P'   "Y8 ""     `Y8 a8"     "" 88 ,a8"  a8P_____88 88P'   "Y8  
    #     `8b d8'   ,adPPPPP88 88          `"Y8ba,  88 88         ,adPPPPP88 8b         8888[    8PP""""""" 88          
    #      `888'    88,    ,88 88         aa    ]8I 88 88         88,    ,88 "8a,   ,aa 88`"Yba, "8b,   ,aa 88          
    #       `8'     `"8bbdP"Y8 88         `"YbbdP"' 88 88         `"8bbdP"Y8  `"Ybbd8"' 88   `Y8a `"Ybbd8"' 88          
                                                                                                                  
    class VarsTracker:
        def __init__(self):
            self.reset_state()
        
        def reset_state(self):
            self.previous_values: list[dict[tuple[str, int], VarPreviousValue]] = []
            self.global_previous_values: dict[tuple[str, int], VarPreviousValue] = {}
            self.vars_changed: dict[tuple[str, int], list[tuple[str, ...]]] = {}
            self.vars_unchanged: list[tuple[tuple[str, int], tuple[str, ...]]] = []
            self.vars_unchanged_count = 0
            self.vars_declared: list[list[tuple[str, int]]] = []
            self.vars_removed: set[tuple[str, int]] = set()
            self.frames: list[str] = ['start']
            self.declared_variables_by_line: dict[str, list[VarInfo]] = {}
            self.dynamic_variable_info_by_line: dict[str, list[DynamicVarInfo]] = {}

            self.track_gvar()
        
        def track_gvar(self):
            gvars = []
            for module in target.module_iter():
                for sym in module:
                    if sym.GetType() != lldb.eSymbolTypeData:  # データシンボル（変数
                        continue
                    if (name := sym.GetName()):
                        var = target.FindFirstGlobalVariable(name)
                        if var.IsValid():
                            gvars.append(var)
            self.track_var(gvars, self.global_previous_values, isLocal=False)
            
        def trackStart(self, frame: lldb.SBFrame):
            current_frames = [
                thread.GetFrameAtIndex(i).GetFunctionName()
                for i in range(thread.GetNumFrames())
            ]

            # 何かしらの関数に遷移したとき
            if len(current_frames) > len(self.frames):
                self.previous_values.append({})
                self.vars_declared.append([])
                self.frames = current_frames
            # 何かしらの関数から戻ってきたとき
            elif len(current_frames) < len(self.frames):
                self.previous_values.pop(-1)
                self.vars_declared.pop(-1)
                self.frames = current_frames
            
            self.vars_changed = {}
            self.vars_unchanged = []
            self.vars_unchanged_count = 0

            self.track_gvar()

            self.track_var(frame.GetVariables(True, True, True, True), self.previous_values[-1])

            self.analyze_var_nodes(str(frame.GetLineEntry().GetLine()), frame)

        # 変数宣言リストの中から次に宣言される変数を取得して、その計算式の内容を解析する
        def analyze_var_nodes(self, line_number: str, frame: lldb.SBFrame):
            # ここで次の計算式で参照される変数の値を取得する
            if line_number not in self.declared_variables_by_line:
                return
            
            dynamic_variable_info_list = self.dynamic_variable_info_by_line.pop(line_number, [])
            if len(dynamic_variable_info_list) == 0:
                for var_info in self.declared_variables_by_line[line_number]:
                    dynamic_variable_info_list.append(
                        DynamicVarInfo(
                            dynamic_var_node = self.transform_2_dynamic_var_node(var_info["varNode"]),
                            start = var_info["start"],
                            end = var_info["end"],
                            skipped_function_list = [],
                            current_comment = None
                        )
                    )

            for dynamic_variable_info in dynamic_variable_info_list:
                dynamic_variable_info["current_comment_w_index"] = []
                dynamic_variable_info["skipped_function_list"] = []
                if (dynamic_comment_handler_w_index := self.analyze_var_expr_comments(dynamic_variable_info["dynamic_var_node"], dynamic_variable_info["skipped_function_list"], frame)):
                    dynamic_variable_info["current_comment_w_index"] = dynamic_comment_handler_w_index
                    break

            self.dynamic_variable_info_by_line[line_number] = dynamic_variable_info_list
  
        def transform_2_dynamic_var_node(self, var_node: VarNode):
            return DynamicVarNode(
                name = var_node["name"],
                type = var_node["type"],
                children = [
                    self.transform_2_dynamic_var_node(child_var_node)
                    for child_var_node in var_node["children"]
                ],
                comments = DynamicCommentHandler(comments = var_node["comments"]),
                initialized = var_node["initialized"]
            )
        
        def analyze_var_expr_comments(self, var_node: DynamicVarNode, skipped_function_list_by_part: list[list[str]], frame: lldb.SBFrame) -> tuple[DynamicCommentHandler, int] | None:
            dynamic_comment_handler = self.set_expr_comments(var_node["comments"], frame)
            
            skipped_function_list_by_part.append(var_node["comments"].skipped_function_list)

            if dynamic_comment_handler is not None:
                return (dynamic_comment_handler, len(skipped_function_list_by_part)-1)
            
            for child_var_node in var_node["children"]:
                if (dynamic_comment_handler_w_index := self.analyze_var_expr_comments(child_var_node, skipped_function_list_by_part, frame)):
                    return dynamic_comment_handler_w_index
            
            return None
          
        def get_reference_expr_comments(self, expr_part: ScalarVariablePart | StructVariablePart | ArrayVariablePart, expr_result_by_id: dict[int, any], expr_str_to_show_by_id: dict[int, str], frame: lldb.SBFrame):
            if expr_part["type"] == "scalar":
                # scalar variableの結果自体は取得する必要がない
                reference = expr_part["name"]
                reference_w_result = reference
            elif expr_part["type"] == "struct":
                # struct variableの結果自体は取得する必要がない。
                struct_base, struct_base_w_result = self.get_reference_expr_comments(expr_part["parent"], expr_result_by_id, expr_str_to_show_by_id, frame)
                reference = '.'.join([struct_base, *expr_part["members"]])
                reference_w_result = '.'.join([struct_base_w_result, *expr_part["members"]])
            else: # array
                reference_index_to_show_list: list[str] = []
                # 計算結果を含めていない、計算式の文字列
                reference_index_base_list: list[str] = []
                # indexごとにresultを取得する(arrayの結果自体はここで取得する必要がない)
                for index_part in expr_part["indexes"]:
                    if "expr_id" in index_part:
                        # expr_id
                        reference_index_to_show_list.append(f"[<{expr_str_to_show_by_id[index_part["expr_id"]]}>(={expr_result_by_id[index_part["expr_id"]]})]")
                        reference_index_base_list.append(f"[{expr_str_to_show_by_id[index_part["expr_id"]]}]")
                    else:
                        # text
                        reference_index_to_show_list.append(f"[{index_part["text"]}]")
                        reference_index_base_list.append(f"[{index_part["text"]}]")
                reference_top, reference_top_w_result = self.get_reference_expr_comments(expr_part["parent"], expr_result_by_id, expr_str_to_show_by_id, frame)
                reference = ''.join([reference_top, *reference_index_base_list])
                reference_w_result = ''.join([reference_top_w_result, *reference_index_to_show_list])
            return reference, reference_w_result

        # 取得した値がC言語にて真か偽かを確かめる
        # GetValueAsSignedで真偽値をintで
        def check_value_bool(self, value: str, frame: lldb.SBFrame) -> bool:
            return frame.EvaluateExpression(f"(int)!!({value})").GetValueAsSigned() != 0

        # 解析した結果がTrueなら、その部分の計算式の解析は全て終了したことになる
        def set_expr_comments(self, dynamic_comment_handler: DynamicCommentHandler, frame: lldb.SBFrame):
            return dynamic_comment_handler.set_expr_comments(frame)

        def track_var(self, vars: list[lldb.SBValue] | lldb.SBValueList, var_previous_values: dict[tuple[str, int], VarPreviousValue], isLocal: bool = True):
            crnt_vars: list[tuple[str, int]] = []

            for var in vars:
                name = var.GetName()
                line = int(var.GetDeclaration().GetLine())
                full_name = name
                value = var.GetValue()
                address = var.GetLoadAddress()

                var_previous_value = var_previous_values[(name, line)].value if (name, line) in var_previous_values else None

                if value != var_previous_value:
                    print(f"{full_name} = {value}    ← changed")
                    self.vars_changed[(name,line)] = [()]
                else:
                    print(f"{full_name} = {value}")
                    self.vars_unchanged_count += 1

                    if (name, line) in self.vars_declared[-1]:
                        item = ((name, line), tuple())

                        if len(self.vars_unchanged) < 3:
                            self.vars_unchanged.append(item)
                        else:
                            r = random.randint(0, self.vars_unchanged_count - 1)

                            if r < 3:
                                self.vars_unchanged[r] = item

                if isLocal:
                    crnt_vars.append((name, line))

                if (name, line) in var_previous_values:
                    var_previous_values[(name, line)].update_value(value, address)
                else:
                    var_previous_values[(name, line)] = VarPreviousValue(value, address)

                num_children = var.GetNumChildren()
                
                if var.GetType().IsPointerType():
                    pointee_type = var.GetType().GetPointeeType()
                    type_name = pointee_type.GetName()

                    try:
                        if not pointee_type.IsPointerType():
                            addr = int(var.GetValue(), 16)
                            target = var.GetTarget()
                            process = target.GetProcess()
                            error = lldb.SBError()
                            if type_name == "char":
                                cstr = process.ReadCStringFromMemory(addr, 100, error)
                                if error.Success():
                                    print(f"→ {full_name} points to string: \"{cstr}\"")
                                    var_previous_value = var_previous_values[(name, line)].children['*'].value if '*' in var_previous_values[(name, line)].children else None
                                    if cstr != var_previous_value:
                                        if (name,line) in self.vars_changed:
                                            self.vars_changed[(name,line)].append(('*', ))
                                        else:
                                            self.vars_changed[(name,line)]= [('*', )]
                                    var_previous_values[(name, line)].children['*'] = VarPreviousValue(cstr, addr)
                                else:
                                    print(f"→ {full_name} points to unreadable char*")
                            elif type_name == "int":
                                data = process.ReadMemory(addr, 4, error)
                                if error.Success():
                                    val = struct.unpack("i", data)[0]
                                    print(f"→ {full_name} points to int: {val}")
                                    var_previous_value = var_previous_values[(name, line)].children['*'].value if '*' in var_previous_values[(name, line)].children else None
                                    if val != var_previous_value:
                                        if (name,line) in self.vars_changed:
                                            self.vars_changed[(name,line)].append(('*', ))
                                        else:
                                            self.vars_changed[(name,line)]= [('*', )]
                                    var_previous_values[(name, line)].children['*'] = VarPreviousValue(val, addr)
                                else:
                                    print(f"→ {full_name} points to unreadable int*")
                            elif type_name == "float":
                                data = process.ReadMemory(addr, 4, error)
                                if error.Success():
                                    val = struct.unpack("f", data)[0]
                                    print(f"→ {full_name} points to float: {val}")
                                    var_previous_value = var_previous_values[(name, line)].children['*'].value if '*' in var_previous_values[(name, line)].children else None
                                    if val != var_previous_value:
                                        if (name,line) in self.vars_changed:
                                            self.vars_changed[(name,line)].append(('*', ))
                                        else:
                                            self.vars_changed[(name,line)]= [('*', )]
                                    var_previous_values[(name, line)].children['*'] = VarPreviousValue(val, addr)
                                else:
                                    print(f"→ {full_name} points to unreadable float*")
                            elif type_name == "double":
                                data = process.ReadMemory(addr, 8, error)
                                if error.Success():
                                    val = struct.unpack("d", data)[0]
                                    print(f"→ {full_name} points to double: {val}")
                                    var_previous_value = var_previous_values[(name, line)].children['*'].value if '*' in var_previous_values[(name, line)].children else None
                                    if val != var_previous_value:
                                        if (name,line) in self.vars_changed:
                                            self.vars_changed[(name,line)].append(('*', ))
                                        else:
                                            self.vars_changed[(name,line)]= [('*', )]
                                    var_previous_values[(name, line)].children['*'] = VarPreviousValue(val, addr)
                                else:
                                    print(f"→ {full_name} points to unreadable double*")
                            else:
                                # 構造体などの場合
                                deref = var.Dereference()
                                if deref.IsValid() and deref.GetNumChildren() > 0:
                                    print(f"→ Deref {full_name}")
                                    self.track([deref.GetChildAtIndex(i) for i in range(deref.GetNumChildren())], var_previous_values[(name, line)].children, [name], line, full_name)
                        else:
                            self.track([var.GetChildAtIndex(i) for i in range(num_children)], var_previous_values[(name, line)].children, line, [name], full_name)

                    except Exception as e:
                        print(f"→ {full_name} deref error: {e}")

                elif num_children > 0:
                    self.track([var.GetChildAtIndex(i) for i in range(num_children)], var_previous_values[(name, line)].children, line, [name], full_name)
        
            if not isLocal or len(self.vars_declared) == 0:
                return
            
            vars_removed = set(var_previous_values.keys()) - set(crnt_vars)
            self.vars_removed.update(vars_removed)
            for var_removed in vars_removed:
                if var_removed not in self.vars_declared[-1]:
                    continue
                self.vars_declared[-1].remove(var_removed)
                var_previous_values.pop(var_removed, None)
                        
        def track(self, vars: list[lldb.SBValue], var_previous_values: dict[str, VarPreviousValue], line: int, vars_path: list[str], prefix: str, depth: int = 1) -> list[str]:
            indent = "    " * depth

            for var in vars:
                name = '*' if var.GetType().IsPointerType() else var.GetName() 
                full_name = f"{prefix}.{name}"
                value = var.GetValue()
                address = var.GetLoadAddress()

                var_previous_value = var_previous_values[name].value if name in var_previous_values else None

                if value != var_previous_value:
                    print(f"{indent}{full_name} = {value}    ← changed")
                    if (vars_path[0], line) in self.vars_changed:
                        self.vars_changed[(vars_path[0], line)].append((*vars_path[1:], name))
                    else:
                        self.vars_changed[(vars_path[0], line)] = [(*vars_path[1:], name)]
                else:
                    print(f"{indent}{full_name} = {value}")
                    self.vars_unchanged_count += 1

                    if (vars_path[0], line) in self.vars_declared[-1]:
                        item = ((vars_path[0], line), (*vars_path[1:], name))

                        if len(self.vars_unchanged) < 3:
                            self.vars_unchanged.append(item)
                        else:
                            r = random.randint(0, self.vars_unchanged_count - 1)

                            if r < 3:
                                self.vars_unchanged[r] = item

                if name in var_previous_values:
                    var_previous_values[name].update_value(value, address)
                else:
                    var_previous_values[name] = VarPreviousValue(value, address)

                num_children = var.GetNumChildren()
                
                if var.GetType().IsPointerType():
                    pointee_type = var.GetType().GetPointeeType()
                    type_name = pointee_type.GetName()

                    try:
                        if not pointee_type.IsPointerType():
                            addr = int(var.GetValue(), 16)
                            target = var.GetTarget()
                            process = target.GetProcess()
                            error = lldb.SBError()
                            if type_name == "char":
                                cstr = process.ReadCStringFromMemory(addr, 100, error)
                                if error.Success():
                                    print(f"{indent}→ {full_name} points to string: \"{cstr}\"")
                                    var_previous_value = var_previous_values[name].children['*'].value if '*' in var_previous_values[name].children else None
                                    if cstr != var_previous_value:
                                        if len(vars_path) == 0:
                                            if (name, line) in self.vars_changed:
                                                self.vars_changed[(name, line)].append(('*', ))
                                            else:
                                                self.vars_changed[(name, line)]= [('*', )]
                                        else:
                                            if (vars_path[0], line) in self.vars_changed:
                                                self.vars_changed[(vars_path[0], line)].append((*vars_path[1:], name, '*'))
                                            else:
                                                self.vars_changed[(vars_path[0], line)] = [(*vars_path[1:], name, '*')]
                                    var_previous_values[name].children['*'] = VarPreviousValue(cstr, addr)
                                else:
                                    print(f"{indent}→ {full_name} points to unreadable char*")
                            elif type_name == "int":
                                data = process.ReadMemory(addr, 4, error)
                                if error.Success():
                                    val = struct.unpack("i", data)[0]
                                    print(f"{indent}→ {full_name} points to int: {val}")
                                    var_previous_value = var_previous_values[name].children['*'].value if '*' in var_previous_values[name].children else None
                                    if val != var_previous_value:
                                        if len(vars_path) == 0:
                                            if (name, line) in self.vars_changed:
                                                self.vars_changed[(name, line)].append(('*', ))
                                            else:
                                                self.vars_changed[(name, line)]= [('*', )]
                                        else:
                                            if (vars_path[0], line) in self.vars_changed:
                                                self.vars_changed[(vars_path[0], line)].append((*vars_path[1:], name, '*'))
                                            else:
                                                self.vars_changed[(vars_path[0], line)] = [(*vars_path[1:], name, '*')]
                                    var_previous_values[name].children['*'] = VarPreviousValue(val, addr)
                                else:
                                    print(f"{indent}→ {full_name} points to unreadable int*")
                            elif type_name == "float":
                                data = process.ReadMemory(addr, 4, error)
                                if error.Success():
                                    val = struct.unpack("f", data)[0]
                                    print(f"{indent}→ {full_name} points to float: {val}")
                                    var_previous_value = var_previous_values[name].children['*'].value if '*' in var_previous_values[name].children else None
                                    if val != var_previous_value:
                                        if len(vars_path) == 0:
                                            if (name, line) in self.vars_changed:
                                                self.vars_changed[(name, line)].append(('*', ))
                                            else:
                                                self.vars_changed[(name, line)]= [('*', )]
                                        else:
                                            if (vars_path[0], line) in self.vars_changed:
                                                self.vars_changed[(vars_path[0], line)].append((*vars_path[1:], name, '*'))
                                            else:
                                                self.vars_changed[(vars_path[0], line)] = [(*vars_path[1:], name, '*')]
                                    var_previous_values[name].children['*'] = VarPreviousValue(val, addr)
                                else:
                                    print(f"{indent}→ {full_name} points to unreadable float*")
                            elif type_name == "double":
                                data = process.ReadMemory(addr, 8, error)
                                if error.Success():
                                    val = struct.unpack("d", data)[0]
                                    print(f"{indent}→ {full_name} points to double: {val}")
                                    var_previous_value = var_previous_values[name].children['*'].value if '*' in var_previous_values[name].children else None
                                    if val != var_previous_value:
                                        if len(vars_path) == 0:
                                            if (name, line) in self.vars_changed:
                                                self.vars_changed[(name, line)].append(('*', ))
                                            else:
                                                self.vars_changed[(name, line)]= [('*', )]
                                        else:
                                            if (vars_path[0], line) in self.vars_changed:
                                                self.vars_changed[(vars_path[0], line)].append((*vars_path[1:], name, '*'))
                                            else:
                                                self.vars_changed[(vars_path[0], line)] = [(*vars_path[1:], name, '*')]
                                    var_previous_values[name].children['*'] = VarPreviousValue(val, addr)
                                else:
                                    print(f"{indent}→ {full_name} points to unreadable double*")
                            else:
                                # 構造体などの場合
                                deref = var.Dereference()
                                if deref.IsValid() and deref.GetNumChildren() > 0:
                                    print(f"{indent}→ Deref {full_name}")
                                    children = [deref.GetChildAtIndex(i) for i in range(deref.GetNumChildren())]
                                    self.track(children, var_previous_values[name].children, line, vars_path + [name], full_name, depth + 1)
                        else:
                            children = [var.GetChildAtIndex(i) for i in range(num_children)]
                            self.track(children, var_previous_values[name].children, line, vars_path + [name], full_name, depth + 1)

                    except Exception as e:
                        print(f"{indent}→ {full_name} deref error: {e}")

                elif num_children > 0:
                    children = [var.GetChildAtIndex(i) for i in range(num_children)]
                    self.track(children, var_previous_values[name].children, line, vars_path + [name], full_name, depth + 1)

        def getValueAll(self):
            return {
                var_key[0]: {
                    var_key[1]: VariableValue(
                        value = self.previous_values[-1][var_key].value,
                        children = self.getValuesDict(self.previous_values[-1][var_key].children)
                    )
                } 
                for var_key in self.vars_declared[-1] if var_key in self.previous_values[-1]
            }
        
        def getValueAllEachFrame(self):
            var_dict_list: list[dict[str, dict[int | str, VariableValue]]] = []
            for i in range(len(self.vars_declared)):
                var_dict = {
                    var_key[0]: {
                        var_key[1]: VariableValue(
                            value = self.previous_values[i][var_key].value,
                            children = self.getValuesDict(self.previous_values[i][var_key].children)
                        )
                    } 
                    for var_key in self.vars_declared[i] if var_key in self.previous_values[i]
                }
                var_dict_list.append(var_dict)
            return var_dict_list
        
        def getGlobalValueAll(self):
            return {
                var_key[0]: {
                    var_key[1]: VariableValue(
                        value = global_previous_value.value, 
                        children = self.getValuesDict(global_previous_value.children)
                    )
                } 
                for var_key, global_previous_value in self.global_previous_values.items()
            }

        def getValuesDict(self, previous_values: dict[str, VarPreviousValue]):
            values_dict: dict[str, VariableValue] = {}
            for varname, previous_value in previous_values.items():
                values_dict[varname] = VariableValue(
                    value = previous_value.value, 
                    children = self.getValuesDict(previous_value.children)
                )
            return values_dict
        
        def getValuePartly(self, var_name: tuple[str, int], value_path: list[str]):
            temp_previous_value = self.previous_values[-1][var_name]
            while len(value_path):
                children_name = value_path.pop(0)
                temp_previous_value = temp_previous_value.children[children_name]
            return temp_previous_value.value

        # "item": {"value": aaa, "children": {}}
        def getValueByVar(self, varname: tuple[str, int], back=0):
            return self.getValueByVarDict(self.previous_values[int(-1+back)][varname])
            
        # {"value": bbb, "children": {0: {...}}...}
        def getValueByVarDict(self, previous_value: VarPreviousValue):
            value_var_declared_dict = VariableValue(
                value = previous_value.value,
                children = {}
            )
            for var_part, var_previous_value in previous_value.children.items():
                value_var_declared_dict["children"][var_part] = self.getValueByVarDict(var_previous_value)
            return value_var_declared_dict
        
        def set_variable_declared(self, name: tuple[str, int]):
            return self.vars_declared[-1].append(name)

    class DebugManager():
        def __init__(self):
            self.reset_state()
            self.vars_tracker = VarsTracker()
            self.rollback_index: int | None = None
            self.events_history: list[dict] = []
            self.process: lldb.SBProcess | None = None
            self.thread: lldb.SBThread | None = None
            self.is_english: bool = args.english

        def reset_state(self):
            self.is_end = False
            self.line_loop = []
            self.dynamic_comment_handler_being_checked: list[tuple[DynamicCommentHandler, int]] = []
            self.std_messages: list[str] = []
            self.input_check_num = {}
            self.stdin_buffer = ""
            self.file_check_num = {}
            self.file_info_to_send: list[FileInfo] = []
            self.memory_check_num = {}
            self.memory_info_to_send: list[MemoryAllocation | MemoryFree] = []
            self.str_check_num = {}
            self.str_info_to_send: list[StrcpyInfo] = []
            self.skipped_var_declaration_lines: list[str] = []
            ### return文のdynamic_comment_handlerはこのexpr_statusに設定する?
            self.expr_status_list: list[DynamicNonVarStatus] = []
            self.exprs_by_line: dict[str, NonVarComment] = {}

        def set_process_and_thread(self, process: lldb.SBProcess, thread: lldb.SBThread) -> None:
            self.process = process
            self.thread = thread

            if (next_state := self.get_next_state()):
                self.state, self.frame, self.file_name, self.next_line_number, self.func_crnt_name, self.next_frame_num = next_state
                with open(f"{DATA_DIR}/{self.file_name[:-2]}/{self.file_name[:-2]}_line.json", 'r') as f:
                    self.line_data: dict[str, dict] = json.load(f)
                    self.func_name = self.func_crnt_name
                    self.frame_num = 1
                    self.get_std_outputs()
                    self.event_sender(
                        SendEvent(
                            message = "The first step" if self.is_english else "最初の処理",
                            line = self.line_data[self.func_name]["start"], 
                            items = self.vars_tracker.getGlobalValueAll(), 
                            first_func = self.func_name, 
                            status = "ok"
                        ), 
                        False
                    )
                    self.line_number: int = self.line_data[self.func_name]["start"] - 1
                with open(f"{DATA_DIR}/{self.file_name[:-2]}/{self.file_name[:-2]}_variables.json", 'r') as f:
                    variables_info: dict[str, dict] = json.load(f)
                    self.vars_tracker.declared_variables_by_line = variables_info["declaration"]
                    self.exprs_by_line = variables_info["expr"]
            else:
                self.event_sender(
                    SendEvent(
                        message = "", 
                        is_end = True, 
                        status = "ok"
                    ), 
                    False
                )
                self.is_end = True

            self.vars_tracker.trackStart(self.frame)
            self.vars_checker()

        def step_conditionally(self, var_check: bool = True) -> None:
            # scanf フォーマット → Python 正規表現パターンの対応表
            scanf_patterns = {
                "%d": (r"[-+]?\d+", "符号付き10進整数"),
                "%i": (r"[-+]?(0[xX][0-9a-fA-F]+|0[0-7]*|\d+)", "符号付き整数(何進数かは自動判定)"),
                "%u": (r"\d+", "符号なし10進整数"),
                "%o": (r"[0-7]+", "8進整数"),
                "%x": (r"[0-9a-f]+", "16進整数(小文字)"),
                "%X": (r"[0-9A-F]+", "16進整数(大文字)"),
                "%f": (r"[-+]?\d*(\.\d+)?([eE][-+]?\d+)?", "固定小数点"),
                "%F": (r"[-+]?\d*(\.\d+)?([eE][-+]?\d+)?", "固定小数点(INF, NANも可)"),
                "%e": (r"[-+]?\d+(\.\d+)?[eE][-+]?\d+", "指数表記(小文字)"),
                "%E": (r"[-+]?\d+(\.\d+)?[eE][-+]?\d+", "指数表記(大文字)"),
                "%g": (r"[-+]?\d+(\.\d+)?([eE][-+]?\d+)?", "固定小数点または指数表記の短い方(小文字)"),
                "%G": (r"[-+]?\d+(\.\d+)?([eE][-+]?\d+)?", "固定小数点または指数表記の短い方(大文字)"),
                "%c": (r".", "1文字"),
                "%s": (r"\S+", "文字列(区切りとなる空白以外)"),
                "%p": (r"0x[0-9a-fA-F]+", "ポインタ"),
                "%n": (r"", "出力された文字の個数")
            }

            def skip_whitespace(text, pos):
                """空白・改行・タブをスキップ"""
                while pos < len(text) and text[pos].isspace():
                    pos += 1
                return pos

            def match_scanf(fmt: str, text: str):
                tokens = re.findall(r"%\*?[diuoxXfFeEgGcspn]", fmt)
                pos = 0
                results = []

                for i, token in enumerate(tokens):
                    if token.endswith("c"):
                        pass
                    elif token.endswith("n"):
                        results.append(str(pos))
                        continue
                    else:
                        pos = skip_whitespace(text, pos)

                    pat = scanf_patterns.get(token.lstrip("*"), (None, None))[0]
                    if not pat:
                        raise ValueError(f"Unsupported format specifier: {token}")

                    if pos >= len(text):
                        return "incomplete", results, "", {"incomplete": [f'{t}: {scanf_patterns.get(t.lstrip("*"), (r"", "不明な指定子"))[1]}' for t in tokens[i:]]}
                    
                    regex = re.compile(pat)
                    match = regex.match(text, pos)
                    # mismatchしたらscanfは終了して、mismatch以降の変数にはランダムな値が入るので、解析を終了する
                    if not match:
                        return "mismatch", results, text[pos:], {"mismatch": f'{token}: {scanf_patterns[token.lstrip("*")][1]}', "incomplete": [f'{t}: {scanf_patterns.get(t.lstrip("*"), (r"", "不明な指定子"))[1]}' for t in tokens[i+1:]]}

                    value = match.group(0)
                    # *がつく指定子では変数に代入しない
                    if not token.startswith("%*"):
                        results.append(value)
                    pos = match.end()

                return "ok", results, text[pos:], {}

            def is_complete_match(fmt: str, text: str):
                """入力文字列がフォーマット全体に合致するかを確認"""
                # stateは、incomplete, mismatch, okのどれか(これで入力の過不足一致不一致を確認する)
                # resultsは一致した入力の結果
                # remainingは入力の過分
                state, results, remaining_text, errors = match_scanf(fmt, text)
                return state, results, remaining_text, errors
            
            # プロセスの状態を更新
            if self.is_end:
                while True:
                    if (event := self.event_reciever()) is None:
                        continue
                    if event.get('type', None) == 'return' and event['fromTo'][0] == self.line_number:
                        self.event_sender(
                            SendEvent(
                                message = "Congraturations!! Here is a goal!!" if self.is_english else "おめでとうございます!! ここがゴールです!!", 
                                status = "ok", 
                                is_finished = True
                            )
                        )
                        raise ProgramFinished()
                    else:
                        self.event_sender(
                            SendEvent(
                                message = "Talk to a Return Character!!" if self.is_english else "returnキャラに話しかけてください!!", 
                                status = "ng"
                            )
                        )

            self.thread = self.frame.GetThread()
            self.process = self.thread.GetProcess()

            # 初期化されない変数や静的変数はスキップされるので、そのステップを後追いで見る
            # 変数が合致していればstepinを実行して次に進む

            while len(self.skipped_var_declaration_lines):
                line = self.skipped_var_declaration_lines.pop(0)
                
                skipped_varDecls = list(
                    [
                        (var["varNode"]["name"], int(line)) 
                        for var in self.vars_tracker.declared_variables_by_line[line]
                    ] &
                    self.vars_tracker.previous_values[self.next_frame_num-2].keys()
                )

                if len(skipped_varDecls) == 0:
                    continue

                vars_event: list[tuple[str, int]] = []
                errorCnt = 0
                while True:
                    if (event := self.event_reciever()) is None:
                        continue
                    if (item := event.get('item', None)) is not None:
                        var_to_get = (item["name"], item["line"])
                        if not var_to_get in skipped_varDecls or var_to_get[1] != int(line):
                            errorCnt += 1
                            # 複数回入力を間違えたらヒントをあげる
                            if errorCnt >= 3:
                                item_lacked_list = list(set(skipped_varDecls) - set(vars_event))
                                item_message = f"HINT: Get item {', '.join([item_lacked[0] for item_lacked in item_lacked_list])} !!" if self.is_english else f"ヒント: アイテム {', '.join([item_lacked[0] for item_lacked in item_lacked_list])} を取得してください!!"
                            else:
                                item_message = f"You are trying to get different item {var_to_get[0]} !!" if self.is_english else f"異なるアイテム {var_to_get[0]} を取得しようとしています!!"
                            
                            self.event_sender(
                                SendEvent(
                                    message = item_message,
                                    status = "ng"
                                )
                            )
                        else:
                            vars_event.append(var_to_get)

                            self.vars_tracker.set_variable_declared(var_to_get)
                            item_message = f"You got item {var_to_get[0]} !!" if self.is_english else f"アイテム {var_to_get[0]} を正確に取得できました!!"

                            is_all_acquired = Counter(vars_event) == Counter(skipped_varDecls)
                            
                            self.event_sender(
                                SendEvent(
                                    message = item_message, 
                                    item = DeclaredVariableInfo(
                                        value = self.vars_tracker.getValueByVar(var_to_get), 
                                        line = var_to_get[1],
                                        initialized = False
                                    ),
                                    status = "ok"
                                ),
                                not is_all_acquired
                            )

                            if is_all_acquired:
                                break
                    else:
                        errorCnt += 1
                        # 複数回入力を間違えたらヒントをあげる
                        if errorCnt >= 3:
                            items = list(set(skipped_varDecls) - set(vars_event))
                            item_message = f"HINT: Get items {', '.join([item_lacked[0] for item_lacked in items])} !!" if self.is_english else f"ヒント: アイテム {', '.join([item_lacked[0] for item_lacked in items])} を取得してください!!"
                        else:
                            item_message = "Get an item !!" if self.is_english else "何らかのアイテムを取得してください!!"

                        self.event_sender(
                            SendEvent(
                                message = item_message,
                                status = "ng"
                            )
                        )

            if str(self.next_line_number) in self.line_data[self.func_crnt_name]["input"] and (self.next_frame_num, self.next_line_number) not in self.input_check_num:
                self.input_check_num[(self.next_frame_num, self.next_line_number)] = (self.line_data[self.func_crnt_name]["input"][str(self.next_line_number)], -1)

            input_check = None
            if ((self.next_frame_num, self.next_line_number)) in self.input_check_num:
                if str(self.input_check_num[(self.next_frame_num, self.next_line_number)][1] + 1) in self.input_check_num[(self.next_frame_num, self.next_line_number)][0]:
                    input_check = str(self.input_check_num[(self.next_frame_num, self.next_line_number)][1] + 1)
                self.input_check_num[(self.next_frame_num, self.next_line_number)] = (self.input_check_num[(self.next_frame_num, self.next_line_number)][0], self.input_check_num[(self.next_frame_num, self.next_line_number)][1] + 1)

            # inputが入れられるまで次のstepには行かない
            if input_check:
                errorCnt = 0
                while True:
                    if (event := self.event_reciever()) is None:
                        continue
                    if (new_stdin := event.get('stdin', None)) is not None:
                        
                        # ここの引数の型がis_complete_matchと合致するように後で修正する
                        state, results, remaining, errors = is_complete_match(
                            self.input_check_num[(self.next_frame_num, self.next_line_number)][0][input_check][0], 
                            self.stdin_buffer + new_stdin
                        )
                        
                        if state == "incomplete":
                            errorCnt += 1
                            self.event_sender(
                                SendEvent(
                                    message = 
                                        (
                                            f"HINT: Missing input ({', '.join(errors['incomplete'])})!! input again !!" 
                                            if self.is_english else 
                                            f"ヒント: 入力({', '.join(errors['incomplete'])})が足りていません!! もう一度入力してください!!"
                                        )
                                        if errorCnt >= 3 else
                                        (
                                            "Missing input !! input again !!" 
                                            if self.is_english else 
                                            "入力が足りていません!! もう一度入力してください!!"
                                        ),
                                    status = "ng"
                                )
                            )
                            continue
                        self.stdin_buffer = remaining
                        self.process.PutSTDIN(new_stdin)
                        self.input_check_num[(self.next_frame_num, self.next_line_number)][0][input_check].pop(0)
                        if len(self.input_check_num[(self.next_frame_num, self.next_line_number)][0][input_check]):
                            self.event_sender(
                                SendEvent(
                                    message = "input again for scanf !!" if self.is_english else "次のscanf用に入力してください!!",
                                    status = "ok"
                                ), 
                                False
                            )
                        else:
                            break
                    else:
                        errorCnt += 1
                        self.event_sender(
                            SendEvent(
                                message = 
                                    (
                                        f"input values in the format ({self.input_check_num[(self.next_frame_num, self.next_line_number)][0][input_check][0]}) !!"
                                        if self.is_english else
                                        f"値をフォーマット({self.input_check_num[(self.next_frame_num, self.next_line_number)][0][input_check][0]})\nに沿って入力してください!!"
                                    ) 
                                    if errorCnt >= 3 else
                                    (
                                        "input values for scanf" 
                                        if self.is_english else 
                                        "値を入力してください!!"
                                    ),
                                status = "ng"
                            )
                        )

                self.input_check_num[(self.next_frame_num, self.next_line_number)][0].pop(input_check)
                if len(self.input_check_num[(self.next_frame_num, self.next_line_number)][0]) == 0:
                    self.input_check_num.pop((self.next_frame_num, self.next_line_number))

            self.analyze_non_var_expr_comments()

            if (next_state := self.get_next_state()):
                self.line_number = self.next_line_number
                self.func_name = self.func_crnt_name
                self.frame_num = self.next_frame_num
                self.state, self.frame, self.file_name, self.next_line_number, self.func_crnt_name, self.next_frame_num = next_state
                
                if var_check:
                    self.vars_tracker.trackStart(self.frame)

                ### ここから下の標準関数の解析はdynamic_comment_handlerのset_expr_commentsメソッドで行うことにする(予定)
                if input_check:
                    if state == "ok":
                        self.event_sender(
                            SendEvent(
                                message = f"values ({', '.join(results)}) were set to stdin !!" if self.is_english else f"値 ({', '.join(results)}) がstdinに入力されました!!",
                                status = "ok",
                                items = self.vars_tracker.getValueAll()
                            ), 
                            False
                        )
                    elif state == "mismatch":
                        message = (
                            f"values do not match to scanf format \n({errors['mismatch']})" 
                            if self.is_english else 
                            f"値がscanfのフォーマットに合致しませんでした、、、\n({errors['mismatch']}で合致していません!!)"
                        )
                        if errors["incomplete"]:
                            message += (
                                f"\fset random values for variables in\n{", ".join(errors["incomplete"])}" 
                                if self.is_english else 
                                f"\f{", ".join(errors["incomplete"])}\nに該当する変数にはランダムな値が設定されます"
                            )

                        self.event_sender(
                            SendEvent(
                                message = message,
                                status = "ok",
                                items = self.vars_tracker.getValueAll()
                            ),
                            False
                        )
                
                # fopen, fclose
                if str(self.line_number) in self.line_data[self.func_name]["file"] and (self.frame_num, self.line_number) not in self.file_check_num:
                    self.file_check_num[(self.frame_num, self.line_number)] = (self.line_data[self.func_name]["file"][str(self.line_number)], -1)

                if (self.frame_num, self.line_number) in self.file_check_num:
                    self.file_check_num[(self.frame_num, self.line_number)] = (self.file_check_num[(self.frame_num, self.line_number)][0], self.file_check_num[(self.frame_num, self.line_number)][1] + 1)
                    if str(self.file_check_num[(self.frame_num, self.line_number)][1]) in self.file_check_num[(self.frame_num, self.line_number)][0]:
                        file_check = str(self.file_check_num[(self.frame_num, self.line_number)][1])
                        for file_info in self.file_check_num[(self.frame_num, self.line_number)][0][file_check]:
                            file_info["address"] = self.frame.EvaluateExpression(file_info["varname"]).GetValue()
                            self.file_info_to_send.append(file_info)
                        self.file_check_num[(self.frame_num, self.line_number)][0].pop(file_check)
                        if len(self.file_check_num[(self.frame_num, self.line_number)][0]) == 0:
                            self.file_check_num.pop((self.frame_num, self.line_number))

                # malloc, realloc, free
                if str(self.line_number) in self.line_data[self.func_name]["memory"] and (self.frame_num, self.line_number) not in self.memory_check_num:
                    self.memory_check_num[(self.frame_num, self.line_number)] = (self.line_data[self.func_name]["memory"][str(self.line_number)], -1)

                if (self.frame_num, self.line_number) in self.memory_check_num:
                    self.memory_check_num[(self.frame_num, self.line_number)] = (self.memory_check_num[(self.frame_num, self.line_number)][0], self.memory_check_num[(self.frame_num, self.line_number)][1] + 1)
                    if str(self.memory_check_num[(self.frame_num, self.line_number)][1]) in self.memory_check_num[(self.frame_num, self.line_number)][0]:
                        memory_check = str(self.memory_check_num[(self.frame_num, self.line_number)][1])
                        for memory_info in self.memory_check_num[(self.frame_num, self.line_number)][0][memory_check]:
                            if memory_info["type"] in ["malloc", "realloc"]:
                                self.memory_info_to_send.append(
                                    {
                                        "type": memory_info["type"], 
                                        "size": str(self.frame.EvaluateExpression(f"{memory_info["size"]} / sizeof({memory_info["vartype"]})").GetValue()), 
                                        "vartype": memory_info["vartype"], 
                                        "source_address": memory_info.get("source_address", None)
                                    }
                                )
                                # self.memory_info_to_send.append({"type": memory_info["type"], "varname": memory_info["varname"], "size": str(self.frame.EvaluateExpression(f"{memory_info["size"]} / sizeof({memory_info["vartype"]})").GetValue()), "vartype": memory_info["vartype"], "address": self.frame.EvaluateExpression(memory_info["varname"]).GetValue(), "source_address": memory_info.get("source_address", None)})
                            else:
                                self.memory_info_to_send.append(
                                    {
                                        "type": memory_info["type"], 
                                        "varname": memory_info["varname"], 
                                        "address": self.frame.EvaluateExpression(memory_info["varname"]).GetValue()
                                    }
                                )
                        self.memory_check_num[(self.frame_num, self.line_number)][0].pop(memory_check)
                        if len(self.memory_check_num[(self.frame_num, self.line_number)][0]) == 0:
                            self.memory_check_num.pop((self.frame_num, self.line_number))

                # strcpy
                if str(self.line_number) in self.line_data[self.func_name]["string"] and (self.frame_num, self.line_number) not in self.str_check_num:
                    self.str_check_num[(self.frame_num, self.line_number)] = (self.line_data[self.func_name]["string"][str(self.line_number)], -1)

                if (self.frame_num, self.line_number) in self.str_check_num:
                    self.str_check_num[(self.frame_num, self.line_number)] = (self.str_check_num[(self.frame_num, self.line_number)][0], self.str_check_num[(self.frame_num, self.line_number)][1] + 1)
                    if str(self.str_check_num[(self.frame_num, self.line_number)][1]) in self.str_check_num[(self.frame_num, self.line_number)][0]:
                        str_check = str(self.str_check_num[(self.frame_num, self.line_number)][1])
                        for str_info in self.str_check_num[(self.frame_num, self.line_number)][0][str_check]:
                            self.str_info_to_send.append(
                                StrcpyInfo(
                                    value = self.frame.EvaluateExpression(str_info["original"]).GetValue(),
                                    original = str_info["original"],
                                    destination = str_info["destination"]
                                )
                            )
                        self.str_check_num[(self.frame_num, self.line_number)][0].pop(str_check)
                        if len(self.str_check_num[(self.frame_num, self.line_number)][0]) == 0:
                            self.str_check_num.pop((self.frame_num, self.line_number))
            else:
                self.is_end = True
                self.line_number = self.next_line_number

            self.get_std_outputs()

        def get_next_state(self) -> tuple[int, lldb.SBFrame, str, int, str, int] | None:
            state = self.process.GetState()

            frame: lldb.SBFrame = thread.GetFrameAtIndex(0)

            line_entry: lldb.SBLineEntry = frame.GetLineEntry()
            file_spec: lldb.SBFileSpec = line_entry.GetFileSpec()
            file_name = file_spec.GetFilename()
            line_number = line_entry.GetLine()
            func_name = frame.GetFunctionName()

            if func_name is None or file_name is None:
                return None
            
            frame_num = thread.GetNumFrames()
            
            # これで取得できるのは、16進数アドレスを10進数に変換したもの
            # print(frame.FindVariable("p").GetValueAsUnsigned())
            
            print(f"{func_name} at {file_name}:{line_number}")

            return state, frame, file_name, line_number, func_name, frame_num

        def get_std_outputs(self) -> None:
            # 新しい出力だけ読む
            out_chunk = stdout_r.read()
            err_chunk = stderr_r.read()

            if out_chunk:
                out_chunk = "/".join(out_chunk.rstrip("\n").split("\n"))
                self.std_messages.append(f"  [stdout]: {out_chunk}")
            if err_chunk:
                err_chunk = "/".join(err_chunk.rstrip("\n").split("\n"))
                self.std_messages.append(f". [stderr]: {err_chunk}")

        def get_vars_w_value_changed(self, values_changed: list[tuple[str, int]]) -> list[VariablePartWithValue]:
            value_changed_dict_list = []
            for value_changed in values_changed:
                for value_changed_tuple in self.vars_tracker.vars_changed[value_changed]:
                    value_path = [*value_changed_tuple]
                    value = self.vars_tracker.getValuePartly(value_changed, value_path.copy())
                    value_changed_dict_list.append(
                        VariablePartWithValue(
                            item = VariableDeclarationInfo(
                                name = value_changed[0],
                                line = value_changed[1]
                            ),
                            path = value_path,
                            value = value
                        )
                    )

            return value_changed_dict_list
        
        def get_vars_w_value_unchanged(self) -> list[VariablePartWithValue]:
            value_unchanged_dict_list = []
            for value_unchanged in self.vars_tracker.vars_unchanged:
                value_path = [*value_unchanged[1]]
                value = self.vars_tracker.getValuePartly(value_unchanged[0], value_path.copy())
                value_unchanged_dict_list.append(
                    VariablePartWithValue(
                        item = VariableDeclarationInfo(
                            name = value_unchanged[0][0],
                            line = value_unchanged[0][1]
                        ),
                        path = value_path,
                        value = value
                    )
                )
            return value_unchanged_dict_list
        
        def set_skipped_var_declaration(self, new_lines: list[str]):
            self.skipped_var_declaration_lines = new_lines
            for line in new_lines:
                self.vars_tracker.analyze_var_nodes(line, self.frame)

        def vars_checker(self, isForFalse: bool = False) -> None:
            if self.is_end:
                return
            
            # これだとスコープ外の変数を拾ってしまうことがある
            # for文の条件文内の宣言だとfalseの時にself.vars_tracker.declared_variables_by_line.get(str(self.line_number), [])でスコープ外の変数を取得してしまうことがある
            varsDeclLines: list[DynamicVarInfo] = (
                [

                ] 
                if isForFalse else 
                [
                    dynamic_variable_info
                    for dynamic_variable_info in self.vars_tracker.dynamic_variable_info_by_line.get(str(self.line_number), []) 
                    if (dynamic_variable_info["dynamic_var_node"]["name"], self.line_number) not in self.vars_tracker.vars_declared[-1]
                ]
            )

            varsDeclLines_copy = varsDeclLines[:]

            if len(varsDeclLines_copy):
                # やはり、変数は順番に取得させる
                while len(varsDeclLines_copy):
                    dynamic_variable_info = varsDeclLines_copy.pop(0)
                    var = (dynamic_variable_info["dynamic_var_node"]["name"], self.line_number)
                    errorCnt = 0
                    while True:
                        # 異なる変数の取得、または関数のスキップの後はメッセージを受信する
                        if (event := self.event_reciever()) is None:
                            continue

                        if (item := event.get('item', None)) is None:
                            errorCnt += 1
                            self.event_sender(
                                SendEvent(
                                    message = (
                                        "HINT: Get a correct item !!" 
                                        if self.is_english else 
                                        "アイテムを取得してください !!"
                                    ) 
                                    if errorCnt >= 3 else 
                                    (
                                        "You did a different action !!" 
                                        if self.is_english else 
                                        "異なる行動をしようとしています !!"
                                    ),
                                    status = "ng"
                                )
                            )
                            continue

                        var_to_get = (item["name"], item["line"])
                        if var_to_get != var:
                            errorCnt += 1
                            # 複数回入力を間違えたらヒントをあげる
                            self.event_sender(
                                SendEvent(
                                    message = (
                                        f"HINT: Get item {var[0]} !!" 
                                        if self.is_english else 
                                        f"ヒント: アイテム {var[0]} を取得してください!!"
                                    ) 
                                    if errorCnt >= 3 else 
                                    (
                                        f"You are trying to get a different item {var_to_get[0]} !!" 
                                        if self.is_english else 
                                        f"異なるアイテム {var_to_get[0]} を取得しようとしています!!"
                                    ),
                                    status = "ng"
                                )
                            )
                            continue

                        # 変数宣言の処理の行番は完全一致ではなくbetweenで確認する(条件分岐は引き続き完全一致で?)
                        if self.line_number_track < event["start"] or event["end"] < self.line_number:
                            errorCnt += 1
                            self.event_sender(
                                SendEvent(
                                    message = (
                                        f"HINT: Get item {var[0]} !!" 
                                        if self.is_english else 
                                        f"ヒント: アイテム {var[0]} を取得してください!!"
                                    )
                                    if errorCnt >= 3 else
                                    (
                                        f"You are trying to get a different item {var_to_get[0]} !!" 
                                        if self.is_english else 
                                        f"異なるアイテム {var_to_get[0]} を取得しようとしています!!"
                                    ),
                                    status = "ng"
                                )
                            )
                            continue

                        # current_comment is None = 未処理の関数がない = アイテムを正しく取得できた → 次の変数に移る
                        if (current_comment := dynamic_variable_info["current_comment_w_index"]) is None:
                            # 取得した変数を宣言済リストに登録する
                            self.vars_tracker.set_variable_declared(var)

                            # まだ全ての宣言が完了していない場合
                            if len(varsDeclLines_copy):
                                self.event_sender(
                                    SendEvent(
                                        message = f"You got item {var[0]} !!" if self.is_english else f"アイテム {var[0]} を正確に取得できました!!",
                                        status = "ok",
                                        item = DeclaredVariableInfo(
                                            value = self.vars_tracker.getValueByVar(var),
                                            line = var[1],
                                            initialized = dynamic_variable_info["dynamic_var_node"]["initialized"]
                                        ),
                                        skipped_function_list = dynamic_variable_info["skipped_function_list"]
                                    ), 
                                    False
                                )
                            # 全ての宣言が完了している場合
                            else:
                                # vars_changedとvarsTrackerの共通項とvarsDeclLinesの差項を、値が変化した変数として検知する
                                # vars_changedにもkeysを使って宣言済みかつ値が変わった変数を取得できる
                                values_changed = []
                                for varname in self.vars_tracker.vars_changed.keys():
                                    if varname in self.vars_tracker.vars_declared[-1] and varname not in varsDeclLines:
                                        values_changed.append(varname)
                                # # その後、varsChangedをキーとしてvars_changedの変更値を取得する
                                # value_changed_dict = self.get_vars_w_value_changed(values_changed)
                                # 変数が初期化されない時、スキップされるので、それも読み取る
                                vars_declared = self.vars_tracker.vars_declared[self.next_frame_num - 2]

                                self.set_skipped_var_declaration([
                                    line for line in self.vars_tracker.declared_variables_by_line
                                    if (self.line_number < int(line) < self.next_line_number)
                                    and 
                                    {
                                        (var["name"], int(line))
                                        for var in self.vars_tracker.declared_variables_by_line[line]
                                        if (var["name"], int(line)) not in vars_declared
                                    }
                                ])
                                
                                self.event_sender(
                                    SendEvent(
                                        message = f"You got item {var[0]} !!" if self.is_english else f"アイテム {var[0]} を正確に取得できました!!", 
                                        status = "ok",
                                        item = DeclaredVariableInfo(
                                            value = self.vars_tracker.getValueByVar(var), 
                                            line = var[1],
                                            initialized = dynamic_variable_info["dynamic_var_node"]["initialized"]   
                                        ),
                                        vars_w_value_changed = self.get_vars_w_value_changed(values_changed), 
                                        vars_w_value_unchanged = self.get_vars_w_value_unchanged(),
                                        skipped_function_list = dynamic_variable_info["skipped_function_list"]
                                    ), 
                                    str(self.line_number) not in self.line_data[self.func_name]["loops"])
                            break

                        # non_varの時と同じくこのメソッドで次の関数を解析する
                        self.analyze_next_function(dynamic_variable_info)
            else:
                values_changed = []
                for varname in self.vars_tracker.vars_changed.keys():
                    if varname in self.vars_tracker.vars_declared[-1] and varname not in varsDeclLines:
                        values_changed.append(varname)

                # if, while True, while False, for In, for True, for False, switch Caseによる値の変化は無視できるようにする
                if len(values_changed) != 0:
                    if self.line_number in self.line_data[self.func_name]["lines"]:
                        self.vars_tracker.vars_changed = {var: self.vars_tracker.vars_changed[var] for var in values_changed}
                        # 変数が初期化されない時、スキップされるので、それも読み取る
                        vars_declared = self.vars_tracker.vars_declared[self.next_frame_num - 2]

                        self.set_skipped_var_declaration([
                            line for line in self.vars_tracker.declared_variables_by_line
                            if (self.line_number < int(line) < self.next_line_number)
                            and 
                            {
                                (var["name"], int(line))
                                for var in self.vars_tracker.declared_variables_by_line[line]
                                if (var["name"], int(line)) not in vars_declared
                            }
                        ])

        # 変数宣言以外の計算式の解析
        def analyze_non_var_expr_comments(self):
            if self.next_line_number not in self.exprs_by_line:
                self.thread.StepInto()
                return

            if len(self.expr_status_list) == 0 or self.expr_status_list[-1]["line"] != self.next_line_number:
                self.set_expr_status(self.exprs_by_line[self.next_line_number], self.next_line_number)

            expr_status = self.expr_status_list[-1]

            if expr_status["type"] == "return" and expr_status["dynamic_expr"].is_analysis_potentially_completed():
                self.thread.StepOut()
            else:
                self.thread.StepInto()

            if expr_status["type"] == "if":
                if len(expr_status["results"]) and expr_status["results"][-1] is True:
                    return
                
                for dynamic_comment_handler in expr_status["dynamic_conditions"][len(expr_status["results"]):]:
                    # まずは解析
                    if dynamic_comment_handler.set_expr_comments(self.frame):
                        # 解析が途中で終了する = 自作関数が現れた → ひとまずは解析を終了する
                        break
                    
                    # 解析終了 → 本条件の値の真偽値を取得し、その結果をresultsに格納する
                    result = dynamic_comment_handler.get_result_bool(self.frame)
                    expr_status["results"].append(result)

                    # 条件がTrueならそれ以降の条件は確認しないので
                    if result is True:
                        break
            elif expr_status["type"] == "while" or expr_status["type"] == "do_while":
                if expr_status["result"] is not None:
                    return
                
                dynamic_comment_handler = expr_status["dynamic_condition"]
                if dynamic_comment_handler.set_expr_comments(self.frame):
                    return
                
                result = dynamic_comment_handler.get_result_bool(self.frame)
                expr_status["result"] = result
            elif expr_status["type"] == "for":
                # is_firstがTrue = まだ初期化が済んでいない
                if expr_status["is_first"]:
                    # 初期化部があるならその解析を行う
                    if "initializer" in expr_status:
                        if "var_initializer" in expr_status:
                            sys.exit("variable initializer cannot be mixed with normal initializer")
                        
                        dynamic_comment_handler = expr_status["initializer"]["dynamic_expr"]
                        if (dynamic_comment_handler.set_expr_comments(self.frame)):
                            return

                    elif "var_initializer" in expr_status:
                        if "initializer" in expr_status:
                            sys.exit("normal initializer cannot be mixed with variable initializer")
                        return
                    
                    # 条件がない = 常に条件がTrue → 解析しない
                    if expr_status["condition"] is None:
                        return
                    
                    dynamic_comment_handler = expr_status["condition"]["dynamic_expr"]
                    if dynamic_comment_handler.set_expr_comments(self.frame):
                        return
                    
                    expr_status["is_first"] = True
                else:
                    if "initializer" in expr_status or "var_initializer" in expr_status:
                        sys.exit("initializer or var_initializer have to be already done")
                    
                    # is_initializer is True = 条件部に戻ってきた → その前に変更式の解析を行う
                    if "change" in expr_status and expr_status["change"]["is_not_completed"]:
                        if expr_status["change"]["dynamic_expr"] is None:
                            expr_status["change"]["dynamic_expr"] = DynamicCommentHandler(comments = expr_status["change"]["expr"])
                        dynamic_comment_handler = expr_status["change"]["dynamic_expr"]
                        dynamic_comment_handler.set_expr_comments(self.frame)
                        return
                    
                    # 条件がない = 常に条件がTrue → 解析しない
                    if expr_status["condition"] is None:
                        return
                    
                    dynamic_comment_handler = expr_status["condition"]["dynamic_expr"]
                    dynamic_comment_handler.set_expr_comments(self.frame)
            elif expr_status["type"] == "switch":
                # matched_caseがNoneではない = 何らかのcaseが条件式の値と合致したことが確認済み = ラベル式の値の計算は終了済み
                if expr_status["matched_case"] is not None:
                    return
                
                # resultがNone = 条件文の計算処理は完了していない → その処理を実行しにいく
                if expr_status["condition"]["result"] is None:
                    dynamic_comment_handler = expr_status["condition"]["dynamic_condition"]
                    if dynamic_comment_handler.set_expr_comments(self.frame):
                        return
                    
                    if (result := dynamic_comment_handler.expr_result_by_id[-1]) is None:
                        sys.exit("error in result of switch condition")
                    
                    expr_status["condition"]["result"] = result

                for i, case_expr_list in enumerate(expr_status["case_expr_list_by_index"]):
                    for j, case_expr in enumerate(case_expr_list):
                        if case_expr["result"] is None:
                            if case_expr["dynamic_case_expr"].set_expr_comments(self.frame):
                                return
                            
                            if (result := case_expr["dynamic_case_expr"].expr_result_by_id[-1]) is None:
                                sys.exit("error in result of case expression")

                            case_expr["result"] = result

                        if expr_status["condition"]["result"] == case_expr["result"] != None:
                            expr_status["matched_case"] = ','.join([i,j])
                            return
            elif expr_status["type"] == "expression":
                if expr_status["dynamic_expr"].expr_result_by_id[-1] is not None:
                    return
                expr_status["dynamic_expr"].set_expr_comments(self.frame)
            elif expr_status["type"] == "return":
                if expr_status["dynamic_expr"].set_expr_comments(self.frame) is None:
                    return
                
                # これで取得するのか?
                return_value = thread.GetStopReturnValue().GetValue()
                expr_status["result"] = return_value

        # 次の処理の内容を取得する
        def set_expr_status(self, expr: NonVarComment, line: str):
            if expr["type"] == "if":
                conditions: list[list[Comment]] = [
                    value for _, value in sorted(expr["condition"].items())
                ]
                expr_status = IfStatus(
                    type = expr["type"],
                    line = line,
                    conditions = conditions,
                    dynamic_conditions = [
                        DynamicCommentHandler(comments = comments) 
                        for comments in conditions
                    ],
                    results = []
                )
            elif expr["type"] == "while":
                expr_status = WhileStatus(
                    type = expr["type"],
                    line = line,
                    condition = expr["condition"],
                    dynamic_condition = DynamicCommentHandler(comments = expr["condition"]),
                    result = None
                )
            elif expr["type"] == "do_while":
                expr_status = DoWhileStatus(
                    type = expr["type"],
                    line = line,
                    condition = expr["condition"],
                    dynamic_condition = DynamicCommentHandler(comments = expr["condition"]),
                    result = None
                )
            elif expr["type"] == "for":
                expr_status = ForStatus(
                    type = expr["type"],
                    line = line,
                    condition = ForConditionStatus(
                        expr = expr["condition"],
                        dynamic_expr = DynamicCommentHandler(comments = expr["condition"]), 
                        result = None
                    ) if expr["condition"] else None,
                    is_first = True
                )
                
                if "initializer" in expr:
                    expr_status["initializer"] = ForInitializerStatus(
                        expr = expr["initializer"],
                        dynamic_expr = DynamicCommentHandler(comments = expr["initializer"]),
                    )

                if "var_initializer" in expr:
                    self.vars_tracker.dynamic_variable_info_by_line[line] = [
                        DynamicVarInfo(
                            dynamic_var_node = self.vars_tracker.transform_2_dynamic_var_node(var_info["varNode"]),
                            start = var_info["start"],
                            end = var_info["end"],
                            skipped_function_list = [],
                            current_comment = None
                        ) for var_info in expr["var_initializer"]
                    ]

                    expr_status["var_initializer"] = ForVarInitializerStatus(
                        required = [
                            (var_info["varNode"]["name"], int(line)) 
                            for var_info in expr["var_initializer"]
                        ],
                    )

                if "change" in expr:
                    expr_status["change"] = ForChangeStatus(
                        expr = expr["change"],
                        # 一回目のループ直前には変更式に到達することはないのでDynamicCommentHandlerは生成しない
                        dynamic_expr = None,
                        is_not_completed = True
                    )
            elif expr["type"] == "switch":
                if None in expr["case_exprs"]:
                    sys.exit("None cannot be included in case exprs")

                expr_status = SwitchStatus(
                    type = expr["type"],
                    line = line,
                    condition = SwitchConditionStatus(
                        condition = expr["condition"],
                        dynamic_condition = DynamicCommentHandler(comments = expr["condition"]),
                        result = None
                    ),
                    case_expr_list_by_index = [
                        [
                            CaseStatus(
                                case_expr = case_expr,
                                dynamic_case_expr = DynamicCommentHandler(
                                    comments = case_expr
                                ),
                                result = None
                            )
                            for case_expr in case_expr_list
                        ] for case_expr_list in expr["case_exprs"]
                    ],
                    matched_case = None
                )
            elif expr["type"] in ("continue", "break"):
                expr_status = ControlFlowStatus(
                    type = expr["type"],
                    line = line
                )
            elif expr["type"] == "expression":
                expr_status = ExpressionStatus(
                    type = expr["type"],
                    line = line,
                    expr = expr["expr"],
                    dynamic_expr = DynamicCommentHandler(comments = expr["expr"])
                )
            else:
                expr_status = ReturnStatus(
                    type = expr["type"],
                    line = line,
                    expr = expr["expr"],
                    dynamic_expr = DynamicCommentHandler(comments = expr["expr"]),
                    result = None
                )
            
            self.expr_status_list.append(expr_status)

        # スキップされた関数を取得する
        # ただし、そもそも関数の存在があり得ない処理文に関してはNoneを返す
        def get_skipped_functions_non_var(self, expr_status: DynamicNonVarStatus):
            if expr_status["type"] == "if":
                return [dynamic_comment_handler.skipped_function_list for dynamic_comment_handler in expr_status["dynamic_conditions"]]
            elif expr_status["type"] == "while" or expr_status["type"] == "do_while":
                return [expr_status["dynamic_condition"].skipped_function_list]
            elif expr_status["type"] == "for":
                if "initializer" in expr_status:
                    return [expr_status["initializer"]["dynamic_expr"].skipped_function_list]
                elif "change" in expr_status and expr_status["change"]["dynamic_expr"] is not None:
                    return [expr_status["change"]["dynamic_expr"].skipped_function_list]
                elif (for_condition_status := expr_status["condition"]) is not None:
                    return [for_condition_status["dynamic_expr"].skipped_function_list]
                else:
                    return None
            elif expr_status["type"] == "switch":
                return [expr_status["condition"]["dynamic_condition"].skipped_function_list]
            elif expr_status["type"] == "expression":
                return [expr_status["dynamic_expr"].skipped_function_list]
            elif expr_status["type"] == "return":
                return [expr_status["dynamic_expr"].skipped_function_list]
            else:
                sys.exit("continue or break statement have not to have any fucntions")

        def get_next_function_non_var(self, expr_status: DynamicNonVarStatus):
            # 次の関数が在するfunction_groupのインデックス
            index = 0

            if expr_status["type"] == "if":
                if True in expr_status["results"] or len(expr_status["results"]) == len(expr_status["conditions"]):
                    sys.exit("this if statement is already completely scanned")

                dynamic_comment_handler = expr_status["dynamic_conditions"][len(expr_status["results"])]
                index = len(expr_status["results"])
            elif expr_status["type"] == "while" or expr_status["type"] == "do_while":
                dynamic_comment_handler = expr_status["dynamic_condition"]
            elif expr_status["type"] == "for":
                if "initializer" in expr_status:
                    dynamic_comment_handler = expr_status["initializer"]["dynamic_expr"]
                elif "change" in expr_status and expr_status["change"]["dynamic_expr"] is not None:
                    dynamic_comment_handler = expr_status["change"]["dynamic_expr"]
                elif (for_condition_status := expr_status["condition"]) is not None:
                    dynamic_comment_handler = for_condition_status["dynamic_expr"]
                else:
                    sys.exit("next function is not found")
            elif expr_status["type"] == "switch":
                dynamic_comment_handler = expr_status["condition"]["dynamic_condition"]
            elif expr_status["type"] == "expression":
                dynamic_comment_handler = expr_status["dynamic_expr"]
            elif expr_status["type"] == "return":
                dynamic_comment_handler = expr_status["dynamic_expr"]
            else:
                sys.exit("continue or break statement have not to have any fucntions")

            # 次の関数のコメントと、それが在するfunction_groupのインデックスを返す
            return dynamic_comment_handler, index
            
        def get_skipped_functions_var(self, var_info: DynamicVarInfo):
            return var_info["skipped_function_list"]

        def check_expr_status(self, execution_info: ExecutionInfo):
            if len(self.expr_status_list) == 0:
                return False
            
            current_expr_status = self.expr_status_list[-1]
            
            if current_expr_status["line"] != execution_info["line"]:
                return False
            
            send_event = SendEvent(
                message = "",
                status = "ok",
            )

            if current_expr_status["type"] == "if" and execution_info["type"] == "if":
                # true_condition_index = 0,1,2,...
                if execution_info["true_condition_index"] == -1:
                    if True in current_expr_status["results"]:
                        return False
                    
                    # まだ解析できていない条件がある
                    if len(current_expr_status["results"]) != len(current_expr_status["conditions"]):
                        self.analyze_next_function(current_expr_status)
                        return True
                    
                    # 全ての条件がFalse → どの条件にも該当しない = true_case_indexは-1で正しい
                else:
                    # 今回選んだ条件より前の条件が正しい = 間違った条件を選んだ
                    if True in current_expr_status["results"][:execution_info["true_condition_index"]]:
                        return False
                    
                    # まだ探索中であれば(どこかしらの自作関数で止まっているなら)、その関数を確かめる方向に行く
                    if len(current_expr_status["results"]) <= execution_info["true_condition_index"]:
                        self.analyze_next_function(current_expr_status)
                        return True

                    # 間違った条件を選んだ
                    if current_expr_status["results"][execution_info["true_condition_index"]] is False:
                        return False
                    
                    # executioin_info["true_condition_index"]番目の条件が正しい → 正しい条件を選んだ   
            elif (current_expr_status["type"] == "while" and execution_info["type"] == "while") or (current_expr_status["type"] == "do_while" and execution_info["type"] == "do_while"):
                if current_expr_status["result"] is None:
                    self.analyze_next_function(current_expr_status)
                    return True
                
                if current_expr_status["result"] is not execution_info["condition"]:
                    return False
                
                if not execution_info["condition"]:
                    self.set_skipped_var_declaration([
                        line for line in self.vars_tracker.declared_variables_by_line
                        if self.line_number < int(line) < self.next_line_number
                    ])
            elif current_expr_status["type"] == "for":
                if execution_info["type"] == "for":
                    if "initializer" in current_expr_status or "var_initializer" in current_expr_status:
                        return False
                    
                    if "change" in current_expr_status and current_expr_status["change"]["dynamic_expr"] is not None:
                        return False
                    
                    for_condition_status = current_expr_status["condition"]
                    if for_condition_status is None:
                        if execution_info["condition"]:
                            return {}
                        else:
                            return False
                    
                    if for_condition_status["result"] is not None:
                        self.analyze_next_function(current_expr_status)
                        return True
                    
                    if for_condition_status["result"] is not execution_info["condition"]:
                        return False

                    if not execution_info["condition"]:
                        self.set_skipped_var_declaration([
                            line for line in self.vars_tracker.declared_variables_by_line
                            if self.line_number < int(line) < self.next_line_number
                        ])
                elif execution_info["type"] == "for_initializer":
                    if "initializer" not in current_expr_status:
                        return False
                    
                    if current_expr_status["initializer"]["dynamic_expr"].current_function_comment is not None:
                        self.analyze_next_function(current_expr_status)
                        return True
                    
                    # 初期化時(結果がNoneでない場合)はそのコメント(result)を取得する
                    initializer_str = current_expr_status["initializer"]["dynamic_expr"].get_str_after_analysis_completed()
                    current_expr_status.pop("initializer")

                    return {}
                elif execution_info["type"] == "for_change":
                    if "change" not in current_expr_status:
                        return False
                    
                    dynamic_comment_handler = current_expr_status["change"]["dynamic_expr"]

                    if dynamic_comment_handler is None:
                        return False
                    
                    if dynamic_comment_handler.current_function_comment is not None:
                        self.analyze_next_function(current_expr_status)
                        return True
                        
                    # 変更式があるならその内容を登録する
                    change_str = dynamic_comment_handler.get_str_after_analysis_completed()
                    
                    current_expr_status["change"]["dynamic_expr"] = None
                    return {}
                else:
                    return False
            elif current_expr_status["type"] == "switch" and execution_info["type"] == "switch":
                # condition_resultがまだ解析中ならその内容を返す
                if current_expr_status["condition_result"] is None:
                    self.analyze_next_function(current_expr_status)
                    return True
                
                if execution_info["true_case_index"] == -1:
                    # どこかしらの条件がTrue → 間違った条件を選んでいる
                    if any(result["condition"] is True for result in current_expr_status["case_results"]):
                        return False
                    
                    # 全ての条件がFalse → どの条件にも該当しない = true_case_indexは-1で正しい
                    if len(all(result["condition"] is False for result in current_expr_status["case_results"])) != len(current_expr_status["case_results"]):
                        # まだ探索中であれば(どこかしらの自作関数で止まっているなら)、その関数を確かめる方向に行く
                        self.analyze_next_function(current_expr_status)
                        return True
                else:
                    # 今回のアクション以前のcase群でTrueとなっているものがあるなら、そのcase群を選んでいないこととなるので、アクションが間違っていることとなる
                    if any(result["condition"] is True for result in current_expr_status["case_results"][:execution_info["true_case_index"]]):
                        return False
                    
                    # まだ探索中であれば(どこかしらの自作関数で止まっているなら)、その関数を確かめる方向に行く
                    if len(current_expr_status["case_results"]) <= execution_info["true_case_index"]:
                        self.analyze_next_function(current_expr_status)
                        return True
                    
                    # 間違った条件を選んだ
                    if current_expr_status["results"][execution_info["true_case_index"]] is False:
                        return False
            elif (current_expr_status["type"] == "continue" and execution_info["type"] == "continue") and (current_expr_status["type"] == "break" and execution_info["type"] == "break"):
                # lineがあっている時点で正しい → 正しいcontinueまたはbreakを選んでいる
                pass
            elif current_expr_status["type"] == "expression" and execution_info["type"] == "expression":
                # 計算式を解析し終わっている → 次のアクションに進める → 計算式の結果を取得する
                if current_expr_status["result"] is None:
                    self.analyze_next_function(current_expr_status)
                    return True
            elif current_expr_status["type"] == "return" and execution_info["type"] == "return":
                # 計算式の解析が終わっている → 次のアクションに進める → 計算式の結果を取得する
                result = current_expr_status["result"]
                if result is None:
                    self.analyze_next_function(current_expr_status)
                    return True

                if len(self.dynamic_comment_handler_being_checked):
                    dynamic_comment_handler, index = self.dynamic_comment_handler_being_checked[-1]
                    send_event["function_return_info"] = FunctionReturnInfo(
                        func_name = dynamic_comment_handler.get_current_function(),
                        index = index,
                        return_value = result
                    )
                    dynamic_comment_handler.set_function_comment(result)
            else:
                return False

            send_event["skipped_function_list"] = self.get_skipped_functions_non_var(current_expr_status)
            send_event["vars_w_value_changed"] = self.get_vars_w_value_changed(list(self.vars_tracker.vars_changed.keys())), 
            send_event["vars_w_value_unchanged"] = self.get_vars_w_value_unchanged()
            
            self.event_sender(send_event)
            
            self.expr_status_list.pop(-1)

            return {}
        
        def analyze_next_function(self, expression_info_being_analyzed: DynamicNonVarStatus | DynamicVarInfo):
            if "dynamic_var_node" in expression_info_being_analyzed:
                skipped_function_list = self.get_skipped_functions_var(expression_info_being_analyzed)
                current_comment_w_index = expression_info_being_analyzed["current_comment_w_index"]
            else:
                skipped_function_list = self.get_skipped_functions_non_var(expression_info_being_analyzed)
                current_comment_w_index = self.get_next_function_non_var(expression_info_being_analyzed)

            if current_comment_w_index is None:
                sys.exit("function comment is not found even though next functions is being analyzed")

            current_comment_handler, index = current_comment_w_index
            current_function_comment = current_comment_handler.current_function_comment
            if current_function_comment is None:
                sys.exit("function comment is not found even though next functions is being analyzed")

            if self.func_crnt_name != current_function_comment["func_name"]:
                sys.exit(f"function which is currently handled by current comment does not match self.func_crnt_name {self.func_crnt_name}")

            self.event_sender(
                SendEvent(
                    message = f"Will you skip function \"{self.func_crnt_name}\" ?" if self.is_english else f"遷移先の関数 {self.func_crnt_name} の処理をスキップしますか?",
                    status = "ok", 
                    skip = True,
                    skipped_function_list = skipped_function_list
                )
            )
            event = self.event_reciever()

            if self.next_frame_num > self.frame_num:
                if event.get('skip', False):
                    back_line_number = self.line_number
                    back_frame_num = self.frame_num
                    while True:
                        self.step_conditionally()
                        
                        if back_line_number == self.next_line_number and back_frame_num == self.next_frame_num:
                            return_value = thread.GetStopReturnValue().GetValue()
                            current_comment_handler.set_function_comment(return_value)

                            self.event_sender(
                                SendEvent(
                                    message = "function skip is completed" if self.is_english else "スキップが完了しました", 
                                    status = "ok", 
                                    items = self.vars_tracker.getValueAll(), 
                                    func = self.func_crnt_name,
                                    function_return_info = FunctionReturnInfo(
                                        func_name = current_comment_handler.get_current_function(),
                                        index = index,
                                        return_value = return_value
                                    )
                                )
                            )

                        if back_line_number == self.line_number and back_frame_num == self.frame_num:
                            break
                else:
                    funcWarp = event["funcWarp"]
                    self.event_sender(
                        SendEvent(
                            message = f"skip is canceled. move to function {self.func_crnt_name}" if self.is_english else f"スキップをキャンセルしました。関数 {self.func_crnt_name} に遷移します", 
                            status = "ok", 
                            func = self.func_name, 
                            from_line = self.line_number, 
                            next_func = NextFunctionInfo(
                                name = funcWarp["name"], 
                                x = funcWarp["x"], 
                                y = funcWarp["y"], 
                                items = {
                                    argname: {
                                        arg_info["line"]: ArgumentItemInfo(
                                            value = self.vars_tracker.getValueByVar((argname, arg_info["line"])), 
                                            type = arg_info["type"]
                                        )
                                    }
                                    for argname, arg_info in funcWarp['args'].items()
                                }
                            )
                        )
                    )
                    self.dynamic_comment_handler_being_checked.append((current_comment_handler, index))
                    back_line_number = self.line_number
                    back_frame_num = self.frame_num
                    self.set_skipped_var_declaration([line for line in self.variable_declarations_by_line if int(line) < self.next_line_number])
                    while True:
                        if self.analyze_frame(back_line_number):
                            continue
                        if back_line_number == self.line_number and back_frame_num == self.frame_num:
                            break
                    self.dynamic_comment_handler_being_checked.pop(-1)
            # ここはインライン関数が来る可能性がある? (今はまだ対応しない)
            else:
                sys.exit("error in function move")

        def analyze_frame(self, backToLine: int | None = None) -> int: # Literal[PROGRESS, CONTINUE]
            skipStart = None
            skipEnd = None

            if self.line_data.get(self.func_name, None) and self.line_number in self.line_data[self.func_name]["lines"] and not self.is_end:
                if (event := self.event_reciever()) is None:
                    return CONTINUE
                
                execution_info: ExecutionInfo | None = event.get("execution_info")

                if execution_info is not None:
                    # ここで何が返されるかによって次のアクションに向かうか、今のアクションを解析するか、間違ったアクションをしたのかを解析する
                    if (result := self.check_expr_status(execution_info)) is False:
                        self.event_sender(
                            SendEvent(
                                message = "You did a different action !!" if self.is_english else "異なる処理に対するアクションをしました!!", 
                                status = "ng"
                            )
                        )
                        return CONTINUE
                else:
                    self.event_sender(
                        SendEvent(
                            message = "You did a different action !!" if self.is_english else "異なる処理に対するアクションをしました!!", 
                            status = "ng"
                        )
                    )
                    return CONTINUE
                
            self.step_conditionally()
            self.vars_checker()

            if (len(self.expr_status_list) and self.expr_status_list[-1]["type"] == "for" and self.expr_status_list[-1].get("var_initializer", {}).get("required", [])):
                vars_declared = set(self.vars_tracker.vars_declared[-1])
                vars_required = self.expr_status_list[-1]["var_initializer"]["required"]
                self.expr_status_list[-1]["var_initializer"]["required"] = [v for v in vars_required if v not in vars_declared]
                if len(self.expr_status_list[-1]["var_initializer"]["required"]):
                    self.expr_status_list[-1].pop("var_initializer")

            return PROGRESS

        def event_reciever(self) -> dict | None:
            # JSONが複数回に分かれて送られてくる可能性があるためパース

            # rollbackアクションにて処理を再実行している最中は一処理につきindexをインクリメントする
            # この繰り返しで、rollback_indexがlen(self.events_history)と等しくなったとき、rollback終了の合図メッセージをゲーム側に送信する
            if self.rollback_index is not None:
                event = self.events_history[self.rollback_index]
                self.rollback_index += 1
                return event
            
            data = conn.recv(1024)
            # ここは後々変えるかも
            if not data:
                raise NoConnection()
            
            event = json.loads(data.decode())
            if "rollback" in event:
                self.event_sender(
                    SendEvent(
                        message = "", 
                        status = "rollback"
                    )
                )
                data = conn.recv(1024)
                # ここは後々変えるかも
                if not data:
                    raise NoConnection()
                
                event = json.loads(data.decode())
                if event["rollback"]:
                    self.reset_state()
                    self.events_history[:] = self.events_history[:event["index"]]
                    raise RollBack()
                else:
                    self.event_sender(
                        SendEvent(
                            message = "", 
                            status = "rollback_fail"
                        )
                    )
                    return None
            else:
                self.events_history.append(event)
            return event
    
        def event_sender(self, send_event: SendEvent, getLine: bool = True) -> None:
            if self.rollback_index is not None:
                '''
                処理を再実行していき、events_historyの大きさとrollback_indexが等しくなったらプレイヤーが指定した処理を全て再実行
                できたことになるのでrollbackアクションが終了したことを示すメッセージを送信する
                同時に現時点での全ての変数の内容もゲーム側に反映させるために送信する
                '''
                if len(self.events_history) != self.rollback_index:
                    return
                
                send_event = SendEvent(
                    message = "",
                    status = "rollback_success", 
                    gvars = self.vars_tracker.getGlobalValueAll(), 
                    vars = self.vars_tracker.getValueAllEachFrame()
                )

                # ゲーム側で行番は取得済みなのでgetLineフラグはFalseにする
                getLine = False
                self.rollback_index = None
            
            # 正しいアクションを実行した時のみ送信するメッセージに情報を追加していく
            if send_event["status"] == "ok" or send_event["status"] == "rollback_success":
                # 標準
                send_event["std"] = self.std_messages

                send_event["files"] = self.file_info_to_send
                self.file_info_to_send = []

                send_event["memory"] = self.memory_info_to_send
                self.memory_info_to_send = []

                send_event["str"] = self.str_info_to_send
                self.str_info_to_send = []

                if getLine:
                    if len(self.skipped_var_declaration_lines):
                        # 初期化されていない変数はスキップされてしまうので、そのような変数があるなら最初の行数を取得する
                        send_event["line"] = int(self.skipped_var_declaration_lines[0])
                    else:
                        if self.line_loop and self.line_data[self.func_name]["loops"].get(str(self.line_loop[-1])) == self.next_line_number:
                            send_event["line"] = self.line_loop[-1]
                        else:
                            send_event["line"] = self.next_line_number
                    # スコープから外れて除外された変数を取り除く
                    send_event["removed"] = [
                        VariableDeclarationInfo(
                            name = var_removed[0], 
                            line = var_removed[1]
                        )
                        for var_removed in self.vars_tracker.vars_removed
                    ]
                    self.vars_tracker.vars_removed = set()

                if "skip" in send_event and "skipped_function_list" not in send_event:
                    send_event["removed"] = [
                        VariableDeclarationInfo(
                            name = previous_value_key[0], 
                            line = previous_value_key[1]
                        )
                        for previous_value_key in self.vars_tracker.previous_values[-1].keys() 
                        if previous_value_key not in self.vars_tracker.vars_declared[-1]
                    ]
            elif send_event["status"] == "ng":
                self.events_history.pop(-1)

            send_data = json.dumps(send_event)
            conn.sendall(send_data.encode('utf-8'))

    print(f"[connected] {addr} is connected" if args.english else f"[接続] {addr} が接続しました")

    stdout_file = None
    stderr_file = None

    try:
        lldb.SBDebugger.Initialize()
        debugger: lldb.SBDebugger = lldb.SBDebugger.Create()
        debugger.SetAsync(False)

        target: lldb.SBTarget = debugger.CreateTargetWithFileAndArch(args.name, lldb.LLDB_ARCH_DEFAULT)
        if not target:
            print("failed in build of target")
            exit(-1)

        # breakpointを行で指定するならByLocation
        breakpoint: lldb.SBBreakpoint = target.BreakpointCreateByName("main", target.GetExecutable().GetFilename())

        launch_info = lldb.SBLaunchInfo([])
        launch_info.SetWorkingDirectory(os.getcwd())

        stdout_file = tempfile.NamedTemporaryFile(delete=False)
        stderr_file = tempfile.NamedTemporaryFile(delete=False)

        # stdout, stderr を別々のパイプにする
        launch_info.AddOpenFileAction(1, stdout_file.name, True, True)  # fd=1 → stdout
        launch_info.AddOpenFileAction(2, stderr_file.name, True, True)  # fd=2 → stderr

        error = lldb.SBError()
        process: lldb.SBProcess = target.Launch(launch_info, error)

    except Exception as e:
        # エラーの行番をトラックするためのコード
        tb = e.__traceback__
        error_lines_list = [tb.tb_lineno]
        while tb is not None and tb.tb_next is not None:
            tb = tb.tb_next
            error_lines_list.append(tb.tb_lineno)
        print("line:", error_lines_list, f"\n{e} サーバ終了")
        if stdout_file:
            os.unlink(stdout_file.name)
        if stderr_file:
            os.unlink(stderr_file.name)
        return
        
    debug_manager = DebugManager()

    stdout_r = None
    stderr_r = None

    while True:
        try:
            # 読み取り用にlogファイルを常にopenしておく
            stdout_r = open(stdout_file.name, "r")
            stderr_r = open(stderr_file.name, "r")

            if not error.Success() or not process or not process.IsValid():
                print("failed in operation")
                exit(-1)

            thread: lldb.SBThread = process.GetThreadAtIndex(0)
            if not thread.IsValid():
                print("no valid thread found")
                exit(-1)

            debug_manager.set_process_and_thread(process, thread)
            # 変数は次の行での値を見て考える(まず変数チェッカーで次の行に進み変数の更新を確認) => その行と前の行で構文や関数は比較する(構文内の行の移動及び関数の移動は次の行と前の行が共に必要)
            while process.GetState() == lldb.eStateStopped:
                debug_manager.analyze_frame()

        except Exception as e:
            # エラーの行番をトラックするためのコード
            tb = e.__traceback__
            error_lines_list = [tb.tb_lineno]
            while tb is not None and tb.tb_next is not None:
                tb = tb.tb_next
                error_lines_list.append(tb.tb_lineno)
            print("line:", error_lines_list)

            if stdout_r:
                stdout_r.close()
            if stderr_r:
                stderr_r.close()
            os.unlink(stdout_file.name)
            os.unlink(stderr_file.name)

            if isinstance(e, RollBack):
                lldb.SBDebugger.Initialize()
                debugger: lldb.SBDebugger = lldb.SBDebugger.Create()
                debugger.SetAsync(False)

                target: lldb.SBTarget = debugger.CreateTargetWithFileAndArch(args.name, lldb.LLDB_ARCH_DEFAULT)
                if not target:
                    print("failed in build of target")
                    exit(-1)

                debug_manager.rollback_index = 0
                debug_manager.reset_state()
                debug_manager.vars_tracker.reset_state()
            else:
                print(e, "サーバ終了")
                break

# region コマンドライン引数の確認
parser = argparse.ArgumentParser(description='for the c-backdoor')
# ベース名を取得
parser.add_argument('--name', type=str, required=True, help='string')
parser.add_argument('--lines', type=str, required=True, help='string')
parser.add_argument('--events', type=str, required=True, help='string')
parser.add_argument('--english', action='store_true', help='Enable english mode')

# 引数を解析
args = parser.parse_args()
# endregion

# サーバの開始メソッドは再利用性がないのでインライン展開する
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    host='localhost'
    port=9999

    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    s.bind((host, port))
    s.listen()
    print(f"[サーバ起動] {host}:{port} で待機中...")

    conn, addr = s.accept()
    server_thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
    server_thread.start()

    server_thread.join() 