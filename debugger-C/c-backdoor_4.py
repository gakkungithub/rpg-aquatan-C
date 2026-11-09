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

class LoopLineInfo(TypedDict):
    type: Literal["while", "do_while", "for"]
    top_edge: int
    bottom_edge: int
    frame_num: int

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

class DynamicNonVarStatusHandler:
    def __init__(self, line: int, is_english: bool):
        self.line = line
        self.is_english = is_english

    def analyze_comment(self, frame: lldb.SBFrame):
        pass

    def get_next_function(self) -> tuple[DynamicCommentHandler, int] | None:
        return None
    
    def get_skipped_functions(self) -> list[list[str]] | None:
        return None

    def check_expr_automatically(self) -> Literal["progress", "end", "next_function"]:
        return "end"

class IfStatusHandler(DynamicNonVarStatusHandler):
    def __init__(self, line: int, conditions: list[IfConditionComment], is_english: bool):
        super().__init__(line, is_english)
        self.conditions = conditions
        self.dynamic_conditions = [
            DynamicCommentHandler(comments = if_condition_comment["comments"]) 
            for if_condition_comment in conditions
        ]
        self.results: list[bool] = []

    def analyze_comment(self, frame: lldb.SBFrame):
        num_of_results = len(self.results)
        if num_of_results == len(self.conditions):
            return

        for dynamic_comment_handler in self.dynamic_conditions[num_of_results:]:
            # まずは解析
            if dynamic_comment_handler.set_expr_comments(frame):
                # 解析が途中で終了する = 自作関数が現れた → ひとまずは解析を終了する
                break
            
            # 解析終了 → 本条件の値の真偽値を取得し、その結果をresultsに格納する
            result = dynamic_comment_handler.get_result_bool(frame)
            self.results.append(result)

            # 条件がTrueならそれ以降の条件は確認しないので
            if result is True:
                break

    def get_next_function(self):
        num_of_results = len(self.results)
        if True in self.results or num_of_results == len(self.conditions):
            sys.exit("this if statement is already completely scanned")

        return self.dynamic_conditions[num_of_results], num_of_results

    def get_skipped_functions(self):
        return [dynamic_comment_handler.skipped_function_list for dynamic_comment_handler in self.dynamic_conditions]
    
    def check_conditions(self, send_event: SendEvent, true_condition_index: int):
        if true_condition_index < -1 or len(self.conditions) <= true_condition_index:
            sys.exit(f"a given true condition index has to between -1 and {len(self.conditions)}")

        if true_condition_index == -1:
            if True in self.results:
                return "incorrect"
            
            # まだ解析できていない条件がある
            if len(self.results) != len(self.conditions):
                # self.analyze_next_function(current_expr_status)
                return "next_function"

            # 全ての条件がFalse → どの条件にも該当しない = true_case_indexは-1で正しい
            send_event["execution_and_result_str_list"] = [
                ExecutionAndResultStr(
                    execution = dynamic_comment_handler.get_str_after_analysis_completed(),
                    result = f"so, the {i+1}th condition is False" if self.is_english else f"ゆえに、{i+1}番目の条件は偽です"
                )
                for i, dynamic_comment_handler in enumerate(self.dynamic_conditions)
            ]
        else:
            # 今回選んだ条件より前の条件が正しい = 間違った条件を選んだ
            if True in self.results[:true_condition_index]:
                return "incorrect"
            
            # まだ探索中であれば(どこかしらの自作関数で止まっているなら)、その関数を確かめる方向に行く
            if len(self.results) <= true_condition_index:
                return "next_function"

            # 間違った条件を選んだ
            if self.results[true_condition_index] is False:
                return "incorrect"
            
            # executioin_info["true_condition_index"]番目の条件が正しい → 正しい条件を選んだ
            execution_and_result_str_list: list[ExecutionAndResultStr] = []
            for i, dynamic_comment_handler in enumerate(self.dynamic_conditions):
                is_true = i == true_condition_index
                execution_and_result_str_list.append(
                    ExecutionAndResultStr(
                        execution = dynamic_comment_handler.get_str_after_analysis_completed(),
                        result = f"so, the {i+1}th condition is {"True" if is_true else "False"}" if self.is_english else f"ゆえに、{i+1}番目の条件は{"真" if is_true else "偽"}です"
                    )
                )
                if is_true:
                    break

            send_event["execution_and_result_str_list"] = execution_and_result_str_list

        return "correct"

    def check_expr_automatically(self):
        if True in self.results:
            return "end"

        if len(self.results) == len(self.conditions):
            return "end"

        return "next_function"

class WhileStatusHandler(DynamicNonVarStatusHandler):
    def __init__(self, line: int, condition: list[Comment], is_english: bool):
        super().__init__(line, is_english)
        self.condition = condition
        self.dynamic_condition = DynamicCommentHandler(comments = condition)
        self.result: bool | None = None

    def analyze_comment(self, frame: lldb.SBFrame):
        if self.result is not None:
            return

        dynamic_comment_handler = self.dynamic_condition
        if dynamic_comment_handler.set_expr_comments(frame):
            return

        self.result = dynamic_comment_handler.get_result_bool(frame)

    def get_next_function(self):
        return self.dynamic_condition, 0

    def get_skipped_functions(self):
        return [self.dynamic_condition.skipped_function_list]
    
    def check_condition(self, send_event: SendEvent, condition: bool):
        if self.result is None:
            return "next_function"

        if self.result is not condition:
            return "incorrect"

        send_event["execution_and_result_str_list"] = [
            ExecutionAndResultStr(
                execution = self.dynamic_condition.get_str_after_analysis_completed(),
                result = f"so, the condition is {"True" if self.result else "False"}" if self.is_english else f"ゆえに、{"真" if self.result else "偽"}です"
            )
        ]

        return "correct"

    def check_expr_automatically(self):
        if self.result is True:
            return "progress"
        elif self.result is False:
            return "end"

        return "next_function"
    
class DoWhileStatusHandler(DynamicNonVarStatusHandler):
    def __init__(self, line: int, condition: list[Comment], is_english: bool):
        super().__init__(line, is_english)
        self.condition = condition
        self.dynamic_condition = DynamicCommentHandler(comments = condition)
        self.result: bool | None = None

    def analyze_comment(self, frame: lldb.SBFrame):
        if self.result is not None:
            return

        dynamic_comment_handler = self.dynamic_condition
        if dynamic_comment_handler.set_expr_comments(frame):
            return

        self.result = dynamic_comment_handler.get_result_bool(frame)

    def get_next_function(self):
        return self.dynamic_condition

    def get_skipped_functions(self):
        return [self.dynamic_condition.skipped_function_list]
    
    def check_condition(self, send_event: SendEvent, condition: bool):
        if self.result is None:
            return "next_function"

        if self.result is not condition:
            return "incorrect"

        send_event["execution_and_result_str_list"] = [
            ExecutionAndResultStr(
                execution = self.dynamic_condition.get_str_after_analysis_completed(),
                result = f"so, the condition is {"True" if self.result else "False"}" if self.is_english else f"ゆえに、{"真" if self.result else "偽"}です"
            )
        ]

        return "correct"

    def check_expr_automatically(self):
        if self.result is True:
            return "progress"
        elif self.result is False:
            return "end"

        return "next_function"
    
class ForStatusHandler(DynamicNonVarStatusHandler):
    def __init__(self, line: int, expr: ForComment, is_english: bool):
        super().__init__(line, is_english)
        
        self.initializer = ForInitializerStatus(
            expr = initializer,
            dynamic_expr = DynamicCommentHandler(comments = initializer),
        ) if (initializer := expr.get("initializer", None)) is not None else None
        
        self.required_var_list = [
            (var_info["varNode"]["name"], line) 
            for var_info in var_initializer
        ] if (var_initializer := expr.get("var_initializer", None)) is not None else None
        
        self.condition = ForConditionStatus(
            expr = condition,
            dynamic_expr = DynamicCommentHandler(comments = condition), 
            result = None
        ) if (condition := expr["condition"]) is not None else None

        self.change = ForChangeStatus(
            expr = change,
            # 一回目のループ直前には変更式に到達することはないのでDynamicCommentHandlerは生成しない
            dynamic_expr = None,
            is_not_completed = True
        ) if (change := expr.get("change", None)) is not None else None

        self.is_first = True

    def analyze_comment(self, frame: lldb.SBFrame):
        # is_firstがTrue = まだ初期化が済んでいない
        if self.is_first:
            # 初期化部があるならその解析を行う
            if self.initializer is not None:
                if self.required_var_list is not None:
                    sys.exit("variable initializer cannot be mixed with normal initializer")
                
                dynamic_comment_handler = self.initializer["dynamic_expr"]
                if (dynamic_comment_handler.set_expr_comments(frame)):
                    return
            elif self.required_var_list is not None:
                if self.initializer is not None:
                    sys.exit("normal initializer cannot be mixed with variable initializer")
                return
            
            # 条件がない = 常に条件がTrue → 解析しない
            if self.condition is None:
                return
            
            dynamic_comment_handler = self.condition["dynamic_expr"]
            if dynamic_comment_handler.set_expr_comments(self.frame):
                return
            
            self.is_first = True
        else:
            if self.initializer is not None or self.required_var_list is not None:
                sys.exit("initializer or var_initializer have to be already done")
            
            # is_initializer is True = 条件部に戻ってきた → その前に変更式の解析を行う
            if self.change is not None and self.change["is_not_completed"]:
                if self.change["dynamic_expr"] is None:
                    self.change["dynamic_expr"] = DynamicCommentHandler(comments = self.change["expr"])
                dynamic_comment_handler = self.change["dynamic_expr"]
                dynamic_comment_handler.set_expr_comments(frame)
                return
            
            # 条件がない = 常に条件がTrue → 解析しない
            if self.condition is None:
                return
            
            dynamic_comment_handler = self.condition["dynamic_expr"]
            dynamic_comment_handler.set_expr_comments(self.frame)

    def get_next_function(self):
        if self.initializer is not None:
            dynamic_comment_handler = self.initializer["dynamic_expr"]
        elif self.change is not None and self.change["dynamic_expr"] is not None:
            dynamic_comment_handler = self.change["dynamic_expr"]
        elif (for_condition_status := self.condition) is not None:
            dynamic_comment_handler = for_condition_status["dynamic_expr"]
        else:
            return None

        return dynamic_comment_handler, 0

    def get_skipped_functions(self):
        if self.initializer is not None:
            return [self.initializer["dynamic_expr"].skipped_function_list]
        elif self.change is not None and self.change["dynamic_expr"] is not None:
            return [self.change["dynamic_expr"].skipped_function_list]
        elif (for_condition_status := self.condition) is not None:
            return [for_condition_status["dynamic_expr"].skipped_function_list]
        else:
            return None

    def check_status(self, send_event: SendEvent, execution_info: ForExecutionInfo):
        if execution_info["type"] == "for":
            if self.initializer is not None or self.required_var_list is not None:
                return "incorrect"
            
            if self.change is not None and self.change["dynamic_expr"] is not None:
                return "incorrect"
            
            if self.condition is None:
                if not execution_info["condition"]:
                    return "incorrect"
                
                send_event["execution_and_result_str_list"] = [
                    ExecutionAndResultStr(
                        execution = "no condition expression" if self.is_english else "条件式がない",
                        result = f"so, this condition is always true" if self.is_english else f"ゆえに常に真です"
                    )
                ]
            else:
                if (result := self.condition["result"]) is None:
                    return "next_function"
                
                if result is not execution_info["condition"]:
                    return "incorrect"

                send_event["execution_and_result_str_list"] = [
                    ExecutionAndResultStr(
                        execution = self.condition["dynamic_expr"].get_str_after_analysis_completed(),
                        result = f"so, the condition is {"True" if result else "False"}" if self.is_english else f"ゆえに、{"真" if result else "偽"}です"
                    )
                ]
        elif execution_info["type"] == "for_initializer":
            if self.initializer is None:
                return "incorrect"
            
            if self.initializer["dynamic_expr"].current_function_comment is not None:
                return "next_function"
            
            # 初期化時(結果がNoneでない場合)はそのコメント(result)を取得する
            send_event["execution_and_result_str_list"] = [
                ExecutionAndResultStr(
                    execution = self.initializer["dynamic_expr"].get_str_after_analysis_completed(),
                    result = None
                )
            ]
            self.initializer = None
        elif execution_info["type"] == "for_change":
            if self.change is None:
                return "incorrect"

            if (dynamic_comment_handler := self.change["dynamic_expr"]) is None:
                return "incorrect"
            
            if dynamic_comment_handler.current_function_comment is not None:
                return "next_function"
                
            # 変更式があるならその内容を登録する
            send_event["execution_and_result_str_list"] = [
                ExecutionAndResultStr(
                    execution = dynamic_comment_handler.get_str_after_analysis_completed(),
                    result = None
                )
            ]
            
            self.change["dynamic_expr"] = None
        else:
            return "incorrect"

        return "correct"

    def check_expr_automatically(self):
        if self.initializer is not None:
            if self.initializer["dynamic_expr"].current_function_comment is not None:
                return "next_function"

            return "progress"

        if self.change and (dynamic_comment_handler := self.change["dynamic_expr"]) is not None:
            if dynamic_comment_handler.current_function_comment is not None:
                return "next_function"

            self.change["dynamic_expr"] = None
            return "progress"

        if self.condition is None:
            return "progress"

        if (result := self.condition["result"]) is None:
            return "next_function"

        return "progress" if result else "end"

class ForInitializerStatus(TypedDict):
    expr: list[Comment]
    dynamic_expr: DynamicCommentHandler

class ForConditionStatus(TypedDict):
    expr: list[Comment]
    dynamic_expr: DynamicCommentHandler
    result: bool | None

class ForChangeStatus(TypedDict):
    expr: list[Comment]
    dynamic_expr: DynamicCommentHandler | None
    is_not_completed: bool


class SwitchStatusHandler(DynamicNonVarStatusHandler):
    def __init__(self, line: int, expr: SwitchConditionComment, is_english: bool):
        super().__init__(line, is_english)
        self.condition = expr["condition"]
        self.dynamic_condition = DynamicCommentHandler(comments = expr["condition"])
        self.condition_result: str | None = None
        self.case_expr_list_by_index = [
            [
                CaseStatus(
                    case_expr = case_expr["comments"],
                    dynamic_case_expr = DynamicCommentHandler(
                        comments = case_expr["comments"]
                    ),
                    result = None,
                    line = case_expr["line"]
                )
                for case_expr in case_expr_list
            ] for case_expr_list in expr["case_exprs"]
        ]
        self.matched_case: tuple[int, int, str] | None = None
        self.default_index = expr.get("default_index", None)

    def analyze_comment(self, frame: lldb.SBFrame):
        # matched_caseがNoneではない = 何らかのcaseが条件式の値と合致したことが確認済み = ラベル式の値の計算は終了済み
        if self.matched_case is not None:
            return
        
        # resultがNone = 条件文の計算処理は完了していない → その処理を実行しにいく
        if self.condition_result is None:
            dynamic_comment_handler = self.dynamic_condition
            if dynamic_comment_handler.set_expr_comments(frame):
                return
            
            if (result := dynamic_comment_handler.expr_result_by_id[-1]) is None:
                sys.exit("error in result of switch condition")
            
            self.condition_result = result

        for i, case_expr_list in enumerate(self.case_expr_list_by_index):
            for case_expr in case_expr_list:
                if case_expr["result"] is None:
                    if case_expr["dynamic_case_expr"].set_expr_comments(frame):
                        sys.exit("expression of case value cannot have any functions")
                    
                    if (result := case_expr["dynamic_case_expr"].expr_result_by_id[-1]) is None:
                        sys.exit("error in result of case expression")

                    case_expr["result"] = result

                    if self.condition_result == result and result is not None:
                        self.matched_case = (i, case_expr["line"], result)
                        return

    def get_next_function(self):
        return self.dynamic_condition, 0

    def get_skipped_functions(self):
        return [self.dynamic_condition.skipped_function_list]

    def check_status(self, send_event: SendEvent, execution_info: SwitchCaseExecutionInfo):
        if self.dynamic_condition.current_function_comment is not None:
            return "next_function"
        
        if execution_info["true_case_index"] == -1:
            # どこかしらの条件がTrue → 間違った条件を選んでいる
            if self.matched_case is not None:
                return "incorrect"

            if self.default_index is not None:
                return "incorrect"

            # execution_and_result_str_list = []

            # for case_expr_list in self.case_expr_list_by_index:
            #     for case_expr in case_expr_list:
                    
            #         pass

            execution_and_result_str_list = [
                ExecutionAndResultStr(
                    execution = self.dynamic_condition.get_str_after_analysis_completed(),
                    result = "so, any case labels are not matched" if self.is_english else "ゆえに、どのcaseにも合致しません"
                )
            ]

            send_event["execution_and_result_str_list"] = execution_and_result_str_list
        else:
            if self.matched_case is None:
                if execution_info["true_case_index"] != self.default_index:
                    return "incorrect"
                
                send_event["execution_and_result_str_list"] = [
                    ExecutionAndResultStr(
                        execution = self.dynamic_condition.get_str_after_analysis_completed(),
                        result = "so, default label is matched" if self.is_english else "ゆえに、defaultに合致しました"
                    )
                ]
            else:
                case_index, line, result = self.matched_case
                if execution_info["true_case_index"] != case_index:
                    return "incorrect"

                send_event["execution_and_result_str_list"] = [
                    ExecutionAndResultStr(
                        execution = self.dynamic_condition.get_str_after_analysis_completed(),
                        result = f"so, case label of line {line} (value = {result}) is matched" if self.is_english else f"ゆえに、{line}行のcase (値は{result}) に合致しました"
                    )
                ]

        return "correct"

    def check_expr_automatically(self):
        if self.dynamic_condition.current_function_comment is not None:
            return "next_function"

        if self.default_index is None and self.matched_case is None:
            return "end"

        if self.default_index is not None and self.matched_case is not None:
            return "end"

        sys.exit("all case exprs of switch statement have to be calculated at once")

class CaseStatus(TypedDict):
    case_expr: list[Comment]
    dynamic_case_expr: DynamicCommentHandler
    result: str | None
    line: int


class ControlFlowStatusHandler(DynamicNonVarStatusHandler):
    def __init__(self, line: int, type: Literal["break", "continue"], is_english: bool):
        super().__init__(line, is_english)
        self.type = type

    def check_status(self, send_event: SendEvent):
        # lineがあっている時点で正しい → 正しいcontinueまたはbreakを選んでいる
        send_event["execution_and_result_str_list"] = [
            ExecutionAndResultStr(
                execution = (
                    (
                        "skip the remaining executions in a loop by continue" 
                        if self.is_english else 
                        "continueによりループ内の残りの処理をスキップします"
                    )
                    if self.type == "continue" else
                    (
                        "exit the current loop by break"
                        if self.is_english else
                        "breakにより現在のループから脱出します"
                    )
                ),
                result = None
            )
        ]
        return "correct"


class ExpressionStatusHandler(DynamicNonVarStatusHandler):
    def __init__(self, line: int, expr: list[Comment], is_english: bool):
        super().__init__(line, is_english)
        self.expr = expr
        self.dynamic_expr = DynamicCommentHandler(comments = expr)

    def analyze_comment(self, frame: lldb.SBFrame):
        if self.dynamic_expr.expr_result_by_id[-1] is not None:
            return
        
        self.dynamic_expr.set_expr_comments(frame)

    def get_next_function(self):
        return self.dynamic_expr, 0
    
    def get_skipped_functions(self):
        return [self.dynamic_expr.skipped_function_list]

    def check_expr(self, send_event: SendEvent):
        # 計算式を解析し終わっている → 次のアクションに進める → 計算式の結果を取得する
        if self.dynamic_expr.current_function_comment is not None:
            return "next_function"

        send_event["execution_and_result_str_list"] = [
            ExecutionAndResultStr(
                execution = self.dynamic_expr.get_str_after_analysis_completed(),
                result = None
            )
        ]

        return "correct"

    def check_expr_automatically(self):
        if self.dynamic_expr.current_function_comment is not None:
            return "next_function"
        
        return "end"
    
# void関数は、自由に戻れるキャラにする 
# ただし、frame_numが減らない場合(到達先の関数が異なる場合)は戻れない = プレイヤーはダメージを受けるようにする
class ReturnStatusHandler(DynamicNonVarStatusHandler):
    def __init__(self, line: int, expr: list[Comment], thread: lldb.SBThread, is_english: bool):
        super().__init__(line, is_english)
        self.expr = expr
        self.dynamic_expr = DynamicCommentHandler(comments = expr)
        self.result: str | None = None
        self.thread = thread

    def analyze_comment(self, frame: lldb.SBFrame):
        if self.dynamic_expr.set_expr_comments(frame) is not None:
            return
        
        # これで取得するのか?
        if (return_value := self.thread.GetStopReturnValue().GetValue()) is None:
            return

        self.result = return_value

    def get_next_function(self):
        return self.dynamic_expr, 0

    def get_skipped_functions(self):
        return [self.dynamic_expr.skipped_function_list]

    def check_status(self, send_event: SendEvent, current_dynamic_comment_handler_being_checked: tuple[DynamicCommentHandler, int] | None):
        # 計算式の解析が終わっている → 次のアクションに進める → 計算式の結果を取得する
        if (result := self.result) is None:
            print("check status returns next function")
            return "next_function"

        if current_dynamic_comment_handler_being_checked is not None:
            dynamic_comment_handler, index = current_dynamic_comment_handler_being_checked
            send_event["function_return_info"] = FunctionReturnInfo(
                func_name = dynamic_comment_handler.get_current_function(),
                index = index,
                return_value = result
            )
            dynamic_comment_handler.set_function_comment(result)

        print("result:", result)
        send_event["execution_and_result_str_list"] = [
            ExecutionAndResultStr(
                execution = result,
                result = None
            )
        ]

        return "correct"

    def check_expr_automatically(self):
        if self.result is None:
            return "next_function"

        return "end"

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
                
                expr_str_base_list.append(f"{expr_description["func_name"]}({','.join(arg_list)})")
            else:
                expr_str_base_list_by_part: list[str] = []

                for expr_part in expr_description["expr"]: # "expr": [{"name": "day"}, {"text": "*"}, {"text": "1.2f"}]}
                    if "type" in expr_part:
                        expr_str_base_list_by_part.append(self.get_reference_str_base(expr_part, expr_str_base_list))
                    elif "text" in expr_part:
                        expr_str_base_list_by_part.append(expr_part["text"])
                    elif "macro" in expr_part: # 今はスカラー値のみを考えるが、後々、関数やifdefも考えられると良いかも
                        expr_str_base_list_by_part.append(expr_part["macro"])
                    else: # expr_id
                        expr_str_base_list_by_part.append(expr_str_base_list[expr_part["expr_id"]])

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
                            str_to_show_list.append(f"<{expr_part["macro"]}>(={self.get_expr_result(expr_part["replacement"]["expr_id"]) or "not to evaluate"})")
                    else: # expr_id
                        str_for_evaluation_list.append(self.get_expr_result(expr_part["expr_id"]))
                        str_to_show_list.append(f"<{self.get_expr_to_show(expr_part["expr_id"])}>(={self.get_expr_result(expr_part["expr_id"]) or "not to evaluate"})")

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

    def get_expr_result(self, index: int = -1):
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
        if any(not isinstance(expr_description, str) for expr_description in self.expr_description_to_show_by_id):
            sys.exit("this expression is not completely analyzed yet")
        
        return '\f'.join(self.expr_description_to_show_by_id)

    def is_analysis_potentially_completed(self):
        for comment in self.expr_description_to_show_by_id[self.index_scanned_currently:]:
            if isinstance(comment, str):
                sys.exit("str is found in an analyzed parts of expr_description_to_show_by_id")
            
            if "func_name" in comment["comment"] and all(self.get_expr_result(index) is result for index, result in comment["execution_condition"].items()):
                return False

        return True


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
            self.track_var(gvars, self.global_previous_values, is_local=False)
            
        def start_tracking(self, frame: lldb.SBFrame):
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
                dynamic_variable_info_list.extend(
                    [
                        DynamicVarInfo(
                            dynamic_var_node = self.transform_2_dynamic_var_node(var_info["varNode"]),
                            start = var_info["start"],
                            end = var_info["end"],
                            skipped_function_list = [],
                            current_comment = None
                        )
                        for var_info in self.declared_variables_by_line[line_number]
                    ]
                )

            for dynamic_variable_info in dynamic_variable_info_list:
                dynamic_variable_info["current_comment_w_index"] = None
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
                comments = DynamicCommentHandler(
                    comments = var_node["comments"]
                ),
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

        def track_var(self, vars: list[lldb.SBValue] | lldb.SBValueList, var_previous_values: dict[tuple[str, int], VarPreviousValue], is_local: bool = True):
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

                if is_local:
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
        
            if not is_local or len(self.vars_declared) == 0:
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

        def get_value(self):
            return [
                VariableInfo(
                    name = var_key[0],
                    line = var_key[1],
                    value = VariableValue(
                        value = self.previous_values[-1][var_key].value,
                        children = self.get_value_dict(self.previous_values[-1][var_key].children)
                    )
                )
                for var_key in self.vars_declared[-1] if var_key in self.previous_values[-1]
            ]
        
        def get_value_each_frame(self):
            return [
                [
                    VariableInfo(
                        name = var_key[0],
                        line = var_key[1],
                        value = VariableValue(
                            value = self.previous_values[i][var_key].value,
                            children = self.get_value_dict(self.previous_values[i][var_key].children)
                        )
                    )
                    for var_key in self.vars_declared[i] if var_key in self.previous_values[i]
                ]
                for i in range(len(self.vars_declared))
            ]
        
        def get_global_value(self):
            return [
                VariableInfo(
                    name = var_key[0],
                    line = var_key[1],
                    value = VariableValue(
                        value = global_previous_value.value, 
                        children = self.get_value_dict(global_previous_value.children)
                    )
                )
                for var_key, global_previous_value in self.global_previous_values.items()
            ]

        def get_value_dict(self, previous_values: dict[str, VarPreviousValue]):
            return {
                var_name: VariableValue(
                    value = previous_value.value, 
                    children = self.get_value_dict(previous_value.children)
                )
                for var_name, previous_value in previous_values.items()
            }
        
        def get_value_partly(self, var_name: tuple[str, int], value_path: list[str]):
            temp_previous_value = self.previous_values[-1][var_name]
            while len(value_path):
                children_name = value_path.pop(0)
                temp_previous_value = temp_previous_value.children[children_name]
            return temp_previous_value.value

        def get_declared_var_value_w_comment(self, var_node: DynamicVarNode):
            return VariableValueWComment(
                value = var_node["comments"].get_expr_result(), # previous_valueで取得するかは後で考える
                type = var_node["type"],
                comment = var_node["comments"].get_str_after_analysis_completed(),
                children = {
                    child["name"] : self.get_declared_var_value_w_comment(child)
                    for child in var_node["children"]
                },
                initialized = var_node["initialized"]
            )
        
        def get_value_by_var(self, var: tuple[str, int]):
            return self.get_value_by_var_part(self.previous_values[-1][var])

        # {"value": bbb, "children": {0: {...}}...}
        def get_value_by_var_part(self, previous_value: VarPreviousValue):
            return VariableValue(
                value = previous_value.value,
                children = {
                    var_part : self.get_value_by_var_part(var_previous_value)
                    for var_part, var_previous_value in previous_value.children.items()
                }
            )
        
        def set_variable_declared(self, name: tuple[str, int]):
            return self.vars_declared[-1].append(name)

                                                                                                                                                   
# 88888888ba,              88                                  88b           d88                                                                      
# 88      `"8b             88                                  888b         d888                                                                      
# 88        `8b            88                                  88`8b       d8'88                                                                      
# 88         88  ,adPPYba, 88,dPPYba,  88       88  ,adPPYb,d8 88 `8b     d8' 88 ,adPPYYba, 8b,dPPYba,  ,adPPYYba,  ,adPPYb,d8  ,adPPYba, 8b,dPPYba,  
# 88         88 a8P_____88 88P'    "8a 88       88 a8"    `Y88 88  `8b   d8'  88 ""     `Y8 88P'   `"8a ""     `Y8 a8"    `Y88 a8P_____88 88P'   "Y8  
# 88         8P 8PP""""""" 88       d8 88       88 8b       88 88   `8b d8'   88 ,adPPPPP88 88       88 ,adPPPPP88 8b       88 8PP""""""" 88          
# 88      .a8P  "8b,   ,aa 88b,   ,a8" "8a,   ,a88 "8a,   ,d88 88    `888'    88 88,    ,88 88       88 88,    ,88 "8a,   ,d88 "8b,   ,aa 88          
# 88888888Y"'    `"Ybbd8"' 8Y"Ybbd8"'   `"YbbdP'Y8  `"YbbdP"Y8 88     `8'     88 `"8bbdP"Y8 88       88 `"8bbdP"Y8  `"YbbdP"Y8  `"Ybbd8"' 88          
#                                                   aa,    ,88                                                      aa,    ,88                        
#                                                    "Y8bbdP"                                                        "Y8bbdP"                         

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
            self.line_loop_list: list[LoopLineInfo] = []
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
            self.expr_status_handler_dict_by_frame: list[dict[int, DynamicNonVarStatusHandler]] = [{}]
            self.exprs_by_line: dict[str, NonVarComment] = {}

        def set_process_and_thread(self, process: lldb.SBProcess, thread: lldb.SBThread) -> None:
            self.process = process
            self.thread = thread

            if (next_state := self.get_next_state()):
                self.state, self.frame, self.file_name, self.next_line_number, self.func_crnt_name, self.next_frame_num = next_state
                with open(f"{DATA_DIR}/{self.file_name[:-2]}/{self.file_name[:-2]}_line.json", 'r') as f:
                    self.line_data: dict[str, LineInfoDataByFunc] = json.load(f)
                    self.func_name = self.func_crnt_name
                    self.frame_num = 1
                    self.get_std_outputs()
                    self.event_sender(
                        SendEvent(
                            message = "The first step" if self.is_english else "最初の処理",
                            line = self.line_data[self.func_name]["start"], 
                            items = self.vars_tracker.get_global_value(), 
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

            self.vars_tracker.start_tracking(self.frame)
            self.vars_checker()

        def step_conditionally(self) -> None:
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
                self.analyze_non_var_expr_comments(is_end = True)
                self.get_std_outputs()
                return

            self.thread = self.frame.GetThread()
            self.process = self.thread.GetProcess()

            # 初期化されない変数や静的変数はスキップされるので、そのステップを後追いで見る
            while len(self.skipped_var_declaration_lines):
                line = self.skipped_var_declaration_lines.pop(0)
                self.vars_tracker.analyze_var_nodes(line, self.frame)
                
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
                
                self.vars_tracker.start_tracking(self.frame)

                ### ここから下の標準関数の解析はdynamic_comment_handlerのset_expr_commentsメソッドで行うことにする(予定)
                if input_check:
                    if state == "ok":
                        self.event_sender(
                            SendEvent(
                                message = f"values ({', '.join(results)}) were set to stdin !!" if self.is_english else f"値 ({', '.join(results)}) がstdinに入力されました!!",
                                status = "ok",
                                items = self.vars_tracker.get_value()
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
                                items = self.vars_tracker.get_value()
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
                self.frame_num = self.next_frame_num
                self.func_name = self.func_crnt_name

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
                    value_changed_dict_list.append(
                        VariablePartWithValue(
                            item = VariableDeclarationInfo(
                                name = value_changed[0],
                                line = value_changed[1]
                            ),
                            path = value_path,
                            value = self.vars_tracker.get_value_partly(value_changed, value_path.copy())
                        )
                    )

            return value_changed_dict_list
        
        def get_vars_w_value_unchanged(self) -> list[VariablePartWithValue]:
            value_unchanged_dict_list = []
            for value_unchanged in self.vars_tracker.vars_unchanged:
                value_path = [*value_unchanged[1]]
                value_unchanged_dict_list.append(
                    VariablePartWithValue(
                        item = VariableDeclarationInfo(
                            name = value_unchanged[0][0],
                            line = value_unchanged[0][1]
                        ),
                        path = value_path,
                        value = self.vars_tracker.get_value_partly(value_unchanged[0], value_path.copy())
                    )
                )
            return value_unchanged_dict_list
        
        def set_skipped_var_declaration(self, start_line: int | None, end_line: int | None):
            start_line, end_line = self.get_start_end_lines_for_skipped_var_declaration(start_line, end_line)

            if start_line is None and end_line is None:
                return

            self.skipped_var_declaration_lines = [
                line for line in self.vars_tracker.declared_variables_by_line
                if ((start_line is not None and end_line is not None and start_line < int(line) < end_line) 
                or (start_line is None and end_line is not None and int(line) < end_line) 
                or (start_line is not None and end_line is None and start_line < int(line)))
            ]

        def get_start_end_lines_for_skipped_var_declaration(self, start_line: int | None, end_line: int | None) -> tuple[int | None, int | None]:
            if start_line is None or end_line is None:
                return start_line, end_line
            
            if start_line > end_line:
                if self.frame_num < self.next_frame_num:
                    return start_line, end_line
                elif self.frame_num > self.next_frame_num:
                    end_line = None
                else: # 同じ関数内 = while, do-while, or for
                    # 直前のself.loop_listのend_lineを取得する
                    if len(self.line_loop_list):
                        end_line = self.line_loop_list[-1]["bottom_edge"]

            return start_line, end_line

        def vars_checker(self, is_for_false: bool = False) -> None:
            if self.is_end:
                return

            line_number = self.line_number
            # これだとスコープ外の変数を拾ってしまうことがある
            # for文の条件文内の宣言だとfalseの時にself.vars_tracker.declared_variables_by_line.get(str(self.line_number), [])でスコープ外の変数を取得してしまうことがある
            if is_for_false:
                varsDeclLines = []
            else:
                varsDeclLines = [
                    dynamic_variable_info
                    for dynamic_variable_info in self.vars_tracker.dynamic_variable_info_by_line.get(str(line_number), []) 
                    if (dynamic_variable_info["dynamic_var_node"]["name"], line_number) not in self.vars_tracker.vars_declared[-1]
                ]

            varsDeclLines_copy = varsDeclLines[:]

            # やはり、変数は順番に取得させる
            while len(varsDeclLines_copy):
                dynamic_variable_info = varsDeclLines_copy.pop(0)
                var = (dynamic_variable_info["dynamic_var_node"]["name"], line_number)
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
                    if line_number < event["start"] or event["end"] < line_number:
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
                                        value = self.vars_tracker.get_declared_var_value_w_comment(dynamic_variable_info["dynamic_var_node"]),
                                        line = var[1]
                                    ),
                                    skipped_function_list = dynamic_variable_info["skipped_function_list"]
                                ),
                                False
                            )
                        # 全ての宣言が完了している場合
                        else:
                            # vars_changedとvarsTrackerの共通項とvarsDeclLinesの差項を、値が変化した変数として検知する
                            # vars_changedにもkeysを使って宣言済みかつ値が変わった変数を取得できる
                            values_changed = [
                                varname
                                for varname in self.vars_tracker.vars_changed.keys()
                                if varname in self.vars_tracker.vars_declared[-1] and varname not in varsDeclLines
                            ]

                            # 変数宣言が全て完了した時の処理
                            self.set_skipped_var_declaration(self.line_number, self.next_line_number)

                            self.event_sender(
                                SendEvent(
                                    message = f"You got item {var[0]} !!" if self.is_english else f"アイテム {var[0]} を正確に取得できました!!", 
                                    status = "ok",
                                    item = DeclaredVariableInfo(
                                        # value = self.vars_tracker.get_value_by_var(var),
                                        value = self.vars_tracker.get_declared_var_value_w_comment(dynamic_variable_info["dynamic_var_node"]),
                                        line = var[1]  
                                    ),
                                    vars_w_value_changed = self.get_vars_w_value_changed(values_changed), 
                                    vars_w_value_unchanged = self.get_vars_w_value_unchanged(),
                                    skipped_function_list = dynamic_variable_info["skipped_function_list"]
                                )
                            )

                        break

                    # non_varの時と同じくこのメソッドで次の関数を解析する
                    self.analyze_next_function(dynamic_variable_info)

                    self.vars_tracker.analyze_var_nodes(str(var[1]), self.frame)

                    self.step_conditionally()

        # 変数宣言以外の計算式の解析
        def analyze_non_var_expr_comments(self, is_end: bool = False):
            if str(self.next_line_number) not in self.exprs_by_line:
                if is_end:
                    sys.exit("main return statement is not found")

                self.thread.StepInto()
                return

            if len(self.expr_status_handler_dict_by_frame) <= self.next_frame_num - 2:
                self.expr_status_handler_dict_by_frame.append({})

            if self.next_line_number not in self.expr_status_handler_dict_by_frame[self.next_frame_num-2]:
                self.set_expr_status(self.exprs_by_line[str(self.next_line_number)], self.next_line_number)

            expr_status_handler = self.expr_status_handler_dict_by_frame[self.next_frame_num-2][self.next_line_number]

            if isinstance(expr_status_handler, ForStatusHandler):
                expr_status_handler.analyze_comment(self.frame)
                return

            if not is_end:
                if isinstance(expr_status_handler, ReturnStatusHandler) and expr_status_handler.dynamic_expr.is_analysis_potentially_completed():
                    self.thread.StepOut()
                else:
                    self.thread.StepInto()

            # if isinstance(expr_status_handler, ReturnStatusHandler) and expr_status_handler.dynamic_expr.is_analysis_potentially_completed():
            #     self.thread.StepOut()
            # elif not is_end:
            #     self.thread.StepInto()

            expr_status_handler.analyze_comment(self.frame)

        # 次の処理の内容を取得する
        def set_expr_status(self, expr: NonVarComment, line: int):
            if expr["type"] == "if":
                expr_status_handler = IfStatusHandler(line, expr["conditions"], self.is_english)
            elif expr["type"] == "while":
                expr_status_handler = WhileStatusHandler(line, expr["condition"], self.is_english)
            elif expr["type"] == "do_while":
                expr_status_handler = DoWhileStatusHandler(line, expr["condition"], self.is_english)
                # do_while_true用にここで追加する
                self.append_line_loop("do_while", line)
            elif expr["type"] == "for":
                expr_status_handler = ForStatusHandler(line, expr, self.is_english)

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
            elif expr["type"] == "switch":
                expr_status_handler = SwitchStatusHandler(line, expr, self.is_english)
            elif expr["type"] in ("continue", "break"):
                expr_status_handler = ControlFlowStatusHandler(line, expr["type"], self.is_english)
            elif expr["type"] == "expression":
                expr_status_handler = ExpressionStatusHandler(line, expr["expr"], self.is_english)
            else: # return
                expr_status_handler = ReturnStatusHandler(line, expr["expr"], thread, self.is_english)
            
            self.expr_status_handler_dict_by_frame[self.next_frame_num-2][line] = expr_status_handler

        def append_line_loop(self, type: Literal["while", "do_while", "for"], line: int):
            if (opposite_edge := self.line_data[self.func_name]["loops"].get(str(line), None)) is None:
                sys.exit("opposite edge of a loop statement is not found")

            if type in ("while", "for"):
                if (len(self.line_loop_list) and self.line_loop_list[-1]["type"] == type and self.line_loop_list[-1]["top_edge"] == line and self.line_loop_list[-1]["frame_num"] == self.frame_num):
                    return
                
                self.line_loop_list.append(
                    LoopLineInfo(
                        type = type,
                        top_edge = line,
                        bottom_edge = opposite_edge,
                        frame_num = self.frame_num
                    )
                )
            else:
                if len(self.line_loop_list) and self.line_loop_list[-1]["type"] == type and self.line_loop_list[-1]["bottom_edge"] == line and self.line_loop_list[-1]["frame_num"] == self.frame_num:
                    return
                
                self.line_loop_list.append(
                    LoopLineInfo(
                        type = type,
                        top_edge = opposite_edge,
                        bottom_edge = line,
                        frame_num = self.frame_num
                    )
                )

        def remove_line_loop(self, type: Literal["while", "do_while", "for", "break"], line: int):
            if len(self.line_loop_list) == 0:
                return
            
            if type in ("while", "for"):
                if self.line_loop_list[-1]["type"] != type and self.line_loop_list[-1]["top_edge"] != line or self.line_loop_list[-1]["frame_num"] != self.frame_num:
                    return
            elif type == "do_while":
                if self.line_loop_list[-1]["type"] != type and self.line_loop_list[-1]["bottom_edge"] != line or self.line_loop_list[-1]["frame_num"] != self.frame_num:
                    return
                
            self.line_loop_list.pop(-1)

        def check_expr_status(self, execution_info: ExecutionInfo):

            if (current_expr_status_handler := self.expr_status_handler_dict_by_frame[self.frame_num-2].get(self.line_number, None)) is None:
                return False
            
            if current_expr_status_handler.line != execution_info["line"]:
                return False
            
            send_event = SendEvent(
                message = "",
                status = "ok",
            )

            start_line: int | None = None
            end_line: int | None = None

            if isinstance(current_expr_status_handler, IfStatusHandler) and execution_info["type"] == "if":
                check_result = current_expr_status_handler.check_conditions(send_event, execution_info["true_condition_index"])
                if check_result == "correct":
                    self.expr_status_handler_dict_by_frame[self.frame_num-2].pop(self.line_number)
                    start_line = self.line_number
                    end_line = self.next_line_number
            elif (isinstance(current_expr_status_handler, WhileStatusHandler) and execution_info["type"] == "while") or (isinstance(current_expr_status_handler, DoWhileStatusHandler) and execution_info["type"] == "do_while"):
                check_result = current_expr_status_handler.check_condition(send_event, execution_info["condition"])
                if check_result == "correct":
                    if execution_info["condition"]:
                        if execution_info["type"] == "while":
                            start_line = self.line_number

                            if self.line_number == self.next_line_number:
                                if (end_line := self.line_data[self.func_name]["loops"].get(str(self.line_number))) is None:
                                    sys.exit("end_line of while statement is not found")
                            else: # self.line_number < self.next_line_numberにしかなり得ない
                                end_line = self.next_line_number

                            self.append_line_loop("while", self.line_number)
                        else:
                            if (start_line := self.line_data[self.func_name]["loops"].get(str(self.line_number))) is None:
                                sys.exit("end_line of do-while statement is not found")

                            if self.line_number == self.next_line_number:
                                end_line = self.line_number
                            else: # self.next_line_number < self.line_numberにしかなり得ない
                                end_line = self.next_line_number
                    else: # falseなら、一番下の行をstart_lineに設定して、next_line_numberをend_lineに設定する
                        self.expr_status_handler_dict_by_frame[self.frame_num-2].pop(self.line_number)

                        if execution_info["type"] == "while":
                            if (start_line := self.line_data[self.func_name]["loops"].get(str(self.line_number), None)) is None:
                                sys.exit("end_line of while statement is not found")
                            end_line = self.next_line_number
                        else:
                            start_line = self.line_number
                            end_line = self.next_line_number

                        self.remove_line_loop(execution_info["type"], self.line_number)
            elif isinstance(current_expr_status_handler, ForStatusHandler):
                check_result = current_expr_status_handler.check_status(send_event, execution_info)
                
                # for falseの条件文チェックが完了した場合のみ、スキップされ得る次の変数リストを取得する
                if check_result == "correct" and execution_info["type"] == "for":
                    if execution_info["condition"]:
                        if self.line_number == self.next_line_number:
                            start_line = self.line_number
                            if (end_line := self.line_data[self.func_name]["loops"].get(str(self.line_number))) is None:
                                sys.exit("end_line of for statement is not found")
                        else:
                            start_line = self.line_number
                            end_line = self.next_line_number

                        self.append_line_loop("for", self.line_number)
                    else:
                        self.expr_status_handler_dict_by_frame[self.frame_num-2].pop(self.line_number)

                        if (start_line := self.line_data[self.func_name]["loops"].get(str(self.line_number), None)) is None:
                            sys.exit("start_line of for statement is not found")
                        end_line = self.next_line_number

                        self.remove_line_loop(execution_info["type"], self.line_number)
            elif isinstance(current_expr_status_handler, SwitchStatusHandler) and execution_info["type"] == "switch":
                check_result = current_expr_status_handler.check_status(send_event, execution_info)
                if check_result == "correct":
                    self.expr_status_handler_dict_by_frame[self.frame_num-2].pop(self.line_number)
                    start_line = self.line_number
                    end_line = self.next_line_number
            elif isinstance(current_expr_status_handler, ControlFlowStatusHandler) and execution_info["type"] in ("continue", "break"):
                check_result = current_expr_status_handler.check_status(send_event)
                self.expr_status_handler_dict_by_frame[self.frame_num-2].pop(self.line_number)
                if execution_info["type"] == "break":
                    self.remove_line_loop(execution_info["type"], self.line_number)
            elif isinstance(current_expr_status_handler, ExpressionStatusHandler) and execution_info["type"] == "expression":
                check_result = current_expr_status_handler.check_expr(send_event)
                if check_result == "correct":
                    self.expr_status_handler_dict_by_frame[self.frame_num-2].pop(self.line_number)
                    start_line = self.line_number
                    end_line = self.next_line_number
            elif isinstance(current_expr_status_handler, ReturnStatusHandler) and execution_info["type"] == "return":
                print("return statement")

                print(self.dynamic_comment_handler_being_checked)
                check_result = current_expr_status_handler.check_status(
                    send_event, 
                    self.dynamic_comment_handler_being_checked[-1] 
                    if len(self.dynamic_comment_handler_being_checked) else 
                    None
                )

                if check_result == "correct":
                    self.expr_status_handler_dict_by_frame.pop(-1)

                if self.is_end:
                    send_event["is_finished"] = True
                    print(check_result)
            else:
                return False

            if not self.is_end:
                if check_result == "incorrect":
                    return False
                elif check_result == "next_function":
                    self.analyze_next_function(current_expr_status_handler)
                    print("return check true")
                    return True

            self.set_skipped_var_declaration(start_line, end_line)

            send_event["skipped_function_list"] = current_expr_status_handler.get_skipped_functions()
            if not self.is_end:
                send_event["vars_w_value_changed"] = self.get_vars_w_value_changed(list(self.vars_tracker.vars_changed.keys()))
                send_event["vars_w_value_unchanged"] = self.get_vars_w_value_unchanged()

            self.event_sender(send_event)

            if self.is_end:
                raise ProgramFinished()

            return True
        
        def analyze_next_function(self, expression_info_being_analyzed: DynamicNonVarStatusHandler | DynamicVarInfo):
            if isinstance(expression_info_being_analyzed, DynamicNonVarStatusHandler):
                skipped_function_list = expression_info_being_analyzed.get_skipped_functions()
                current_comment_w_index = expression_info_being_analyzed.get_next_function()
            else:
                skipped_function_list = expression_info_being_analyzed["skipped_function_list"]
                current_comment_w_index = expression_info_being_analyzed["current_comment_w_index"]

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
                    self.dynamic_comment_handler_being_checked.append((current_comment_handler, index))

                    return_value = None
                    while True:
                        self.step_conditionally()

                        if back_line_number == self.line_number and back_frame_num == self.frame_num:
                            break

                        if self.line_data.get(self.func_name, None) and self.line_number in self.line_data[self.func_name]["lines"]:
                            if (current_expr_status_handler := self.expr_status_handler_dict_by_frame[self.frame_num-2].get(self.line_number, None)) is None:
                                sys.exit("expr status handler is not found")

                            if (result := current_expr_status_handler.check_expr_automatically()) == "end":
                                if isinstance(current_expr_status_handler, ReturnStatusHandler):
                                    self.expr_status_handler_dict_by_frame.pop(-1)
                                    return_value = current_expr_status_handler.result
                                    break
                                else:
                                    self.expr_status_handler_dict_by_frame[self.frame_num-2].pop(self.line_number)
                            elif result == "next_function":
                                current_comment_w_index = current_expr_status_handler.get_next_function()
                                current_comment_w_index[0].set_function_comment(self.analyze_next_function_in_skip())

                    current_comment_handler.set_function_comment(return_value)
                    self.event_sender(
                        SendEvent(
                            message = "function skip is completed" if self.is_english else "スキップが完了しました", 
                            status = "ok", 
                            items = self.vars_tracker.get_value(), 
                            func = self.func_crnt_name,
                            function_return_info = FunctionReturnInfo(
                                func_name = current_comment_handler.get_current_function(),
                                index = index,
                                return_value = return_value
                            )
                        )
                    )
                else:
                    func_warp = event["func_warp"]
                    self.event_sender(
                        SendEvent(
                            message = f"skip is canceled. move to function {self.func_crnt_name}" if self.is_english else f"スキップをキャンセルしました。関数 {self.func_crnt_name} に遷移します", 
                            status = "ok", 
                            func = self.func_name, 
                            from_line = self.line_number, 
                            next_func = NextFunctionInfo(
                                name = func_warp["name"], 
                                x = func_warp["x"], 
                                y = func_warp["y"], 
                                items = [
                                    ArgumentItemInfo(
                                        name = arg_name,
                                        line = arg_info["line"],
                                        value = self.vars_tracker.get_value_by_var(
                                            (
                                                arg_name, 
                                                arg_info["line"]
                                            )
                                        ),
                                        type = arg_info["type"]
                                    )
                                    for arg_name, arg_info in func_warp['args'].items()
                                ]
                            )
                        )
                    )

                    self.dynamic_comment_handler_being_checked.append((current_comment_handler, index))
                    back_line_number = self.line_number
                    back_frame_num = self.frame_num

                    # 次の関数の遷移時の処理
                    self.set_skipped_var_declaration(func_warp["line"], self.next_line_number)

                    while True:
                        if self.analyze_frame(back_line_number):
                            continue
                        if back_line_number == self.line_number and back_frame_num == self.frame_num:
                            break

                self.dynamic_comment_handler_being_checked.pop(-1)
            # ここはインライン関数が来る可能性がある? (今はまだ対応しない)
            else:
                sys.exit("error in function move")

            print("next func check is already completed")

        def analyze_next_function_in_skip(self) -> str | None:
            crnt_frame_num = self.frame_num
            while crnt_frame_num == self.frame_num:
                self.step_conditionally()
                if self.line_data.get(self.func_name, None) and self.line_number in self.line_data[self.func_name]["lines"]:
                    if (current_expr_status_handler := self.expr_status_handler_dict_by_frame[self.frame_num-2].get(self.line_number, None)) is None:
                        sys.exit("expr status handler is not found")

                    if (result := current_expr_status_handler.check_expr_automatically()) == "end":
                        if isinstance(current_expr_status_handler, ReturnStatusHandler):
                            self.expr_status_handler_dict_by_frame.pop(-1)
                            return current_expr_status_handler.result
                        else:
                            self.expr_status_handler_dict_by_frame[self.frame_num-2].pop(self.line_number)
                    elif result == "next_function":
                        current_comment_handler, index = current_expr_status_handler.get_next_function()
                        current_comment_handler.set_function_comment(self.analyze_next_function_in_skip())
                    
            return None

        def analyze_frame(self, backToLine: int | None = None) -> int: # Literal[PROGRESS, CONTINUE]
            if self.line_data.get(self.func_name, None) and self.line_number in self.line_data[self.func_name]["lines"]:
                print("herearaega??")
                
                if (event := self.event_reciever()) is None:
                    return CONTINUE

                execution_info: ExecutionInfo | None = event.get("execution_info")

                if execution_info is not None:
                    # ここで何が返されるかによって次のアクションに向かうか、今のアクションを解析するか、間違ったアクションをしたのかを解析する
                    if self.check_expr_status(execution_info) is False:
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

            # if not len(self.expr_status_handler_list):
            #     return PROGRESS
            
            # current_expr_status_handler = self.expr_status_handler_list[-1]
            # if not isinstance(current_expr_status_handler, ForStatusHandler) or not current_expr_status_handler.required_var_list:
            #     return PROGRESS
            
            # vars_declared = set(self.vars_tracker.vars_declared[-1])
            # vars_required = current_expr_status_handler.required_var_list
            # current_expr_status_handler.required_var_list = [v for v in vars_required if v not in vars_declared]
            # if not len(current_expr_status_handler.required_var_list):
            #     return PROGRESS
            
            # current_expr_status_handler.required_var_list = None

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
    
        def event_sender(self, send_event: SendEvent, get_line: bool = True) -> None:
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
                    gvars = self.vars_tracker.get_global_value(), 
                    vars = self.vars_tracker.get_value_each_frame()
                )

                # ゲーム側で行番は取得済みなのでget_lineフラグはFalseにする
                get_line = False
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

                if get_line:
                    if len(self.skipped_var_declaration_lines):
                        # 初期化されていない変数はスキップされてしまうので、そのような変数があるなら最初の行数を取得する
                        send_event["line"] = int(self.skipped_var_declaration_lines[0])
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