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

class VarsTracker:
    def __init__(self):
        self.previous_values: list[dict[str, str]] = []
        self.vars_declared: list[list[str]] = []
        self.vars_removed = []
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
        
        return self.track(frame.GetVariables(True, True, False, True))

    def track(self, vars, depth=0, max_depth=10, prefix="") -> list[str]:
        vars_changed = []
        crnt_vars = []

        if depth > max_depth:
            return []
        
        indent = "    " * depth

        for var in vars:
            name = var.GetName()
            full_name = f"{prefix}.{name}" if prefix else name
            value = var.GetValue()

            prev_value = self.previous_values[-1].get(full_name)

            if value != prev_value:
                print(f"{indent}{full_name} = {value}    ← changed")
                vars_changed.append(full_name)
            else:
                print(f"{indent}{full_name} = {value}")

            if depth == 0: # スコープから外れて消える変数を検知するため、次の変数を確認するために現在の変数を取得する
                crnt_vars.append(name)

            self.previous_values[-1][full_name] = value

            num_children = var.GetNumChildren()
            
            if var.GetType().IsPointerType():
                pointee_type = var.GetType().GetPointeeType()
                type_name = pointee_type.GetName()

                try:
                    addr = int(var.GetValue(), 16)
                    target = var.GetTarget()
                    process = target.GetProcess()
                    error = lldb.SBError()

                    if not pointee_type.IsPointerType():
                        if type_name == "char":
                            cstr = process.ReadCStringFromMemory(addr, 100, error)
                            if error.Success():
                                print(f"{indent}→ {full_name} points to string: \"{cstr}\"")
                            else:
                                print(f"{indent}→ {full_name} points to unreadable char*")

                        elif type_name == "int":
                            data = process.ReadMemory(addr, 4, error)
                            if error.Success():
                                val = struct.unpack("i", data)[0]
                                print(f"{indent}→ {full_name} points to int: {val}")
                            else:
                                print(f"{indent}→ {full_name} points to unreadable int*")

                        elif type_name == "float":
                            data = process.ReadMemory(addr, 4, error)
                            if error.Success():
                                val = struct.unpack("f", data)[0]
                                print(f"{indent}→ {full_name} points to float: {val}")
                            else:
                                print(f"{indent}→ {full_name} points to unreadable float*")

                        elif type_name == "double":
                            data = process.ReadMemory(addr, 8, error)
                            if error.Success():
                                val = struct.unpack("d", data)[0]
                                print(f"{indent}→ {full_name} points to double: {val}")
                            else:
                                print(f"{indent}→ {full_name} points to unreadable double*")

                        else:
                            # 構造体などの場合
                            deref = var.Dereference()
                            if deref.IsValid() and deref.GetNumChildren() > 0:
                                print(f"{indent}→ Deref {full_name}")
                                children = [deref.GetChildAtIndex(i) for i in range(deref.GetNumChildren())]
                                vars_changed += self.track(children, depth + 1, max_depth, full_name)
                    else:
                        children = [var.GetChildAtIndex(i) for i in range(num_children)]
                        vars_changed += self.track(children, depth + 1, max_depth, full_name)

                except Exception as e:
                    print(f"{indent}→ {full_name} deref error: {e}")

            elif num_children > 0: # 配列?
                children = [var.GetChildAtIndex(i) for i in range(num_children)]
                vars_changed += self.track(children, depth + 1, max_depth, full_name)

        if depth == 0:
            if len(self.vars_declared) != 0:
                self.vars_removed = list(set(self.vars_declared[-1]) - set(crnt_vars))

        return vars_changed
    
    # def setValue(self, )
    
    def getValue(self, varname):
        return self.previous_values[-1][varname]
    
    def getValueBeforeFuncWarp(self, varname):
        return self.previous_values[-2][varname]
    
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

    def event_reciever():
        # JSONが複数回に分かれて送られてくる可能性があるためパース
        data = conn.recv(1024)
        # ここは後々変えるかも
        if not data:
            return None
        buffer = data.decode()
        event = json.loads(buffer)
        print(f"[受信イベント] {event}")
        return event
    
    def event_sender(msgJson, getLine=True):
        if getLine and msgJson["status"] == "ok":
            target_lines = [line for line in varsDeclLines_list if line_number < int(line) < next_line_number]
            # 初期化されていない変数はスキップされてしまうので、そのような変数があるなら最初の行数を取得する
            if len(target_lines) != 0 and line_number not in line_data[func_name][0]:
                msgJson["line"] = int(target_lines[0])
            else:
                msgJson["line"] = next_line_number
                msgJson["removed"] = varsTracker.vars_removed
        send_data = json.dumps(msgJson)
        conn.sendall(send_data.encode('utf-8'))

    def step_conditionally(frame):
        # プロセスの状態を更新
        if isEnd:
            while True:
                if (event := event_reciever()) is None:
                    continue
                if (retValue := event.get('return', None)) is not None:
                    event_sender({"message": "おめでとうございます!! ここがゴールです!!", "status": "ok", "finished": True})
                    print("プログラムは正常に終了しました")
                    raise ProgramFinished()
                else:
                    event_sender({"message": "NG行動をしました1!!", "status": "ng"})

        thread = frame.GetThread()
        process = thread.GetProcess()
        target = process.GetTarget()

        # 現在の命令アドレス
        pc_addr = frame.GetPCAddress()

        # 現在の命令を取得（必要な数だけ、ここでは1つ）
        instructions = target.ReadInstructions(pc_addr, 1)

        inst = instructions[0]
        
        mnemonic = inst.GetMnemonic(target)

        print(f"Next instruction: {mnemonic} {inst.GetOperands(target)}")
        
        # とりあえず現在はvoid型の関数も扱わないし、戻り値の計算式に関数が含まれるものはないので、
        # func_crnt_nameの最終行とnext_line_numberが合致するかを確認して、合致していればstepOutする。
        # つまり、line_numberがreturn文の行の時に戻り値を取得できる
        # そのうち、returnの場所を予め取得して参照するようにする
        if line_data[func_crnt_name][0][-1] == next_line_number:
            thread.StepOut()
        else:
            thread.StepInto()

    def get_next_state():
        state = process.GetState()

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

    def get_std_outputs():
        stdout_output, stderr_output = get_all_stdvalue(process)
        if stdout_output:
            print("[STDOUT]")
            print(stdout_output)

        if stderr_output:
            print("[STDERR]")
            print(stderr_output)

    def vars_checker(first_event=None):
        nonlocal state, next_state, frame, file_name, line_number, next_line_number, func_name, func_crnt_name, vars_changed, frame_num, next_frame_num, isEnd
        if isEnd:
            return
        
        varsDeclLines = list(set(varsDeclLines_list.pop(str(line_number), [])) - set(varsTracker.vars_declared[-1]))
        getLine = (first_event is None)

        if len(varsDeclLines) != 0:
            # 変数が合致していればstepinを実行して次に進む
            vars_event = []
            errorCnt = 0 
            if first_event:
                event = first_event
                first_event = None
            else:
                if (event := event_reciever()) is None:
                    return
            while True:
                if (item := event.get('item', None)) is not None:
                    if not item in varsDeclLines:
                        errorCnt += 1
                        print(f'your variables were incorrect!!\ncorrect variables: {varsDeclLines}')
                        # 複数回入力を間違えたらヒントをあげる
                        if errorCnt >= 3:
                            event_sender({"message": f"ヒント: アイテム {', '.join(list(set(varsDeclLines) - set(vars_event)))} を取得してください!!", "status": "ng"})
                        else:
                            event_sender({"message": f"異なるアイテム {item} を取得しようとしています!!", "status": "ng"})
                        event = event_reciever()
                        continue
                    
                    funcWarps = event['funcWarp']
                    if len(funcWarps) != 0:
                        for funcWarp in funcWarps:
                            if funcWarp["name"] == func_crnt_name and funcWarp["line"] == next_line_number:
                                event_sender({"message": "遷移先の関数の処理をスキップしますか?", "value": varsTracker.getValueBeforeFuncWarp(item), "undefined": True, "status": "ok", "skip": True})
                                event = event_reciever()
                                if event.get('skip', False):
                                    back_line_number = line_number
                                    while 1:
                                        step_conditionally(frame)
                                        if (next_state := get_next_state()):
                                            line_number = next_line_number
                                            func_name = func_crnt_name
                                            frame_num = next_frame_num
                                            state, frame, file_name, next_line_number, func_crnt_name, next_frame_num = next_state
                                            vars_changed = varsTracker.trackStart(frame)
                                        else:
                                            isEnd = True
                                            line_number = next_line_number
                                        if back_line_number == line_number:
                                            break
                                    event_sender({"message": "スキップが完了しました", "status": "ok", "items": varsTracker.previous_values[-1]})
                                else:
                                    items = {}
                                    for argname, argtype in funcWarp["args"].items():
                                        items[argname] = {"value": varsTracker.getValue(argname), "type": argtype}
                                    event_sender({"message": f"スキップをキャンセルしました。関数 {func_crnt_name} に遷移します", "status": "ok", "fromLine": line_number, "skipTo": {"name": funcWarp["name"], "x": funcWarp["x"], "y": funcWarp["y"], "items": items}})
                                    back_line_number = line_number
                                    while 1:
                                        if analyze_frame():
                                            continue
                                        if back_line_number == line_number:
                                            break
                        vars_event.append(item)
                        if Counter(vars_event) == Counter(varsDeclLines):
                            print("you selected correct vars")
                            varsTracker.setVarsDeclared(item)
                            break

                        varsTracker.setVarsDeclared(item)
                    else:
                        vars_event.append(item)
                        if Counter(vars_event) == Counter(varsDeclLines):
                            print("you selected correct vars")
                            event_sender({"message": f"アイテム {item} を正確に取得できました!!", "value": varsTracker.getValue(item), "undefined": False, "status": "ok"}, getLine)
                            varsTracker.setVarsDeclared(item)
                            break

                        event_sender({"message": f"アイテム {item} を正確に取得できました!!", "value": varsTracker.getValue(item), "undefined": False, "status": "ok"}, False)
                        varsTracker.setVarsDeclared(item)
                else:
                    errorCnt += 1
                    event_sender({"message": "異なる行動をしようとしています1!!", "status": "ng"})
                    event = event_reciever()
                    continue

        # vars_changedとvarsTrackerの共通項とvarsDeclLinesの差項を、値が変化した変数として検知する
        common = list(set(vars_changed) & set(varsTracker.vars_declared[-1]))
        varsChanged = list(set(common) - set(varsDeclLines))

        if len(varsChanged) != 0:
            vars_event = []
            errorCnt = 0
            if first_event:
                event = first_event
                first_event = None
            else:
                if (event := event_reciever()) is None:
                    return
            while True:
                if (itemset := event.get('itemset', None)) is not None:
                    item, itemValue = itemset
                    if item not in varsChanged:
                        errorCnt += 1
                        print(f'your variables were incorrect!!\ncorrect variables: {varsChanged}')
                        # 複数回入力を間違えたらヒントをあげる
                        if errorCnt >= 3:
                            event_sender({"message": f"ヒント: アイテム {', '.join(list(set(varsChanged) - set(vars_event)))} の値を変えてください!!", "status": "ng"})
                        else:
                            event_sender({"message": f"異なるアイテム {item} の値を変えようとしています!!", "status": "ng"})
                        event = event_reciever()
                        continue
                    if itemValue != varsTracker.getValue(item):
                        errorCnt += 1
                        print(f'your variable numbers were incorrect!!\ncorrect variables: {varsChanged}')
                        # 複数回入力を間違えたらヒントをあげる
                        if errorCnt >= 3:
                            item_values_str = ', '.join(f"{name} は {varsTracker.getValue(name)}" for name in list(set(varsChanged) - set(vars_event)))
                            event_sender({"message": f"ヒント: {item_values_str} に設定しましょう!!", "status": "ng"})
                        else:
                            event_sender({"message": f"アイテムに異なる値 {itemValue} を設定しようとしています!!", "status": "ng"})
                        event = event_reciever()
                        continue
                    vars_event.append(item)
                    if Counter(vars_event) == Counter(varsChanged):
                        print("you changed correct vars")
                        event_sender({"message": f"アイテム {item} の値を {itemValue} で正確に設定できました!!", "status": "ok"}, getLine)
                        break
                    event_sender({"message": f"アイテム {item} の値を {itemValue} で正確に設定できました!!", "status": "ok"}, False)
                else:
                    errorCnt += 1
                    event_sender({"message": "異なる行動をしようとしています2!!", "status": "ng"})
                    event = event_reciever()
                    continue

        # 変数が初期化されない時、スキップされるので、それも読み取る
        target_lines = [line for line in varsDeclLines_list if line_number < int(line) < next_line_number]

        if len(target_lines) != 0 and line_number not in line_data[func_name][0]:
            # 変数が合致していればstepinを実行して次に進む
            for line in target_lines:
                skipped_varDecls = varsDeclLines_list.pop(line)
                vars_event = []
                errorCnt = 0
                if first_event:
                    event = first_event
                    first_event = None
                else:
                    if (event := event_reciever()) is None:
                        return
                while True:
                    if (item := event.get('item', None)) is not None:
                        if not item in skipped_varDecls:
                            errorCnt += 1
                            print(f'your variables were incorrect!!\ncorrect variables: {skipped_varDecls}')
                            # 複数回入力を間違えたらヒントをあげる
                            if errorCnt >= 3:
                                event_sender({"message": f"ヒント: アイテム {', '.join(list(set(skipped_varDecls) - set(vars_event)))} を取得してください!!", "status": "ng"})
                            else:
                                event_sender({"message": f"異なるアイテム {item} を取得しようとしています!!", "status": "ng"})
                            event = event_reciever()
                            continue
                        
                        vars_event.append(item)
                        if Counter(vars_event) == Counter(skipped_varDecls):
                            print("you selected correct vars")
                            event_sender({"message": f"アイテム {item} を正確に取得できました!!", "value": varsTracker.getValue(item), "undefined": True, "status": "ok"}, getLine)
                            varsTracker.setVarsDeclared(item)
                            break
                        event_sender({"message": f"アイテム {item} を正確に取得できました!!", "value": varsTracker.getValue(item), "undefined": True, "status": "ok"}, False)
                        varsTracker.setVarsDeclared(item)
                    else:
                        errorCnt += 1
                        event_sender({"message": "異なる行動をしようとしています1!!", "status": "ng"})
                        event = event_reciever()
                        continue

    def analyze_frame(backToLine: int = None):
        def check_condition(condition_type: str, fromTo: list[int], funcWarp):
            nonlocal state, next_state, frame, file_name, line_number, next_line_number, func_name, func_crnt_name, vars_changed, skipStart, skipEnd, line_data, frame_num, next_frame_num, isEnd
            print('here2')
            errorCnt = 0
            line_number_track: list[int] = fromTo[:2]
            func_num = 0
            while True:
                # まず、if文でどの行まで辿ったかを確かめる
                if fromTo[:len(line_number_track)] == line_number_track:
                    crntFromTo = fromTo[len(line_number_track):]
                    print('here')
                    if len(funcWarp) < func_num:
                        continue
                    elif len(funcWarp) != 0:
                        funcWarp = funcWarp[func_num:]
                    print('here1')
                # もし、fromToと今まで辿った行が部分一致しなければ新たな通信を待つ
                else:
                    errorCnt += 1
                    event_sender({"message": f"ここから先は進入できません2!! {f"ヒント: {condition_type} 条件を見ましょう!!" if errorCnt >= 3 else ""}", "status": "ng"})
                    while True:
                        if (event := event_reciever()) is None:
                            break
                        if (type := event.get('type', '')) != condition_type:
                            errorCnt += 1
                            event_sender({"message": f"NG行動をしました!! {f"ヒント: {condition_type} 条件を見ましょう!!" if errorCnt >= 3 else ""}", "status": "ng"})
                        elif (fromTo := event.get('fromTo', None)) is None:
                            errorCnt += 1
                            event_sender({"message": f"NG行動をしました!! {f"ヒント: {condition_type} 条件を見ましょう!!" if errorCnt >= 3 else ""}", "status": "ng"})
                        elif (funcWarp := event.get('funcWarp', None)) is None:
                            errorCnt += 1
                            event_sender({"message": f"NG行動をしました!! {f"ヒント: {condition_type} 条件を見ましょう!!" if errorCnt >= 3 else ""}", "status": "ng"})
                        else:
                            break
                    continue
                # 全ての行数が合致していたらif文の開始の正誤の分析を終了する
                while crntFromTo:
                    # 何かしらの関数に遷移したとき
                    if next_frame_num > frame_num:
                        if line_number_track[-1] == next_line_number:
                            event_sender({"message": f"関数 {func_crnt_name} の処理をスキップしますか?", "status": "ok", "skipCond": True})
                            event = event_reciever()
                            # スキップする
                            if event.get('skip', False):
                                retVal = None
                                back_line_number = line_number
                                skipped_func_name = func_crnt_name
                                while 1:
                                    step_conditionally(frame)
                                    if (next_state := get_next_state()):
                                        line_number = next_line_number
                                        func_name = func_crnt_name
                                        frame_num = next_frame_num
                                        state, frame, file_name, next_line_number, func_crnt_name, next_frame_num = next_state
                                        vars_changed = varsTracker.trackStart(frame)
                                    else:
                                        isEnd = True
                                        line_number = next_line_number
                                    if back_line_number == next_line_number:
                                        retVal = thread.GetStopReturnValue().GetValue()
                                    if back_line_number == line_number:
                                        break
                                event_sender({"message": "スキップを完了しました", "status": "ok", "items": varsTracker.previous_values[-1], "func": func_name, "skippedFunc": skipped_func_name, "retVal": retVal})
                            # スキップしない
                            else:
                                items = {}
                                func = funcWarp.pop(0)
                                for argname, argtype in func["args"].items():
                                    items[argname] = {"value": varsTracker.getValue(argname), "type": argtype}
                                event_sender({"message": f"スキップをキャンセルしました。関数 {func_crnt_name} に遷移します", "status": "ok", "func": func_name, "fromLine": line_number, "skipTo": {"name": func["name"], "x": func["x"], "y": func["y"], "items": items}})
                                back_line_number = line_number
                                step_conditionally(frame)
                                if (next_state := get_next_state()):
                                    line_number = next_line_number
                                    func_name = func_crnt_name
                                    frame_num = next_frame_num
                                    state, frame, file_name, next_line_number, func_crnt_name, next_frame_num = next_state
                                    vars_changed = varsTracker.trackStart(frame)
                                else:
                                    isEnd = True
                                    line_number = next_line_number
                                while 1:
                                    if analyze_frame(fromTo[0]):
                                        continue
                                    if back_line_number == line_number:
                                        break
                            line_number_track.append(next_line_number)
                            func_num += 1
                        else:
                            event_sender({"message": "ここから先は進入できません10!!", "status": "ng"})
                        event = event_reciever()
                        break
                    else:
                        step_conditionally(frame)

                        if (next_state := get_next_state()):
                            line_number = next_line_number
                            func_name = func_crnt_name
                            frame_num = next_frame_num
                            state, frame, file_name, next_line_number, func_crnt_name, next_frame_num = next_state
                        else:
                            isEnd = True
                            line_number = next_line_number

                        if crntFromTo[0] != next_line_number:
                            errorCnt += 1
                            event_sender({"message": f"ここから先は進入できません3!! {f"ヒント: {condition_type} 条件を見ましょう!!" if errorCnt >= 3 else ""}", "status": "ng"})
                            while True:
                                if (event := event_reciever()) is None:
                                    continue
                                if (type := event.get('type', '')) != condition_type:
                                    errorCnt += 1
                                    event_sender({"message": f"NG行動をしました!! {f"ヒント: {condition_type} 条件を見ましょう!!" if errorCnt >= 3 else ""}", "status": "ng"})
                                elif (fromTo := event.get('fromTo', None)) is None:
                                    errorCnt += 1
                                    event_sender({"message": f"NG行動をしました!! {f"ヒント: {condition_type} 条件を見ましょう!!" if errorCnt >= 3 else ""}", "status": "ng"})
                                else:
                                    break
                            line_number_track.append(next_line_number)
                            break
                        line_number_track.append(crntFromTo.pop(0))

                # crntFromToが 空 => 行番が完全一致になる
                if not crntFromTo:
                    print('here5')
                    event_sender({"message": "", "status": "ok"})
                    vars_changed = varsTracker.trackStart(frame)
                    print('here4')
                    vars_checker()
                    print('here3')
                    break

        nonlocal state, next_state, frame, file_name, line_number, next_line_number, func_name, func_crnt_name, vars_changed, skipStart, skipEnd, line_data, frame_num, next_frame_num, isEnd
        if line_data.get(func_name, None) and line_number in line_data[func_name][0] and not isEnd:
            if (event := event_reciever()) is None:
                return PROGRESS
            if (ngname := event.get('ng', None)) is not None:
                if ngname == "notEnter":
                    event_sender({"message": "ここから先は進入できません1!!", "status": "ng"})
                else:
                    event_sender({"message": "NG行動をしました2!!", "status": "ng"})
                return CONTINUE
            elif (fromTo := event.get('fromTo', None)) is not None:
                type = event.get('type', '')
                # そもそも最初の行番が合致していなければ下のwhile Trueに入る前にカットする必要がある
                # こうしないとどこのエリアに行っても条件構文に関する受信待ちが永遠に続いてしまう
                if len(fromTo) >= 2:
                    if fromTo[:2] == [line_number, next_line_number]:
                        if type in ['if', 'whileTrue', 'whileFalse', 'forTrue', 'forFalse', 'doWhileTrue', 'doWhileFalse']:
                            # 同じメソッドでいけるかを確認する
                            funcWarp = event['funcWarp']
                            check_condition(type, fromTo, funcWarp)
                            if type in ['whileFalse, forFalse', 'doWhileFalse']:
                                line_loop.pop(-1)
                                skipStart = None
                                skipEnd = None
                        elif type == 'ifEnd':
                            event_sender({"message": "", "status": "ok"})
                        elif type == 'switchCase':
                            if (funcWarps := event.get('funcWarp', None)) is not None:
                                for funcWarp in funcWarps:
                                    if funcWarp["name"] == func_crnt_name and funcWarp["line"] == next_line_number:
                                        event_sender({"message": "遷移先の関数の処理をスキップしますか?", "status": "ok", "skip": True})
                                        event = event_reciever()
                                        if event.get('skip', False):
                                            back_line_number = line_number
                                            while 1:
                                                step_conditionally(frame)
                                                if (next_state := get_next_state()):
                                                    line_number = next_line_number
                                                    func_name = func_crnt_name
                                                    frame_num = next_frame_num
                                                    state, frame, file_name, next_line_number, func_crnt_name, next_frame_num = next_state
                                                    vars_changed = varsTracker.trackStart(frame)
                                                else:
                                                    isEnd = True
                                                    line_number = next_line_number
                                                if back_line_number == line_number:
                                                    break
                                            event_sender({"message": "スキップが完了しました", "status": "ok", "items": varsTracker.previous_values[-1]})
                                        else:
                                            items = {}
                                            for argname, argtype in funcWarp["args"].items():
                                                items[argname] = {"value": varsTracker.getValue(argname), "type": argtype}
                                            event_sender({"message": f"スキップをキャンセルしました。関数 {func_crnt_name} に遷移します", "status": "ok", "fromLine": line_number, "skipTo": {"name": funcWarp["name"], "x": funcWarp["x"], "y": funcWarp["y"], "items": items}})
                                            back_line_number = line_number
                                            while 1:
                                                if analyze_frame():
                                                    continue
                                                if back_line_number == line_number:
                                                    break
                            else:
                                event_sender({"message": "", "status": "ok"})
                                vars_changed = varsTracker.trackStart(frame)
                                vars_checker()
                        elif type == 'continue':
                            # type == while or forの場合
                            if line_number >= next_line_number:
                                skipStart = next_line_number
                                skipEnd = line_data[func_name][1][str(next_line_number)]
                                # ここでスキップするかどうかを確認する
                                event_sender({"message": "ループを抜ける直前までスキップしますか?", "status": "ok", "skip": True})
                                event = event_reciever()
                                if event.get('skip', False):
                                    while skipStart <= next_line_number <= skipEnd:
                                        step_conditionally(frame)
                                        if (next_state := get_next_state()):
                                            line_number = next_line_number
                                            func_name = func_crnt_name
                                            frame_num = next_frame_num
                                            state, frame, file_name, next_line_number, func_crnt_name, next_frame_num = next_state
                                            vars_changed = varsTracker.trackStart(frame)
                                        else:
                                            isEnd = True
                                            line_number = next_line_number
                                    event_sender({"message": "スキップが完了しました", "status": "ok", "items": varsTracker.previous_values[-1]})
                                    return CONTINUE
                                else:
                                    event_sender({"message": "スキップをキャンセルしました", "status": "ok"})
                            # type == do_whileの場合
                            else:
                                # まずは条件文に行って次がTrueかFalseかを見る
                                step_conditionally(frame)
                                if (next_state := get_next_state()):
                                    line_number = next_line_number
                                    func_name = func_crnt_name
                                    frame_num = next_frame_num
                                    state, frame, file_name, next_line_number, func_crnt_name, next_frame_num = next_state
                                    vars_changed = varsTracker.trackStart(frame)
                                else:
                                    isEnd = True
                                    line_number = next_line_number
                                # 次がdoWhileTrueと考えられるならスキップを提案する
                                if line_data[func_name][1][str(line_number)] <= next_line_number <= line_number:
                                    skipStart = line_number
                                    skipEnd = line_data[func_name][1][str(line_number)]
                                    # ここでスキップするかどうかを確認する
                                    event_sender({"message": "ループを抜ける直前までスキップしますか?", "status": "ok", "skip": True})
                                    event = event_reciever()
                                    if event.get('skip', False):
                                        while skipStart <= next_line_number <= skipEnd:
                                            step_conditionally(frame)
                                            if (next_state := get_next_state()):
                                                line_number = next_line_number
                                                func_name = func_crnt_name
                                                frame_num = next_frame_num
                                                state, frame, file_name, next_line_number, func_crnt_name, next_frame_num = next_state
                                                vars_changed = varsTracker.trackStart(frame)
                                            else:
                                                isEnd = True
                                                line_number = next_line_number
                                        event_sender({"message": "スキップが完了しました", "status": "ok", "items": varsTracker.previous_values[-1]})
                                    else:
                                        event_sender({"message": "スキップをキャンセルしました", "status": "ok"})
                                else:
                                    event_sender({"message": "", "status": "ok"})
                                return CONTINUE
                        elif type == 'break':
                            event_sender({"message": "", "status": "ok"})
                            line_loop.pop(-1)
                            skipEnd = None
                        elif type == 'return':
                            # return内の計算式の確認方法は後で考える
                            retVal = thread.GetStopReturnValue().GetValue()
                            step_conditionally(frame)
                            if (next_state := get_next_state()):
                                line_number = next_line_number
                                func_name = func_crnt_name
                                frame_num = next_frame_num
                                state, frame, file_name, next_line_number, func_crnt_name, next_frame_num = next_state
                            else:
                                isEnd = True
                                line_number = next_line_number
                            vars_changed = varsTracker.trackStart(frame)
                            get_std_outputs()
                            event_sender({"message": f"関数 {func_name} に戻ります!!", "status": "ok", "items": varsTracker.previous_values[-1], "backToFunc": func_name, "backToLine": backToLine, "retVal": retVal})
                            return PROGRESS
                        else:
                            event_sender({"message": "ここから先は進入できません4!!", "status": "ng"})
                            return CONTINUE
# region do while
# if len(line_loop) == 0 or line_loop[-1] != next_line_number:
#     line_loop.append(next_line_number)
# if (funcWarps := event.get('funcWarp', None)) is not None:
#     for funcWarp in funcWarps:
#         if funcWarp["name"] == func_crnt_name and funcWarp["line"] == next_line_number:
#             event_sender({"message": "遷移先の関数の処理をスキップしますか?", "status": "ok", "skipCond": True})
#             event = event_reciever()
#             if event.get('skip', False):
#                 back_line_number = line_number
#                 while 1:
#                     step_conditionally(frame)
#                     if (next_state := get_next_state()):
#                         line_number = next_line_number
#                         func_name = func_crnt_name
#                         frame_num = next_frame_num
#                         state, frame, file_name, next_line_number, func_crnt_name, next_frame_num = next_state
#                         vars_changed = varsTracker.trackStart(frame)
#                     else:
#                         isEnd = True
#                         line_number = next_line_number
#                     if back_line_number == line_number:
#                         break
#                 event_sender({"message": "スキップが完了しました", "status": "ok", "items": varsTracker.previous_values[-1]})
#             else:
#                 items = {}
#                 for argname, argtype in funcWarp["args"].items():
#                     items[argname] = {"value": varsTracker.getValue(argname), "type": argtype}
#                 event_sender({"message": f"スキップをキャンセルしました。関数 {func_crnt_name} に遷移します", "status": "ok", "fromLine": line_number, "skipTo": {"name": funcWarp["name"], "x": funcWarp["x"], "y": funcWarp["y"], "items": items}})
#                 back_line_number = line_number
#                 while 1:
#                     if analyze_frame():
#                         continue
#                     if back_line_number == line_number:
#                         break
# else:
#     event_sender({"message": "", "status": "ok"})
#     vars_changed = varsTracker.trackStart(frame)
#     vars_checker()
# endregion
                    elif fromTo[:2] == [None, next_line_number]:
                        if type == 'doWhileInit':
                            # 最初なので確定でline_loopに追加する
                            line_loop.append(next_line_number)
                            event_sender({"message": "", "status": "ok"})
                            vars_changed = varsTracker.trackStart(frame)
                            vars_checker()
                        elif type == 'switchEnd':
                            event_sender({"message": "", "status": "ok"})
                    else:
                        print(f"{line_number}, {next_line_number}")
                        event_sender({"message": "ここから先は進入できません5!!", "status": "ng"})
                        return CONTINUE            
                elif len(fromTo) == 1 and fromTo == [line_number]:
                    if type == 'whileIn':
                        if len(line_loop) and line_loop[-1] == line_number:
                            skipStart = line_number
                            skipEnd = line_data[func_name][1][str(line_number)]
                            if skipStart <= next_line_number <= skipEnd:
                                # ここでスキップするかどうかを確認する
                                event_sender({"message": "ループを抜ける直前までスキップしますか?", "status": "ok", "skip": True})
                                event = event_reciever()
                                if event.get('skip', False):
                                    while skipStart <= next_line_number <= skipEnd:
                                        step_conditionally(frame)
                                        if (next_state := get_next_state()):
                                            line_number = next_line_number
                                            func_name = func_crnt_name
                                            frame_num = next_frame_num
                                            state, frame, file_name, next_line_number, func_crnt_name, next_frame_num = next_state
                                            vars_changed = varsTracker.trackStart(frame)
                                        else:
                                            isEnd = True
                                            line_number = next_line_number
                                    event_sender({"message": "スキップが完了しました", "status": "ok", "type": "while", "items": varsTracker.previous_values[-1]})
                                else:
                                    event_sender({"message": "スキップをキャンセルしました", "status": "ok"})
                            else:
                                event_sender({"message": "", "status": "ok"})
                        else:
                            event_sender({"message": "", "status": "ok"})
                            line_loop.append(line_number)
                    elif type == 'doWhileIn':
                        if len(line_loop) and line_loop[-1] == next_line_number:
                            # ここでスキップするかどうを確認する
                            skipStart = line_data[func_name][1][str(line_number)]
                            skipEnd = line_number
                            event_sender({"message": "ループを抜ける直前までスキップしますか?", "status": "ok", "skip": True})
                            event = event_reciever()
                            if event.get('skip', False):
                                while skipStart <= next_line_number <= skipEnd:
                                    step_conditionally(frame)
                                    if (next_state := get_next_state()):
                                        line_number = next_line_number
                                        func_name = func_crnt_name
                                        frame_num = next_frame_num
                                        state, frame, file_name, next_line_number, func_crnt_name, next_frame_num = next_state
                                        vars_changed = varsTracker.trackStart(frame)
                                    else:
                                        isEnd = True
                                        line_number = next_line_number
                                event_sender({"message": "スキップが完了しました", "status": "ok", "type": "doWhile", "items": varsTracker.previous_values[-1]})
                            else:
                                event_sender({"message": "スキップをキャンセルしました", "status": "ok"})
                        else:
                            event_sender({"message": "", "status": "ok"})
                    elif type == 'forIn':
                        if str(line_number) not in varsDeclLines_list:
                            if len(line_loop) and line_loop[-1] == line_number:
                                skipStart = line_number
                                skipEnd = line_data[func_name][1][str(line_number)]
                                if skipStart <= next_line_number <= skipEnd:
                                    # ここでスキップするかどうかを確認する
                                    event_sender({"message": "ループを抜ける直前までスキップしますか?", "status": "ok", "skip": True})
                                    event = event_reciever()
                                    if event.get('skip', False):
                                        while skipStart <= next_line_number <= skipEnd:
                                            step_conditionally(frame)
                                            if (next_state := get_next_state()):
                                                line_number = next_line_number
                                                func_name = func_crnt_name
                                                frame_num = next_frame_num
                                                state, frame, file_name, next_line_number, func_crnt_name, next_frame_num = next_state
                                                vars_changed = varsTracker.trackStart(frame)
                                            else:
                                                isEnd = True
                                                line_number = next_line_number
                                        event_sender({"message": "スキップが完了しました", "status": "ok", "type": "for", "items": varsTracker.previous_values[-1]})
                                    else:
                                        event_sender({"message": "スキップをキャンセルしました", "status": "ok"})
                                else:
                                    event_sender({"message": "", "status": "ok"})
                            else:
                                event_sender({"message": "", "status": "ok"})
                                line_loop.append(line_number)
                        else:
                            event_sender({"message": "ある変数の初期化がされていません!!", "status": "ng"})
                    else:
                        event_sender({"message": "ここから先は進入できません6!!", "status": "ng"})
                    return CONTINUE
                else:
                    print(f"correct line numbers are {line_number}, {next_line_number}")
                    event_sender({"message": "ここから先は進入できません7!!", "status": "ng"})
                    return CONTINUE
            else:
                event_sender({"message": "NG行動をしました6!!", "status": "ng"})
                return CONTINUE

        step_conditionally(frame)

        if (next_state := get_next_state()):
            line_number = next_line_number
            func_name = func_crnt_name
            frame_num = next_frame_num
            state, frame, file_name, next_line_number, func_crnt_name, next_frame_num = next_state
        else:
            isEnd = True
            line_number = next_line_number

        vars_changed = varsTracker.trackStart(frame)

        get_std_outputs()

        # 変数は前回の処理で変更されていたら見る
        vars_checker()

        return PROGRESS

    try:
        print(f"[接続] {addr} が接続しました")

        func_crnt_name = "main"

        varsTracker = VarsTracker()
            
        with conn:
            isEnd = False

            if (next_state := get_next_state()):
                state, frame, file_name, next_line_number, func_crnt_name, next_frame_num = next_state
                with open(f"{DATA_DIR}/{file_name[:-2]}/{file_name[:-2]}_line.json", 'r') as f:
                    line_data = json.load(f)
                    func_name = func_crnt_name
                    frame_num = 1
                    event_sender({"line": line_data[func_name][2]}, False)
                    line_number = line_data[func_name][2] - 1
                with open(f"{DATA_DIR}/{file_name[:-2]}/{file_name[:-2]}_varDeclLines.json", 'r') as f:
                    varsDeclLines_list = json.load(f)
            else:
                event_sender({"end": True})
                isEnd = True
                line_number = line_data["main"][2]

            vars_changed = varsTracker.trackStart(frame)
            vars_checker()

            line_loop = []
            skipStart = None
            skipEnd = None

            # 変数は次の行での値を見て考える(まず変数チェッカーで次の行に進み変数の更新を確認) => その行と前の行で構文や関数は比較する(構文内の行の移動及び関数の移動は次の行と前の行が共に必要)
            while process.GetState() == lldb.eStateStopped:
                analyze_frame()
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