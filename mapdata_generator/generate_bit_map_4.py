from __future__ import annotations
import sys
from typing import TypedDict
import random
import os
import json
import configparser
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import import_lib

import_lib.ensure_package("pydot")
import_lib.ensure_package("numpy")
import_lib.ensure_package("scipy", "scipy.ndimage")
import_lib.ensure_package("matplotlib", "matplotlib.pyplot")
import_lib.ensure_package("astar", "astar.search")

import pydot
import numpy as np
import scipy.ndimage as ndimage
import matplotlib.pyplot as plt
from astar.search import AStar, Tile

from rpg_aquatan_utils.types.expr_descriptions import *
from rpg_aquatan_utils.types.execution_info import *
from rpg_aquatan_utils.types.json_data_type import *
from rpg_aquatan_utils.types.map_data_generator import *

# condition_line_trackerを修正する必要がある
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = BASE_DIR + '/mapdata_for_test'

class RoomInfo(TypedDict):
    room_size: tuple[int, int, int, int]
    direction: str

class FuncReferenceGroup(TypedDict):
    name: str
    func: list[FuncReference]

class TempCommentWindowInfo(TypedDict):
    detail: list[list[str]]
    hover: list[list[Comment]]
    func_groups: list[FuncReferenceGroup | None]
    type: str

class TempExpressionDetail(TypedDict):
    expr: TempCommentWindowInfo
    vars: set[tuple[str, int]]
    execution_info: ExecutionInfo

class TempIfConditionsComment(TypedDict):
    type: Literal["if"]
    conditions: dict[int, list[Comment]]
    
class MoveEvent:
    def __init__(self, from_pos: tuple[int, int], to_pos: tuple[int, int], comment_window_info: TempCommentWindowInfo | None, mapchip: int, execution_info: ExecutionInfo | None, func_name: str):
        self.local_from_pos = from_pos
        self.local_to_pos = to_pos 
        self.comment_window_info = comment_window_info
        self.mapchip = mapchip
        # execution_infoがNoneなら条件や計算式の確認がないワープゾーンとなる
        self.execution_info = execution_info
        self.func_name = func_name

class Treasure:
    def __init__(self, pos: tuple[int, int], name: str, var_info: VarInfo, func_name: str):
        self.local_pos = pos
        self.name = name
        self.var_info = var_info
        self.func_name = func_name

class FuncWarpBase:
    def __init__(self, to_pos: tuple[int, int], args: list[VarInfo], line: int):
        self.local_to_pos = to_pos
        self.args = args
        self.line = line

    def get_attributes(self):
        return (self.local_to_pos, self.args, self.line)

class CharaReturn:
    def __init__(self, pos: tuple[int, int], comment_window_info: TempCommentWindowInfo, execution_info: ExecutionInfo, func_name: str):
        self.local_pos = pos
        self.comment_window_info = comment_window_info
        self.execution_info = execution_info
        self.func_name = func_name

class Door:
    def __init__(self, pos: tuple[int, int], dir: int, name: str):
        self.local_pos = pos
        self.name = name
        self.dir = dir

class CharaCheckCondition:
    def __init__(self, func: str, pos: tuple[int,int], dir: int, execution_info: ExecutionInfo, comment_window_info: TempCommentWindowInfo):
        self.func = func
        self.local_pos = pos
        self.dir = dir
        self.execution_info = execution_info
        self.comment_window_info = comment_window_info

class CharaExpression:
    def __init__(self, pos: tuple[int, int], func: str):
        self.local_pos = pos
        self.func = func
        self.detail_by_line: dict[int, TempExpressionDetail] = {}

class ExecutionCommentHandler:
    def __init__(self):
        self.variable_comments: dict[int, list[VarInfo]] = {}
        self.if_condition_comments: dict[int, TempIfConditionsComment] = {}
        self.while_condition_comments: dict[int, WhileConditionComment] = {}
        self.do_while_condition_comments: dict[int, DoWhileConditionComment] = {}
        self.for_comments: dict[int, ForComment] = {}
        self.switch_condition_comments: dict[int, SwitchConditionComment] = {}
        self.control_flow_comments: dict[int, ControlFlowComment] = {}
        self.expression_comments: dict[int, ExpressionComment] = {}
        self.return_comments: dict[int, ReturnComment] = {}

    def register_variable_comment(self, var_info: VarInfo):
        if var_info["start"] in self.variable_comments:
            self.variable_comments[var_info["start"]].append(var_info)
        else:
            self.variable_comments[var_info["start"]] = [var_info]

    def register_if_condition_comment(self, line: int, condition_line: int, condition_comment: list[Comment]):
        if line <= 0 or condition_line <= 0:
            sys.exit("line or case line have to be 1 or bigger integer")

        if line in self.if_condition_comments:
            if self.if_condition_comments[line]["type"] != "if":
                sys.exit("type of if condition comments has to be \"if\"")
            if condition_line in self.if_condition_comments[line]["conditions"]:
                sys.exit("different conditions of same if statement cannot be in same condition_line")
            self.if_condition_comments[line]["conditions"][condition_line] = condition_comment
        else:
            self.if_condition_comments[line] = TempIfConditionsComment(
                type="if", 
                conditions={
                    condition_line: condition_comment
                }
            )
    
    def register_while_condition_comment(self, line: int, condition_comment: list[Comment]):
        if line <= 0:
            sys.exit("line has to be 1 or bigger integer")

        if line in self.while_condition_comments:
            if self.while_condition_comments[line]["type"] != "while":
                sys.exit("type of while condition comments has to be \"while\"")
        else:
            self.while_condition_comments[line] = WhileConditionComment(
                type="while", 
                condition=condition_comment
            )

    def register_do_while_condition_comment(self, line: int, condition_comment: list[Comment]):
        if line <= 0:
            sys.exit("line has to be 1 or bigger integer")

        if line in self.do_while_condition_comments:
            if self.do_while_condition_comments[line]["type"] != "do_while":
                sys.exit("type of do-while condition comments has to be \"do-while\"")
        else:
            self.do_while_condition_comments[line] = DoWhileConditionComment(
                type="do_while", 
                condition=condition_comment
            )

    # for文は、初期化式と条件式、更新式があるので、それをひとまとめにして登録する
    # こうすることで、execution_comments[line]はリストにする必要がなくなる
    def register_for_comment(self, line: int, comment_type: str, comment: list[Comment]):
        if line <= 0:
            sys.exit("line has to be 1 or bigger integer")

        if comment_type not in ("initializer", "condition", "change"):
            sys.exit(f"{comment_type} is not applicable to for statement comment type")

        if line not in self.for_comments:
            self.for_comments[line] = ForComment(type="for")

        for_comment = self.for_comments[line]

        if for_comment["type"] != "for":
            sys.exit('type of for comments has to be "for"')

        if comment_type in for_comment:
            sys.exit(f"{comment_type} comments of for statement cannot be overlapped")

        if comment_type == "initializer" and "var_initializer" in for_comment:
            sys.exit(f"{comment_type} element cannot be mixed up with variable initializer")

        for_comment[comment_type] = comment

    def register_for_var_initializer_comment(self, line: int, comment: list[VarInfo]):
        if line <= 0:
            sys.exit("line has to be 1 or bigger integer")

        if line not in self.for_comments:
            self.for_comments[line] = ForComment(type="for")

        for_comment = self.for_comments[line]

        if for_comment["type"] != "for":
            sys.exit('type of for comments has to be "for"')

        if "var_initializer" in for_comment:
            sys.exit("variable initializer comments of for statement cannot be overlapped")

        if "initializer" in for_comment:
            sys.exit(f"varialbe initializer element cannot be mixed up with for initializer")

        for_comment["var_initializer"] = comment

    def register_switch_condition_comment(self, line: int, condition_comment: list[Comment]):
        if line <= 0:
            sys.exit("line has to be 1 or bigger integer")

        if line in self.switch_condition_comments:
            if self.switch_condition_comments[line]["type"] != "switch":
                sys.exit("type of switch condition comments has to be \"switch\"")
        else:
            self.switch_condition_comments[line] = SwitchConditionComment(
                type="switch",
                condition=condition_comment,
                case_exprs=[]
            )

    def register_case_comment(self, line: int, case_expr_node_info_list: list[ExprNodeInfo]):
        if line <= 0:
            sys.exit("line has to be 1 or bigger integer")

        if not line in self.switch_condition_comments or self.switch_condition_comments[line]["type"] != "switch":
            sys.exit("switch condition comment has to be already registered")

        self.switch_condition_comments[line]["case_exprs"].append(
            [
                SwitchCaseComment(
                    comments = case_expr_node_info["comments"],
                    line = case_expr_node_info["line"]
                )
                for case_expr_node_info in case_expr_node_info_list
            ]
        )

    def register_default_index(self, line: int, index: int):
        if line <= 0 or index <= -1:
            sys.exit("line has to be 1 or bigger integer, and default index have to be 0 or bigger integer")

        if not line in self.switch_condition_comments or self.switch_condition_comments[line]["type"] != "switch":
            sys.exit("switch condition comment has to be already registered")

        if "default_index" in self.switch_condition_comments[line]:
            sys.exit("default index of switch statement cannot be overlapped")

        self.switch_condition_comments[line]["default_index"] = index

    def register_control_flow_comment(self, line: int, type: Literal["break"] | Literal["continue"]):
        if line <= 0:
            sys.exit("line has to be 1 or bigger integer")
        if line in self.control_flow_comments:
            sys.exit("some comments are already registered in the line")

        self.control_flow_comments[line] = ControlFlowComment(
            type=type
        )

    def register_expression_comment(self, line: int, expression: list[Comment]):
        if line <= 0:
            sys.exit("line has to be 1 or bigger integer")

        if line in self.expression_comments:
            sys.exit("expression comment is already registered")

        self.expression_comments[line] = ExpressionComment(
            type="expression",
            expr=expression
        )

    def register_return_comment(self, line: int, expression: list[Comment]):
        if line <= 0:
            sys.exit("line has to be 1 or bigger integer")

        if line in self.expression_comments:
            sys.exit("expression comment is already registered")

        self.return_comments[line] = ReturnComment(
            type="return",
            expr=expression
        )

    def register_non_variable_comments(self, line: int, comment: NonVarComment, execution_comments: dict[int, NonVarComment]):
        if line in execution_comments:
            sys.exit("two or more comments cannot be registered to execution_comments dictionary")
        execution_comments[line] = comment

    def create_non_varialble_execution_comments(self) -> dict[int, NonVarComment]:
        execution_comments: dict[int, NonVarComment] = {}
        for line, if_conditions_comment in self.if_condition_comments.items():
            if line in execution_comments:
                sys.exit("two or more comments cannot be registered to execution_comments dictionary")
            execution_comments[line] = IfConditionsComment(
                type = "if",
                line = line,
                conditions = [
                    IfConditionComment(
                        line = condition_line,
                        comments = if_condition_comment
                    )
                    for condition_line, if_condition_comment in sorted(if_conditions_comment["conditions"].items())
                ]
            )

        for line, while_condition_comment in self.while_condition_comments.items():
            self.register_non_variable_comments(line, while_condition_comment, execution_comments)

        for line, do_while_condition_comment in self.do_while_condition_comments.items():
            self.register_non_variable_comments(line, do_while_condition_comment, execution_comments)

        for line, for_condition_comment in self.for_comments.items():
            self.register_non_variable_comments(line, for_condition_comment, execution_comments)

        for line, switch_condition_comment in self.switch_condition_comments.items():
            self.register_non_variable_comments(line, switch_condition_comment, execution_comments)

        for line, control_flow_comment in self.control_flow_comments.items():
            self.register_non_variable_comments(line, control_flow_comment, execution_comments)

        for line, expression_comment in self.expression_comments.items():
            self.register_non_variable_comments(line, expression_comment, execution_comments)

        for line, return_comment in self.return_comments.items():
            self.register_non_variable_comments(line, return_comment, execution_comments) 

        return execution_comments

# マップデータ生成に必要な情報はここに格納
class MapInfo:
    ISEVENT = 2

    def __init__(self, execution_info: dict[str, ExecutionInfo], is_english: bool):
        self.event_map = np.zeros((20,20))
        self.offset: dict[str, int] = {"y": 0, "x": 0}
        self.room_info: dict[str, RoomInfo] = {}
        self.execution_info = execution_info
        self.player_init_local_pos: tuple[int, int] | None = None
        self.move_events: list[MoveEvent] = []
        self.treasures: list[Treasure] = []
        self.func_warps: dict[str, FuncWarpBase] = {}
        self.chara_moveItems: list[tuple[tuple[int, int], str, list[list[str]], str, list[str]]] = []
        self.chara_returns: list[CharaReturn] = []
        self.doors: list[Door] = []
        self.chara_checkConditions: list[CharaCheckCondition] = []
        self.chara_expressions: dict[str, CharaExpression] = {}
        self.input_lines: dict[str, dict[int, list[int]]] = {}
        self.file_lines: dict[str, dict[int, list[dict]]] = {}
        self.memory_lines: dict[str, dict[int, list[dict]]] = {}
        self.str_lines: dict[str, dict[int, list[dict]]] = {}
        self.execution_comment_handler = ExecutionCommentHandler()

        self.is_english = is_english

    # 空間をランダムに一つ取得する
    def pick_random_space_pos_from_map(self, check_map) -> tuple[int,int]:
        zero_elements = np.argwhere(check_map == 0)
        return zero_elements[np.random.choice(zero_elements.shape[0])]

    # プレイヤーの初期位置の設定
    def set_player_init_pos(self, initNodeID: str):  
        if self.player_init_local_pos:
            return
        # ローカル座標
        local_y, local_x, height, width = self.room_info[initNodeID]["room_size"]
        y, x = self.pick_random_space_pos_from_map(self.event_map[local_y+self.offset["y"]:local_y+self.offset["y"]+height, local_x+self.offset["x"]:local_x+self.offset["x"]+width])
        self.event_map[local_y+self.offset["y"]+y, local_x+self.offset["x"]+x] = self.ISEVENT
        self.player_init_local_pos = (local_y+y, local_x+x)

    def set_func_warp_start_pos(self, start_nodeID: str):
        local_y, local_x, height, width = self.room_info[start_nodeID]["room_size"]
        y, x = self.pick_random_space_pos_from_map(self.event_map[local_y+self.offset["y"]:local_y+self.offset["y"]+height, local_x+self.offset["x"]:local_x+self.offset["x"]+width])
        self.event_map[local_y+self.offset["y"]+y, local_x+self.offset["x"]+x] = self.ISEVENT
        return (local_y+y, local_x+x)

    # 話しかけると戻るキャラの設定
    def setCharaReturn(self, roomNodeID: str, execution_info_nodeID: str, comment_window_info: TempCommentWindowInfo, func_name: str):
        local_y, local_x, height, width = self.room_info[roomNodeID]["room_size"]
        y, x = self.pick_random_space_pos_from_map(self.event_map[local_y+self.offset["y"]+1:local_y+self.offset["y"]+height-1, local_x+self.offset["x"]+1:local_x+self.offset["x"]+width-1])
        self.event_map[local_y+self.offset["y"]+y+1, local_x+self.offset["x"]+x+1] = self.ISEVENT
        # type (ifやexp等) と line_track を取得していた
        return_execution_info = self.execution_info[execution_info_nodeID]
        self.chara_returns.append(CharaReturn((local_y+y+1, local_x+x+1), comment_window_info, return_execution_info, func_name))

    # ワープゾーンの設定 (条件式については、とりあえず関数だけを確認する)
    # expr_node_info = var_refs, func_refs, expr_comments, expr_line_num
    def setWarpZone(self, fromNodeID: str, to_nodeID: str, comment_window_info: TempCommentWindowInfo | None, crnt_func_name: str, warpNodeID: str | None = None):
        # まず遷移元を設定する
        from_local_y, from_local_x, from_height, from_width = self.room_info[fromNodeID]["room_size"]
        y, x = self.pick_random_space_pos_from_map(self.event_map[from_local_y+self.offset["y"]:from_local_y+self.offset["y"]+from_height, from_local_x+self.offset["x"]:from_local_x+self.offset["x"]+from_width])
        from_local_pos = (int(from_local_y+y), int(from_local_x+x))
        self.event_map[from_local_y+self.offset["y"]+y, from_local_x+self.offset["x"]+x] = self.ISEVENT

        # 次に遷移先を設定する
        to_local_y, to_local_x, to_height, to_width = self.room_info[to_nodeID]["room_size"]
        y, x = self.pick_random_space_pos_from_map(self.event_map[to_local_y+self.offset["y"]:to_local_y+self.offset["y"]+to_height, to_local_x+self.offset["x"]:to_local_x+self.offset["x"]+to_width])
        to_local_pos = (int(to_local_y+y), int(to_local_x+x))
        self.event_map[to_local_y+self.offset["y"]+y, to_local_x+self.offset["x"]+x] = self.ISEVENT

        execution_info = self.execution_info.get(warpNodeID, None) if warpNodeID is not None else self.execution_info.get(to_nodeID, None)

        # ステージによってマップチップ(UI)番号(158)を変えるかは今後判断する
        self.move_events.append(MoveEvent(from_local_pos, to_local_pos, comment_window_info, 158, execution_info, crnt_func_name))

    # スカラー変数に対応した宝箱の設定 (item_exp_infoは、変数名、値の計算式で使われている変数、計算式で使われている関数、宣言の行数を格納している)
    def setItemBox(self, roomNodeID: str, item_name: str, var_info: VarInfo, crnt_func_name: str):
        local_y, local_x, height, width = self.room_info[roomNodeID]["room_size"]
        y, x = self.pick_random_space_pos_from_map(self.event_map[local_y+self.offset["y"]:local_y+self.offset["y"]+height, local_x+self.offset["x"]:local_x+self.offset["x"]+width])
        self.event_map[local_y+self.offset["y"]+y, local_x+self.offset["x"]+x] = self.ISEVENT
        self.treasures.append(Treasure((local_y+y, local_x+x), item_name, var_info, crnt_func_name))

    # 処理上逆戻りを禁止するドアの生成
    def setDoor(self, pos: tuple[int, int], dir: int, comment_window_info: TempCommentWindowInfo):
        # hover_list = comment_window_info["hover"]
        # detail_parts = comment_window_info["detail"]
        # crnt_condition_num = 0
        # parts = []

        # for subparts in detail_parts:
        #     segment = ""
        #     for i, s in enumerate(subparts):
        #         segment += s
        #         if i < len(subparts) - 1:  
        #             # ? があった場所に条件を挿入
        #             segment += f"condition {hover_list[crnt_condition_num]}" if self.is_english else f"条件 {hover_list[crnt_condition_num]}"
        #             crnt_condition_num += 1
        #     parts.append(segment)

        # door_name = "AND\n".join(parts) if self.is_english else "かつ\n".join(parts) 
        self.doors.append(Door((pos[0] - self.offset["y"], pos[1] - self.offset["x"]), dir, ""))
        self.event_map[pos[0], pos[1]] = self.ISEVENT

    # 条件文キャラの生成
    # self.map_info.setCharaCheckCondition(self.func_name, path[i], 0, execution_info, comment_window_info, expr_node_info=self.getExprNodeInfo(exprNodeID))
    def setCharaCheckCondition(self, func_name: str, pos: tuple[int, int], dir: int, execution_info: ExecutionInfo, comment_window_info: TempCommentWindowInfo):
        absolute_pos = (pos[0] - self.offset["y"], pos[1] - self.offset["x"])

        self.chara_checkConditions.append(CharaCheckCondition(func_name, absolute_pos, dir, execution_info, comment_window_info))
        self.event_map[pos[0], pos[1]] = self.ISEVENT

    def addExpressionToCharaExpression(self, crntRoomID: str, detail: TempExpressionDetail, line: int, func_name: str):
        if crntRoomID not in self.chara_expressions:
            # まだ現在の部屋の計算式キャラが作られていなかったら作る
            local_y, local_x, height, width = self.room_info[crntRoomID]["room_size"]
            y, x = self.pick_random_space_pos_from_map(self.event_map[local_y+self.offset["y"]+1:local_y+self.offset["y"]+height-1, local_x+self.offset["x"]+1:local_x+self.offset["x"]+width-1])
            self.event_map[local_y+self.offset["y"]+y+1, local_x+self.offset["x"]+x+1] = self.ISEVENT
            self.chara_expressions[crntRoomID] = CharaExpression((local_y+y+1, local_x+x+1), func_name)
        self.chara_expressions[crntRoomID].detail_by_line[line] = detail

    # マップデータの生成
    def mapdata_generator(self, program_name: str, gvar_str: str, floor_map, is_universal: bool, line_info: dict[str, LineInfo], wall_chip_type: int):
        default_mapchips = [503, 343, 160, 32]
        floor_mapchip = random.choice([390, 43, 402, 31])
        floor_map = np.where(floor_map == 0, floor_mapchip, floor_map) 
        # 390 = gray thick brick, 43 = grass floor, 402 = gray thin iron brick, or 31 = sand

        self.writeMapIni(program_name, self.player_init_local_pos, gvar_str)
        self.writeMapJson(program_name, floor_map, is_universal, default_mapchips[wall_chip_type], floor_mapchip)
        self.writeLineFile(program_name, line_info)

        plt.imshow(floor_map, cmap='gray', interpolation='nearest')
        plt.title(program_name)
        plt.savefig(f'{DATA_DIR}/{program_name}/bm_{program_name}.png')

    def create_func_warp(self, func_references: list[FuncReference]) -> list[FuncWarp]:
        func_warps: list[FuncWarp] = []
        for func in func_references:
            # 自作関数だけfunc_warpに登録する
            if "children" not in func:
                continue

            local_to_pos, args, line_start = self.func_warps[func["name"]].get_attributes()
            func_warps.append(
                FuncWarp(
                    name = func["name"], 
                    x = int(local_to_pos[1]+self.offset["x"]), 
                    y = int(local_to_pos[0]+self.offset["y"]), 
                    args = args, 
                    line = line_start, 
                    children = func["children"]
                )
            )
        
        return func_warps

    def create_treasure_func_warp(self, varNode: VarNode, func_groups: list[FuncWarpGroup | None]):
        if len(varNode["children"]):
            for child_varNode in varNode["children"]:
                self.create_treasure_func_warp(child_varNode, func_groups)
        else:
            func_warps = self.create_func_warp(varNode["funcs"])
            func_warp_group = FuncWarpGroup(
                name = varNode["name"], 
                func_warps = func_warps
            ) if func_warps else None
            
            func_groups.append(func_warp_group)

    def convert_to_comment_window_info(self, temp_comment_window_info: TempCommentWindowInfo | None) -> CommentWindowInfo | None:
        if temp_comment_window_info is None:
            return None

        return CommentWindowInfo(
            detail = temp_comment_window_info["detail"],
            hover = temp_comment_window_info["hover"],
            func_groups = [
                FuncWarpGroup(
                    name = func_group["name"], 
                    func_warps = self.create_func_warp(func_group["func"])
                ) if func_group else None
                for func_group in temp_comment_window_info["func_groups"]
            ],
            type = temp_comment_window_info["type"]
        )

    def create_treasure_event_info(self, treasure: Treasure):
        func_groups: list[FuncWarpGroup | None] = []
        self.create_treasure_func_warp(treasure.var_info["varNode"], func_groups)

        treasure_event = TreasureInfo(
            type = "TREASURE",
            x = int(treasure.local_pos[1]+self.offset["x"]),
            y = int(treasure.local_pos[0]+self.offset["y"]),
            name = treasure.name,
            start = treasure.var_info["start"],
            end = treasure.var_info["end"], 
            func_groups = func_groups, 
            func = treasure.func_name
        )

        return treasure_event

    def writeMapJson(self, program_name: str, bit_map, is_universal: bool, default_mapchip: int, floor_mapchip: int):
        events = []
        characters = []

        # カラーユニバーサルデザインの色
        universal_colors = [15000, 15001, 15089, 15120, 15157, 15162, 15164]

        # 変数アイテム宝箱の情報
        for treasure in self.treasures:
            events.append(self.create_treasure_event_info(treasure))

        # ワープイベントの情報
        for move_event in self.move_events:
            events.append(
                {
                    "type": "MOVE", 
                    "x": int(move_event.local_from_pos[1]+self.offset["x"]), 
                    "y": int(move_event.local_from_pos[0]+self.offset["y"]),
                    "func": move_event.func_name,
                    "dest_x": int(move_event.local_to_pos[1]+self.offset["x"]), 
                    "dest_y": int(move_event.local_to_pos[0]+self.offset["y"]), 
                    "dest_map": program_name,
                    "execution_info": move_event.execution_info,
                    "detail": self.convert_to_comment_window_info(move_event.comment_window_info),
                    "mapchip": move_event.mapchip
                }
            )

        # 関数の戻りに応じたキャラクターの情報
        for chara_return in self.chara_returns:
            characters.append(
                {
                    "type": "CHARARETURN", 
                    "name": "15161" if chara_return.func_name else "15084", 
                    "x": int(chara_return.local_pos[1]+self.offset["x"]), 
                    "y": int(chara_return.local_pos[0]+self.offset["y"]),
                    "dir": 0, 
                    "movetype": 1, 
                    "message": ("Congraturations !! Here is A Goal !!" if self.is_english else "おめでとうございます!! ここがゴールです!!") if chara_return.func_name == "main" else (f"This is the end of function {chara_return.func_name} !!" if self.is_english else f"ここが {chara_return.func_name} の終了地点です!!"), 
                    "execution_info": chara_return.execution_info,
                    "detail": self.convert_to_comment_window_info(chara_return.comment_window_info),
                    "func": chara_return.func_name
                }
            )

        # 状態遷移のチェックキャラクターの情報
        for chara_checkCondition in self.chara_checkConditions:
            color = random.choice(universal_colors) if is_universal else random.randint(15102,15160)
            # y, x 
            # d, l, r, u = 0, 1, 2, 3
            move_dir_list: list[int] = []
            pos = (int(chara_checkCondition.local_pos[0] + self.offset["y"]), int(chara_checkCondition.local_pos[1] + self.offset["x"]))
            
            max_y, max_x = bit_map.shape
            if max_y >= pos[0] + 1 and bit_map[pos[0] + 1, pos[1]] not in [390, 43, 402, 31]:
                move_dir_list.append(0)
            if pos[1] >= 0 and bit_map[pos[0], pos[1] - 1] not in [390, 43, 402, 31]:
                move_dir_list.append(1)
            if max_x >= pos[1] + 1 and bit_map[pos[0], pos[1] + 1] not in [390, 43, 402, 31]:
                move_dir_list.append(2)
            if pos[0] >= 0 and bit_map[pos[0] - 1, pos[1]] not in [390, 43, 402, 31]:
                move_dir_list.append(3)

            move_dir = random.choice(move_dir_list)
            characters.append(
                {
                    "type": "CHARACHECKCONDITION", 
                    "name": str(color), 
                    "x": pos[1], 
                    "y": pos[0], 
                    "dir": chara_checkCondition.dir, 
                    "moveDir": move_dir,
                    "movetype": 1, 
                    "message": "Condition checked !! Get through here !!" if self.is_english else "条件文を確認しました！!　どうぞお通りください！!", 
                    "func": chara_checkCondition.func,
                    "execution_info": chara_checkCondition.execution_info, 
                    "detail": self.convert_to_comment_window_info(chara_checkCondition.comment_window_info)
                }
            )

        for chara_expression in self.chara_expressions.values():
            detail_by_line: dict[int, ExpressionDetail] = {}
            for firstLine, detail in chara_expression.detail_by_line.items():
                detail_by_line[firstLine] = ExpressionDetail(
                    expr = self.convert_to_comment_window_info(detail["expr"]), 
                    execution_info = detail["execution_info"],
                    vars = [
                        VarReference(
                            name = var_reference[0], 
                            line = var_reference[1]
                        )
                        for var_reference in detail["vars"]
                    ]
                )

            characters.append(
                {
                    "type": "CHARAEXPRESSION", 
                    "name": "15165", 
                    "x": int(chara_expression.local_pos[1]+self.offset["x"]), 
                    "y": int(chara_expression.local_pos[0]+self.offset["y"]), 
                    "dir": 0,
                    "movetype": 1, 
                    "message": "updated values of items !!" if self.is_english else "変数の値を新しい値で更新できました!!", 
                    "func": chara_expression.func, 
                    "comments": detail_by_line
                }
            )

        # 入口用のドアの情報 (開けようとする時に行数を確認する)
        for door in self.doors:
            events.append(
                {
                    "type": "SDOOR", 
                    "x": int(door.local_pos[1]+self.offset["x"]), 
                    "y": int(door.local_pos[0]+self.offset["y"]), 
                    "door_name": door.name, 
                    "dir": door.dir
                }
            )

        with open(f'{DATA_DIR}/{program_name}/{program_name}.json', 'w') as f:
            fileContent = {
                "row": bit_map.shape[0], 
                "col": bit_map.shape[1], 
                "default": default_mapchip, 
                "floor": floor_mapchip, 
                "map": bit_map.astype(int).tolist(), 
                "characters": characters, 
                "events": events
            }

            self.check_data_format_is_true(fileContent)
            json.dump(fileContent, f) 

        with open(f'{DATA_DIR}/{program_name}/{program_name}_variables.json', 'w') as f:
            json.dump(
                {
                    "declaration": self.execution_comment_handler.variable_comments, 
                    "expr": self.execution_comment_handler.create_non_varialble_execution_comments()
                }, f
            ) 

    # jsonファイルに登録する要素の形式がjsonに適したものであるかを確認するためのメソッド
    def check_data_format_is_true(self, obj, path="root"):
        if isinstance(obj, np.integer):
            print(f"np.integer found at: {path}")
        elif isinstance(obj, dict):
            for k, v in obj.items():
                self.check_data_format_is_true(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                self.check_data_format_is_true(v, f"{path}[{i}]")
        elif isinstance(obj, set):
            sys.exit(f"error in the set\nits detail is {obj}")

    def writeMapIni(self, program_name, player_init_local_pos: tuple[int, int], gvarString):
        config = configparser.ConfigParser()

        config['screen'] = {
            'width': '1024',
            'height': '768'
        }

        config['game'] = {
            'player' : '15070',
            'player_x' : f'{player_init_local_pos[1]+self.offset["x"]}',
            'player_y' : f'{player_init_local_pos[0]+self.offset["y"]}',
            'map' : program_name,
            'items' : f"{gvarString}"
        }

        config['api'] = {
            'key': '13f94c514269aa86469bc7642a6387b8',
            'url': 'se.is.kit.ac.jp'
        }

        file_name = f'{DATA_DIR}/{program_name}/{program_name}.ini'
        with open(file_name, 'w') as f:
            config.write(f)

    def writeLineFile(self, program_name: str, line_info_dict: dict[str, LineInfo]):
        file_name = f'{DATA_DIR}/{program_name}/{program_name}_line.json'

        line_info_json = {
            func_name: LineInfoDataByFunc(
                lines = sorted(list(line_info.lines)),
                loops = line_info.loops,
                returns = sorted(list(line_info.returns)),
                stdins = sorted(list(line_info.stdins)),
                start = line_info.start,
                input = self.input_lines.get(func_name, {}), 
                file = self.file_lines.get(func_name, {}), 
                memory = self.memory_lines.get(func_name, {}), 
                string = self.str_lines.get(func_name, {})
            )
            for func_name, line_info in line_info_dict.items()
        }
        
        with open(file_name, 'w') as f:
            json.dump(line_info_json, f)

class CustomTile(Tile):
    def update_origin(self, current):
        """Update which tile this one came from."""
        self.came_from = current
        if current.came_from:
            if ((current.came_from.x == current.x == self.x) 
                or (current.came_from.y == current.y == self.y)):
                self.distance = current.distance + self.weight
            else:
                self.distance = current.distance + self.weight + 1
        else:
            self.distance = current.distance + self.weight

class CustomAStar(AStar):
    def __init__(self, world, event_map):
        super().__init__(world)
        self.event_map = event_map

    '''
    start_posからtarget_posを結ぶ「最短の」通路を一つ探索し、見つかったらその通路を構成するマスのリストを返す
    見つからなかったら空のマスのリストを返す
    リストの一要素はマスの座標(y,x)である
    '''
    def search(self, start_pos, target_pos) -> list[tuple[int, int]]:
        """A_Star (A*) path search algorithm"""
        start = CustomTile(*start_pos)
        self.open_tiles = set([start])
        self.closed_tiles = set()

        # while we still have tiles to search
        while len(self.open_tiles) > 0:
            # get the tile with the shortest distance
            tile = min(self.open_tiles)
            # check if we're there. Happy path!
            if tile.pos == target_pos:
                return self.rebuild_path(tile)
            # search new ways in the neighbor's tiles.
            self.search_for_tiles(tile)

            self.close_tile(tile)
        # if we got here, path is blocked :(
        return []
    
    def get_neighbors(self, tile):
        """Return a list of available tiles around a given tile, avoiding contact with walls (1s)."""
        neighbors = []
        directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]  # 上下左右

        for dx, dy in directions:
            nx, ny = tile.x + dx, tile.y + dy

            # 範囲外は除外
            if not (1 <= nx < len(self.world) - 1 and 1 <= ny < len(self.world[0]) - 1):
                continue

            # 通行可能マスであることを確認
            if self.world[nx][ny] == 1 or self.event_map[nx][ny] == 2:
                continue

            # 周りのマスが部屋を構成していないかを確認
            if self.world[nx-1][ny] == 1 or self.world[nx+1][ny] == 1 or self.world[nx][ny-1] == 1 or self.world[nx][ny+1] == 1:
                continue

            neighbors.append(CustomTile(nx, ny))

        return neighbors

# フローチャートを辿って最終的にマップデータを生成する
class GenBitMap:
    PADDING2 = 4
    PADDING = 2
    SIZE_EXPAND = 5

    # 型指定はまた後で行う
    def __init__(
            self, 
            program_name: str, 
            func_info_dict: dict[str, FuncInfo], 
            gvar_info: list[str], 
            var_info: dict[str, VarInfo], 
            expr_node_info: dict[str, ExprNodeInfo], 
            room_size_info: dict[str, dict[str, int]], 
            gotoRoom_list: dict[str, dict[str, GotoRoomInfo]], 
            execution_info: dict[str, ExecutionInfo], 
            is_english: bool
        ):
        (self.graph, ) = pydot.core.graph_from_dot_file(f'{DATA_DIR}/{program_name}/{program_name}.dot') # このフローチャートを辿ってデータを作成していく
        self.nextNodeInfo: dict[str, list[tuple[str, str]]] = {}
        self.func_info_dict = func_info_dict
        self.gvar_info = gvar_info
        self.var_info = var_info
        self.expr_node_info = expr_node_info
        self.room_size_info = room_size_info
        self.floor_map = np.ones((20,20))
        self.only_room_map = np.ones((20,20))
        self.gotoRoom_list: dict[str, dict[str, GotoRoomInfo]] = gotoRoom_list # gotoラベルによるワープゾーンを作るための変数
        self.map_info = MapInfo(execution_info, is_english)
        self.func_name: str = ""
        self.is_english = is_english

    def trim_map_padding(self):
        # 上方向
        top = np.argmax(~np.all(self.floor_map == 1, axis=1))
        # 下方向（反転して調べる）
        bottom = self.floor_map.shape[0] - np.argmax(~np.all(self.floor_map[::-1] == 1, axis=1)) - 1
        # 左方向
        left = np.argmax(~np.all(self.floor_map == 1, axis=0))
        # 右方向
        right = self.floor_map.shape[1] - np.argmax(~np.all(self.floor_map[:, ::-1] == 1, axis=0)) - 1
        self.floor_map = self.floor_map[top-self.PADDING:bottom+self.PADDING2+1, left-self.PADDING:right+self.PADDING2+1]
        self.map_info.offset["y"] -= top-self.PADDING
        self.map_info.offset["x"] -= left-self.PADDING

    def set_mapchip(self, program_name: str, line_info_dict: dict[str, LineInfo], is_universal: bool):
        self.trim_map_padding()
        wallFlags = np.zeros(8, dtype=int)
        height, width = self.floor_map.shape
        # ここで壁パネルの種類を選択する
        wall_chip_type = random.randint(0, 3)
        if wall_chip_type == 3:
            # 値が1の位置のインデックスを取得
            ones_idx = np.argwhere(self.floor_map == 1)
            # その中からランダムにいくつか選ぶ（全体の2%）
            num_to_modify = len(ones_idx) // 50
            selected_idx = ones_idx[np.random.choice(len(ones_idx), num_to_modify, replace=False)]

            # まず全体を32に置き換え
            self.floor_map = np.where(self.floor_map == 1, 32, self.floor_map)

            # 選ばれた一部に32*100 + a の値を代入
            for (i, j) in selected_idx:
                a = np.random.randint(0, 100)
                self.floor_map[i, j] = 32 * 100 + a
        elif wall_chip_type == 2:
            # 値が1の位置のインデックスを取得
            ones_idx = np.argwhere(self.floor_map == 1)

            # その中からランダムにいくつか選ぶ（全体の2%）
            num_to_modify = len(ones_idx) // 50
            selected_idx = ones_idx[np.random.choice(len(ones_idx), num_to_modify, replace=False)]

            # まず全体を160に置き換え
            self.floor_map = np.where(self.floor_map == 1, 160, self.floor_map)

            # 選ばれた一部に花タイルを設置する
            for (i, j) in selected_idx:
                self.floor_map[i, j] = 16000
        elif wall_chip_type == 1:
            # 値が1の位置のインデックスを取得
            ones_idx = np.argwhere(self.floor_map == 1)

            # その中からランダムにいくつか選ぶ（全体の2%）
            num_to_modify = len(ones_idx) // 50
            selected_idx = ones_idx[np.random.choice(len(ones_idx), num_to_modify, replace=False)]

            # まず全体を343に置き換え
            self.floor_map = np.where(self.floor_map == 1, 343, self.floor_map)

            # 選ばれた一部に694(反転色タイル)を代入
            for (i, j) in selected_idx:
                self.floor_map[i, j] = 694
        else:
            bit_map_padded = np.pad(self.floor_map, pad_width=1, mode='constant', constant_values=0)
            for i in range(1, height+1):
                for j in range(1, width+1):
                    if bit_map_padded[i, j]:
                        wallFlags[:] = 0
                        #まず上下左右が壁であるかを確かめる(壁でないならそちら方向に仕切りが出来る)
                        if bit_map_padded[i, j-1] == 0:
                            #左壁フラグ
                            wallFlags[0] = 1
                        if bit_map_padded[i-1, j] == 0:
                            #上壁フラグ
                            wallFlags[1] = 1
                        if bit_map_padded[i, j+1] == 0:
                            #右壁フラグ
                            wallFlags[2] = 1
                        if bit_map_padded[i+1, j] == 0:
                            #下壁フラグ
                            wallFlags[3] = 1
                        #次に斜めを確かめる
                        if wallFlags[0] + wallFlags[1] == 0:
                            #左上
                            if bit_map_padded[i-1, j-1] == 0:
                                #左上角壁フラグ
                                wallFlags[4] = 1
                        if wallFlags[1] + wallFlags[2] == 0:
                            #右上
                            if bit_map_padded[i-1, j+1] == 0:
                                #右上角壁フラグ
                                wallFlags[5] = 1
                        if wallFlags[2] + wallFlags[3] == 0:
                            #右下
                            if bit_map_padded[i+1, j+1] == 0:
                                #右下角壁フラグ
                                wallFlags[6] = 1
                        if wallFlags[3] + wallFlags[0] == 0:
                            #左下
                            if bit_map_padded[i+1, j-1] == 0:
                                #左下角壁フラグ
                                wallFlags[7] = 1
                        bit_map_padded[i, j] = self.getFloorChipID(wallFlags, wall_chip_type)
            self.floor_map = bit_map_padded[1:height+1, 1:width+1]

        self.map_info.mapdata_generator(program_name, self.set_gvar(), self.floor_map, is_universal, line_info_dict, wall_chip_type)

    def getFloorChipID(self, arr, wall_chip_type: int):
        floorChipID =  {
            (0, 0, 0, 0, 0, 0, 0, 0): 14,
            (1, 0, 0, 0, 0, 0, 0, 0): 13,
            (0, 1, 0, 0, 0, 0, 0, 0): 6,
            (1, 1, 0, 0, 0, 0, 0, 0): 5,
            (0, 0, 1, 0, 0, 0, 0, 0): 15,
            (1, 0, 1, 0, 0, 0, 0, 0): 12,
            (0, 1, 1, 0, 0, 0, 0, 0): 7,
            (1, 1, 1, 0, 0, 0, 0, 0): 4,
            (0, 0, 0, 1, 0, 0, 0, 0): 22,
            (1, 0, 0, 1, 0, 0, 0, 0): 21,
            (0, 1, 0, 1, 0, 0, 0, 0): 2,
            (1, 1, 0, 1, 0, 0, 0, 0): 1,
            (0, 0, 1, 1, 0, 0, 0, 0): 23,
            (1, 0, 1, 1, 0, 0, 0, 0): 20,
            (0, 1, 1, 1, 0, 0, 0, 0): 3,
            (1, 1, 1, 1, 0, 0, 0, 0): 0,
            (0, 0, 0, 0, 1, 0, 0, 0): 37,
            (0, 0, 1, 0, 1, 0, 0, 0): 33,
            (0, 0, 0, 1, 1, 0, 0, 0): 35,
            (0, 0, 1, 1, 1, 0, 0, 0): 17,
            (0, 0, 0, 0, 0, 1, 0, 0): 36,
            (1, 0, 0, 0, 0, 1, 0, 0): 32,
            (0, 0, 0, 1, 0, 1, 0, 0): 34,
            (1, 0, 0, 1, 0, 1, 0, 0): 16,
            (0, 0, 0, 0, 1, 1, 0, 0): 40,
            (0, 0, 0, 1, 1, 1, 0, 0): 18,
            (0, 0, 0, 0, 0, 0, 1, 0): 28,
            (1, 0, 0, 0, 0, 0, 1, 0): 24,
            (0, 1, 0, 0, 0, 0, 1, 0): 26,
            (1, 1, 0, 0, 0, 0, 1, 0): 8,
            (0, 0, 0, 0, 1, 0, 1, 0): 45,
            (0, 0, 0, 0, 0, 1, 1, 0): 42,
            (1, 0, 0, 0, 0, 1, 1, 0): 10,
            (0, 0, 0, 0, 1, 1, 1, 0): 38,
            (0, 0, 0, 0, 0, 0, 0, 1): 29,
            (0, 1, 0, 0, 0, 0, 0, 1): 27,
            (0, 0, 1, 0, 0, 0, 0, 1): 25,
            (0, 1, 1, 0, 0, 0, 0, 1): 9,
            (0, 0, 0, 0, 1, 0, 0, 1): 43,
            (0, 0, 1, 0, 1, 0, 0, 1): 19,
            (0, 0, 0, 0, 0, 1, 0, 1): 44,
            (0, 0, 0, 0, 1, 1, 0, 1): 39,
            (0, 0, 0, 0, 0, 0, 1, 1): 41,
            (0, 1, 0, 0, 0, 0, 1, 1): 11,
            (0, 0, 0, 0, 1, 0, 1, 1): 31,
            (0, 0, 0, 0, 0, 1, 1, 1): 30,
            (0, 0, 0, 0, 1, 1, 1, 1): 46
        }

        # floorGrassChipID =  {
        #     (0, 0, 0, 0, 0, 0, 0, 0): 113,
        #     (1, 0, 0, 0, 0, 0, 0, 0): 114,
        #     (0, 1, 0, 0, 0, 0, 0, 0): 119,
        #     (1, 1, 0, 0, 0, 0, 0, 0): 120,
        #     (0, 0, 1, 0, 0, 0, 0, 0): 115,
        #     (1, 0, 1, 0, 0, 0, 0, 0): 113,
        #     (0, 1, 1, 0, 0, 0, 0, 0): 121,
        #     (1, 1, 1, 0, 0, 0, 0, 0): 113,
        #     (0, 0, 0, 1, 0, 0, 0, 0): 116,
        #     (1, 0, 0, 1, 0, 0, 0, 0): 117,
        #     (0, 1, 0, 1, 0, 0, 0, 0): 113,
        #     (1, 1, 0, 1, 0, 0, 0, 0): 113,
        #     (0, 0, 1, 1, 0, 0, 0, 0): 118,
        #     (1, 0, 1, 1, 0, 0, 0, 0): 113,
        #     (0, 1, 1, 1, 0, 0, 0, 0): 113,
        #     (1, 1, 1, 1, 0, 0, 0, 0): 113,
        #     (0, 0, 0, 0, 1, 0, 0, 0): 120,
        #     (0, 0, 1, 0, 1, 0, 0, 0): 115,
        #     (0, 0, 0, 1, 1, 0, 0, 0): 116,
        #     (0, 0, 1, 1, 1, 0, 0, 0): 118,
        #     (0, 0, 0, 0, 0, 1, 0, 0): 121,
        #     (1, 0, 0, 0, 0, 1, 0, 0): 114,
        #     (0, 0, 0, 1, 0, 1, 0, 0): 116,
        #     (1, 0, 0, 1, 0, 1, 0, 0): 117,
        #     (0, 0, 0, 0, 1, 1, 0, 0): 113,
        #     (0, 0, 0, 1, 1, 1, 0, 0): 116,
        #     (0, 0, 0, 0, 0, 0, 1, 0): 113,
        #     (1, 0, 0, 0, 0, 0, 1, 0): 114,
        #     (0, 1, 0, 0, 0, 0, 1, 0): 119,
        #     (1, 1, 0, 0, 0, 0, 1, 0): 120,
        #     (0, 0, 0, 0, 1, 0, 1, 0): 113,
        #     (0, 0, 0, 0, 0, 1, 1, 0): 113,
        #     (1, 0, 0, 0, 0, 1, 1, 0): 114,
        #     (0, 0, 0, 0, 1, 1, 1, 0): 113,
        #     (0, 0, 0, 0, 0, 0, 0, 1): 117,
        #     (0, 1, 0, 0, 0, 0, 0, 1): 119,
        #     (0, 0, 1, 0, 0, 0, 0, 1): 115,
        #     (0, 1, 1, 0, 0, 0, 0, 1): 121,
        #     (0, 0, 0, 0, 1, 0, 0, 1): 113,
        #     (0, 0, 1, 0, 1, 0, 0, 1): 115,
        #     (0, 0, 0, 0, 0, 1, 0, 1): 113,
        #     (0, 0, 0, 0, 1, 1, 0, 1): 113,
        #     (0, 0, 0, 0, 0, 0, 1, 1): 113,
        #     (0, 1, 0, 0, 0, 0, 1, 1): 119,
        #     (0, 0, 0, 0, 1, 0, 1, 1): 113,
        #     (0, 0, 0, 0, 0, 1, 1, 1): 113,
        #     (0, 0, 0, 0, 1, 1, 1, 1): 113
        # }

        floor_chip_list = [floorChipID[tuple(map(int, arr))] + 489, # wall-up
                           343,
                           160,
                           32]
        
        return floor_chip_list[wall_chip_type]
        # return floorGrassChipID[tuple(map(int, arr))] # stone-grass

    def start_tracking(self):
        self.set_next_node_info()

        self.func_name = "main"
        if (func_info := self.func_info_dict.pop(self.func_name, None)) is None:
            sys.exit("function \"main\" is not found")
        
        self.track_function_entry(func_info)

    def set_gvar(self):
        gvar_string_list: list[str] = []

        for gvarNodeID in self.gvar_info:
            varName = self.getNodeLabel(gvarNodeID)
            var_info = self.var_info[gvarNodeID]
            gvar_string_list.append(f"'{varName}' : {var_info["varNode"]}")

        return ''.join(["{", *gvar_string_list, "}"])

    def track_function_entry(self, func_info: FuncInfo):
        nodeID = func_info.start_nodeID
        self.createRoom(nodeID)
        
        # 関数呼び出しのワープ情報を更新
        # キャラクターではなくなるが、この情報は流用可能
        # ただし、ワープ元の部屋を表すノードは使わない(アイテムに対するワープ情報はアイテムの生成時にくっつける)
        self.map_info.func_warps[self.func_name] = FuncWarpBase(
            to_pos = self.map_info.set_func_warp_start_pos(nodeID), 
            args = func_info.args,
            line = func_info.start
        )

        for to_nodeID, edgeLabel in self.getNextNodeInfo(nodeID):
            self.track_function_body(nodeID, to_nodeID)
        
        for labelName, gotoRoom in self.gotoRoom_list[self.func_name].items():
            # gotoラベルの処理は後々考える
            sys.exit("our game still cannot accept c programs which have goto labels")

            to_nodeID = gotoRoom["to_nodeID"]
            fromNodeID_list = gotoRoom["fromNodeID"]
            for fromNodeID in fromNodeID_list:
                self.map_info.setWarpZone(
                    fromNodeID, 
                    to_nodeID, 
                    self.create_comment_window_info(
                        "cond-check",
                        detail=[
                            [f"move to label {labelName}"] 
                            if self.is_english else 
                            [f"ラベル: {labelName} に遷移します"]
                        ]
                    ),
                    self.func_name
                )

        self.map_info.set_player_init_pos(nodeID)

        for func_name in func_info.funcs:
            if (next_func_info := self.func_info_dict.pop(func_name, None)):
                self.func_name = func_name
                self.track_function_entry(next_func_info)

    # 繰り返し文の終わりだけはgetNextNodeInfoメソッドではなく、next_node_info.get(nodeID, [])で取得する
    def track_function_body(self, crntRoomID: str, nodeID: str, condition_comment_window_info: TempCommentWindowInfo | None = None):
        # if文とdo_while文とswitch文
        if self.getNodeShape(nodeID) == 'diamond':
            next_track_list: list[tuple[str, str, TempCommentWindowInfo | None]] = []

            if self.getNodeLabel(nodeID) == 'if':
                to_nodeID_info = self.getNextNodeInfo(nodeID)

                if len(to_nodeID_info) == 0:
                    return

                if len(to_nodeID_info) != 2:
                    sys.exit("number of nodes connected from an if node has to be 2")

                node_shapes = tuple([self.getNodeShape(to_nodeID) for to_nodeID, _ in to_nodeID_info])
                # (circle, diamond), (circle, doublecircle), (circle, terminator)
                if node_shapes[1] == "circle":
                    to_nodeID_info.reverse()
                    node_shapes = (node_shapes[1], node_shapes[0])
                elif node_shapes[0] != "circle":
                    sys.exit("a circle node has to be included")

                if node_shapes[1] not in ("diamond", "doublecircle", "terminator"):
                    sys.exit("a wrong node for false condition is included")
                
                to_nodeID = to_nodeID_info[0][0]
                self.createRoom(to_nodeID, crntRoomID)
                
                # 今までのif条件を繋げる
                if (expr_node_info := self.getExprNodeInfo(nodeID)) is None:
                    sys.exit(f"flowchart node of a true condition in if statement is not found")

                func_reference_group = FuncReferenceGroup(
                    name = f"{"condition" if self.is_english else "条件"}{self.map_info.execution_info[to_nodeID]["true_condition_index"] + 1}", 
                    func = expr_node_info["funcs"]
                ) if len(expr_node_info["funcs"]) else None

                comment_window_info = self.create_comment_window_info(
                    "cond-check",
                    detail = [
                        [f"{self.getNodeLabel(nodeID)}", f"of line {expr_node_info["line"]} is true"] 
                        if self.is_english else 
                        [f"{expr_node_info["line"]}行目の{self.getNodeLabel(nodeID)}文の", "が真"]
                    ], 
                    hover = [
                        expr_node_info["comments"]
                    ],
                    func_reference_group = func_reference_group, 
                    base_comment_window_info=condition_comment_window_info
                )

                # if true の条件だけ登録しておく
                self.map_info.execution_comment_handler.register_if_condition_comment(
                    self.map_info.execution_info[to_nodeID]["line"],
                    expr_node_info["line"],
                    expr_node_info["comments"]
                )
                    
                self.createPath(
                    crntRoomID, 
                    to_nodeID, 
                    comment_window_info
                ) # 条件文の計算式を確かめる
                
                next_track_list.append((to_nodeID, to_nodeID, None))

                to_nodeID = to_nodeID_info[1][0]

                self.createRoom(to_nodeID, crntRoomID)
                if (expr_node_info := self.getExprNodeInfo(nodeID)) is None:
                    sys.exit("false node in if statement is not found")

                # else if の条件への繋がり
                if node_shapes[1] == "diamond":
                    # 今までのif条件を繋げる (今まで+今回の条件が偽の場合を次のdiamondに渡す)
                    comment_window_info = self.create_comment_window_info(
                        "cond-check", 
                        detail = [
                            [f"{self.getNodeLabel(nodeID)}", f"of line {expr_node_info["line"]} is false"] 
                            if self.is_english else 
                            [f"{expr_node_info["line"]}行目の{self.getNodeLabel(nodeID)}文の", "が偽"]
                        ], 
                        hover = [
                            expr_node_info["comments"]
                        ],
                        func_reference_group = func_reference_group,
                        base_comment_window_info=condition_comment_window_info
                    )
                
                    next_track_list.append((crntRoomID, to_nodeID, comment_window_info))
                # else
                elif node_shapes[1] == "doublecircle":
                    comment_window_info = self.create_comment_window_info(
                        "cond-check", 
                        detail=[
                            [f"{self.getNodeLabel(nodeID)}", f"of line {expr_node_info["line"]} is false"] 
                            if self.is_english else 
                            [f"{expr_node_info["line"]}行目の{self.getNodeLabel(nodeID)}文の", "が偽"]
                        ], 
                        hover=[
                            expr_node_info["comments"]
                        ],
                        func_reference_group=func_reference_group,
                        base_comment_window_info=condition_comment_window_info
                    )

                    self.createPath(
                        crntRoomID, 
                        to_nodeID, 
                        comment_window_info
                    ) # 条件文の計算式を確かめる
                    
                    next_track_list.append((to_nodeID, to_nodeID, None))
                # terminator = non else
                else:
                    comment_window_info = self.create_comment_window_info(
                        "cond-check", 
                        detail = [
                            [f"{self.getNodeLabel(nodeID)}", f"of line {expr_node_info["line"]} is false"] 
                            if self.is_english else 
                            [f"{expr_node_info["line"]}行目の{self.getNodeLabel(nodeID)}文の", "が偽"]
                        ], 
                        hover = [
                            expr_node_info["comments"]
                        ],
                        func_reference_group=func_reference_group,
                        base_comment_window_info=condition_comment_window_info
                    )

                    # self.track_function_body(crntRoomID, to_nodeID, comment_window_info)
                    next_track_list.append((crntRoomID, to_nodeID, comment_window_info))

            elif self.getNodeLabel(nodeID) == 'do':
                self.createRoom(nodeID, crntRoomID)

                self.createPath(
                    crntRoomID, 
                    nodeID, 
                    None
                )

                to_nodeID_info = self.getNextNodeInfo(nodeID)

                if len(to_nodeID_info) == 0:
                    return
                
                if len(to_nodeID_info) != 2 or (self.getNodeShape(to_nodeID_info[0][0]), self.getNodeShape(to_nodeID_info[1][0])) not in ("circle", "doublecircle"):
                    sys.exit("wrong number or type nodes are connected from a do-while condition node")

                crntRoomID = nodeID

                if (expr_node_info := self.getExprNodeInfo(nodeID)) is None:
                    sys.exit(f"flowchart node of a false condition in do-while statement is not found")
                
                func_reference_group = FuncReferenceGroup(   
                    name = f"do-while condition line of {expr_node_info["line"]}" if self.is_english else f"{expr_node_info["line"]}行目のdo-while条件", 
                    func = expr_node_info["funcs"]
                ) if len(expr_node_info["funcs"]) else None

                for to_nodeID, edgeLabel in to_nodeID_info:
                    self.createRoom(to_nodeID, crntRoomID)

                    if self.getNodeShape(to_nodeID) == 'circle':
                        self.map_info.execution_comment_handler.register_do_while_condition_comment(
                            self.map_info.execution_info[to_nodeID]["line"], 
                            expr_node_info["comments"]
                        )

                        self.map_info.setWarpZone(
                            crntRoomID, 
                            to_nodeID,
                            self.create_comment_window_info(
                                "cond-check",
                                detail = [
                                    ["do-while", f"of line {expr_node_info["line"]} is true"] 
                                    if self.is_english else 
                                    [f"{expr_node_info["line"]}行目のdo-while文の", "が真"]
                                ], 
                                hover = [
                                    expr_node_info["comments"]
                                ],
                                func_reference_group = func_reference_group, 
                            ),
                            self.func_name
                        )
                        
                    else: # double circle node (while false)
                        self.createPath(
                            crntRoomID, 
                            to_nodeID, 
                            self.create_comment_window_info(
                                "cond-check",
                                detail = [
                                    ["do-while", f"of line {expr_node_info["line"]} is false"] 
                                    if self.is_english else 
                                    [f"{expr_node_info["line"]}行目のdo-while文の", "が偽"]
                                ], 
                                hover = [
                                    expr_node_info["comments"]
                                ],
                                func_reference_group = func_reference_group,
                            )
                        )
                    
                    next_track_list.append((to_nodeID, to_nodeID, None))

            else: # switch
                if (switch_expr_node_info := self.getExprNodeInfo(nodeID)) is None:
                    sys.exit("flowchart node of a switch statement condition is not found")
                
                to_nodeID_info = self.getNextNodeInfo(nodeID)

                if len(to_nodeID_info) == 0:
                    return

                if any(self.getNodeShape(to_nodeID) != "invtriangle" for to_nodeID, _ in to_nodeID_info):
                    sys.exit("wrong type nodes are connected from a switch condition node")

                self.map_info.execution_comment_handler.register_switch_condition_comment(
                    switch_expr_node_info["line"],
                    switch_expr_node_info["comments"]
                )

                func_reference_group = FuncReferenceGroup(
                    name = f"switch condition line of {switch_expr_node_info["line"]}" if self.is_english else f"{switch_expr_node_info["line"]}行目のswitch条件",
                    func = switch_expr_node_info["funcs"]
                ) if len(switch_expr_node_info["funcs"]) else None

                end_nodeID: str | None = None

                has_default = False
                # caseラベルをグループごとに格納するリスト
                case_group_list: list[tuple[str, list[ExprNodeInfo], int | None]] = []

                for to_nodeID, _ in to_nodeID_info:
                    if self.getNodeLabel(to_nodeID) == "end":
                        end_nodeID = to_nodeID
                        continue

                    default_line: int | None = None
                    case_expr_node_info_list: list[ExprNodeInfo] = []
                    while True:
                        if (temp_node_info := self.nextNodeInfo.get(to_nodeID, None)) is None:
                            break
                        temp_nodeID, _ = temp_node_info[0]
                        expr_node_info = self.getExprNodeInfo(to_nodeID)

                        # caseラベルノード
                        if expr_node_info is not None:
                            case_expr_node_info_list.append(expr_node_info)
                        # defaultラベルノード
                        else:
                            if has_default:
                                sys.exit("default label cannot be overlapped")

                            default_label = self.getNodeLabel(to_nodeID)
                            if len(default_label) < 4:
                                sys.exit("default label for switch statement is not found")
                            split_label_str = default_label[1:-1].split(',')

                            if len(split_label_str) != 2 or split_label_str[0] != "default":
                                sys.exit("unknown node is found for switch default label")
                            try:
                                default_line = int(split_label_str[1])
                            except:
                                sys.exit("line of default label is not found")
                            has_default = True

                        if self.getNodeShape(temp_nodeID) != 'invtriangle':
                            break

                        to_nodeID = temp_nodeID

                    if to_nodeID not in self.map_info.execution_info:
                        sys.exit("execution info for a case label is not found")

                    case_group_list.append((to_nodeID, case_expr_node_info_list, default_line))

                if len(case_group_list) == 0:
                    sys.exit("switch statement has to have one or more case labels")

                case_group_list.sort(
                    key=lambda case_group: self.map_info.execution_info[case_group[0]]["true_case_index"]
                )

                for case_index, (to_nodeID, case_expr_node_info_list, default_line) in enumerate(case_group_list):
                    if case_index != self.map_info.execution_info[to_nodeID]["true_case_index"]:
                        sys.exit("true case index does not match the order of case label groups")

                    condition_detail_list = [
                        [f"switch condition of line {switch_expr_node_info["line"]}", "matches"]
                        if self.is_english else 
                        [f"{switch_expr_node_info["line"]}行目のswitch文の", "が"]
                    ]

                    final_case_index = len(case_expr_node_info_list) - 1

                    for i, case_expr_node_info in enumerate(case_expr_node_info_list):
                        condition_detail = [f"case of line {case_expr_node_info["line"]}" if self.is_english else f"{case_expr_node_info["line"]}行のcase"]
                        condition_detail.append(
                            (
                                "" 
                                if self.is_english else 
                                "に合致する"
                            )
                            if i == final_case_index else
                            (
                                "OR" 
                                if self.is_english else 
                                "または"
                            )
                        )

                        condition_detail_list.append(condition_detail)

                    if default_line is not None:
                        if len(condition_detail_list) == 1:
                            condition_detail_list.append(
                                [
                                    f"default of line {default_line}\n(unmatches any case labels)" 
                                    if self.is_english else 
                                    f"{default_line}行目のdefaultに合致する\n(他のいずれのcaseにも合致しない)"
                                ]
                            )
                        else: # 他のcaseがある場合、それに続く文にする
                            condition_detail_list.append(
                                [
                                    f"OR ALTENATIVELY, matches default of line {default_line}\n(unmatches any case labels)"
                                    if self.is_english else 
                                    f"もしくは、{default_line}行目のdefaultに合致する\n(他のいずれのcaseにも合致しない)"
                                ]
                            )
                            
                        self.map_info.execution_comment_handler.register_default_index(
                            switch_expr_node_info["line"],
                            case_index
                        )

                    self.map_info.execution_comment_handler.register_case_comment(
                        switch_expr_node_info["line"], 
                        case_expr_node_info_list
                    )

                    hover = [
                        switch_expr_node_info["comments"], 
                        *[case_expr_node_info["comments"] for case_expr_node_info in case_expr_node_info_list]
                    ]

                    comment_window_info = self.create_comment_window_info(
                        "cond-check",
                        detail = condition_detail_list, 
                        hover = hover,
                        func_reference_group = func_reference_group
                    )

                    self.createRoom(to_nodeID, crntRoomID)

                    self.map_info.setWarpZone(
                        crntRoomID,
                        to_nodeID, 
                        comment_window_info, 
                        self.func_name, 
                    )

                    in_case_nodeID_info = self.getNextNodeInfo(to_nodeID)
                    if len(in_case_nodeID_info) != 1:
                        sys.exit("number of child nodes connected from case node has to be 1")

                    next_track_list.insert(0, (to_nodeID, in_case_nodeID_info[0][0], None))

                if end_nodeID is not None:
                    comment_window_info = self.create_comment_window_info(
                        "cond-check",
                        detail = [
                            ["switch condition", f"of line {switch_expr_node_info["line"]} is not true for any cases"]
                        ] 
                        if self.is_english else 
                        [
                            [f"{switch_expr_node_info["line"]}行目のswitch文条件の", "がいずれのcaseにも該当しない"]
                        ], 
                        hover = [
                            switch_expr_node_info["comments"]
                        ],
                        func_reference_group=func_reference_group,
                    )

                    self.map_info.setWarpZone(
                        crntRoomID, 
                        end_nodeID, 
                        comment_window_info, 
                        self.func_name, 
                    )

                    in_case_nodeID_info = self.getNextNodeInfo(end_nodeID)
                    if len(in_case_nodeID_info) != 1:
                        sys.exit("number of child nodes connected from case node has to be 1")

                    next_track_list.insert(0, (end_nodeID, in_case_nodeID_info[0][0], None))

            for next_track in next_track_list:
                self.track_function_body(*next_track)

            return

        # if文の終点でワープゾーンを作る
        elif self.getNodeShape(nodeID) == 'terminator':
            to_nodeID_info = self.getNextNodeInfo(nodeID)

            if len(to_nodeID_info) != 1:
                sys.exit("number of child nodes connected from a terminator node has to be 1")

            to_nodeID, _ = to_nodeID_info[0]

            next_of_if_end_conclusion_node_info: list[tuple[str, str]] | None = None
            # 今まではifの終了ごとにワープゾーンを作っていたが、ifの終了が連続する場合に対応できなかったので、連続するノードは飛ばすようにした
            while True:
                # ifの終点ノードは再び通ることが必要な場合が存在するので、ノード情報をポップしてしまうgetNextNodeInfoメソッドは使わない
                if (next_of_if_end_conclusion_node_info := self.nextNodeInfo.get(to_nodeID, None)) is None:
                    break
                if len(next_of_if_end_conclusion_node_info) != 1:
                    sys.exit("number of nodes which are derived from a if-end conclusion node has to be 1")
                next_nodeID, _ = next_of_if_end_conclusion_node_info[0]
                if self.getNodeShape(next_nodeID) != 'terminator':
                    self.createRoom(to_nodeID, crntRoomID)
                    break
                # if-endノードの次は同じ階層のif-endノードをまとめるノードに繋がっている
                if (if_end_conclusion_node_info := self.nextNodeInfo.get(next_nodeID, None)) is None:
                    sys.exit("node info which should be derived from a if-end node is not found")
                if len(if_end_conclusion_node_info) != 1:
                    sys.exit("number of nodes which are derived from a if-end node has to be 1")
                to_nodeID, _ = if_end_conclusion_node_info[0]

            self.map_info.setWarpZone(
                crntRoomID, 
                to_nodeID, 
                condition_comment_window_info, 
                self.func_name,
                warpNodeID=nodeID
            )

            '''
            next_of_if_end_conclusion_node_infoがある場合 = if文の終了ノード以降のノードを初めて通る場合なので、そこからASTのトラッキングを再開する
            二回目以降(他のif条件でこの終了ノードを辿る時)にまたnext_of_if_end_conclusion_node_infoが存在すると、上の繰り返し処理で再び同じ部屋を作ってしまうので、
            next_of_if_end_conclusion_node_infoを取得したto_nodeIDをgetNextNodeInfoにかけて再びそのnext_of_if_end_conclusion_node_infoを取得できないようにする
            '''
            if next_of_if_end_conclusion_node_info is not None:
                self.track_function_body(to_nodeID, self.getNextNodeInfo(to_nodeID)[0][0])

            return
        
        # while文とfor文は最終ノードからワープで戻る必要があるので、現在の部屋ノードのID(戻り先)を取得する
        elif self.getNodeShape(nodeID) == 'pentagon':
            condition_type = self.getNodeLabel(nodeID)
            if condition_type not in ("while", "for"):
                sys.exit("label of a pentagon node is incorrect")

            # 条件文以前の処理を同部屋に含めてはいけない
            self.createRoom(nodeID, crntRoomID)

            to_nodeID_info = self.getNextNodeInfo(nodeID)
            
            if len(to_nodeID_info) != 2 or (self.getNodeShape(to_nodeID_info[0][0]), self.getNodeShape(to_nodeID_info[1][0])) not in ("circle", "doublecircle"):
                sys.exit(f"wrong number or type nodes are connected from a {condition_type} condition node ")

            # 一回目ではWhileのTrueとFalseノードを取得できるので解析する
            nodeID_list: list[str] = []

            # condition_typeがforの場合は、expr_node_infoがない場合もある? (今後考える必要あり?)
            # → conditionがなくてもline情報だけを持つexpr_node_infoを登録することにした
            if (expr_node_info := self.getExprNodeInfo(nodeID)) is None:
                sys.exit(f"flowchart node of {condition_type} condition is not found")

            func_reference_group = FuncReferenceGroup(
                name = f"{condition_type} condition line of {expr_node_info["line"]}" if self.is_english else f"{expr_node_info["line"]}行目の{condition_type}条件",
                func = expr_node_info["funcs"]
            ) if len(expr_node_info["funcs"]) else None

            if condition_type == "while":
                self.map_info.execution_comment_handler.register_while_condition_comment(
                    expr_node_info["line"], 
                    expr_node_info["comments"]
                )
            else: # for
                self.map_info.execution_comment_handler.register_for_comment(
                    expr_node_info["line"],
                    "condition",
                    expr_node_info["comments"]
                )

            # エッジの順番がランダムで想定通りに解析されない可能性があるので入れ替える
            for to_nodeID, edgeLabel in to_nodeID_info:
                self.createRoom(to_nodeID, nodeID)

                shape = self.getNodeShape(to_nodeID)

                is_true = shape == "circle"

                self.createPath(
                    nodeID, 
                    to_nodeID, 
                    self.create_comment_window_info(
                        "cond-check",
                        detail = [
                            [{condition_type}, f"of line {expr_node_info["line"]} is {"true" if is_true else "false"}"]
                        ] 
                        if self.is_english else 
                        [
                            [f"{expr_node_info["line"]}行目の{condition_type}文の", f"が{"真" if is_true else "偽"}"]
                        ], 
                        hover = [
                            expr_node_info["comments"]
                        ],
                        func_reference_group = func_reference_group,
                    )
                )

                nodeID_list.insert(0, to_nodeID) if is_true else nodeID_list.append(to_nodeID)
                    
            # while or forの領域に入る (whileIn or forIn) (ただし、今後 whileIn, forInの確認キャラを消去する見込み)
            self.createPath(
                crntRoomID, 
                nodeID, 
                None
            )

            # true
            self.track_function_body(nodeID_list[0], nodeID_list[0])
            # false
            self.track_function_body(nodeID_list[1], nodeID_list[1])

        # while文とfor文のワープ元である部屋のIDを取得する
        elif self.getNodeShape(nodeID) == 'parallelogram':
            loopBack_nodeID_info = self.nextNodeInfo.get(nodeID)

            if loopBack_nodeID_info is None:
                sys.exit("there is a loopBackID at a parallelogram node")
            if len(loopBack_nodeID_info) != 1:
                sys.exit("number of nodes connected from a parallelogram node has to be 1")
            
            loopBackID, _ = loopBack_nodeID_info[0]

            if self.getNodeShape(loopBackID) != "pentagon":
                sys.exit("shape of loopBack node has to be pentagon")
            if (loopBack_expr_node_info := self.getExprNodeInfo(loopBackID)) is None:
                sys.exit(f"flowchart node of change expression statement in {self.getNodeLabel(loopBackID)} is not found")
            if int(self.getNodeLabel(nodeID)) != loopBack_expr_node_info["line"]:
                sys.exit("line of execution looped back is incorrect")

            # for(A; B; C) について、Cがある場合　と　それ以外 (forでCがない場合と、whileの場合)で区別する
            change_expr_node_info = self.getExprNodeInfo(nodeID)
            if change_expr_node_info is not None:
                comment_window_info = self.create_comment_window_info(
                    "cond-in-change",
                    detail = [
                        [f"if next is check of {self.getNodeLabel(loopBackID)}", f"in line {loopBack_expr_node_info["line"]}"], 
                        ["execute", f"of line {loopBack_expr_node_info["line"]}"]
                    ]
                    if self.is_english else 
                    [
                        [f"次が{loopBack_expr_node_info["line"]}行目の{self.getNodeLabel(loopBackID)}文の", "の真偽の確認処理なら"], 
                        [f"{loopBack_expr_node_info["line"]}行目の", "を実行して"]
                    ], 
                    hover = [
                        loopBack_expr_node_info["comments"], 
                        change_expr_node_info["comments"]
                    ],
                    func_reference_group = FuncReferenceGroup(
                        name = f"update expression of for statement line of {change_expr_node_info["line"]}" if self.is_english else f"{change_expr_node_info["line"]}行目のfor文の更新式",
                        func = change_expr_node_info["funcs"]
                    ) if len(change_expr_node_info["funcs"]) else None
                ) 
                self.map_info.execution_comment_handler.register_for_comment(
                    change_expr_node_info["line"],
                    "change",
                    change_expr_node_info["comments"]
                )
            else:
                comment_window_info = None
            
            self.map_info.setWarpZone(
                crntRoomID, 
                loopBackID, 
                comment_window_info, 
                self.func_name,
                nodeID if change_expr_node_info is not None else None
            )

        # 話しかけると関数の遷移元に戻るようにする
        elif self.getNodeShape(nodeID) == 'lpromoter':
            if (expr_node_info := self.getExprNodeInfo(nodeID)) is None:
                sys.exit(f"flowchart node of change expression statement in return statement is not found")

            # まだvoidができていない? 後でvoidのやり方を考える
            if expr_node_info["line"] is None:
                sys.exit("our game does not accept void function yet")

            comment_window_info = self.create_comment_window_info(
                "end",
                detail = [
                    ["get a return value executing", f"of line {expr_node_info["line"]}"]
                    if self.is_english else 
                    [f"{expr_node_info["line"]}行目の", "を実行した値を戻り値として取得します"]
                ], 
                hover = [
                    expr_node_info["comments"]
                ],
                func_reference_group = FuncReferenceGroup(
                    name = f"return statement line of {expr_node_info["line"]}" if self.is_english else f"{expr_node_info["line"]}行目のreturn文",
                    func = expr_node_info["funcs"]
                ) if len(expr_node_info["funcs"]) else None
            )

            self.map_info.setCharaReturn(
                crntRoomID,
                nodeID,
                comment_window_info,
                self.func_name, 
            )

            self.map_info.execution_comment_handler.register_return_comment(
                expr_node_info["line"],
                expr_node_info["comments"]
            )

        # 変数宣言ノードから遷移するノードの種類で変数のタイプを分ける
        elif self.getNodeShape(nodeID) == 'signature':
            var_info = self.var_info[nodeID]
            self.createRoom(nodeID, crntRoomID)
            # 変数用に部屋を作る必要があるなら作る
            if nodeID in self.map_info.room_info:
                self.createPath(
                    crntRoomID, 
                    nodeID, 
                    None
                )
                crntRoomID = nodeID
            self.map_info.setItemBox(crntRoomID, self.getNodeLabel(nodeID), var_info, self.func_name)
            self.map_info.execution_comment_handler.register_variable_comment(var_info)
        
        # for文の初期値で変数の初期化がある場合はアイテムを作る
        elif self.getNodeShape(nodeID) == 'invhouse':
            to_nodeID_info = self.getNextNodeInfo(nodeID)

            if len(to_nodeID_info) == 0:
                return

            self.createRoom(nodeID, crntRoomID)

            next_nodeID: str | None = None
            # (変数宣言ではない)初期化式がある場合
            if (initializer_expr_node_info := self.getExprNodeInfo(nodeID)) is not None:
                self.map_info.execution_comment_handler.register_for_comment(
                    initializer_expr_node_info["line"],
                    "initializer",
                    initializer_expr_node_info["comments"]
                )

                comment_window_info = self.create_comment_window_info(
                    "cond-in",
                    detail = [
                        [f"if next is initializer of for statement", f"in line {initializer_expr_node_info["line"]}"]
                    ]
                    if self.is_english else 
                    [
                        [f"次が{initializer_expr_node_info["line"]}行目のfor文の", "の初期化処理なら"]
                    ], 
                    hover = [
                        initializer_expr_node_info["comments"]
                    ],
                    func_reference_group = FuncReferenceGroup(
                        name = f"initializer for statement line of {initializer_expr_node_info["line"]}" if self.is_english else f"{initializer_expr_node_info["line"]}行目のfor文の初期化",
                        func = initializer_expr_node_info["funcs"]
                    ) if len(initializer_expr_node_info["funcs"]) else None
                )

                self.createPath(
                    crntRoomID, 
                    nodeID,
                    comment_window_info
                )
                
                crntRoomID = nodeID

                if len(to_nodeID_info) != 1:
                    sys.exit("number of nodes which are connected from a for-initializer node has to be 1")

                next_nodeID = to_nodeID_info[0][0]
                if self.getNodeShape(to_nodeID) != 'pentagon':
                    sys.exit("shape of nodes connected from a for-initializer node without var-initializer have to be 'pentagon")
            # (変数宣言ではない)初期化式がない場合 → 変数宣言があるなら、その変数に当たる宝箱を作る。
            else:
                var_decl_nodeID: str | None = None
                for to_nodeID, _ in to_nodeID_info:
                    if self.getNodeShape(to_nodeID) == 'signature':
                        sys.exit("this game does not allow variable initializers in for statement initializer")
                        if var_decl_nodeID is not None:
                            sys.exit("number of signature nodes which are connected from a for-initializer node has to be 1")
                        var_decl_nodeID = to_nodeID
                    elif self.getNodeShape(to_nodeID) == 'pentagon':
                        if next_nodeID is not None:
                            sys.exit("number of nodes which are connected from a for-initializer node execpt of a signature node has to be 1")
                        next_nodeID = to_nodeID
                    else:
                        sys.exit("shape of nodes connected from a for-initializer node have to be 'signature' or 'pentagon")

                self.createPath(
                    crntRoomID, 
                    nodeID,
                    None
                )
                
                crntRoomID = nodeID

                if var_decl_nodeID is not None:
                    to_nodeID = var_decl_nodeID

                    var_info_list: list[VarInfo] = []
                    while True:
                        if (var_info := self.var_info.get(to_nodeID)) is None:
                            sys.exit("var_info of a variable declaration of for initializer is not found")
                        if (var_expr_node_info := self.getExprNodeInfo(to_nodeID)) is None:
                            sys.exit("expr node info in scalar varialbe is not found")
                        # ここに関数の呼び出しのコメントが含まれている場合を考える必要がある
                        self.map_info.setItemBox(crntRoomID, self.getNodeLabel(to_nodeID), var_info, self.func_name)
                        var_info_list.append(var_info)

                        var_nodeID_info = self.getNextNodeInfo(nodeID)
                        if len(var_nodeID_info) == 0:
                            break
                        if len(var_nodeID_info) != 1:
                            sys.exit("error in number of nodes connected fron var node")

                        to_nodeID, _ = var_nodeID_info[0]
                        if self.getNodeShape(to_nodeID) != 'signature':
                            sys.exit("error in shape of node \"signature\"")

                    if len(var_info_list):
                        self.map_info.execution_comment_handler.register_for_var_initializer_comment(
                            int(self.getNodeLabel(nodeID)),
                            var_info_list
                        )
                
            # for文の条件文に当たるノードが無いのはおかしい
            if next_nodeID is None:
                sys.exit("next node of a for initializer node is not found")

            # 条件文の解析に進んでいく
            self.track_function_body(crntRoomID, next_nodeID)
            return

        # break, continue
        elif self.getNodeShape(nodeID) == 'hexagon':
            # warpNodeIDが必要なのでここで解析する
            if nodeID not in self.map_info.execution_info:
                sys.exit("an execution information of a line breaker is not found")

            next_nodeID_info = self.getNextNodeInfo(nodeID)

            if len(next_nodeID_info) != 1:
                sys.exit("only one node has to be connected from a hexagon node")

            nextNodeID, edgeLabel = next_nodeID_info[0]

            if self.getNodeLabel(nodeID) == "continue":
                if self.getNodeShape(nextNodeID) == 'parallelogram':
                    loopBack_nodeID_info = self.nextNodeInfo.get(nodeID)

                    if loopBack_nodeID_info is None:
                        sys.exit("there is a loopBackID at a parallelogram node")
                    if len(loopBack_nodeID_info) != 1:
                        sys.exit("number of nodes connected from a parallelogram node has to be 1")
                    
                    loopBackID, _ = loopBack_nodeID_info[0]

                    if self.getNodeShape(loopBackID) != "pentagon":
                        sys.exit("shape of loopBack node has to be pentagon")
                    if (expr_node_info := self.getExprNodeInfo(loopBackID)) is None:
                        sys.exit(f"flowchart node of change expression statement in {self.getNodeLabel(loopBackID)} is not found")
                    if int(self.getNodeLabel(nextNodeID)) != expr_node_info["line"]:
                        sys.exit("line of execution looped back is incorrect")

                    if condition_comment_window_info is not None:
                        sys.exit("there has not be comment_window_info here")

                    self.map_info.setWarpZone(
                        crntRoomID, 
                        loopBackID, 
                        self.create_comment_window_info(
                            "end",
                            detail = [
                                ["exit from the current loop statement by continue"] 
                                if self.is_english else 
                                ["continueで現在のループから脱出します"]
                            ]
                        ), 
                        self.func_name,
                        warpNodeID=nodeID
                    )

                    nextNodeID = loopBackID

                # continue → doWhile構文の場合
                elif self.getNodeShape(nextNodeID) == 'diamond':
                    self.createRoom(nextNodeID, crntRoomID)
                    if (expr_node_info := self.getExprNodeInfo(nextNodeID)) is None:
                        sys.exit(f"flowchart node of change expression statement in do-while statement is not found")

                    if condition_comment_window_info is not None:
                        sys.exit("there has not be comment_window_info here")

                    self.map_info.setWarpZone(
                        crntRoomID, 
                        nextNodeID, 
                        self.create_comment_window_info(
                            "end",
                            [
                                ["exit from the current loop statement by continue"] 
                                if self.is_english else 
                                ["continueで現在のループから脱出します"]
                            ]
                        ), 
                        self.func_name,
                        warpNodeID=nodeID
                    )
                
                else:
                    sys.exit("impossible node is found")

                self.map_info.execution_comment_handler.register_control_flow_comment(
                    self.map_info.execution_info[nodeID]["line"], 
                    "continue"
                )

            # breakのノードの場合
            elif self.getNodeLabel(nodeID) == "break":
                self.createRoom(nextNodeID, crntRoomID)
                self.map_info.setWarpZone(
                    crntRoomID, 
                    nextNodeID,
                    self.create_comment_window_info(
                        "end",
                        detail = [
                            [
                                "exit from the current loop statement by break" 
                                if self.is_english else 
                                "breakにより現在のループから脱出します"
                            ]
                        ]
                    ),
                    self.func_name,
                    warpNodeID=nodeID
                )

                self.map_info.execution_comment_handler.register_control_flow_comment(
                    self.map_info.execution_info[nodeID]["line"], 
                    "break"
                )
            else:
                sys.exit("unknown node is found")

            self.track_function_body(nextNodeID, nextNodeID)
            return
        
        # do while構文の最初の1回
        elif self.getNodeShape(nodeID) == 'invtrapezium':
            true_nodeID_info = self.getNextNodeInfo(nodeID)
            if len(true_nodeID_info) != 1:
                sys.exit("number of child nodes of do-while entry node has to be 1")
            trueNodeID, _ = true_nodeID_info
            # do-whileの条件真の部屋を作る
            self.createRoom(trueNodeID, crntRoomID)
            self.map_info.setWarpZone(
                crntRoomID, 
                trueNodeID,
                None,
                self.func_name,
                warpNodeID=nodeID
            )
            nodeID = trueNodeID
            crntRoomID = trueNodeID

        # switch構文の途中のcaseまたは末尾に接続する
        elif self.getNodeShape(nodeID) == 'invtriangle':
            case_expr_node_info_list = []
            to_nodeID = nodeID

            while True:
                if (tempNode_info := self.nextNodeInfo.get(to_nodeID, None)) is None:
                    break
                temp_nodeID, _ = tempNode_info[0]

                if (expr_node_info := self.getExprNodeInfo(to_nodeID)) is not None:
                    case_expr_node_info_list.append(expr_node_info["comments"])
                else:
                    case_expr_node_info_list = []

                if self.getNodeShape(temp_nodeID) != 'invtriangle' or self.getNodeLabel(to_nodeID) == 'end':
                    break

                to_nodeID = temp_nodeID
 
            self.createRoom(to_nodeID, crntRoomID)
            self.map_info.setWarpZone(
                crntRoomID,
                to_nodeID, 
                None, 
                self.func_name
            )

            next_nodeID_info = self.getNextNodeInfo(to_nodeID)
            if len(next_nodeID_info) == 0:
                return

            self.track_function_body(to_nodeID, next_nodeID_info[0][0])
            return

        # 計算式が単独で出た場合は、その部屋にキャラクターを配置する (計算内容は lineをキーとする辞書として追加していく)
        elif self.getNodeShape(nodeID) == 'rect':
            self.createRoom(nodeID, crntRoomID)
            if nodeID in self.map_info.room_info:
                self.createPath(
                    crntRoomID, 
                    nodeID, 
                    None
                )
                crntRoomID = nodeID

            if (execution_info := self.map_info.execution_info.get(nodeID)) is None:
                sys.exit("execution_info is not found")

            if (expr_node_info := self.getExprNodeInfo(nodeID)) is None:
                sys.exit("expr_node_info is not found")

            detail = TempExpressionDetail(
                expr = self.create_comment_window_info(
                    "exps",
                    detail = [
                        ["execute", f"of line {expr_node_info["line"]}"] 
                        if self.is_english else 
                        [f"{expr_node_info["line"]}行目の", "を実行します"]
                    ], 
                    hover = [
                        expr_node_info["comments"]
                    ],
                    func_reference_group = FuncReferenceGroup(
                        name = f"expression line of {expr_node_info["line"]}" if self.is_english else f"{expr_node_info["line"]}行目の計算式",
                        func = expr_node_info["funcs"]
                    ) if len(expr_node_info["funcs"]) else None
                ),
                vars = expr_node_info["vars"], 
                execution_info = execution_info
            )

            self.map_info.execution_comment_handler.register_expression_comment(
                expr_node_info["line"], 
                expr_node_info["comments"]
            )

            self.map_info.addExpressionToCharaExpression(crntRoomID, detail, expr_node_info["line"], self.func_name)

        for to_nodeID, edgeLabel in self.getNextNodeInfo(nodeID):
            self.track_function_body(crntRoomID, to_nodeID)

    # ノードの形を確認する
    def getNodeShape(self, nodeID: str) -> str:
        #IDが重複する場合にも対応しているのでリストを得る。ゆえに、リストの最初の要素を取得する。
        attrs = self.graph.get_node(nodeID)[0].obj_dict['attributes']
        return attrs['shape']
    
    # ノード内のラベルを確認する
    def getNodeLabel(self, nodeID: str) -> str:
        #IDが重複する場合にも対応しているのでリストを得る。ゆえに、リストの最初の要素を取得する。
        attrs = self.graph.get_node(nodeID)[0].obj_dict['attributes']
        return attrs['label']
    
    # getNextNodeInfo用にノード情報を格納する
    def set_next_node_info(self):
        for edge in self.graph.get_edges():
            label = edge.get_attributes().get("label", "")
            if (edgeSource := edge.get_source()) in self.nextNodeInfo:
                self.nextNodeInfo[edgeSource].append((edge.get_destination(), label))
            else:
                self.nextNodeInfo[edgeSource] = [(edge.get_destination(), label)]

    # 次のノードを取得する(複数ある場合にも対応できるようにリストで取得する)
    def getNextNodeInfo(self, nodeID: str):
        return self.nextNodeInfo.pop(nodeID, [])
    
    # 計算式, 変数の参照リスト、関数の参照リスト、計算式のコメントリスト、計算式の行数を取得
    # 型はExprNodeInfo
    def getExprNodeInfo(self, nodeID: str) -> ExprNodeInfo | None:
        return self.expr_node_info.get(nodeID)

    def createRoom(self, nodeID: str, prevRoomID: str | None = None):
        if (size := self.room_size_info[self.func_name].pop(nodeID, None)):
            height = random.randint(4, size-4)
            width = size - height
            mapHeight, mapWidth = self.floor_map.shape
            kernel = np.ones((height+self.PADDING2,width+self.PADDING2))
            if prevRoomID:
                if self.map_info.room_info[prevRoomID]["direction"] == "left":
                    direction = random.choice(['left', 'up'])
                elif self.map_info.room_info[prevRoomID]["direction"] == "up":
                    direction = random.choice(['left', 'right'])
                else:
                    direction = random.choice(['up', 'right'])
            else:
                direction = None
            self.map_info.room_info[nodeID] = RoomInfo(
                room_size = self.findRoomArea((height, width), (mapHeight, mapWidth), kernel, (prevRoomID, direction) if direction else None), 
                direction = direction or random.choice(['left', 'up', 'right'])
            )

    def findRoomArea(self, roomSize: tuple[int, int], mapSize: tuple[int, int], kernel, prevRoom_info: tuple[str, str] | None, add_size: dict = {"x": 0, "y": 0}):
        def expand_map(original, map_size, new_shape, fill_value, direction: str | None):
            new_map = np.full(new_shape, fill_value, dtype=original.dtype)
            if direction:
                if direction == "left":
                    new_map[self.SIZE_EXPAND:new_shape[0], self.SIZE_EXPAND:new_shape[1]] = original
                elif direction == "up":
                    new_map[self.SIZE_EXPAND:new_shape[0], self.SIZE_EXPAND:map_size[1]+self.SIZE_EXPAND] = original
                else:
                    new_map[self.SIZE_EXPAND:new_shape[0], 0:map_size[1]] = original
            else:
                new_map[:map_size[0], :map_size[1]] = original
            return new_map
    
        candidate_squares: list[tuple[int, int]] = []
        convolved = ndimage.convolve(self.floor_map, kernel, mode='constant', cval=0)

        if prevRoom_info:
            if prevRoom_info[1] == "left":
                range_x = (1, self.map_info.room_info[prevRoom_info[0]]["room_size"][1]+self.map_info.offset["x"]-roomSize[1]-self.PADDING2)
                range_y = (self.map_info.room_info[prevRoom_info[0]]["room_size"][0]+self.map_info.offset["y"]-roomSize[0], self.map_info.room_info[prevRoom_info[0]]["room_size"][0]+self.map_info.offset["y"]+self.map_info.room_info[prevRoom_info[0]]["room_size"][2]-roomSize[0])
            elif prevRoom_info[1] == "up":
                range_x = (self.map_info.room_info[prevRoom_info[0]]["room_size"][1]+self.map_info.offset["x"]-roomSize[1], self.map_info.room_info[prevRoom_info[0]]["room_size"][1]+self.map_info.offset["x"]+self.map_info.room_info[prevRoom_info[0]]["room_size"][3]-roomSize[1])
                range_y = (1, self.map_info.room_info[prevRoom_info[0]]["room_size"][0]+self.map_info.offset["y"]-self.PADDING2)
            else:
                range_x = (self.map_info.room_info[prevRoom_info[0]]["room_size"][1]+self.map_info.offset["x"]+self.map_info.room_info[prevRoom_info[0]]["room_size"][3]+self.PADDING2, mapSize[0]-roomSize[0])
                range_y = (self.map_info.room_info[prevRoom_info[0]]["room_size"][0]+self.map_info.offset["y"]-roomSize[0], self.map_info.room_info[prevRoom_info[0]]["room_size"][0]+self.map_info.offset["y"]+self.map_info.room_info[prevRoom_info[0]]["room_size"][2]-roomSize[0])
            if range_x[0] >= range_x[1]:
                range_x = (range_x[0], range_x[0]+1)
            if range_y[0] >= range_y[1]:
                range_y = (range_y[0], range_y[0]+1)

            for y in range(range_y[0], range_y[1]):
                if y < 1 or mapSize[0] <= y:
                    continue
                for x in range(range_x[0], range_x[1]):
                    if 1 <= x < mapSize[1] and convolved[y,x] == (roomSize[0]+self.PADDING2)*(roomSize[1]+self.PADDING2) and np.all(self.floor_map[y-self.PADDING:y+roomSize[0]+self.PADDING, x-self.PADDING:x+roomSize[1]+self.PADDING] == 1):
                        candidate_squares.append((y,x))
        else:
            for y in range(1, mapSize[0]-roomSize[0]-self.PADDING2):
                for x in range(1, mapSize[1]-roomSize[1]-self.PADDING2):
                    if convolved[y,x] == (roomSize[0]+self.PADDING2)*(roomSize[1]+self.PADDING2) and np.all(self.floor_map[y-self.PADDING:y+roomSize[0]+self.PADDING, x-self.PADDING:x+roomSize[1]+self.PADDING] == 1):
                        candidate_squares.append((y,x))
        
        if candidate_squares:
            # region choose room pos with weight
            # # 重みづけをする (部屋の位置のランダム性は増すが、道が長くなる可能性がある)
            # if prevRoom_info is None:
            #     # fallback: 均等重み
            #     w = list(range(len(candidate_squares), 0, -1))
            # elif prevRoom_info[1] == "left":
            #     # x が大きい方が優先されるように
            #     w = [x for (_, x) in candidate_squares]
            # elif prevRoom_info[1] == "up":
            #     # y が大きい方が優先されるように
            #     w = [y for (y, _) in candidate_squares]
            # else:
            #     # x が小さい方が優先されるように
            #     w = [1 / (x + 1) for (_, x) in candidate_squares]
            # # 正規化して選択（数値のスケールが大きくても安定する）
            # wsum = sum(w)
            # w = [wi / wsum for wi in w]
            # y, x = random.choices(candidate_squares, weights=w)[0]
            # endregion 
            
            # directionに応じて重みを変える
            if prevRoom_info is None:
                y, x = random.choice(candidate_squares)
            elif prevRoom_info[1] == "left":
                # x が大きい方が優先されるように
                y, x = max(candidate_squares, key=lambda c: c[1])
            elif prevRoom_info[1] == "up":
                # y が大きい方が優先されるように
                y, x = max(candidate_squares, key=lambda c: c[0])
            else:
                # x が小さい方が優先されるように
                y, x = min(candidate_squares, key=lambda c: c[1])
            # 部屋を配置
            self.floor_map[y:y+roomSize[0], x:x+roomSize[1]] = 0
            self.only_room_map[y:y+roomSize[0], x:x+roomSize[1]] = 0
            return (y - self.map_info.offset["y"], x - self.map_info.offset["x"], roomSize[0], roomSize[1])
        else:
            if prevRoom_info:
                # 拡張サイズの計算
                if prevRoom_info[1] == "left":
                    new_height = mapSize[0] + self.SIZE_EXPAND
                    new_width = mapSize[1] + self.SIZE_EXPAND
                    self.map_info.offset["y"] += self.SIZE_EXPAND
                    self.map_info.offset["x"] += self.SIZE_EXPAND
                elif prevRoom_info[1] == "up":
                    new_height = mapSize[0] + self.SIZE_EXPAND
                    new_width = mapSize[1] + self.SIZE_EXPAND * 2
                    self.map_info.offset["y"] += self.SIZE_EXPAND
                    self.map_info.offset["x"] += self.SIZE_EXPAND
                else:
                    new_height = mapSize[0] + self.SIZE_EXPAND
                    new_width = mapSize[1] + self.SIZE_EXPAND
                    self.map_info.offset["y"] += self.SIZE_EXPAND
                new_shape = (new_height, new_width)
                # 各マップを更新
                self.floor_map = expand_map(self.floor_map, mapSize, new_shape, fill_value=1, direction=prevRoom_info[1])
                self.only_room_map = expand_map(self.only_room_map, mapSize, new_shape, fill_value=1, direction=prevRoom_info[1])
                self.map_info.event_map = expand_map(self.map_info.event_map, mapSize, new_shape, fill_value=0, direction=prevRoom_info[1])
                return self.findRoomArea(roomSize, new_shape, kernel, prevRoom_info, add_size)
            else:
                # 拡張サイズの計算
                new_height = mapSize[0] + self.SIZE_EXPAND
                new_width = mapSize[1] + self.SIZE_EXPAND
                new_shape = (new_height, new_width)
                # 各マップを更新
                self.floor_map = expand_map(self.floor_map, mapSize, new_shape, fill_value=1, direction=None)
                self.only_room_map = expand_map(self.only_room_map, mapSize, new_shape, fill_value=1, direction=None)
                self.map_info.event_map = expand_map(self.map_info.event_map, mapSize, new_shape, fill_value=0, direction=None)
                return self.findRoomArea(roomSize, (new_height, new_width), kernel, prevRoom_info, add_size)

    def createPath(self, start_nodeID: str, goal_nodeID: str, comment_window_info: TempCommentWindowInfo | None):
        def get_edge_point(start, goal):
            # start, goalはローカル座標
            def random_edge_point(dir, room_pos):
                local_ry, local_rx, rheight, rwidth = room_pos
                ry = local_ry + self.map_info.offset["y"]
                rx = local_rx + self.map_info.offset["x"]
                candidates: list[tuple[int,int]] = []
                # top edge (y = ry - 1)
                if dir == 'u':
                    y = ry - 1
                    for x in range(rx, rx + rwidth):
                        if (0 <= y < h and 0 <= x < w and self.floor_map[y, x] != 0 and 
                            0 <= x-1 and self.map_info.event_map[y, x-1] == 0 and 
                            0 <= y-1 and self.map_info.event_map[y-1, x] == 0 and 
                            x+1 < w and self.map_info.event_map[y, x+1] == 0):
                            candidates.append((y, x))
                # bottom edge (y = ry + height)
                elif dir == 'd':
                    y = ry + rheight
                    for x in range(rx, rx + rwidth):
                        if (0 <= y < h and 0 <= x < w and self.floor_map[y, x] != 0 and 
                            0 <= x-1 and self.map_info.event_map[y, x-1] == 0 and 
                            y+1 < h and self.map_info.event_map[y+1, x] == 0 and 
                            x+1 < w and self.map_info.event_map[y, x+1] == 0):
                            candidates.append((y, x))
                # left edge (x = rx - 1)
                elif dir == 'l':
                    x = rx - 1
                    for y in range(ry, ry + rheight):
                        if (0 <= y < h and 0 <= x < w and self.floor_map[y, x] != 0 and 
                            0 <= y-1 and self.map_info.event_map[y-1, x] == 0 and 
                            0 <= x-1 and self.map_info.event_map[y, x-1] == 0 and 
                            y+1 < h and self.map_info.event_map[y+1, x] == 0):
                            candidates.append((y, x))
                # right edge (x = rx + width)
                elif dir == 'r':
                    x = rx + rwidth
                    for y in range(ry, ry + rheight):
                        if (0 <= y < h and 0 <= x < w and self.floor_map[y, x] != 0 and 
                            0 <= y-1 and self.map_info.event_map[y-1, x] == 0 and 
                            x+1 < w and self.map_info.event_map[y, x+1] == 0 and 
                            y+1 < h and self.map_info.event_map[y+1, x] == 0):
                            candidates.append((y, x))

                if not candidates:
                    return None

                return random.choice(candidates)

            h, w = self.floor_map.shape

            sy, sx, sheight, swidth = start
            gy, gx, gheight, gwidth = goal

            center_s = (sy + sheight / 2, sx + swidth / 2)
            center_g = (gy + gheight / 2, gx + gwidth / 2)

            dy = center_g[0] - center_s[0]
            dx = center_g[1] - center_s[1]

            start_edge_point = None
            goal_edge_point = None
            dir = None

            # DOWN, LEFT, RIGHT, UP = 0, 1, 2, 3
            if abs(dy) > abs(dx):
                if dy > 0:
                    start_edge_point = random_edge_point('d', start)
                    dir = 0
                else:
                    start_edge_point = random_edge_point('u', start)
                    dir = 3
            else:
                if dx > 0:
                    start_edge_point = random_edge_point('r', start)
                    dir = 2
                else:
                    start_edge_point = random_edge_point('l', start)
                    dir = 1

            if start_edge_point is None:
                if abs(dy) > abs(dx):
                    if dx > 0:
                        start_edge_point = random_edge_point('r', start)
                        dir = 2
                    else:
                        start_edge_point = random_edge_point('l', start)
                        dir = 1
                else:
                    if dy > 0:
                        start_edge_point = random_edge_point('d', start)
                        dir = 0
                    else:
                        start_edge_point = random_edge_point('u', start)
                        dir = 3
            
            if start_edge_point is not None:
                if dir == 0:
                    goal_edge_point = random_edge_point('u', goal)
                elif dir == 1:
                    goal_edge_point = random_edge_point('r', goal)
                elif dir == 2:
                    goal_edge_point = random_edge_point('l', goal)
                else: # dir == 3
                    goal_edge_point = random_edge_point('d', goal)
            
            return start_edge_point, goal_edge_point, dir

        check_map = 1 - self.only_room_map

        start, goal, dir = get_edge_point(self.map_info.room_info[start_nodeID]["room_size"], self.map_info.room_info[goal_nodeID]["room_size"])

        if start is None or goal is None:
            self.map_info.setWarpZone(
                start_nodeID, 
                goal_nodeID, 
                comment_window_info, 
                self.func_name
            ) 
            self.only_room_map = 1 - check_map
        else:
            if dir == 0: # d
                sny = start[0] + 1
                snx = start[1]
                gny = goal[0] - 1
                gnx = goal[1]
            elif dir == 1: # r
                sny = start[0]
                snx = start[1] + 1
                gny = goal[0]
                gnx = goal[1] - 1
            elif dir == 2: # l
                sny = start[0]
                snx = start[1] - 1            
                gny = goal[0]
                gnx = goal[1] + 1
            else: # u
                sny = start[0] - 1
                snx = start[1]
                gny = goal[0] + 1
                gnx = goal[1]

            check_map[sny, snx] = 0
            check_map[gny, gnx] = 0

            to_local_y, to_local_x, to_height, to_width = self.map_info.room_info[goal_nodeID]["room_size"]
            to_y = to_local_y + self.map_info.offset["y"]
            to_x = to_local_x + self.map_info.offset["x"]
            check_map[to_y:to_y+to_height, to_x:to_x+to_width] = 0

            path = CustomAStar(check_map, self.map_info.event_map).search(start, goal)

            check_map[to_y:to_y+to_height, to_x:to_x+to_width] = 1
            check_map[sny, snx] = 1
            check_map[gny, gnx] = 1

            '''
            ワープゾーンで部屋同士を繋げる必要がある場合は二通りある
            通路候補が見つからなかった場合 (通路のマスの数が0)
            または
            候補が見つかったとしてもその通路を構成するマスの数が1以下 (通路のマスの数は一方通行扉と確認キャラを配置するために「2以上」であることが必要) かつ comment_window_infoがNoneではない (通路にすると、一方通行扉と確認キャラを配置する必要がある場合) 
            '''
            if len(path) == 0 or (len(path) == 1 and comment_window_info is not None):
                self.map_info.setWarpZone(
                    start_nodeID, 
                    goal_nodeID, 
                    comment_window_info, 
                    self.func_name
                ) 
            else:
                for i in range(len(path)):
                    if ((to_y <= path[i][0] <= to_y+to_height-1 and (path[i][1] == to_x-1 or path[i][1] == to_x+to_width))
                        or (to_x <= path[i][1] <= to_x+to_width-1 and (path[i][0] == to_y-1 or path[i][0] == to_y+to_height))):
                        path = path[:i+1]
                        break

                for i in range(len(path)):
                    self.floor_map[path[i][0], path[i][1]] = 0

                if comment_window_info is not None:
                    if (execution_info := self.map_info.execution_info.get(goal_nodeID, None)) is None:
                        sys.exit("execution info on path is not found")
                    if execution_info["type"] == "expression":
                        sys.exit("a unit of door and condition-check character cannot be produced if type of execution info is \"expression\"")
                    self.map_info.setDoor(path[0], dir, comment_window_info)     
                    door_direction = (path[i-1][0] - path[i][0], path[i-1][1] - path[i][1])
                    if door_direction == (1,0): # 下向き d
                        self.map_info.setCharaCheckCondition(self.func_name, path[i], 0, execution_info, comment_window_info)
                    elif door_direction == (-1,0): # 上向き u
                        self.map_info.setCharaCheckCondition(self.func_name, path[i], 3, execution_info, comment_window_info)
                    elif door_direction == (0,1): # 右向き r
                        self.map_info.setCharaCheckCondition(self.func_name, path[i], 2, execution_info, comment_window_info)
                    else: # 左向き l
                        self.map_info.setCharaCheckCondition(self.func_name, path[i], 1, execution_info, comment_window_info)

        self.only_room_map = 1 - check_map

    # 引数は空リストになるものが多いので、デフォルト値を設定できるようにしている
    def create_comment_window_info(self, info_type: str, detail: list[list[str]] | None = None, hover: list[list[Comment]] | None = None, func_reference_group: FuncReferenceGroup | None = None, base_comment_window_info: TempCommentWindowInfo | None = None) -> TempCommentWindowInfo:
        if base_comment_window_info:
            comment_window_info = TempCommentWindowInfo(
                detail = base_comment_window_info["detail"] + (detail or []), 
                hover = base_comment_window_info["hover"]+ (hover or []),
                func_groups = [*base_comment_window_info["func_groups"], func_reference_group],
                type = info_type
            )
        else:
            comment_window_info = TempCommentWindowInfo(
                detail = detail or [], 
                hover = hover or [],
                func_groups = [func_reference_group],
                type = info_type
            )

        # デバッグ用に要素の中身が正しいか確認する
        if any(len(c) == 0 for c in comment_window_info["detail"]):
            sys.exit("each list in detail must have one or more elements")
        
        if sum(len(c)-1 for c in comment_window_info["detail"]) != len(comment_window_info["hover"]):
            sys.exit("number of elements in detail and ones in hover do not match")

        return comment_window_info