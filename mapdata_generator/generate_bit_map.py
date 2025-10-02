from typing import TypedDict
import pydot
import numpy as np
import random
import os
import json
import configparser
import scipy.ndimage as ndimage
import matplotlib.pyplot as plt
from astar.search import AStar, Tile
import mapChipID as mcID

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = BASE_DIR + '/mapdata'

class ConditionLineTracker:
    def __init__(self, condition_line_track: tuple[str, list[int | tuple[str, list[list[str]]] | dict | None]]):
        self.type = condition_line_track[0]
        self.condition_line_track = condition_line_track[1]

class ConditionLineTrackers:
    def __init__(self, condition_move: dict[str, tuple[str, list[int | tuple[str, list[list[str]]] | dict | None]]]):
        self.tracks: dict[str, ConditionLineTracker] = {nodeID: ConditionLineTracker(line_track) for nodeID, line_track in condition_move.items()}

    def get_condition_line_tracker(self, nodeID: str):
        if nodeID in self.tracks:
            # return tuple(self.tracks[nodeID].__dict__.values())
            return (self.tracks[nodeID].type, self.tracks[nodeID].condition_line_track)
        else:
            return ('', [])
    
class MoveEvent:
    def __init__(self, from_pos: tuple[int, int], to_pos: tuple[int, int], detail: str, mapchip: int, 
                    type: str, line_track: list[int | tuple[str, list[list[str]]] | dict | None], exps: list[str | dict], func_name: str):
        self.from_pos = from_pos
        self.to_pos = to_pos
        self.detail = detail
        self.mapchip = mapchip
        self.type = type
        self.line_track = line_track
        self.func_name = func_name
        self.exps = exps

class Treasure:
    def __init__(self, pos: tuple[int, int], name: str, line_track: list[int | tuple[str, list[list[str]]] | dict | None], exps: dict, type: str, func_name: str):
        self.pos = pos
        self.name = name
        self.type = type
        self.line_track = []
        for line in line_track:
            if isinstance(line, dict) and line["type"] in ["malloc", "realloc"]:
                line["vartype"] = self.type[:-1]
                line["varname"] = self.name
            self.line_track.append(line)
        self.exps = exps
        self.func_name = func_name

class FuncWarp:
    def __init__(self, to_pos: tuple[int, int], args: dict[str, str], line: int):
        self.to_pos = to_pos
        self.args = args
        self.line = line

    def get_attributes(self):
        return (self.to_pos, self.args, self.line)

class CharaReturn:
    def __init__(self, pos: tuple[int, int], func_name: str, line_track: list[int | tuple[str, list[list[str]]] | dict | None], exps):
        self.pos = pos
        self.func_name = func_name
        self.line_track = line_track
        self.exps = exps

    def get_attributes(self):
        return (self.pos, self.func_name, self.line_track)

class AutoEvent:
    def __init__(self, pos: tuple[int, int], mapchip: int, dir: str):
        self.pos = pos
        self.mapchip = mapchip
        self.dir = dir

class Door:
    def __init__(self, pos: tuple[int, int], dir: int, name: str):
        self.pos = pos
        self.name = name
        self.dir = dir

class CharaCheckCondition:
    def __init__(self, func, pos, dir, type, line_track: tuple[str, list[list[str]]], detail: str, exps: list[str]):
        self.func = func
        self.pos = pos
        self.dir = dir
        self.type = type
        self.line_track = line_track
        self.detail = detail
        self.exps = exps

class CharaExpression:
    def __init__(self, pos: tuple[int, int], func: str):
        self.pos = pos
        self.func = func
        self.exps_dict: dict[int, dict] = {}
    
    def addExp(self, line_track: list[int | tuple[str, list[list[str]]] | None], expNodeInfo: tuple[str, list[str], list[str], list[str | dict], int]):
        self.exps_dict[line_track[0]] = {"comments": expNodeInfo[3], "var_references": expNodeInfo[1], "line_track": line_track}

# マップデータ生成に必要な情報はここに格納
class MapInfo:
    ISEVENT = 2

    def __init__(self, condition_move: dict[str, tuple[str, list[int | str | None]]]):
        self.eventMap = np.zeros((20,20))
        self.room_info: dict[str, tuple[int, int, int, int]] = {}
        self.condition_line_trackers: ConditionLineTrackers = ConditionLineTrackers(condition_move)
        self.initPos: tuple[int, int] | None = None
        self.move_events: list[MoveEvent] = []
        self.treasures: list[Treasure] = []
        self.func_warps: dict[str, FuncWarp] = {}
        self.chara_moveItems: list[tuple[tuple[int, int], str, list[list[str]], str, list[str]]] = []
        self.chara_returns: list[CharaReturn] = []
        self.auto_events: list[AutoEvent] = []
        self.doors: list[Door] = []
        self.chara_checkConditions: list[CharaCheckCondition] = []
        self.chara_expressions: dict[str, CharaExpression] = {}
        self.input_lines: dict[str, dict[int, list[int]]] = {}
        self.file_lines: dict[str, dict[int, list[dict]]] = {}
        self.memory_lines: dict[str, dict[int, list[dict]]] = {}
        self.str_lines: dict[str, dict[int, list[dict]]] = {}

    # プレイヤーの初期位置の設定
    def setPlayerInitPos(self, initNodeID):  
        if self.initPos:
            return
        py, px, pheight, pwidth = self.room_info[initNodeID]
        zero_elements = np.argwhere(self.eventMap[py:py+pheight, px:px+pwidth] == 0)
        y, x = zero_elements[np.random.choice(zero_elements.shape[0])]
        self.eventMap[py+y, px+x] = self.ISEVENT
        self.initPos =  (int(py+y), int(px+x))

    def setFuncWarpStartPos(self, startNodeID):
        sy, sx, sheight, swidth = self.room_info[startNodeID]
        zero_elements = np.argwhere(self.eventMap[sy:sy+sheight, sx:sx+swidth] == 0)
        y, x = zero_elements[np.random.choice(zero_elements.shape[0])]
        pos = (int(sy+y), int(sx+x))
        self.eventMap[pos[0], pos[1]] = self.ISEVENT
        return pos     

    # 話しかけると戻るキャラの設定
    def setCharaReturn(self, roomNodeID, line, func_name, funcNodeID, expNodeInfo):
        gy, gx, gheight, gwidth = self.room_info[roomNodeID]
        zero_elements = np.argwhere(self.eventMap[gy:gy+gheight, gx:gx+gwidth] == 0)
        y, x = zero_elements[np.random.choice(zero_elements.shape[0])]
        pos = (int(gy+y), int(gx+x))
        self.eventMap[pos[0], pos[1]] = self.ISEVENT
        _, c_move_fromTo = self.condition_line_trackers.get_condition_line_tracker(funcNodeID)
        exp_comments = expNodeInfo[3] if expNodeInfo else []
        self.chara_returns.append(CharaReturn(pos, func_name, [int(line)] + c_move_fromTo if len(c_move_fromTo) else [int(line)], exp_comments))

    # ワープゾーンの設定 (条件式については、とりあえず関数だけを確認する)
    # expNodeInfo = exp_str, var_refs, func_refs, exp_comments, exp_line_num
    def setWarpZone(self, startNodeID: str, goalNodeID: str, warpComment: str, crnt_func_name: str, mapchip_num: int, warpNodeID: str = None, expNodeInfo: tuple[str, list[str], list[str], list[str | dict], int] | None = None):
        sy, sx, sheight, swidth = self.room_info[startNodeID]
        gy, gx, gheight, gwidth = self.room_info[goalNodeID]
        
        #まず遷移元を設定する
        zero_elements = np.argwhere(self.eventMap[sy:sy+sheight, sx:sx+swidth] == 0)
        y, x = zero_elements[np.random.choice(zero_elements.shape[0])]
        warpFrom = (int(sy+y), int(sx+x))
        self.eventMap[warpFrom[0], warpFrom[1]] = self.ISEVENT
        #次に遷移先を設定する
        zero_elements = np.argwhere(self.eventMap[gy:gy+gheight, gx:gx+gwidth] == 0)
        y, x = zero_elements[np.random.choice(zero_elements.shape[0])]
        warpTo = (int(gy+y), int(gx+x))
        self.eventMap[warpTo[0], warpTo[1]] = self.ISEVENT
        c_move_type, c_move_fromTo = self.condition_line_trackers.get_condition_line_tracker(goalNodeID)
        # doWhileTrue, ifEndについてはワープゾーン情報を上書きする
        if warpNodeID is not None:
            c_move_type, c_move_fromTo = self.condition_line_trackers.get_condition_line_tracker(warpNodeID)
        exp_comments = expNodeInfo[3] if expNodeInfo else []
        self.move_events.append(MoveEvent(warpFrom, warpTo, warpComment, mapchip_num, c_move_type, c_move_fromTo, exp_comments, crnt_func_name))

    # スカラー変数に対応した宝箱の設定 (item_exp_infoは、変数名、値の計算式で使われている変数、計算式で使われている関数、宣言の行数を格納している)
    def setItemBox(self, roomNodeID, item_name, lineNodeID, item_exp_dict: dict, var_type: str, crnt_func_name: str):
        ry, rx, rheight, rwidth = self.room_info[roomNodeID]
        zero_elements = np.argwhere(self.eventMap[ry:ry+rheight, rx:rx+rwidth] == 0)
        _, line_track = self.condition_line_trackers.get_condition_line_tracker(lineNodeID)
        y, x = zero_elements[np.random.choice(zero_elements.shape[0])]
        item_pos = (int(ry+y), int(rx+x))
        self.eventMap[item_pos[0], item_pos[1]] = self.ISEVENT
        self.treasures.append(Treasure(item_pos, item_name, line_track, item_exp_dict, var_type, crnt_func_name))

    # 一方通行パネルの設定
    def setOneWay(self, pos, dy, dx):
        self.eventMap[pos[0], pos[1]] = self.ISEVENT
        if dx == 0:
            self.auto_events.append(AutoEvent(pos, 6, "d" if dy == 1 else "u"))
        else:
            self.auto_events.append(AutoEvent(pos, 7, "r" if dx == 1 else "l"))

    # 出口のドア生成
    def setDoor(self, pos: tuple[int, int], dir: int, pathComment: str):
        self.doors.append(Door(pos, dir, pathComment))
        self.eventMap[pos[0], pos[1]] = self.ISEVENT

    def setCharaCheckCondition(self, func_name: str, pos: tuple[int, int], dir: int, condition_line_tracker: tuple[str, list[int | str | None]], detail: str, expNodeInfo: tuple[str, list[str], list[str], list[str], int] | None):
        exp_comments = expNodeInfo[3] if expNodeInfo else []
        self.chara_checkConditions.append(CharaCheckCondition(func_name, pos, dir, condition_line_tracker[0], condition_line_tracker[1], detail, exp_comments))
        self.eventMap[pos[0], pos[1]] = self.ISEVENT

    def addExpressionToCharaExpression(self, crntRoomID, expNodeInfo, lineNodeID, func):
        _, line_track = self.condition_line_trackers.get_condition_line_tracker(lineNodeID)
        if crntRoomID not in self.chara_expressions:
            ry, rx, rheight, rwidth = self.room_info[crntRoomID]
            zero_elements = np.argwhere(self.eventMap[ry:ry+rheight, rx:rx+rwidth] == 0)
            y, x = zero_elements[np.random.choice(zero_elements.shape[0])]
            chara_pos = (int(ry+y), int(rx+x))
            self.eventMap[chara_pos[0], chara_pos[1]] = self.ISEVENT
            self.chara_expressions[crntRoomID] = CharaExpression(chara_pos, func)
        self.chara_expressions[crntRoomID].addExp(line_track, expNodeInfo)

    # マップデータの生成
    def mapDataGenerator(self, pname: str, gvar_str: str, floorMap, isUniversal: bool, line_info: dict, wall_chip_type: int):
        defaultMapChips = [503, 343, 160, 32]
        floorMap = np.where(floorMap == 0, random.choice([390, 43, 402, 31]), floorMap) 
        # gray thick brick, grass floor, gray thin brick, or dungeon_floor

        self.writeMapIni(pname, self.initPos, gvar_str)
        self.writeMapJson(pname, floorMap, isUniversal, defaultMapChips[wall_chip_type])
        self.writeLineFile(pname, line_info)

        plt.imshow(floorMap, cmap='gray', interpolation='nearest')
        plt.title(pname)
        plt.savefig(f'{DATA_DIR}/{pname}/bm_{pname}.png')

    def line_track_transformer(self, line_track, func_name: str):
        func_num = 0
        func_warp: list[dict] = []
        converted_fromTo: list[int | None] = []
        str_order_num: dict[int, list[dict]] = {}
        input_order_num: dict[int, list[int]] = {}
        file_order_num: dict[int, list[dict]] = {}
        memory_order_num: dict[int, list[dict]] = {}
        for line in line_track:
            if isinstance(line, tuple):
                func_num += 1
                warp_pos, args, line_start = self.func_warps[line[0]].get_attributes()
                func_warp.append({"name": line[0], "x": warp_pos[1], "y": warp_pos[0], "args": args, "line": line_start, "children": line[1]})
                converted_fromTo.append(line_start)
            elif isinstance(line, dict):
                if line["type"] == "strcpy":
                    if func_num in str_order_num:
                        str_order_num[func_num].append(line)
                    else:
                        str_order_num[func_num] = [line]
                elif line["type"] == "scanf":
                    if func_num in input_order_num:
                        input_order_num[func_num].append(line["format"])
                    else:
                        input_order_num[func_num] = [line["format"]]
                elif line["type"] == "fopen":
                    if func_num in file_order_num:
                        file_order_num[func_num].append(line)
                    else:
                        file_order_num[func_num] = [line]
                elif line["type"] == "fclose":
                    if func_num in file_order_num:
                        file_order_num[func_num].append(line)
                    else:
                        file_order_num[func_num] = [line]
                elif line["type"] in ["malloc", "realloc"]:
                    if func_num in memory_order_num:
                        memory_order_num[func_num].append(line)
                    else:
                        memory_order_num[func_num] = [line]
                elif line["type"] == "free":
                    if func_num in memory_order_num:
                        memory_order_num[func_num].append(line)
                    else:
                        memory_order_num[func_num] = [line]
            elif isinstance(line, str):
                pass
            else:
                converted_fromTo.append(line)
        if len(input_order_num):
            if func_name in self.input_lines:
                self.input_lines[func_name][converted_fromTo[0]] = input_order_num
            else:
                self.input_lines[func_name] = {converted_fromTo[0]: input_order_num}
        if len(file_order_num):
            if func_name in self.file_lines:
                self.file_lines[func_name][converted_fromTo[0]] = file_order_num
            else:
                self.file_lines[func_name] = {converted_fromTo[0]: file_order_num}
        if len(memory_order_num):
            if func_name in self.memory_lines:
                self.memory_lines[func_name][converted_fromTo[0]] = memory_order_num
            else:
                self.memory_lines[func_name] = {converted_fromTo[0]: memory_order_num}
        if len(str_order_num):
            if func_name in self.str_lines:
                self.str_lines[func_name][converted_fromTo[0]] = str_order_num
            else:
                self.str_lines[func_name] = {converted_fromTo[0]: str_order_num}

        return func_warp, converted_fromTo

    def writeMapJson(self, pname, bitMap, isUniversal, defaultMapChip=503):
        events = []
        characters = []
        vardecl_lines: dict[int, list[str]] = {}

        # カラーユニバーサルデザインの色
        universal_colors = [15000, 15001, 15089, 15120, 15157, 15162, 15164]

        # アイテムの情報
        for treasure in self.treasures:
            func_warp, converted_fromTo = self.line_track_transformer(treasure.line_track, treasure.func_name)
            if converted_fromTo[0] in vardecl_lines:
                vardecl_lines[converted_fromTo[0]].append(treasure.name)
            else:
                vardecl_lines[converted_fromTo[0]] = [treasure.name]
            events.append({"type": "TREASURE", "x": treasure.pos[1], "y": treasure.pos[0], "item": treasure.name, "exps": treasure.exps, "vartype": treasure.type, "fromTo": converted_fromTo, "funcWarp": func_warp, "func": treasure.func_name})

        # ワープイベントの情報
        for move_event in self.move_events:
            func_warp, converted_fromTo = self.line_track_transformer(move_event.line_track, move_event.func_name)
            events.append({"type": "MOVE", "x": move_event.from_pos[1], "y": move_event.from_pos[0], "mapchip": move_event.mapchip, "warpType": move_event.type, "fromTo": converted_fromTo,
                        "dest_map": pname, "dest_x": move_event.to_pos[1], "dest_y": move_event.to_pos[0], "func": move_event.func_name, "funcWarp": func_warp, "exps": move_event.exps, "detail": move_event.detail})

        # 経路の一方通行情報
        for auto_event in self.auto_events:
            events.append({"type": "AUTO", "x": auto_event.pos[1], "y": auto_event.pos[0], "mapchip": auto_event.mapchip, "sequence": auto_event.dir})
    
        # 入口用のドアの情報 (開けようとする時に行数を確認する)
        for door in self.doors:
            events.append({"type": "SDOOR", "x": door.pos[1], "y": door.pos[0], "doorname": door.name, "dir": door.dir})
        
        # 関数の戻りに応じたキャラクターの情報
        for chara_return in self.chara_returns:
            pos, funcName, line_track = chara_return.get_attributes()
            func_warp, converted_fromTo = self.line_track_transformer(line_track, funcName)
            if funcName == "main":
                characters.append({"type": "CHARARETURN", "name": "15161", "x": pos[1], "y": pos[0], "dir": 0, "movetype": 1, "message": f"おめでとうございます!! ここがゴールです!!", "dest_map": pname, "fromTo": converted_fromTo, "func": funcName, "funcWarp": func_warp, "exps": chara_return.exps})
            else:
                characters.append({"type": "CHARARETURN", "name": "15084", "x": pos[1], "y": pos[0], "dir": 0, "movetype": 1, "message": f"ここが関数 {funcName} の終わりです!!", "dest_map": pname, "fromTo": converted_fromTo, "func": funcName, "funcWarp": func_warp, "exps": chara_return.exps})

        # 状態遷移のチェックキャラクターの情報
        for chara_checkCondition in self.chara_checkConditions:
            color = random.choice(universal_colors) if isUniversal else random.randint(15102,15160)
            func_warp, converted_fromTo = self.line_track_transformer(chara_checkCondition.line_track, chara_checkCondition.func)
            # y, x 
            # d, l, r, u = 0, 1, 2, 3
            move_dir_list = []
            if bitMap[chara_checkCondition.pos[0] + 1, chara_checkCondition.pos[1]] not in [390, 43, 402, 31]:
                move_dir_list.append(0)
            if bitMap[chara_checkCondition.pos[0], chara_checkCondition.pos[1] - 1] not in [390, 43, 402, 31]:
                move_dir_list.append(1)
            if bitMap[chara_checkCondition.pos[0], chara_checkCondition.pos[1] + 1] not in [390, 43, 402, 31]:
                move_dir_list.append(2)
            if bitMap[chara_checkCondition.pos[0] - 1, chara_checkCondition.pos[1]] not in [390, 43, 402, 31]:
                move_dir_list.append(3)
            move_dir = random.choice(move_dir_list)
            characters.append({"type": "CHARACHECKCONDITION", "name": str(color), "x": chara_checkCondition.pos[1], "y": chara_checkCondition.pos[0], "dir": chara_checkCondition.dir, "moveDir": move_dir,
                               "movetype": 1, "message": "条件文を確認しました！!　どうぞお通りください！!", "condType": chara_checkCondition.type, "fromTo": converted_fromTo, "func": chara_checkCondition.func, 
                               "funcWarp": func_warp, "exps": chara_checkCondition.exps, "detail": chara_checkCondition.detail})

        for chara_expression in self.chara_expressions.values():
            exps_dict = {}
            for firstLine, exps in chara_expression.exps_dict.items():
                func_warp, converted_fromTo = self.line_track_transformer(exps["line_track"], chara_expression.func)
                exps_dict[firstLine] = {"fromTo": converted_fromTo, "exps": exps["comments"], "funcWarp": func_warp, "vars": exps["var_references"]}
            characters.append({"type": "CHARAEXPRESSION", "name": "15165", "x": chara_expression.pos[1], "y": chara_expression.pos[0], "dir": 0,
                               "movetype": 1, "message": "変数の値を新しい値で更新できました!!", "func": chara_expression.func, "exps": exps_dict})
            
        filename = f'{DATA_DIR}/{pname}/{pname}.json'
        with open(filename, 'w') as f:
            fileContent = {"row": bitMap.shape[0], "col": bitMap.shape[1], "default": defaultMapChip, "map": bitMap.astype(int).tolist(), "characters": characters, "events": events}
            json.dump(fileContent, f) 

        vl_filename = f'{DATA_DIR}/{pname}/{pname}_varDeclLines.json'
        with open(vl_filename, 'w') as f:
            json.dump(vardecl_lines, f) 

    def writeMapIni(self, pname, initPos: tuple[int, int], gvarString):
        config = configparser.ConfigParser()

        config['screen'] = {
            'width': '1024',
            'height': '768'
        }

        config['game'] = {
            'player' : '15070',
            'player_x' : f'{initPos[1]}',
            'player_y' : f'{initPos[0]}',
            'map' : pname,
            'items' : f"{gvarString}"
        }

        config['api'] = {
            'key': '13f94c514269aa86469bc7642a6387b8',
            'url': 'se.is.kit.ac.jp'
        }

        filename = f'{DATA_DIR}/{pname}/{pname}.ini'
        with open(filename, 'w') as f:
            config.write(f)

    def writeLineFile(self, pname: str, line_info_dict: dict):
        filename = f'{DATA_DIR}/{pname}/{pname}_line.json'

        line_info_json = {funcname: 
            {
                "lines": sorted(list(line_info.lines)),
                "onelines": sorted(list(line_info.one_lines)),
                "loops": line_info.loops, 
                "start": line_info.start, 
                "return": line_info.returns,
                "voidreturn": line_info.void_returns,
                "input": self.input_lines.get(funcname, {}), 
                "file": self.file_lines.get(funcname, {}), 
                "memory": self.memory_lines.get(funcname, {}), 
                "string": self.str_lines.get(funcname, {})
            }
            for funcname, line_info in line_info_dict.items()
        }
        
        with open(filename, 'w') as f:
            json.dump(line_info_json, f)

class TileFixed(Tile):
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

class AStarFixed(AStar):
    def search(self, start_pos, target_pos):
        """A_Star (A*) path search algorithm"""
        start = TileFixed(*start_pos)
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
        return None
    
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
            if self.world[nx][ny] != 0:
                continue

            # 隣接マスに1がある場合は除外（接触を避ける）
            if any(
                self.world[nx + ddx][ny + ddy] == 1
                for ddx, ddy in directions
            ):
                continue

            neighbors.append(TileFixed(nx, ny))

        return neighbors

class GotoRoomInfo(TypedDict):
    toNodeID: str
    fromNodeID: str

# フローチャートを辿って最終的にマップデータを生成する
class GenBitMap:
    PADDING2 = 2
    PADDING = 1

    # 型指定はまた後で行う
    def __init__(self, pname: str, func_info_dict, gvar_info, varNode_info: dict[str, str], expNode_info: dict[str, tuple[str, list[str], list[str], list[str | dict], int]], 
                 roomSize_info, gotoRoom_list: dict[str, dict[str, GotoRoomInfo]], condition_move: dict[str, tuple[str, list[int | str | None]]]):
        
        (self.graph, ) = pydot.core.graph_from_dot_file(f'{DATA_DIR}/{pname}/{pname}.dot') # このフローチャートを辿ってデータを作成していく
        self.nextNodeInfo: dict[str, list[tuple[str, str]]] = {}
        self.func_info_dict: dict = func_info_dict
        self.gvar_info = gvar_info
        self.varNode_info = varNode_info
        self.expNode_info = expNode_info
        self.roomSize_info = roomSize_info
        self.floorMap = None
        self.roomsMap = None
        self.gotoRoom_list: dict[str, dict[str, GotoRoomInfo]] = gotoRoom_list # gotoラベルによるワープゾーンを作るための変数
        self.mapInfo = MapInfo(condition_move)

    def setMapChip(self, pname, line_info_dict, isUniversal):
        wallFlags = np.zeros(8, dtype=int)
        height, width = self.floorMap.shape
        bitMap_padded = np.pad(self.floorMap, pad_width=1, mode='constant', constant_values=0)
        # ここで壁パネルの種類を選択する
        wall_chip_type = random.randint(0, 3)
        for i in range(1, height+1):
            for j in range(1, width+1):
                if bitMap_padded[i, j]:
                    wallFlags[:] = 0
                    #まず上下左右が壁であるかを確かめる(壁でないならそちら方向に仕切りが出来る)
                    if bitMap_padded[i, j-1] == 0:
                        #左壁フラグ
                        wallFlags[0] = 1
                    if bitMap_padded[i-1, j] == 0:
                        #上壁フラグ
                        wallFlags[1] = 1
                    if bitMap_padded[i, j+1] == 0:
                        #右壁フラグ
                        wallFlags[2] = 1
                    if bitMap_padded[i+1, j] == 0:
                        #下壁フラグ
                        wallFlags[3] = 1
                    #次に斜めを確かめる
                    if wallFlags[0] + wallFlags[1] == 0:
                        #左上
                        if bitMap_padded[i-1, j-1] == 0:
                            #左上角壁フラグ
                            wallFlags[4] = 1
                    if wallFlags[1] + wallFlags[2] == 0:
                        #右上
                        if bitMap_padded[i-1, j+1] == 0:
                            #右上角壁フラグ
                            wallFlags[5] = 1
                    if wallFlags[2] + wallFlags[3] == 0:
                        #右下
                        if bitMap_padded[i+1, j+1] == 0:
                            #右下角壁フラグ
                            wallFlags[6] = 1
                    if wallFlags[3] + wallFlags[0] == 0:
                        #左下
                        if bitMap_padded[i+1, j-1] == 0:
                            #左下角壁フラグ
                            wallFlags[7] = 1
                    bitMap_padded[i, j] = self.getFloorChipID(wallFlags, wall_chip_type)

        self.floorMap = bitMap_padded[1:height+1, 1:width+1]

        self.mapInfo.mapDataGenerator(pname, self.set_gvar(), self.floorMap, isUniversal, line_info_dict, wall_chip_type)

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
        # # return floorGrassChipID[tuple(map(int, arr))] # stone-grass

    def startTracking(self):
        self.setNextNodeInfo()
        self.func_name = "main"
        refInfo = self.func_info_dict.pop(self.func_name)
        self.floorMap = np.ones((20,20))
        self.roomsMap = np.ones((20,20))
        self.trackFuncAST(refInfo)

    def set_gvar(self):
        gvarString = ""
        for gvarNodeID in self.gvar_info:
            varName = self.getNodeLabel(gvarNodeID)
            var_type = self.varNode_info[gvarNodeID]
            for gvarContentNodeID, edgeName in self.getNextNodeInfo(gvarNodeID):
                #配列
                if self.getNodeShape(gvarContentNodeID) == 'box3d':
                    pass
                #構造体系
                elif self.getNodeShape(gvarContentNodeID) == 'tab':
                    pass
                #ノーマル変数
                elif self.getNodeShape(gvarContentNodeID) == 'square':
                    eni = self.getExpNodeInfo(gvarContentNodeID)
                    if gvarString:
                        gvarString = ', '.join([gvarString, f"'{varName}' : {{'values': {eni[3]}, 'type': '{var_type}'}}"])
                    else:
                        gvarString = f"'{varName}' : {{'values': {eni[3]}, 'type': '{var_type}'}}"
                #これはあり得ないがデバッグ用
                else:
                    print("wrong node shape")
        return ''.join(["{", gvarString, "}"])

    def trackFuncAST(self, refInfo):
        nodeID = refInfo.start_nodeID
        self.createRoom(nodeID)
        
        # 関数呼び出しのワープ情報を更新
        # キャラクターではなくなるが、この情報は流用可能
        # ただし、ワープ元の部屋を表すノードは使わない(アイテムに対するワープ情報はアイテムの生成時にくっつける)
        if self.func_name in self.mapInfo.func_warps:
            # クラスの属性に値を設定
            self.mapInfo.func_warps[self.func_name].to_pos = self.mapInfo.setFuncWarpStartPos(nodeID)
            self.mapInfo.func_warps[self.func_name].line = refInfo.start
        else:
            # クラスを生成
            self.mapInfo.func_warps[self.func_name] = FuncWarp(self.mapInfo.setFuncWarpStartPos(nodeID), {}, refInfo.start)

        for toNodeID, edgeLabel in self.getNextNodeInfo(nodeID):
            self.trackAST(nodeID, toNodeID)
        
        for labelName, gotoRoom in self.gotoRoom_list[self.func_name].items():
            toNodeID = gotoRoom["toNodeID"]
            fromNodeIDs = gotoRoom["fromNodeID"]
            for fromNodeID in fromNodeIDs:
                self.mapInfo.setWarpZone(fromNodeID, toNodeID, f"ラベル: {labelName} に遷移します", self.func_name, 158)

        self.mapInfo.setPlayerInitPos(nodeID)

        for ref in refInfo.refs:
            if (nextRefInfo := self.func_info_dict.pop(ref, None)):
                self.func_name = ref
                self.trackFuncAST(nextRefInfo)
    
    def trackAST(self, crntRoomID, nodeID, loopBackID = None):
        #引数を取得
        if self.getNodeShape(nodeID) == 'cylinder':
            # クラスの属性に値を設定
            self.mapInfo.func_warps[self.func_name].args[self.getNodeLabel(nodeID)] = self.varNode_info[nodeID]
        #if文とdo_while文とswitch文
        elif self.getNodeShape(nodeID) == 'diamond':
            nodeIDs = []
            if self.getNodeLabel(nodeID) == 'do':
                self.createRoom(nodeID)
                exp = self.getExpNodeInfo(nodeID)
                self.createPath(crntRoomID, nodeID, f"{exp[4]}行目の do-while文の条件 {exp[0]} の真偽の確認に移る")
                crntRoomID = nodeID
                for toNodeID, edgeLabel in self.nextNodeInfo.get(nodeID, []):
                    self.createRoom(toNodeID)
                    if self.getNodeShape(toNodeID) == 'circle':
                        exp = self.getExpNodeInfo(nodeID)
                        self.mapInfo.setWarpZone(crntRoomID, toNodeID, f"{exp[4]}行目の do-while文の条件 {exp[0]} が真", self.func_name, 158, expNodeInfo=self.getExpNodeInfo(nodeID)) # 条件文の計算式を確かめる
                    elif self.getNodeShape(toNodeID) == 'doublecircle':
                        exp = self.getExpNodeInfo(nodeID)
                        self.createPath(crntRoomID, toNodeID, f"{exp[4]}行目の do-while文の条件 {exp[0]} が偽", expNodeID=nodeID) # 条件文の計算式を確かめる
                    nodeIDs.append(toNodeID)
            else:
                #エッジの順番がランダムで想定通りに解析されない可能性があるので入れ替える
                for toNodeID, edgeLabel in self.getNextNodeInfo(nodeID):
                    self.createRoom(toNodeID)
                    if self.getNodeShape(toNodeID) == 'circle':
                        exp = self.getExpNodeInfo(nodeID)
                        self.createPath(crntRoomID, toNodeID, f"{exp[4]}行目の {self.getNodeLabel(nodeID)}文の条件 {exp[0]} が真", expNodeID=nodeID) # 条件文の計算式を確かめる
                        nodeIDs.insert(0, toNodeID)
                    elif self.getNodeShape(toNodeID) == 'diamond':
                        nodeIDs.append(toNodeID)
                    elif self.getNodeShape(toNodeID) == 'invtriangle': # 条件文から派生するcase文なので、条件文の計算式を確かめる必要がある
                        switch_exp = self.getExpNodeInfo(nodeID)
                        if (exp := self.getExpNodeInfo(toNodeID)) is not None:
                            warp_comment = f"{exp[4]}行目の case {exp[0]} ({switch_exp[0]} == {exp[0]}) が真"
                        else:
                            warp_comment = f"{switch_exp[4]}行目の条件 {switch_exp[0]} がいずれの case にも該当しない (default)"
                        self.mapInfo.setWarpZone(crntRoomID, toNodeID, warp_comment, self.func_name, 158, expNodeInfo=self.getExpNodeInfo(nodeID)) # 条件文の計算式を確かめる
                        nodeIDs.insert(0, toNodeID)
                    elif self.getNodeShape(toNodeID) == 'doublecircle':
                        exp = self.getExpNodeInfo(nodeID)
                        self.createPath(crntRoomID, toNodeID, f"{exp[4]}行目の {self.getNodeLabel(nodeID)}文の条件 {exp[0]} が偽", expNodeID=nodeID) # 条件文の計算式を確かめる
                        nodeIDs.append(toNodeID)
                    elif self.getNodeShape(toNodeID) == 'terminator':
                        self.trackAST(crntRoomID, toNodeID, loopBackID)
                    else:
                        print("unknown node appeared")
            for toNodeID in nodeIDs:
                if self.getNodeShape(toNodeID) == 'diamond':
                    self.trackAST(crntRoomID, toNodeID, loopBackID)
                else:
                    self.trackAST(toNodeID, toNodeID, loopBackID)
            return

        #while文とfor文は最終ノードからワープで戻る必要があるので、現在の部屋ノードのID(戻り先)を取得する
        elif self.getNodeShape(nodeID) == 'pentagon':
            #条件文以前の処理を同部屋に含めてはいけない
            self.createRoom(nodeID)
            #エッジの順番がランダムで想定通りに解析されない可能性があるので入れ替える
            nodeIDs = []
            for toNodeID, edgeLabel in self.getNextNodeInfo(nodeID):
                self.createRoom(toNodeID)
                if self.getNodeShape(toNodeID) == 'circle':
                    exp = self.getExpNodeInfo(nodeID)
                    self.createPath(nodeID, toNodeID, f"{exp[4]}行目の {self.getNodeLabel(nodeID)}文の条件 {exp[0]} が真", expNodeID=nodeID) # 条件文の計算式を確かめる
                    nodeIDs.insert(0, toNodeID)
                elif self.getNodeShape(toNodeID) == 'doublecircle':
                    exp = self.getExpNodeInfo(nodeID)
                    self.createPath(nodeID, toNodeID, f"{exp[4]}行目の {self.getNodeLabel(nodeID)}文の条件 {exp[0]} が偽", expNodeID=nodeID) # 条件文の計算式を確かめる
                    nodeIDs.append(toNodeID)
            # pentagonノードに戻ってくる時は既にtrue, false以降の解析は済んでいるのでnodeIDsは空リスト
            if nodeIDs:
                exp = self.getExpNodeInfo(nodeID)
                # while or forの領域に入る (whileIn or forIn)
                self.createPath(crntRoomID, nodeID, f"{exp[4]}行目の {self.getNodeLabel(nodeID)}文の条件 {exp[0]} の真偽の確認に移る")
                # true
                self.trackAST(nodeIDs[0], nodeIDs[0], nodeID)
                # false
                self.trackAST(nodeIDs[1], nodeIDs[1], loopBackID)

        #話しかけると関数の遷移元に戻るようにする
        elif self.getNodeShape(nodeID) == 'lpromoter':
            # returnノードに行数ラベルをつけて、それで行数を確認する
            self.mapInfo.setCharaReturn(crntRoomID, self.getNodeLabel(nodeID), self.func_name, nodeID, self.getExpNodeInfo(nodeID))
        
        # while文とfor文のワープ元である部屋のIDを取得する
        elif self.getNodeShape(nodeID) == 'parallelogram' and loopBackID:
            exp = self.getExpNodeInfo(loopBackID)
            self.mapInfo.setWarpZone(crntRoomID, loopBackID, f"{exp[4]}行目の {self.getNodeLabel(loopBackID)}文の条件 {exp[0]} の真偽の確認に移ります!!", self.func_name, 158)
            loopBackID = None

        # if文の終点でワープゾーンを作る
        elif self.getNodeShape(nodeID) == 'terminator':
            toNodeID, edgeLabel = self.getNextNodeInfo(nodeID)[0]
            self.createRoom(toNodeID)
            self.mapInfo.setWarpZone(crntRoomID, toNodeID, "if文を終了します", self.func_name, 158, warpNodeID=nodeID)
            nodeID = toNodeID
            crntRoomID = nodeID
        #変数宣言ノードから遷移するノードの種類で変数のタイプを分ける
        elif self.getNodeShape(nodeID) == 'signature':
            var_type = self.varNode_info[nodeID]
            for toNodeID, edgeLabel in self.getNextNodeInfo(nodeID):
                # 配列
                if self.getNodeShape(toNodeID) == 'box3d':
                    arrContNodeID_list: list[str] = []
                    string_comments = None
                    index_comments = []
                    for childNodeID, childEdgeLabel in self.getNextNodeInfo(toNodeID):
                        if childEdgeLabel == 'arrCont':
                            arrContNodeID_list.append(childNodeID)
                        elif childEdgeLabel == 'strCont':
                            exp_str, var_refs, func_refs, exp_comments, exp_line_num = self.getExpNodeInfo(childNodeID)
                            string_comments = exp_comments
                        else:
                            indexNodeID = childNodeID
                            # ここに関数の呼び出しのコメントが含まれている場合を考える必要がある
                            exp_str, var_refs, func_refs, exp_comments, exp_line_num = self.getExpNodeInfo(indexNodeID)
                            index_comments += exp_comments
                            while (indexNodeID_list := self.getNextNodeInfo(indexNodeID)) != []:
                                indexNodeID, _ = indexNodeID_list[0]
                                exp_str, var_refs, func_refs, exp_comments, exp_line_num = self.getExpNodeInfo(indexNodeID)
                                index_comments += exp_comments
                    
                    if len(arrContNodeID_list):
                        arrContExp_values = self.setArrayTreasure(arrContNodeID_list)
                    elif string_comments:
                        arrContExp_values = string_comments
                    else:
                        arrContExp_values = index_comments + ['初期化されていません']
                    self.mapInfo.setItemBox(crntRoomID, self.getNodeLabel(nodeID), toNodeID, {"values": arrContExp_values, "indexes": index_comments}, var_type, self.func_name)
                # 構造体系
                elif self.getNodeShape(toNodeID) == 'tab':
                    memberExp_dict = {}
                    for memberNodeID, _ in self.getNextNodeInfo(toNodeID):
                        # ここに関数の呼び出しのコメントが含まれている場合を考える必要がある
                        exp_str, var_refs, func_refs, exp_comments, exp_line_num = self.getExpNodeInfo(memberNodeID)
                        memberExp_dict[self.getNodeLabel(memberNodeID)] = exp_comments
                    self.mapInfo.setItemBox(crntRoomID, self.getNodeLabel(nodeID), toNodeID, {"values": memberExp_dict}, var_type, self.func_name)
                # スカラー変数
                elif self.getNodeShape(toNodeID) == 'square':
                    # ここに関数の呼び出しのコメントが含まれている場合を考える必要がある
                    exp_str, var_refs, func_refs, exp_comments, exp_line_num = self.getExpNodeInfo(toNodeID)
                    self.mapInfo.setItemBox(crntRoomID, self.getNodeLabel(nodeID), toNodeID, {"values": exp_comments}, var_type, self.func_name)
                #次のノード
                else:
                    self.trackAST(crntRoomID, toNodeID, loopBackID)
        # for文の初期値で変数の初期化がある場合はアイテムを作る
        elif self.getNodeShape(nodeID) == 'invhouse':
            for toNodeID, edgeLabel in self.getNextNodeInfo(nodeID):
                # ノーマル変数
                if self.getNodeShape(toNodeID) == 'signature':
                    var_type = self.varNode_info[toNodeID]
                    valueNodeID, _ = self.getNextNodeInfo(toNodeID)[0]
                    # ここに関数の呼び出しのコメントが含まれている場合を考える必要がある
                    exp_str, var_refs, func_refs, exp_comments, exp_line_num = self.getExpNodeInfo(valueNodeID)
                    self.mapInfo.setItemBox(crntRoomID, self.getNodeLabel(toNodeID), valueNodeID, {"values": exp_comments}, var_type, self.func_name)
                # 次のノード
                else:
                    self.trackAST(crntRoomID, toNodeID, loopBackID)
        elif self.getNodeShape(nodeID) == 'hexagon':
            # warpNodeIDが必要なのでここで解析する
            if nodeID in self.mapInfo.condition_line_trackers.tracks:
                nextNodeID, edgeLabel = self.getNextNodeInfo(nodeID)[0]
                if self.getNodeShape(nextNodeID) == 'parallelogram' and loopBackID:
                    self.mapInfo.setWarpZone(crntRoomID, loopBackID, "continue", self.func_name, 158, warpNodeID=nodeID)
                    loopBackID = None
                # continue → do While構文の場合
                elif self.getNodeShape(nextNodeID) == 'diamond':
                    self.createRoom(nextNodeID)
                    exp = self.getExpNodeInfo(nextNodeID)
                    self.mapInfo.setWarpZone(crntRoomID, nextNodeID, f"continueにより、{exp[4]}行目の do-while文の条件/{exp[0]} の真偽の確認に移ります!!", self.func_name, 158, warpNodeID=nodeID)
                    for toNodeID, edgeLabel in self.nextNodeInfo.get(nodeID, []):
                        self.createRoom(toNodeID)
                        if self.getNodeShape(toNodeID) == 'circle':
                            self.mapInfo.setWarpZone(nextNodeID, toNodeID, f"{exp[4]}行目の do-while文の条件 {exp[0]} が偽", self.func_name, 158, expNodeInfo=self.getExpNodeInfo(nextNodeID)) # 条件文の計算式を確かめる
                        elif self.getNodeShape(toNodeID) == 'doublecircle':
                            self.createPath(nextNodeID, toNodeID, f"{exp[4]}行目の do-while文の条件 {exp[0]} が偽", expNodeID=nextNodeID) # 条件文の計算式を確かめる
                            nodeID = nextNodeID
                # breakのノードの場合
                else:
                    self.createRoom(nextNodeID)
                    self.mapInfo.setWarpZone(crntRoomID, nextNodeID, "現在のループから抜けます", self.func_name, 158, warpNodeID=nodeID)
        # do while構文の最初の1回
        elif self.getNodeShape(nodeID) == 'invtrapezium':
            trueNodeID, edgeLabel = self.getNextNodeInfo(nodeID)[0]
            self.createRoom(trueNodeID)
            self.mapInfo.setWarpZone(crntRoomID, trueNodeID, f"{self.getNodeLabel(nodeID)}行目の do-while文の1回目の処理に入ります", self.func_name, 158, warpNodeID=nodeID) # 条件文の計算式を確かめる
            nodeID = trueNodeID
            crntRoomID = trueNodeID
        # switch構文の途中のcaseまたは末尾に接続する
        elif self.getNodeShape(nodeID) == 'invtriangle' and crntRoomID != nodeID:
            self.createRoom(nodeID)
            if "end" == self.getNodeLabel(nodeID):
                warp_comment = "switch文を終了します"
            else:
                if (exp := self.getExpNodeInfo(nodeID)) is not None:
                    warp_comment = f"{exp[4]}行目の case {exp[0]} に進入します"
                else:
                    warp_comment = "defaultに進入します"
            self.mapInfo.setWarpZone(crntRoomID, nodeID, warp_comment, self.func_name, 158)
            crntRoomID = nodeID
        # 計算式が単独で出た場合は、その部屋にキャラクターを配置する (計算内容は lineをキーとする辞書として追加していく)
        elif self.getNodeShape(nodeID) == 'rect':
            self.mapInfo.addExpressionToCharaExpression(crntRoomID, self.getExpNodeInfo(nodeID), nodeID, self.func_name)

        for toNodeID, edgeLabel in self.getNextNodeInfo(nodeID):
            self.trackAST(crntRoomID, toNodeID, loopBackID)

    # 配列の変数宣言用のアイテムの解析
    def setArrayTreasure(self, arrContNodeID_list: list[str]):
        arrContExp_dict: dict = {}
        for arrContNodeID in arrContNodeID_list:
            # 末端のノードならその計算式を取得する
            if self.getNodeShape(arrContNodeID) == 'square':
                exp_str, var_refs, func_refs, exp_comments, exp_line_num = self.getExpNodeInfo(arrContNodeID)
                arrContExp_dict[self.getNodeLabel(arrContNodeID)] = exp_comments
            # 途中のノード(box3d)ならその子要素を辿る
            else:
                childNodeID_list = [nodeID for nodeID, _ in self.getNextNodeInfo(arrContNodeID)]
                arrContExp_dict[self.getNodeLabel(arrContNodeID)] = self.setArrayTreasure(childNodeID_list)
        return arrContExp_dict

    # 'label', 'shape'属性がある
    def getNodeShape(self, nodeID):
        #IDが重複する場合にも対応しているのでリストを得る。ゆえに、リストの最初の要素を取得する。
        attrs = self.graph.get_node(nodeID)[0].obj_dict['attributes']
        return attrs['shape']
    
    def getNodeLabel(self, nodeID) -> str:
        #IDが重複する場合にも対応しているのでリストを得る。ゆえに、リストの最初の要素を取得する。
        attrs = self.graph.get_node(nodeID)[0].obj_dict['attributes']
        return attrs['label']
    
    def setNextNodeInfo(self):
        for edge in self.graph.get_edges():
            label = edge.get_attributes().get("label", "")
            if (edgeSource := edge.get_source()) in self.nextNodeInfo:
                self.nextNodeInfo[edgeSource].append((edge.get_destination(), label))
            else:
                self.nextNodeInfo[edgeSource] = [(edge.get_destination(), label)]

    def getNextNodeInfo(self, fromNodeID):
        return self.nextNodeInfo.pop(fromNodeID, [])
    
    # 計算式, 変数の参照リスト、関数の参照リスト、計算式のコメントリスト、計算式の行数を取得
    def getExpNodeInfo(self, nodeID):
        return self.expNode_info.get(nodeID, None)

    def createRoom(self, nodeID):
        if (size := self.roomSize_info[self.func_name].pop(nodeID, None)):
            height = random.randint(4, size-4)
            width = size - height
            mapHeight, mapWidth = self.floorMap.shape
            kernel = np.ones((height+self.PADDING2,width+self.PADDING2))
            self.mapInfo.room_info[nodeID] = self.findRoomArea((height, width), (mapHeight, mapWidth), kernel)

    def findRoomArea(self, roomSize, mapSize, kernel):
        def expand_map(original, map_size, new_shape, fill_value):
            new_map = np.full(new_shape, fill_value, dtype=original.dtype)
            new_map[:map_size[0], :map_size[1]] = original
            return new_map
        
        candidate_squares = []
        convolved = ndimage.convolve(self.floorMap, kernel, mode='constant', cval=0)
        for i in range(1, mapSize[0]-roomSize[0]-self.PADDING2):
            for j in range(1, mapSize[1]-roomSize[1]-self.PADDING2):
                if convolved[i,j] == (roomSize[0]+self.PADDING2)*(roomSize[1]+self.PADDING2) and np.all(self.floorMap[i:i+roomSize[0]+self.PADDING2, j:j+roomSize[1]+self.PADDING2] == 1):
                    candidate_squares.append((i,j))
        
        if candidate_squares:
            w = list(range(len(candidate_squares), 0, -1))
            i, j = random.choices(candidate_squares, weights=w)[0]
            self.floorMap[i+self.PADDING:i+self.PADDING+roomSize[0], j+self.PADDING:j+self.PADDING+roomSize[1]] = 0
            self.roomsMap[i+self.PADDING:i+self.PADDING+roomSize[0], j+self.PADDING:j+self.PADDING+roomSize[1]] = 0            

            return (i+self.PADDING,j+self.PADDING,roomSize[0],roomSize[1])
        else:
            # 拡張サイズの計算
            new_height = mapSize[0] + 20
            new_width = mapSize[1] + 20
            new_shape = (new_height, new_width)

            # 各マップを更新
            self.floorMap = expand_map(self.floorMap, mapSize, new_shape, fill_value=1)
            self.roomsMap = expand_map(self.roomsMap, mapSize, new_shape, fill_value=1)
            self.mapInfo.eventMap = expand_map(self.mapInfo.eventMap, mapSize, new_shape, fill_value=0)
            return self.findRoomArea(roomSize, (new_height, new_width), kernel)

    def createPath(self, startNodeID: str, goalNodeID: str, pathComment: str, expNodeID: str = None):
        def get_edge_point(start, goal):
            def random_edge_point(dir, roomPos):
                ry, rx, rheight, rwidth = roomPos
                candidates = []
                # top edge (y = ry)
                if dir == 'u':
                    y = ry - 1
                    for x in range(rx, rx + rwidth):
                        if (0 <= y < h and 0 <= x < w and self.floorMap[y, x] != 0 and 
                            self.mapInfo.eventMap[y, x-1] == 0 and self.mapInfo.eventMap[y-1, x] == 0 and self.mapInfo.eventMap[y, x+1] == 0):
                            candidates.append((ry, x))
                # bottom edge (y = ry + height - 1)
                elif dir == 'd':
                    y = ry + rheight
                    for x in range(rx, rx + rwidth):
                        if (0 <= y < h and 0 <= x < w and self.floorMap[y, x] != 0 and 
                            self.mapInfo.eventMap[y, x-1] == 0 and self.mapInfo.eventMap[y+1, x] == 0 and self.mapInfo.eventMap[y, x+1] == 0):
                            candidates.append((y, x))
                # left edge (x = rx)
                elif dir == 'l':
                    x = rx-1
                    for y in range(ry, ry + rheight):
                        if (0 <= y < h and 0 <= x < w and self.floorMap[y, x] != 0 and 
                            self.mapInfo.eventMap[y-1, x] == 0 and self.mapInfo.eventMap[y, x-1] == 0 and self.mapInfo.eventMap[y+1, rx] == 0):
                            candidates.append((y, x))
                # right edge (x = rx + width - 1)
                elif dir == 'r':
                    x = rx + rwidth
                    for y in range(ry, ry + rheight):
                        if (0 <= y < h and 0 <= x < w and self.floorMap[y, x] != 0 and 
                            self.mapInfo.eventMap[y-1, x] == 0 and self.mapInfo.eventMap[y, x+1] == 0 and self.mapInfo.eventMap[y+1, x] == 0):
                            candidates.append((y, x))

                if not candidates:
                    return None

                return random.choice(candidates)

            h, w = self.floorMap.shape

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
            
            return (start_edge_point, goal_edge_point, dir)

        room_reversed = self.roomsMap
        check_map = 1 - room_reversed

        start, goal, dir = get_edge_point(self.mapInfo.room_info[startNodeID], self.mapInfo.room_info[goalNodeID])

        if start is None or goal is None:
            self.mapInfo.setWarpZone(startNodeID, goalNodeID, pathComment, self.func_name, 158, expNodeInfo=self.getExpNodeInfo(expNodeID)) 
            self.roomsMap = 1 - check_map
        else:
            if dir == 0: # u
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
            else: # d
                sny = start[0] - 1
                snx = start[1]
                gny = goal[0] + 1
                gnx = goal[1]

            check_map[(sny, snx)] = 0
            check_map[(gny, gnx)] = 0

            path = AStarFixed(check_map).search(start, goal)

            check_map[(sny, snx)] = 1
            check_map[(gny, gnx)] = 1

            if path is None or len(path) == 1:
                self.mapInfo.setWarpZone(startNodeID, goalNodeID, pathComment, self.func_name, 158, expNodeInfo=self.getExpNodeInfo(expNodeID)) 
            else:
                self.mapInfo.setDoor(path[0], dir, pathComment)     

                for i in range(len(path)):
                    self.floorMap[path[i][0], path[i][1]] = 0

                i = len(path) - 1
                dir_door = (path[i-1][0] - path[i][0], path[i-1][1] - path[i][1])
                if dir_door == (1,0): # 下向き d
                    self.mapInfo.setCharaCheckCondition(self.func_name, path[i], 0, self.mapInfo.condition_line_trackers.get_condition_line_tracker(goalNodeID), pathComment, expNodeInfo=self.getExpNodeInfo(expNodeID))
                elif dir_door == (-1,0): # 上向き u
                    self.mapInfo.setCharaCheckCondition(self.func_name, path[i], 3, self.mapInfo.condition_line_trackers.get_condition_line_tracker(goalNodeID), pathComment, expNodeInfo=self.getExpNodeInfo(expNodeID))
                elif dir_door == (0,1): # 右向き r
                    self.mapInfo.setCharaCheckCondition(self.func_name, path[i], 2, self.mapInfo.condition_line_trackers.get_condition_line_tracker(goalNodeID), pathComment, expNodeInfo=self.getExpNodeInfo(expNodeID))
                else: # 左向き l
                    self.mapInfo.setCharaCheckCondition(self.func_name, path[i], 1, self.mapInfo.condition_line_trackers.get_condition_line_tracker(goalNodeID), pathComment, expNodeInfo=self.getExpNodeInfo(expNodeID))

        self.roomsMap = 1 - check_map
           
