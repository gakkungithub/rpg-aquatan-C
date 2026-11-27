import argparse
from parse import AST2Flowchart
from generate_bit_map import BitMapGenerator

parser = argparse.ArgumentParser()
parser.add_argument('-p', required=True)
parser.add_argument('-c', nargs='+', required=True)
parser.add_argument('-u', action='store_true', help='Enable color universal design mode')
parser.add_argument('-e', action='store_true', help='Enable english mode')

args = parser.parse_args()

program_name: str = args.p
c_files: list[str] = args.c
is_english: bool = args.e
is_universal: bool = args.u

ast_to_flowchart = AST2Flowchart(program_name, c_files, is_english)

genBitMap = BitMapGenerator(
    program_name, 
    ast_to_flowchart.func_info_dict, 
    ast_to_flowchart.gvar_info, 
    ast_to_flowchart.var_info, 
    ast_to_flowchart.expr_node_info, 
    ast_to_flowchart.room_size_info, 
    ast_to_flowchart.gotoRoom_list, 
    ast_to_flowchart.execution_info,
    ast_to_flowchart.line_info_dict,
    is_english,
    is_universal
)

genBitMap.start_tracking()