import os
import subprocess
import argparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = BASE_DIR + '/data'

parser = argparse.ArgumentParser()
parser.add_argument('-p', '--program', dest='program', type=str, required=True)
parser.add_argument('-c', '--cfiles', dest='cfiles', nargs='+', type=str, required=True)
args = parser.parse_args()

programname = args.program
cfiles = [f"{DATA_DIR}/{programname}/{cfile}" for cfile in args.cfiles]

subprocess.run(["python3.13", "c-flowchart.py", "-p", programname, "-c", ", ".join(cfiles)], cwd="mapdata_generator")

programpath = f"{DATA_DIR}/{programname}/{programname}"
result = subprocess.run(["gcc", "-g", "-o", programpath, " ".join(cfiles)])

env = os.environ.copy()

env["PYTHONPATH"] = os.path.abspath("modules") + (
    ":" + env["PYTHONPATH"] if "PYTHONPATH" in env else ""
)

server = subprocess.Popen(["/opt/homebrew/opt/python@3.13/bin/python3.13", "c-backdoor.py", "--name", programpath], cwd="debugger-C", env=env)

inifilepath = f"{programpath}.ini"
print(inifilepath)
client = subprocess.Popen(["python3.13", "simple.py", "-i", inifilepath], cwd="rpg-aquatan")

server.wait()
client.wait()