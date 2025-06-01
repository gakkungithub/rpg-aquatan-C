import json
import configparser
import os 

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = BASE_DIR + '/data'

def writeMapJson(pname, bitMap, warpInfo, itemInfo, exitInfo, warpCharaInfo):
    events = []
    characters = []

    #ワープの情報
    for warp in warpInfo:
        events.append({"type": "MOVE", "x": warp[0][1], "y": warp[0][0], "mapchip": warp[2], "warpType": warp[3], "fromTo": warp[4],
                       "dest_map": pname, "dest_x": warp[1][1], "dest_y": warp[1][0]})
        
    #アイテムの情報
    for item in itemInfo:
        events.append({"type": "TREASURE", "x": item[0][1], "y": item[0][0], "item": item[1]})

    #経路の一方通行情報
    for exit in exitInfo:
        events.append({"type": "AUTO", "x": exit[0][1], "y": exit[0][0], "mapchip": exit[1], "autoType": exit[2], "fromTo": exit[3], "sequence": exit[4]})

    #ゴールの案内人の情報
    for warpChara in warpCharaInfo:
        type, pos, *otherInfo = warpChara
        if type == "CHARAMOVEITEMS":
            warpTo, vars, funcName, arguments = otherInfo
            characters.append({"type": type, "name": "15001", "x": pos[1], "y": pos[0], "dir": 0, "movetype": 1, "message": f"関数 {warpTo[0]} に遷移します!!", "errmessage": f"関数 {warpTo[0]} に遷移できません!!", "dest_map": pname, "dest_x": warpTo[1][1], "dest_y": warpTo[1][0], "items": vars, "funcName": funcName, "arguments": arguments})
        elif type == "CHARARETURN":
            if otherInfo[0] == "main":
                characters.append({"type": type, "name": "15161", "x": pos[1], "y": pos[0], "dir": 0, "movetype": 1, "message": f"おめでとうございます!! ここがゴールです!!", "dest_map": pname, "line": otherInfo[1]})
            else:
                characters.append({"type": type, "name": "15084", "x": pos[1], "y": pos[0], "dir": 0, "movetype": 1, "message": f"ここが関数 {otherInfo[0]} の終わりです!!", "dest_map": pname, "line": otherInfo[1]})

    filename = f'{DATA_DIR}/{pname}/{pname}.json'

    with open(filename, 'w') as f:
        fileContent = {"row": bitMap.shape[0], "col": bitMap.shape[1], "default": 503, "map": bitMap.astype(int).tolist(), "characters": characters, "events": events}
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

def writeLineFile(pname, line_info):
    filename = f'{DATA_DIR}/{pname}/{pname}_line.json'

    line_info_serializable = {
        k: list(v) for k, v in line_info.items()
    }
    with open(filename, 'w') as f:
        json.dump(line_info_serializable, f)