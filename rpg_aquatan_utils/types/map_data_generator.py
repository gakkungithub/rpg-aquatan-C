from rpg_aquatan_utils.types.expr_descriptions import *

class GotoRoomInfo(TypedDict):
    to_nodeID: str
    from_nodeID: str
    
class FuncInfo:
    def __init__(self, nodeID: str):
        self.start_nodeID: str = f'"{nodeID}"'
        self.args: list[VarInfo]
        self.funcs: set[str] = set()
        self.start: int = 0

    def set_func_reference(self, func: str):
        self.funcs.add(func)

    def set_start(self, line: int):
        if self.start:
            return
        self.start = line

class LineInfo:
    def __init__(self):
        self.lines: set[int] = set()
        self.loops: dict[int, int] = {}
        self.returns: set[int] = set()
        # キーの行番(int型、現在の処理の行番)から次はどの行番(次の処理)に行くか、その関係をリストアップする辞書
        # 値について、intならその行番に行く、boolキーの辞書ならその条件(if, while, do-while, for の True/Falseと、switchのcase群index)
        self.next_lines: dict[int, int | dict[int, int]] = {}
        self.stdins: set[int] = set()
        self.start = 0

    def set_execution_line(self, line: int):
        self.lines.add(line)

    def set_loop_start_and_goal(self, condition_line: int, edge_line: int):
        self.loops[condition_line] = edge_line

    def set_return(self, line: int):
        self.returns.add(line)

    def set_next_line(self, previous_line: int | tuple[int, int], next_line: int):
        if isinstance(previous_line, int):
            if previous_line == next_line:
                return True
            
            if previous_line in self.next_lines:
                return False

            self.next_lines[previous_line] = next_line
        else:
            line, condition = previous_line

            if (next_line_info := self.next_lines.get(line)) is None:
                self.next_lines[line] = {condition: next_line}
                return True

            if isinstance(next_line_info, int):
                return False

            if condition in next_line_info:
                return False

            next_line_info[condition] = next_line

        return True

    def set_stdin(self, line: int):
        self.stdins.add(line)

    def set_start(self, line: int, not_to_set: bool = False):
        if self.start or not_to_set:
            return
        self.start = line