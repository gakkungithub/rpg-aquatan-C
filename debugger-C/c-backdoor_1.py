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

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = BASE_DIR + '/data'

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

class VarsTracker:
    def __init__(self):
        self.previous_values = {}
        self.vars_declared = []
    
    def trackStart(self, frame):
        return self.track(frame.GetVariables(True, True, False, True))

    def track(self, vars, depth=0, max_depth=10, prefix="") -> list[str]:
        vars_changed = []

        if depth > max_depth:
            return []
        
        indent = "    " * depth
        for var in vars:
            name = var.GetName()
            full_name = f"{prefix}.{name}" if prefix else name
            value = var.GetValue()

            prev_value = self.previous_values.get(full_name)
            changed = (value != prev_value)

            if changed:
                print(f"{indent}{full_name} = {value}    ← changed")
                vars_changed.append(full_name)
            else:
                print(f"{indent}{full_name} = {value}")

            self.previous_values[full_name] = value

            num_children = var.GetNumChildren()
            # region commandline
            # print(var.GetType().GetName() + str(var.GetType().IsPointerType()))

            # コマンドライン引数の名前をフローチャートを使って解明できるならここを使ってコマンドライン引数を取得
            # コマンドライン引数は定数なので、精査する必要はない
            # if argv_name == name:
            #     try:
            #         argc_val = int(var.GetValue())
            #         argv_addr = int(var.GetValue(), 16)

            #         for i in range(argc_val):
            #             element_addr = argv_addr + i * process.GetAddressByteSize()
            #             error = lldb.SBError()
            #             ptr_data = process.ReadPointerFromMemory(element_addr, error)
            #             if error.Success() and ptr_data:
            #                 cstr = process.ReadCStringFromMemory(ptr_data, 100, error)
            #                 if error.Success():
            #                     print(f"{indent}argv[{i}]: \"{cstr}\"")
            #                 else:
            #                     print(f"{indent}argv[{i}]: <unreadable>")
            #             else:
            #                 print(f"{indent}argv[{i}]: <null or error>")
            #     except Exception as e:
            #         print(f"{indent}Failed to read argv: {e}")
            # endregion
            
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


            elif num_children > 0:
                children = [var.GetChildAtIndex(i) for i in range(num_children)]
                vars_changed += self.track(children, depth + 1, max_depth, full_name)

        return vars_changed
    
    def getValue(self, var):
        return self.previous_values[var]
    
    def setVarsDeclared(self, var):
        return self.vars_declared.append(var)
    
# コマンドライン引数の確認
def get_command_line_args():
    parser = argparse.ArgumentParser(description='for the c-backdoor')

    # ベース名を取得
    parser.add_argument('--name', type=str, required=True, help='string')

    # 引数を解析
    return parser.parse_args()

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

    def vars_checker(vars_changed):
        varsDeclLines = list(set(varsDeclLines_list.pop(str(line_number), [])) - set(varsTracker.vars_declared))
        
        if len(varsDeclLines) != 0:
            # 変数が合致していればstepinを実行して次に進む
            vars_event = []
            errorCnt = 0
            while True:
                # とりあえずスカラー変数
                event = event_reciever()

                if (item := event.get('item', None)) is not None:
                    if not item in varsDeclLines:
                        errorCnt += 1
                        print(f'your variables were incorrect!!\ncorrect variables: {varsDeclLines}')
                        # 複数回入力を間違えたらヒントをあげる
                        if errorCnt >= 3:
                            event_sender({"message": f"ヒント: アイテム {', '.join(list(set(varsDeclLines) - set(vars_event)))} を取得してください!!", "status": "ng"})
                        else:
                            event_sender({"message": f"異なるアイテム {item} を取得しようとしています!!", "status": "ng"})
                        continue
                    
                    vars_event.append(item)
                    if Counter(vars_event) == Counter(varsDeclLines):
                        print("you selected correct vars")
                        event_sender({"message": f"アイテム {item} を正確に取得できました!!", "value": varsTracker.getValue(item), "undefined": False, "status": "ok"})
                        varsTracker.setVarsDeclared(item)
                        break
                    event_sender({"message": f"アイテム {item} を正確に取得できました!!", "value": varsTracker.getValue(item), "undefined": False, "status": "ok", "getting": True})
                    varsTracker.setVarsDeclared(item)
                else:
                    errorCnt += 1
                    event_sender({"message": "異なる行動をしようとしています1!!", "status": "ng"})
                    continue

        # vars_changedとvarsTrackerの共通項とvarsDeclLinesの差項を、値が変化した変数として検知する
        common = list(set(vars_changed) & set(varsTracker.vars_declared))
        varsChanged = list(set(common) - set(varsDeclLines))

        if len(varsChanged) != 0:
            print(f"vars_changed: {varsChanged}")
            vars_event = []
            errorCnt = 0
            while True:
                event = event_reciever()
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
                        continue
                    vars_event.append(item)
                    if Counter(vars_event) == Counter(varsChanged):
                        print("you changed correct vars")
                        event_sender({"message": f"アイテム {item} の値を {itemValue} で正確に設定できました!!", "status": "ok"})
                        break
                    event_sender({"message": f"アイテム {item} の値を {itemValue} で正確に設定できました!!", "status": "ok", "getting": True})
                else:
                    errorCnt += 1
                    event_sender({"message": "異なる行動をしようとしています2!!", "status": "ng"})
                    continue

        # 変数が初期化されない時、スキップされるので、それも読み取る
        target_lines = [line for line in varsDeclLines_list if line_number < int(line) < crnt_line_number]

        print(f"{line_data[func_name]} - {line_number}")
        if len(target_lines) != 0 and line_number not in line_data[func_name]:
            # 変数が合致していればstepinを実行して次に進む
            for line in target_lines:
                skipped_varDecls = varsDeclLines_list.pop(line)
                vars_event = []
                errorCnt = 0
                while True:
                    # とりあえずスカラー変数
                    event = event_reciever()

                    if (item := event.get('item', None)) is not None:
                        if not item in skipped_varDecls:
                            errorCnt += 1
                            print(f'your variables were incorrect!!\ncorrect variables: {skipped_varDecls}')
                            # 複数回入力を間違えたらヒントをあげる
                            if errorCnt >= 3:
                                event_sender({"message": f"ヒント: アイテム {', '.join(list(set(skipped_varDecls) - set(vars_event)))} を取得してください!!", "status": "ng"})
                            else:
                                event_sender({"message": f"異なるアイテム {item} を取得しようとしています!!", "status": "ng"})
                            continue
                        
                        vars_event.append(item)
                        if Counter(vars_event) == Counter(skipped_varDecls):
                            print("you selected correct vars")
                            event_sender({"message": f"アイテム {item} を正確に取得できました!!", "value": varsTracker.getValue(item), "undefined": True, "status": "ok"})
                            varsTracker.setVarsDeclared(item)
                            break
                        event_sender({"message": f"アイテム {item} を正確に取得できました!!", "value": varsTracker.getValue(item), "undefined": True, "status": "ok", "getting": True})
                        varsTracker.setVarsDeclared(item)
                    else:
                        errorCnt += 1
                        event_sender({"message": "異なる行動をしようとしています1!!", "status": "ng"})
                        continue
            

    def event_reciever():
        # JSONが複数回に分かれて送られてくる可能性があるためパース
        data = conn.recv(1024)
        # ここは後々変える
        if not data:
            return None
        buffer = data.decode()
        event = json.loads(buffer)
        print(f"[受信イベント] {event}")
        return event
    
    def event_sender(msgJson):
        if msgJson["status"] == "ok" and not msgJson.get("getting", None):
            target_lines = [line for line in varsDeclLines_list if line_number < int(line) < crnt_line_number]
            # 初期化されていない変数はスキップされてしまうので、そのような変数があるなら最初の行数を取得する
            if len(target_lines) != 0 and line_number not in line_data[func_name]:
                msgJson["line"] = int(target_lines[0])
            else:
                msgJson["line"] = crnt_line_number
        send_data = json.dumps(msgJson)
        conn.sendall(send_data.encode('utf-8'))

    def step_conditionally(frame):
        # プロセスの状態を更新
        if isEnd:
            while True:
                if (event := event_reciever()) is None:
                    continue
                if (retValue := event.get('return', None)) is not None:
                    event_sender({"message": "おめでとうございます!! ここがゴールです!!", "status": "ok"})
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
        
        print(f"{func_name} at {file_name}:{line_number}")
        return state, frame, file_name, line_number, func_name

    def get_std_outputs():
        stdout_output, stderr_output = get_all_stdvalue(process)
        if stdout_output:
            print("[STDOUT]")
            print(stdout_output)

        if stderr_output:
            print("[STDERR]")
            print(stderr_output)

    try:
        print(f"[接続] {addr} が接続しました")

        func_crnt_name = "main"

        varsTracker = VarsTracker()
            
        with conn:
            isEnd = False

            if (next_state := get_next_state()):
                state, frame, file_name, line_number, func_name = next_state
                with open(f"{DATA_DIR}/{file_name[:-2]}/{file_name[:-2]}_line.json", 'r') as f:
                    line_data = json.load(f)
                with open(f"{DATA_DIR}/{file_name[:-2]}/{file_name[:-2]}_varDeclLines.json", 'r') as f:
                    varsDeclLines_list = json.load(f)
            else:
                isEnd = True

            step_conditionally(frame)
            
            if (next_state := get_next_state()):
                state, frame, file_name, crnt_line_number, func_crnt_name = next_state
            else:
                isEnd = True

            vars_changed = varsTracker.trackStart(frame)

            get_std_outputs()

            vars_checker(vars_changed)

            # 変数は次の行での値を見て考える(まず変数チェッカーで次の行に進み変数の更新を確認) => その行と前の行で構文や関数は比較する(構文内の行の移動及び関数の移動は次の行と前の行が共に必要)
            while process.GetState() == lldb.eStateStopped: 
            # JSONが複数回に分かれて送られてくる可能性があるためパース
                if line_data.get(func_name, None) and line_number in line_data[func_name] and not isEnd:
                    if (event := event_reciever()) is None:
                        continue

                    if (ngname := event.get('ng', None)) is not None:
                        if ngname == "notEnter":
                            event_sender({"message": "ここから先は進入できません1!!", "status": "ng"})
                        else:
                            event_sender({"message": "NG行動をしました2!!", "status": "ng"})
                        continue
                    elif func_crnt_name != func_name:
                        if (funcChange := event.get('funcChange', None)) is not None:
                        # func_event = [event['roomname']]
                        # if func_event != func_name:
                        #     print(f'your func name was incorrect!!\ncorrect func name: {func_name}')
                        #     continue
                            func_crnt_name = func_name
                        else:
                            event_sender({"message": "NG行動をしました3!!", "status": "ng"})
                            continue
                    elif (fromTo := event.get('fromTo', None)) is not None:
                        type = event.get('type', '')
                        # そもそも最初の行番が合致していなければ下のwhile Trueに入る前にカットする必要がある
                        # こうしないとどこのエリアに行っても条件構文に関する受信待ちが永遠に続いてしまう
                        if len(fromTo) >= 2:
                            if fromTo[:2] == [line_number, crnt_line_number]:
                                if type == 'if':
                                    errorCnt_if = 0
                                    line_number_track = fromTo[:2]
                                    while True:
                                        # まず、if文でどの行まで辿ったかを確かめる
                                        if fromTo[:len(line_number_track)] == line_number_track:
                                            crntFromTo = fromTo[len(line_number_track):]
                                        # もし、fromToと今まで辿った行が部分一致しなければ新たな通信を待つ
                                        else:
                                            errorCnt_if += 1
                                            event_sender({"message": f"ここから先は進入できません2!! {"ヒント: if 条件を見ましょう!!" if errorCnt_if >= 3 else ""}", "status": "ng"})
                                            while True:
                                                if (event := event_reciever()) is None:
                                                    break
                                                if (type := event.get('type', '')) != 'if':
                                                    errorCnt_if += 1
                                                    event_sender({"message": f"NG行動をしました!! {"ヒント: if 条件を見ましょう!!" if errorCnt_if >= 3 else ""}", "status": "ng"})
                                                elif (fromTo := event.get('fromTo', None)) is None:
                                                    errorCnt_if += 1
                                                    event_sender({"message": f"NG行動をしました!! {"ヒント: if 条件を見ましょう!!" if errorCnt_if >= 3 else ""}", "status": "ng"})
                                                else:
                                                    break
                                            continue
                                        while True:
                                            # 全ての行数が合致していたらif文の開始の正誤の分析を終了する
                                            if not crntFromTo:
                                                break

                                            step_conditionally(frame)

                                            if (next_state := get_next_state()):
                                                line_number = crnt_line_number
                                                func_name = func_crnt_name
                                                state, frame, file_name, crnt_line_number, func_crnt_name = next_state
                                            else:
                                                isEnd = True

                                            if crntFromTo[0] != crnt_line_number:
                                                errorCnt_if += 1
                                                event_sender({"message": f"ここから先は進入できません3!! {"ヒント: if 条件を見ましょう!!" if errorCnt_if >= 3 else ""}", "status": "ng"})
                                                while True:
                                                    if (event := event_reciever()) is None:
                                                        continue
                                                    if (type := event.get('type', '')) != 'if':
                                                        errorCnt_if += 1
                                                        event_sender({"message": f"NG行動をしました!! {"ヒント: if 条件を見ましょう!!" if errorCnt_if >= 3 else ""}", "status": "ng"})
                                                    elif (fromTo := event.get('fromTo', None)) is None:
                                                        errorCnt_if += 1
                                                        event_sender({"message": f"NG行動をしました!! {"ヒント: if 条件を見ましょう!!" if errorCnt_if >= 3 else ""}", "status": "ng"})
                                                    else:
                                                        break
                                                line_number_track.append(crnt_line_number)
                                                break
                                            line_number_track.append(crntFromTo.pop(0))

                                        # crntFromToが 空 = 行番が完全一致 になるか、if文の中の処理が空な場合で最後の行番が一致するかを確認する
                                        if not crntFromTo or crntFromTo[-1] == line_number:
                                            event_sender({"message": "", "status": "ok"})
                                            vars_changed = varsTracker.trackStart(frame)
                                            vars_checker(vars_changed)
                                            break
                                elif type == 'doWhileIn':
                                    event_sender({"message": "", "status": "ok"})
                                elif type in ['doWhileTrue', 'doWhileFalse']:
                                    event_sender({"message": "", "status": "ok"})
                                elif type == 'switchCase':
                                    event_sender({"message": "", "status": "ok"})
                                else:
                                    event_sender({"message": "ここから先は進入できません4!!", "status": "ng"})
                                    continue 
                            elif fromTo[:2] == [None, crnt_line_number] and type == 'switchEnd':
                                event_sender({"message": "", "status": "ok"})
                            else:
                                event_sender({"message": "ここから先は進入できません5!!", "status": "ng"})
                                continue            
                        elif len(fromTo) == 1 and fromTo == [line_number]:
                            if type == 'ifEnd':
                                event_sender({"message": "", "status": "ok"})
                            elif type == 'whileIn':
                                event_sender({"message": "", "status": "ok"})

                                # get_std_outputs, state_checkerを入れるかは後々考える

                                while True:
                                    if (event := event_reciever()) is None:
                                        break

                                    if (fromTo := event.get('fromTo', None)) is not None:
                                        type = event.get('type', '')
                                        if type in ['whileTrue', 'whileFalse']:
                                            if fromTo == [line_number, crnt_line_number]:
                                                event_sender({"message": "", "status": "ok"})
                                                break
                                    event_sender({"message": "NG行動をしました4!!", "status": "ng"})
                            elif type == 'forIn':
                                event_sender({"message": "", "status": "ok"})

                                # get_std_outputs, state_checkerを入れるかは後々考える

                                while True:
                                    print(line_number, crnt_line_number)
                                    if (event := event_reciever()) is None:
                                        break

                                    if (fromTo := event.get('fromTo', None)) is not None:
                                        type = event.get('type', '')
                                        if type in ['forTrue', 'forFalse']:
                                            if fromTo == [line_number, crnt_line_number]:
                                                event_sender({"message": "", "status": "ok"})
                                                break
                                    event_sender({"message": "NG行動をしました5!!", "status": "ng"})
                            else:
                                event_sender({"message": "ここから先は進入できません6!!", "status": "ng"})
                                continue
                        else:
                            event_sender({"message": "ここから先は進入できません7!!", "status": "ng"})
                            continue
                    elif event.get('item', None) or event.get('itemset', None):
                        event_sender({"message": "NG行動をしました6!!", "status": "ng"})
                        continue
                    else:
                        pass
                    
                step_conditionally(frame)

                if (next_state := get_next_state()):
                    line_number = crnt_line_number
                    func_name = func_crnt_name
                    state, frame, file_name, crnt_line_number, func_crnt_name = next_state
                else:
                    isEnd = True

                vars_changed = varsTracker.trackStart(frame)

                get_std_outputs()

                # 変数は前回の処理で変更されていたら見る
                vars_checker(vars_changed)
    except:
        pass

def start_server(host='localhost', port=9999):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        s.bind((host, port))
        s.listen()
        print(f"[サーバ起動] {host}:{port} で待機中...")

        conn, addr = s.accept()
        thread = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
        thread.start()

        thread.join()
        print("[サーバ終了]")

args = get_command_line_args()

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

start_server()
