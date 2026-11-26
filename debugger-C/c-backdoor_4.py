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

# ループ処理の開始地点から終了地点を登録するクラス 
# ループスキップ処理の判断の際に用いる
class LoopLineInfo(TypedDict):
    type: Literal["while", "do_while", "for"]
    top_edge: int
    bottom_edge: int

# EvaluateExpressionのラッパーメソッド
def evaluate_expression_wrapper(frame: lldb.SBFrame, expression: str):
    if not isinstance((sb_value := frame.EvaluateExpression(expression)), lldb.SBValue):
        sys.exit("error in evaluate expression")
    return sb_value

# 計算式文字列からその計算結果を取得する
def evaluate_expression(frame: lldb.SBFrame, expression: str) -> str | None:
    return evaluate_expression_wrapper(frame, expression).GetValue()

def evaluate_expression_address(frame: lldb.SBFrame, expression: str) -> str:
    result = evaluate_expression_wrapper(frame, expression).GetValueAsUnsigned()
    if not isinstance(result, int):
        return ""
    return str(hex(result))

def get_thread(frame: lldb.SBFrame):
    sb_thread = frame.GetThread()
    if not isinstance(sb_thread, lldb.SBThread):
        sys.exit("error in GetThread")
    if not sb_thread.IsValid():
        sys.exit("invalid SBThread is found")
    return sb_thread

def get_process(thread: lldb.SBThread):
    sb_process = thread.GetProcess()
    if not isinstance(sb_process, lldb.SBProcess):
        sys.exit("error in GetProcess")
    if not sb_process.IsValid():
        sys.exit("invalid SBProcess is found")
    return sb_process

def get_target(process: lldb.SBProcess):
    sb_target = process.GetTarget()
    if not isinstance(sb_target, lldb.SBTarget):
        sys.exit("error in GetTarget")
    if not sb_target.IsValid():
        sys.exit("invalid SBTarget is found")
    return sb_target

def get_sb_value_type(value: lldb.SBValue):
    sb_type = value.GetType()
    if not (isinstance(sb_type, lldb.SBType) and sb_type.IsValid()):
        sys.exit("invalid SBType is found")
    return sb_type

def dereference_sb_value(value: lldb.SBValue):
    dereferenced_value = value.Dereference()
    if not isinstance(dereferenced_value, lldb.SBValue):
        sys.exit("invalid dereferenced SBValue is found")
    return dereferenced_value

# 計算式解析ハンドラクラス
class DynamicCommentHandler:
    def __init__(self, comments: list[Comment], side_effect_values: dict[str, SideEffectValue] | None = None):
        # a (=5) + b (=4) のような、変数(計算式)とその値を表示する文字列を、途中式のidごとに記録する
        # 計算式の評価がどうなろうと、このリストの内容は一定(計算式の生文字列)なので初期化時に全て取得しておく
        self.expr_str_to_show_by_id = self.get_str_base(comments)
        # 分析初期化メソッドでリセットする
        self.initialize_analysis(comments)
        # 演算子による副作用後の値を登録する (計算中に使われる値と、計算後の値)
        self.side_effect_values = side_effect_values if side_effect_values is not None else {}

    # while, do_while, for文がもう一度来たときのために分析部分の所だけリセットできるメソッドを設けておく
    def initialize_analysis(self, comments: list[Comment]):
        self.index_scanned_currently = 0
        # a + b (=9) のような、途中式(comment)の結果を記録する 
        self.expr_result_by_id: list[str | None] = [None] * len(comments) 
        # 「aとbをかけます」のような、説明文をidごとに記録する
        self.expr_description_to_show_by_id: list[str | Comment] = comments.copy()
        # a[i] = a[1] のような、計算用の文字列を取得する (side_effect_valuesへの登録に用いる)
        self.str_for_evaluation_by_id: list[str | None] = [None] * len(comments)

        # 計算されずに飛ばされた自作関数を登録するリスト
        self.skipped_function_list: list[str] = []

        self.current_function_comment: FunctionComment | None = None

    # 計算式そのものの文字列を取得する。その結果は解析中に動的に取得し、str_base (= 結果)のようにして表示メッセージを生成する
    def get_str_base(self, comments: list[Comment]):
        expr_str_base_list: list[str] = []

        for comment in comments:
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

                for expr_part in expr_description["expr"]:
                    if "category" in expr_part:
                        expr_str_base_list_by_part.append(self.get_reference_str_base(expr_part, expr_str_base_list))
                    elif "text" in expr_part:
                        expr_str_base_list_by_part.append(expr_part["text"])
                    elif "macro" in expr_part: # 今はスカラー値のみを考えるが、後々、関数やifdefも考えられると良いかも
                        expr_str_base_list_by_part.append(expr_part["macro"])
                    elif "operator" in expr_part:
                        if "is_front_operator" in expr_part:
                            expr_str_base = (
                                f"{expr_part["operator"]}{expr_str_base_list[expr_part["operand_id"]]}" # 前置
                                if expr_part["is_front_operator"] else 
                                f"{expr_str_base_list[expr_part["operand_id"]]}{expr_part["operator"]}" # 後置
                            )
                        else:
                            expr_str_base = f"{expr_str_base_list[expr_part["left_operand_id"]]} {expr_part["operator"]} {expr_str_base_list[expr_part["right_operand_id"]]}"
                        expr_str_base_list_by_part.append(expr_str_base)
                    elif "addr_operator" in expr_part:
                        expr_str_base_list_by_part.append(f"{expr_part["addr_operator"]}{expr_str_base_list[expr_part["operand_id"]]}")
                    else: # expr_id
                        expr_str_base_list_by_part.append(expr_str_base_list[expr_part["expr_id"]])

                expr_str_base_list.append(" ".join(expr_str_base_list_by_part))
        
        return expr_str_base_list

    # 変数そのものの文字列を取得する
    def get_reference_str_base(self, expr_part: ScalarVariablePart | StructVariablePart | ArrayVariablePart, expr_str_to_show_by_id: list[str]):
        if expr_part["category"] == "scalar":
            # scalar variableの結果自体は取得する必要がない
            reference = expr_part["name"]
        elif expr_part["category"] == "struct":
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
                if self.check_value_bool(self.get_expr_result(int(line)), frame) is not condition:
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

                for expr_part in expr_description["expr"]:
                    if "category" in expr_part:
                        reference_str_base, reference_str_to_show = self.get_reference_expr_comments(expr_part, frame)
                        result_str_to_show = self.get_variable_value(frame, reference_str_base, expr_part["value_type"])
                        str_for_evaluation_list.append(result_str_to_show)
                        str_to_show_list.append(f"<{reference_str_to_show}>(={result_str_to_show})")
                    elif "text" in expr_part:
                        if expr_part["text"] in ("||", "&&", "?"):
                            if special_operator is not None:
                                sys.exit("condition operator cannot be overlapped")
                            special_operator = expr_part["text"]

                        str_for_evaluation_list.append(expr_part["text"])
                        str_to_show_list.append(expr_part["text"])
                    elif "macro" in expr_part: # 今はスカラー値のみを考えるが、後々、関数やifdefも考えられると良いかも
                        str_for_evaluation_list.append(expr_part["macro"])
                        str_to_show_list.append(f"<{expr_part["macro"]}>(={evaluate_expression(frame, expr_part["macro"])})")
                    elif "operator" in expr_part:
                        if "is_front_operator" in expr_part:
                            str_to_show_base = self.get_expr_to_show(expr_part["operand_id"] + 1)

                            operand_str = self.get_str_for_evaluation(expr_part["operand_id"])

                            if (operand_result := self.get_expr_result(expr_part["operand_id"])) is None:
                                sys.exit("result of operand of unary expression is not found")

                            if (operator := expr_part["operator"]) in ("++", "--"):
                                # 未定義動作を弾く
                                if (variable_value_str_after_side_effect := self.side_effect_values.get(operand_str)) is not None:
                                    if variable_value_str_after_side_effect["result_value_str"] is not None:
                                        sys.exit("undefined expression is found")

                                if expr_part["is_front_operator"]:
                                    current_value_str = f"{variable_value_str_after_side_effect["current_value_str"] if variable_value_str_after_side_effect is not None else operand_result} {'+' if operator == "++" else '-'} 1"
                                    result_value_str = current_value_str
                                else:
                                    current_value_str = variable_value_str_after_side_effect["current_value_str"] if variable_value_str_after_side_effect is not None else operand_result
                                    result_value_str = f"{current_value_str} {'+' if operator == "++" else '-'} 1"

                                if variable_value_str_after_side_effect:
                                    variable_value_str_after_side_effect["current_value_str"] = current_value_str
                                    variable_value_str_after_side_effect["result_value_str"] = result_value_str
                                else:
                                    self.side_effect_values[operand_str] = SideEffectValue(
                                        current_value_str = current_value_str,
                                        result_value_str = result_value_str
                                    )
                            else:
                                current_value_str = f"{operator}{operand_result}" if expr_part["is_front_operator"] else f"{operand_result}{operator}"
                        else:
                            str_to_show_base = self.get_expr_to_show(expr_part["right_operand_id"] + 1)
                            left_operand_str = self.get_str_for_evaluation(expr_part["left_operand_id"])
                            # right_operand_str = self.get_str_for_evaluation(expr_part["right_operand_id"])

                            # 未定義動作を弾く
                            if (variable_value_str_after_side_effect := self.side_effect_values.get(left_operand_str)) is not None:
                                if variable_value_str_after_side_effect["result_value_str"] is not None:
                                    sys.exit("undefined expression is found")

                            if expr_part["operator"] == "=":
                                if (right_operand_result := self.get_expr_result(expr_part["right_operand_id"])) is None:
                                    sys.exit("result of right operand of \"=\" operator is not found")
                                current_value_str = right_operand_result
                            else:
                                if (left_operand_result := self.get_expr_result(expr_part["left_operand_id"])) is None:
                                    sys.exit(f"result of right operand of \"{expr_part["operator"]}\" operator is not found")
                                if (right_operand_result := self.get_expr_result(expr_part["right_operand_id"])) is None:
                                    sys.exit(f"result of right operand of \"{expr_part["operator"]}\" operator is not found")
                                current_value_str = f"{left_operand_result} {expr_part["operator"][:-1]} {right_operand_result}"

                            if variable_value_str_after_side_effect:
                                variable_value_str_after_side_effect["current_value_str"] = current_value_str
                                variable_value_str_after_side_effect["result_value_str"] = current_value_str
                            else:
                                self.side_effect_values[left_operand_str] = SideEffectValue(
                                    current_value_str = current_value_str,
                                    result_value_str = current_value_str
                                )
                        str_for_evaluation_list.append(current_value_str)
                        str_to_show_list.append(f"<{str_to_show_base}>(={current_value_str})")
                    elif "addr_operator" in expr_part:
                        str_to_show_base = self.get_expr_to_show(expr_part["operand_id"] + 1)
                        value = (
                            self.get_value_at_address(frame, expr_part)
                            if expr_part["addr_operator"] == "*" else
                            evaluate_expression(frame, f"{expr_part["addr_operator"]}{self.get_str_for_evaluation(expr_part["operand_id"])}")
                        )
                        str_for_evaluation_list.append(value)
                        str_to_show_list.append(f"<{str_to_show_base}>(={value})")
                    else: # expr_id
                        str_to_show_base = self.get_expr_to_show(expr_part["expr_id"])
                        if (result := self.get_expr_result(expr_part["expr_id"])) is None:
                            sys.exit(f"result of {str_to_show_base} is not found")

                        str_for_evaluation_list.append(result)
                        str_to_show_list.append(f"<{str_to_show_base}>(={result})")

                '''
                ここで"||", "&&", "?"の演算子の処理を行う
                a || b の時はbが未処理なら"1"(aが真であるため), bが未処理でないならbool(b)で真偽(1, 0)を確かめ、その値をstr_for_evaluationリストに登録する
                a && b の時はbが未処理なら"0"(aが偽であるため), bが未処理でないならbool(b)で真偽(1, 0)を確かめ、その値をstr_for_evaluationリストに登録する
                c ? a : b の時はaが未処理ならbの値, bが未処理ならaの値をstr_for_evaluationリストに登録する
                未処理の計算式については、Noneをstr_for_evaluationに登録する
                '''
                description_to_show_list = []
                for expr_part in expr_description["description"]:
                    if "category" in expr_part:
                        reference_description_base, reference_description_to_show = self.get_reference_expr_comments(expr_part, frame)
                        value = evaluate_expression(frame, reference_description_base)
                        description_to_show_list.append(
                            f"{reference_description_to_show}(={value})"
                            if value is not None else
                            reference_description_to_show
                        )
                    elif "text" in expr_part:
                        description_to_show_list.append(expr_part["text"])
                    elif "macro" in expr_part: # 今はスカラー値のみを考えるが、後々、関数やifdefも考えられると良いかも
                        description_to_show_list.append(f"{expr_part["macro"]}(={evaluate_expression(frame, expr_part["macro"])})")
                    # 型定義でdescriptionの方だけ取り除くのは面倒なので、ここでエラーを出させる
                    elif "operator" in expr_part:
                        sys.exit("description parts cannot include unary or binary part")
                    elif "addr_operator" in expr_part:
                        sys.exit("description parts cannot include address part")
                    else: # expr_id
                        description_to_show_list.append(self.get_expr_result(expr_part["expr_id"]))

                description_to_show = " ".join(description_to_show_list)
                if special_operator == "||":
                    if str_for_evaluation_list[-1] is None:
                        str_for_evaluation = "1"
                    else:
                        str_for_evaluation = "1" if self.check_value_bool(str_for_evaluation_list[-1], frame) else "0"
                elif special_operator == "&&":
                    if str_for_evaluation_list[-1] is None:
                        str_for_evaluation = "0"
                    else:
                        str_for_evaluation = "1" if self.check_value_bool(str_for_evaluation_list[-1], frame) else "0"
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

            if comment["expr_type"].count('*') + comment["expr_type"].count('['):
                print(comment["expr_type"])
                self.expr_result_by_id[self.index_scanned_currently] = evaluate_expression_address(frame, str_for_evaluation)
            else:
                self.expr_result_by_id[self.index_scanned_currently] = evaluate_expression(frame, str_for_evaluation)
            expr_to_show = self.get_expr_to_show(self.index_scanned_currently)
            self.expr_description_to_show_by_id[self.index_scanned_currently] = f'{expr_to_show}: {description_to_show}' if len(description_to_show) else expr_to_show
            self.str_for_evaluation_by_id[self.index_scanned_currently] = str_for_evaluation

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
        return evaluate_expression_wrapper(frame, f"(int)!!({value})").GetValueAsSigned() != 0

    def get_reference_expr_comments(self, expr_part: ScalarVariablePart | StructVariablePart | ArrayVariablePart, frame: lldb.SBFrame):
        if expr_part["category"] == "scalar":
            # scalar variableの結果自体は取得する必要がない
            reference = expr_part["name"]
            reference_w_result = reference
        elif expr_part["category"] == "struct":
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
                    reference_index_to_show_list.append(f"[<{self.get_expr_to_show(index_part["expr_id"])}>(={self.get_expr_result(index_part["expr_id"])})]")
                    reference_index_base_list.append(f"[{self.get_expr_to_show(index_part["expr_id"])}]")
                else:
                    # text
                    reference_index_to_show_list.append(f"[{index_part["text"]}]")
                    reference_index_base_list.append(f"[{index_part["text"]}]")
            reference_top, reference_top_w_result = self.get_reference_expr_comments(expr_part["parent"], frame)
            reference = ''.join([reference_top, *reference_index_base_list])
            reference_w_result = ''.join([reference_top_w_result, *reference_index_to_show_list])
        return reference, reference_w_result

    def get_variable_value(self, frame: lldb.SBFrame, reference_str_base: str, value_type: str) -> str | None:
        data_value = frame.FindVariable(reference_str_base)

        if not (isinstance(data_value, lldb.SBValue) and data_value.IsValid()):
            data_value = evaluate_expression_wrapper(frame, reference_str_base)

        if not (isinstance(data_value, lldb.SBValue) and data_value.IsValid()):
            sys.exit(f"data value is not found for variable {reference_str_base}")

        pointer_count = 0
        pointer_count += value_type.count('*')
        pointer_count += value_type.count('[')

        result_value = data_value.GetValue()
        if pointer_count == 0 or result_value is not None:
            return result_value

        pointee = data_value
        for _ in range(pointer_count):
            if get_sb_value_type(pointee).IsPointerType():
                pointee = dereference_sb_value(pointee)
            else:
                pointee = pointee.AddressOf()
                if not isinstance(pointee, lldb.SBValue):
                    sys.exit("invalid dereferenced SBValue is found")

            if not pointee.IsValid():
                sys.exit("invalid dereferenced SBValue is found")

        return str(hex(pointee.GetValueAsUnsigned()))
    
    def get_expr_result(self, index: int = -1):
        if index >= len(self.expr_result_by_id):
            sys.exit("error in id number for getting expression result")

        return self.expr_result_by_id[index]

    def get_str_for_evaluation(self, index: int):
        if index >= len(self.str_for_evaluation_by_id):
            sys.exit("error in id number for getting string for evaluation")

        if (str_for_evaluation := self.str_for_evaluation_by_id[index]) is None:
            sys.exit(f"string for evaluation no.{index} is not found")

        return str_for_evaluation

    def get_expr_to_show(self, index: int):
        if index >= len(self.expr_str_to_show_by_id):
            sys.exit("error in id number for getting expression result")
        
        return self.expr_str_to_show_by_id[index]

    def get_current_function(self):
        if self.current_function_comment is None:
            sys.exit("current function comment is not found")
        return self.current_function_comment["func_name"]

    def get_value_at_address(self, frame: lldb.SBFrame, addr_operand_part: AddressOperandPart) -> str | None:
        target = get_target(get_process(get_thread(frame)))
        result_type = addr_operand_part["result_type"]
        pointer_count = result_type.count("*")
        base_type_name = result_type.replace("*", "").strip()

        sb_type = target.FindFirstType(base_type_name)

        if not (isinstance(sb_type, lldb.SBType) and sb_type.IsValid()):
            sys.exit(f"invalid type: {base_type_name}")

        for i in range(pointer_count):
            sb_type = sb_type.GetPointerType()
            if not (isinstance(sb_type, lldb.SBType) and sb_type.IsValid()):
                sys.exit(f"invalid type: {base_type_name}{"*" * (i+1)}")

        if (operand_address_str := self.get_expr_result(addr_operand_part["operand_id"])) is None:
            sys.exit("result of operand of unary expression is not found")
        operand_address = lldb.SBAddress(int(operand_address_str, 16), target)

        sb_value = target.CreateValueFromAddress(
            "value",
            operand_address,
            sb_type
        )

        if not (isinstance(sb_value, lldb.SBValue) and sb_value.IsValid()):
            sys.exit(f"value is not found at address {operand_address_str}")

        return sb_value.GetValue()

    def get_arg_comment_of_current_function(self):
        if self.current_function_comment is None:
            sys.exit("current function comment is not found")

        return [
            self.get_expr_result(expr_part["expr_id"]) if "expr_id" in expr_part else None
            for expr_part in self.current_function_comment["description"]
        ]

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
            
            if "func_name" in comment["comment"] and all(self.get_expr_result(int(index)) is result for index, result in comment["execution_condition"].items()):
                return False

        return True


# 変数の実行処理ハンドラ
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
    comments: DynamicCommentHandler | None
    initialized: bool
    is_analysis_completed: bool


# 変数以外の実行処理ハンドラのベース
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
        # 副作用辞書は共通のものを設定することで、計算量や代入の手間を減らせる
        side_effect_values: dict[str, SideEffectValue] = {}
        self.dynamic_conditions = [
            DynamicCommentHandler(
                comments = if_condition_comment["comments"],
                side_effect_values = side_effect_values
            ) 
            for if_condition_comment in conditions
        ]
        self.scanning_condition_index: int = 0
        # (条件文のインデックス, 条件文の行番)のタプルを取得し、self.check_conditionsで合致するかを確認する
        self.true_condition: tuple[int, int] | None = None

    def analyze_comment(self, frame: lldb.SBFrame):
        if self.true_condition is not None:
            return

        ### 今までは全ての条件を一気に解析していたが、現在の実行状況(self.line_numberなど)と同期していなかったので、
        dynamic_comment_handler = self.dynamic_conditions[self.scanning_condition_index]

        if dynamic_comment_handler.current_function_comment is not None:
            return
        
        # まずは解析
        if dynamic_comment_handler.set_expr_comments(frame):
            # 解析が途中で終了する = 自作関数が現れた → ひとまずは解析を終了する
            return
        
        # 解析終了 → 本条件の値の真偽値を取得し、その結果をresultsに格納する
        result = dynamic_comment_handler.get_result_bool(frame)

        # 条件がTrueならそれ以降の条件は確認しないので
        if result is True:
            self.true_condition = (self.scanning_condition_index, self.conditions[self.scanning_condition_index]["line"])
            return

        # side_effect_values = dynamic_comment_handler.side_effect_values
        # for value in side_effect_values.values():
        #     value["current_value_str"] = value["result_value_str"]
        #     value["result_value_str"] = None
        dynamic_comment_handler.side_effect_values.clear()
        self.scanning_condition_index += 1

        if len(self.conditions) == self.scanning_condition_index and self.true_condition is None:
            self.true_condition = (-1, self.conditions[-1]["line"])

    def get_next_function(self):
        if self.true_condition is not None:
            sys.exit("this if statement is already completely scanned")

        return self.dynamic_conditions[self.scanning_condition_index], self.scanning_condition_index

    def get_skipped_functions(self):
        return [
            dynamic_comment_handler.skipped_function_list 
            for dynamic_comment_handler in self.dynamic_conditions
        ]
    
    def check_conditions(self, send_event: Debugger2GameEvent, true_condition_index: int):
        if true_condition_index < -1 or len(self.conditions) <= true_condition_index:
            sys.exit(f"a given true condition index has to between -1 and {len(self.conditions)}")

        if self.true_condition is None:
            return "next_function"
            
        if self.true_condition[0] != true_condition_index:
            return "incorrect"

        condition_count = (
            len(self.dynamic_conditions)
            if true_condition_index == -1
            else true_condition_index + 1
        )

        send_event["execution_and_result_str_list"] = [
            ExecutionAndResultStr(
                execution=dynamic_comment_handler.get_str_after_analysis_completed(),
                result=(
                    f"so, the {i+1}th condition is {'True' if i == true_condition_index else 'False'}"
                    if self.is_english else 
                    f"ゆえに、{i+1}番目の条件は{'真' if i == true_condition_index else '偽'}です"
                )
            )
            for i, dynamic_comment_handler
            in enumerate(self.dynamic_conditions[:condition_count])
        ]

        return "correct"

    def check_expr_automatically(self):
        if self.true_condition is not None:
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
    
    def check_condition(self, send_event: Debugger2GameEvent, condition: bool):
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


class DoWhileInitializerStatusHandler(DynamicNonVarStatusHandler):
    def __init__(self, line: int, is_english: bool):
        super().__init__(line, is_english)

    def check_arrival(self, send_event: Debugger2GameEvent):
        send_event["execution_and_result_str_list"] = [
            ExecutionAndResultStr(
                execution = "the first do-while loop begins" if self.is_english else "do while文の最初の繰り返しが始まります",
                result = None
            )
        ]
        return "correct"


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
    
    def check_condition(self, send_event: Debugger2GameEvent, condition: bool):
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

        side_effect_values: dict[str, SideEffectValue] = {}
        self.initializer = ForInitializerStatus(
            expr = initializer,
            dynamic_expr = DynamicCommentHandler(
                comments = initializer,
                side_effect_values = side_effect_values
            ),
        ) if (initializer := expr.get("initializer", None)) is not None else None
        
        # self.required_var_list = [
        #     (var_info["varNode"]["name"], line) 
        #     for var_info in var_initializer
        # ] if (var_initializer := expr.get("var_initializer", None)) is not None else None
        self.required_var_list: list[tuple[str, int]] | None = None
        
        self.condition = ForConditionStatus(
            expr = expr["condition"],
            dynamic_expr = DynamicCommentHandler(
                comments = condition,
                side_effect_values = side_effect_values
            ) if len(condition := expr["condition"]) else None, 
            result = None,
            is_check_completed = False
        )

        self.change = ForChangeStatus(
            expr = change,
            # 一回目のループ直前には変更式に到達することはないのでDynamicCommentHandlerは生成しない
            dynamic_expr = None
        ) if (change := expr.get("change", None)) is not None else None

        self.is_first_arrival = True

    def analyze_comment(self, frame: lldb.SBFrame):
        # is_firstがTrue = まだ初期化が済んでいない
        if self.is_first_arrival:
            # 初期化部があるならその解析を行う
            if self.initializer is not None:
                if self.required_var_list is not None:
                    sys.exit("variable initializer cannot be mixed with normal initializer")
                
                dynamic_comment_handler = self.initializer["dynamic_expr"]
                if (dynamic_comment_handler.set_expr_comments(frame)):
                    return

                for value in self.initializer["dynamic_expr"].side_effect_values.values():
                    value["current_value_str"] = value["result_value_str"]
                    value["result_value_str"] = None
            elif self.required_var_list is not None:
                if self.initializer is not None:
                    sys.exit("normal initializer cannot be mixed with variable initializer")
                return
            
            if (dynamic_comment_handler := self.condition["dynamic_expr"]):
                if dynamic_comment_handler.set_expr_comments(frame):
                    return

                self.condition["result"] = dynamic_comment_handler.get_result_bool(frame)
            # (else) 条件がない = 常に条件がTrue → 解析しない
            else:
                self.condition["result"] = True

            self.is_first_arrival = False
        else:
            if self.initializer is not None or self.required_var_list is not None:
                sys.exit("initializer or var_initializer have to be already done")
            
            # is_initializer is True = 条件部に戻ってきた → その前に更新式の解析を行う
            if self.change is not None:
                # 戻ってきた直後には更新式がないので生成する
                if self.change["dynamic_expr"] is None:
                    if (dynamic_comment_handler := self.condition["dynamic_expr"]):
                        side_effect_values: dict[str, SideEffectValue] = dynamic_comment_handler.side_effect_values
                        side_effect_values.clear()
                    else:
                        side_effect_values = {}

                    self.change["dynamic_expr"] = DynamicCommentHandler(
                        comments = self.change["expr"],
                        side_effect_values = side_effect_values
                    )

                dynamic_comment_handler = self.change["dynamic_expr"]
                if dynamic_comment_handler.set_expr_comments(frame):
                    return

                for value in dynamic_comment_handler.side_effect_values.values():
                    value["current_value_str"] = value["result_value_str"]
                    value["result_value_str"] = None
            
            if (dynamic_comment_handler := self.condition["dynamic_expr"]):
                if dynamic_comment_handler.set_expr_comments(frame):
                    return
                
                self.condition["result"] = dynamic_comment_handler.get_result_bool(frame)
            else:
                self.condition["result"] = True

    def get_next_function(self):
        if self.initializer is not None:
            dynamic_comment_handler = self.initializer["dynamic_expr"]
        elif self.change is not None and self.change["dynamic_expr"] is not None:
            dynamic_comment_handler = self.change["dynamic_expr"]
        elif (dynamic_comment_handler := self.condition["dynamic_expr"]) is not None:
            pass
        else:
            return None

        return dynamic_comment_handler, 0

    def get_skipped_functions(self):
        if self.initializer is not None:
            return [self.initializer["dynamic_expr"].skipped_function_list]
        elif self.change is not None and self.change["dynamic_expr"] is not None:
            return [self.change["dynamic_expr"].skipped_function_list]
        elif (dynamic_comment_handler := self.condition["dynamic_expr"]) is not None:
            return [dynamic_comment_handler.skipped_function_list]
        else:
            return None

    def check_status(self, send_event: Debugger2GameEvent, execution_info: ForExecutionInfo):
        if execution_info["type"] == "for":
            if self.initializer is not None or self.required_var_list is not None:
                return "incorrect"
            
            if self.change is not None and self.change["dynamic_expr"] is not None:
                return "incorrect"
            
            if (result := self.condition["result"]) is None:
                return "next_function"
            
            if result is not execution_info["condition"]:
                return "incorrect"

            self.condition["is_check_completed"] = True
            send_event["execution_and_result_str_list"] = [
                ExecutionAndResultStr(
                    execution = (
                        dynamic_comment_handler.get_str_after_analysis_completed() 
                        if (dynamic_comment_handler := self.condition["dynamic_expr"]) else 
                        (
                            "no condition expression" 
                            if self.is_english else 
                            "条件式がない"
                        )
                    ),
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

        if (result := self.condition["result"]) is None:
            return "next_function"

        self.condition["is_check_completed"] = True

        return "progress" if result else "end"

class ForInitializerStatus(TypedDict):
    expr: list[Comment]
    dynamic_expr: DynamicCommentHandler

class ForConditionStatus(TypedDict):
    expr: list[Comment]
    dynamic_expr: DynamicCommentHandler | None
    result: bool | None
    is_check_completed: bool

class ForChangeStatus(TypedDict):
    expr: list[Comment]
    dynamic_expr: DynamicCommentHandler | None


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

    def check_status(self, send_event: Debugger2GameEvent, execution_info: SwitchCaseExecutionInfo):
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

        if self.default_index is None and self.matched_case is not None:
            return "end"

        if self.default_index is not None and self.matched_case is None:
            return "end"

        sys.exit("all case exprs of switch statement have to be calculated at once")

    def get_matched_group_line(self):
        if self.dynamic_condition.current_function_comment is not None:
            return None

        if self.matched_case is not None:
            return self.matched_case[1]

        if self.default_index is not None:
            return self.case_expr_list_by_index[self.default_index][0]["line"]

        sys.exit("any cases are not found matched")
    
class CaseStatus(TypedDict):
    case_expr: list[Comment]
    dynamic_case_expr: DynamicCommentHandler
    result: str | None
    line: int


class ControlFlowStatusHandler(DynamicNonVarStatusHandler):
    def __init__(self, line: int, type: Literal["break", "continue"], condition_line: int, is_english: bool):
        super().__init__(line, is_english)
        self.type = type
        self.condition_line = condition_line

    def check_status(self, send_event: Debugger2GameEvent):
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

    def check_expr(self, send_event: Debugger2GameEvent):
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

    def check_status(self, send_event: Debugger2GameEvent):
        # 計算式の解析が終わっている → 次のアクションに進める → 計算式の結果を取得する
        if (result := self.result) is None:
            return "next_function"

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

class SideEffectValue(TypedDict):
    current_value_str: str
    result_value_str: str | None


def handle_client(conn: socket.socket, addr: tuple[str, int]) -> None:
    # エラーハンドリング
    class ProgramFinished(Exception):
        print("program finished" if args.english else "プログラムが終了しました")

    class RollBack(Exception):
        print("starting rollback" if args.english else "処理の巻き戻しを実行します")
    
    class NoConnection(Exception):
        print("Disconnected from the client" if args.english else "クライアントとの接続が切れました")

    class VarPreviousValue:
        def __init__(self, value: str | None = None, address: int | None = None):
            self.value = value
            self.address = address
            self.children: dict[str, VarPreviousValue] = {}  # 配列の添字や構造体のメンバ

        def update_value(self, value: str | None, address: str | None):
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

            if len(dynamic_variable_info_list := self.dynamic_variable_info_by_line.pop(line_number, [])) == 0:
                side_effect_values: dict[str, SideEffectValue] = {}
                
                dynamic_variable_info_list.extend(
                    [
                        DynamicVarInfo(
                            dynamic_var_node = self.transform_2_dynamic_var_node(var_info["var_node"], side_effect_values),
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

                if (dynamic_comment_handler_w_index := self.analyze_var_expr_comments(dynamic_variable_info["dynamic_var_node"], dynamic_variable_info["skipped_function_list"], frame)) is None:
                    continue
                dynamic_variable_info["current_comment_w_index"] = dynamic_comment_handler_w_index
                break

            self.dynamic_variable_info_by_line[line_number] = dynamic_variable_info_list
  
        def transform_2_dynamic_var_node(self, var_node: VarNode, side_effect_values: dict[str, SideEffectValue]):
            return DynamicVarNode(
                name = var_node["name"],
                type = var_node["type"],
                children = [
                    self.transform_2_dynamic_var_node(child_var_node, side_effect_values)
                    for child_var_node in var_node["children"]
                ],
                comments = DynamicCommentHandler(
                    comments = var_node["comments"],
                    side_effect_values = side_effect_values
                ) if len(var_node["comments"]) != 0 else None,
                initialized = var_node["initialized"],
                is_analysis_completed = False
            )
        
        def analyze_var_expr_comments(self, var_node: DynamicVarNode, skipped_function_list_by_part: list[list[str]], frame: lldb.SBFrame) -> tuple[DynamicCommentHandler, int] | None:
            # コメントの解析が終了している階層はset_expr_commentsすることなく次の階層に遷移する
            if var_node["is_analysis_completed"]:
                skipped_function_list_by_part.append([])
            else:
                if (current_dynamic_comment_handler := var_node["comments"]) is not None:
                    dynamic_comment_handler = self.set_expr_comments(current_dynamic_comment_handler, frame)
                    
                    skipped_function_list_by_part.append(current_dynamic_comment_handler.skipped_function_list)

                    if dynamic_comment_handler is not None:
                        return (dynamic_comment_handler, len(skipped_function_list_by_part)-1)

                    var_node["is_analysis_completed"] = True
                    for value in current_dynamic_comment_handler.side_effect_values.values():
                        value["current_value_str"] = value["result_value_str"]
                        value["result_value_str"] = None
                else:
                    var_node["is_analysis_completed"] = True
            
            for child_var_node in var_node["children"]:
                if child_var_node["name"] == "*" and child_var_node["comments"] is None:
                    address_str = var_node["comments"].get_expr_result()
                    print("address:", address_str, "type:", child_var_node["type"])
                    # child_var_node["comments"] = DynamicCommentHandler(
                    #     comments = [
                    #         Comment(
                    #             id = 0,
                    #             comment = ExprDescription(
                    #                 description = [
                    #                     TextPart(
                    #                         text = ""
                    #                     )
                    #                 ],
                    #                 expr = [

                    #                 ]
                    #             )
                    #         )
                    #     ]
                    # )
                if (dynamic_comment_handler_w_index := self.analyze_var_expr_comments(child_var_node, skipped_function_list_by_part, frame)):
                    return dynamic_comment_handler_w_index
            
            return None
          
        def get_reference_expr_comments(self, expr_part: ScalarVariablePart | StructVariablePart | ArrayVariablePart, expr_result_by_id: dict[int, any], expr_str_to_show_by_id: dict[int, str], frame: lldb.SBFrame):
            if expr_part["category"] == "scalar":
                # scalar variableの結果自体は取得する必要がない
                reference = expr_part["name"]
                reference_w_result = reference
            elif expr_part["category"] == "struct":
                # struct variableの結果自体は取得する必要がない。
                struct_base, struct_base_w_result = self.get_reference_expr_comments(
                    expr_part["parent"], 
                    expr_result_by_id, 
                    expr_str_to_show_by_id, 
                    frame
                )
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
                reference_top, reference_top_w_result = self.get_reference_expr_comments(
                    expr_part["parent"], 
                    expr_result_by_id, 
                    expr_str_to_show_by_id, 
                    frame
                )
                reference = ''.join([reference_top, *reference_index_base_list])
                reference_w_result = ''.join([reference_top_w_result, *reference_index_to_show_list])
            return reference, reference_w_result

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

                var_type = get_sb_value_type(var)
                if var_type.IsPointerType():
                    pointee_type = var_type.GetPointeeType()
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
                                deref = dereference_sb_value(var)
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
                name = '*' if get_sb_value_type(var).IsPointerType() else var.GetName() 
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

                var_type = get_sb_value_type(var)
                if var_type.IsPointerType():
                    pointee_type = var_type.GetPointeeType()
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
                                deref = dereference_sb_value(var)
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
                    variable_value = VariableValue(
                        value = self.previous_values[-1][var_key].value,
                        children = self.get_value_by_part(self.previous_values[-1][var_key].children)
                    )
                )
                for var_key in self.vars_declared[-1] if var_key in self.previous_values[-1]
            ]
        
        def get_value_by_frame(self):
            return [
                [
                    VariableInfo(
                        name = var_key[0],
                        line = var_key[1],
                        variable_value = VariableValue(
                            value = self.previous_values[i][var_key].value,
                            children = self.get_value_by_part(self.previous_values[i][var_key].children)
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
                    variable_value = VariableValue(
                        value = global_previous_value.value, 
                        children = self.get_value_by_part(global_previous_value.children)
                    )
                )
                for var_key, global_previous_value in self.global_previous_values.items()
            ]

        def get_value_by_part(self, previous_values: dict[str, VarPreviousValue]):
            return {
                var_part: VariableValue(
                    value = previous_value.value, 
                    children = self.get_value_by_part(previous_value.children)
                )
                for var_part, previous_value in previous_values.items()
            }
        
        def get_value_partly(self, var_name: tuple[str, int], value_path: list[str]):
            temp_previous_value = self.previous_values[-1][var_name]
            while len(value_path):
                children_name = value_path.pop(0)
                temp_previous_value = temp_previous_value.children[children_name]
            return temp_previous_value.value

        def get_declared_var_value_w_comment(self, var: tuple[str, int], var_node: DynamicVarNode):
            var_previous_value = self.previous_values[-1].get(var)
            return self.get_declared_var_value_w_comment_by_part(var_node, var_previous_value)

        def get_declared_var_value_w_comment_by_part(self, var_node: DynamicVarNode, previous_value: VarPreviousValue | None,):
            print(previous_value.value if previous_value else previous_value)
            dynamic_comment_handler = var_node["comments"]

            if dynamic_comment_handler:
                value = dynamic_comment_handler.get_expr_result() or (previous_value.value if previous_value else None)
            else:
                value = previous_value.value if previous_value else None

            comment = (
                dynamic_comment_handler.get_str_after_analysis_completed()
                if dynamic_comment_handler
                else None
            )

            previous_value_children = previous_value.children if previous_value is not None else {}

            children = {
                child["name"]: self.get_declared_var_value_w_comment_by_part(
                    child,
                    previous_value_children.get(child["name"])
                )
                for child in var_node["children"]
            }

            return VariableValueWComment(
                value=value,
                type=var_node["type"],
                comment=comment,
                children=children,
                initialized=var_node["initialized"],
            )

        def get_arg_value(self, var_info: VarInfo, comment: str | None):
            variable_value_w_comment = self.get_arg_value_by_part(
                self.previous_values[-1][(var_info["var_node"]["name"], var_info["start"])],
                var_info["var_node"]
            )

            variable_value_w_comment["comment"] = comment

            return variable_value_w_comment

        def get_arg_value_by_part(self, previous_value: VarPreviousValue, var_node: VarNode):
            children: dict[str, VariableValueWComment] = {}

            for child_var_node in var_node["children"]:
                if child_var_node["name"] not in previous_value.children:
                    sys.exit("child keys of previous value do not match child keys of var node")

                children[child_var_node["name"]] = self.get_arg_value_by_part(
                    previous_value.children[child_var_node["name"]], 
                    child_var_node
                )

            return VariableValueWComment(
                value = previous_value.value,
                type = var_node["type"],
                comment = None,
                children = children,
                initialized = var_node["initialized"]
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
            self.events_history: list[Game2DebuggerEvent] = []
            self.process: lldb.SBProcess | None = None
            self.thread: lldb.SBThread | None = None
            self.is_english: bool = args.english

        def reset_state(self):
            self.is_end = False
            self.line_number: int = 0
            self.next_line_number: int = 0
            self.line_loop_dict_by_frame: list[dict[int, LoopLineInfo]] = [{}]
            self.dynamic_comment_handler_being_checked: list[DynamicCommentHandler] = []
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
            self.switch_expr_status_handler: SwitchStatusHandler | None = None

        def set_process_and_thread(self, process: lldb.SBProcess, thread: lldb.SBThread) -> None:
            self.process = process
            self.thread = thread

            if (next_state := self.get_next_state()):
                self.state, self.frame, self.file_name, self.next_line_number, self.func_crnt_name, self.next_frame_num = next_state
                with open(f"{DATA_DIR}/{self.file_name[:-2]}/{self.file_name[:-2]}_line.json", 'r') as f:
                    self.line_data: dict[str, LineInfoDataByFunc] = json.load(f)
                    self.func_name = self.func_crnt_name
                    self.frame_num: int = 1
                    self.get_std_outputs()

                    self.event_sender(
                        Debugger2GameEvent(
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
                    Debugger2GameEvent(
                        message = "", 
                        is_end = True, 
                        status = "ok"
                    ), 
                    False
                )
                self.is_end = True

            self.vars_tracker.start_tracking(self.frame)
            self.vars_checker(self.line_number)

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

        def skip_whitespace(self, text, pos):
            """空白・改行・タブをスキップ"""
            while pos < len(text) and text[pos].isspace():
                pos += 1
            return pos

        def match_scanf(self, fmt: str, text: str):
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
                    pos = self.skip_whitespace(text, pos)

                pat = self.scanf_patterns.get(token.lstrip("*"), (None, None))[0]
                if not pat:
                    raise ValueError(f"Unsupported format specifier: {token}")

                if pos >= len(text):
                    return "incomplete", results, "", {"incomplete": [f'{t}: {self.scanf_patterns.get(t.lstrip("*"), (r"", "不明な指定子"))[1]}' for t in tokens[i:]]}
                
                regex = re.compile(pat)
                match = regex.match(text, pos)
                # mismatchしたらscanfは終了して、mismatch以降の変数にはランダムな値が入るので、解析を終了する
                if not match:
                    return "mismatch", results, text[pos:], {"mismatch": f'{token}: {self.scanf_patterns[token.lstrip("*")][1]}', "incomplete": [f'{t}: {self.scanf_patterns.get(t.lstrip("*"), (r"", "不明な指定子"))[1]}' for t in tokens[i+1:]]}

                value = match.group(0)
                # *がつく指定子では変数に代入しない
                if not token.startswith("%*"):
                    results.append(value)
                pos = match.end()

            return "ok", results, text[pos:], {}

        def is_complete_match(self, fmt: str, text: str):
            """入力文字列がフォーマット全体に合致するかを確認"""
            # stateは、incomplete, mismatch, okのどれか(これで入力の過不足一致不一致を確認する)
            # resultsは一致した入力の結果
            # remainingは入力の過分
            state, results, remaining_text, errors = self.match_scanf(fmt, text)
            return state, results, remaining_text, errors


        # 次の処理を取得するためのメソッド
        def step_conditionally(self):
            # プロセスの状態を更新
            if self.is_end:
                self.analyze_non_var_expr_comments(is_end = True)
                self.get_std_outputs()
                return

            # ここでswitch文の下処理(defaultの場合)を行う
            if self.switch_expr_status_handler is not None and self.frame_num == self.next_frame_num:
                if (matched_line := self.switch_expr_status_handler.get_matched_group_line()) is not None:
                    if self.next_line_number < matched_line:
                        while self.next_line_number > matched_line:
                            if (next_state := self.get_next_state()):
                                self.line_number = self.next_line_number
                                self.func_name = self.func_crnt_name
                                self.frame_num = self.next_frame_num
                                self.state, self.frame, self.file_name, self.next_line_number, self.func_crnt_name, self.next_frame_num = next_state
                            else:
                                self.is_end = True
                                self.line_number = self.next_line_number
                                self.frame_num = self.next_frame_num
                                self.func_name = self.func_crnt_name
                        self.switch_expr_status_handler = None
                                
            self.thread = get_thread(self.frame)
            self.process = get_process(self.thread)

            # 初期化されない変数や静的変数はスキップされるので、そのステップを後追いで見る
            while len(self.skipped_var_declaration_lines):
                line = self.skipped_var_declaration_lines.pop(0)
                self.vars_tracker.analyze_var_nodes(line, self.frame)
                self.vars_checker(int(line), is_skipped_var_check = True)
                
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
                    if (event := self.event_receiver()) is None:
                        continue

                    if (new_stdin := event.get('stdin', None)) is not None:
                        
                        # ここの引数の型がis_complete_matchと合致するように後で修正する
                        state, results, remaining, errors = self.is_complete_match(
                            self.input_check_num[(self.next_frame_num, self.next_line_number)][0][input_check][0], 
                            self.stdin_buffer + new_stdin
                        )
                        
                        if state == "incomplete":
                            errorCnt += 1
                            self.event_sender(
                                Debugger2GameEvent(
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
                                Debugger2GameEvent(
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
                            Debugger2GameEvent(
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

            if (next_step := self.analyze_non_var_expr_comments()) is not None:
                return

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
                            Debugger2GameEvent(
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
                            Debugger2GameEvent(
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
                            file_info["address"] = evaluate_expression(self.frame, file_info["varname"])
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
                                        "size": evaluate_expression(self.frame, f"{memory_info["size"]} / sizeof({memory_info["vartype"]})"), 
                                        "vartype": memory_info["vartype"], 
                                        "source_address": memory_info.get("source_address", None)
                                    }
                                )
                                # self.memory_info_to_send.append({"type": memory_info["type"], "varname": memory_info["varname"], "size": evaluate_expression(self.frame, f"{memory_info["size"]} / sizeof({memory_info["vartype"]})"), "vartype": memory_info["vartype"], "address": evaluate_expression(self.frame, memory_info["varname"]), "source_address": memory_info.get("source_address", None)})
                            else:
                                self.memory_info_to_send.append(
                                    {
                                        "type": memory_info["type"], 
                                        "varname": memory_info["varname"], 
                                        "address": evaluate_expression(self.frame, memory_info["varname"])
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
                                    value = evaluate_expression(self.frame, str_info["original"]),
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

            if self.is_end:
                return
            
            if not isinstance((current_expr_status_handler := self.get_expr_status_handler(False)), IfStatusHandler):
                return

            # 真となる条件が存在する = その行番はself.line_numberと合致 → 解析が終わっているのでこれ以上はstep_condtionallyを必要としない
            if current_expr_status_handler.true_condition is not None:
                return

            # 現在の処理が自作関数の確認で止まっている → その解析待ちなのでこれ以上はstep_conditionallyを必要としない
            if current_expr_status_handler.dynamic_conditions[current_expr_status_handler.scanning_condition_index].current_function_comment is not None:
                return

            # 今は次の行番に進めるはずなのに、次が同じ行番または他の関数に遷移する場合を考えていない (今後ありそうなら適宜修正する)
            if self.line_number == self.next_line_number:
                sys.exit(f"if-statement condition line {self.line_number} has to be already completely analyzed")
            if self.frame_num != self.next_frame_num:
                sys.exit(f"it is impossible that there is a function transfer from {self.func_name} to {self.func_crnt_name} here")

            self.expr_status_handler_dict_by_frame[self.next_frame_num-2][self.next_line_number] = self.pop_expr_status_handler(False)
            self.step_conditionally()

        # 次の処理の内容を設定する
        def set_expr_status(self, expr: NonVarComment, line: int) -> DynamicNonVarStatusHandler:
            if expr["type"] == "if":
                expr_status_handler = IfStatusHandler(line, expr["conditions"], self.is_english)
            elif expr["type"] == "while":
                expr_status_handler = WhileStatusHandler(line, expr["condition"], self.is_english)
                self.append_line_loop("while", line)
            elif expr["type"] == "do_while":
                # do (最初のdo-whileループに入る = コメントがない)
                expr_status_handler = (
                    DoWhileStatusHandler(
                        line, 
                        expr["condition"], 
                        self.is_english
                    ) if len(expr["condition"]) else 
                    DoWhileInitializerStatusHandler(
                        line, 
                        self.is_english
                    )
                )
                self.append_line_loop("do_while", line)
            elif expr["type"] == "for":
                expr_status_handler = ForStatusHandler(line, expr, self.is_english)
                # if "var_initializer" in expr:
                #     self.vars_tracker.dynamic_variable_info_by_line[line] = [
                #         DynamicVarInfo(
                #             dynamic_var_node = self.vars_tracker.transform_2_dynamic_var_node(var_info["varNode"]),
                #             start = var_info["start"],
                #             end = var_info["end"],
                #             skipped_function_list = [],
                #             current_comment = None
                #         ) for var_info in expr["var_initializer"]
                #     ]
                self.append_line_loop("for", line)
            elif expr["type"] == "switch":
                expr_status_handler = SwitchStatusHandler(line, expr, self.is_english)
            elif expr["type"] in ("continue", "break"):
                expr_status_handler = ControlFlowStatusHandler(line, expr["type"], expr["condition_line"], self.is_english)
            elif expr["type"] == "expression":
                expr_status_handler = ExpressionStatusHandler(line, expr["expr"], self.is_english)
            else: # return
                expr_status_handler = ReturnStatusHandler(line, expr["expr"], thread, self.is_english)
            
            return expr_status_handler

        # 次の処理情報を取得して移行するためのメソッド
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

        def get_std_outputs(self):
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

        def set_next_line(self, send_event: Debugger2GameEvent, previous_line: int | tuple[int, int], is_func_entry: bool = False):
            self.skipped_var_declaration_lines = []

            if is_func_entry:
                if isinstance(previous_line, tuple):
                    sys.exit("previous line of function entry has to be integer")
                send_event["line"] = previous_line
                if previous_line == self.next_line_number:
                    return
                if str(previous_line) not in self.vars_tracker.declared_variables_by_line:
                    sys.exit(f"variable declaration info of {previous_line} is not found")

                self.skipped_var_declaration_lines.append(str(previous_line))

            next_line_number = self.get_next_line(previous_line, is_func_entry)

            if not is_func_entry:
                send_event["line"] = next_line_number

            while next_line_number != self.next_line_number:
                if str(next_line_number) not in self.vars_tracker.declared_variables_by_line:
                    return

                self.skipped_var_declaration_lines.append(str(next_line_number))
                next_line_number = self.get_next_line(next_line_number, is_func_entry)
                
        def get_next_line(self, previous_line: int | tuple[int, int], is_next: bool):
            if (line_data := self.line_data.get(self.func_crnt_name if is_next else self.func_name)) is None:
                sys.exit(f"line data of function {self.func_crnt_name if is_next else self.func_name} is not found")

            next_line_data_dict = line_data["next_lines"]
            if isinstance(previous_line, int):
                if (next_line_data := next_line_data_dict.get(str(previous_line))) is None:
                    sys.exit(f"next-line data is not found in line {previous_line}")
                if isinstance(next_line_data, dict):
                    sys.exit(f"next-line data in line {line} is integer")
                return next_line_data
            else:
                line, condition = previous_line
                if (next_line_data := next_line_data_dict.get(str(line))) is None:
                    sys.exit(f"next-line data is not found in line {line}")
                if isinstance(next_line_data, int):
                    sys.exit(f"next-line data in line {line} is integer")
                if (skipped_start_line := next_line_data.get(str(condition))) is None:
                    sys.exit(f"next line of line {line} with condition {condition} is not found")
                return skipped_start_line

        def vars_checker(self, line_number: int, is_for_false: bool = False, is_skipped_var_check: bool = False):
            if self.is_end:
                return

            # これだとスコープ外の変数を拾ってしまうことがある (for文から出た時など)
            if is_for_false:
                declared_vars = []
            else:
                declared_vars = [
                    dynamic_variable_info
                    for dynamic_variable_info in self.vars_tracker.dynamic_variable_info_by_line.get(str(line_number), []) 
                    if (dynamic_variable_info["dynamic_var_node"]["name"], line_number) not in self.vars_tracker.vars_declared[-1]
                ]

            # 変数は順番に取得させる
            while len(declared_vars):
                dynamic_variable_info = declared_vars.pop(0)
                var = (dynamic_variable_info["dynamic_var_node"]["name"], line_number)
                errorCnt = 0
                while True:
                    # 異なる変数の取得、または関数のスキップの後はメッセージを受信する
                    if (event := self.event_receiver()) is None:
                        continue

                    if (item := event.get("item", None)) is None:
                        errorCnt += 1
                        self.event_sender(
                            Debugger2GameEvent(
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
                            Debugger2GameEvent(
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
                            Debugger2GameEvent(
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
                        break

                    # non_varの時と同じくこのメソッドで次の関数を解析する
                    self.analyze_next_function(dynamic_variable_info)

                    # 関数後はまた解析する
                    self.vars_tracker.analyze_var_nodes(str(var[1]), self.frame)

                    self.step_conditionally()

                # 取得した変数を宣言済リストに登録する
                self.vars_tracker.set_variable_declared(var)

                # 全ての宣言が完了した/完了していないに関わらずこの4つは共通しているので先に取得しておく
                send_event = Debugger2GameEvent(
                    message = f"You got item {var[0]} !!" if self.is_english else f"アイテム {var[0]} を正確に取得できました!!",
                    status = "ok",
                    item = DeclaredVariableInfo(
                        value = self.vars_tracker.get_declared_var_value_w_comment(var, dynamic_variable_info["dynamic_var_node"]),
                        line = var[1]
                    ),
                    skipped_function_list = dynamic_variable_info["skipped_function_list"]
                )

                # まだ全ての宣言が完了していない場合
                if len(declared_vars):
                    self.event_sender(send_event, False)
                    continue

                # 全ての宣言が完了している場合
                # vars_changedとvarsTrackerの共通項とdeclared_varsの差項を、値が変化した変数として検知する
                # vars_changedにもkeysを使って宣言済みかつ値が変わった変数を取得できる
                send_event["vars_w_value_changed"] = self.get_vars_w_value_changed(
                    [
                        varname
                        for varname in self.vars_tracker.vars_changed.keys()
                        if varname in self.vars_tracker.vars_declared[-1] and varname not in declared_vars
                    ]
                )
                send_event["vars_w_value_unchanged"] = self.get_vars_w_value_unchanged()

                # 変数宣言が全て完了した時の処理
                if not is_skipped_var_check:
                    self.set_next_line(send_event, self.line_number)

                self.event_sender(send_event)

        # 変数宣言以外の計算式の解析
        def analyze_non_var_expr_comments(self, is_end: bool = False):
            if (previous_expr_status_handler := self.get_expr_status_handler(False)):
                if isinstance(previous_expr_status_handler, ForStatusHandler) and not previous_expr_status_handler.condition["is_check_completed"]:
                    return "not_next_line"
                
            if str(self.next_line_number) not in self.exprs_by_line:
                if is_end:
                    sys.exit("main return statement is not found")

                self.thread.StepInto()
                return None

            expr_status_handler = self.register_next_expr_status_handler()

            # 繰り返し文は戻ってくる毎に再利用されるので、前回の解析結果がまだ残っている場合は初期化する
            if isinstance(expr_status_handler, (WhileStatusHandler, DoWhileStatusHandler)) and expr_status_handler.result is not None:
                expr_status_handler.dynamic_condition.initialize_analysis(expr_status_handler.condition)
                expr_status_handler.result = None
            elif isinstance(expr_status_handler, ForStatusHandler) and expr_status_handler.condition["result"] is not None:
                if (dynamic_comment_handler := expr_status_handler.condition["dynamic_expr"]):
                    dynamic_comment_handler.initialize_analysis(expr_status_handler.condition["expr"])
                expr_status_handler.condition["is_check_completed"] = False
                expr_status_handler.condition["result"] = None

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
            
            # ここでswitch文の下処理(defaultの場合)を行う
            if isinstance(expr_status_handler, SwitchStatusHandler):
                self.switch_expr_status_handler = expr_status_handler

            return None

        def check_expr_status(self, execution_info: ExecutionInfo) -> Literal["correct", "incorrect", "after_loop_skip"]:
            if (current_expr_status_handler := self.get_expr_status_handler(False)) is None:
                return "incorrect"
            
            if current_expr_status_handler.line != execution_info["line"]:
                return "incorrect"
            
            send_event = Debugger2GameEvent(
                message = "",
                status = "ok",
            )

            get_line = True

            # if文は、条件ごとに実行行が異なるので、これから変えないといけない?
            # (self.line_number, self.next_line_numberを気にしない解析を始めるのはどうか?)
            # 自動解析の時はどうするか? → これも同じく特別な処理に持っていく 
            # 自作関数が現れたら、self.frame_num < self.next_frame_numになるまでstep_conditionallyを繰り返し実行する
            # これらは、他の実行文に対しても同じ (これによって、複数行にまたがる一処理も解析できるのでは?)
            # 要するに、引っ掛かりの行番(最初に実行される行番)でこれらの処理ハンドラを取得し、その解析に突入させると良いかも?
            if isinstance(current_expr_status_handler, IfStatusHandler) and execution_info["type"] == "if":
                true_condition_index = execution_info["true_condition_index"]
                check_result = current_expr_status_handler.check_conditions(send_event, true_condition_index)
                if check_result == "correct":
                    self.pop_expr_status_handler(False)
                    self.set_next_line(send_event, (self.line_number, int(true_condition_index != -1)))
            elif (isinstance(current_expr_status_handler, WhileStatusHandler) and execution_info["type"] == "while") or (isinstance(current_expr_status_handler, DoWhileStatusHandler) and execution_info["type"] == "do_while"):
                condition = execution_info["condition"]
                if condition is None:
                    return "incorrect"
                
                check_result = current_expr_status_handler.check_condition(send_event, condition)
                if check_result == "correct":
                    if condition:
                        return "after_loop_skip" if self.check_loop_statement_skip(send_event, current_expr_status_handler) else "correct"
                    else: # falseなら、一番下の行をstart_lineに設定して、next_line_numberをend_lineに設定する
                        self.pop_expr_status_handler(False)
                        self.set_next_line(send_event, (self.line_number, int(False)))
                        self.remove_line_loop(self.line_number)
            elif isinstance(current_expr_status_handler, DoWhileInitializerStatusHandler) and execution_info["type"] == "do_while":
                # あり得ないが
                if execution_info["condition"] is not None:
                    return "incorrect"
    
                check_result = current_expr_status_handler.check_arrival(send_event)
                self.pop_expr_status_handler(False)
                
                self.set_next_line(send_event, self.line_number)
            elif isinstance(current_expr_status_handler, ForStatusHandler):
                check_result = current_expr_status_handler.check_status(send_event, execution_info)

                # for falseの条件文チェックが完了した場合のみ、スキップされ得る次の変数リストを取得する
                if check_result == "correct":
                    if execution_info["type"] == "for":
                        if execution_info["condition"]:
                            return "after_loop_skip" if self.check_loop_statement_skip(send_event, current_expr_status_handler) else "correct"
                        else:
                            self.pop_expr_status_handler(False)
                            self.set_next_line(send_event, (self.line_number, int(False)))
                            self.remove_line_loop(self.line_number)
                    elif execution_info["type"] == "for_initializer":
                        get_line = False
                    else: # "for_change"
                        send_event["line"] = self.line_number
                        get_line = False
            elif isinstance(current_expr_status_handler, SwitchStatusHandler) and execution_info["type"] == "switch":
                check_result = current_expr_status_handler.check_status(send_event, execution_info)
                if check_result == "correct":
                    self.pop_expr_status_handler(False)
                    self.set_next_line(send_event, (self.line_number, execution_info["true_case_index"]))
            elif isinstance(current_expr_status_handler, ControlFlowStatusHandler):
                if current_expr_status_handler.type == execution_info["type"]:
                    check_result = current_expr_status_handler.check_status(send_event)
                    self.pop_expr_status_handler(False)
                    if execution_info["type"] == "break":
                        self.remove_line_loop(current_expr_status_handler.condition_line)
                    self.set_next_line(send_event, self.line_number)
                else:
                    check_result = "incorrect"
            elif isinstance(current_expr_status_handler, ExpressionStatusHandler) and execution_info["type"] == "expression":
                check_result = current_expr_status_handler.check_expr(send_event)
                if check_result == "correct":
                    self.pop_expr_status_handler(False)
                    self.set_next_line(send_event, self.line_number)
            elif isinstance(current_expr_status_handler, ReturnStatusHandler) and execution_info["type"] == "return":
                check_result = current_expr_status_handler.check_status(send_event)

                if check_result == "correct":
                    if (dynamic_comment_handler := self.dynamic_comment_handler_being_checked[-1] if len(self.dynamic_comment_handler_being_checked) else None) is not None:
                        send_event["return_value"] = current_expr_status_handler.result
                        send_event["items"] = self.vars_tracker.get_value()
                        dynamic_comment_handler.set_function_comment(current_expr_status_handler.result)

                    self.remove_line_loop_of_frame_by_return()
                    self.pop_top_expr_status_handler_dict()

                if self.is_end:
                    send_event["message"] = "Congraturations!! Here is a goal!!" if self.is_english else "おめでとうございます!! ここがゴールです!!"
                    send_event["is_finished"] = True
            else:
                return "incorrect"

            if not self.is_end:
                if check_result == "incorrect":
                    return "incorrect"
                elif check_result == "next_function":
                    self.analyze_next_function(current_expr_status_handler)
                    return "correct"

            send_event["skipped_function_list"] = current_expr_status_handler.get_skipped_functions()
            if not self.is_end:
                send_event["vars_w_value_changed"] = self.get_vars_w_value_changed(list(self.vars_tracker.vars_changed.keys()))
                send_event["vars_w_value_unchanged"] = self.get_vars_w_value_unchanged()

            self.event_sender(
                send_event, 
                get_line = get_line
            )

            if self.is_end:
                raise ProgramFinished()

            return "correct"
        
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
                Debugger2GameEvent(
                    message = (
                        f"Will you skip function \"{self.func_crnt_name}\" ?" 
                        if self.is_english else 
                        f"遷移先の関数 {self.func_crnt_name} の処理をスキップしますか?"
                    ),
                    status = "ok", 
                    func_skip_index = index,
                    skipped_function_list = skipped_function_list
                )
            )

            event = self.event_receiver()

            if self.next_frame_num > self.frame_num:
                if (is_skip := event.get("skip")) is None:
                    sys.exit("\"skip\" attribute is not found in a sent message")

                if is_skip:
                    back_line_number = self.line_number
                    back_frame_num = self.frame_num
                    self.dynamic_comment_handler_being_checked.append(current_comment_handler)

                    return_value = None
                    while True:
                        self.step_conditionally()

                        if back_line_number == self.line_number and back_frame_num == self.frame_num:
                            self.remove_line_loop_of_frame_by_return()
                            break

                        if self.line_data.get(self.func_name, None) and self.line_number in self.line_data[self.func_name]["lines"]:
                            if (current_expr_status_handler := self.get_expr_status_handler(False)) is None:
                                sys.exit("expr status handler is not found")

                            if (result := current_expr_status_handler.check_expr_automatically()) == "end":
                                if isinstance(current_expr_status_handler, ReturnStatusHandler):
                                    self.pop_top_expr_status_handler_dict()
                                    return_value = current_expr_status_handler.result
                                    self.remove_line_loop_of_frame_by_return()
                                    break

                                if isinstance(current_expr_status_handler,(WhileStatusHandler, DoWhileStatusHandler, ForStatusHandler)):
                                    self.remove_line_loop(current_expr_status_handler.line)

                                self.pop_expr_status_handler(False)
                            elif result == "next_function":
                                current_comment_w_index = current_expr_status_handler.get_next_function()
                                current_comment_w_index[0].set_function_comment(self.analyze_next_function_in_skip())
                        
                    current_comment_handler.set_function_comment(return_value)
                    self.event_sender(
                        Debugger2GameEvent(
                            message = "function skip is completed" if self.is_english else "スキップが完了しました", 
                            status = "ok", 
                            items = self.vars_tracker.get_value(), 
                            func = self.func_crnt_name,
                            return_value = return_value
                        )
                    )
                else:
                    if (func_warp := event.get("func_warp")) is None:
                        sys.exit("func_warp is not found")

                    arg_comment_list = current_comment_handler.get_arg_comment_of_current_function()

                    if len(arg_comment_list) != len(func_warp["args"]):
                        sys.exit("number of argument comments does not match number of arguments in func warp")

                    send_event = Debugger2GameEvent(
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
                                    name = var_info["var_node"]["name"],
                                    line = var_info["start"],
                                    value = self.vars_tracker.get_arg_value(var_info, arg_comment_list[i])
                                )
                                for i, var_info in enumerate(func_warp["args"])
                            ]
                        )
                    )

                    self.set_next_line(send_event, func_warp["line"], is_func_entry = True)

                    self.event_sender(
                        send_event
                    )

                    self.dynamic_comment_handler_being_checked.append(current_comment_handler)
                    back_line_number = self.line_number
                    back_frame_num = self.frame_num

                    index_scanned_currently_before = current_comment_handler.index_scanned_currently

                    while True:
                        if self.analyze_frame(back_line_number):
                            continue

                        if index_scanned_currently_before < current_comment_handler.index_scanned_currently:
                            break

                        if back_line_number == self.line_number and back_frame_num == self.frame_num:
                            break

                self.dynamic_comment_handler_being_checked.pop(-1)
            # ここはインライン関数が来る可能性がある? (今はまだ対応しない)
            else:
                sys.exit("error in function move")

        def analyze_next_function_in_skip(self) -> str | None:
            crnt_frame_num = self.frame_num

            while crnt_frame_num == self.frame_num:
                self.step_conditionally()
                
                if self.line_data.get(self.func_name, None) and self.line_number in self.line_data[self.func_name]["lines"]:
                    if (current_expr_status_handler := self.get_expr_status_handler(False)) is None:
                        sys.exit("expr status handler is not found")

                    if (result := current_expr_status_handler.check_expr_automatically()) == "end":
                        if isinstance(current_expr_status_handler, ReturnStatusHandler):
                            self.pop_top_expr_status_handler_dict()
                            self.remove_line_loop_of_frame_by_return()
                            return current_expr_status_handler.result
                        elif isinstance(current_expr_status_handler, (WhileStatusHandler, DoWhileStatusHandler, ForStatusHandler)):
                            self.remove_line_loop(current_expr_status_handler.line)
                        elif isinstance(current_expr_status_handler, ControlFlowStatusHandler) and current_expr_status_handler.type == "break":
                            self.remove_line_loop(current_expr_status_handler.condition_line)

                        self.pop_expr_status_handler(False)
                    elif result == "next_function":
                        current_comment_handler, index = current_expr_status_handler.get_next_function()
                        current_comment_handler.set_function_comment(self.analyze_next_function_in_skip())
                    
            return None

        def analyze_frame(self, line_number_to_back: int | None = None) -> int: # Literal[PROGRESS, CONTINUE]
            if self.line_data.get(self.func_name, None) and self.line_number in self.line_data[self.func_name]["lines"]:
                if (event := self.event_receiver()) is None:
                    return CONTINUE

                if (execution_info := event.get("execution_info")) is not None:
                    # ここで何が返されるかによって次のアクションに向かうか、今のアクションを解析するか、間違ったアクションをしたのかを解析する
                    if (result := self.check_expr_status(execution_info)) == "incorrect":
                        self.event_sender(
                            Debugger2GameEvent(
                                message = (
                                    "You did a different action !!" 
                                    if self.is_english else 
                                    "異なる処理に対するアクションをしました!!"
                                ), 
                                status = "ng"
                            )
                        )
                        return CONTINUE
                    elif result == "after_loop_skip":
                        return CONTINUE
                else:
                    self.event_sender(
                        Debugger2GameEvent(
                            message = "You did a different action !!" if self.is_english else "異なる処理に対するアクションをしました!!", 
                            status = "ng"
                        )
                    )
                    return CONTINUE

            self.step_conditionally()

            if line_number_to_back != self.line_number:
                self.vars_checker(self.line_number)

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

        def event_receiver(self):
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
            
            event: Game2DebuggerEvent = json.loads(data.decode())

            if "rollback_request" in event:
                self.event_sender(
                    Debugger2GameEvent(
                        message = "", 
                        status = "rollback_accept"
                    )
                )
                data = conn.recv(1024)
                # ここは後々変えるかも
                if not data:
                    raise NoConnection()
                
                event = json.loads(data.decode())
                if event["rollback"]:
                    self.reset_state()
                    del self.events_history[event["index"]:]
                    raise RollBack()

                self.event_sender(
                    Debugger2GameEvent(
                        message = "", 
                        status = "rollback_fail"
                    )
                )
                return None

            self.events_history.append(event)
            
            return event
    
        def event_sender(self, send_event: Debugger2GameEvent, get_line: bool = True) -> None:
            if self.rollback_index is not None:
                '''
                処理を再実行していき、events_historyの大きさとrollback_indexが等しくなったらプレイヤーが指定した処理を全て再実行
                できたことになるのでrollbackアクションが終了したことを示すメッセージを送信する
                同時に現時点での全ての変数の内容もゲーム側に反映させるために送信する
                '''
                if len(self.events_history) != self.rollback_index:
                    return
                
                send_event = Debugger2GameEvent(
                    message = "",
                    status = "rollback_success", 
                    gvars = self.vars_tracker.get_global_value(), 
                    vars = self.vars_tracker.get_value_by_frame()
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

                if get_line and "line" not in send_event:
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

                if "func_skip" in send_event and "skipped_function_list" not in send_event:
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

        def append_line_loop(self, type: Literal["while", "do_while", "for"], line: int):
            if (opposite_edge := self.line_data[self.func_name]["loops"].get(str(line), None)) is None:
                sys.exit("opposite edge of a loop statement is not found")

            if len(self.line_loop_dict_by_frame) <= self.frame_num - 2:
                self.line_loop_dict_by_frame.append({})

            crnt_line_loop_dict = self.line_loop_dict_by_frame[self.frame_num - 2]

            if line in crnt_line_loop_dict:
                return
            
            if type in ("while", "for"):
                crnt_line_loop_dict[line] = LoopLineInfo(
                    type = type,
                    top_edge = line,
                    bottom_edge = opposite_edge
                )
            else:
                top_edge = min(line, opposite_edge)
                bottom_edge = max(line, opposite_edge)

                crnt_line_loop_dict[bottom_edge] = LoopLineInfo(
                    type = type,
                    top_edge = top_edge,
                    bottom_edge = bottom_edge
                )

        def remove_line_loop(self, line: int):
            if len(self.line_loop_dict_by_frame) <= self.frame_num - 2:
                sys.exit(f"line loop info is not found in frame layer no.{self.frame_num-2}")

            if line not in self.line_loop_dict_by_frame[self.frame_num - 2]:
                sys.exit(f"line loop info of line {line} is not found in frame layer no.{self.frame_num-2}")

            return self.line_loop_dict_by_frame[self.frame_num - 2].pop(line)

        def remove_line_loop_of_frame_by_return(self):
            if len(self.line_loop_dict_by_frame) <= self.frame_num - 3:
                sys.exit(f"line loop info is not found in function in frame layer no.{self.frame_num-2}")

            del self.line_loop_dict_by_frame[self.frame_num-2:]

        def check_loop_statement_skip(self, send_event: Debugger2GameEvent, current_expr_status_handler: DynamicNonVarStatusHandler):
            if (loop_line_info := self.line_loop_dict_by_frame[self.frame_num-2].get(current_expr_status_handler.line)
                if len(self.line_loop_dict_by_frame) > self.frame_num - 2 else None) is None:
                sys.exit(f"loop line info is not found in line of {current_expr_status_handler.line}")

            send_event["message"] = (
                f"Will you skip {loop_line_info["type"]} loop of line {loop_line_info["top_edge"]} to {loop_line_info["bottom_edge"]} ?" 
                if self.is_english else 
                f"{loop_line_info["top_edge"]}から{loop_line_info["bottom_edge"]}行の{loop_line_info["type"]}文の処理をスキップしますか?"
            )
            send_event["skipped_function_list"] = current_expr_status_handler.get_skipped_functions()
            send_event["loop_skip"] = True

            self.event_sender(send_event)

            line_number_to_back = current_expr_status_handler.line

            if (event := self.event_receiver()) is None:
                raise ProgramFinished()

            if (is_skip := event.get("skip")) is None:
                sys.exit("\"skip\" attribute is not found in a sent message")

            if is_skip:
                send_event = Debugger2GameEvent(
                    message = "loop skip is completed" if self.is_english else "スキップが完了しました",
                    status = "ok"
                )

                while True:
                    self.step_conditionally()

                    if self.line_data.get(self.func_name, None) and self.line_number in self.line_data[self.func_name]["lines"]:
                        if (result := current_expr_status_handler.check_expr_automatically()) == "end":
                            if isinstance(current_expr_status_handler, ControlFlowStatusHandler) and current_expr_status_handler.type == "break":
                                # マップにて、該当するbreakのワープゾーンまで遷移させるために、current_expr_status_handler.lineをsend_eventに登録する
                                send_event["break_line_after_loop_skip"] = current_expr_status_handler.line
                                send_event["line"] = current_expr_status_handler.line
                                break
                            elif isinstance(current_expr_status_handler, (WhileStatusHandler, DoWhileStatusHandler, ForStatusHandler)):
                                # スキップ開始行に戻っているならスキップは終了目前であるため、スキップ終了の手続きを開始する
                                if current_expr_status_handler.line == line_number_to_back:
                                    send_event["line"] = line_number_to_back
                                    break
                            elif isinstance(current_expr_status_handler, ReturnStatusHandler):
                                # マップにて、該当するreturnのキャラまで遷移させるために、current_expr_status_handler.lineをsend_eventに登録する
                                send_event["return_line_after_loop_skip"] = current_expr_status_handler.line
                                send_event["line"] = current_expr_status_handler.line
                                break

                            self.pop_expr_status_handler(False)
                        elif result == "next_function":
                            current_comment_w_index = current_expr_status_handler.get_next_function()
                            current_comment_w_index[0].set_function_comment(self.analyze_next_function_in_skip())

                send_event["items"] = self.vars_tracker.get_value()

                self.event_sender(
                    send_event,
                    get_line = False
                )

                return True
            else:
                send_event = Debugger2GameEvent(
                    message = f"skip is canceled" if self.is_english else f"スキップをキャンセルしました。",
                    status = "ok",
                    vars_w_value_changed = self.get_vars_w_value_changed(list(self.vars_tracker.vars_changed.keys())),
                    vars_w_value_unchanged = self.get_vars_w_value_unchanged()
                )

                self.set_next_line(send_event, (self.line_number, int(True)))
                
                self.event_sender(
                    send_event
                )
                
                return False

        def get_expr_status_handler(self, is_next: bool):
            frame_num = self.next_frame_num if is_next else self.frame_num
            line_number = self.next_line_number if is_next else self.line_number
            
            if len(self.expr_status_handler_dict_by_frame) > frame_num -2:
                return self.expr_status_handler_dict_by_frame[frame_num-2].get(line_number)

            return None

        def pop_expr_status_handler(self, is_next: bool):
            frame_num = self.next_frame_num if is_next else self.frame_num
            line_number = self.next_line_number if is_next else self.line_number

            if len(self.expr_status_handler_dict_by_frame) <= frame_num - 2:
                sys.exit(f"expr status handler dict is not found in frame no.{frame_num -2}")

            if line_number not in self.expr_status_handler_dict_by_frame[frame_num-2]:
                sys.exit(f"expr status handler is not found in line {line_number} of frame no.{frame_num - 2}")

            return self.expr_status_handler_dict_by_frame[frame_num-2].pop(line_number)

        def pop_top_expr_status_handler_dict(self):
            if len(self.expr_status_handler_dict_by_frame) == 0:
                sys.exit("no expr status handler is found in self.expr_status_handler_dict_by_frame")

            self.expr_status_handler_dict_by_frame.pop(-1)

        def register_next_expr_status_handler(self):
            frame_index = self.next_frame_num - 2
            line = self.next_line_number

            if (missing_count := frame_index - len(self.expr_status_handler_dict_by_frame) + 1) >= 1:
                self.expr_status_handler_dict_by_frame.extend({} for _ in range(missing_count))

            if line not in self.expr_status_handler_dict_by_frame[frame_index]:
                self.expr_status_handler_dict_by_frame[frame_index][line] = self.set_expr_status(
                    self.exprs_by_line[str(line)], line
                )

            return self.expr_status_handler_dict_by_frame[frame_index][line]

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
        except ProgramFinished:
            print("プログラムが終了しました")
            break
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