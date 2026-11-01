from typing import TypedDict, Literal

type ExecutionInfo = (
    IfExecutionInfo 
    | WhileExecutionInfo
    | DoWhileExecutionInfo
    | ForExecutionInfo
    | ForInitializerInfo
    | ForChangeInfo
    | SwitchCaseExecutionInfo
    | ControlFlowInfo
    | ExpressionExecutionInfo
    | ReturnExecutionInfo
)

class IfExecutionInfo(TypedDict):
    type: Literal["if"]
    line: int
    condition_line: int
    true_condition_index: int

def create_if_execution_info(line: int, condition_line: int, true_condition_index: int):
    return IfExecutionInfo(
        type = "if", 
        line = line, 
        condition_line = condition_line, 
        true_condition_index = true_condition_index
    )

class WhileExecutionInfo(TypedDict):
    type: Literal["while"]
    line: int
    condition: bool

def create_while_execution_info(line: int, condition: bool):
    return WhileExecutionInfo(
        type = "while", 
        line = line, 
        condition = condition
    )

class DoWhileExecutionInfo(TypedDict):
    type: Literal["do_while"]
    line: int
    condition: bool

def create_do_while_execution_info(line: int, condition: bool):
    return DoWhileExecutionInfo(
        type = "do_while", 
        line = line, 
        condition = condition
    )

class ForInitializerInfo(TypedDict):
    type: Literal["for_initializer"]
    line: int

def create_for_initializer_execution_info(line: int):
    return ForInitializerInfo(
        type = "for_initializer",
        line = line
    )

class ForChangeInfo(TypedDict):
    type: Literal["for_change"]
    line: int

def create_for_change_execution_info(line: int):
    return ForChangeInfo(
        type = "for_change",
        line = line
    )

class ForExecutionInfo(TypedDict):
    type: Literal["for"]
    line: int
    condition: bool

def create_for_execution_info(line: int, condition: bool):
    return ForExecutionInfo(
        type = "for", 
        line = line, 
        condition = condition
    )

class SwitchCaseExecutionInfo(TypedDict):
    type: Literal["switch"]
    line: int
    true_case_index: int

def create_switch_case_executioin_info(line: int, true_case_index: int):
    return SwitchCaseExecutionInfo(
        type = "switch", 
        line = line, 
        true_case_index = true_case_index
    )

class ControlFlowInfo(TypedDict):
    type: Literal["continue", "break"]
    line: int

def create_control_flow_info(type: Literal["continue", "break"], line: int):
    return ControlFlowInfo(
        type = type, 
        line = line
    )

class ExpressionExecutionInfo(TypedDict):
    type: Literal["expression"]
    line: int

def create_expression_execution_info(line: int):
    return ExpressionExecutionInfo(
        type = "expression", 
        line = line
    )

class ReturnExecutionInfo(TypedDict):
    type: Literal["return"]
    line: int | None

def create_return_execution_info(line: int | None):
    return ReturnExecutionInfo(
        type = "return", 
        line = line
    )