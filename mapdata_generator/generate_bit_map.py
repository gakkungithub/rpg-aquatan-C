from typing import TypedDict
import pydot
import numpy as np
import random
import os
import scipy.ndimage as ndimage
import matplotlib.pyplot as plt
from astar.search import AStar, Tile
import mapChipID as mcID
import fileGenerator as fg

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = BASE_DIR + '/mapdata'

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

# マップデータ生成に必要な情報はここに格納
class MapInfo:
    ISEVENT = 2

    def __init__(self, condition_move):
        self.eventMap = np.zeros((20,20))
        self.room_info: dict[str, tuple[int, int, int, int]] = {}
        self.condition_move: dict[str, tuple[str, list[int | str | None]]] = condition_move
        self.initPos: tuple[int, int] | None = None
        self.warp_info: list[tuple[tuple[int, int], tuple[int, int], int, str]] = []
        self.treasure_info: list[tuple[str, list[str], list[str], int]] = []
        self.func_warp: dict[str, tuple[tuple[int, int], dict[str, str], int]] = {}
        self.chara_moveItems: list[tuple[tuple[int, int], str, list[list[str]], str, list[str]]] = []
        self.chara_return: list[tuple[tuple[int, int], str, int]] = []
        self.exit_info: list[tuple[int, int], str, list[int | None], str] = []
        self.door_info: list[tuple[tuple[int, int], str, int]] = []

    # プレイヤーの初期位置の設定
    def setPlayerInitPos(self, initNodeID):  
        if self.initPos:
            return 
        
        py, px, pheight, pwidth = self.room_info[initNodeID]
        zero_elements = np.argwhere(self.eventMap[py:py+pheight, px:px+pwidth] == 0)
        if zero_elements.size > 0:
            y, x = zero_elements[np.random.choice(zero_elements.shape[0])]
            self.eventMap[py+y, px+x] = self.ISEVENT
            self.initPos =  (int(py+y), int(px+x))
        else:
            print("generation failed: try again!! 0")

    def setFuncWarpStartPos(self, startNodeID):
        sy, sx, sheight, swidth = self.room_info[startNodeID]
        zero_elements = np.argwhere(self.eventMap[sy:sy+sheight, sx:sx+swidth] == 0)
        if zero_elements.size > 0:
            y, x = zero_elements[np.random.choice(zero_elements.shape[0])]
            pos = (int(sy+y), int(sx+x))
            self.eventMap[pos[0], pos[1]] = self.ISEVENT
            return pos
        else:
            print("generation failed: try again!! 5")
            return None
    
    # 関数キャラの設定
    # def setFuncWarp(self, func_warp):
    #     for funcName, funcWarp in func_warp.items():
    #         if funcWarp[0] and funcWarp[1]:
    #             wy, wx, wheight, wwidth = self.room_info[funcWarp[0]]
    #             zero_elements = np.argwhere(self.eventMap[wy:wy+wheight, wx:wx+wwidth] == 0)
    #             if zero_elements.size > 0:
    #                 y, x = zero_elements[np.random.choice(zero_elements.shape[0])]
    #                 warpPos = (int(wy+y), int(wx+x))
    #                 self.eventMap[warpPos[0], warpPos[1]] = self.ISEVENT
    #                 for warpFuncInfo in funcWarp[1]:
    #                     self.setCharaMoveItems(warpFuncInfo, (funcName, warpPos), funcWarp[2])

    # # 話しかけると別の関数に進むキャラの設定
    # def setCharaMoveItems(self, warpFuncInfo, warpTo, arguments):
    #     roomNodeID, vars, funcName = warpFuncInfo
    #     gy, gx, gheight, gwidth = self.room_info[roomNodeID]
    #     zero_elements = np.argwhere(self.eventMap[gy:gy+gheight, gx:gx+gwidth] == 0)
    #     if zero_elements.size > 0:
    #         y, x = zero_elements[np.random.choice(zero_elements.shape[0])]
    #         pos = (int(gy+y), int(gx+x))
    #         self.eventMap[pos[0], pos[1]] = self.ISEVENT
    #         self.chara_moveItems.append((pos, warpTo, vars, funcName, arguments))
    #     else:
    #         print("generation failed: try again!! 5")        

    # 話しかけると戻るキャラの設定
    def setCharaReturn(self, roomNodeID, line, funcName):
        gy, gx, gheight, gwidth = self.room_info[roomNodeID]
        zero_elements = np.argwhere(self.eventMap[gy:gy+gheight, gx:gx+gwidth] == 0)
        if zero_elements.size > 0:
            y, x = zero_elements[np.random.choice(zero_elements.shape[0])]
            pos = (int(gy+y), int(gx+x))
            self.eventMap[pos[0], pos[1]] = self.ISEVENT
            # とりあえずreturn文が必ずある場合のみを考える (void型は""となるのでint型ではキャストできない)
            if line == '""':
                line_ret = None
            else:
                line_ret = int(line)
            self.chara_return.append((pos, funcName, line_ret))
        else:
            print("generation failed: try again!! 6")

    # gotoラベルによるワープゾーンの設定
    def setGotoWarpZone(self, gotoRooms, func_name):
        for gotoRoom in gotoRooms.values():
            toNodeID = gotoRoom["toNodeID"]
            fromNodeIDs = gotoRoom["fromNodeID"]
            for fromNodeID in fromNodeIDs:
                # pyramid mapchip = 105
                self.setWarpZone(fromNodeID, toNodeID, func_name, 158)

    # ワープゾーンの設定 (条件式については、とりあえず関数だけを確認する)
    # expNodeInfo = exp_str, var_refs, func_refs, exp_comments, exp_line_num
    def setWarpZone(self, startNodeID: str, goalNodeID: str, crnt_func_name: str, mapChipNum: int, warpNodeID: str = None, expNodeInfo: tuple[str, list[str], list[str], list[str], int] | None = None):
        sy, sx, sheight, swidth = self.room_info[startNodeID]
        gy, gx, gheight, gwidth = self.room_info[goalNodeID]
        
        #まず遷移元を設定する
        zero_elements = np.argwhere(self.eventMap[sy:sy+sheight, sx:sx+swidth] == 0)
        if zero_elements.size > 0:
            y, x = zero_elements[np.random.choice(zero_elements.shape[0])]
            warpFrom = (int(sy+y), int(sx+x))
            self.eventMap[warpFrom[0], warpFrom[1]] = self.ISEVENT
            #次に遷移先を設定する
            zero_elements = np.argwhere(self.eventMap[gy:gy+gheight, gx:gx+gwidth] == 0)
            if zero_elements.size > 0:
                y, x = zero_elements[np.random.choice(zero_elements.shape[0])]
                warpTo = (int(gy+y), int(gx+x))
                self.eventMap[warpTo[0], warpTo[1]] = self.ISEVENT
                c_move_type, c_move_fromTo = self.condition_move.get(goalNodeID, ['', []])
                # doWhileTrue, ifEndについてはワープゾーン情報を上書きする
                if warpNodeID:
                    c_move_type, c_move_fromTo = self.condition_move[warpNodeID]
                self.warp_info.append([warpFrom, warpTo, mapChipNum, c_move_type, c_move_fromTo, crnt_func_name])
            else:
                print("generation failed: try again!! 1")
        else:
            print("generation failed: try again!! 2")

    # スカラー変数に対応した宝箱の設定 (item_exp_infoは、変数名、値の計算式で使われている変数、計算式で使われている関数、宣言の行数を格納している)
    def setItemBox(self, roomNodeID, itemName, item_exp_info: tuple[str, list[str], list[str], int], var_type: str):
        ry, rx, rheight, rwidth = self.room_info[roomNodeID]
        zero_elements = np.argwhere(self.eventMap[ry:ry+rheight, rx:rx+rwidth] == 0)
        if zero_elements.size > 0:
            y, x = zero_elements[np.random.choice(zero_elements.shape[0])]
            itemPos = (int(ry+y), int(rx+x))
            self.eventMap[itemPos[0], itemPos[1]] = self.ISEVENT
            self.treasure_info.append((itemPos, itemName, item_exp_info, var_type))
        else:
            print("generation failed: try again!! 3")

    # 一方通行パネルの設定
    def setOneWay(self, pos, dy, dx, condition_move, expNodeInfo: tuple[str, list[str], list[str], list[str], int] | None):
        self.eventMap[pos[0], pos[1]] = self.ISEVENT
        autoType, line_track = condition_move

        #left
        if dx == -1:
            self.exit_info.append([pos, 7, autoType, line_track, "l"])
        #up
        elif dy == -1:
            self.exit_info.append([pos, 6, autoType, line_track, "u"])
        #right
        elif dx == 1:
            self.exit_info.append([pos, 7, autoType, line_track, "r"])
        #down
        elif dy == 1:
            self.exit_info.append([pos, 6, autoType, line_track, "d"])

    # 出口のドア生成
    def setDoor(self, pos, dir):
        self.door_info.append((pos, "test", dir))
        self.eventMap[pos[0], pos[1]] = self.ISEVENT

    # マップデータの生成
    def mapDataGenerator(self, pname: str, gvar_str: str, floorMap, isUniversal: bool, line_info: dict[str, tuple[set[int], dict[int, int], int]]):
        defaultMapChips = [503, 113, 343, 160, 32]
        floorMap = np.where(floorMap == 0, 390, floorMap) # gray thick brick
        # self.floorMap = np.where(self.floorMap == 0, 43, self.floorMap) # grass floor
        # self.floorMap = np.where(self.floorMap == 0, 402, self.floorMap) # gray thin brick
        # self.floorMap = np.where(self.floorMap == 0, 31, self.floorMap) # dungeon_floor

        fg.writeMapIni(pname, self.initPos, gvar_str)
        fg.writeMapJson(pname, floorMap, self.warp_info, self.treasure_info, self.exit_info, self.func_warp, self.chara_return, self.door_info, isUniversal, defaultMapChips[0])
        fg.writeLineFile(pname, line_info)

        plt.imshow(floorMap, cmap='gray', interpolation='nearest')
        plt.title(pname)
        plt.savefig(f'{DATA_DIR}/{pname}/bm_{pname}.png')

class GotoRoomInfo(TypedDict):
    toNodeID: str
    fromNodeID: str

# フローチャートを辿って最終的にマップデータを生成する
class GenBitMap:
    PADDING2 = 2
    PADDING = 1

    # 型指定はまた後で行う
    def __init__(self, pname: str, func_info, gvar_info, varNode_info: dict[str, str], expNode_info: dict[str, tuple[str, list[str], list[str], list[str], int]], 
                 roomSize_info, gotoRoom_list: dict[str, dict[str, GotoRoomInfo]], condition_move):
        
        (self.graph, ) = pydot.core.graph_from_dot_file(f'{DATA_DIR}/{pname}/{pname}.dot') # このフローチャートを辿ってデータを作成していく
        self.nextNodeInfo: dict[str, tuple[str, str]] = {}
        self.func_info = func_info
        self.gvar_info = gvar_info
        self.varNode_info = varNode_info
        self.expNode_info = expNode_info
        self.roomSize_info = roomSize_info
        self.floorMap = None
        self.roomsMap = None
        self.gotoRoom_list: dict[str, dict[str, GotoRoomInfo]] = gotoRoom_list # gotoラベルによるワープゾーンを作るための変数
        self.mapInfo = MapInfo(condition_move)

    def setMapChip(self, pname, line_info, isUniversal):
        wallFlags = np.zeros(8, dtype=int)
        height, width = self.floorMap.shape
        bitMap_padded = np.pad(self.floorMap, pad_width=1, mode='constant', constant_values=0)
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
                    bitMap_padded[i, j] = mcID.getFloorChipID(wallFlags)

        self.floorMap = bitMap_padded[1:height+1, 1:width+1]

        # self.mapInfo.setFuncWarp(self.func_warp)

        self.mapInfo.mapDataGenerator(pname, self.set_gvar(), self.floorMap, isUniversal, line_info)

    def startTracking(self):
        self.setNextNodeInfo()
        self.func_name = "main"
        refInfo = self.func_info.pop(self.func_name)
        self.floorMap = np.ones((20,20))
        self.roomsMap = np.ones((20,20))
        self.trackFuncAST(refInfo)

    def set_gvar(self):
        gvarString = ""
        for gvarNodeID in self.gvar_info:
            varName = self.getNodeLabel(gvarNodeID)
            for gvarContentNodeID in self.getNextNodeInfo(gvarNodeID):
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
                        gvarString = ', '.join([gvarString, f"'{varName}' : {eni}"])
                    else:
                        gvarString = f"'{varName}' : {eni}"
                #これはあり得ないがデバッグ用
                else:
                    print("wrong node shape")
        return ''.join(["{", gvarString, "}"])

    def trackFuncAST(self, refInfo):
        nodeID = refInfo["start"]
        self.createRoom(nodeID)
        
        # 関数呼び出しのワープ情報を更新
        # キャラクターではなくなるが、この情報は流用可能
        # ただし、ワープ元の部屋を表すノードは使わない(アイテムに対するワープ情報はアイテムの生成時にくっつける)
        if self.func_name in self.mapInfo.func_warp:
            args = self.mapInfo.func_warp[self.func_name][1]
            self.mapInfo.func_warp[self.func_name] = (self.mapInfo.setFuncWarpStartPos(nodeID), args, refInfo["line"])
        else:
            self.mapInfo.func_warp[self.func_name] = (self.mapInfo.setFuncWarpStartPos(nodeID), {}, refInfo["line"])

        for toNodeID, edgeLabel in self.getNextNodeInfo(nodeID):
            self.trackAST(nodeID, toNodeID)
        
        self.mapInfo.setGotoWarpZone(self.gotoRoom_list[self.func_name], self.func_name)

        self.mapInfo.setPlayerInitPos(nodeID)

        for ref in refInfo["refs"]:
            if (nextRefInfo := self.func_info.pop(ref, None)):
                self.func_name = ref
                self.trackFuncAST(nextRefInfo)
    
    def trackAST(self, crntRoomID, nodeID, loopBackID = None):
        #引数を取得
        if self.getNodeShape(nodeID) == 'cylinder':
            self.mapInfo.func_warp[self.func_name][1][self.getNodeLabel(nodeID)] = self.varNode_info[nodeID]
        #if文とdo_while文とswitch文
        elif self.getNodeShape(nodeID) == 'diamond':
            nodeIDs = []
            #do_whileの場合はcondNodeIDのcondition_moveを使う
            if self.getNodeLabel(nodeID) == 'do':
                self.createRoom(nodeID)
                self.createPath(crntRoomID, nodeID)
                crntRoomID = nodeID
                for toNodeID, edgeLabel in self.nextNodeInfo.get(nodeID, []):
                    self.createRoom(toNodeID)
                    if self.getNodeShape(toNodeID) == 'circle':
                        self.mapInfo.setWarpZone(crntRoomID, toNodeID, 158, self.func_name, expNodeInfo=self.getExpNodeInfo(nodeID)) # 条件文の計算式を確かめる
                    elif self.getNodeShape(toNodeID) == 'doublecircle':
                        self.createPath(crntRoomID, toNodeID, expNodeID=nodeID) # 条件文の計算式を確かめる
                    nodeIDs.append(toNodeID)
            else:
                #エッジの順番がランダムで想定通りに解析されない可能性があるので入れ替える
                for toNodeID, edgeLabel in self.getNextNodeInfo(nodeID):
                    self.createRoom(toNodeID)
                    if self.getNodeShape(toNodeID) == 'circle':
                        self.createPath(crntRoomID, toNodeID, expNodeID=nodeID) # 条件文の計算式を確かめる
                        nodeIDs.insert(0, toNodeID)
                    elif self.getNodeShape(toNodeID) == 'diamond':
                        nodeIDs.append(toNodeID)
                    elif self.getNodeShape(toNodeID) == 'invtriangle': # 条件文から派生するcase文なので、条件文の計算式を確かめる必要がある
                        self.mapInfo.setWarpZone(crntRoomID, toNodeID, self.func_name, 158, expNodeInfo=self.getExpNodeInfo(nodeID)) # 条件文の計算式を確かめる
                        nodeIDs.insert(0, toNodeID)
                    elif self.getNodeShape(toNodeID) == 'doublecircle':
                        self.createPath(crntRoomID, toNodeID, expNodeID=nodeID) # 条件文の計算式を確かめる
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
            #while, forの領域に入る
            self.createPath(crntRoomID, nodeID)
            #エッジの順番がランダムで想定通りに解析されない可能性があるので入れ替える
            nodeIDs = []
            for toNodeID, edgeLabel in self.getNextNodeInfo(nodeID):
                self.createRoom(toNodeID)
                if self.getNodeShape(toNodeID) == 'circle':
                    self.createPath(nodeID, toNodeID, expNodeID=nodeID) # 条件文の計算式を確かめる
                    nodeIDs.insert(0, toNodeID)
                elif self.getNodeShape(toNodeID) == 'doublecircle':
                    self.createPath(nodeID, toNodeID, expNodeID=nodeID) # 条件文の計算式を確かめる
                    nodeIDs.append(toNodeID)
            # pentagonノードに戻ってくる時は既にtrue, false以降の解析は済んでいるのでnodeIDsは空リスト
            if nodeIDs:
                #whileの領域に入る
                self.createPath(crntRoomID, nodeID)
                # true
                self.trackAST(nodeIDs[0], nodeIDs[0], nodeID)
                # false
                self.trackAST(nodeIDs[1], nodeIDs[1], loopBackID)

        #話しかけると関数の遷移元に戻るようにする
        elif self.getNodeShape(nodeID) == 'lpromoter':
            # returnノードに行数ラベルをつけて、それで行数を確認する
            self.mapInfo.setCharaReturn(crntRoomID, self.getNodeLabel(nodeID), self.func_name)
        
        # while文とfor文のワープ元である部屋のIDを取得する
        elif self.getNodeShape(nodeID) == 'parallelogram' and loopBackID:
            self.mapInfo.setWarpZone(crntRoomID, loopBackID, self.func_name, 158)
            loopBackID = None

        # if文の終点でワープゾーンを作る
        elif self.getNodeShape(nodeID) == 'terminator':
            toNodeID, edgeLabel = self.getNextNodeInfo(nodeID)[0]
            self.createRoom(toNodeID)
            self.mapInfo.setWarpZone(crntRoomID, toNodeID, self.func_name, 158, warpNodeID=nodeID)
            nodeID = toNodeID
            crntRoomID = nodeID

        #変数宣言ノードから遷移するノードの種類で変数のタイプを分ける
        elif self.getNodeShape(nodeID) == 'signature':
            var_type = self.varNode_info[nodeID]
            for toNodeID, edgeLabel in self.getNextNodeInfo(nodeID):
                #配列
                if self.getNodeShape(toNodeID) == 'box3d':
                    self.trackAST(crntRoomID, toNodeID)
                #構造体系
                elif self.getNodeShape(toNodeID) == 'tab':
                    self.trackAST(crntRoomID, toNodeID)
                #ノーマル変数
                elif self.getNodeShape(toNodeID) == 'square':
                    eni = self.getExpNodeInfo(toNodeID)
                    self.mapInfo.setItemBox(crntRoomID, self.getNodeLabel(nodeID), eni, var_type)
                #初期化値なし(or次のノード)
                else:
                    self.trackAST(crntRoomID, toNodeID, loopBackID)
        # for文の初期値で変数の初期化がある場合はアイテムを作る
        elif self.getNodeShape(nodeID) == 'invhouse':
            for toNodeID, edgeLabel in self.getNextNodeInfo(nodeID):
                # ノーマル変数
                if self.getNodeShape(toNodeID) == 'signature':
                    var_type = self.varNode_info[toNodeID]
                    valueNodeID, _ = self.getNextNodeInfo(toNodeID)[0]
                    eni = self.getExpNodeInfo(valueNodeID)
                    self.mapInfo.setItemBox(crntRoomID, self.getNodeLabel(toNodeID), eni, var_type)
                # 次のノード
                else:
                    self.trackAST(crntRoomID, toNodeID, loopBackID)
        elif self.getNodeShape(nodeID) == 'hexagon':
            if self.mapInfo.condition_move.get(nodeID, None):
                nextNodeID, edgeLabel = self.getNextNodeInfo(nodeID)[0]
                if self.getNodeShape(nextNodeID) == 'parallelogram' and loopBackID:
                    self.mapInfo.setWarpZone(crntRoomID, loopBackID, self.func_name, 158, warpNodeID=nodeID)
                    loopBackID = None
                elif self.getNodeShape(nextNodeID) == 'diamond':
                    self.createRoom(nextNodeID)
                    self.mapInfo.setWarpZone(crntRoomID, nextNodeID, self.func_name, 158, warpNodeID=nodeID)
                    for toNodeID, edgeLabel in self.nextNodeInfo.get(nodeID, []):
                        self.createRoom(toNodeID)
                        if self.getNodeShape(toNodeID) == 'circle':
                            self.mapInfo.setWarpZone(nextNodeID, toNodeID, self.func_name, 158, expNodeInfo=self.getExpNodeInfo(nextNodeID)) # 条件文の計算式を確かめる
                        elif self.getNodeShape(toNodeID) == 'doublecircle':
                            self.createPath(nextNodeID, toNodeID, expNodeID=nextNodeID) # 条件文の計算式を確かめる
                            nodeID = nextNodeID
                # break
                else:
                    self.createRoom(nextNodeID)
                    self.mapInfo.setWarpZone(crntRoomID, nextNodeID, self.func_name, 158, warpNodeID=nodeID)
        else:
            # switch構文の途中のcase(breakなしでまたがる), 終点をワープゾーンで繋げる or do_while構文に入った時にstart(True)ノードにくっつける
            # ゆえに、条件関係なしに遷移できるワープゾーンなので条件文の計算式は確かめない
            if crntRoomID != nodeID:
                if nodeID in self.roomSize_info[self.func_name]:
                    self.createRoom(nodeID)

                if nodeID in self.mapInfo.room_info:
                    self.mapInfo.setWarpZone(crntRoomID, nodeID, self.func_name, 158)
                    crntRoomID = nodeID
                    
        for toNodeID, edgeLabel in self.getNextNodeInfo(nodeID):
            self.trackAST(crntRoomID, toNodeID, loopBackID)

    #'label', 'shape'属性がある
    def getNodeShape(self, nodeID):
        #IDが重複する場合にも対応しているのでリストを得る。ゆえに、リストの最初の要素を取得する。
        attrs = self.graph.get_node(nodeID)[0].obj_dict['attributes']
        return attrs['shape']
    
    def getNodeLabel(self, nodeID):
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

    def createPath(self, startNodeID: str, goalNodeID: str, expNodeID: str = None):
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

        sy, sx, sheight, swidth = self.mapInfo.room_info[startNodeID]
        gy, gx, gheight, gwidth = self.mapInfo.room_info[goalNodeID]

        room_reversed = self.roomsMap
        check_map = 1 - room_reversed

        start, goal, dir = get_edge_point(self.mapInfo.room_info[startNodeID], self.mapInfo.room_info[goalNodeID])

        print(start, goal)
        if start is None or goal is None:
            self.mapInfo.setWarpZone(startNodeID, goalNodeID, self.func_name, 158, expNodeInfo=self.getExpNodeInfo(expNodeID)) 
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

            if path is None:
                self.mapInfo.setWarpZone(startNodeID, goalNodeID, self.func_name, 158, expNodeInfo=self.getExpNodeInfo(expNodeID)) 
            else:
                self.floorMap[path[0][0], path[0][1]] = 0
                self.mapInfo.setDoor(path[0], dir)
                for i in range(1, len(path)):
                    self.floorMap[path[i][0], path[i][1]] = 0
                i = len(path) - 1
                if gy-1 == path[i][0]:
                    self.mapInfo.setOneWay(path[i], 1, 0, self.mapInfo.condition_move[goalNodeID], expNodeInfo=self.getExpNodeInfo(expNodeID))
                elif gy+1 == path[i][0]:
                    self.mapInfo.setOneWay(path[i], -1, 0, self.mapInfo.condition_move[goalNodeID], expNodeInfo=self.getExpNodeInfo(expNodeID))
                elif gx-1 == path[i][1]:
                    self.mapInfo.setOneWay(path[i], 0, 1, self.mapInfo.condition_move[goalNodeID], expNodeInfo=self.getExpNodeInfo(expNodeID))
                else: # gx+1 == path[i][1]
                    self.mapInfo.setOneWay(path[i], 0, -1, self.mapInfo.condition_move[goalNodeID], expNodeInfo=self.getExpNodeInfo(expNodeID))

        self.roomsMap = 1 - check_map
           
