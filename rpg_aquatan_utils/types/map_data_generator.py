from rpg_aquatan_utils.types.expr_descriptions import *

class GotoRoomInfo(TypedDict):
    to_nodeID: str
    fromNodeID: str
    
class FuncInfo:
    def __init__(self, nodeID: str):
        self.start_nodeID: str = f'"{nodeID}"'
        self.args: list[VarInfo]
        self.funcs: set[str] = set()
        self.start: int = 0

    def set_func_reference(self, func: str):
        self.funcs.add(func)

    def set_start(self, line: int, not_to_set: bool = False):
        if self.start or not_to_set:
            return
        self.start = line

class LineInfo:
    def __init__(self):
        self.lines: set[int] = set()
        self.loops: dict[int, int] = {}
        self.returns: set[int] = set()
        self.stdins: set[int] = set()
        self.start = 0

    def set_execution_line(self, line: int):
        self.lines.add(line)

    def set_loop_start_and_goal(self, condition_line: int, edge_line: int):
        self.loops[condition_line] = edge_line

    def set_return(self, line: int):
        self.returns.add(line)

    def set_stdin(self, line: int):
        self.stdins.add(line)

    def set_start(self, line: int, not_to_set: bool = False):
        if self.start or not_to_set:
            return
        self.start = line