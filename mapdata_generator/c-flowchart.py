import argparse
from parse import parseIndex, ASTtoFlowChart
from generate_bit_map import GenBitMap

parser = argparse.ArgumentParser()
parser.add_argument('-p', required=True)
parser.add_argument('-c', nargs='+', required=True)
args = parser.parse_args()
translation_units = parseIndex(args.c)

programname = args.p

for cname, tu in translation_units.items():
    fchart = ASTtoFlowChart()
    fchart.createErrorInfo(tu.diagnostics)
    fchart.write_ast(tu, programname)
    # for cr in tu.cursor.get_children():
    #     fchart.write_ast_tree(cr)

genBitMap = GenBitMap(programname, fchart.func_info, fchart.gvar_info, fchart.expNode_info, fchart.roomSize_info, fchart.gotoRoom_list, fchart.condition_move)
genBitMap.startTracking()
genBitMap.setMapChip(programname)