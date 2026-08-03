import argparse
from parse_2 import parseIndex, ASTtoFlowChart
from generate_bit_map_2 import GenBitMap

parser = argparse.ArgumentParser()
parser.add_argument('-p', required=True)
parser.add_argument('-c', nargs='+', required=True)
parser.add_argument('-u', action='store_true', help='Enable color universal design mode')
parser.add_argument('-e', action='store_true', help='Enable english mode')

args = parser.parse_args()
translation_units = parseIndex(args.c)

programname = args.p

for cname, tu in translation_units.items():
    fchart = ASTtoFlowChart(args.e)
    fchart.write_ast(tu, programname)

genBitMap = GenBitMap(programname, fchart.func_info_dict, fchart.gvar_info, fchart.varNode_info, fchart.expr_node_info, fchart.roomSize_info, fchart.gotoRoom_list, fchart.condition_move, args.e)
genBitMap.startTracking()

genBitMap.setMapChip(programname, fchart.line_info_dict, args.u)