import json
import configparser
import os 
import random

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = BASE_DIR + '/data'

def writeMapJson(pname, bitMap, warpInfo, itemInfo, exitInfo, chara_moveItemsInfo, chara_returnInfo, isUniversal, defaultMapChip=503):
    events = []
    characters = []

    universal_colors = [15000, 15001, 15089, 15120, 15157, 15162, 15164]

    # ワープの情報
    for warp in warpInfo:
        events.append({"type": "MOVE", "x": warp[0][1], "y": warp[0][0], "mapchip": warp[2], "warpType": warp[3], "fromTo": warp[4],
                       "dest_map": pname, "dest_x": warp[1][1], "dest_y": warp[1][0]})
        
    # アイテムの情報
    for item in itemInfo:
        events.append({"type": "TREASURE", "x": item[0][1], "y": item[0][0], "item": item[1]})

    # 経路の一方通行情報
    for exit in exitInfo:
        events.append({"type": "AUTO", "x": exit[0][1], "y": exit[0][0], "mapchip": exit[1], "autoType": exit[2], "fromTo": exit[3], "sequence": exit[4]})

    # ワープキャラの情報
    ### 関数の呼び出しに応じたキャラクターの情報
    for chara_moveItems in chara_moveItemsInfo:
        pos, warpTo, vars, funcName, arguments = chara_moveItems
        # キャラの色をでランダムにする
        color = random.choice(universal_colors) if isUniversal else random.randint(15102,15161)
        
        characters.append({"type": "CHARAMOVEITEMS", "name": str(color), "x": pos[1], "y": pos[0], "dir": 0, "movetype": 1, "message": f"関数 {warpTo[0]} に遷移します!!", "errmessage": f"関数 {warpTo[0]} に遷移できません!!", "dest_map": pname, "dest_x": warpTo[1][1], "dest_y": warpTo[1][0], "items": vars, "funcName": funcName, "arguments": arguments})
    
    ### 関数の戻りに応じたキャラクターの情報
    for chara_return in chara_returnInfo:
        pos, funcName, line = chara_return
        if funcName == "main":
            characters.append({"type": "CHARARETURN", "name": "15161", "x": pos[1], "y": pos[0], "dir": 0, "movetype": 1, "message": f"おめでとうございます!! ここがゴールです!!", "dest_map": pname, "line": line})
        else:
            characters.append({"type": "CHARARETURN", "name": "15084", "x": pos[1], "y": pos[0], "dir": 0, "movetype": 1, "message": f"ここが関数 {funcName} の終わりです!!", "dest_map": pname, "line": line})

    filename = f'{DATA_DIR}/{pname}/{pname}.json'

    with open(filename, 'w') as f:
        fileContent = {"row": bitMap.shape[0], "col": bitMap.shape[1], "default": defaultMapChip, "map": bitMap.astype(int).tolist(), "characters": characters, "events": events}
        json.dump(fileContent, f) 

def writeMapIni(pname, initPos, gvarString):
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

def writeLineFile(pname: str, line_info: dict[str, set[int]]):
    filename = f'{DATA_DIR}/{pname}/{pname}_line.json'

    line_info_json = {funcname: list(line_nums) for funcname, line_nums in line_info.items()}
    with open(filename, 'w') as f:
        json.dump(line_info_json, f)