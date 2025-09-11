import faulthandler
faulthandler.enable()
import lldb
import argparse
import os
import struct
import socket
import threading
import json
import tempfile

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
        self.frames = ['start']
        self.track(gvars, self.global_previous_values, [])
    
    def trackStart(self, frame):
        current_frames = [thread.GetFrameAtIndex(i).GetFunctionName()
                      for i in range(thread.GetNumFrames())]
        # 何かしらの関数に遷移したとき
        if len(current_frames) > len(self.frames):
            self.previous_values.append({})
            self.frames = current_frames
        # 何かしらの関数から戻ってきたとき
        elif len(current_frames) < len(self.frames):
            self.previous_values.pop()
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
        self.track(gvars, self.global_previous_values, [])
        self.track(frame.GetVariables(True, True, False, True), self.previous_values[-1], [])

    def track(self, vars, var_previous_values: dict[str, VarPreviousValue], vars_path: list[str], depth=0, prefix="") -> list[str]:
        # crnt_vars = []
        
        indent = "    " * depth

        for var in vars:
            name = var.GetName()
            full_name = f"{prefix}.{name}" if prefix else name
            value = var.GetValue()
            address = var.GetLoadAddress()
            # print(name, var.GetSummary())

            var_previous_value = var_previous_values[name].value if name in var_previous_values else None

            # print(var, address)
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
                print(f"{indent}{full_name} = {value}")

            # if depth == 0:
            #     crnt_vars.append(name)

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

    def print_variables(self, previous_values: dict[str, VarPreviousValue], depth=1):
        indent = "    " * depth
        for name, previous_value in previous_values.items():
            print(f"{indent}name: {name}: [value: {previous_value.value}, address: {previous_value.address}]")
            self.print_variables(previous_value.children, depth+1)

    def print_all_variables(self):
        self.print_variables(self.global_previous_values)
        all_frames = self.frames[:-1]
        for i, frame in enumerate(all_frames):
            print(f"func_name: {frame}")
            self.print_variables(self.previous_values[-(i+1)])

def step_conditionally(frame):
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
    
    process.PutSTDIN("1\n")

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
    # 新しい出力だけ読む
    out_chunk = stdout_r.read()

    err_chunk = stderr_r.read()

    if out_chunk:
        print("[STDOUT]", out_chunk, end="")
    if err_chunk:
        print("[STDERR]", err_chunk, end="")

def handle_client(conn: socket.socket, addr: tuple[str, int]):
    def event_reciever():
        # JSONが複数回に分かれて送られてくる可能性があるためパース
        data = conn.recv(1024)
        # ここは後々変えるかも
        if not data:
            return False
        return True
    
    def event_sender(finished: bool):
        send_data = json.dumps({"finished": finished})
        conn.sendall(send_data.encode('utf-8'))

    print(f"[接続] {addr} が接続しました")

    try:
        gvars = []
        for module in target.module_iter():
            for sym in module:
                if sym.GetType() == lldb.eSymbolTypeData:  # データシンボル（変数）
                    name = sym.GetName()
                    if name:
                        var = target.FindFirstGlobalVariable(name)
                        if var.IsValid():
                            gvars.append(var)

        varsTracker = VarsTracker(gvars)

        with conn:
            event_reciever()
            if (next_state := get_next_state()):
                state, frame, file_name, next_line_number, func_crnt_name, next_frame_num = next_state
                func_name = func_crnt_name
                frame_num = 1
                line_number = -1
                # print(func_name, func_crnt_name)
                # print(line_number, next_line_number)
                varsTracker.trackStart(frame)
                print(varsTracker.vars_changed)
                get_std_outputs()
                step_conditionally(frame)
                event_sender(False)
            else:
                event_sender(True)
                event_reciever()
                return

            while 1:
                event_reciever()
                if (next_state := get_next_state()):
                    line_number = next_line_number
                    func_name = func_crnt_name
                    frame_num = next_frame_num
                    state, frame, file_name, next_line_number, func_crnt_name, next_frame_num = next_state
                    # print(func_name, func_crnt_name)
                    # print(line_number, next_line_number)
                    varsTracker.trackStart(frame)
                    print(varsTracker.vars_changed)
                    varsTracker.print_all_variables()
                    get_std_outputs()
                    event_sender(False)
                    print("funcname", frame.GetFunctionName())
                    step_conditionally(frame)
                else:
                    event_sender(True)
                    event_reciever()
                    return
    except:
        return

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