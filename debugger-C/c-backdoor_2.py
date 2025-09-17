import faulthandler
faulthandler.enable()
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

# break pointを打ってスキップすることも考えられる
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = BASE_DIR + '/mapdata'
CONTINUE = 1
PROGRESS = 0

class VarPreviousValue:
    def __init__(self, value=None, address=None):
        self.value = value
        self.address = address
        self.children: dict[str, VarPreviousValue] = {}  # 配列の添字や構造体のメンバ

    def update_value(self, value, address):
        """LLDBのSBValueから最新値を更新"""
        self.value = value
        self.address = address
        # 必要なら children も更新

    def __repr__(self):
        return f"<{self.name}={self.value}>"

class VarsTracker:
    def __init__(self, gvars):
        self.previous_values: list[dict[str, VarPreviousValue]] = []
        self.global_previous_values: dict[str, VarPreviousValue] = {}
        self.vars_changed: dict[str, list[tuple[str, ...]]] = {}
        self.vars_declared: list[list[str]] = []
        self.vars_removed: list[str] = []
        self.frames = ['start']
        self.track(gvars, self.global_previous_values, [])
    
    def trackStart(self, frame):
        current_frames = [thread.GetFrameAtIndex(i).GetFunctionName()
                      for i in range(thread.GetNumFrames())]
        # 何かしらの関数に遷移したとき
        if len(current_frames) > len(self.frames):
            self.previous_values.append({})
            self.vars_declared.append([])
            self.frames = current_frames
        # 何かしらの関数から戻ってきたとき
        elif len(current_frames) < len(self.frames):
            self.previous_values.pop()
            self.vars_declared.pop()
            self.frames = current_frames
        
        gvars = []
        for module in target.module_iter():
            for sym in module:
                if sym.GetType() == lldb.eSymbolTypeData:  # データシンボル（変数）
                    name = sym.GetName()
                    if name:
                        var = target.FindFirstGlobalVariable(name)
                        if var.IsValid():
                            gvars.append(var)

        self.vars_changed = {}
        self.track(gvars, self.global_previous_values, [], isLocal=False)
        self.track(frame.GetVariables(True, True, True, True), self.previous_values[-1], [])

    def track(self, vars, var_previous_values: dict[str, VarPreviousValue], vars_path: list[str], depth=0, prefix="", isLocal=True) -> list[str]:
        crnt_vars: list[str] = []
        
        indent = "    " * depth

        for var in vars:
            name = var.GetName()
            full_name = f"{prefix}.{name}" if prefix else name
            value = var.GetValue()
            address = var.GetLoadAddress()

            var_previous_value = var_previous_values[name].value if name in var_previous_values else None

            if value != var_previous_value:
                print(f"{indent}{full_name} = {value}    ← changed")
                if len(vars_path) == 0:
                    self.vars_changed[name] = [()]
                else:
                    if vars_path[0] in self.vars_changed:
                        self.vars_changed[vars_path[0]].append((*vars_path[1:], name))
                    else:
                        self.vars_changed[vars_path[0]] = [(*vars_path[1:], name)]
            else:
                # print(f"{indent}{full_name} = {value}")
                pass

            if depth == 0 and isLocal:
                crnt_vars.append(name)

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
                                var_previous_value = var_previous_values[name].children['[0]'].value if '[0]' in var_previous_values[name].children else None
                                if cstr != var_previous_value:
                                    if len(vars_path) == 0:
                                        self.vars_changed[name] = [('[0]', )]
                                    else:
                                        if vars_path[0] in self.vars_changed:
                                            self.vars_changed[vars_path[0]].append((*vars_path[1:], name, '[0]'))
                                        else:
                                            self.vars_changed[vars_path[0]] = [(*vars_path[1:], name, '[0]')]
                                var_previous_values[name].children['[0]'] = VarPreviousValue(cstr, addr)
                            else:
                                print(f"{indent}→ {full_name} points to unreadable char*")
                        elif type_name == "int":
                            data = process.ReadMemory(addr, 4, error)
                            if error.Success():
                                val = struct.unpack("i", data)[0]
                                print(f"{indent}→ {full_name} points to int: {val}")
                                var_previous_value = var_previous_values[name].children['[0]'].value if '[0]' in var_previous_values[name].children else None
                                if val != var_previous_value:
                                    if len(vars_path) == 0:
                                        self.vars_changed[name] = [('[0]', )]
                                    else:
                                        if vars_path[0] in self.vars_changed:
                                            self.vars_changed[vars_path[0]].append((*vars_path[1:], name, '[0]'))
                                        else:
                                            self.vars_changed[vars_path[0]] = [(*vars_path[1:], name, '[0]')]
                                var_previous_values[name].children['[0]'] = VarPreviousValue(val, addr)
                            else:
                                print(f"{indent}→ {full_name} points to unreadable int*")
                        elif type_name == "float":
                            data = process.ReadMemory(addr, 4, error)
                            if error.Success():
                                val = struct.unpack("f", data)[0]
                                print(f"{indent}→ {full_name} points to float: {val}")
                                var_previous_value = var_previous_values[name].children['[0]'].value if '[0]' in var_previous_values[name].children else None
                                if val != var_previous_value:
                                    if len(vars_path) == 0:
                                        self.vars_changed[name] = [('[0]', )]
                                    else:
                                        if vars_path[0] in self.vars_changed:
                                            self.vars_changed[vars_path[0]].append((*vars_path[1:], name, '[0]'))
                                        else:
                                            self.vars_changed[vars_path[0]] = [(*vars_path[1:], name, '[0]')]
                                var_previous_values[name].children['[0]'] = VarPreviousValue(val, addr)
                            else:
                                print(f"{indent}→ {full_name} points to unreadable float*")
                        elif type_name == "double":
                            data = process.ReadMemory(addr, 8, error)
                            if error.Success():
                                val = struct.unpack("d", data)[0]
                                print(f"{indent}→ {full_name} points to double: {val}")
                                var_previous_value = var_previous_values[name].children['[0]'].value if '[0]' in var_previous_values[name].children else None
                                if val != var_previous_value:
                                    if len(vars_path) == 0:
                                        self.vars_changed[name] = [('[0]', )]
                                    else:
                                        if vars_path[0] in self.vars_changed:
                                            self.vars_changed[vars_path[0]].append((*vars_path[1:], name, '[0]'))
                                        else:
                                            self.vars_changed[vars_path[0]] = [(*vars_path[1:], name, '[0]')]
                                var_previous_values[name].children['[0]'] = VarPreviousValue(val, addr)
                            else:
                                print(f"{indent}→ {full_name} points to unreadable double*")

                        else:
                            # 構造体などの場合
                            deref = var.Dereference()
                            if deref.IsValid() and deref.GetNumChildren() > 0:
                                print(f"{indent}→ Deref {full_name}")
                                children = [deref.GetChildAtIndex(i) for i in range(deref.GetNumChildren())]
                                self.track(children, var_previous_values[name].children, vars_path + [name], depth + 1, full_name, isLocal)
                    else:
                        children = [var.GetChildAtIndex(i) for i in range(num_children)]
                        self.track(children, var_previous_values[name].children, vars_path + [name], depth + 1, full_name, isLocal)

                except Exception as e:
                    print(f"{indent}→ {full_name} deref error: {e}")

            elif num_children > 0:
                children = [var.GetChildAtIndex(i) for i in range(num_children)]
                self.track(children, var_previous_values[name].children, vars_path + [name], depth + 1, full_name, isLocal)
    
        if depth == 0 and isLocal:
            if len(self.vars_declared) != 0:
                self.vars_removed = list(set(self.vars_declared[-1]) - set(crnt_vars))
                if len(self.vars_removed) != 0:
                    self.vars_declared[-1] = list(set(self.vars_declared[-1]) - set(self.vars_removed))

    def print_variables(self, previous_values: dict[str, VarPreviousValue], depth=1):
        indent = "    " * depth
        for name, previous_value in previous_values.items():
            print(f"{indent}name: {name}: [value: {previous_value.value}, address: {previous_value.address}]")
            self.print_variables(previous_value.children, depth+1)

    def print_all_variables(self):
        all_frames = self.frames[:-1]
        for i, frame in enumerate(all_frames):
            print(f"func_name: {frame}")
            self.print_variables(self.previous_values[-(i+1)])

    def getValueAll(self):
        filtered_previous_values = {var: self.previous_values[-1][var] for var in self.vars_declared[-1] if var in self.previous_values[-1]}
        return self.getValuesDict(filtered_previous_values)
    
    def getGlobalValueAll(self):
        return self.getValuesDict(self.global_previous_values) 

    def getValuesDict(self, previous_values: dict[str, VarPreviousValue]):
        values_dict = {}
        for varname, previous_value in previous_values.items():
            values_dict[varname] = {"value": previous_value.value, "children": self.getValuesDict(previous_value.children)}
        return values_dict
    
    def getValuePartly(self, value_path: list[str]):
        if len(value_path) == 0:
            return (False, None)
        temp_previous_values_dict = self.previous_values[-1]
        while 1:
            if (varname := value_path.pop(0)) not in temp_previous_values_dict:
                return (False, None)
            if len(value_path) == 0:
                return (True, temp_previous_values_dict[varname].value)
            temp_previous_values_dict = temp_previous_values_dict[varname].children

    # "item": {"value": aaa, "children": {}}
    def getValueByVar(self, varname: str, back=0):
        return self.getValueByVarDict(self.previous_values[int(-1+back)][varname])
        
    # {"value": bbb, "children": {0: {...}}...}
    def getValueByVarDict(self, previous_value: VarPreviousValue):
        value_var_declared_dict = {"value": previous_value.value, "children": {}}
        for var_part, var_previous_value in previous_value.children.items():
            value_var_declared_dict["children"][var_part] = self.getValueByVarDict(var_previous_value)
        return value_var_declared_dict
    
    def setVarsDeclared(self, var):
        return self.vars_declared[-1].append(var)

def handle_client(conn: socket.socket, addr: tuple[str, int]):
    class ProgramFinished(Exception):
        pass

    class DebugManager():
        def __init__(self, process, thread):
            gvars = []
            for module in target.module_iter():
                for sym in module:
                    if sym.GetType() == lldb.eSymbolTypeData:  # データシンボル（変数）
                        name = sym.GetName()
                        if name:
                            var = target.FindFirstGlobalVariable(name)
                            if var.IsValid():
                                gvars.append(var)
            self.vars_tracker: VarsTracker = VarsTracker(gvars)
            self.isEnd = False
            self.process = process
            self.thread = thread
            self.line_loop = []
            self.func_checked = []
            self.std_messages = []
            self.input_check_num = {}
            self.stdin_buffer = ""
            self.file_check_num = {}
            self.file_info_to_send = []

            if (next_state := self.get_next_state()):
                self.state, self.frame, self.file_name, self.next_line_number, self.func_crnt_name, self.next_frame_num = next_state
                with open(f"{DATA_DIR}/{self.file_name[:-2]}/{self.file_name[:-2]}_line.json", 'r') as f:
                    self.line_data = json.load(f)
                    self.func_name = self.func_crnt_name
                    self.frame_num = 1
                    self.get_std_outputs()
                    self.event_sender({"line": self.line_data[self.func_name][2], "items": self.vars_tracker.getGlobalValueAll(), "status": "ok"}, False)
                    self.line_number = self.line_data[self.func_name][2] - 1
                with open(f"{DATA_DIR}/{self.file_name[:-2]}/{self.file_name[:-2]}_varDeclLines.json", 'r') as f:
                    self.varsDeclLines_list: dict[str, list[str]] = json.load(f)
            else:
                self.event_sender({"end": True, "status": "ng"})
                self.isEnd = True
                # self.line_number = self.line_data["main"][2]

            self.vars_tracker.trackStart(self.frame)
            self.vars_checker()

        def step_conditionally(self, var_check = True):
            # scanf フォーマット → Python 正規表現パターンの対応表
            scanf_patterns = {
                "%d": r"[-+]?\d+",
                "%i": r"[-+]?(0[xX][0-9a-fA-F]+|0[0-7]*|\d+)",
                "%u": r"\d+",
                "%o": r"[0-7]+",
                "%x": r"[0-9a-fA-F]+",
                "%X": r"[0-9a-fA-F]+",
                "%f": r"[-+]?\d*(\.\d+)?([eE][-+]?\d+)?",
                "%F": r"[-+]?\d*(\.\d+)?([eE][-+]?\d+)?",
                "%e": r"[-+]?\d+(\.\d+)?[eE][-+]?\d+",
                "%E": r"[-+]?\d+(\.\d+)?[eE][-+]?\d+",
                "%g": r"[-+]?\d+(\.\d+)?([eE][-+]?\d+)?",
                "%G": r"[-+]?\d+(\.\d+)?([eE][-+]?\d+)?",
                "%c": r".",
                "%s": r"\S+",
                "%p": r"0x[0-9a-fA-F]+",
                "%n": None,
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

                for token in tokens:
                    if token.endswith("c"):
                        pass
                    elif token.endswith("n"):
                        results.append(str(pos))
                        continue
                    else:
                        pos = skip_whitespace(text, pos)

                    pat = scanf_patterns.get(token.lstrip("*"))
                    if not pat:
                        raise ValueError(f"Unsupported format specifier: {token}")

                    if pos >= len(text):
                        return "incomplete", results, ""
                    
                    regex = re.compile(pat)
                    match = regex.match(text, pos)
                    if not match:
                        return "mismatch", results, text[pos:]

                    value = match.group(0)
                    if not token.startswith("%*"):
                        results.append(value)
                    pos = match.end()

                remaining = text[pos:]
                return "ok", results, remaining

            def is_complete_match(fmt: str, text: str):
                """入力文字列がフォーマット全体に合致するかを確認"""
                state, results, remaining = match_scanf(fmt, text)
                return state, results, remaining
            
            # プロセスの状態を更新
            if self.isEnd:
                while True:
                    if (event := self.event_reciever()) is None:
                        continue
                    if event.get('return', None) is not None:
                        self.event_sender({"message": "おめでとうございます!! ここがゴールです!!", "status": "ok", "finished": True})
                        print("プログラムは正常に終了しました")
                        raise ProgramFinished()
                    else:
                        self.event_sender({"message": "NG行動をしました1!!", "status": "ng"})

            self.thread = self.frame.GetThread()
            self.process = self.thread.GetProcess()
            target = self.process.GetTarget()

            # 現在の命令アドレス
            pc_addr = self.frame.GetPCAddress()

            # 現在の命令を取得（必要な数だけ、ここでは1つ）
            inst = target.ReadInstructions(pc_addr, 1)[0]
            
            mnemonic = inst.GetMnemonic(target)

            print(f"Next instruction: {mnemonic} {inst.GetOperands(target)}")

            if str(self.next_line_number) in self.line_data[self.func_crnt_name][3] and len(self.func_checked) < self.next_frame_num - 1:
                self.func_checked.append(self.line_data[self.func_crnt_name][3][str(self.next_line_number)])

            if str(self.next_line_number) in self.line_data[self.func_crnt_name][4] and (self.next_frame_num, self.next_line_number) not in self.input_check_num:
                self.input_check_num[(self.next_frame_num, self.next_line_number)] = (self.line_data[self.func_crnt_name][4][str(self.next_line_number)], -1)

            input_check = None
            if ((self.next_frame_num, self.next_line_number)) in self.input_check_num:
                if str(self.input_check_num[(self.next_frame_num, self.next_line_number)][1] + 1) in self.input_check_num[(self.next_frame_num, self.next_line_number)][0]:
                    input_check = str(self.input_check_num[(self.next_frame_num, self.next_line_number)][1] + 1)
                self.input_check_num[(self.next_frame_num, self.next_line_number)] = (self.input_check_num[(self.next_frame_num, self.next_line_number)][0], self.input_check_num[(self.next_frame_num, self.next_line_number)][1] + 1)

            # inputが入れられるまで次のstepには行かない
            if input_check:
                while True:
                    if (event := self.event_reciever()) is None:
                        return
                    if (new_stdin := event.get('stdin', None)) is not None:
                        state, results, remaining = is_complete_match(self.input_check_num[(self.next_frame_num, self.next_line_number)][0][input_check][0], self.stdin_buffer + new_stdin)
                        if state == "incomplete":
                            self.event_sender({"message": "入力が足りていません!! もう一度入力してください!!", "status": "ng"})
                            continue
                        self.stdin_buffer = remaining
                        self.process.PutSTDIN(new_stdin)
                        self.input_check_num[(self.next_frame_num, self.next_line_number)][0][input_check].pop(0)
                        if len(self.input_check_num[(self.next_frame_num, self.next_line_number)][0][input_check]):
                            self.event_sender({"message": "次のscanf用に入力してください!!", "status": "ok"})
                        else:
                            break
                    else:
                        self.event_sender({"message": f"ヒント: 値を入力してください!!", "status": "ng"})
                self.input_check_num[(self.next_frame_num, self.next_line_number)][0].pop(input_check)
                if len(self.input_check_num[(self.next_frame_num, self.next_line_number)][0]) == 0:
                    self.input_check_num.pop((self.next_frame_num, self.next_line_number))

            if str(self.next_line_number) not in self.line_data[self.func_crnt_name][3]:
                self.thread.StepInto()
            else:
                if len(self.func_checked) and len(self.func_checked[-1]) != 0:
                    self.func_checked[-1].pop(0)
                    self.thread.StepInto()
                else:
                    self.func_checked.pop()
                    self.thread.StepOut()

            if (next_state := self.get_next_state()):
                self.line_number = self.next_line_number
                self.func_name = self.func_crnt_name
                self.frame_num = self.next_frame_num
                self.state, self.frame, self.file_name, self.next_line_number, self.func_crnt_name, self.next_frame_num = next_state
                if var_check:
                    self.vars_tracker.trackStart(self.frame)
                if input_check:
                    if state == "ok":
                        self.event_sender({"message": "値がstdinに入力されました!!", "status": "ok", "items": self.vars_tracker.getValueAll()})
                    elif state == "mismatch":
                        self.event_sender({"message": "値がscanfのフォーマットに合致しませんでした、、、", "status": "ok", "items": self.vars_tracker.getValueAll()})
                
                if str(self.line_number) in self.line_data[self.func_name][5] and (self.frame_num, self.line_number) not in self.file_check_num:
                    self.file_check_num[(self.frame_num, self.line_number)] = (self.line_data[self.func_name][5][str(self.line_number)], -1)

                if ((self.frame_num, self.line_number)) in self.file_check_num:
                    self.file_check_num[(self.frame_num, self.line_number)] = (self.file_check_num[(self.frame_num, self.line_number)][0], self.file_check_num[(self.frame_num, self.line_number)][1] + 1)
                    if str(self.file_check_num[(self.frame_num, self.line_number)][1]) in self.file_check_num[(self.frame_num, self.line_number)][0]:
                        file_check = str(self.file_check_num[(self.frame_num, self.line_number)][1])
                        self.file_info_to_send = self.file_check_num[(self.frame_num, self.line_number)][0][file_check]
                        self.file_check_num[(self.frame_num, self.line_number)][0].pop(file_check)
                        if len(self.file_check_num[(self.frame_num, self.line_number)][0]) == 0:
                            self.file_check_num.pop((self.frame_num, self.line_number))
            else:
                self.isEnd = True
                self.line_number = self.next_line_number

            self.get_std_outputs()

        def get_next_state(self):
            state = self.process.GetState()

            frame = thread.GetFrameAtIndex(0)

            line_entry = frame.GetLineEntry()
            file_name = line_entry.GetFileSpec().GetFilename()
            line_number = line_entry.GetLine()
            func_name = frame.GetFunctionName()

            if func_name is None or file_name is None:
                # state_checker(state)
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

        def get_new_values(self, values_changed):
            value_changed_dict = []
            for value_changed in values_changed:
                for value_changed_tuple in self.vars_tracker.vars_changed[value_changed]:
                    value_path = [*value_changed_tuple]
                    isCorrect, value = self.vars_tracker.getValuePartly([value_changed, *value_path])
                    value_changed_dict.append({"item": value_changed, "path": value_path, "value": value})
            return value_changed_dict
        
        def vars_checker(self, isForFalse=False):
            if self.isEnd:
                return
            
            # varsDeclLines = list(set(self.varsDeclLines_list.pop(str(self.line_number), [])) - set(self.vars_tracker.vars_declared[-1]))
            # これだとスコープ外の変数を拾ってしまうことがある
            # for文の条件文内の宣言だとfalseの時にself.varsDeclLines_list.get(str(self.line_number), [])でスコープ外の変数を取得してしまうことがある
            varsDeclLines = [] if isForFalse else [var for var in self.varsDeclLines_list.get(str(self.line_number), []) if var not in self.vars_tracker.vars_declared[-1]]

            varsDeclLines_copy = varsDeclLines[:]

            # やはり、変数は順番に取得させる
            while len(varsDeclLines_copy) != 0:
                var = varsDeclLines_copy.pop(0)
                vars_event: list[str] = []
                errorCnt = 0
                line_number_track: list[int] = [self.line_number]
                func_num = 0
                # 変数が合致していればstepinを実行して次に進む
                while True:
                    # 異なる変数の取得、または関数のスキップの後はメッセージを受信する
                    if (event := self.event_reciever()) is None:
                        return
                    if (item := event.get('item', None)) is not None:
                        if item != var:
                            errorCnt += 1
                            # 複数回入力を間違えたらヒントをあげる
                            if errorCnt >= 3:
                                self.event_sender({"message": f"ヒント: アイテム {var} を取得してください!!", "status": "ng"})
                            else:
                                self.event_sender({"message": f"異なるアイテム {item} を取得しようとしています!!", "status": "ng"})
                            continue

                        fromTo = event['fromTo']
                        funcWarp = event['funcWarp']
                        if fromTo[:len(line_number_track)] == line_number_track:
                            crntFromTo = fromTo[len(line_number_track):]
                            if len(funcWarp) != 0:
                                funcWarp = funcWarp[func_num:]

                        # アイテムを正しく取得できたら次の変数に移る
                        if not crntFromTo:
                            self.event_sender({"message": f"アイテム {var} を正確に取得できました!!", "item": self.vars_tracker.getValueByVar(var), "status": "ok"}, len(varsDeclLines_copy) == 0)
                            self.vars_tracker.setVarsDeclared(var)
                            break

                        while crntFromTo:
                            if self.next_frame_num > self.frame_num:
                                line_number_track.append(self.next_line_number)
                                if funcWarp[0]["name"] == self.func_crnt_name and funcWarp[0]["line"] == self.next_line_number:
                                    func_num += 1
                                    self.event_sender({"message": f"遷移先の関数 {self.func_crnt_name} の処理をスキップしますか?", "undefined": False, "status": "ok", "skip": True})
                                    event = self.event_reciever()
                                    if event.get('skip', False):
                                        back_line_number = self.line_number
                                        skipped_func_name = self.func_crnt_name
                                        while 1:
                                            self.step_conditionally()
                                            if back_line_number == self.next_line_number:
                                                retVal = thread.GetStopReturnValue().GetValue()
                                                self.event_sender({"message": "スキップが完了しました", "status": "ok", "items": self.vars_tracker.getValueAll(), "func": self.func_crnt_name, "skippedFunc": skipped_func_name, "retVal": retVal})
                                            if back_line_number == self.line_number:
                                                break
                                    else:
                                        items = {}
                                        for argname, argtype in funcWarp[0]['args'].items():
                                            items[argname] = {"value": self.vars_tracker.getValueByVar(argname), "type": argtype}
                                        self.event_sender({"message": f"スキップをキャンセルしました。関数 {self.func_crnt_name} に遷移します", "status": "ok", "func": self.func_name, "fromLine": self.line_number, "skipTo": {"name": funcWarp[0]["name"], "x": funcWarp[0]["x"], "y": funcWarp[0]["y"], "items": items}})
                                        back_line_number = self.line_number
                                        while 1:
                                            if self.analyze_frame():
                                                continue
                                            if back_line_number == self.line_number:
                                                break
                                    break
                                # もし、fromToと今まで辿った行が部分一致しなければ新たな通信を待つ
                                else:
                                    errorCnt += 1
                                    self.event_sender({"message": f"異なる行動をしようとしています10!!", "status": "ng"})
                                    break
                            # ここは次が関数以外の場合(構造体や配列の最初の行から最初の関数に行番が移る場合)
                            else:
                                self.step_conditionally(var_check=False)
                                if crntFromTo[0] != self.line_number:
                                    self.event_sender({"message": f"このアイテムは取得できません11!!", "status": "ng"})
                                    break
                                line_number_track.append(self.line_number)
                                crntFromTo.pop(0)
                    else:
                        errorCnt += 1
                        self.event_sender({"message": "異なる行動をしようとしています1!!", "status": "ng"})

            # vars_changedとvarsTrackerの共通項とvarsDeclLinesの差項を、値が変化した変数として検知する
            # vars_changedにもkeysを使って宣言済みかつ値が変わった変数を取得できる
            common = list(set(self.vars_tracker.vars_changed.keys()) & set(self.vars_tracker.vars_declared[-1]))
            # そして今回宣言された変数以外で値が変わった変数(の一番上の名前)を取得できる
            values_changed = list(set(common) - set(varsDeclLines))
            # その後、varsChangedをキーとしてvars_changedの変更値を取得する

            # if, while True, while False, for In, for True, for False, switch Caseによる値の変化は無視できるようにする
            if len(values_changed) != 0:
                if self.line_number in self.line_data[self.func_name][0]:
                    self.vars_tracker.vars_changed = {var: self.vars_tracker.vars_changed[var] for var in values_changed}
                else:
                    vars_event = []
                    errorCnt = 0
                    if (event := self.event_reciever()) is None:
                        return
                    while True:
                        if event.get('itemsetall', False):
                            value_changed_dict = self.get_new_values(values_changed)
                            self.event_sender({"message": "新しいアイテムの値を設定しました!!", "status": "ok", "values": value_changed_dict})
                            break
                        errorCnt += 1
                        self.event_sender({"message": "異なる行動をしようとしています2!!", "status": "ng"})
                        event = self.event_reciever()

            # 変数が初期化されない時、スキップされるので、それも読み取る
            target_lines = [line for line in self.varsDeclLines_list if self.line_number < int(line) < self.next_line_number]

            if len(target_lines) != 0 and self.line_number not in self.line_data[self.func_name][0]:
                # 変数が合致していればstepinを実行して次に進む
                for line in target_lines:
                    # skipped_varDecls = self.varsDeclLines_list.pop(line)
                    skipped_varDecls = self.varsDeclLines_list[line]
                    vars_event = []
                    errorCnt = 0
                    if (event := self.event_reciever()) is None:
                        return
                    while True:
                        if (item := event.get('item', None)) is not None:
                            if not item in skipped_varDecls:
                                errorCnt += 1
                                print(f'your variables were incorrect!!\ncorrect variables: {skipped_varDecls}')
                                # 複数回入力を間違えたらヒントをあげる
                                if errorCnt >= 3:
                                    self.event_sender({"message": f"ヒント: アイテム {', '.join(list(set(skipped_varDecls) - set(vars_event)))} を取得してください!!", "status": "ng"})
                                else:
                                    self.event_sender({"message": f"異なるアイテム {item} を取得しようとしています!!", "status": "ng"})
                            else:
                                vars_event.append(item)
                                if Counter(vars_event) == Counter(skipped_varDecls):
                                    print("you selected correct vars")
                                    self.vars_tracker.setVarsDeclared(item)
                                    self.event_sender({"message": f"アイテム {item} を正確に取得できました!!", "undefined": True, "item": self.vars_tracker.getValueByVar(item), "status": "ok"})
                                    break
                                self.vars_tracker.setVarsDeclared(item)
                                self.event_sender({"message": f"アイテム {item} を正確に取得できました!!", "undefined": True, "item": self.vars_tracker.getValueByVar(item), "status": "ok"}, False)
                        else:
                            errorCnt += 1
                            self.event_sender({"message": "異なる行動をしようとしています1!!", "status": "ng"})
                        event = self.event_reciever()

        def analyze_frame(self, backToLine: int = None):
            def check_condition(condition_type: str, fromTo: list[int], funcWarp):
                errorCnt = 0
                line_number_track: list[int] = fromTo[:2]
                func_num = 0
                while True:
                    # まず、if文でどの行まで辿ったかを確かめる
                    if fromTo[:len(line_number_track)] == line_number_track:
                        crntFromTo = fromTo[len(line_number_track):]
                        if len(funcWarp) != 0:
                            funcWarp = funcWarp[func_num:]
                    # もし、fromToと今まで辿った行が部分一致しなければ新たな通信を待つ
                    else:
                        errorCnt += 1
                        self.event_sender({"message": f"ここから先は進入できません2!! {f"ヒント: {condition_type} 条件を見ましょう!!" if errorCnt >= 3 else ""}", "status": "ng"})
                        while True:
                            if (event := self.event_reciever()) is None:
                                break
                            if (type := event.get('type', '')) != condition_type:
                                errorCnt += 1
                                self.event_sender({"message": f"NG行動をしました!! {f"ヒント: {condition_type} 条件を見ましょう!!" if errorCnt >= 3 else ""}", "status": "ng"})
                            elif (fromTo := event.get('fromTo', None)) is None:
                                errorCnt += 1
                                self.event_sender({"message": f"NG行動をしました!! {f"ヒント: {condition_type} 条件を見ましょう!!" if errorCnt >= 3 else ""}", "status": "ng"})
                            elif (funcWarp := event.get('funcWarp', None)) is None:
                                errorCnt += 1
                                self.event_sender({"message": f"NG行動をしました!! {f"ヒント: {condition_type} 条件を見ましょう!!" if errorCnt >= 3 else ""}", "status": "ng"})
                            else:
                                break
                        continue
                    # 全ての行数が合致していたらif文の開始の正誤の分析を終了する
                    # crntFromToが 空 => 行番が完全一致になる
                    if not crntFromTo:
                        # 条件文での値の変化はここで一括で取得する (allではなくpartlyにするかどうかは考える)
                        self.event_sender({"message": "", "status": "ok", "values": self.get_new_values(self.vars_tracker.vars_changed.keys())})
                        self.vars_tracker.trackStart(self.frame)
                        self.vars_checker(condition_type == 'forFalse')
                        break

                    while crntFromTo:
                        # 何かしらの関数に遷移したとき
                        if self.next_frame_num > self.frame_num:
                            if line_number_track[-1] == self.next_line_number:
                                func_num += 1
                                self.event_sender({"message": f"関数 {self.func_crnt_name} の処理をスキップしますか?", "status": "ok", "skipCond": True})
                                event = self.event_reciever()
                                # スキップする
                                if event.get('skip', False):
                                    retVal = None
                                    back_line_number = self.line_number
                                    back_frame_num = self.frame_num
                                    skipped_func_name = self.func_crnt_name
                                    while 1:
                                        self.step_conditionally()
                                        if back_line_number == self.next_line_number:
                                            retVal = thread.GetStopReturnValue().GetValue()
                                            self.event_sender({"message": "スキップを完了しました", "status": "ok", "items": self.vars_tracker.getValueAll(), "func": self.func_crnt_name, "skippedFunc": skipped_func_name, "retVal": retVal})
                                        elif back_line_number == self.line_number:
                                            line_number_track.append(self.next_line_number)
                                            break
                                        # たまにvoid型の関数限定で元の場所以上に戻ってくることがあるので、その場合に対応する
                                        elif condition_type == "func" and back_frame_num == self.next_frame_num and back_line_number < self.next_line_number:
                                            line_number_track = fromTo
                                            self.event_sender({"message": "スキップを完了しました", "status": "ok", "items": self.vars_tracker.getValueAll(), "func": self.func_name, "skippedFunc": skipped_func_name, "retVal": retVal})
                                            break
                                # スキップしない
                                else:
                                    items = {}
                                    func = funcWarp.pop(0)
                                    for argname, argtype in func["args"].items():
                                        items[argname] = {"value": self.vars_tracker.getValueByVar(argname), "type": argtype}
                                    self.event_sender({"message": f"スキップをキャンセルしました。関数 {self.func_crnt_name} に遷移します", "status": "ok", "func": self.func_name, "fromLine": self.line_number, "skipTo": {"name": func["name"], "x": func["x"], "y": func["y"], "items": items}})
                                    back_line_number = self.line_number
                                    self.step_conditionally()
                                    while 1:
                                        if self.analyze_frame(fromTo[0]):
                                            continue
                                        if back_line_number == self.line_number:
                                            break
                                    line_number_track.append(self.next_line_number)
                            else:
                                self.event_sender({"message": "ここから先は進入できません10!!", "status": "ng"})
                            while True:
                                if (event := self.event_reciever()) is None:
                                    continue
                                if (type := event.get('type', '')) != condition_type:
                                    errorCnt += 1
                                    self.event_sender({"message": f"NG行動をしました!! {f"ヒント: {condition_type} 条件を見ましょう!!" if errorCnt >= 3 else ""}", "status": "ng"})
                                elif (fromTo := event.get('fromTo', None)) is None:
                                    errorCnt += 1
                                    self.event_sender({"message": f"NG行動をしました!! {f"ヒント: {condition_type} 条件を見ましょう!!" if errorCnt >= 3 else ""}", "status": "ng"})
                                elif (funcWarp := event.get('funcWarp', None)) is None:
                                    errorCnt += 1
                                    self.event_sender({"message": f"NG行動をしました!! {f"ヒント: {condition_type} 条件を見ましょう!!" if errorCnt >= 3 else ""}", "status": "ng"})
                                else:
                                    break
                            break
                        else:
                            self.step_conditionally(var_check=False)

                            if crntFromTo[0] != self.next_line_number:
                                errorCnt += 1
                                self.event_sender({"message": f"ここから先は進入できません3!! {f"ヒント: {condition_type} 条件を見ましょう!!" if errorCnt >= 3 else ""}", "status": "ng"})
                                while True:
                                    if (event := self.event_reciever()) is None:
                                        continue
                                    if (type := event.get('type', '')) != condition_type:
                                        errorCnt += 1
                                        self.event_sender({"message": f"NG行動をしました!! {f"ヒント: {condition_type} 条件を見ましょう!!" if errorCnt >= 3 else ""}", "status": "ng"})
                                    elif (fromTo := event.get('fromTo', None)) is None:
                                        errorCnt += 1
                                        self.event_sender({"message": f"NG行動をしました!! {f"ヒント: {condition_type} 条件を見ましょう!!" if errorCnt >= 3 else ""}", "status": "ng"})
                                    else:
                                        break
                                line_number_track.append(self.next_line_number)
                                break
                            line_number_track.append(crntFromTo.pop(0))

            def check_return(fromTo: list[int], funcWarp):
                errorCnt = 0
                line_number_track: list[int] = fromTo[:2]
                func_num = 0
                while True:
                    # まず、if文でどの行まで辿ったかを確かめる
                    if fromTo[:len(line_number_track)] == line_number_track:
                        crntFromTo = fromTo[len(line_number_track):]
                        if len(funcWarp) != 0:
                            funcWarp = funcWarp[func_num:]
                    # もし、fromToと今まで辿った行が部分一致しなければ新たな通信を待つ
                    else:
                        errorCnt += 1
                        self.event_sender({"message": f"ここから先は進入できません2!!", "status": "ng"})
                        while True:
                            if (event := self.event_reciever()) is None:
                                break
                            if (fromTo := event.get('fromTo', None)) is None:
                                errorCnt += 1
                                self.event_sender({"message": f"NG行動をしました!!", "status": "ng"})
                            elif (funcWarp := event.get('funcWarp', None)) is None:
                                errorCnt += 1
                                self.event_sender({"message": f"NG行動をしました!!", "status": "ng"})
                            else:
                                break
                        continue
                    # 全ての行数が合致していたらif文の開始の正誤の分析を終了する
                    # crntFromToが 空 => 行番が完全一致になる
                    if not crntFromTo:
                        retVal = thread.GetStopReturnValue().GetValue()
                        self.step_conditionally()
                        self.event_sender({"message": f"関数 {self.func_name} に戻ります!!", "status": "ok", "items": self.vars_tracker.getValueAll(), "backToFunc": self.func_name, "backToLine": backToLine, "retVal": retVal})
                        break
                    
                    while crntFromTo:
                        # 何かしらの関数に遷移したとき
                        if self.next_frame_num > self.frame_num:
                            if line_number_track[-1] == self.next_line_number:
                                func_num += 1
                                self.event_sender({"message": f"関数 {self.func_crnt_name} の処理をスキップしますか?", "status": "ok", "skipReturn": True})
                                event = self.event_reciever()
                                # スキップする
                                if event.get('skip', False):
                                    retVal = None
                                    back_line_number = self.line_number
                                    skipped_func_name = self.func_crnt_name
                                    while 1:
                                        self.step_conditionally()
                                        if back_line_number == self.next_line_number:
                                            retVal = thread.GetStopReturnValue().GetValue()
                                            self.event_sender({"message": "スキップを完了しました", "status": "ok", "items": self.vars_tracker.getValueAll(), "func": self.func_crnt_name, "skippedFunc": skipped_func_name, "retVal": retVal})
                                        if back_line_number == self.line_number:
                                            break
                                # スキップしない
                                else:
                                    items = {}
                                    func = funcWarp.pop(0)
                                    for argname, argtype in func["args"].items():
                                        items[argname] = {"value": self.vars_tracker.getValueByVar(argname), "type": argtype}
                                    self.event_sender({"message": f"スキップをキャンセルしました。関数 {self.func_crnt_name} に遷移します", "status": "ok", "func": self.func_name, "fromLine": self.line_number, "skipTo": {"name": func["name"], "x": func["x"], "y": func["y"], "items": items}})
                                    back_line_number = self.line_number
                                    self.step_conditionally()
                                    while 1:
                                        if self.analyze_frame(fromTo[0]):
                                            continue
                                        if back_line_number == self.line_number:
                                            break
                                line_number_track.append(self.next_line_number)
                            else:
                                self.event_sender({"message": "ここから先は進入できません10!!", "status": "ng"})
                            while True:
                                if (event := self.event_reciever()) is None:
                                    continue
                                if (fromTo := event.get('fromTo', None)) is None:
                                    errorCnt += 1
                                    self.event_sender({"message": f"NG行動をしました!!", "status": "ng"})
                                elif (funcWarp := event.get('funcWarp', None)) is None:
                                    errorCnt += 1
                                    self.event_sender({"message": f"NG行動をしました!!", "status": "ng"})
                                else:
                                    break
                            break
                        else:
                            self.step_conditionally(var_check=False)

                            if crntFromTo[0] != self.next_line_number:
                                errorCnt += 1
                                self.event_sender({"message": f"ここから先は進入できません3!!", "status": "ng"})
                                while True:
                                    if (event := self.event_reciever()) is None:
                                        continue
                                    if (fromTo := event.get('fromTo', None)) is None:
                                        errorCnt += 1
                                        self.event_sender({"message": f"NG行動をしました!!", "status": "ng"})
                                    elif (funcWarp := event.get('funcWarp', None)) is None:
                                        errorCnt += 1
                                        self.event_sender({"message": f"NG行動をしました!!", "status": "ng"})
                                    else:
                                        break
                                line_number_track.append(self.next_line_number)
                                break
                            line_number_track.append(crntFromTo.pop(0))

            skipStart = None
            skipEnd = None

            if self.line_data.get(self.func_name, None) and self.line_number in self.line_data[self.func_name][0] and not self.isEnd:
                if (event := self.event_reciever()) is None:
                    return PROGRESS
                if (ngname := event.get('ng', None)) is not None:
                    if ngname == "notEnter":
                        self.event_sender({"message": "ここから先は進入できません1!!", "status": "ng"})
                    else:
                        self.event_sender({"message": "NG行動をしました2!!", "status": "ng"})
                    return CONTINUE
                elif (fromTo := event.get('fromTo', None)) is not None:
                    type = event.get('type', '')
                    # そもそも最初の行番が合致していなければ下のwhile Trueに入る前にカットする必要がある
                    # こうしないとどこのエリアに行っても条件構文に関する受信待ちが永遠に続いてしまう
                    if len(fromTo) >= 2:
                        if fromTo[:2] == [self.line_number, self.next_line_number]:
                            if type in ['if', 'whileTrue', 'whileFalse', 'forTrue', 'forFalse', 'doWhileTrue', 'doWhileFalse', 'func']:
                                funcWarp = event['funcWarp']
                                check_condition(type, fromTo, funcWarp)
                                if type in ['whileFalse', 'forFalse', 'doWhileFalse']:
                                    self.line_loop.pop(-1)
                                    skipStart = None
                                    skipEnd = None
                            elif type == 'ifEnd':
                                self.event_sender({"message": "", "status": "ok"})
                            elif type == 'switchCase':
                                if (funcWarps := event.get('funcWarp', None)) is not None:
                                    for funcWarp in funcWarps:
                                        if funcWarp["name"] == self.func_crnt_name and funcWarp["line"] == self.next_line_number:
                                            self.event_sender({"message": f"遷移先の関数 {self.func_crnt_name} の処理をスキップしますか?", "status": "ok", "skip": True})
                                            event = self.event_reciever()
                                            if event.get('skip', False):
                                                back_line_number = self.line_number
                                                while 1:
                                                    self.step_conditionally()
                                                    if back_line_number == self.line_number:
                                                        break
                                                self.event_sender({"message": "スキップが完了しました", "status": "ok", "items": self.vars_tracker.getValueAll()})
                                            else:
                                                items = {}
                                                for argname, argtype in funcWarp["args"].items():
                                                    items[argname] = {"item": self.vars_tracker.getValueByVar(argname), "type": argtype}
                                                self.event_sender({"message": f"スキップをキャンセルしました。関数 {self.func_crnt_name} に遷移します", "status": "ok", "fromLine": self.line_number, "skipTo": {"name": funcWarp["name"], "x": funcWarp["x"], "y": funcWarp["y"], "items": items}})
                                                back_line_number = self.line_number
                                                while 1:
                                                    if self.analyze_frame():
                                                        continue
                                                    if back_line_number == self.line_number:
                                                        break
                                else:
                                    self.event_sender({"message": "", "status": "ok", "values": self.get_new_values(self.vars_tracker.vars_changed.keys())})
                                    self.vars_tracker.trackStart(self.frame)
                                    self.vars_checker()
                            elif type == 'continue':
                                # type == while or forの場合
                                if self.line_number >= self.next_line_number:
                                    skipStart = self.next_line_number
                                    skipEnd = self.line_data[self.func_name][1][str(self.next_line_number)]
                                    # ここでスキップするかどうかを確認する
                                    self.event_sender({"message": "ループを抜ける直前までスキップしますか?", "status": "ok", "skip": True})
                                    event = self.event_reciever()
                                    if event.get('skip', False):
                                        while skipStart <= self.next_line_number <= skipEnd:
                                            # ここは後々、scanfがあるかどうかでスキップするかどうかを確かめる
                                            self.step_conditionally()
                                        self.event_sender({"message": "スキップが完了しました", "status": "ok", "items": self.vars_tracker.getValueAll()})
                                        return CONTINUE
                                    else:
                                        self.event_sender({"message": "スキップをキャンセルしました", "status": "ok"})
                                # type == do_whileの場合
                                else:
                                    # まずは条件文に行って次がTrueかFalseかを見る
                                    self.step_conditionally()
                                    # 次がdoWhileTrueと考えられるならスキップを提案する
                                    if self.line_data[self.func_name][1][str(self.line_number)] <= self.next_line_number <= self.line_number:
                                        skipStart = self.line_number
                                        skipEnd = self.line_data[self.func_name][1][str(self.line_number)]
                                        # ここでスキップするかどうかを確認する
                                        self.event_sender({"message": "ループを抜ける直前までスキップしますか?", "status": "ok", "skip": True})
                                        event = self.event_reciever()
                                        if event.get('skip', False):
                                            while skipStart <= self.next_line_number <= skipEnd:
                                                # ここは後々、scanfがあるかどうかでスキップするかどうかを確かめる
                                                self.step_conditionally()
                                            self.event_sender({"message": "スキップが完了しました", "status": "ok", "items": self.vars_tracker.getValueAll()})
                                        else:
                                            self.event_sender({"message": "スキップをキャンセルしました", "status": "ok"})
                                    else:
                                        self.event_sender({"message": "", "status": "ok"})
                                    return CONTINUE
                            elif type == 'break':
                                self.event_sender({"message": "", "status": "ok"})
                                self.line_loop.pop(-1)
                                skipEnd = None
                            elif type == 'return':
                                funcWarp = event['funcWarp']
                                check_return(fromTo, funcWarp)
                                return PROGRESS
                            else:
                                self.event_sender({"message": "ここから先は進入できません4!!", "status": "ng"})
                                return CONTINUE
                        elif fromTo[:2] == [None, self.next_line_number]:
                            if type == 'doWhileInit':
                                # 最初なので確定でline_loopに追加する
                                self.line_loop.append(self.next_line_number)
                                self.event_sender({"message": "", "status": "ok"})
                                self.vars_tracker.trackStart(self.frame)
                                self.vars_checker()
                            elif type == 'switchEnd':
                                self.event_sender({"message": "", "status": "ok"})
                        else:
                            self.event_sender({"message": "ここから先は進入できません5!!", "status": "ng"})
                            return CONTINUE            
                    elif len(fromTo) == 1 and fromTo == [self.line_number]:
                        if type == 'whileIn':
                            if len(self.line_loop) and self.line_loop[-1] == self.line_number:
                                skipStart = self.line_number
                                skipEnd = self.line_data[self.func_name][1][str(self.line_number)]
                                if skipStart <= self.next_line_number <= skipEnd:
                                    # ここでスキップするかどうかを確認する
                                    self.event_sender({"message": "ループを抜ける直前までスキップしますか?", "status": "ok", "skip": True})
                                    event = self.event_reciever()
                                    if event.get('skip', False):
                                        while skipStart <= self.next_line_number <= skipEnd:
                                            # ここは後々、scanfがあるかどうかでスキップするかどうかを確かめる
                                            self.step_conditionally()
                                        self.event_sender({"message": "スキップが完了しました", "status": "ok", "type": "while", "items": self.vars_tracker.getValueAll()})
                                    else:
                                        self.event_sender({"message": "スキップをキャンセルしました", "status": "ok"})
                                else:
                                    self.event_sender({"message": "", "status": "ok"})
                            else:
                                self.event_sender({"message": "", "status": "ok"})
                                self.line_loop.append(self.line_number)
                        elif type == 'doWhileIn':
                            if len(self.line_loop) and self.line_loop[-1] == self.next_line_number:
                                # ここでスキップするかどうを確認する
                                skipStart = self.line_data[self.func_name][1][str(self.line_number)]
                                skipEnd = self.line_number
                                self.event_sender({"message": "ループを抜ける直前までスキップしますか?", "status": "ok", "skip": True})
                                event = self.event_reciever()
                                if event.get('skip', False):
                                    while skipStart <= self.next_line_number <= skipEnd:
                                        # ここは後々、scanfがあるかどうかでスキップするかどうかを確かめる
                                        self.step_conditionally()
                                    self.event_sender({"message": "スキップが完了しました", "status": "ok", "type": "doWhile", "items": self.vars_tracker.getValueAll()})
                                else:
                                    self.event_sender({"message": "スキップをキャンセルしました", "status": "ok"})
                            else:
                                self.event_sender({"message": "", "status": "ok"})
                        elif type == 'forIn':
                            if len(self.line_loop) and self.line_loop[-1] == self.line_number:
                                skipStart = self.line_number
                                skipEnd = self.line_data[self.func_name][1][str(self.line_number)]
                                if skipStart <= self.next_line_number <= skipEnd:
                                    # ここでスキップするかどうかを確認する
                                    self.event_sender({"message": "ループを抜ける直前までスキップしますか?", "status": "ok", "skip": True, "values": self.get_new_values(self.vars_tracker.vars_changed.keys())})
                                    event = self.event_reciever()
                                    if event.get('skip', False):
                                        while skipStart <= self.next_line_number <= skipEnd:
                                            # ここは後々、scanfがあるかどうかでスキップするかどうかを確かめる
                                            self.step_conditionally()
                                        self.event_sender({"message": "スキップが完了しました", "status": "ok", "type": "for", "items": self.vars_tracker.getValueAll()})
                                    else:
                                        self.event_sender({"message": "スキップをキャンセルしました", "status": "ok"})
                                else:
                                    self.event_sender({"message": "", "status": "ok"})
                            else:
                                self.event_sender({"message": "", "status": "ok"})
                                self.line_loop.append(self.line_number)
                        else:
                            self.event_sender({"message": "ここから先は進入できません6!!", "status": "ng"})
                        return CONTINUE
                    else:
                        self.event_sender({"message": "ここから先は進入できません7!!", "status": "ng"})
                        return CONTINUE
                else:
                    self.event_sender({"message": "NG行動をしました6!!", "status": "ng"})
                    return CONTINUE

            self.step_conditionally()

            # 変数は前回の処理で変更されていたら見る
            self.vars_checker()

            return PROGRESS

        def event_reciever(self):
            # JSONが複数回に分かれて送られてくる可能性があるためパース
            data = conn.recv(1024)
            # ここは後々変えるかも
            if not data:
                return None
            buffer = data.decode()
            event = json.loads(buffer)
            print(f"[受信イベント] {event}")
            return event
    
        def event_sender(self, msgJson, getLine=True):
            if msgJson["status"] == "ok":
                msgJson["std"] = self.std_messages
                msgJson["files"] = self.file_info_to_send
                self.file_info_to_send = []
                if getLine:
                    target_lines = [line for line in self.varsDeclLines_list if self.line_number < int(line) < self.next_line_number]
                    skipped_vars = []
                    for target_line in target_lines:
                        skipped_vars += list(set(self.varsDeclLines_list[target_line]) - set(self.vars_tracker.vars_declared[-1]))
                    # 初期化されていない変数はスキップされてしまうので、そのような変数があるなら最初の行数を取得する
                    if len(skipped_vars) != 0 and self.line_number not in self.line_data[self.func_name][0]:
                        msgJson["line"] = int(target_lines[0])
                    else:
                        msgJson["line"] = self.next_line_number
                        msgJson["removed"] = self.vars_tracker.vars_removed
            send_data = json.dumps(msgJson)
            conn.sendall(send_data.encode('utf-8'))

    try:
        print(f"[接続] {addr} が接続しました")
            
        with conn:
            debug_manager = DebugManager(process, thread)

            # 変数は次の行での値を見て考える(まず変数チェッカーで次の行に進み変数の更新を確認) => その行と前の行で構文や関数は比較する(構文内の行の移動及び関数の移動は次の行と前の行が共に必要)
            while process.GetState() == lldb.eStateStopped:
                debug_manager.analyze_frame()
    except:
        pass


# region コマンドライン引数の確認
parser = argparse.ArgumentParser(description='for the c-backdoor')
# ベース名を取得
parser.add_argument('--name', type=str, required=True, help='string')
# 引数を解析
args = parser.parse_args()
# endregion

# region lldbの初期設定
lldb.SBDebugger.Initialize()
debugger = lldb.SBDebugger.Create()
debugger.SetAsync(False)

target = debugger.CreateTargetWithFileAndArch(args.name, lldb.LLDB_ARCH_DEFAULT)
if not target:
    print("failed in build of target")
    exit(1)

# print(f"Command line arguments: {args}")

# breakpointを行で指定するならByLocation
breakpoint = target.BreakpointCreateByName("main", target.GetExecutable().GetFilename())

launch_info = lldb.SBLaunchInfo([])
launch_info.SetWorkingDirectory(os.getcwd())

stdout_file = tempfile.NamedTemporaryFile(delete=False)
stderr_file = tempfile.NamedTemporaryFile(delete=False)

# stdout, stderr を別々のパイプにする
launch_info.AddOpenFileAction(1, stdout_file.name, True, True)  # fd=1 → stdout
launch_info.AddOpenFileAction(2, stderr_file.name, True, True)  # fd=2 → stderr

error = lldb.SBError()
process = target.Launch(launch_info, error)

# 読み取り用にlogファイルを常にopenしておく
stdout_r = open(stdout_file.name, "r")
stderr_r = open(stderr_file.name, "r")

if not error.Success() or not process or not process.IsValid():
    print("failed in operation")
    exit(1)

thread = process.GetThreadAtIndex(0)
if not thread.IsValid():
    print("no valid thread found")
    exit(1)
# endregion

# region サーバーの開始メソッドは再利用性がないのでインライン展開する
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

stdout_r.close()
stderr_r.close()

os.unlink(stdout_file.name)
os.unlink(stderr_file.name)

print("[サーバ終了]")
# endregion