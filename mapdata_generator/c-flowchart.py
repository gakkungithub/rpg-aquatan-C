import argparse
from parse_1 import parseIndex, ASTtoFlowChart
from generate_bit_map_1 import GenBitMap

parser = argparse.ArgumentParser()
parser.add_argument('-p', required=True)
parser.add_argument('-c', nargs='+', required=True)
parser.add_argument('-u', action='store_true', help='Enable color universal design mode')
args = parser.parse_args()
translation_units = parseIndex(args.c)

programname = args.p

for cname, tu in translation_units.items():
    fchart = ASTtoFlowChart()
    fchart.createErrorInfo(tu.diagnostics)
    fchart.write_ast(tu, programname)

genBitMap = GenBitMap(programname, fchart.func_info_dict, fchart.gvar_info, fchart.varNode_info, fchart.expNode_info, fchart.roomSize_info, fchart.gotoRoom_list, fchart.condition_move)
genBitMap.startTracking()

genBitMap.setMapChip(programname, fchart.line_info_dict, args.u)