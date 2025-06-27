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
        """Return a list of available tiles around a given tile"""
        min_x = max(1, tile.x - 1)
        max_x = min(len(self.world)-2, tile.x + 1)
        min_y = max(1, tile.y - 1)
        max_y = min(len(self.world[tile.x])-2, tile.y + 1)

        available_tiles = [
            (min_x, tile.y),
            (max_x, tile.y),
            (tile.x, min_y),
            (tile.x, max_y),
        ]
        neighbors = []
        for x, y in available_tiles:
            if (x, y) == tile.pos:
                continue

            if self.world[x][y] == 0:
                if (self.world[x-1][y] == 0 and self.world[x+1][y] == 0
                    and self.world[x][y-1] == 0 and self.world[x][y+1] == 0):
                    neighbors.append(TileFixed(x, y))

        return neighbors


class GenBitMap:
    ISEVENT = 1
    PADDING2 = 2
    PADDING = 1

    def __init__(self, pname, func_info, gvar_info, expNode_info, roomSize_info, gotoRoom_list, condition_move):
        (self.graph, ) = pydot.core.graph_from_dot_file(f'{DATA_DIR}/{pname}/{pname}.dot')
        self.edgeInfo = {}
        self.func_info = func_info
        self.gvar_info = gvar_info
        self.expNode_info = expNode_info
        self.roomSize_info = roomSize_info
        self.floorMap = None
        self.roomsMap = None
        self.eventMap = None
        self.room_info = {}
        self.gotoRoom_list = gotoRoom_list
        self.warp_info = []
        self.treasure_info = []
        self.initPos = None
        self.func_warp = {}
        self.warpChara_info = []
        self.exit_info = []
        self.line_info: dict[str, set[int]] = {}
        self.condition_move: list[tuple[str, list[int | None]]] = condition_move

    def setMapChip(self, pname, isUniversal):
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

        defaultMapChips = [503, 113, 343, 160, 32]
        self.floorMap = np.where(self.floorMap == 0, 390, self.floorMap) # gray thick brick
        # self.floorMap = np.where(self.floorMap == 0, 43, self.floorMap) # grass floor
        # self.floorMap = np.where(self.floorMap == 0, 402, self.floorMap) # gray thin brick
        # self.floorMap = np.where(self.floorMap == 0, 31, self.floorMap) # dungeon_floor

        self.setFuncWarp()

        fg.writeMapIni(pname, self.initPos, self.set_gvar())
        fg.writeMapJson(pname, self.floorMap, self.warp_info, self.treasure_info, self.exit_info, self.warpChara_info, isUniversal, defaultMapChips[0])
        fg.writeLineFile(pname, self.line_info)

        plt.imshow(self.floorMap, cmap='gray', interpolation='nearest')
        plt.title(pname)
        plt.savefig(f'{DATA_DIR}/{pname}/bm_{pname}.png')

    def setItemBox(self, roomNodeID, itemName):
        ry, rx, rheight, rwidth = self.room_info[roomNodeID]
        zero_elements = np.argwhere(self.eventMap[ry:ry+rheight, rx:rx+rwidth] == 0)
        if zero_elements.size > 0:
            y, x = zero_elements[np.random.choice(zero_elements.shape[0])]
            itemPos = (int(ry+y), int(rx+x))
            self.eventMap[itemPos[0], itemPos[1]] = self.ISEVENT
            self.treasure_info.append((itemPos, itemName))
        else:
            print("generation failed: try again!! 3")

    def setFuncWarp(self):
        for funcName in self.func_warp.keys():
            funcWarp = self.func_warp[funcName]
            if funcWarp[0] and funcWarp[1]:
                wy, wx, wheight, wwidth = self.room_info[funcWarp[0]]
                zero_elements = np.argwhere(self.eventMap[wy:wy+wheight, wx:wx+wwidth] == 0)
                if zero_elements.size > 0:
                    y, x = zero_elements[np.random.choice(zero_elements.shape[0])]
                    warpPos = (int(wy+y), int(wx+x))
                    self.eventMap[warpPos[0], warpPos[1]] = self.ISEVENT
                    for warpFuncInfo in funcWarp[1]:
                        self.setCharaMoveItems(warpFuncInfo, (funcName, warpPos), funcWarp[2])
    
    def setWarpZone(self, startNodeID, goalNodeID, mapChipNum, diamondNodeID=None):
        sy, sx, sheight, swidth = self.room_info[startNodeID]
        gy, gx, gheight, gwidth = self.room_info[goalNodeID]
        
        #まず遷移元を設定する
        zero_elements = np.argwhere(self.eventMap[sy+1:sy+sheight-1, sx+1:sx+swidth-1] == 0)
        if zero_elements.size > 0:
            y, x = zero_elements[np.random.choice(zero_elements.shape[0])]
            warpFrom = (int(sy+y+1), int(sx+x+1))
            self.eventMap[warpFrom[0], warpFrom[1]] = self.ISEVENT
            #次に遷移先を設定する
            zero_elements = np.argwhere(self.eventMap[gy+1:gy+gheight-1, gx+1:gx+gwidth-1] == 0)
            if zero_elements.size > 0:
                y, x = zero_elements[np.random.choice(zero_elements.shape[0])]
                warpTo = (int(gy+y+1), int(gx+x+1))
                self.eventMap[warpTo[0], warpTo[1]] = self.ISEVENT
                c_move_type, c_move_fromTo = self.condition_move.get(goalNodeID, ['', []])
                # doWhileTrue, ifEndについては上書きする
                if diamondNodeID:
                    c_move_type, c_move_fromTo = self.condition_move[diamondNodeID]
                self.warp_info.append((warpFrom, warpTo, mapChipNum, c_move_type, c_move_fromTo))
                self.line_info[self.func_name].add(c_move_fromTo[0])
            else:
                print("generation failed: try again!! 1")
        else:
            print("generation failed: try again!! 2")

    def setPlayerInitPos(self, initNodeID):  
        py, px, pheight, pwidth = self.room_info[initNodeID]
        zero_elements = np.argwhere(self.eventMap[py+1:py+pheight-1, px+1:px+pwidth-1] == 0)
        if zero_elements.size > 0:
            y, x = zero_elements[np.random.choice(zero_elements.shape[0])]
            self.eventMap[py+y, px+x] = self.ISEVENT
            self.initPos =  (int(py+y+1), int(px+x+1))
        else:
            print("generation failed: try again!! 0")

    #話しかけると別の関数に進むキャラの設定
    def setCharaMoveItems(self, warpFuncInfo, warpTo, arguments):
        roomNodeID, vars, funcName = warpFuncInfo
        gy, gx, gheight, gwidth = self.room_info[roomNodeID]
        zero_elements = np.argwhere(self.eventMap[gy:gy+gheight, gx:gx+gwidth] == 0)
        if zero_elements.size > 0:
            y, x = zero_elements[np.random.choice(zero_elements.shape[0])]
            pos = (int(gy+y), int(gx+x))
            self.eventMap[pos[0], pos[1]] = self.ISEVENT
            self.warpChara_info.append(("CHARAMOVEITEMS", pos, warpTo, vars, funcName, arguments))
        else:
            print("generation failed: try again!! 5")        

    #話しかけると戻るキャラの設定
    def setCharaReturn(self, roomNodeID, line):
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
            self.warpChara_info.append(("CHARARETURN", pos, self.func_name, line_ret))
        else:
            print("generation failed: try again!! 6")

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

        self.line_info[self.func_name].add(line_track[0])

    def startTracking(self):
        self.setEdgeInfo()
        self.func_name = "main"
        refInfo = self.func_info.pop(self.func_name)
        self.floorMap = np.ones((20,20))
        self.roomsMap = np.ones((20,20))
        self.eventMap = np.zeros((20,20))
        self.trackFuncAST(refInfo)

    def set_gvar(self):
        gvarString = ""
        for gvarNodeID in self.gvar_info:
            varName = self.getNodeLabel(gvarNodeID)
            for gvarContentNodeID in self.getEdgeInfo(gvarNodeID):
                #配列
                if self.getNodeShape(gvarContentNodeID) == 'box3d':
                    pass
                #構造体系
                elif self.getNodeShape(gvarContentNodeID) == 'tab':
                    pass
                #ノーマル変数
                elif self.getNodeShape(gvarContentNodeID) == 'square':
                    if gvarString:
                        gvarString = ', '.join([gvarString, f"'{varName}' : {self.expNode_info[gvarContentNodeID]}"])
                    else:
                        gvarString = f"'{varName}' : {self.expNode_info[gvarContentNodeID]}"
                #これはあり得ないがデバッグ用
                else:
                    print("wrong node shape")
        return ''.join(["{", gvarString, "}"])

    def trackFuncAST(self, refInfo):
        nodeID = refInfo["start"]
        self.createRoom(nodeID)

        self.line_info[self.func_name] = set()
        
        #関数呼び出しのワープ情報を更新
        if self.func_name in self.func_warp:
            self.func_warp[self.func_name][0] = nodeID
        else:
            self.func_warp[self.func_name] = [nodeID, [], []]

        for toNodeID in self.getEdgeInfo(nodeID):
            self.trackAST(nodeID, toNodeID)
        
        gotoRooms = self.gotoRoom_list[self.func_name]
        for gotoRoom in gotoRooms.values():
            toNodeID = gotoRoom["toNodeID"]
            fromNodeIDs = gotoRoom["fromNodeID"]
            for fromNodeID in fromNodeIDs:
                #pyramid mapchip = 105
                self.setWarpZone(fromNodeID, toNodeID, 158)

        if self.initPos is None:
            self.setPlayerInitPos(nodeID)
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
            for toNodeID in self.getEdgeInfo(nodeID):
                self.createRoom(toNodeID)
                if self.getNodeShape(toNodeID) == 'circle':
                    #do_whileの同じノードに返って来る用
                    if crntRoomID == toNodeID:
                        self.setWarpZone(crntRoomID, toNodeID, 158, nodeID)
                    else:
                        self.createPath(crntRoomID, toNodeID)
                    nodeIDs.insert(0, toNodeID)
                elif self.getNodeShape(toNodeID) == 'diamond':
                    nodeIDs.append(toNodeID)
                elif self.getNodeShape(toNodeID) == 'invtriangle':
                    self.setWarpZone(crntRoomID, toNodeID, 158)
                    nodeIDs.insert(0, toNodeID)
                elif self.getNodeShape(toNodeID) == 'doublecircle':
                    self.createPath(crntRoomID, toNodeID)
                    # self.setWarpZone(crntRoomID, toNodeID, 158)
                    nodeIDs.append(toNodeID)
                else:
                    print("unknown node appeared")
            for toNodeID in nodeIDs:
                if self.getNodeShape(toNodeID) == 'diamond':
                    self.trackAST(crntRoomID, toNodeID)
                else:
                    self.trackAST(toNodeID, toNodeID)

        #while文とfor文は最終ノードからワープで戻る必要があるので、現在の部屋ノードのID(戻り先)を取得する
        elif self.getNodeShape(nodeID) == 'pentagon':
            #条件文以前の処理を同部屋に含めてはいけない
            self.createRoom(nodeID)
            #エッジの順番がランダムで想定通りに解析されない可能性があるので入れ替える
            nodeIDs = []
            for toNodeID in self.getEdgeInfo(nodeID):
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
                self.trackAST(nodeIDs[0], nodeIDs[0], nodeID)
                self.trackAST(nodeIDs[1], nodeIDs[1])

        #関数のワープ情報を更新する
        elif self.getNodeShape(nodeID) == 'oval':
            funcName = self.getNodeLabel(nodeID)
            funcWarpInfo = [crntRoomID, [], funcName]
            for toNodeID in self.getEdgeInfo(nodeID):
                #関数の引数を関数遷移の鍵とする
                if self.getNodeShape(toNodeID) == 'egg':
                    funcWarpInfo[1].append(self.expNode_info[toNodeID][1])
                    for eggFuncNodeID in self.getEdgeInfo(toNodeID):
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
            self.setCharaReturn(crntRoomID, self.getNodeLabel(nodeID))
        
        # while文とfor文のワープ元である部屋のIDを取得する
        elif self.getNodeShape(nodeID) == 'parallelogram':
            if loopBackID:
                self.setWarpZone(crntRoomID, loopBackID, 158)
                loopBackID = None

        # if文の終点でワープゾーンを作る
        elif self.getNodeShape(nodeID) == 'terminator':
            toNodeID = self.getEdgeInfo(nodeID)[0]
            self.createRoom(toNodeID)
            self.setWarpZone(crntRoomID, toNodeID, 158, nodeID)
            nodeID = toNodeID
            crntRoomID = nodeID

        #変数宣言ノードから遷移するノードの種類で変数のタイプを分ける
        elif self.getNodeShape(nodeID) == 'signature':
            for toNodeID in self.getEdgeInfo(nodeID):
                #配列
                if self.getNodeShape(toNodeID) == 'box3d':
                    self.trackAST(crntRoomID, toNodeID)
                #構造体系
                elif self.getNodeShape(toNodeID) == 'tab':
                    self.trackAST(crntRoomID, toNodeID)
                #ノーマル変数
                elif self.getNodeShape(toNodeID) == 'square':
                    self.setItemBox(crntRoomID, self.getNodeLabel(nodeID))
                #初期化値なし(or次のノード)
                else:
                    self.trackAST(crntRoomID, toNodeID, loopBackID)
        else:
            #switch構文でワープゾーンを繋げる
            if crntRoomID != nodeID:
                if nodeID in self.roomSize_info[self.func_name]:
                    self.createRoom(nodeID)

                if nodeID in self.room_info:
                    self.setWarpZone(crntRoomID, nodeID, 158)
                    crntRoomID = nodeID
                    
        for toNodeID in self.getEdgeInfo(nodeID):
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
    
    def setEdgeInfo(self):
        for edge in self.graph.get_edges():
            if (edgeSource := edge.get_source()) in self.edgeInfo:
                self.edgeInfo[edgeSource].append(edge.get_destination())
            else:
                self.edgeInfo[edgeSource] = [edge.get_destination()]

    def getEdgeInfo(self, fromNodeID):
        if fromNodeID in self.edgeInfo:
            return self.edgeInfo.pop(fromNodeID)
        return []

    def createRoom(self, nodeID):
        if (size := self.roomSize_info[self.func_name].pop(nodeID, None)):
            height = random.randint(4, size-4)
            width = size - height
            mapHeight, mapWidth = self.floorMap.shape
            kernel = np.ones((height+self.PADDING2,width+self.PADDING2))
            self.room_info[nodeID] = self.findRoomArea((height, width), (mapHeight, mapWidth), kernel)

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
            self.eventMap = expand_map(self.eventMap, mapSize, new_shape, fill_value=0)
            return self.findRoomArea(roomSize, (new_height, new_width), kernel)

    def createPath(self, startNodeID, goalNodeID):
        def random_edge_point(ty, lx, height, width):
            h, w = self.floorMap.shape
            candidates = []

            # top edge (y = ty)
            for x in range(lx, lx + width):
                if (0 <= ty-1 < h and 0 <= x < w and self.floorMap[ty, x] != 0 and
                    self.roomsMap[ty, x-1] != 0 and self.roomsMap[ty-1, x] != 0 and self.roomsMap[ty, x+1] != 0):
                    candidates.append((ty, x))

            # bottom edge (y = ty + height - 1)
            for x in range(lx, lx + width):
                y = ty + height
                if (0 <= y < h and 0 <= x < w and self.floorMap[y, x] != 0 and 
                    self.roomsMap[y, x-1] != 0 and self.roomsMap[y+1, x] != 0 and self.roomsMap[y, x+1] != 0):
                    candidates.append((y, x))

            # left edge (x = lx)
            for y in range(ty, ty + height):
                if (0 <= y < h and 0 <= lx-1 < w and self.floorMap[y, lx] != 0 and
                    self.roomsMap[y-1, lx] != 0 and self.roomsMap[y, lx-1] != 0 and self.roomsMap[y+1, lx] != 0):
                    candidates.append((y, lx))

            # right edge (x = lx + width - 1)
            for y in range(ty, ty + height):
                x = lx + width
                if (0 <= y < h and 0 <= x < w and self.floorMap[y, x] != 0 and
                    self.roomsMap[y-1, x] != 0 and self.roomsMap[y, x+1] != 0 and self.roomsMap[y+1, x] != 0):
                    candidates.append((y, x))

            if not candidates:
                return None

            return random.choice(candidates)

        sy, sx, sheight, swidth = self.room_info[startNodeID]
        gy, gx, gheight, gwidth = self.room_info[goalNodeID]

        room_reversed = self.roomsMap
        room_reversed[sy:sy+sheight, sx:sx+swidth] = 1
        room_reversed[gy:gy+gheight, gx:gx+gwidth] = 1
        check_map = 1 - room_reversed

        start = random_edge_point(sy, sx, sheight, swidth)
        goal = (gy - 1 + random.randint(1, gheight), gx - 1 + random.randint(1, gwidth))

        if start is None or goal is None:
            self.setWarpZone(startNodeID, goalNodeID, 158) 
            check_map[sy:sy+sheight, sx:sx+swidth] = 1
            check_map[gy:gy+gheight, gx:gx+gwidth] = 1
            self.roomsMap = 1 - check_map

        check_map[start] = 0
        check_map[goal] = 0

        setExit = False
        path = AStarFixed(check_map).search(start, goal)
        self.floorMap[path[0][0], path[0][1]] = 0
        for i in range(1, len(path)):
            self.floorMap[path[i][0], path[i][1]] = 0

            #出口のための一方通行パネルを設置する
            if setExit is False:
                if (gy-1 <= path[i][0] < gy+gheight+1 and gx <= path[i][1] < gx+gwidth) or (gy <= path[i][0] < gy+gheight and gx-1 <= path[i][1] < gx+gwidth+1):
                    if gy <= path[i+1][0] < gy+gheight and gx <= path[i+1][1] < gx+gwidth:
                        self.setOneWay(path[i], path[i+1][0]-path[i][0], path[i+1][1]-path[i][1], self.condition_move[goalNodeID])
                    else:
                        if gy-1 == path[i][0]:
                            self.setOneWay(path[i], 1, 0, self.condition_move[goalNodeID])
                        elif gy+1 == path[i][0]:
                            self.setOneWay(path[i], -1, 0, self.condition_move[goalNodeID])
                        elif gx-1 == path[i][1]:
                            self.setOneWay(path[i], 0, 1, self.condition_move[goalNodeID])
                        else: # gx+1 == path[i][1]
                            self.setOneWay(path[i], 0, -1, self.condition_move[goalNodeID])
                        break
                    setExit = True

        check_map[sy:sy+sheight, sx:sx+swidth] = 1
        check_map[gy:gy+gheight, gx:gx+gwidth] = 1
        self.roomsMap = 1 - check_map
           
