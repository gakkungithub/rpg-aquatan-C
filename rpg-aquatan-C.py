import os
import subprocess
import argparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = BASE_DIR + '/data'

parser = argparse.ArgumentParser()
parser.add_argument('-p', '--program', dest='program', type=str, required=True)
parser.add_argument('-c', '--cfiles', dest='cfiles', nargs='+', type=str, required=True)
parser.add_argument('-u', '--universal', dest='universal', action='store_true', help='Enable color universal design mode')
args = parser.parse_args()

programname = args.program
cfiles = [f"{DATA_DIR}/{programname}/{cfile}" for cfile in args.cfiles]

# cファイルを解析してマップデータを生成する
# args.universalがあるなら -uオプションをつけてカラーユニバーサルデザインを可能にする
cfcode = ["python3.13", "c-flowchart.py", "-p", programname, "-c", ", ".join(cfiles)]
if args.universal:
    cfcode.append("-u")
subprocess.run(cfcode, cwd="mapdata_generator")

programpath = f"{DATA_DIR}/{programname}/{programname}"
subprocess.run(["gcc", "-g", "-o", programpath, " ".join(cfiles)])

# cプログラムを整形する
subprocess.run(["clang-format", "-i", f"{programpath}.c"])

# サーバを立てる
env = os.environ.copy()
env["PYTHONPATH"] = os.path.abspath("modules") + (
    ":" + env["PYTHONPATH"] if "PYTHONPATH" in env else ""
)
server = subprocess.Popen(["/opt/homebrew/opt/python@3.13/bin/python3.13", "c-backdoor_1.py", "--name", programpath], cwd="debugger-C", env=env)

# クライアントを立てる
inifilepath = f"{programpath}.ini"
client = subprocess.Popen(["python3.13", "simple.py", "-i", inifilepath], cwd="rpg-aquatan")

server.wait()
client.wait()