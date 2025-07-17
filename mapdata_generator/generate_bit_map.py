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
DATA_DIR = BASE_DIR + '/data'

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
        self.condition_move: dict[str, tuple[str, list[int | None]]] = condition_move
        self.initPos: tuple[int, int] | None = None
        self.warp_info: list[tuple[tuple[int, int], tuple[int, int], int, str]] = []
        self.treasure_info: list[tuple[str, list[str], list[str], int]] = []
        self.chara_moveItems = []
        self.chara_return = []
        self.exit_info = []
        self.door_info: list[tuple[tuple[int, int], str]] = []

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

    # 関数キャラの設定
    def setFuncWarp(self, func_warp):
        for funcName, funcWarp in func_warp.items():
            if funcWarp[0] and funcWarp[1]:
                wy, wx, wheight, wwidth = self.room_info[funcWarp[0]]
                zero_elements = np.argwhere(self.eventMap[wy:wy+wheight, wx:wx+wwidth] == 0)
                if zero_elements.size > 0:
                    y, x = zero_elements[np.random.choice(zero_elements.shape[0])]
                    warpPos = (int(wy+y), int(wx+x))
                    self.eventMap[warpPos[0], warpPos[1]] = self.ISEVENT
                    for warpFuncInfo in funcWarp[1]:
                        self.setCharaMoveItems(warpFuncInfo, (funcName, warpPos), funcWarp[2])

    # 話しかけると別の関数に進むキャラの設定
    def setCharaMoveItems(self, warpFuncInfo, warpTo, arguments):
        roomNodeID, vars, funcName = warpFuncInfo
        gy, gx, gheight, gwidth = self.room_info[roomNodeID]
        zero_elements = np.argwhere(self.eventMap[gy:gy+gheight, gx:gx+gwidth] == 0)
        if zero_elements.size > 0:
            y, x = zero_elements[np.random.choice(zero_elements.shape[0])]
            pos = (int(gy+y), int(gx+x))
            self.eventMap[pos[0], pos[1]] = self.ISEVENT
            self.chara_moveItems.append((pos, warpTo, vars, funcName, arguments))
        else:
            print("generation failed: try again!! 5")        

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
    def setGotoWarpZone(self, gotoRooms):
        for gotoRoom in gotoRooms.values():
            toNodeID = gotoRoom["toNodeID"]
            fromNodeIDs = gotoRoom["fromNodeID"]
            for fromNodeID in fromNodeIDs:
                # pyramid mapchip = 105
                self.setWarpZone(fromNodeID, toNodeID, 158)

    # ワープゾーンの設定
    def setWarpZone(self, startNodeID: str, goalNodeID: str, mapChipNum: int, diamondNodeID: str = None):
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
                # doWhileTrue, ifEndについては上書きする
                if diamondNodeID:
                    c_move_type, c_move_fromTo = self.condition_move[diamondNodeID]
                self.warp_info.append((warpFrom, warpTo, mapChipNum, c_move_type, c_move_fromTo))
            else:
                print("generation failed: try again!! 1")
        else:
            print("generation failed: try again!! 2")

    # スカラー変数に対応した宝箱の設定
    def setItemBox(self, roomNodeID, itemName, item_exp_Info: tuple[str, list[str], list[str], int], var_type: str):
        ry, rx, rheight, rwidth = self.room_info[roomNodeID]
        zero_elements = np.argwhere(self.eventMap[ry:ry+rheight, rx:rx+rwidth] == 0)
        if zero_elements.size > 0:
            y, x = zero_elements[np.random.choice(zero_elements.shape[0])]
            itemPos = (int(ry+y), int(rx+x))
            self.eventMap[itemPos[0], itemPos[1]] = self.ISEVENT
            self.treasure_info.append((itemPos, itemName, item_exp_Info, var_type))
        else:
            print("generation failed: try again!! 3")

    # 一方通行パネルの設定
    def setOneWay(self, pos, dy, dx, condition_move):
        self.eventMap[pos[0], pos[1]] = self.ISEVENT
        
        autoType, line_track = condition_move

        #left
        if dx == -1:
            self.exit_info.append((pos, 7, autoType, line_track, "l"))
        #up
        elif dy == -1:
            self.exit_info.append((pos, 6, autoType, line_track, "u"))
        #right
        elif dx == 1:
            self.exit_info.append((pos, 7, autoType, line_track, "r"))
        #down
        elif dy == 1:
            self.exit_info.append((pos, 6, autoType, line_track, "d"))

    # 出口のドア生成
    def setDoor(self, pos):
        self.door_info.append((pos, "test"))
        self.eventMap[pos[0], pos[1]] = self.ISEVENT

    # マップデータの生成
    def mapDataGenerator(self, pname: str, gvar_str: str, floorMap, isUniversal: bool, line_info: dict[str, set[int]]):
        defaultMapChips = [503, 113, 343, 160, 32]
        floorMap = np.where(floorMap == 0, 390, floorMap) # gray thick brick
        # self.floorMap = np.where(self.floorMap == 0, 43, self.floorMap) # grass floor
        # self.floorMap = np.where(self.floorMap == 0, 402, self.floorMap) # gray thin brick
        # self.floorMap = np.where(self.floorMap == 0, 31, self.floorMap) # dungeon_floor

        fg.writeMapIni(pname, self.initPos, gvar_str)
        fg.writeMapJson(pname, floorMap, self.warp_info, self.treasure_info, self.exit_info, self.chara_moveItems, self.chara_return, self.door_info, isUniversal, defaultMapChips[0])
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
    def __init__(self, pname: str, func_info, gvar_info, varNode_info: dict[str, str], expNode_info: dict[str, tuple[str, list[str], list[str], int]], roomSize_info, 
                 gotoRoom_list: dict[str, dict[str, GotoRoomInfo]], condition_move):
        
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
        self.func_warp = {}
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

        self.mapInfo.setFuncWarp(self.func_warp)

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
        
        #関数呼び出しのワープ情報を更新
        if self.func_name in self.func_warp:
            self.func_warp[self.func_name][0] = nodeID
        else:
            self.func_warp[self.func_name] = [nodeID, [], []]

        for toNodeID, edgeLabel in self.getNextNodeInfo(nodeID):
            self.trackAST(nodeID, toNodeID)
        
        self.mapInfo.setGotoWarpZone(self.gotoRoom_list[self.func_name])

        self.mapInfo.setPlayerInitPos(nodeID)

        for ref in refInfo["refs"]:
            if (nextRefInfo := self.func_info.pop(ref, None)):
                self.func_name = ref
                self.trackFuncAST(nextRefInfo)
    
    def trackAST(self, crntRoomID, nodeID, loopBackID = None):
        #引数を取得
        if self.getNodeShape(nodeID) == 'cylinder':
            self.func_warp[self.func_name][2].append(self.getNodeLabel(nodeID))
        #if文とdo_while文とswitch文
        elif self.getNodeShape(nodeID) == 'diamond':
            nodeIDs = []
            #エッジの順番がランダムで想定通りに解析されない可能性があるので入れ替える
            for toNodeID, edgeLabel in self.getNextNodeInfo(nodeID):
                self.createRoom(toNodeID)
                if self.getNodeShape(toNodeID) == 'circle':
                    #do_whileの同じノードに返って来る用
                    if crntRoomID == toNodeID:
                        self.mapInfo.setWarpZone(crntRoomID, toNodeID, 158, nodeID)
                    else:
                        self.createPath(crntRoomID, toNodeID)
                    nodeIDs.insert(0, toNodeID)
                elif self.getNodeShape(toNodeID) == 'diamond':
                    nodeIDs.append(toNodeID)
                elif self.getNodeShape(toNodeID) == 'invtriangle':
                    self.mapInfo.setWarpZone(crntRoomID, toNodeID, 158)
                    nodeIDs.insert(0, toNodeID)
                elif self.getNodeShape(toNodeID) == 'doublecircle':
                    self.createPath(crntRoomID, toNodeID)
                    # self.setWarpZone(crntRoomID, toNodeID, 158)
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

        #while文とfor文は最終ノードからワープで戻る必要があるので、現在の部屋ノードのID(戻り先)を取得する
        elif self.getNodeShape(nodeID) == 'pentagon':
            #条件文以前の処理を同部屋に含めてはいけない
            self.createRoom(nodeID)
            #エッジの順番がランダムで想定通りに解析されない可能性があるので入れ替える
            nodeIDs = []
            for toNodeID, edgeLabel in self.getNextNodeInfo(nodeID):
                self.createRoom(toNodeID)
                if self.getNodeShape(toNodeID) == 'circle':
                    self.createPath(nodeID, toNodeID)
                    nodeIDs.insert(0, toNodeID)
                elif self.getNodeShape(toNodeID) == 'doublecircle':
                    self.createPath(nodeID, toNodeID)
                    # self.setWarpZone(nodeID, toNodeID, 158)
                    nodeIDs.append(toNodeID)
            if nodeIDs:
                #whileの領域に入る
                self.createPath(crntRoomID, nodeID)
                # true
                self.trackAST(nodeIDs[0], nodeIDs[0], nodeID)
                # false
                self.trackAST(nodeIDs[1], nodeIDs[1], loopBackID)

        #関数のワープ情報を更新する
        elif self.getNodeShape(nodeID) == 'oval':
            funcName = self.getNodeLabel(nodeID)
            funcWarpInfo = [crntRoomID, [], funcName]
            for toNodeID, edgeLabel in self.getNextNodeInfo(nodeID):
                #関数の引数を関数遷移の鍵とする
                if self.getNodeShape(toNodeID) == 'egg':
                    eni = self.getExpNodeInfo(toNodeID)
                    funcWarpInfo[1].append(eni[1])
                    for eggFuncNodeID, edgeLabel in self.getNextNodeInfo(toNodeID):
                        self.trackAST(crntRoomID, eggFuncNodeID)
                #それ以外は次のノードに進む
                else:
                    self.trackAST(crntRoomID, toNodeID)
            #関数のノードはidをつけて唯一性を確保している
            funcType = f'{funcName.split()[0][1:]}'
            if funcType in self.func_warp:
                self.func_warp[funcType][1].append(tuple(funcWarpInfo))
            else:
                self.func_warp[funcType] = [None, [tuple(funcWarpInfo)], []]
        
        #話しかけると関数の遷移元に戻るようにする
        elif self.getNodeShape(nodeID) == 'lpromoter':
            # returnノードに行数ラベルをつけて、それで行数を確認する
            self.mapInfo.setCharaReturn(crntRoomID, self.getNodeLabel(nodeID), self.func_name)
        
        # while文とfor文のワープ元である部屋のIDを取得する
        elif self.getNodeShape(nodeID) == 'parallelogram':
            if loopBackID:
                self.mapInfo.setWarpZone(crntRoomID, loopBackID, 158)
                loopBackID = None

        # if文の終点でワープゾーンを作る
        elif self.getNodeShape(nodeID) == 'terminator':
            toNodeID, edgeLabel = self.getNextNodeInfo(nodeID)[0]
            self.createRoom(toNodeID)
            self.mapInfo.setWarpZone(crntRoomID, toNodeID, 158, nodeID)
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
        # for文の初期値で変数の初期化がある場合はアイテムを作る ()
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
        # elif self.getNodeShape(nodeID) == 'hexagon':
        #     toNodeID, _ = self.getNextNodeInfo(nodeID)[0]
        #     self.createRoom(toNodeID)
        #     self.mapInfo.setWarpZone(crntRoomID, toNodeID, 158)
        else:
            # switch構文でワープゾーンを繋げる
            if crntRoomID != nodeID:
                if nodeID in self.roomSize_info[self.func_name]:
                    self.createRoom(nodeID)

                if nodeID in self.mapInfo.room_info:
                    self.mapInfo.setWarpZone(crntRoomID, nodeID, 158)
                    crntRoomID = nodeID
                    
        for toNodeID, edgeLabel in self.getNextNodeInfo(nodeID):
            print(f"{self.getNodeShape(toNodeID)} - {loopBackID}")
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
        # tuple[str, list[str], list[str], int]
        return self.expNode_info.pop(nodeID, ("", [], [], 0))

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

    def createPath(self, startNodeID, goalNodeID):
        def get_edge_point(start, goal):
            def random_edge_point(dir):
                candidates = []
                # top edge (y = sy)
                if dir == 'up':
                    for x in range(sx, sx + swidth):
                        if (0 <= sy-1 < h and 0 <= x < w and self.floorMap[sy, x] != 0 and 
                            self.roomsMap[sy, x-1] != 0 and self.roomsMap[sy-1, x] != 0 and self.roomsMap[sy, x+1] != 0):
                            candidates.append((sy, x))

                # bottom edge (y = sy + height - 1)
                elif dir == 'down':
                    for x in range(sx, sx + swidth):
                        y = sy + sheight
                        if (0 <= y < h and 0 <= x < w and self.floorMap[y, x] != 0 and 
                            self.roomsMap[y, x-1] != 0 and self.roomsMap[y+1, x] != 0 and self.roomsMap[y, x+1] != 0):
                            candidates.append((y, x))

                # left edge (x = sx)
                elif dir == 'left':
                    for y in range(sy, sy + sheight):
                        if (0 <= y < h and 0 <= sx-1 < w and self.floorMap[y, sx] != 0 and 
                            self.roomsMap[y-1, sx] != 0 and self.roomsMap[y, sx-1] != 0 and self.roomsMap[y+1, sx] != 0):
                            candidates.append((y, sx))

                # right edge (x = sx + width - 1)
                elif dir == 'right':
                    for y in range(sy, sy + sheight):
                        x = sx + swidth
                        if (0 <= y < h and 0 <= x < w and self.floorMap[y, x] != 0 and 
                            self.roomsMap[y-1, x] != 0 and self.roomsMap[y, x+1] != 0 and self.roomsMap[y+1, x] != 0):
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

            edge_point = None

            if abs(dy) > abs(dx):
                edge_point = random_edge_point('down') if dy > 0 else random_edge_point('up')
            else:
                edge_point = random_edge_point('right') if dx > 0 else random_edge_point('left')

            if edge_point is None:
                if abs(dy) > abs(dx):
                    edge_point = random_edge_point('right') if dx > 0 else random_edge_point('left')
                else:
                    edge_point = random_edge_point('down') if dy > 0 else random_edge_point('up')
            
            return edge_point

        sy, sx, sheight, swidth = self.mapInfo.room_info[startNodeID]
        gy, gx, gheight, gwidth = self.mapInfo.room_info[goalNodeID]

        room_reversed = self.roomsMap
        # room_reversed[sy:sy+sheight, sx:sx+swidth] = 1
        room_reversed[gy:gy+gheight, gx:gx+gwidth] = 1
        check_map = 1 - room_reversed

        start = get_edge_point(self.mapInfo.room_info[startNodeID], self.mapInfo.room_info[goalNodeID])
        goal = (gy - 1 + random.randint(1, gheight), gx - 1 + random.randint(1, gwidth))

        if start is None or goal is None:
            self.mapInfo.setWarpZone(startNodeID, goalNodeID, 158) 
            # check_map[sy:sy+sheight, sx:sx+swidth] = 1
            check_map[gy:gy+gheight, gx:gx+gwidth] = 1
            self.roomsMap = 1 - check_map
        else:
            check_map[start] = 0
            check_map[goal] = 0

            setExit = False
            path = AStarFixed(check_map).search(start, goal)

            if path is None:
                self.mapInfo.setWarpZone(startNodeID, goalNodeID, 158) 
            else:
                self.floorMap[path[0][0], path[0][1]] = 0
                self.mapInfo.setDoor(path[0])
                for i in range(1, len(path)):
                    self.floorMap[path[i][0], path[i][1]] = 0

                    #出口のための一方通行パネルを設置する
                    if setExit is False:
                        if (gy-1 <= path[i][0] < gy+gheight+1 and gx <= path[i][1] < gx+gwidth) or (gy <= path[i][0] < gy+gheight and gx-1 <= path[i][1] < gx+gwidth+1):
                            if gy <= path[i+1][0] < gy+gheight and gx <= path[i+1][1] < gx+gwidth:
                                self.mapInfo.setOneWay(path[i], path[i+1][0]-path[i][0], path[i+1][1]-path[i][1], self.mapInfo.condition_move[goalNodeID])
                            else:
                                if gy-1 == path[i][0]:
                                    self.mapInfo.setOneWay(path[i], 1, 0, self.mapInfo.condition_move[goalNodeID])
                                elif gy+1 == path[i][0]:
                                    self.mapInfo.setOneWay(path[i], -1, 0, self.mapInfo.condition_move[goalNodeID])
                                elif gx-1 == path[i][1]:
                                    self.mapInfo.setOneWay(path[i], 0, 1, self.mapInfo.condition_move[goalNodeID])
                                else: # gx+1 == path[i][1]
                                    self.mapInfo.setOneWay(path[i], 0, -1, self.mapInfo.condition_move[goalNodeID])
                                break
                            setExit = True

        # check_map[sy:sy+sheight, sx:sx+swidth] = 1
        check_map[gy:gy+gheight, gx:gx+gwidth] = 1
        self.roomsMap = 1 - check_map
           
