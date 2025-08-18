import faulthandler
faulthandler.enable()
import lldb
import argparse
import os
import struct
import threading
import socket
import json
from collections import Counter

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
    def __init__(self):
        self.previous_values: list[dict[str, VarPreviousValue]] = []
        self.vars_changed: dict[str, list[tuple[str, ...]]] = {}
        self.vars_declared: list[list[str]] = []
        self.vars_removed: list[str] = []
        self.frames = ['start']
    
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
        
        self.vars_changed = {}
        return self.track(frame.GetVariables(True, True, False, True), self.previous_values[-1], [])

    def track(self, vars, var_previous_values: dict[str, VarPreviousValue], vars_path: list[str], depth=0, prefix="") -> list[str]:
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

            if depth == 0:
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
                                var_previous_values[name].children['[0]'] = VarPreviousValue(cstr, addr)
                            else:
                                print(f"{indent}→ {full_name} points to unreadable char*")

                        elif type_name == "int":
                            data = process.ReadMemory(addr, 4, error)
                            if error.Success():
                                val = struct.unpack("i", data)[0]
                                print(f"{indent}→ {full_name} points to int: {val}")
                                var_previous_values[name].children['[0]'] = VarPreviousValue(val, addr)
                            else:
                                print(f"{indent}→ {full_name} points to unreadable int*")

                        elif type_name == "float":
                            data = process.ReadMemory(addr, 4, error)
                            if error.Success():
                                val = struct.unpack("f", data)[0]
                                print(f"{indent}→ {full_name} points to float: {val}")
                                var_previous_values[name].children['[0]'] = VarPreviousValue(val, addr)
                            else:
                                print(f"{indent}→ {full_name} points to unreadable float*")

                        elif type_name == "double":
                            data = process.ReadMemory(addr, 8, error)
                            if error.Success():
                                val = struct.unpack("d", data)[0]
                                print(f"{indent}→ {full_name} points to double: {val}")
                                var_previous_values[name].children['[0]'] = VarPreviousValue(val, addr)
                            else:
                                print(f"{indent}→ {full_name} points to unreadable double*")

                        else:
                            # 構造体などの場合
                            deref = var.Dereference()
                            if deref.IsValid() and deref.GetNumChildren() > 0:
                                print(f"{indent}→ Deref {full_name}")
                                children = [deref.GetChildAtIndex(i) for i in range(deref.GetNumChildren())]
                                self.track(children, var_previous_values[name].children, vars_path + [name], depth + 1, full_name)
                    else:
                        children = [var.GetChildAtIndex(i) for i in range(num_children)]
                        self.track(children, var_previous_values[name].children, vars_path + [name], depth + 1, full_name)

                except Exception as e:
                    print(f"{indent}→ {full_name} deref error: {e}")

            elif num_children > 0:
                children = [var.GetChildAtIndex(i) for i in range(num_children)]
                self.track(children, var_previous_values[name].children, vars_path + [name], depth + 1, full_name)
    
        if depth == 0:
            if len(self.vars_declared) != 0:
                self.vars_removed = list(set(self.vars_declared[-1]) - set(crnt_vars))
                if len(self.vars_removed) != 0:
                    self.vars_declared[-1] = crnt_vars

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
    
def get_all_stdvalue(process):
    stdout_output = ""
    stderr_output = ""

    while True:
        out = process.GetSTDOUT(1024)
        err = process.GetSTDERR(1024)

        if not out and not err:
            break

        stdout_output += out
        stderr_output += err

    return stdout_output, stderr_output

def get_instructions_for_current_line(frame, target):
    line_entry = frame.GetLineEntry()
    start_addr = line_entry.GetStartAddress()
    end_addr = line_entry.GetEndAddress()

    start_load = start_addr.GetLoadAddress(target)
    end_load = end_addr.GetLoadAddress(target)

    # 命令数は大まかに見積もる（多めに取得して範囲で絞る）
    max_instrs = 20  
    all_instructions = target.ReadInstructions(start_addr, max_instrs)

    result = []
    for i in range(all_instructions.GetSize()):
        instr = all_instructions.GetInstructionAtIndex(i)
        addr = instr.GetAddress().GetLoadAddress(target)

        if start_load <= addr < end_load:
            mnemonic = instr.GetMnemonic(target)
            operands = instr.GetOperands(target)
            result.append((mnemonic, operands))
    
    return result

def handle_client(conn: socket.socket, addr: tuple[str, int]):
    class ProgramFinished(Exception):
        pass

    class DebugManager():
        def __init__(self, process, thread):
            self.vars_tracker: VarsTracker = VarsTracker()
            self.isEnd = False
            self.process = process
            self.thread = thread
            self.line_loop = []
            if (next_state := self.get_next_state()):
                self.state, self.frame, self.file_name, self.next_line_number, self.func_crnt_name, self.next_frame_num = next_state
                with open(f"{DATA_DIR}/{self.file_name[:-2]}/{self.file_name[:-2]}_line.json", 'r') as f:
                    self.line_data = json.load(f)
                    self.func_name = self.func_crnt_name
                    self.frame_num = 1
                    self.event_sender({"line": self.line_data[self.func_name][2]}, False)
                    self.line_number = self.line_data[self.func_name][2] - 1
                with open(f"{DATA_DIR}/{self.file_name[:-2]}/{self.file_name[:-2]}_varDeclLines.json", 'r') as f:
                    self.varsDeclLines_list: dict[str, list[str]] = json.load(f)
            else:
                self.event_sender({"end": True})
                self.isEnd = True
                # self.line_number = self.line_data["main"][2]

            self.vars_tracker.trackStart(self.frame)
            self.vars_checker()

        def step_conditionally(self, var_check = True):
            # プロセスの状態を更新
            if self.isEnd:
                while True:
                    if (event := self.event_reciever()) is None:
                        continue
                    if (retValue := event.get('return', None)) is not None:
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
            instructions = target.ReadInstructions(pc_addr, 1)

            inst = instructions[0]
            
            mnemonic = inst.GetMnemonic(target)

            print(f"Next instruction: {mnemonic} {inst.GetOperands(target)}")
            
            # とりあえず現在はvoid型の関数も扱わないし、戻り値の計算式に関数が含まれるものはないので、
            # func_crnt_nameの最終行とnext_line_numberが合致するかを確認して、合致していればstepOutする。
            # つまり、line_numberがreturn文の行の時に戻り値を取得できる
            # そのうち、returnの場所を予め取得して参照するようにする
            if self.line_data[self.func_crnt_name][0][-1] == self.next_line_number:
                self.thread.StepOut()
            else:
                self.thread.StepInto()

            if (next_state := self.get_next_state()):
                self.line_number = self.next_line_number
                self.func_name = self.func_crnt_name
                self.frame_num = self.next_frame_num
                self.state, self.frame, self.file_name, self.next_line_number, self.func_crnt_name, self.next_frame_num = next_state
                if var_check:
                    self.vars_tracker.trackStart(self.frame)
            else:
                self.isEnd = True
                self.line_number = self.next_line_number

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
            stdout_output, stderr_output = get_all_stdvalue(self.process)
            if stdout_output:
                print("[STDOUT]")
                print(stdout_output)

            if stderr_output:
                print("[STDERR]")
                print(stderr_output)

        def vars_checker(self, first_event=None):
            if self.isEnd:
                return
            
            # varsDeclLines = list(set(self.varsDeclLines_list.pop(str(self.line_number), [])) - set(self.vars_tracker.vars_declared[-1]))
            varsDeclLines = list(set(self.varsDeclLines_list.get(str(self.line_number), [])) - set(self.vars_tracker.vars_declared[-1]))
            getLine = (first_event is None)

            if len(varsDeclLines) != 0:
                # 変数が合致していればstepinを実行して次に進む
                vars_event: list[str] = []
                errorCnt = 0 
                if first_event:
                    event = first_event
                    first_event = None
                else:
                    if (event := self.event_reciever()) is None:
                        return
                while True:
                    if (item := event.get('item', None)) is not None:
                        if not item in varsDeclLines:
                            errorCnt += 1
                            print(f'your variables were incorrect!!\ncorrect variables: {varsDeclLines}')
                            # 複数回入力を間違えたらヒントをあげる
                            if errorCnt >= 3:
                                self.event_sender({"message": f"ヒント: アイテム {', '.join(list(set(varsDeclLines) - set(vars_event)))} を取得してください!!", "status": "ng"})
                            else:
                                self.event_sender({"message": f"異なるアイテム {item} を取得しようとしています!!", "status": "ng"})
                            event = self.event_reciever()
                            continue
                        
                        funcWarps = event['funcWarp']
                        if len(funcWarps) != 0:
                            for funcWarp in funcWarps:
                                if funcWarp["name"] == self.func_crnt_name and funcWarp["line"] == self.next_line_number:
                                    self.event_sender({"message": "遷移先の関数の処理をスキップしますか?", "item": self.vars_tracker.getValueByVar(item, -1), "undefined": False, "status": "ok", "skip": True})
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
                            vars_event.append(item)
                            if Counter(vars_event) == Counter(varsDeclLines):
                                print("you selected correct vars")
                                self.vars_tracker.setVarsDeclared(item)
                                break

                            self.vars_tracker.setVarsDeclared(item)
                        else:
                            vars_event.append(item)
                            if Counter(vars_event) == Counter(varsDeclLines):
                                print("you selected correct vars")
                                self.event_sender({"message": f"アイテム {item} を正確に取得できました!!", "item": self.vars_tracker.getValueByVar(item), "status": "ok"}, getLine)
                                self.vars_tracker.setVarsDeclared(item)
                                break

                            self.event_sender({"message": f"アイテム {item} を正確に取得できました!!", "item": self.vars_tracker.getValueByVar(item), "undefined": False, "status": "ok"}, False)
                            self.vars_tracker.setVarsDeclared(item)
                    else:
                        errorCnt += 1
                        self.event_sender({"message": "異なる行動をしようとしています1!!", "status": "ng"})
                        event = self.event_reciever()
                        continue

            # vars_changedとvarsTrackerの共通項とvarsDeclLinesの差項を、値が変化した変数として検知する
            # vars_changedにもkeysを使って宣言済みかつ値が変わった変数を取得できる
            common = list(set(self.vars_tracker.vars_changed.keys()) & set(self.vars_tracker.vars_declared[-1]))
            # そして今回宣言された変数以外で値が変わった変数(の一番上の名前)を取得できる
            values_changed = list(set(common) - set(varsDeclLines))
            # その後、varsChangedをキーとしてvars_changedの変更値を取得する
            print(values_changed)

            if len(values_changed) != 0:
                vars_event = []
                errorCnt = 0
                if first_event:
                    event = first_event
                    first_event = None
                else:
                    if (event := self.event_reciever()) is None:
                        return
                while True:
                    # if (itemset := event.get('itemset', None)) is not None:
                    #     item, itemValue = itemset
                    #     if item not in values_changed:
                    #         errorCnt += 1
                    #         print(f'your variables were incorrect!!\ncorrect variables: {values_changed}')
                    #         # 複数回入力を間違えたらヒントをあげる
                    #         if errorCnt >= 3:
                    #             self.event_sender({"message": f"ヒント: アイテム {', '.join(list(set(values_changed) - set(vars_event)))} の値を変えてください!!", "status": "ng"})
                    #         else:
                    #             self.event_sender({"message": f"異なるアイテム {item} の値を変えようとしています!!", "status": "ng"})
                    #         event = self.event_reciever()
                    #         continue
                    #     # ここはitemValueではなくどこの変数を変えようとするかが合致していればOKにする
                    #     if itemValue != self.vars_tracker.getValueByVar(item):
                    #         errorCnt += 1
                    #         print(f'your variable numbers were incorrect!!\ncorrect variables: {values_changed}')
                    #         # 複数回入力を間違えたらヒントをあげる
                    #         if errorCnt >= 3:
                    #             item_values_str = ', '.join(f"{name} は {self.vars_tracker.getValueByVar(name)}" for name in list(set(values_changed) - set(vars_event)))
                    #             self.event_sender({"message": f"ヒント: {item_values_str} に設定しましょう!!", "status": "ng"})
                    #         else:
                    #             self.event_sender({"message": f"アイテムに異なる値 {itemValue} を設定しようとしています!!", "status": "ng"})
                    #         event = self.event_reciever()
                    #         continue
                    #     vars_event.append(item)
                    #     if Counter(vars_event) == Counter(values_changed):
                    #         print("you changed correct vars")
                    #         self.event_sender({"message": f"アイテム {item} の値を {itemValue} で正確に設定できました!!", "status": "ok"}, getLine)
                    #         break
                    #     self.event_sender({"message": f"アイテム {item} の値を {itemValue} で正確に設定できました!!", "status": "ok"}, False)
                    # else:
                    #     errorCnt += 1
                    #     self.event_sender({"message": "異なる行動をしようとしています2!!", "status": "ng"})
                    #     event = self.event_reciever()
                    #     continue
                    
                    if (event.get('itemsetall', False)):
                        value_changed_dict = []
                        for value_changed in values_changed:
                            for value_changed_tuple in self.vars_tracker.vars_changed[value_changed]:
                                value_path = [*value_changed_tuple]
                                isCorrect, value = self.vars_tracker.getValuePartly([value_changed, *value_path])
                                print(isCorrect)
                                value_changed_dict.append({"item": value_changed, "path": value_path, "value": value})
                        self.event_sender({"message": "新しいアイテムの値を設定しました!!", "status": "ok", "values": value_changed_dict}, getLine)
                        break
                    else:
                        errorCnt += 1
                        self.event_sender({"message": "異なる行動をしようとしています2!!", "status": "ng"})
                        event = self.event_reciever()
                        continue

            # 変数が初期化されない時、スキップされるので、それも読み取る
            target_lines = [line for line in self.varsDeclLines_list if self.line_number < int(line) < self.next_line_number]

            if len(target_lines) != 0 and self.line_number not in self.line_data[self.func_name][0]:
                # 変数が合致していればstepinを実行して次に進む
                for line in target_lines:
                    # skipped_varDecls = self.varsDeclLines_list.pop(line)
                    skipped_varDecls = self.varsDeclLines_list[line]
                    vars_event = []
                    errorCnt = 0
                    if first_event:
                        event = first_event
                        first_event = None
                    else:
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
                                event = self.event_reciever()
                                continue
                            
                            vars_event.append(item)
                            if Counter(vars_event) == Counter(skipped_varDecls):
                                print("you selected correct vars")
                                self.event_sender({"message": f"アイテム {item} を正確に取得できました!!", "undefined": True, "item": self.vars_tracker.getValueByVar(item), "status": "ok"}, getLine)
                                self.vars_tracker.setVarsDeclared(item)
                                break
                            self.event_sender({"message": f"アイテム {item} を正確に取得できました!!", "undefined": True, "item": self.vars_tracker.getValueByVar(item), "status": "ok"}, False)
                            self.vars_tracker.setVarsDeclared(item)
                        else:
                            errorCnt += 1
                            self.event_sender({"message": "異なる行動をしようとしています1!!", "status": "ng"})
                            event = self.event_reciever()
                            continue

        def analyze_frame(self, backToLine: int = None):
            def check_condition(condition_type: str, fromTo: list[int], funcWarp):
                errorCnt = 0
                line_number_track: list[int] = fromTo[:2]
                func_num = 0
                while True:
                    # まず、if文でどの行まで辿ったかを確かめる
                    if fromTo[:len(line_number_track)] == line_number_track:
                        crntFromTo = fromTo[len(line_number_track):]
                        if len(funcWarp) < func_num:
                            continue
                        elif len(funcWarp) != 0:
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
                    while crntFromTo:
                        # 何かしらの関数に遷移したとき
                        if self.next_frame_num > self.frame_num:
                            if line_number_track[-1] == self.next_line_number:
                                self.event_sender({"message": f"関数 {self.func_crnt_name} の処理をスキップしますか?", "status": "ok", "skipCond": True})
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
                                        if back_line_number == self.line_number:
                                            break
                                    self.event_sender({"message": "スキップを完了しました", "status": "ok", "items": self.vars_tracker.getValueAll(), "func": self.func_name, "skippedFunc": skipped_func_name, "retVal": retVal})
                                # スキップしない
                                else:
                                    items = {}
                                    func = funcWarp.pop(0)
                                    for argname, argtype in func["args"].items():
                                        items[argname] = {"item": self.vars_tracker.getValueByVar(argname), "type": argtype}
                                    self.event_sender({"message": f"スキップをキャンセルしました。関数 {self.func_crnt_name} に遷移します", "status": "ok", "func": self.func_name, "fromLine": self.line_number, "skipTo": {"name": func["name"], "x": func["x"], "y": func["y"], "items": items}})
                                    back_line_number = self.line_number
                                    self.step_conditionally()
                                    while 1:
                                        if self.analyze_frame(fromTo[0]):
                                            continue
                                        if back_line_number == self.line_number:
                                            break
                                line_number_track.append(self.next_line_number)
                                func_num += 1
                            else:
                                self.event_sender({"message": "ここから先は進入できません10!!", "status": "ng"})
                            event = self.event_reciever()
                            break
                        else:
                            self.step_conditionally(False)

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

                    # crntFromToが 空 => 行番が完全一致になる
                    if not crntFromTo:
                        self.event_sender({"message": "", "status": "ok"})
                        self.vars_tracker.trackStart(self.frame)
                        self.vars_checker()
                        break

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
                            if type in ['if', 'whileTrue', 'whileFalse', 'forTrue', 'forFalse', 'doWhileTrue', 'doWhileFalse']:
                                # 同じメソッドでいけるかを確認する
                                funcWarp = event['funcWarp']
                                check_condition(type, fromTo, funcWarp)
                                if type in ['whileFalse, forFalse', 'doWhileFalse']:
                                    self.line_loop.pop(-1)
                                    skipStart = None
                                    skipEnd = None
                            elif type == 'ifEnd':
                                self.event_sender({"message": "", "status": "ok"})
                            elif type == 'switchCase':
                                if (funcWarps := event.get('funcWarp', None)) is not None:
                                    for funcWarp in funcWarps:
                                        if funcWarp["name"] == self.func_crnt_name and funcWarp["line"] == self.next_line_number:
                                            self.event_sender({"message": "遷移先の関数の処理をスキップしますか?", "status": "ok", "skip": True})
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
                                    self.event_sender({"message": "", "status": "ok"})
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
                                # return内の計算式の確認方法は後で考える
                                retVal = thread.GetStopReturnValue().GetValue()
                                self.step_conditionally()
                                self.get_std_outputs()
                                self.event_sender({"message": f"関数 {self.func_name} に戻ります!!", "status": "ok", "items": self.vars_tracker.getValueAll(), "backToFunc": self.func_name, "backToLine": backToLine, "retVal": retVal})
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
                            print(f"{self.line_number}, {self.next_line_number}")
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
                                        self.step_conditionally()
                                    self.event_sender({"message": "スキップが完了しました", "status": "ok", "type": "doWhile", "items": self.vars_tracker.getValueAll()})
                                else:
                                    self.event_sender({"message": "スキップをキャンセルしました", "status": "ok"})
                            else:
                                self.event_sender({"message": "", "status": "ok"})
                        elif type == 'forIn':
                            print(self.line_loop)
                            if len(self.line_loop) and self.line_loop[-1] == self.line_number:
                                skipStart = self.line_number
                                skipEnd = self.line_data[self.func_name][1][str(self.line_number)]
                                if skipStart <= self.next_line_number <= skipEnd:
                                    # ここでスキップするかどうかを確認する
                                    self.event_sender({"message": "ループを抜ける直前までスキップしますか?", "status": "ok", "skip": True})
                                    event = self.event_reciever()
                                    if event.get('skip', False):
                                        while skipStart <= self.next_line_number <= skipEnd:
                                            self.step_conditionally()
                                        print(self.vars_tracker.vars_removed)
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
                        print(f"correct line numbers are {self.line_number}, {self.next_line_number}")
                        self.event_sender({"message": "ここから先は進入できません7!!", "status": "ng"})
                        return CONTINUE
                else:
                    self.event_sender({"message": "NG行動をしました6!!", "status": "ng"})
                    return CONTINUE

            self.step_conditionally()

            self.get_std_outputs()

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
            if getLine and msgJson["status"] == "ok":
                target_lines = [line for line in self.varsDeclLines_list if self.line_number < int(line) < self.next_line_number]
                # 初期化されていない変数はスキップされてしまうので、そのような変数があるなら最初の行数を取得する
                if len(target_lines) != 0 and self.line_number not in self.line_data[self.func_name][0]:
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
print(target.GetAddressByteSize() * 8)
if not target:
    print("failed in build of target")
    exit(1)

# print(f"Command line arguments: {args}")

# breakpointを行で指定するならByLocation
breakpoint = target.BreakpointCreateByName("main", target.GetExecutable().GetFilename())

for module in target.module_iter():
    for sym in module:
        if sym.GetType() == lldb.eSymbolTypeData:  # データシンボル（変数）
            name = sym.GetName()
            if name:
                var = target.FindFirstGlobalVariable(name)
                if var.IsValid():
                    print(f"{name} = {var.GetValue()}")

launch_info = lldb.SBLaunchInfo([])
launch_info.SetWorkingDirectory(os.getcwd())

error = lldb.SBError()
process = target.Launch(launch_info, error)

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
    print("[サーバ終了]")
# endregion