#!/usr/bin/env python3
"""RPGあくあたん"""
import codecs
import os
import subprocess
import random
import struct
import sys
# socket通信を行う
import socket
import json
import ast
import time
import math
import datetime
from threading import Thread
from configparser import ConfigParser
import ephem
#from genericpath import exists
import pygame
import pygame.freetype
from pygame.locals import *

import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = BASE_DIR + '/mapdata'

#FONT_NAME = "Boku2-Regular.otf"
#FONT_NAME = "logotypejp_mp_b_1.ttf"
#FONT_NAME = "rounded-mgenplus-1cp-bold.ttf"
FONT_DIR = './font/'
FONT_NAME = "PixelMplus12-Bold.ttf"

# fpsはデフォルト
MAX_FRAME_PER_SEC = 24

GS = 32
DOWN, LEFT, RIGHT, UP = 0, 1, 2, 3
STOP, MOVE = 0, 1  # 移動タイプ
PROB_MOVE = 0.0075  # 移動確率
TRANS_COLOR = (190, 179, 145)  # マップチップの透明色

SBW_WIDTH = 800
SBW_HEIGHT = 600

MSGWND = None
DIMWND = None
LIGHTWND = None
STATUSWND = None
ITEMWND = None

PLAYER = None

e = []
AUTOMOVE = 1

BUTTON_WINDOW = None
BUTTON_WIDTH = 50
PATH = 'foot_print.csv'

cmd = "aquatan"
# time [ms]
INTERVAL = 100
mouse_down = False
last_action_time = 0

LONGPRESS_EVENT = pygame.USEREVENT + 1

# 長押し処理をするためのメソッド (200m秒後に長押しイベントをキューに追加する = キューの中の複数の処理が順に実行されていく)
def start_timer():
    pygame.time.set_timer(LONGPRESS_EVENT, 200)
def end_timer():
    pygame.time.set_timer(LONGPRESS_EVENT, 0)

#                                               
#                               88              
#                               ""              
#                                               
# 88,dPYba,,adPYba,  ,adPPYYba, 88 8b,dPPYba,   
# 88P'   "88"    "8a ""     `Y8 88 88P'   `"8a  
# 88      88      88 ,adPPPPP88 88 88       88  
# 88      88      88 88,    ,88 88 88       88  
# 88      88      88 `"8bbdP"Y8 88 88       88  
#                                               
#                                               
# 

def main():
    """Main"""
    global MSGWND, PLAYER, DIMWND, LIGHTWND, STATUSWND, ITEMWND, cmd
    # 現状はグローバル変数にしているが、今後どうするかは考える
    global SCR_RECT, SCR_WIDTH, SCR_HEIGHT, MIN_MAP_SIZE, TXTBOX_HEIGHT

    pygame.init()

    SBW_RECT = Rect(0, 0, SBW_WIDTH, SBW_HEIGHT)

    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.abspath("modules") + (
        ":" + env["PYTHONPATH"] if "PYTHONPATH" in env else ""
    )

    while True:
        if os.uname()[0] != 'Darwin':
            drivers = ['fbcon', 'directfb', 'svgalib']
            found = False
            for driver in drivers:
                # Make sure that SDL_VIDEODRIVER is set
                if not os.getenv('SDL_VIDEODRIVER'):
                    os.putenv('SDL_VIDEODRIVER', driver)
                try:
                    pygame.display.init()
                except pygame.error:
                    print(f'Driver: {driver} failed.')
                    continue
                found = True
                break
            if not found:
                raise Exception('No suitable video driver found!')

            size = (pygame.display.Info().current_w,
                    pygame.display.Info().current_h)
            print(f"Framebuffer size: {size[0]} x {size[1]}")
            screen = pygame.display.set_mode(SBW_RECT.size, FULLSCREEN)
        else:
            scropt = DOUBLEBUF | HWSURFACE
            screen = pygame.display.set_mode(SBW_RECT.size, scropt)

        SBWND = StageButtonWindow()
        SBWND.show()
        SBWND.draw(screen)
        pygame.display.update()

        # region ステージ選択メニュー
        stage_name = None
        code_name = None
        last_mouse_pos = None
        mouse_down = False
        scroll_start = False
        server = None
        
        try:
            while stage_name is None:
                for event in pygame.event.get():
                    if event.type == QUIT:
                        print('ゲームを終了しました')
                        sys.exit()
                    if event.type == KEYDOWN and event.key == K_ESCAPE:
                        print('ゲームを終了しました')
                        sys.exit()

                    # region mouse click event
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        if event.button == 1 and SBWND.is_visible:
                            mouse_down = True
                            code_name = SBWND.is_clicked(event.pos)
                            last_mouse_pos = event.pos
                    elif event.type == pygame.MOUSEBUTTONUP:
                        if event.button == 1 and SBWND.is_visible:
                            if code_name == SBWND.is_clicked(event.pos) == 'color support':
                                SBWND.color_support = not SBWND.color_support
                            elif code_name == SBWND.is_clicked(event.pos) == 'check lldb':
                                if server is not None:
                                    SBWND.close()
                                    server = None
                                else:
                                    SBWND.stage_selecting = not SBWND.stage_selecting
                            # ステージのボタンを押した場合
                            elif code_name is not None and scroll_start == False and code_name == SBWND.is_clicked(event.pos):
                                if SBWND.stage_selecting:
                                    SBWND.hide()
                                    stage_name = code_name
                                elif server is None:
                                    programname = code_name
                                    programpath = f"{DATA_DIR}/{programname}/{programname}"
                                    # 現在は一つのcファイルにしか対応してないので、下記のようにリストに要素を一つだけ入れる
                                    # cfiles = [f"{DATA_DIR}/{programname}/{cfile}" for cfile in args.cfiles]
                                    cfiles = [f"{programpath}.c"]

                                    # cプログラムを整形する
                                    subprocess.run(["clang-format", "-i", f"{programpath}.c"])

                                    subprocess.run(["gcc", "-g", "-o", programpath, " ".join(cfiles)])
                                    server = subprocess.Popen(["/opt/homebrew/opt/python@3.13/bin/python3.13", "checking_lldb.py", "--name", programpath], cwd="debugger-C", env=env)
                                    SBWND.start_checking_lldb()
                            mouse_down = False
                            scroll_start = False
                    if mouse_down and event.type == pygame.MOUSEMOTION:
                        scroll_start = True
                        dx = - (event.pos[0] - last_mouse_pos[0])
                        if 0 <= SBWND.scrollX + dx <= SBWND.maxScrollX:
                            SBWND.scrollX += dx
                        elif SBWND.scrollX + dx < 0:
                            SBWND.scrollX = 0
                        else:
                            SBWND.scrollX = SBWND.maxScrollX
                        if dx != 0:
                            SBWND.load_sb()
                        last_mouse_pos = event.pos
                    
                    if server is not None and event.type == KEYDOWN and (event.key == K_SPACE or event.key == K_RETURN):
                        # ステップ実行してプログラムの終了に到達した時プログラムを終了する
                        if SBWND.step_into():
                            SBWND.close()
                            server = None
                    
                    SBWND.draw(screen)
                    pygame.display.update()
        except Exception as e:
            if e == SystemExit:
                return
            continue
        # endregion

        # region マップデータ生成
        programpath = f"{DATA_DIR}/{stage_name}/{stage_name}"
        # 現在は一つのcファイルにしか対応してないので、下記のようにリストに要素を一つだけ入れる
        # cfiles = [f"{DATA_DIR}/{programname}/{cfile}" for cfile in args.cfiles]
        cfiles = [f"{programpath}.c"]

        # cプログラムを整形する
        subprocess.run(["clang-format", "-i", f"{programpath}.c"])

        # cファイルを解析してマップデータを生成する
        # args.universalがあるなら -uオプションをつけてカラーユニバーサルデザインを可能にする
        cfcode = ["python3.13", "c-flowchart.py", "-p", stage_name, "-c", ", ".join(cfiles)]
        if SBWND.color_support:
            cfcode.append("-u")
        try:
            subprocess.run(cfcode, cwd="mapdata_generator", check=True)
        except subprocess.CalledProcessError as e:
            print(f"subprocess failed with exit code {e.returncode}")
            sys.exit(1)   # 呼び出し元プログラムを終了

        subprocess.run(["gcc", "-g", "-o", programpath, " ".join(cfiles)])

        # サーバを立てる
        server = subprocess.Popen(["/opt/homebrew/opt/python@3.13/bin/python3.13", "c-backdoor.py", "--name", programpath], cwd="debugger-C", env=env)
        # endregion

        # region マップの初期設定
        config = ConfigParser()
        config.read(f"mapdata/{stage_name}/{stage_name}.ini")
        SCR_WIDTH = int(config.get('screen', 'width'))
        SCR_HEIGHT = int(config.get('screen', 'height'))

        PAUSE_RECT = Rect(0, 0, SCR_WIDTH, SCR_HEIGHT)

        SCR_RECT = Rect(0, 0, SCR_WIDTH, SCR_HEIGHT)
        DB_CHECK_WAIT = 30 * MAX_FRAME_PER_SEC
        SCR_RECT_WITH_TXTBOX = Rect(0, 0, SCR_WIDTH, SCR_HEIGHT)
        TXTBOX_HEIGHT = 40
        TXTBOX_RECT = Rect(0, SCR_HEIGHT - TXTBOX_HEIGHT, SCR_WIDTH, TXTBOX_HEIGHT)

        ## ミニマップの表示座標を設定する
        MIN_MAP_SIZE = 300
        MMAP_RECT = Rect(SCR_WIDTH - MIN_MAP_SIZE - 10, 10, MIN_MAP_SIZE, MIN_MAP_SIZE)

        ## デバッグコードの表示座標を設定する
        MIN_CODE_SIZE_Y = 600
        MCODE_RECT = Rect(SCR_WIDTH - MIN_MAP_SIZE - 10, 10, MIN_MAP_SIZE, MIN_CODE_SIZE_Y)

        if os.uname()[0] != 'Darwin':
            drivers = ['fbcon', 'directfb', 'svgalib']
            found = False
            for driver in drivers:
                # Make sure that SDL_VIDEODRIVER is set
                if not os.getenv('SDL_VIDEODRIVER'):
                    os.putenv('SDL_VIDEODRIVER', driver)
                try:
                    pygame.display.init()
                except pygame.error:
                    print(f'Driver: {driver} failed.')
                    continue
                found = True
                break
            if not found:
                raise Exception('No suitable video driver found!')

            size = (pygame.display.Info().current_w,
                    pygame.display.Info().current_h)
            print(f"Framebuffer size: {size[0]} x {size[1]}")
            screen = pygame.display.set_mode(SCR_RECT_WITH_TXTBOX.size, FULLSCREEN)
        else:
            scropt = DOUBLEBUF | HWSURFACE
            screen = pygame.display.set_mode(SCR_RECT_WITH_TXTBOX.size, scropt)

        # region ポーズ画面の設定
        PAUSEWND = PauseWindow(PAUSE_RECT)
        # endregion

        # region コマンドラインの設定
        pygame.draw.rect(screen, (0,0,0), TXTBOX_RECT)
        font = pygame.font.Font(None, 36)
        text_surface = font.render("Command Box:", True, (255, 255, 255))
        screen.blit(text_surface, (10, SCR_RECT.height + 10))
        input_text = "hogehoge"
        input_surface = font.render(input_text, True, (255, 255, 255))
        screen.blit(input_surface, (10, SCR_RECT.height + 40))
        # endregion

        atxt = ""
        # endregion

        print("1")
        ## set mouse visible for debug
        ## pygame.mouse.set_visible(0)
        print("2")
        # pygame.display.set_caption("あくあたんクエスト")
        # キャラクターチップをロード
        load_charachips("data", "charachip.dat")
        print("3")
        # マップチップをロード
        load_mapchips("data", "mapchip.dat")
        # マップとプレイヤー作成
        print("4")

        # region キャラクターの初期設定
        player_chara = str(config.get("game", "player"))
        player_x = int(config.get("game", "player_x"))
        player_y = int(config.get("game", "player_y"))
        mapname = str(config.get("game", "map"))

        # グローバル変数 = 初期アイテム
        items = ast.literal_eval(config.get("game", "items"))

        ## コードウィンドウを作る
        CODEWND = CodeWindow(MCODE_RECT, mapname)

        sender = EventSender(CODEWND)
        
        PLAYER = Player(player_chara, (player_x, player_y), DOWN, sender)
        initialResult = sender.receive_json()
        if "end" in initialResult:
            PLAYER.fp.write( "end, " + mapname + "," + str(PLAYER.x)+", " + str(PLAYER.y) + "\n")
            PLAYER.fp.close()
            server.terminate()
            sys.exit()
        
        PLAYER.func = initialResult["firstFunc"]

        for gvar_name, item_info in initialResult["items"].items():
            for line, values in item_info.items():
                PLAYER.commonItembag.add(Item(gvar_name, int(line), values, {"values": items[gvar_name]["values"]}, items[gvar_name]["type"]))

        BTNWND = ArrowButtonWindow()
        BTNWND.show()
        mouse_down = False

        fieldmap = Map(mapname)
        fieldmap.add_chara(PLAYER)

        # region ウィンドウの設定
        message_engine = MessageEngine()
        MSGWND = MessageWindow(
            Rect(SCR_WIDTH // 4 , SCR_HEIGHT // 3 * 2, 
                SCR_WIDTH // 2, SCR_HEIGHT // 4), message_engine, sender)
        DIMWND = DimWindow(Rect(0, 0, SCR_WIDTH, SCR_HEIGHT + TXTBOX_HEIGHT), screen)
        DIMWND.hide()
        LIGHTWND = LightWindow(Rect(0, 0, SCR_WIDTH, SCR_HEIGHT), screen, fieldmap)
        LIGHTWND.set_color_scene("normal")
        LIGHTWND.show()

        STATUSWND = StatusWindow(Rect(10, 10, SCR_WIDTH // 5 - 10, SCR_HEIGHT // 5 - 10),PLAYER)
        STATUSWND.show()

        ITEMWND_RECT = Rect(10, 10 + SCR_HEIGHT // 5, SCR_WIDTH // 5 - 10, SCR_HEIGHT // 5 * 3 - 10)
        BIG_ITEMWND_RECT = Rect(10, 10 + SCR_HEIGHT // 5, SCR_WIDTH - MIN_MAP_SIZE - 30, SCR_HEIGHT // 5 * 3 - 10)
        ITEMWND = ItemWindow(ITEMWND_RECT, PLAYER)
        ITEMWND.hide()

        CMNDWND = CommandWindow(TXTBOX_RECT)
        CMNDWND.show()

        ## ミニマップを作る
        MMAPWND = MiniMapWindow(MMAP_RECT, mapname)
        MMAPWND.show()

        # endregion
        clock = pygame.time.Clock()
        print("5")

        db_check_count = 0

        print("6")
        lightrooms = []
        lightrooms = list(set(lightrooms))
        LIGHTWND.set_rooms(lightrooms)

        PLAYER.fp.write("start," + mapname + "," + str(PLAYER.x)+", " + str(PLAYER.y) + "\n")

        last_mouse_pos = None
        
        while not PLAYER.goaled:
            clock.tick(MAX_FRAME_PER_SEC)
            # メッセージウィンドウ表示中は更新を中止
            if not MSGWND.is_visible:
                fieldmap.update()

            MSGWND.update()
            offset = calc_offset(PLAYER)
            if not DIMWND.is_visible:
                fieldmap.draw(screen, offset)
            else:
                DIMWND.dim()
                if MSGWND.is_visible:
                    MSGWND.msgwincount += 1
                MSGWND.next(fieldmap)
                pygame.display.update()
                continue

            # For every interval
            if db_check_count > DB_CHECK_WAIT:
                db_check_count = 0
                lightrooms = []
                lightrooms = list(set(lightrooms))
                LIGHTWND.set_rooms(lightrooms)

            db_check_count = db_check_count + 1

            LIGHTWND.draw(offset)
            MSGWND.draw(screen)
            STATUSWND.draw(screen)
            ITEMWND.draw(screen)
            BTNWND.draw(screen)
            MMAPWND.draw(screen, fieldmap)
            CODEWND.draw(screen)

            draw_string(screen, SCR_WIDTH-60, 10,
                        f"{PLAYER.x},{PLAYER.y}", Color(255, 255, 255, 128))  # プレイヤー座標
            pygame.display.update()

            if MSGWND.is_visible:
                MSGWND.msgwincount += 1

            for event in pygame.event.get():
                if event.type == QUIT:
                    PLAYER.fp.write( "end, " + mapname + "," + str(PLAYER.x)+", " + str(PLAYER.y) + "\n")
                    PLAYER.fp.close()
                    server.terminate()
                    sys.exit()
                if event.type == KEYDOWN and event.key == K_ESCAPE:
                    PLAYER.fp.write( "end, " + mapname + "," + str(PLAYER.x)+", " + str(PLAYER.y) + "\n")
                    PLAYER.fp.close()
                    server.terminate()
                    sys.exit()

                # region mouse click event
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mouse_down = True
                    start_timer()
                    if CODEWND.is_visible:
                        local_pos = (event.pos[0] - CODEWND.x, event.pos[1] - CODEWND.y)
                        if CODEWND.auto_scroll_button_rect.collidepoint(local_pos):
                            CODEWND.is_auto_scroll = True
                            CODEWND.scrollY = 0
                            CODEWND.scrollX = 0
                        elif CODEWND.isCursorInWindow(event.pos):
                            last_mouse_pos = event.pos
                        elif ITEMWND.isCursorInWindow(event.pos):
                            pass
                    if len(PLAYER.funcInfoWindow_list):
                        PLAYER.funcInfoWindow_list[PLAYER.funcInfoWindowIndex].isCursorInWindow(event.pos)

                    cmd = BTNWND.is_clicked(event.pos)
                    
                elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                    mouse_down = False
                    last_mouse_pos = None
                    end_timer()
                    if cmd == "pause" and cmd == BTNWND.is_clicked(event.pos):
                        # ここより下の部分を関数化するかどうかは後で考える
                        PAUSEWND.show()
                        PAUSEWND.draw(screen)
                        pygame.display.update()
                        while PAUSEWND.is_visible:
                            for event in pygame.event.get():
                                if event.type == QUIT:
                                    server.terminate()
                                    print('ゲームを終了しました')
                                    sys.exit()
                                if event.type == KEYDOWN and event.key == K_ESCAPE:
                                    server.terminate()
                                    print('ゲームを終了しました')
                                    sys.exit()

                                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and PAUSEWND.is_visible:
                                    local_pos = (event.pos[0] - PAUSEWND.x, event.pos[1] - PAUSEWND.y)
                                    if PAUSEWND.button_toGame_rect.collidepoint(local_pos):
                                        cmd = ""
                                        PAUSEWND.hide()
                                    elif PAUSEWND.button_toStageSelect_rect.collidepoint(local_pos):
                                        cmd = ""    
                                        PAUSEWND.hide()
                                        PLAYER.goaled = True   
                                    # elif PAUSEWND.button_help_rect.collidepoint(local_pos):
                                    #     cmd = ""
                                    #     if PAUSEWND.mode == "pause":
                                    #         PAUSEWND.mode = "help"
                                    #     elif PAUSEWND.mode == "help":
                                    #         PAUSEWND.mode = "pause"
                                    #     PAUSEWND.draw(screen)
                                    #     pygame.display.update()

                if mouse_down:
                    if event.type == pygame.MOUSEMOTION and last_mouse_pos:
                        dy = - (event.pos[1] - last_mouse_pos[1])
                        dx = - (event.pos[0] - last_mouse_pos[0])
                        if CODEWND.scrollY + dy > 0:
                            CODEWND.scrollY += dy
                        else:
                            CODEWND.scrollY = 0
                        if CODEWND.scrollX + dx > 0:
                            CODEWND.scrollX += dx
                        else:
                            CODEWND.scrollX = 0
                        last_mouse_pos = event.pos
                    elif last_mouse_pos is None:
                        cmd = BTNWND.is_clicked(pygame.mouse.get_pos())
                # endregion
                
                # region keydown event
                ## open map
                if event.type == KEYDOWN and event.key == K_i:
                    PLAYER.set_game_mode("item")

                if event.type == KEYDOWN and event.key == K_b:
                    ITEMWND.is_visible = not ITEMWND.is_visible

                if event.type == KEYDOWN and event.key == K_m:
                    if MMAPWND.is_visible:
                        MMAPWND.hide()
                        CODEWND.show()
                    elif CODEWND.is_visible:
                        CODEWND.hide()
                    else:
                        MMAPWND.show()

                if event.type == KEYDOWN and event.key == K_c:
                    if MSGWND.is_visible:
                        break
                    atxt = CMNDWND.draw(screen, font)

                    #atxt=txtbox.tbox(screen,font,0,SCR_HEIGHT,SCR_WIDTH,TXTBOX_HEIGHT,20)
                    cmd = ""
                    if atxt is None:
                        break
                    parts = atxt.split(' ', 1)
                    cmd = parts[0]
                    atxt = parts[1] if len(parts) > 1 else ''

                    if cmd == "":
                        continue
                    elif cmd == "undo":
                        if len(PLAYER.move5History) < 1:
                            MSGWND.set("No history...")
                        else:
                            move = PLAYER.move5History.pop()
                            if move["return"]:
                                PLAYER.moveHistory.append({'mapname': mapname, 'x': PLAYER.x, 'y': PLAYER.y})
                            # 暗転
                            DIMWND.setdf(200)
                            DIMWND.show()
                            fieldmap.create(move['mapname'])  # 移動先のマップで再構成
                            PLAYER.set_pos(move['x'], move['y'], DOWN)  # プレイヤーを移動先座標へ
                            PLAYER.commonItembag.items[-1] = move['cItems']
                            PLAYER.itembag.items[-1] = move['items']
                            fieldmap.add_chara(PLAYER)  # マップに再登録
                        cmd = "\0"
                        atxt = "\0"
                        PLAYER.fp.write("undo, " + mapname + "," + str(PLAYER.x)+", " + str(PLAYER.y) + "\n")
                    elif cmd == "break":
                        try:
                            move = PLAYER.moveHistory.pop()
                            # 暗転
                            DIMWND.setdf(200)
                            DIMWND.show()
                            fieldmap.create(move['mapname'])  # 移動先のマップで再構成
                            PLAYER.set_pos(move['x'], move['y'], DOWN)  # プレイヤーを移動先座標へ
                            fieldmap.add_chara(PLAYER)  # マップに再登録
                        except IndexError:
                            MSGWND.set("No history.")
                        cmd = "\0"
                        atxt = "\0"
                        PLAYER.fp.write( "break, " + mapname + "," + str(PLAYER.x)+", " + str(PLAYER.y) + "\n")
                    elif cmd == "restart":
                        # ゲームを最初から始める
                        dest_x = int(config.get("game", "player_x"))
                        dest_y = int(config.get("game", "player_y"))
                        dest_map =  str(config.get("game", "map"))
                        # 暗転
                        DIMWND.setdf(200)
                        DIMWND.show()
                        fieldmap.create(dest_map)
                        PLAYER.set_pos(dest_x, dest_y, DOWN)  # プレイヤーを移動先座標へ
                        fieldmap.add_chara(PLAYER)  # マップに再登録
                        cmd = "\0"
                        atxt = "\0"
                        PLAYER.fp.write("restart, " + mapname + "," + str(PLAYER.x)+", " + str(PLAYER.y) + "\n")
                    elif cmd == "echo":
                        MSGWND.set(atxt)
                        atxt = "\0"
                        cmd = "\0"
                    # elif cmd == "itemget":
                    #     try:
                    #         itemname = atxt.strip()
                    #         if not itemname:
                    #             raise ValueError("No item name provided.")
                    #         item = PLAYER.commonItembag.find(itemname)
                    #         if item is None:
                    #             item = PLAYER.itembag.find(itemname)
                    #         if item:
                    #             if(item.get_value() != None):
                    #                 MSGWND.set(f"アイテム {itemname} の値は {str(item.get_value())} です")
                    #         else:
                    #             MSGWND.set(f"アイテム {itemname} は持っていません!!")
                    #     except Exception:
                    #         MSGWND.set("ERROR...")
                    #     cmd = "\0"
                    #     atxt = "\0"
                    # elif cmd == "itemset":
                    #     ## suit for integer item
                    #     ## "itemset <var> num" ,"itemset <var> +<num>" or "item <var> ++"
                    #     try:
                    #         parts = atxt.split(' ', 1)
                    #         itemname = parts[0]
                    #         value = parts[1]
                    #         item = PLAYER.commonItembag.find(itemname)
                    #         if item is None:
                    #             item = PLAYER.itembag.find(itemname)
                    #         if item:
                    #             current_value = item.get_value()
                    #             if value == "++":
                    #                 value = str(int(current_value) + 1)
                    #             elif value == "--":
                    #                 value = str(int(current_value) - 1)
                    #             # この下の計算式コマンドは j = -5 と被るので今は無視
                    #             # elif value.startswith("+"):
                    #             #     value = str(int(current_value) + int(value[1:]))
                    #             # elif value.startswith("-"):
                    #             #     value = str(int(current_value) - int(value[1:]))

                    #             sender.send_event({"itemset": [itemname, value]})
                    #             itemsetResult = sender.receive_json()
                    #             if itemsetResult is not None:
                    #                 PLAYER.remove_itemvalue()
                    #                 if itemsetResult['status'] == "ok":
                    #                     item.set_value(value)
                    #                 MSGWND.set(itemsetResult['message'])
                    #         else:
                    #             MSGWND.set(f"アイテム {itemname} は持っていません!!")
                    #     except (IndexError, ValueError):
                    #         MSGWND.set("ERROR...")
                    #     cmd = "\0"
                    #     atxt = "\0"
                    elif cmd == "itemsetall":
                        sender.send_event({"itemsetall": True})
                        itemsetAllResult = sender.receive_json()
                        MSGWND.set(itemsetAllResult['message'])
                    elif cmd == "goto":
                        ## 任意の座標まで飛ばしてくれる 同じマップ内だけ
                        parts = atxt.split(",", 1)
                        dest_x = int(parts[0])
                        dest_y = int(parts[1])
                        # 暗転
                        DIMWND.setdf(200)
                        DIMWND.show()
                        PLAYER.set_pos(dest_x, dest_y, DOWN)  # プレイヤーを移動先座標へ
                        fieldmap.add_chara(PLAYER)  # マップに再登録
                        cmd = "\0"
                        atxt = "\0"
                        PLAYER.fp.write( "goto, " + mapname + "," + str(PLAYER.x)+", " + str(PLAYER.y) + "\n")
                    elif cmd == "stdin":
                        try:
                            parts = atxt.split(' ', 1)
                            value = " ".join(parts)
                            sender.send_event({"stdin": f"{value}\n"})
                            stdinResult = sender.receive_json()
                            if stdinResult["status"] == "ok":
                                # 今回更新した変数以外の計算コメントは全て消去する
                                PLAYER.remove_itemvalue()
                                for name, item_info in stdinResult["items"].items():
                                    for line, value in item_info.items():
                                        item = PLAYER.commonItembag.find(name, int(line))
                                        if item is None:
                                            item = PLAYER.itembag.find(name, int(line))
                                        if item is not None:
                                            item.update_value(value)
                            MSGWND.set(stdinResult['message'])
                        except (IndexError, ValueError):
                            MSGWND.set("ERROR...")
                        cmd = "\0"
                        atxt = "\0"
                    elif cmd == "jump":
                        # 関数の入り口まで飛ばしてくれる　同じマップ内だけ 
                        # 部屋と関数名の関連付けを取得できるようになったらこのコマンドを有効にする
                        # jumpするなら、デバッグモードに移行するなどを考える
                        MSGWND.set("not valid yet...")
                        # MSGWND.set("Function \'"+atxt+"\' is not found...")
                        cmd = "\0"
                        atxt = "\0"
                    elif cmd == "aquatan":
                        MSGWND.set("Make aquatan\nGrate Again!!!")
                        atxt = "\0"
                        cmd = "\0"
                    elif cmd == "down" or cmd == "left" or cmd == "right" or cmd == "up":
                        if atxt != "":
                            cmd = "\0"
                        continue
                    else:
                        MSGWND.set("Undefined command")
                        atxt = "\0"
                        cmd = "\0"

                if event.type == KEYDOWN and event.key == K_p:
                    PAUSEWND.show()
                    PAUSEWND.draw(screen)
                    pygame.display.update()
                    while PAUSEWND.is_visible:
                        for event in pygame.event.get():
                            if event.type == QUIT:
                                server.terminate()
                                print('ゲームを終了しました')
                                sys.exit()
                            if event.type == KEYDOWN and event.key == K_ESCAPE:
                                server.terminate()
                                print('ゲームを終了しました')
                                sys.exit()

                            if event.type == pygame.MOUSEBUTTONDOWN:
                                if event.button == 1 and PAUSEWND.is_visible:
                                    local_pos = (event.pos[0] - PAUSEWND.x, event.pos[1] - PAUSEWND.y)
                                    if PAUSEWND.button_toGame_rect.collidepoint(local_pos):
                                        cmd = ""
                                        PAUSEWND.hide()
                                    elif PAUSEWND.button_toStageSelect_rect.collidepoint(local_pos):
                                        cmd = ""    
                                        PAUSEWND.hide()
                                        PLAYER.goaled = True
                                    # elif PAUSEWND.button_help_rect.collidepoint(local_pos):
                                    #     cmd = ""
                                    #     if PAUSEWND.mode == "pause":
                                    #         PAUSEWND.mode = "help"
                                    #     elif PAUSEWND.mode == "help":
                                    #         PAUSEWND.mode = "pause"
                                    #     PAUSEWND.draw(screen)
                                    #     pygame.display.update()      

                if event.type == KEYDOWN and event.key in [K_LEFT, K_RIGHT]:
                    if MSGWND.selectMsgText is not None:
                        MSGWND.selectMsg(-1 if event.key == K_LEFT else 1)

                if event.type == KEYDOWN and event.key == K_f:
                    # 足元にあるのが宝箱かワープゾーンかを調べる
                    if not MSGWND.is_visible and PLAYER.search(fieldmap):
                        continue

                if (event.type == KEYDOWN and (event.key == K_SPACE or event.key == K_RETURN or event.key == K_z)) or cmd == "action":
                    cmd = ""
                    if MSGWND.is_visible:
                        # メッセージウィンドウ表示中なら次ページへ
                        MSGWND.next(fieldmap, force_next=True)
                    else:
                        # ドアを開ける
                        if PLAYER.unlock(fieldmap):
                            continue

                        # 表示中でないなら話す
                        PLAYER.talk(fieldmap, CODEWND.linenum)

                # endregion
            MSGWND.next(fieldmap)
            pygame.display.flip()

        server.terminate()

#                                                                                                                                                                                         
#                                                                                       88                                                                                                
#                          ,d                                                           ""                                                                                         ,d     
#                          88                                                                                                                                                      88     
#  ,adPPYb,d8  ,adPPYba, MM88MMM           ,adPPYba, 88       88 8b,dPPYba,  8b,dPPYba, 88 888888888  ,adPPYba,           ,adPPYba, 88       88 8b,dPPYba,  ,adPPYba,  ,adPPYba, MM88MMM  
# a8"    `Y88 a8P_____88   88              I8[    "" 88       88 88P'   `"8a 88P'   "Y8 88      a8P" a8P_____88           I8[    "" 88       88 88P'   `"8a I8[    "" a8P_____88   88     
# 8b       88 8PP"""""""   88               `"Y8ba,  88       88 88       88 88         88   ,d8P'   8PP"""""""            `"Y8ba,  88       88 88       88  `"Y8ba,  8PP"""""""   88     
# "8a,   ,d88 "8b,   ,aa   88,             aa    ]8I "8a,   ,a88 88       88 88         88 ,d8"      "8b,   ,aa           aa    ]8I "8a,   ,a88 88       88 aa    ]8I "8b,   ,aa   88,    
#  `"YbbdP"Y8  `"Ybbd8"'   "Y888           `"YbbdP"'  `"YbbdP'Y8 88       88 88         88 888888888  `"Ybbd8"'           `"YbbdP"'  `"YbbdP'Y8 88       88 `"YbbdP"'  `"Ybbd8"'   "Y888  
#  aa,    ,88                                                                                                                                                                             
#   "Y8bbdP"                    888888888888                                                                   888888888888                                                               
# 

def get_sunrise_sunset(dt):
    """日の出日の入り"""
    # 京都市の緯度経度
    kyoto = ephem.Observer()
    kyoto.lat = '35.021'
    kyoto.lon = '135.756'

    kyoto.date = dt
    sun = ephem.Sun()
    # 日の出時刻を表示
    #print(ephem.localtime(kyoto.previous_rising(sun)))
    # 日の入り時刻を表示
    #print(ephem.localtime(kyoto.next_setting(sun)))
    return (ephem.localtime(kyoto.previous_rising(sun)), ephem.localtime(kyoto.next_setting(sun)))



#                                                                                                                         
#          88                                                                                 88                          
#          88                                                                ,d               ""                          
#          88                                                                88                                           
#  ,adPPYb,88 8b,dPPYba, ,adPPYYba, 8b      db      d8           ,adPPYba, MM88MMM 8b,dPPYba, 88 8b,dPPYba,   ,adPPYb,d8  
# a8"    `Y88 88P'   "Y8 ""     `Y8 `8b    d88b    d8'           I8[    ""   88    88P'   "Y8 88 88P'   `"8a a8"    `Y88  
# 8b       88 88         ,adPPPPP88  `8b  d8'`8b  d8'             `"Y8ba,    88    88         88 88       88 8b       88  
# "8a,   ,d88 88         88,    ,88   `8bd8'  `8bd8'             aa    ]8I   88,   88         88 88       88 "8a,   ,d88  
#  `"8bbdP"Y8 88         `"8bbdP"Y8     YP      YP               `"YbbdP"'   "Y888 88         88 88       88  `"YbbdP"Y8  
#                                                                                                             aa,    ,88  
#                                                     888888888888                                             "Y8bbdP"   
# 

def draw_string(screen, x, y, string, color):
    """画面上に文字列を表示"""
    font_height = 16
    surf, rect = pygame.freetype.Font(FONT_DIR + FONT_NAME, 18).render(string, color)
    screen.blit(surf, (x, y+(font_height-4)-rect[3]))



#                                                                                                                                                          
# 88                                 88                      88                                                      88          88                        
# 88                                 88                      88                                                      88          ""                        
# 88                                 88                      88                                                      88                                    
# 88  ,adPPYba,  ,adPPYYba,  ,adPPYb,88            ,adPPYba, 88,dPPYba,  ,adPPYYba, 8b,dPPYba, ,adPPYYba,  ,adPPYba, 88,dPPYba,  88 8b,dPPYba,  ,adPPYba,  
# 88 a8"     "8a ""     `Y8 a8"    `Y88           a8"     "" 88P'    "8a ""     `Y8 88P'   "Y8 ""     `Y8 a8"     "" 88P'    "8a 88 88P'    "8a I8[    ""  
# 88 8b       d8 ,adPPPPP88 8b       88           8b         88       88 ,adPPPPP88 88         ,adPPPPP88 8b         88       88 88 88       d8  `"Y8ba,   
# 88 "8a,   ,a8" 88,    ,88 "8a,   ,d88           "8a,   ,aa 88       88 88,    ,88 88         88,    ,88 "8a,   ,aa 88       88 88 88b,   ,a8" aa    ]8I  
# 88  `"YbbdP"'  `"8bbdP"Y8  `"8bbdP"Y8            `"Ybbd8"' 88       88 `"8bbdP"Y8 88         `"8bbdP"Y8  `"Ybbd8"' 88       88 88 88`YbbdP"'  `"YbbdP"'  
#                                                                                                                                   88                     
#                                      888888888888                                                                                 88                     
# 

def load_charachips(dir, file):
    """キャラクターチップをロードしてCharacter.imagesに格納"""
    file = os.path.join(dir, file)
    with open(file, "r", encoding="utf-8") as fp:
        for line in fp:
            line = line.rstrip()
            if line.startswith("#"):
                continue  # コメント行は無視
            data = line.split(",")
            #chara_id = int(data[0])
            chara_name = str(data[1])
            Character.images[chara_name] = split_image(
                load_image("charachip", f"{chara_name}.png", TRANS_COLOR))

#                                                                                                                                            
# 88                                 88                                                                88          88                        
# 88                                 88                                                                88          ""                        
# 88                                 88                                                                88                                    
# 88  ,adPPYba,  ,adPPYYba,  ,adPPYb,88           88,dPYba,,adPYba,  ,adPPYYba, 8b,dPPYba,   ,adPPYba, 88,dPPYba,  88 8b,dPPYba,  ,adPPYba,  
# 88 a8"     "8a ""     `Y8 a8"    `Y88           88P'   "88"    "8a ""     `Y8 88P'    "8a a8"     "" 88P'    "8a 88 88P'    "8a I8[    ""  
# 88 8b       d8 ,adPPPPP88 8b       88           88      88      88 ,adPPPPP88 88       d8 8b         88       88 88 88       d8  `"Y8ba,   
# 88 "8a,   ,a8" 88,    ,88 "8a,   ,d88           88      88      88 88,    ,88 88b,   ,a8" "8a,   ,aa 88       88 88 88b,   ,a8" aa    ]8I  
# 88  `"YbbdP"'  `"8bbdP"Y8  `"8bbdP"Y8           88      88      88 `"8bbdP"Y8 88`YbbdP"'   `"Ybbd8"' 88       88 88 88`YbbdP"'  `"YbbdP"'  
#                                                                               88                                    88                     
#                                      888888888888                             88                                    88                     
# 

def load_mapchips(dir, file):
    """マップチップをロードしてMap.imagesに格納"""
    file = os.path.join(dir, file)
    with open(file, "r", encoding="utf-8") as fp:
        for line in fp:
            line = line.rstrip()
            if line.startswith("#"):
                continue  # コメント行は無視
            data = line.split(",")
            #mapchip_id = int(data[0])
            mapchip_name = data[1]
            movable = int(data[2])  # 移動可能か？
            transparent = int(data[3])  # 背景を透明にするか？
            # 画像のidで若い順に画像を登録しているので画像のidは配列の添字と一致する
            if transparent == 0:
                Map.images.append(load_image("mapchip", f"{mapchip_name}.png", -1))
            else:
                Map.images.append(load_image("mapchip", f"{mapchip_name}.png", TRANS_COLOR))
            Map.movable_type.append(movable)

                                                                                         
# 88                                        ,ad8888ba,  88          88                        
# 88   ,d                                  d8"'    `"8b 88          ""                        
# 88   88                                 d8'           88                                    
# 88 MM88MMM ,adPPYba, 88,dPYba,,adPYba,  88            88,dPPYba,  88 8b,dPPYba,  ,adPPYba,  
# 88   88   a8P_____88 88P'   "88"    "8a 88            88P'    "8a 88 88P'    "8a I8[    ""  
# 88   88   8PP""""""" 88      88      88 Y8,           88       88 88 88       d8  `"Y8ba,   
# 88   88,  "8b,   ,aa 88      88      88  Y8a.    .a8P 88       88 88 88b,   ,a8" aa    ]8I  
# 88   "Y888 `"Ybbd8"' 88      88      88   `"Y8888Y"'  88       88 88 88`YbbdP"'  `"YbbdP"'  
#                                                                      88                     
#                                                                      88                     

class ItemChips():
    def __init__(self):
        def load_itemChip(name):
            return load_image('itemchip', name)
        
        self.typeModifierUIMap = {
            'int' : {
                frozenset() : load_itemChip('jewel2l-5.png'),
                frozenset(['long']) : load_itemChip('jewel2l-3.png'),
                frozenset(['long', 'long']) : load_itemChip('jewel2l-4.png'),
                frozenset(['short']) : load_itemChip('jewel2l-2.png'),
                frozenset(['unsigned']) : load_itemChip('jewel2b-5.png'),
                frozenset(['unsigned', 'long']) : load_itemChip('jewel2b-3.png'),
                frozenset(['unsigned', 'long', 'long']) : load_itemChip('jewel2b-4.png'),
                frozenset(['unsigned', 'short']) : load_itemChip('jewel2b-2.png'),
            },
            'char' : {
                frozenset() : pygame.transform.smoothscale(load_image('mapchip', 'foods-25.png'), (32,32)),
            },
            'float' : {
                frozenset() : load_image('mapchip', 'foods-35.png'),
            },
            'double' : {
                frozenset() : pygame.transform.smoothscale(load_image('mapchip', 'foods-33.png'), (24,24)),
                frozenset(['long']) : load_image('mapchip', 'foods-33.png'),
            },
            'other' : {
                frozenset() : load_itemChip('jewel2t-5.png'),
            }
        }
        self.constUIMap = {
            True : pygame.transform.smoothscale(load_itemChip('shield.png'), (12,12)),
            False: None
        }

    def getChip(self, type_name: str):
        tokens = type_name.strip().split()

        is_const = 'const' in tokens
        tokens = [t for t in tokens if t != 'const']

        base_types = ['int', 'char', 'float', 'double', '_Bool', 'bool']

        base_type = None
        for t in tokens:
            if t in base_types:
                base_type = t
                break
        
        if base_type is not None:
            tokens.remove(base_type)
        else:
            base_type = 'int'
        
        modifier_set = frozenset(tokens)

        base_icon = self.typeModifierUIMap.get(base_type, self.typeModifierUIMap['other']).get(modifier_set, self.typeModifierUIMap['other'][frozenset()])
        const_overlay = self.constUIMap[is_const]

        return base_icon, const_overlay

#                                                                                                        
#                       88                                    ad88    ad88                               
#                       88                                   d8"     d8"                          ,d     
#                       88                                   88      88                           88     
#  ,adPPYba, ,adPPYYba, 88  ,adPPYba,            ,adPPYba, MM88MMM MM88MMM ,adPPYba,  ,adPPYba, MM88MMM  
# a8"     "" ""     `Y8 88 a8"     ""           a8"     "8a  88      88    I8[    "" a8P_____88   88     
# 8b         ,adPPPPP88 88 8b                   8b       d8  88      88     `"Y8ba,  8PP"""""""   88     
# "8a,   ,aa 88,    ,88 88 "8a,   ,aa           "8a,   ,a8"  88      88    aa    ]8I "8b,   ,aa   88,    
#  `"Ybbd8"' `"8bbdP"Y8 88  `"Ybbd8"'            `"YbbdP"'   88      88    `"YbbdP"'  `"Ybbd8"'   "Y888  
#                                                                                                        
#                                    888888888888                                                        
# 

def calc_offset(p):
    """オフセット(全体マップ中の相対マップ位置)を計算する"""
    offsetx = p.rect.topleft[0] - SCR_RECT.width//2
    offsety = p.rect.topleft[1] - SCR_RECT.height//2
    return offsetx, offsety

#                                                                                                          
# 88                                 88           88                                                       
# 88                                 88           ""                                                       
# 88                                 88                                                                    
# 88  ,adPPYba,  ,adPPYYba,  ,adPPYb,88           88 88,dPYba,,adPYba,  ,adPPYYba,  ,adPPYb,d8  ,adPPYba,  
# 88 a8"     "8a ""     `Y8 a8"    `Y88           88 88P'   "88"    "8a ""     `Y8 a8"    `Y88 a8P_____88  
# 88 8b       d8 ,adPPPPP88 8b       88           88 88      88      88 ,adPPPPP88 8b       88 8PP"""""""  
# 88 "8a,   ,a8" 88,    ,88 "8a,   ,d88           88 88      88      88 88,    ,88 "8a,   ,d88 "8b,   ,aa  
# 88  `"YbbdP"'  `"8bbdP"Y8  `"8bbdP"Y8           88 88      88      88 `"8bbdP"Y8  `"YbbdP"Y8  `"Ybbd8"'  
#                                                                                   aa,    ,88             
#                                      888888888888                                  "Y8bbdP"              
# 

def load_image(imgdir, file, colorkey=None):
    """画像をロードする"""
    file = os.path.join(imgdir, file)
    try:
        image = pygame.image.load(file)
    except pygame.error as message:
        print("Cannot load image:", file)
        raise SystemExit(message)
    if colorkey is not None:
        if colorkey == -1:
            image = image.convert_alpha()
        else:
            image = image.convert()
            image.set_colorkey(colorkey, RLEACCEL)
    else:
        image = image.convert_alpha()

    return image

#                                                                                                        
#                       88 88                   88                                                       
#                       88 ""   ,d              ""                                                       
#                       88      88                                                                       
# ,adPPYba, 8b,dPPYba,  88 88 MM88MMM           88 88,dPYba,,adPYba,  ,adPPYYba,  ,adPPYb,d8  ,adPPYba,  
# I8[    "" 88P'    "8a 88 88   88              88 88P'   "88"    "8a ""     `Y8 a8"    `Y88 a8P_____88  
#  `"Y8ba,  88       d8 88 88   88              88 88      88      88 ,adPPPPP88 8b       88 8PP"""""""  
# aa    ]8I 88b,   ,a8" 88 88   88,             88 88      88      88 88,    ,88 "8a,   ,d88 "8b,   ,aa  
# `"YbbdP"' 88`YbbdP"'  88 88   "Y888           88 88      88      88 `"8bbdP"Y8  `"YbbdP"Y8  `"Ybbd8"'  
#           88                                                                    aa,    ,88             
#           88                       888888888888                                  "Y8bbdP"              
# 

def split_image(image):
    """128x128のキャラクターイメージを32x32の16枚のイメージに分割
    分割したイメージを格納したリストを返す"""
    image_list = []
    for i in range(0, 128, GS):
        for j in range(0, 128, GS):
            surface = pygame.Surface((GS, GS))
            surface.blit(image, (0, 0), (j, i, GS, GS))
            surface.convert()
            surface.set_colorkey(surface.get_at((0, 0)), RLEACCEL)
            image_list.append(surface)
    return image_list


#                                                                                                                  
# 88888888ba,                                 88                                         88                        
# 88      `"8b               ,d               88                                         88                        
# 88        `8b              88               88                                         88                        
# 88         88 ,adPPYYba, MM88MMM ,adPPYYba, 88          ,adPPYba,  ,adPPYYba,  ,adPPYb,88  ,adPPYba, 8b,dPPYba,  
# 88         88 ""     `Y8   88    ""     `Y8 88         a8"     "8a ""     `Y8 a8"    `Y88 a8P_____88 88P'   "Y8  
# 88         8P ,adPPPPP88   88    ,adPPPPP88 88         8b       d8 ,adPPPPP88 8b       88 8PP""""""" 88          
# 88      .a8P  88,    ,88   88,   88,    ,88 88         "8a,   ,a8" 88,    ,88 "8a,   ,d88 "8b,   ,aa 88          
# 88888888Y"'   `"8bbdP"Y8   "Y888 `"8bbdP"Y8 88888888888 `"YbbdP"'  `"8bbdP"Y8  `"8bbdP"Y8  `"Ybbd8"' 88          
#                                                                                                                  
#                                                                                                                  
# 

class DataLoader(Thread):
    """別スレッドでデータを取得し続けるためのクラス"""
    def __init__(self, data, t):
        super(DataLoader, self).__init__()
        self.interval = t
        self.data = data

    def run(self):
        """無限ループで実行"""
        while True:
            time.sleep(self.interval)
            self.data.get_data()

#                                           
# 88b           d88                         
# 888b         d888                         
# 88`8b       d8'88                         
# 88 `8b     d8' 88 ,adPPYYba, 8b,dPPYba,   
# 88  `8b   d8'  88 ""     `Y8 88P'    "8a  
# 88   `8b d8'   88 ,adPPPPP88 88       d8  
# 88    `888'    88 88,    ,88 88b,   ,a8"  
# 88     `8'     88 `"8bbdP"Y8 88`YbbdP"'   
#                              88           
#                              88           
# 

class Map:
    """マップオブジェクト"""
    # main()のload_mapchips()でセットされる
    images = []  # マップチップ（ID->イメージ）
    movable_type = []  # マップチップが移動可能か？（0:移動不可, 1:移動可）

    def __init__(self, name):
        self.name: str = name
        self.row = -1  # 行数
        self.col = -1  # 列数
        self.map = []  # マップデータ（2次元リスト）
        self.charas: list[Character] = []  # マップにいるキャラクターリスト
        self.events = []  # マップにあるイベントリスト
        self.lights = []  # マップにある光源リスト
        self.load_json()

    def create(self, dest_map):
        """dest_mapでマップを初期化"""
        self.name = dest_map
        self.charas = []
        self.events = []
        self.lights = []
        self.load_json()

    def add_chara(self, chara):
        """キャラクターをマップに追加する"""
        self.charas.append(chara)

    def update(self):
        """マップの更新"""
        # マップにいるキャラクターの更新
        for chara in self.charas:
            chara.update(self)  # mapを渡す

    def draw(self, screen: pygame.Surface, offset):
        """マップを描画する"""
        offsetx, offsety = offset
        # マップの描画範囲を計算
        startx = offsetx // GS
        endx = startx + SCR_RECT.width//GS + 1
        starty = offsety // GS
        endy = starty + SCR_RECT.height//GS + 1
        # マップの描画
        for y in range(starty, endy):
            for x in range(startx, endx):
                # マップの範囲外はデフォルトイメージで描画
                # この条件がないとマップの端に行くとエラー発生
                if x < 0 or y < 0 or x > self.col-1 or y > self.row-1:
                    screen.blit(self.images[self.default],
                                (x*GS-offsetx, y*GS-offsety))
                else:
                    screen.blit(self.images[self.map[y][x]],
                                (x*GS-offsetx, y*GS-offsety))
        if len(PLAYER.funcInfoWindow_list):
            if PLAYER.funcInfoWindowIndex >= len(PLAYER.funcInfoWindow_list):
                PLAYER.funcInfoWindowIndex = len(PLAYER.funcInfoWindow_list) - 1
            else:
                PLAYER.funcInfoWindow_list[PLAYER.funcInfoWindowIndex].draw(screen)

        # このマップにあるイベントを描画
        for event in self.events:
            event.draw(screen, offset)
        # このマップにいるキャラクターを描画
        for chara in self.charas:
            chara.draw(screen, offset)

    def is_movable(self, x, y):
        """(x,y)は移動可能か？"""
        # マップ範囲内か？
        if x < 0 or x > self.col-1 or y < 0 or y > self.row-1:
            return False
        # マップチップは移動可能か？
        if self.movable_type[self.map[y][x]] == 0:
            return False
        # キャラクターと衝突しないか？
        for chara in self.charas:
            if chara.x == x and chara.y == y:
                return False
        # イベントと衝突しないか？
        for event in self.events:
            if self.movable_type[event.mapchip] == 0:
                if event.x == x and event.y == y:
                    if isinstance(event, SmallDoor) and event.status == 1:
                        return True
                    return False
        return True

    def is_movable_but_chara(self, x, y):
        """(x,y)は移動可能か？"""
        # マップ範囲内か？
        if x < 0 or x > self.col-1 or y < 0 or y > self.row-1:
            return False
        # マップチップは移動可能か？
        if self.movable_type[self.map[y][x]] == 0:
            return False
        # イベントと衝突しないか？
        for event in self.events:
#            print(event.mapchip)
            if self.movable_type[event.mapchip] == 0:
                if event.x == x and event.y == y:
                    return False
        return True

    def get_chara(self, x, y):
        """(x,y)にいるキャラクターを返す。いなければNone"""
        for chara in self.charas:
            if chara.x == x and chara.y == y:
                return chara
        return None

    def get_event(self, x, y):
        """(x,y)にあるイベントを返す。なければNone"""
        for event in self.events:
            if event.x == x and event.y == y:
                return event
        return None

    def remove_event(self, event):
        """eventを削除する"""
        self.events.remove(event)

    def load_json(self):
        """json形式のマップ・イベントを読み込む"""
        # ここのファイル名は後々変える -----------------------------------------------------------
        file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mapdata", self.name.lower(), self.name.lower() + ".json")
        with codecs.open(file, "r", "utf-8") as fp:
            json_data = json.load(fp)
        self.row = json_data["row"]
        self.col = json_data["col"]
        self.default = json_data["default"]
        self.map = json_data["map"]
        self.events = []
        self.charas = []
        for chara in json_data["characters"]:
            chara_type = chara["type"]
            if chara_type == "CHARA":  # キャラクター
                self.create_chara_j(chara)
            elif chara_type == "CHARAEXPRESSION": # 計算式のチェックを行うキャラクター
                self.create_charaexpression_j(chara)
            elif chara_type == "CHARARETURN": #キャラクター+遷移元に戻る
                self.create_charareturn_j(chara)
            elif chara_type == "CHARACHECKCONDITION":
                self.create_characheckcondition_j(chara)
            elif chara_type == "NPC":  # NPC
                self.create_npc_j(chara)
            elif chara_type == "NPCPATH":  # NPCPATH
                self.create_npcpath_j(chara)
        for event in json_data["events"]:
            event_type = event["type"]
            if event_type == "OBJECT":  # 一般オブジェクト
                self.create_obj_j(event)
            elif event_type == "SIGN":  # 任意の文字を書く看板
                self.create_sign_j(event)
            elif event_type == "TREASURE":  # 宝箱
                # 一度取得したアイテムの宝箱は現れないようにする
                item = PLAYER.commonItembag.find(event["item"], event["fromTo"][0])
                if item is not None:
                    continue
                item = PLAYER.itembag.find(event["item"], event["fromTo"][0])
                if item is not None:
                    continue
                self.create_treasure_j(event)
            elif event_type == "DOOR":  # ドア
                self.create_door_j(event)
            elif event_type == "SDOOR":  #  小さいドア
                self.create_smalldoor_j(event)
            elif event_type == "ZLIGHT":  # 光源
                self.create_light_j(event)
            elif event_type == "MOVE":  # マップ間移動イベント
                self.create_move_j(event)
            elif event_type == "AUTO":  # 自動移動イベント
                self.create_auto_j(event)
            elif event_type == "PLPATH":  # プレイヤー移動目標
                self.create_plpath_j(event)
            elif event_type == "PLACESET":  # 場所マーカー
                self.create_placeset_j(event)

    def create_chara_j(self, data):
        """キャラクターを作成してcharasに追加する"""
        name = data["name"]
        x, y = int(data["x"]), int(data["y"])
        direction = int(data["dir"])
        movetype = int(data["movetype"])
        message = data["message"]
        chara = Character(name, (x, y), direction, movetype, message)
        #print(chara)
        self.charas.append(chara)

    def create_npc_j(self, data):
        """NPCを作成してcharasに追加する"""
        name = data["name"]
        npcname = data["npcname"]
        dest = (int(data["x"]), int(data["y"]))
        direction = int(data["dir"])
        movetype = int(data["movetype"])
        message = data["message"]
        chara = Character(name, dest, direction, movetype, message)
        chara.npcname = npcname
        self.charas.append(chara)

    def create_npcpath_j(self, data):
        """NPCの部屋での目的地を設定する"""
        npcname = data["name"]
        pathname = data["pathname"]
        dest = (int(data["x"]), int(data["y"]))

    def create_sign_j(self, data):
        """看板を作成してeventsに追加する"""
        x, y = int(data["x"]), int(data["y"])
        text = data["text"]
        self.events.append(Sign((x,y),text))

    def create_treasure_j(self, data):
        """宝箱を作成してeventsに追加する"""
        x, y = int(data["x"]), int(data["y"])
        item = data["item"]
        exps = data["exps"]
        vartype = data["vartype"]
        func = data["func"]
        fromTo = data["fromTo"]
        funcWarp = data["funcWarp"]
        treasure = Treasure((x, y), item, exps, vartype, func, fromTo, funcWarp, self.name.lower())
        self.events.append(treasure)

    def create_light_j(self, data):
        """光源を作成してeventsに追加する"""
        x, y = int(data["x"]), int(data["y"])
        room = data["roomname"]
        light = Light((x, y), room)
        self.lights.append(light)

    def create_door_j(self, data):
        """ドアを作成してeventsに追加する"""
        x, y = int(data["x"]), int(data["y"])
        name = data["doorname"]
        door = Door((x, y), name)
        door.close()
        self.events.append(door)

    def create_smalldoor_j(self, data):
        """ドアを作成してeventsに追加する"""
        x, y = int(data["x"]), int(data["y"])
        name = data["doorname"]
        direction = data["dir"]
        door = SmallDoor((x, y), name, direction)
        door.close()
        self.events.append(door)

    def create_obj_j(self, data):
        """一般オブジェクトを作成してeventsに追加する"""
        x, y = int(data["x"]), int(data["y"])
        mapchip = int(data["mapchip"])
        obj = Object((x, y), mapchip)
        self.events.append(obj)

    def create_charareturn_j(self, data):
        """キャラクター(遷移元に戻る)を作成してcharasに追加する"""
        name = data["name"]
        x, y = int(data["x"]), int(data["y"])
        direction = int(data["dir"])
        movetype = int(data["movetype"])
        message = data["message"]
        fromTo = data["fromTo"]
        func = data["func"]
        funcWarp = data["funcWarp"]
        exps = data["exps"]
        chara = CharaReturn(name, (x, y), direction, movetype, message, fromTo, func, funcWarp, exps, self.name.lower())
        #print(chara)
        self.charas.append(chara)

    def create_characheckcondition_j(self, data):
        avoiding = True if PLAYER.ccchara and PLAYER.ccchara["x"] == x and PLAYER.ccchara["y"] == y else False
        name = data["name"]
        x = PLAYER.ccchara["avoiding_x"] if avoiding else int(data["x"]) 
        y = PLAYER.ccchara["avoiding_y"] if avoiding else int(data["y"]) 
        direction = PLAYER.ccchara["avoiding_dir"] if avoiding else int(data["dir"])
        move_direction = int(data["moveDir"])
        movetype = int(data["movetype"])
        message = data["message"]
        type = data["condType"]
        fromTo = data["fromTo"]
        func = data["func"]
        funcWarp = data["funcWarp"]
        funcExps = data["funcExps"]
        detail = data["detail"]
        chara = CharaCheckCondition(name, (x, y), direction, move_direction, movetype, message, type, fromTo, func, funcWarp, funcExps, detail, avoiding, self.name.lower())
        #print(chara)
        self.charas.append(chara)

    def create_charaexpression_j(self, data):
        """計算式を確認するキャラクターを追加する"""
        name = data["name"]
        x, y = int(data["x"]), int(data["y"])
        direction = int(data["dir"])
        movetype = int(data["movetype"])
        message = data["message"]
        func = data["func"]
        exps = data["exps"]
        chara = CharaExpression(name, (x, y), direction, movetype, message, func, exps, self.name.lower())
        #print(chara)
        self.charas.append(chara)

    def create_move_j(self, data):
        """移動イベントを作成してeventsに追加する"""
        x, y = int(data["x"]), int(data["y"])
        mapchip = int(data["mapchip"])
        dest_map = data["dest_map"]
        type = data.get("warpType", "")
        fromTo = data.get("fromTo", [0,0])
        dest_x, dest_y = int(data["dest_x"]), int(data["dest_y"])
        func = data["func"]
        exps = data["exps"]
        funcWarp = data["funcWarp"]
        funcExps = data["funcExps"]
        detail = data["detail"]
        # print(funcWarp)
        move = MoveEvent((x, y), mapchip, dest_map, type, fromTo, (dest_x, dest_y), func, exps, funcWarp, funcExps, detail, self.name.lower())
        self.events.append(move)

    def create_plpath_j(self, data):
        """プレイヤーの目的地を設定する"""
        pathname = data["pathname"]
        dest = (int(data["x"]),int(data["y"]))
        PLAYER.dest[str(pathname)] = dest

    def create_placeset_j(self, data):
        """移動イベントを作成してeventsに追加する"""
        x, y = int(data["x"]), int(data["y"])
        mapchip = int(data["mapchip"])
        place_label = data["place_label"]
        place = PlacesetEvent((x, y), mapchip, place_label)
        self.events.append(place)

    def create_auto_j(self, data):
        """自動イベントを作成してeventsに追加する"""
        x, y = int(data["x"]), int(data["y"])
        mapchip = int(data["mapchip"])
        sequence = list(data["sequence"])
        # print(funcWarp)
        auto = AutoEvent((x, y), mapchip, sequence)
        self.events.append(auto)

#                                                                                                     
#   ,ad8888ba,  88                                                                                    
#  d8"'    `"8b 88                                                        ,d                          
# d8'           88                                                        88                          
# 88            88,dPPYba,  ,adPPYYba, 8b,dPPYba, ,adPPYYba,  ,adPPYba, MM88MMM ,adPPYba, 8b,dPPYba,  
# 88            88P'    "8a ""     `Y8 88P'   "Y8 ""     `Y8 a8"     ""   88   a8P_____88 88P'   "Y8  
# Y8,           88       88 ,adPPPPP88 88         ,adPPPPP88 8b           88   8PP""""""" 88          
#  Y8a.    .a8P 88       88 88,    ,88 88         88,    ,88 "8a,   ,aa   88,  "8b,   ,aa 88          
#   `"Y8888Y"'  88       88 `"8bbdP"Y8 88         `"8bbdP"Y8  `"Ybbd8"'   "Y888 `"Ybbd8"' 88          
#                                                                                                     
#                                                                                                     
# 

class Character:
    """一般キャラクタークラス"""
    speed = 8  # 1フレームの移動ピクセル数
    animcycle = MAX_FRAME_PER_SEC // 4  # アニメーション速度 //の後の数字を増やすと早くなる
    frame = 0
    # キャラクターイメージ（mainで初期化）
    # キャラクター名 -> 分割画像リストの辞書
    images = {}

    def __init__(self, name, pos, direction, movetype, message):
        self.name = name  # プレイヤー名（ファイル名と同じ）
        self.npcname = ""  # 頭の上の名前
        self.image = self.images[name][0]  # 描画中のイメージ
        self.x, self.y = pos[0], pos[1]  # 座標（単位：マス）
        self.rect = self.image.get_rect(topleft=(self.x*GS, self.y*GS))
        self.vx, self.vy = 0, 0  # 移動速度
        self.moving = False  # 移動中か？
        self.direction = direction  # 向き
        self.movetype = movetype  # 移動タイプ
        self.message = message  # メッセージ
        self.moveto = []
        self.hp = ""  # 在室時間
        self.hp_color = (211, 211, 255, 255)
        self.lim_lu = (self.x - 2, self.y - 2)
        self.lim_rd = (self.x + 2, self.y + 2)

    def pos(self):
        """座標を返す"""
        return (self.x, self.y)

    def set_speed(self, s):
        """移動スピードを設定"""
        self.speed = s

    def update(self, mymap: Map):
        """キャラクター状態を更新する。
        mapは移動可能かの判定に必要。"""
        # プレイヤーの移動処理
        if self.moving:
            # ピクセル移動中ならマスにきっちり収まるまで移動を続ける
            self.rect.move_ip(self.vx, self.vy)
            if self.rect.left % GS == 0 and self.rect.top % GS == 0:  # マスにおさまったら移動完了
                self.moving = False
                self.x = self.rect.left // GS
                self.y = self.rect.top // GS
        elif len(self.moveto) > 0:
            # 移動中でなく，movetoに行き先座標がセットされているなら
            newdir = self.get_next_automove()
            if newdir is not None:
                # print "name:%s -> (%2d,%2d)" % (self.name,self.x,self.y)
                # mymap.get_event(self.x, self.y) #もし、後々CPUは宝箱の上を通れないようにするなら、ここで確認する
                self.direction = newdir
                if self.direction == DOWN:
                    if mymap.is_movable_but_chara(self.x, self.y+1):
                        self.vx, self.vy = 0, self.speed
                        self.moving = True
                elif self.direction == LEFT:
                    if mymap.is_movable_but_chara(self.x-1, self.y):
                        self.vx, self.vy = -self.speed, 0
                        self.moving = True
                elif self.direction == RIGHT:
                    if mymap.is_movable_but_chara(self.x+1, self.y):
                        self.vx, self.vy = self.speed, 0
                        self.moving = True
                elif self.direction == UP:
                    if mymap.is_movable_but_chara(self.x, self.y-1):
                        self.vx, self.vy = 0, -self.speed
                        self.moving = True
            else:
                #print(f"name:{self.name} -> [{self.x},{self.y}]")
                self.lim_lu = (self.x - 3, self.y - 3)
                self.lim_rd = (self.x + 3, self.y + 3)
                self.speed = 8
        elif self.movetype == MOVE and random.random() < PROB_MOVE:
            # 移動中でないならPROB_MOVEの確率でランダム移動開始
            self.direction = random.randint(0, 3)  # 0-3のいずれか
            if self.direction == DOWN:
                if self.y < self.lim_rd[1]:
                    if mymap.is_movable(self.x, self.y+1):
                        self.vx, self.vy = 0, self.speed
                        self.moving = True
            elif self.direction == LEFT:
                if self.x > self.lim_lu[0]:
                    if mymap.is_movable(self.x-1, self.y):
                        self.vx, self.vy = -self.speed, 0
                        self.moving = True
            elif self.direction == RIGHT:
                if self.x < self.lim_rd[0]:
                    if mymap.is_movable(self.x+1, self.y):
                        self.vx, self.vy = self.speed, 0
                        self.moving = True
            elif self.direction == UP:
                if self.y > self.lim_lu[1]:
                    if mymap.is_movable(self.x, self.y-1):
                        self.vx, self.vy = 0, -self.speed
                        self.moving = True
        # キャラクターアニメーション（frameに応じて描画イメージを切り替える）
        self.frame += 1
        self.image = self.images[self.name][self.direction *
                                            4 + (self.frame // self.animcycle  % 4)]

    def draw_light(self, screen, color, offset):
        """オフセットを考慮し光を描画"""
        offsetx, offsety = offset
        px = self.rect.topleft[0]-80
        py = self.rect.topleft[1]-80
        light_surface = pygame.Surface((160, 160), pygame.SRCALPHA)
#        screen.blit(self.image, (px-offsetx, py-offsety))
        pygame.draw.circle(light_surface,Color(color.r,color.g,color.b,color.a//6),
                           (80,80),80,0)
        pygame.draw.circle(light_surface,Color(color.r,color.g,color.b,color.a//4),
                           (80,80),70,0)
        pygame.draw.circle(light_surface,Color(color.r,color.g,color.b,color.a//2),
                           (80,80),60,0)
        pygame.draw.circle(light_surface,Color(0,0,0,color.a),(80,80),48,0)
        screen.blit(light_surface, (px-offsetx+15, py-offsety+15),
                    special_flags=BLEND_RGBA_SUB)

    def draw(self, screen, offset):
        """オフセットを考慮してプレイヤーを描画"""
        offsetx, offsety = offset
        px = self.rect.topleft[0]
        py = self.rect.topleft[1]
        font = pygame.freetype.Font(FONT_DIR + FONT_NAME, 18)
        screen.blit(self.image, (px-offsetx, py-offsety))
        screen.blit(font.render(self.npcname, Color(255, 255, 255, 255))[
                    0], (px-offsetx, py-offsety-18))
        screen.blit(font.render(str(self.hp), self.hp_color)
                    [0], (px-offsetx+32, py-offsety))

    def set_pos(self, x, y, direction):
        """キャラクターの位置と向きをセット"""
        self.x, self.y = x, y
        self.rect = self.image.get_rect(topleft=(self.x*GS, self.y*GS))
        self.direction = direction

    def append_moveto(self, seq):
        """移動先を追加"""
        self.moveto.extend(seq)

    def get_next_automove(self):
        """次の移動先を得る"""
        direction = []
        # moveto[0]が現座標だったらpop
        if len(self.moveto) > 0:
            if self.x - self.moveto[0][0] == 0 and self.y - self.moveto[0][1] == 0:
                self.moveto.pop(0)
        if len(self.moveto) > 0:
            if self.x - self.moveto[0][0] > 0:
                direction.append(LEFT)
            elif self.x - self.moveto[0][0] < 0:
                direction.append(RIGHT)
            if self.y - self.moveto[0][1] > 0:
                direction.append(UP)
            elif self.y - self.moveto[0][1] < 0:
                direction.append(DOWN)
            return random.choice(direction)
        return None

    def __str__(self):
        return f"CHARA,{self.name:s},{self.x:d},{self.y:d},"\
            f"{self.direction:d},{self.movetype:d},{self.message:s}"

#                                                              
# 88888888ba  88                                               
# 88      "8b 88                                               
# 88      ,8P 88                                               
# 88aaaaaa8P' 88 ,adPPYYba, 8b       d8  ,adPPYba, 8b,dPPYba,  
# 88""""""'   88 ""     `Y8 `8b     d8' a8P_____88 88P'   "Y8  
# 88          88 ,adPPPPP88  `8b   d8'  8PP""""""" 88          
# 88          88 88,    ,88   `8b,d8'   "8b,   ,aa 88          
# 88          88 `"8bbdP"Y8     Y88'     `"Ybbd8"' 88          
#                               d8'                            
#                              d8'                             
# 

class Player(Character):
    """プレイヤークラス"""

    def __init__(self, name, pos, direction, sender):
        Character.__init__(self, name, pos, direction, False, None)
        self.prevPos = [pos, pos]
        self.wait = 0
        self.dest = {}
        self.place_label = "away"
        self.automove = []
        self.waitingMove = None
        self.moveHistory = []
        self.move5History = []
        self.status = {"LV":1, "HP":100, "MP":20, "ATK":10, "DEF":10, "AGI":8}
        self.itembag = ItemBag()
        self.commonItembag = ItemBag()
        self.sender : EventSender = sender
        self.itemNameShow = False
        self.door: SmallDoor | None = None # スモールドアイベントがNoneでない(扉の上にいる)時に移動したら扉を閉じるようにする。
        self.ccchara: CharaCheckCondition = None
        self.checkedFuncs: dict[tuple[str, str, int], list[tuple[str, str, bool]]] = {} # ワープゾーンの位置(マップ名と座標)をキー、チェック済みの関数を値として格納する
        self.goaled = False
        self.funcInfoWindow_list: list[FuncInfoWindow] = []
        self.funcInfoWindowIndex = 0
        self.std_messages = []
        self.address_to_fname = {}
        self.address_to_size = {}
        self.func = None
        
        ## start
        self.fp = open(PATH, mode='w')
        ## end

    def update(self, mymap: Map):
        """プレイヤー状態を更新する。
        mapは移動可能かの判定に必要。"""
        self.funcInfoWindow_list = []
        # プレイヤーの移動処理
        if self.moving:
            # ピクセル移動中ならマスにきっちり収まるまで移動を続ける
            self.rect.move_ip(self.vx, self.vy)
            if self.rect.left % GS == 0 and self.rect.top % GS == 0:  # マスにおさまったら移動完了
                ##self.fp.write( str(self.x)+", " + str(self.y) + "\n")
                self.moving = False
                self.x = self.rect.left // GS
                self.y = self.rect.top // GS

                if (self.door is not None and 
                    ((self.door.direction == DOWN and (self.door.x, self.door.y-1) == (self.x, self.y)) or (self.door.direction == UP and (self.door.x, self.door.y+1) == (self.x, self.y)) or
                     (self.door.direction == LEFT and (self.door.x+1, self.door.y) == (self.x, self.y)) or (self.door.direction == RIGHT and (self.door.x-1, self.door.y) == (self.x, self.y)))):
                    door = mymap.get_event(self.door.x, self.door.y)
                    if isinstance(door, SmallDoor):
                        door.close()
                        self.door = None
        elif self.waitingMove is not None:
            dest_map = self.waitingMove.dest_map
            dest_x = self.waitingMove.dest_x
            dest_y = self.waitingMove.dest_y
            self.waitingMove = None
            # 暗転
            DIMWND.setdf(200)
            DIMWND.show()
            mymap.create(dest_map)  # 移動先のマップで再構成
            self.set_pos(dest_x, dest_y, DOWN)  # プレイヤーを移動先座標へ
            mymap.add_chara(self)  # マップに再登録
        else:
            # ここで自動移動の判定
            direction = None
            pressed_keys = None
            tempPrevPos = None

            # region command input
            global cmd
            if cmd == "down":
                direction = 'd'
                # self.append_automove('d')
                cmd = "\0"
            elif cmd == "left":
                direction = 'l'
                # self.append_automove('l')
                cmd = "\0"
            elif cmd == "right":
                direction = 'r'
                # self.append_automove('r')
                cmd = "\0"
            elif cmd == "up":
                direction = 'u'
                # self.append_automove('u')
                cmd = "\0"
            # endregion

            # コマンドまたは矢印ボタンの入力(cmd入力)がなければ、自動移動かキー移動だと考える
            if not direction in ('u', 'd', 'l', 'r'):
                # 自動移動 (cmd以上に優先される)
                if len(self.automove) > 0:
                    direction = self.get_next_automove()
                # キー入力 (cmd移動/自動移動がない時のみ許す => 同時入力は受け付けない)
                else: 
                    pressed_keys = pygame.key.get_pressed()

            # cmd入力と自動移動の許可を判断 (入力の独立性は既に確保されているので一緒に判断しても良い)
            # if direction in ('u', 'd', 'l', 'r'):
            #     if ((self.y - self.prevPos[0][1] == -1 and direction == 'd')
            #     or (self.x - self.prevPos[0][0] == 1 and direction == 'l')
            #     or (self.x - self.prevPos[0][0] == -1 and direction == 'r')
            #     or (self.y - self.prevPos[0][1] == 1 and direction == 'u')):
            #         tempPrevPos = [None, self.prevPos[0]]
            #         MSGWND.set("ここから先は進入できません!!")
            #     self.pop_automove()
            # elif direction == 'x':
            #     self.wait += 1
            #     if self.wait > 60:
            #         self.wait = 0
            #         self.pop_automove()

            if pressed_keys and (pressed_keys[K_LSHIFT] or pressed_keys[K_RSHIFT]):
                self.speed = 16
                self.status["AGI"] = 16
            else:
                self.speed = 8
                self.status["AGI"] = 8

            if direction == 'd' or (pressed_keys and pressed_keys[K_DOWN]):
                self.direction = DOWN  # 移動できるかに関係なく向きは変える
                if mymap.is_movable(self.x, self.y+1) and mymap.is_movable(self.x, self.y+2):
                    self.vx, self.vy = 0, self.speed
                    self.moving = True
                    self.prevPos = tempPrevPos if tempPrevPos else [self.prevPos[1], (self.x, self.y+(self.speed//8))]
                elif mymap.is_movable(self.x, self.y+1):
                    self.vx, self.vy = 0, 8
                    self.moving = True
                    self.prevPos = tempPrevPos if tempPrevPos else [self.prevPos[1], (self.x, self.y+1)]
            elif direction == 'l' or (pressed_keys and pressed_keys[K_LEFT]):
                self.direction = LEFT
                if mymap.is_movable(self.x-1, self.y) and mymap.is_movable(self.x-2, self.y):
                    self.vx, self.vy = -self.speed, 0
                    self.moving = True
                    self.prevPos = tempPrevPos if tempPrevPos else [self.prevPos[1], (self.x-(self.speed//8), self.y)]
                elif mymap.is_movable(self.x-1, self.y):
                    self.vx, self.vy = -8, 0
                    self.moving = True
                    self.prevPos = tempPrevPos if tempPrevPos else [self.prevPos[1], (self.x-1, self.y)]
            elif direction == 'r' or (pressed_keys and pressed_keys[K_RIGHT]):
                self.direction = RIGHT
                if mymap.is_movable(self.x+1, self.y) and mymap.is_movable(self.x+2, self.y):
                    self.vx, self.vy = self.speed, 0
                    self.moving = True
                    self.prevPos = tempPrevPos if tempPrevPos else  [self.prevPos[1], (self.x+(self.speed//8), self.y)]
                elif mymap.is_movable(self.x+1, self.y):
                    self.vx, self.vy = 8, 0
                    self.moving = True
                    self.prevPos = tempPrevPos if tempPrevPos else [self.prevPos[1], (self.x+1, self.y)]
            elif direction == 'u' or (pressed_keys and pressed_keys[K_UP]):
                self.direction = UP
                if mymap.is_movable(self.x, self.y-1) and mymap.is_movable(self.x, self.y-2):
                    self.vx, self.vy = 0, -self.speed
                    self.moving = True
                    self.prevPos = tempPrevPos if tempPrevPos else [self.prevPos[1], (self.x, self.y-(self.speed//8))]
                elif mymap.is_movable(self.x, self.y-1):
                    self.vx, self.vy = 0, -8
                    self.moving = True
                    self.prevPos = tempPrevPos if tempPrevPos else [self.prevPos[1], (self.x, self.y-1)]
            elif direction is None and MSGWND.selectMsgText is None:
                # 接触イベントチェック
                event = mymap.get_event(self.x, self.y)
                if isinstance(event, MoveEvent) or isinstance(event, Treasure):
                    self.funcInfoWindow_list.append(event.funcInfoWindow)
                nextx, nexty = self.x, self.y
                if self.direction == DOWN:
                    nexty = self.y + 1
                elif self.direction == LEFT:
                    nextx = self.x - 1
                elif self.direction == RIGHT:
                    nextx = self.x + 1
                elif self.direction == UP:
                    nexty = self.y - 1
                chara = mymap.get_chara(nextx, nexty)
                if isinstance(chara, CharaCheckCondition) or isinstance(chara, CharaReturn):
                    self.funcInfoWindow_list.append(chara.funcInfoWindow)
                elif isinstance(chara, CharaExpression) and str(self.sender.code_window.linenum) in chara.funcInfoWindow_dict:
                    self.funcInfoWindow_list.append(chara.funcInfoWindow_dict[str(self.sender.code_window.linenum)])

            if self.moving and self.ccchara is not None:
                if self.ccchara["x"] == self.x and self.ccchara["y"] == self.y:
                    chara = mymap.get_chara(self.ccchara["avoiding_x"], self.ccchara["avoiding_y"])
                    if isinstance(chara, CharaCheckCondition):
                        if chara.initial_direction != self.direction:
                            chara.back_to_init_pos()
                            self.ccchara = None
                            door = mymap.get_event(self.door.x, self.door.y)
                            if isinstance(door, SmallDoor):
                                door.close()
                                self.door = None
        if self.speed != 8:
            self.speed = 8
            self.status["AGI"] = 8
        # キャラクターアニメーション（frameに応じて描画イメージを切り替える）
        self.frame += 1
        self.image = self.images[self.name][self.direction *
                                            4+(self.frame // self.animcycle % 4)]

    def get_next_automove(self):
        """次の移動先を得る"""
        if len(self.automove) > 0:
            return self.automove[0]
        return None
    
    def pop_automove(self):
        """自動移動を1つ取り出す"""
        self.automove.pop(0)

    def append_automove(self, ch):
        """自動移動に追加する"""
        self.automove.extend(ch)

    def search(self, mymap: Map):
        """足もとに宝箱またはワープゾーンがあるか調べる"""
        event = mymap.get_event(self.x, self.y)
        if isinstance(event, Treasure) or isinstance(event, MoveEvent):
            if isinstance(event, Treasure):
                ### 宝箱を開けることの情報を送信する
                self.sender.send_event({"item": {"name": event.item, "line": event.fromTo[0]}, "fromTo": event.fromTo, "funcWarp": event.funcWarp})
                itemResult = self.sender.receive_json()
                if itemResult is None:
                    return False
                
                if (mymap.name, event.func, event.fromTo[0]) in self.checkedFuncs:
                    for skippedFunc in itemResult["skippedFunc"]:
                        self.checkedFuncs[(mymap.name, event.func, event.fromTo[0])].append((skippedFunc, None, False))
                if itemResult['status'] == "ok":
                    if itemResult.get('skip', False):
                        MSGWND.set(itemResult['message'], (['はい', 'いいえ'], 'func_skip'))
                    else:
                        # 初期化値なしの変数でコメントを初期化する
                        if 'values' not in itemResult:
                            PLAYER.remove_itemvalue()
                        event.open(itemResult['item']['value'], itemResult['item']['line'], event.exps)
                        item_get_message = f"宝箱を開けた！\n「{event.item}」を手に入れた！"
                        if (indexes := event.exps.get("indexes", None)):
                            item_get_message += "\f" + "\f".join(indexes)
                        if itemResult.get("undefined", False):
                            item_get_message += f"\fただし、アイテム 「{event.item}」 は初期化されていないので注意してください!!"
                        if (mymap.name, event.func, event.fromTo[0]) in self.checkedFuncs:
                            self.checkedFuncs.pop((mymap.name, event.func, event.fromTo[0]))
                        mymap.remove_event(event)
                        MSGWND.set(item_get_message)
                    PLAYER.fp.write("itemget, " + mymap.name + "," + str(PLAYER.x)+", " + str(PLAYER.y) + "," + event.item + "\n")
                else:
                    MSGWND.set(itemResult['message'])
            elif isinstance(event, MoveEvent):
                ### ワープゾーンに入ろうとしていることの情報を送信する (もしfuncWarpが空でなければ戻ってきた時に関数の繰り返しの処理を行うフラグを立てる)
                self.sender.send_event({"type": event.type, "fromTo": event.fromTo, "funcWarp": event.funcWarp})
                moveResult = self.sender.receive_json()
                if moveResult is None:
                    return False
                if (mymap.name, event.func, event.fromTo[0]) in self.checkedFuncs:
                    for skippedFunc in moveResult["skippedFunc"]:
                        self.checkedFuncs[(mymap.name, event.func, event.fromTo[0])].append((skippedFunc, None, False))
                if moveResult['status'] == "ok":
                    # skipアクション (条件文に関数がある場合は関数に遷移するかを判断する)
                    if moveResult.get('skipCond', False):
                        MSGWND.set(moveResult['message'], (['はい', 'いいえ'], 'cond_func_skip'))
                    else:
                        if moveResult.get('skip', False):
                            MSGWND.set(moveResult['message'], (['はい', 'いいえ'], 'loop_skip'))
                        elif (mymap.name, event.func, event.fromTo[0]) in self.checkedFuncs:
                            self.checkedFuncs.pop((mymap.name, event.func, event.fromTo[0]))
                        dest_map = event.dest_map
                        dest_x = event.dest_x
                        dest_y = event.dest_y

                        # region command
                        from_map = mymap.name
                        PLAYER.move5History.append({'mapname': from_map, 'x': PLAYER.x, 'y': PLAYER.y, 'cItems': PLAYER.commonItembag.items[-1], 'items': PLAYER.itembag.items[-1], 'return':False})
                        if len(PLAYER.move5History) > 5:
                            PLAYER.move5History.pop(0)
                        # endregion
                        # 暗転
                        DIMWND.setdf(200)
                        DIMWND.show()
                        mymap.create(dest_map)  # 移動先のマップで再構成
                        PLAYER.set_pos(dest_x, dest_y, DOWN)  # プレイヤーを移動先座標へ
                        mymap.add_chara(PLAYER)  # マップに再登録
                        PLAYER.fp.write("jump, " + dest_map + "," + str(PLAYER.x)+", " + str(PLAYER.y) + "\n")
                else:
                    MSGWND.set(moveResult['message'])
            return True
        return False

    def unlock(self, mymap: Map):
        """キャラクターが向いている方向にドアがあるか調べる"""
        # 向いている方向のとなりの座標を求める
        nextx, nexty = self.x, self.y
        if self.direction == DOWN:
            nexty = self.y + 1
        elif self.direction == LEFT:
            nextx = self.x - 1
        elif self.direction == RIGHT:
            nextx = self.x + 1
        elif self.direction == UP:
            nexty = self.y - 1
        # その方向にドアがあるか？
        event = mymap.get_event(nextx, nexty)
        if isinstance(event, Door):
            # SmallDoorはDoorの子クラスなので、isinstance(event, Door)はTrueになってしまう
            if isinstance(event, SmallDoor):
                if event.status == 0:
                    if event.direction == self.direction:
                        event.open()
                        MSGWND.set(f"「{event.doorname}」への扉を開けた！")
                        if self.door is not None:
                            door = mymap.get_event(self.door.x, self.door.y)
                            if isinstance(door, SmallDoor):
                                door.close()
                                self.door = None
                        self.door = event
                    else:
                        MSGWND.set('この方向から扉は開けられません!!')
                else:
                    return False
            else:
                mymap.remove_event(event)
            return True
        return False

    def talk(self, mymap: Map, linenum: int):
        """キャラクターが向いている方向のとなりにキャラクターがいるか調べる"""
        # 向いている方向のとなりの座標を求める
        nextx, nexty = self.x, self.y
        if self.direction == DOWN:
            nexty = self.y + 1
        elif self.direction == LEFT:
            nextx = self.x - 1
        elif self.direction == RIGHT:
            nextx = self.x + 1
        elif self.direction == UP:
            nexty = self.y - 1
        event = mymap.get_event(nextx, nexty)
        if isinstance(event, Object) and event.mapchip == 242:
            nexty -= 1
        # その方向にキャラクターがいるか？
        chara = mymap.get_chara(nextx, nexty)
        # キャラクターがいればプレイヤーの方向へ向ける
        if chara is not None:
            if self.direction == DOWN:
                chara.direction = UP
            elif self.direction == LEFT:
                chara.direction = RIGHT
            elif self.direction == RIGHT:
                chara.direction = LEFT
            elif self.direction == UP:
                chara.direction = DOWN
            chara.update(mymap)  # 向きを変えたので更新

            if isinstance(chara, Character):
                if isinstance(chara, CharaExpression):
                    linenum = self.sender.code_window.linenum
                    if chara.linenum is None:
                        chara.linenum = linenum

                    if (exps := chara.exps.get(str(chara.linenum), None)):
                        self.sender.send_event({"type": exps["type"], "fromTo": exps["fromTo"], "funcWarp": exps["funcWarp"]})
                        charaExpressionResult = self.sender.receive_json()
                        if (mymap.name, chara.func, exps["fromTo"][0]) in self.checkedFuncs:
                            for skippedFunc in charaExpressionResult["skippedFunc"]:
                                self.checkedFuncs[(mymap.name, chara.func, exps["fromTo"][0])].append((skippedFunc, None, False))
                        if charaExpressionResult is None:
                            return False
                        
                        if charaExpressionResult['status'] == "ng":
                            MSGWND.set(charaExpressionResult['message'])
                        else:
                            if charaExpressionResult.get('skipCond', False):
                                MSGWND.set(charaExpressionResult['message'], (['はい', 'いいえ'], 'exp_func_skip'))
                            else:
                                item_line_info = {}
                                for item_value_changed in charaExpressionResult["values"]:
                                    item_line_info[item_value_changed["item"]["name"]] = item_value_changed["item"]["line"]

                                for var_path in exps["vars"]:
                                    if (line := item_line_info.get(var_path[0], None)) is None:
                                        continue
                                    if (item := PLAYER.commonItembag.find(var_path[0], line)) is None:
                                        item = PLAYER.itembag.find(var_path[0], line)
                                    if item is not None:
                                        item.set_exps(var_path[1:], exps["exps"])
                                if (mymap.name, chara.func, exps["fromTo"][0]) in self.checkedFuncs:
                                    self.checkedFuncs.pop((mymap.name, chara.func, exps["fromTo"][0]))
                                chara.linenum = None
                                # とりあえずprintfであるかどうかに関わらず同じメッセージを入れる
                                MSGWND.set(chara.message)         
                    else:
                        self.sender.send_event({"itemsetall": True})
                        itemsetAllResult = self.sender.receive_json()
                        MSGWND.set(itemsetAllResult['message'])
                        chara.linenum = None
                elif isinstance(chara, CharaReturn):
                    PLAYER.set_waitingMove_return(mymap, chara)
                elif isinstance(chara, CharaCheckCondition):
                    if ((chara.initial_direction == DOWN and self.direction == UP) or (chara.initial_direction == LEFT and self.direction == RIGHT) or
                        (chara.initial_direction == RIGHT and self.direction == LEFT) or (chara.initial_direction == UP and self.direction == DOWN)):
                        if chara.moving is False:
                            if chara.avoiding is False:
                                self.sender.send_event({"type": chara.type, "fromTo": chara.fromTo, "funcWarp": chara.funcWarp})
                                CCCharacterResult = self.sender.receive_json()
                                if CCCharacterResult is not None:
                                    if (mymap.name, chara.func, chara.fromTo[0]) in self.checkedFuncs:
                                        for skippedFunc in CCCharacterResult["skippedFunc"]:
                                            self.checkedFuncs[(mymap.name, chara.func, chara.fromTo[0])].append((skippedFunc, None, False))
                                    if CCCharacterResult['status'] == "ng":
                                        MSGWND.set(CCCharacterResult['message'])
                                    else:
                                        if CCCharacterResult.get('skipCond', False):
                                            MSGWND.set(CCCharacterResult['message'], (['はい', 'いいえ'], 'cond_func_skip'))
                                        else:
                                            if (mymap.name, chara.func, chara.fromTo[0]) in self.checkedFuncs:
                                                self.checkedFuncs.pop((mymap.name, chara.func, chara.fromTo[0]))
                                            self.ccchara = chara.set_checked()
                                else:
                                    MSGWND.set("条件文を確認済みです!!　どうぞお通りください!!")
                                    return False
                            else:
                                MSGWND.set("条件文を確認済みです!!　どうぞお通りください!!")
                        else:
                            MSGWND.set("そのほうこうには　だれもいない。")
                            return False
                    else:
                        MSGWND.set("ここは　出口ではありません。")
                        return False
            return True
        else:
            MSGWND.set("そのほうこうには　だれもいない。")
            return False

    def set_waitingMove_return(self, mymap: Map, chara: "CharaReturn"):
        """returnの案内人に話しかけた時、動的にwaitingMoveを設定する"""
        # main以外のreturnキャラ
        mapname = mymap.name
        fromTo = chara.fromTo
        if self.moveHistory:
            self.sender.send_event({"type": 'return', "fromTo": fromTo + [self.moveHistory[-1]['line']], "funcWarp": chara.funcWarp})
            returnResult = self.sender.receive_json()
            if (mymap.name, chara.func, chara.fromTo[0]) in self.checkedFuncs:
                for skippedFunc in returnResult["skippedFunc"]:
                    self.checkedFuncs[(mymap.name, chara.func, chara.fromTo[0])].append((skippedFunc, None, False))
            if returnResult['status'] == 'ok':
                if returnResult.get('skipReturn', False):
                    MSGWND.set(returnResult['message'], (['はい', 'いいえ'], 'return_func_skip'))
                else:
                    if (mymap.name, chara.func, chara.fromTo[0]) in self.checkedFuncs:
                        self.checkedFuncs.pop((mymap.name, chara.func, chara.fromTo[0]))
                    self.move5History.append({'mapname': mapname, 'x': self.x, 'y': self.y, 'cItems': self.commonItembag.items[-1], 'items': self.itembag.items[-1], 'return':True})
                    if len(self.move5History) > 5:
                        self.move5History.pop(0)
                    move = self.moveHistory.pop()
                    self.itembag.items.pop()
                    PLAYER.remove_itemvalue()
                    for name, item_info in returnResult["items"].items():
                        for line, value in item_info.items():
                            item = PLAYER.commonItembag.find(name, int(line))
                            if item is None:
                                item = PLAYER.itembag.find(name, int(line))
                            if item is not None:
                                item.update_value(value)
                    if (move['mapname'], returnResult["backToFunc"], returnResult["backToLine"]) in PLAYER.checkedFuncs:
                        # ここは辞書を使うかどうかを考える
                        checkedFunc = PLAYER.checkedFuncs[(move['mapname'], returnResult["backToFunc"], returnResult["backToLine"])][-1]
                        PLAYER.checkedFuncs[(move['mapname'], returnResult["backToFunc"], returnResult["backToLine"])][-1] = (checkedFunc[0], returnResult["retVal"], checkedFunc[2])
                    PLAYER.func = returnResult["backToFunc"]
                    self.waitingMove = chara
                    self.waitingMove.dest_map = move['mapname']
                    self.waitingMove.dest_x = move['x']
                    self.waitingMove.dest_y = move['y']
                    self.fp.write("moveout, " + mapname + "," + str(self.x)+", " + str(self.y) + "\n")
                    MSGWND.set(chara.message)
                return
        # mainのreturnキャラ
        else:
            self.sender.send_event({"return": fromTo})
            returnResult = self.sender.receive_json()
            if (mymap.name, chara.func, chara.fromTo[0]) in self.checkedFuncs:
                for skippedFunc in returnResult["skippedFunc"]:
                    self.checkedFuncs[(mymap.name, chara.func, chara.fromTo[0])].append((skippedFunc, None, False))
            if returnResult['status'] == 'ok':
                if returnResult.get('skipReturn', False):
                    MSGWND.set(returnResult['message'], (['はい', 'いいえ'], 'return_func_skip'))
                elif returnResult.get('finished', False):
                    MSGWND.set(returnResult['message'], (['ステージ選択画面に戻る'], 'finished'))
                    self.fp.write("finished\n")
                    MSGWND.set(chara.message)
                return
        MSGWND.set(returnResult['message'])
    
    def remove_itemvalue(self):
        self.commonItembag.remove_item_exps()
        self.itembag.remove_item_exps()

    def set_game_mode(self, type):
        if type == "item":
            self.itemNameShow = not self.itemNameShow

#                                                                                                                                                   
# 88b           d88                                                                  88888888888                         88                         
# 888b         d888                                                                  88                                  ""                         
# 88`8b       d8'88                                                                  88                                                             
# 88 `8b     d8' 88  ,adPPYba, ,adPPYba, ,adPPYba, ,adPPYYba,  ,adPPYb,d8  ,adPPYba, 88aaaaa     8b,dPPYba,   ,adPPYb,d8 88 8b,dPPYba,   ,adPPYba,  
# 88  `8b   d8'  88 a8P_____88 I8[    "" I8[    "" ""     `Y8 a8"    `Y88 a8P_____88 88"""""     88P'   `"8a a8"    `Y88 88 88P'   `"8a a8P_____88  
# 88   `8b d8'   88 8PP"""""""  `"Y8ba,   `"Y8ba,  ,adPPPPP88 8b       88 8PP""""""" 88          88       88 8b       88 88 88       88 8PP"""""""  
# 88    `888'    88 "8b,   ,aa aa    ]8I aa    ]8I 88,    ,88 "8a,   ,d88 "8b,   ,aa 88          88       88 "8a,   ,d88 88 88       88 "8b,   ,aa  
# 88     `8'     88  `"Ybbd8"' `"YbbdP"' `"YbbdP"' `"8bbdP"Y8  `"YbbdP"Y8  `"Ybbd8"' 88888888888 88       88  `"YbbdP"Y8 88 88       88  `"Ybbd8"'  
#                                                              aa,    ,88                                     aa,    ,88                            
#                                                               "Y8bbdP"                                       "Y8bbdP"                             
# 

class MessageEngine:
    """メッセージエンジン"""
    FONT_WIDTH = 16
    FONT_HEIGHT = 18
    WHITE = Color(255, 255, 255, 255)
    RED = Color(255, 31, 31, 255)
    GREEN = Color(31, 255, 31, 255)
    BLUE = Color(31, 31, 255, 255)

    def __init__(self):
        self.color = self.WHITE
        self.myfont = pygame.freetype.Font(
            FONT_DIR + FONT_NAME, self.FONT_HEIGHT)

    def set_color(self, color):
        """文字色をセット"""
        self.color = color
        # 変な値だったらWHITEにする
        if not self.color in [self.WHITE, self.RED, self.GREEN, self.BLUE]:
            self.color = self.WHITE

    def draw_character(self, screen, pos, ch):
        """1文字だけ描画する"""
        if ch not in [" ", "　"]:
            x, y = pos
            try:
                surf, rect = self.myfont.render(ch, self.color)
                screen.blit(surf, (x, y+(self.FONT_HEIGHT//2) - rect[3]//2))
#                screen.blit(self.myfont.render(ch,self.color)[0],(x,y))
            except KeyError:
                print(f"描画できない文字があります:{ch}")

    def draw_string(self, screen, pos, string):
        """文字列を描画"""
        x, y = pos
        screen.blit(self.myfont.render(string,self.WHITE)[0],(x,y))

#                                                                                    
# I8,        8        ,8I 88                      88                                 
# `8b       d8b       d8' ""                      88                                 
#  "8,     ,8"8,     ,8"                          88                                 
#   Y8     8P Y8     8P   88 8b,dPPYba,   ,adPPYb,88  ,adPPYba,  8b      db      d8  
#   `8b   d8' `8b   d8'   88 88P'   `"8a a8"    `Y88 a8"     "8a `8b    d88b    d8'  
#    `8a a8'   `8a a8'    88 88       88 8b       88 8b       d8  `8b  d8'`8b  d8'   
#     `8a8'     `8a8'     88 88       88 "8a,   ,d88 "8a,   ,a8"   `8bd8'  `8bd8'    
#      `8'       `8'      88 88       88  `"8bbdP"Y8  `"YbbdP"'      YP      YP      
#                                                                                    
#                                                                                    
# 

class Window:
    """ウィンドウの基本クラス"""
    EDGE_WIDTH = 4  # 白枠の幅

    def __init__(self, rect):
        self.width = rect[2]
        self.height = rect[3]
        self.x = rect[0]
        self.y = rect[1]
        self.surface = pygame.Surface(
            (self.width, self.height), pygame.SRCALPHA)
        # self.surface.convert_alpha()
        self.rect = Rect(0, 0, self.width, self.height)  # 一番外側の白い矩形
        # 内側の黒い矩形
        self.inner_rect = self.rect.inflate(-self.EDGE_WIDTH, -self.EDGE_WIDTH)
        self.is_visible = False  # ウィンドウを表示中か？

    def draw(self):
        """ウィンドウを描画"""
        if self.is_visible is False:
            return
        # pygame.draw.rect(, (255,255,255), self.rect, 0)
        self.surface.fill(Color(0, 0, 0, 150))
        pygame.draw.lines(self.surface, Color(255, 255, 255, 255), True,
                            [[0, 0],
                             [0, self.height-(self.EDGE_WIDTH/2)],
                             [self.width-(self.EDGE_WIDTH/2), self.height-(self.EDGE_WIDTH/2)],
                             [self.width-(self.EDGE_WIDTH/2), 0] ],
                             self.EDGE_WIDTH)

    def blit(self, screen):
        """blit"""
        screen.blit(self.surface, (self.x, self.y))

    def show(self):
        """ウィンドウを表示"""
        self.is_visible = True

    def hide(self):
        """ウィンドウを隠す"""
        self.is_visible = False


#                                                                                                                      
# 88888888ba,   88                  I8,        8        ,8I 88                      88                                 
# 88      `"8b  ""                  `8b       d8b       d8' ""                      88                                 
# 88        `8b                      "8,     ,8"8,     ,8"                          88                                 
# 88         88 88 88,dPYba,,adPYba,  Y8     8P Y8     8P   88 8b,dPPYba,   ,adPPYb,88  ,adPPYba,  8b      db      d8  
# 88         88 88 88P'   "88"    "8a `8b   d8' `8b   d8'   88 88P'   `"8a a8"    `Y88 a8"     "8a `8b    d88b    d8'  
# 88         8P 88 88      88      88  `8a a8'   `8a a8'    88 88       88 8b       88 8b       d8  `8b  d8'`8b  d8'   
# 88      .a8P  88 88      88      88   `8a8'     `8a8'     88 88       88 "8a,   ,d88 "8a,   ,a8"   `8bd8'  `8bd8'    
# 88888888Y"'   88 88      88      88    `8'       `8'      88 88       88  `"8bbdP"Y8  `"YbbdP"'      YP      YP      
#                                                                                                                      
#                                                                                                                      
# 

class DimWindow:
    """薄暗いウインドウを作る"""
    def __init__(self, rect, screen):
        self.screen = screen
        self.width = rect[2]
        self.height = rect[3]
        self.x = rect[0]
        self.y = rect[1]
        self.surface = pygame.Surface(
            (self.width, self.height), pygame.SRCALPHA)
        self.is_visible = False  # ウィンドウを表示中か？
        self.df = 0
        self.target_df = 0

    def dim(self):
        """ウィンドウを描画"""
        if self.is_visible is False:
            return
        if self.target_df > self.df:
            self.df = self.df + 4
        else:
            self.target_df = 0
            self.df = 0
            self.hide()
        self.surface.fill(Color(0, 0, 0, self.df))
        self.screen.blit(self.surface, (self.x, self.y))

    def setdf(self, df):
        """薄暗さの設定"""
        self.target_df = df

    def show(self):
        """ウィンドウを表示"""
        self.is_visible = True

    def hide(self):
        """ウィンドウを隠す"""
        self.is_visible = False

#                                                                                                                                
# 88          88             88               I8,        8        ,8I 88                      88                                 
# 88          ""             88           ,d  `8b       d8b       d8' ""                      88                                 
# 88                         88           88   "8,     ,8"8,     ,8"                          88                                 
# 88          88  ,adPPYb,d8 88,dPPYba, MM88MMM Y8     8P Y8     8P   88 8b,dPPYba,   ,adPPYb,88  ,adPPYba,  8b      db      d8  
# 88          88 a8"    `Y88 88P'    "8a  88    `8b   d8' `8b   d8'   88 88P'   `"8a a8"    `Y88 a8"     "8a `8b    d88b    d8'  
# 88          88 8b       88 88       88  88     `8a a8'   `8a a8'    88 88       88 8b       88 8b       d8  `8b  d8'`8b  d8'   
# 88          88 "8a,   ,d88 88       88  88,     `8a8'     `8a8'     88 88       88 "8a,   ,d88 "8a,   ,a8"   `8bd8'  `8bd8'    
# 88888888888 88  `"YbbdP"Y8 88       88  "Y888    `8'       `8'      88 88       88  `"8bbdP"Y8  `"YbbdP"'      YP      YP      
#                 aa,    ,88                                                                                                     
#                  "Y8bbdP"                                                                                                      
# 

class LightWindow:
    """光源ウインドウを作る"""
    def __init__(self, rect, screen, fmap):
        self.screen = screen
        self.width = rect[2]
        self.height = rect[3]
        self.x = rect[0]
        self.y = rect[1]
        self.surface = pygame.Surface(
            (self.width, self.height), pygame.SRCALPHA)
        self.is_visible = False  # ウィンドウを表示中か？
        self.alpha = 128
        self.target_alpha = 0
        self.color = Color(0,0,0,0)
        self.map = fmap
        self.light = False
        self.rooms = []

    def set_color_scene(self,scene):
        """背景色の規定セット"""
        if scene == "evening":
            self.set_color(255,148,40,64)
            self.light = False
            self.show()
        elif scene == "dusk":
            self.set_color(32,32,64,128)
            self.light = True
            self.show()
        elif scene == "night":
            self.set_color(16,0,64,196)
            self.light = True
            self.show()
        elif scene == "midnight":
            self.set_color(4,0,4,248)
            self.light = True
            self.show()
        elif scene == "morning":
            self.set_color(0,200,255,48)
            self.light = False
            self.show()
        else:
            self.set_color(0,0,0,0)
            self.light = False
            self.hide()

    def set_rooms(self,rooms):
        """光らせる部屋をを設定"""
        self.rooms = rooms

    def set_color(self,r,g,b,a):
        """背景色を設定"""
        self.color = Color(r,g,b,a)
        self.alpha = a

    def set_alpha(self, alpha):
        """薄暗さの設定"""
        self.target_alpha = alpha

    def draw(self,offset):
        """描画"""
        if self.is_visible is False:
            return
        self.surface.fill(self.color)
        if self.light:
            self.draw_light(offset)
        self.screen.blit(self.surface, (self.x, self.y))

    def draw_light(self,offset):
        """光源の位置を描画"""
        PLAYER.draw_light(self.surface,self.color,offset)
        for cha in self.map.charas:
            if isinstance(cha,Character) and cha.npcname != "" and cha.movetype == 1:
                cha.draw_light(self.surface,self.color,offset)
        for light in self.map.lights:
            if light.room() in self.rooms or light.room() == "":
                light.draw(self.surface,self.color,offset)

    def show(self):
        """ウィンドウを表示"""
        self.is_visible = True

    def hide(self):
        """ウィンドウを隠す"""
        self.is_visible = False

#                                                                                                                                                                     
# 88b           d88                                                                I8,        8        ,8I 88                      88                                 
# 888b         d888                                                                `8b       d8b       d8' ""                      88                                 
# 88`8b       d8'88                                                                 "8,     ,8"8,     ,8"                          88                                 
# 88 `8b     d8' 88  ,adPPYba, ,adPPYba, ,adPPYba, ,adPPYYba,  ,adPPYb,d8  ,adPPYba, Y8     8P Y8     8P   88 8b,dPPYba,   ,adPPYb,88  ,adPPYba,  8b      db      d8  
# 88  `8b   d8'  88 a8P_____88 I8[    "" I8[    "" ""     `Y8 a8"    `Y88 a8P_____88 `8b   d8' `8b   d8'   88 88P'   `"8a a8"    `Y88 a8"     "8a `8b    d88b    d8'  
# 88   `8b d8'   88 8PP"""""""  `"Y8ba,   `"Y8ba,  ,adPPPPP88 8b       88 8PP"""""""  `8a a8'   `8a a8'    88 88       88 8b       88 8b       d8  `8b  d8'`8b  d8'   
# 88    `888'    88 "8b,   ,aa aa    ]8I aa    ]8I 88,    ,88 "8a,   ,d88 "8b,   ,aa   `8a8'     `8a8'     88 88       88 "8a,   ,d88 "8a,   ,a8"   `8bd8'  `8bd8'    
# 88     `8'     88  `"Ybbd8"' `"YbbdP"' `"YbbdP"' `"8bbdP"Y8  `"YbbdP"Y8  `"Ybbd8"'    `8'       `8'      88 88       88  `"8bbdP"Y8  `"YbbdP"'      YP      YP      
#                                                              aa,    ,88                                                                                             
#                                                               "Y8bbdP"                                                                                              
# 

class MessageWindow(Window):
    """メッセージウィンドウ"""
    MAX_LINES = 30             # メッセージを格納できる最大行数
    LINE_HEIGHT = 2            # 行間の大きさ
    animcycle = MAX_FRAME_PER_SEC
    MSGWAIT = 3 * MAX_FRAME_PER_SEC
    HIGHLIGHT_COLOR = (0, 0, 255)

    def __init__(self, rect, msg_eng, sender):
        Window.__init__(self, rect)
        self.sender: EventSender = sender
        self.text_rect = self.inner_rect.inflate(-8, -8)  # テキストを表示する矩形
        self.text = []  # メッセージ
        self.cur_page = 0  # 現在表示しているページ
        self.cur_pos = 0  # 現在ページで表示した最大文字数
        self.next_flag = False  # 次ページがあるか？
        self.hide_flag = False  # 次のキー入力でウィンドウを消すか？
        self.msg_engine = msg_eng  # メッセージエンジン
        self.cursor = load_image("data", "cursor.png", -1)  # カーソル画像
        self.frame = 0
        # max_chars_per_line # 1行の最大文字数
        self.max_chars_per_line = self.text_rect[2]//msg_eng.FONT_WIDTH
        # max_lines_per_page # 1行の最大行数（4行目は▼用）
        self.max_lines_per_page = self.text_rect[3]//msg_eng.FONT_HEIGHT - 1
        self.max_chars_per_page = self.max_chars_per_line * \
            self.max_lines_per_page  # 1ページの最大文字数
        self.msgwincount = 0
        self.selectMsgText = None
        self.select_type = None
        self.selectingIndex = 0
        self.new_std_messages = []
        self.file_message = ""
        self.str_messages = []

    def set(self, base_message, selectMessages=None):
        """メッセージをセットしてウィンドウを画面に表示する"""
        if base_message or len(self.new_std_messages) or len(self.str_messages):
            if selectMessages is not None:
                PLAYER.funcInfoWindow_list = []
                self.selectMsgText, self.select_type = selectMessages
            message_list = []
            if len(self.new_std_messages):
                message_list.append("\n".join(["コンソール出力:"] + self.new_std_messages))
                self.new_std_messages = []
            if len(self.str_messages):
                message_list.append("\n".join(self.str_messages))
                self.str_messages = []
            if len(base_message):
                message_list.append(base_message)
            if len(self.file_message):
                message_list.append(self.file_message)
                self.file_message = ""
            self.cur_pos = 0
            self.cur_page = 0
            self.next_flag = False
            self.hide_flag = False
            # 全角スペースで初期化
            self.text = ""
            # メッセージをセット
            p = 0
            message = "\f".join(message_list)
            for ch in message:
                if ch == "\n":  # \nは改行文字
                    self.text += "\n"
                    self.text += "　" * (self.max_chars_per_line - (p+1) % self.max_chars_per_line)
                    p = int(p//self.max_chars_per_line+1)*self.max_chars_per_line
                elif ch == "\f":  # \fは改ページ文字
                    self.text += "\f"
                    self.text += "　" * (self.max_chars_per_page - (p+1) % self.max_chars_per_page)
                    p = int(p//self.max_chars_per_page+1)*self.max_chars_per_page
                else:
                    self.text += ch
                    p += 1
            # self.text += "$"  # 終端文字
            self.show()

    def update(self):
        """メッセージウィンドウを更新する
        メッセージが流れるように表示する"""
        if self.is_visible:
            if self.next_flag is False and self.hide_flag is False:
                self.cur_pos += 1  # 1文字流す
                # テキスト全体から見た現在位置
                p = self.cur_page * self.max_chars_per_page + self.cur_pos
                if len(self.text) == p:  # 終端文字
                    self.hide_flag = True
                elif self.text[p] == "\n":  # 改行文字
                    self.cur_pos += self.max_chars_per_line
                    self.cur_pos = self.cur_pos//self.max_chars_per_line * self.max_chars_per_line
                elif self.text[p] == "\f":  # 改ページ文字
                    self.cur_pos += self.max_chars_per_page
                    self.cur_pos = self.cur_pos//self.max_chars_per_page * self.max_chars_per_page
                # elif self.text[p] == "$" and len(self.text) == p + 1:  # 終端文字
                #     self.hide_flag = True
                # 1ページの文字数に達したら▼を表示
                if self.cur_pos % self.max_chars_per_page == 0:
                    self.next_flag = True
        self.frame += 1

    def draw(self, screen):
        """メッセージを描画する
        メッセージウィンドウが表示されていないときは何もしない"""
        Window.draw(self)
        if self.is_visible is False:
            return

        # 現在表示しているページのcur_posまでの文字を描画
        for i in range(self.cur_pos):
            ch = self.text[self.cur_page*self.max_chars_per_page+i]
            # if ch == "\n" or ch == "\f" or ch == "$":
            if ch == "\n" or ch == "\f":
                continue  # 制御文字は表示しない
            dx = self.text_rect[0] + MessageEngine.FONT_WIDTH * \
                (i % self.max_chars_per_line)
            dy = self.text_rect[1] + \
                (self.LINE_HEIGHT + MessageEngine.FONT_HEIGHT) * (i // self.max_chars_per_line)
            self.msg_engine.draw_character(self.surface, (dx, dy), ch)
        # 最後のページでない場合は▼を表示
        if (not self.hide_flag) and self.next_flag:
            if int(self.frame // self.animcycle) % 2 == 0:
                dx = self.text_rect[0] + self.max_chars_per_line//2 * \
                    MessageEngine.FONT_WIDTH - MessageEngine.FONT_WIDTH//2
                dy = self.text_rect[1] + \
                    (self.LINE_HEIGHT + MessageEngine.FONT_HEIGHT) * 4
                self.surface.blit(self.cursor, (dx, dy))
        elif self.hide_flag and self.selectMsgText:
            dx = 5
            dy += MessageEngine.FONT_HEIGHT
            for i, text in enumerate(self.selectMsgText):
                text_length = len(text)
                if i == self.selectingIndex:
                    bg_rect = pygame.Rect(
                        dx,
                        dy,
                        text_length * MessageEngine.FONT_WIDTH,
                        MessageEngine.FONT_HEIGHT + 4
                    )
                    pygame.draw.rect(self.surface, self.HIGHLIGHT_COLOR, bg_rect)
                for j, ch in enumerate(text):
                    self.msg_engine.draw_character(self.surface, (dx + j * MessageEngine.FONT_WIDTH, dy), ch)
                dx += (text_length + 1) * MessageEngine.FONT_WIDTH
        Window.blit(self, screen)

    def selectMsg(self, i):
        self.selectingIndex = (self.selectingIndex + i) % len(self.selectMsgText)

    def next(self, fieldmap: Map, force_next=False):
        """メッセージを先に進める"""
        if (self.msgwincount > self.MSGWAIT and not (self.selectMsgText is not None and self.hide_flag)) or force_next:
            # 5秒経つか、スペースキーによる強制進行でメッセージを先に進める (ただし、セレクトメッセージの場合は、強制進行でないと進められない)
            if self.selectMsgText and self.hide_flag:
                if self.select_type == 'loop_skip':
                    if self.selectMsgText[self.selectingIndex] == "はい":
                        startLine = self.sender.code_window.linenum
                        self.sender.send_event({"skip": True})
                        skipResult = self.sender.receive_json()
                        self.sender.code_window.linenum = skipResult["finalLine"]
                        if startLine != skipResult["finalLine"]:
                            for event in fieldmap.events:
                                if isinstance(event, MoveEvent) and event.fromTo[0] == skipResult["finalLine"]:
                                    # 暗転
                                    DIMWND.setdf(200)
                                    DIMWND.show()
                                    fieldmap.create(fieldmap.name)  # 移動先のマップで再構成
                                    PLAYER.set_pos(event.x, event.y, DOWN)  # プレイヤーを移動先座標へ
                                    fieldmap.add_chara(PLAYER)  # マップに再登録
                                    skipResult['message'] += f'\f{skipResult["finalLine"]}行のbreak前まで遷移しました!!'
                                    break
                        self.set(skipResult['message'])
                        PLAYER.remove_itemvalue()
                        for name, item_info in skipResult["items"].items():
                            for line, value in item_info.items():
                                item = PLAYER.commonItembag.find(name, int(line))
                                if item is None:
                                    item = PLAYER.itembag.find(name, int(line))
                                if item is not None:
                                    item.update_value(value)
                    else:
                        self.sender.send_event({"skip": False})
                        skipResult = self.sender.receive_json()
                        self.set(skipResult['message'])
                elif self.select_type == 'func_skip':
                    if self.selectMsgText[self.selectingIndex] == "はい":
                        self.sender.send_event({"skip": True})
                        skipResult = self.sender.receive_json()
                        self.set(skipResult['message'])
                        PLAYER.remove_itemvalue()
                        for name, item_info in skipResult["items"].items():
                            for line, value in item_info.items():
                                item = PLAYER.commonItembag.find(name, int(line))
                                if item is None:
                                    item = PLAYER.itembag.find(name, int(line))
                                if item is not None:
                                    item.update_value(value)
                        event = fieldmap.get_event(PLAYER.x, PLAYER.y)
                        if isinstance(event, Treasure) and len(event.funcWarp) != 0:
                            if (fieldmap.name, event.func, event.fromTo[0]) in PLAYER.checkedFuncs:
                                PLAYER.checkedFuncs[(fieldmap.name, event.func, event.fromTo[0])].append((skipResult["skippedFunc"], skipResult["retVal"], True))
                            else:
                                PLAYER.checkedFuncs[(fieldmap.name, event.func, event.fromTo[0])] = [(skipResult["skippedFunc"], skipResult["retVal"], True)]
                        # 暗転
                        DIMWND.setdf(200)
                        DIMWND.show()
                        fieldmap.create(fieldmap.name)  # 移動先のマップで再構成
                        PLAYER.set_pos(PLAYER.x, PLAYER.y, DOWN)  # プレイヤーを移動先座標へ
                        fieldmap.add_chara(PLAYER)  # マップに再登録
                    else:
                        self.sender.send_event({"skip": False})
                        skipResult = self.sender.receive_json()
                        self.set(skipResult['message'])
                        # 今は一つのファイルだけに対応しているので、マップ名は現在のマップと同じ
                        dest_map = fieldmap.name
                        dest_x = skipResult["skipTo"]["x"]
                        dest_y = skipResult["skipTo"]["y"]

                        PLAYER.func = skipResult["skipTo"]["name"]

                        from_map = fieldmap.name
                        PLAYER.move5History.append({'mapname': from_map, 'x': PLAYER.x, 'y': PLAYER.y, 'cItems': PLAYER.commonItembag.items[-1], 'items': PLAYER.itembag.items[-1], 'return': False})
                        if len(PLAYER.move5History) > 5:
                            PLAYER.move5History.pop(0)
                        PLAYER.moveHistory.append({'mapname': from_map, 'x': PLAYER.x, 'y': PLAYER.y, 'line': skipResult["fromLine"]})
                        
                        event = fieldmap.get_event(PLAYER.x, PLAYER.y)
                        if isinstance(event, Treasure) and len(event.funcWarp) != 0:
                            if (fieldmap.name, event.func, event.fromTo[0]) in PLAYER.checkedFuncs:
                                PLAYER.checkedFuncs[(fieldmap.name, event.func, event.fromTo[0])].append((skipResult["skipTo"]["name"], None, True))
                            else:
                                PLAYER.checkedFuncs[(fieldmap.name, event.func, event.fromTo[0])] = [(skipResult["skipTo"]["name"], None, True)]
                            newItems = []
                            func_num_checked = len(PLAYER.checkedFuncs[(fieldmap.name, event.func, event.fromTo[0])]) - 1
                            arg_index = 0
                            for name, argInfo in skipResult["skipTo"]["items"].items():
                                for line, itemInfo in argInfo.items():
                                    item = Item(name, int(line), itemInfo["value"], event.exps["values"][func_num_checked]["args"][arg_index], itemInfo["type"])
                                    newItems.append(item)
                                    arg_index += 1
                            PLAYER.itembag.items.append(newItems)
                        # 暗転
                        DIMWND.setdf(200)
                        DIMWND.show()
                        fieldmap.create(dest_map)  # 移動先のマップで再構成
                        PLAYER.set_pos(dest_x, dest_y, DOWN)  # プレイヤーを移動先座標へ
                        fieldmap.add_chara(PLAYER)  # マップに再登録
                        PLAYER.fp.write("jump, " + dest_map + "," + str(PLAYER.x)+", " + str(PLAYER.y) + "\n")
                elif self.select_type in ['cond_func_skip', 'exp_func_skip', 'return_func_skip']:
                    if self.selectMsgText[self.selectingIndex] == "はい":
                        self.sender.send_event({"skip": True})
                        skipResult = self.sender.receive_json()
                        self.set(skipResult['message'])
                        PLAYER.remove_itemvalue()
                        for name, item_info in skipResult["items"].items():
                            for line, value in item_info.items():
                                item = PLAYER.commonItembag.find(name, int(line))
                                if item is None:
                                    item = PLAYER.itembag.find(name, int(line))
                                if item is not None:
                                    item.update_value(value)
                        event = fieldmap.get_event(PLAYER.x, PLAYER.y)
                        if isinstance(event, MoveEvent) and len(event.funcWarp) != 0:
                            if (fieldmap.name, event.func, event.fromTo[0]) in PLAYER.checkedFuncs:
                                PLAYER.checkedFuncs[(fieldmap.name, event.func, event.fromTo[0])].append((skipResult["skippedFunc"], skipResult["retVal"], True))
                            else:
                                PLAYER.checkedFuncs[(fieldmap.name, event.func, event.fromTo[0])] = [(skipResult["skippedFunc"], skipResult["retVal"], True)]
                        if PLAYER.direction == DOWN:
                            x = PLAYER.x
                            y = PLAYER.y+1
                        elif PLAYER.direction == LEFT:
                            x = PLAYER.x-1
                            y = PLAYER.y
                        elif PLAYER.direction == RIGHT:
                            x = PLAYER.x+1
                            y = PLAYER.y
                        else:
                            x = PLAYER.x
                            y = PLAYER.y-1
                        chara = fieldmap.get_chara(x, y)
                        if (isinstance(chara, CharaCheckCondition) or isinstance(chara, CharaReturn)) and len(chara.funcWarp) != 0:
                            if (fieldmap.name, chara.func, chara.fromTo[0]) in PLAYER.checkedFuncs:
                                PLAYER.checkedFuncs[(fieldmap.name, chara.func, chara.fromTo[0])].append((skipResult["skippedFunc"], skipResult["retVal"], True))
                            else:
                                PLAYER.checkedFuncs[(fieldmap.name, chara.func, chara.fromTo[0])] = [(skipResult["skippedFunc"], skipResult["retVal"], True)]
                        elif isinstance(chara, CharaExpression):
                            if (fieldmap.name, chara.func, chara.exps[str(chara.linenum)]["fromTo"][0]) in PLAYER.checkedFuncs:
                                PLAYER.checkedFuncs[(fieldmap.name, chara.func, chara.exps[str(chara.linenum)]["fromTo"][0])].append((skipResult["skippedFunc"], skipResult["retVal"], True))
                            else:
                                PLAYER.checkedFuncs[(fieldmap.name, chara.func, chara.exps[str(chara.linenum)]["fromTo"][0])] = [(skipResult["skippedFunc"], skipResult["retVal"], True)]
                    else:
                        self.sender.send_event({"skip": False})
                        skipResult = self.sender.receive_json()
                        event = fieldmap.get_event(PLAYER.x, PLAYER.y)
                        if isinstance(event, MoveEvent) and len(event.funcWarp) != 0:
                            if (fieldmap.name, event.func, event.fromTo[0]) in PLAYER.checkedFuncs:
                                PLAYER.checkedFuncs[(fieldmap.name, event.func, event.fromTo[0])].append((skipResult["skipTo"]["name"], None, True))
                            else:
                                PLAYER.checkedFuncs[(fieldmap.name, event.func, event.fromTo[0])] = [(skipResult["skipTo"]["name"], None, True)]
                            newItems = []
                            func_num_checked = len(PLAYER.checkedFuncs[(fieldmap.name, event.func, event.fromTo[0])]) - 1
                            arg_index = 0
                            print(func_num_checked, event.funcExps)
                            for name, argInfo in skipResult["skipTo"]["items"].items():
                                for line, itemInfo in argInfo.items():
                                    item = Item(name, int(line), itemInfo["value"], event.funcExps[func_num_checked]["args"][arg_index], itemInfo["type"])
                                    newItems.append(item)
                                    arg_index += 1
                            PLAYER.itembag.items.append(newItems)
                        if PLAYER.direction == DOWN:
                            x = PLAYER.x
                            y = PLAYER.y+1
                        elif PLAYER.direction == LEFT:
                            x = PLAYER.x-1
                            y = PLAYER.y
                        elif PLAYER.direction == RIGHT:
                            x = PLAYER.x+1
                            y = PLAYER.y
                        else:
                            x = PLAYER.x
                            y = PLAYER.y-1
                        chara = fieldmap.get_chara(x, y)
                        if (isinstance(chara, CharaCheckCondition) or isinstance(chara, CharaReturn)) and len(chara.funcWarp) != 0:
                            if (fieldmap.name, chara.func, chara.fromTo[0]) in PLAYER.checkedFuncs:
                                PLAYER.checkedFuncs[(fieldmap.name, chara.func, chara.fromTo[0])].append((skipResult["skipTo"]["name"], None, True))
                            else:
                                PLAYER.checkedFuncs[(fieldmap.name, chara.func, chara.fromTo[0])] = [(skipResult["skipTo"]["name"], None, True)]
                            newItems = []
                            func_num_checked = len(PLAYER.checkedFuncs[(fieldmap.name, chara.func, chara.fromTo[0])]) - 1
                            arg_index = 0
                            for name, argInfo in skipResult["skipTo"]["items"].items():
                                for line, itemInfo in argInfo.items():
                                    item = Item(name, int(line), itemInfo["value"], chara.funcExps[func_num_checked]["args"][arg_index] if isinstance(chara, CharaCheckCondition) else chara.exps[func_num_checked]["args"][arg_index], itemInfo["type"])
                                    newItems.append(item)
                                    arg_index += 1
                            PLAYER.itembag.items.append(newItems)
                        elif isinstance(chara, CharaExpression):
                            if (fieldmap.name, chara.func, chara.exps[str(chara.linenum)]["fromTo"][0]) in PLAYER.checkedFuncs:
                                PLAYER.checkedFuncs[(fieldmap.name, chara.func, chara.exps[str(chara.linenum)]["fromTo"][0])].append((skipResult["skipTo"]["name"], None, True))
                            else:
                                PLAYER.checkedFuncs[(fieldmap.name, chara.func, chara.exps[str(chara.linenum)]["fromTo"][0])] = [(skipResult["skipTo"]["name"], None, True)]
                            newItems = []
                            func_num_checked = len(PLAYER.checkedFuncs[(fieldmap.name, chara.func, chara.exps[str(chara.linenum)]["fromTo"][0])]) - 1
                            arg_index = 0
                            for name, argInfo in skipResult["skipTo"]["items"].items():
                                for line, itemInfo in argInfo.items():
                                    item = Item(name, int(line), itemInfo["value"], chara.exps[str(chara.linenum)]["exps"][func_num_checked]["args"][arg_index], itemInfo["type"])
                                    newItems.append(item)
                                    arg_index += 1
                            PLAYER.itembag.items.append(newItems)
                        self.set(skipResult['message'])
                        # 今は一つのファイルだけに対応しているので、マップ名は現在のマップと同じ
                        dest_map = fieldmap.name
                        dest_x = skipResult["skipTo"]["x"]
                        dest_y = skipResult["skipTo"]["y"]

                        from_map = fieldmap.name
                        PLAYER.move5History.append({'mapname': from_map, 'x': PLAYER.x, 'y': PLAYER.y, 'cItems': PLAYER.commonItembag.items[-1], 'items': PLAYER.itembag.items[-1], 'return': False})
                        if len(PLAYER.move5History) > 5:
                            PLAYER.move5History.pop(0)
                        PLAYER.moveHistory.append({'mapname': from_map, 'x': PLAYER.x, 'y': PLAYER.y, 'line': skipResult["fromLine"]})
                        
                        # 暗転
                        DIMWND.setdf(200)
                        DIMWND.show()
                        fieldmap.create(dest_map)  # 移動先のマップで再構成
                        PLAYER.set_pos(dest_x, dest_y, DOWN)  # プレイヤーを移動先座標へ
                        fieldmap.add_chara(PLAYER)  # マップに再登録
                        PLAYER.fp.write("jump, " + dest_map + "," + str(PLAYER.x)+", " + str(PLAYER.y) + "\n")
                elif self.select_type == 'finished':
                    PLAYER.goaled = True
                self.selectMsgText = None
                self.select_type = None
                self.msgwincount = 0
                self.selectingIndex = 0
                return

            if self.is_visible:
                # 現在のページが最後のページだったらウィンドウを閉じる
                if self.hide_flag:
                    self.hide()
                # ▼が表示されてれば次のページへ
                if self.next_flag:
                    self.cur_page += 1
                    self.cur_pos = 0
                    self.next_flag = False
            self.msgwincount = 0

                                                                                                                                          
# 88888888ba                                            I8,        8        ,8I 88                      88                                 
# 88      "8b                                           `8b       d8b       d8' ""                      88                                 
# 88      ,8P                                            "8,     ,8"8,     ,8"                          88                                 
# 88aaaaaa8P' ,adPPYYba, 88       88 ,adPPYba,  ,adPPYba, Y8     8P Y8     8P   88 8b,dPPYba,   ,adPPYb,88  ,adPPYba,  8b      db      d8  
# 88""""""'   ""     `Y8 88       88 I8[    "" a8P_____88 `8b   d8' `8b   d8'   88 88P'   `"8a a8"    `Y88 a8"     "8a `8b    d88b    d8'  
# 88          ,adPPPPP88 88       88  `"Y8ba,  8PP"""""""  `8a a8'   `8a a8'    88 88       88 8b       88 8b       d8  `8b  d8'`8b  d8'   
# 88          88,    ,88 "8a,   ,a88 aa    ]8I "8b,   ,aa   `8a8'     `8a8'     88 88       88 "8a,   ,d88 "8a,   ,a8"   `8bd8'  `8bd8'    
# 88          `"8bbdP"Y8  `"YbbdP'Y8 `"YbbdP"'  `"Ybbd8"'    `8'       `8'      88 88       88  `"8bbdP"Y8  `"YbbdP"'      YP      YP      
                                                                                                                                                                                                                                                                          
class PauseWindow(Window):
    """ポーズウィンドウ""" # 操作説明の表示については後々考える
    FONT_SIZE = 16
    TEXT_COLOR = (255, 255, 255)
    HELP_COLOR = (100, 100, 100)
    HELP_FONT_COLOR = (255, 255, 255)
    TO_GAME_BG_COLOR = (0, 0, 255) 
    TO_GAME_FONT_COLOR = (255, 255, 255)
    TO_SSELECT_BG_COLOR = (255, 0, 0) 
    TO_SSELECT_FONT_COLOR = (255, 255, 255)   

    def __init__(self, rect):
        Window.__init__(self, rect)
        self.font = pygame.freetype.Font(FONT_DIR + FONT_NAME, self.FONT_SIZE)
        self.button_help_rect = pygame.Rect(self.rect.width - 80, 30, 50, 50)
        self.button_toGame_rect = pygame.Rect(self.rect.width // 2 - 210, self.rect.height // 2 - 30, 200, 60)
        self.button_toStageSelect_rect = pygame.Rect(self.rect.width // 2 + 10, self.rect.height // 2 - 30, 200, 60)
        self.mode = "pause"

    def draw(self, screen):
        """ポーズ画面を描画する"""
        if self.is_visible is False:
            return

        Window.draw(self)
        
        # ヘルプボタン
        # pygame.draw.rect(self.surface, self.HELP_COLOR, self.button_help_rect)
        # self.font.size = self.FONT_SIZE * 2
        # label_surf_help, _ = self.font.render("?" if self.mode == "pause" else "←", self.HELP_FONT_COLOR)
        # self.font.size = self.FONT_SIZE
        # label_rect_help = label_surf_help.get_rect(center=self.button_help_rect.center)
        # self.surface.blit(label_surf_help, label_rect_help)

        self.font.size = self.FONT_SIZE * 2
        surf, rect = self.font.render("Pause", self.TEXT_COLOR)
        self.font.size = self.FONT_SIZE
        self.surface.blit(surf, ((self.rect.width - rect[2]) // 2 , self.rect.height // 2 - 100))

        # ゲームボタン
        pygame.draw.rect(self.surface, self.TO_GAME_BG_COLOR, self.button_toGame_rect)
        label_surf_toGame, _ = self.font.render("ゲームに戻る", self.TO_GAME_FONT_COLOR)
        label_rect_toGame = label_surf_toGame.get_rect(center=self.button_toGame_rect.center)
        self.surface.blit(label_surf_toGame, label_rect_toGame)

        # ステージ選択メニューに戻るボタン
        pygame.draw.rect(self.surface, self.TO_SSELECT_BG_COLOR, self.button_toStageSelect_rect)
        label_surf_toStageSelect, _ = self.font.render("ステージ選択画面に戻る", self.TO_SSELECT_FONT_COLOR)
        label_rect_toStageSelect = label_surf_toStageSelect.get_rect(center=self.button_toStageSelect_rect.center)
        self.surface.blit(label_surf_toStageSelect, label_rect_toStageSelect)

        y = self.rect.height // 2 + 50
        x = self.rect.width // 2 - 150
        for line in ["矢印キー:　移動", "shift押しながら移動:　ダッシュ", "space:　前方に対するアクション", "f:　足元に対するアクション", "c:　コマンドラインを開く",
                        "b:　アイテムウィンドウを開く/閉じる", "i:　アイテム名を表示する/消す", "m:　マップ→コード→非表示を切り替える", 
                        "p:　ポーズ画面を開く", "esc:　ゲームを辞める/コマンドラインを閉じる"]:
            surf, rect = self.font.render(line, self.TEXT_COLOR)
            self.surface.blit(surf, (x , y))
            y += 20

        Window.blit(self, screen)

                                                                                                             
# 88888888888 88 88          I8,        8        ,8I 88                      88                                 
# 88          "" 88          `8b       d8b       d8' ""                      88                                 
# 88             88           "8,     ,8"8,     ,8"                          88                                 
# 88aaaaa     88 88  ,adPPYba, Y8     8P Y8     8P   88 8b,dPPYba,   ,adPPYb,88  ,adPPYba,  8b      db      d8  
# 88"""""     88 88 a8P_____88 `8b   d8' `8b   d8'   88 88P'   `"8a a8"    `Y88 a8"     "8a `8b    d88b    d8'  
# 88          88 88 8PP"""""""  `8a a8'   `8a a8'    88 88       88 8b       88 8b       d8  `8b  d8'`8b  d8'   
# 88          88 88 "8b,   ,aa   `8a8'     `8a8'     88 88       88 "8a,   ,d88 "8a,   ,a8"   `8bd8'  `8bd8'    
# 88          88 88  `"Ybbd8"'    `8'       `8'      88 88       88  `"8bbdP"Y8  `"YbbdP"'      YP      YP      
                                                                                                              
class FileWindow(Window):
    """ファイル表示ウィンドウ"""
    FONT_SIZE = 20
    FONT_COLOR = (255, 255, 255)

    def __init__(self):
        Window.__init__(self, pygame.Rect(SBW_WIDTH // 3, 10, SBW_WIDTH // 3 , SBW_HEIGHT // 2))
        self.is_visible = False  # ウィンドウを表示中か？
        self.font = pygame.freetype.Font(FONT_DIR + FONT_NAME, self.FONT_SIZE)
        self.filename = None
        self.filelines = []

    def toggle_is_visible(self, filename):
        if filename == self.filename:
            self.is_visible = False
            self.filename = None
        else:
            self.is_visible = True
            self.filename = filename
            self.read_filelines()

    def read_filelines(self):
        if self.filename:
            time.sleep(0.1)
            with open(f"debugger-C/{self.filename[1:-1]}", "r", encoding="utf-8") as f:
                self.filelines = f.read().splitlines()

    def draw_string(self, x, y, string):
        """文字列出力"""
        surf, rect = self.font.render(string, self.FONT_COLOR)
        self.surface.blit(surf, (x, y+(self.FONT_SIZE+2)-rect[3]))

    def draw(self, screen):
        if self.is_visible:
            Window.draw(self)
            offset_y = 10
            for fileline in self.filelines:
                self.draw_string(10, offset_y, fileline)
                offset_y += 24
            Window.blit(self, screen)

#                                                                                                                          
# 88                                    I8,        8        ,8I 88                      88                                 
# 88   ,d                               `8b       d8b       d8' ""                      88                                 
# 88   88                                "8,     ,8"8,     ,8"                          88                                 
# 88 MM88MMM ,adPPYba, 88,dPYba,,adPYba,  Y8     8P Y8     8P   88 8b,dPPYba,   ,adPPYb,88  ,adPPYba,  8b      db      d8  
# 88   88   a8P_____88 88P'   "88"    "8a `8b   d8' `8b   d8'   88 88P'   `"8a a8"    `Y88 a8"     "8a `8b    d88b    d8'  
# 88   88   8PP""""""" 88      88      88  `8a a8'   `8a a8'    88 88       88 8b       88 8b       d8  `8b  d8'`8b  d8'   
# 88   88,  "8b,   ,aa 88      88      88   `8a8'     `8a8'     88 88       88 "8a,   ,d88 "8a,   ,a8"   `8bd8'  `8bd8'    
# 88   "Y888 `"Ybbd8"' 88      88      88    `8'       `8'      88 88       88  `"8bbdP"Y8  `"YbbdP"'      YP      YP      
#                                                                                                                          
#                                                                                                                          
# 

class ItemWindow(Window):
    """ステータスウィンドウ"""
    FONT_HEIGHT = 16
    WHITE = Color(255, 255, 255, 255)
    BLACK = Color(0, 0, 0, 255)
    RED = Color(255, 31, 31, 255)
    GREEN = Color(31, 255, 31, 255)
    BLUE = Color(31, 31, 255, 255)
    CYAN = Color(100, 248, 248, 255)

    mapchip = 456  # アイテムのUI(テスト用)

    def __init__(self, rect, player):
        Window.__init__(self, rect)
        self.text_rect = self.inner_rect.inflate(-2, -2)  # テキストを表示する矩形
        self.myfont = pygame.freetype.Font(
            FONT_DIR + FONT_NAME, self.FONT_HEIGHT)
        self.color = self.WHITE
        self.player = player
        self.image = Map.images[self.mapchip]
        self.itemChips = ItemChips()
        self.item_changed_lines: set[int] = set()
        self.check_exps_line: tuple[int, bool] = (-1, False)
        self.file_buttons: dict[str, pygame.Rect] = {}
        self.file_window = FileWindow()
        self.is_inAction = True
        self.action_trigger_line_dict: dict[int, ItemValue] = {}

    def draw_string(self, x, y, string, color, size=None):
        """文字列出力"""
        if size:
            self.myfont.size = size
        surf, rect = self.myfont.render(string, color)
        self.surface.blit(surf, (x, y+(self.FONT_HEIGHT+2)-rect[3]))
        if size:
            self.myfont.size = self.FONT_HEIGHT

    def draw(self, screen):
        """メッセージを描画する
        メッセージウィンドウが表示されていないときは何もしない"""
        if not self.is_visible:
            return
        
        Window.draw(self)
        offset_y = 10
        # グローバル変数
        for item in PLAYER.commonItembag.items[-1]:
            is_item_changed = False
            if item.itemvalue.declared_exps is not None:
                is_item_changed = True
                if not MSGWND.is_visible and self.check_exps_line[0] == offset_y // 24:
                    if self.check_exps_line[1]:
                        self.check_exps_line = (-1, False)
                    else:
                        MSGWND.set('\f'.join(item.itemvalue.declared_exps))
                        self.check_exps_line = (self.check_exps_line[0], True)
                self.item_changed_lines.add(offset_y // 24)
                pygame.draw.rect(self.surface, self.RED if self.check_exps_line[0] == offset_y // 24 and self.check_exps_line[1] else self.WHITE, 
                                 pygame.Rect(0, offset_y, self.rect.width, 24))
            if item.index_exps is not None:
                is_item_changed = True
                if not MSGWND.is_visible and self.check_exps_line[0] == offset_y // 24:
                    if self.check_exps_line[1]:
                        self.check_exps_line = (-1, False)
                    else:
                        MSGWND.set('\f'.join(item.index_exps))
                        self.check_exps_line = (self.check_exps_line[0], True)
                self.item_changed_lines.add(offset_y // 24)
                pygame.draw.rect(self.surface, self.RED if self.check_exps_line[0] == offset_y // 24 and self.check_exps_line[1] else self.WHITE, 
                                 pygame.Rect(0, offset_y, self.rect.width, 24))
            if item.itemvalue.changed_exps is not None:
                is_item_changed = True
                if not MSGWND.is_visible and self.check_exps_line[0] == offset_y // 24:
                    if self.check_exps_line[1]:
                        self.check_exps_line = (-1, False)
                    else:
                        MSGWND.set('\f'.join(item.itemvalue.changed_exps))
                        self.check_exps_line = (self.check_exps_line[0], True)
                self.item_changed_lines.add(offset_y // 24)
                pygame.draw.rect(self.surface, self.RED if self.check_exps_line[0] == offset_y // 24 and self.check_exps_line[1] else self.CYAN, 
                                 pygame.Rect(0, offset_y, self.rect.width, 24))
                
            icon_x = 10
            if item.itemvalue.children:
                self.draw_string(icon_x, offset_y+4, '▼' if item.itemvalue.is_open else '▶', self.GREEN, 16)
                if self.is_inAction:
                    self.action_trigger_line_dict[offset_y // 24] = item.itemvalue
                icon_x += 15

            # 型に応じたアイコンを blit（描画）
            icon, constLock = self.itemChips.getChip(item.vartype)

            icon_y = offset_y
            text_x = icon_x + icon.get_width() + 6  # ← アイコン幅 + 余白（6px）

            if icon:
                self.surface.blit(icon, (icon_x, icon_y))

            if constLock:
                self.surface.blit(constLock, (icon_x + icon.get_width() - 12, icon_y))

            # アイコンの右に名前と値を描画
            self.draw_string(text_x, offset_y+4, f"{item.name:<8}", self.GREEN)

            # 配列などの値がないvalueは表示しない
            if item.itemvalue.value is not None:
                name_offset = self.myfont.get_rect(item.name).width + 30
                self.draw_string(text_x + name_offset, offset_y+4, f"({item.itemvalue.value})", self.GREEN)
            
            offset_y += 24
            if item.itemvalue.is_open:
                # ここで変数の値の開閉ボタンを作る
                offset_y = self.draw_values(item.itemvalue.children, offset_y, 24, 'global')

        # ローカル変数
        for item in PLAYER.itembag.items[-1]:
            is_item_changed = False
            if item.itemvalue.declared_exps is not None:
                is_item_changed = True
                if not MSGWND.is_visible and self.check_exps_line[0] == offset_y // 24:
                    if self.check_exps_line[1]:
                        self.check_exps_line = (-1, False)
                    else:
                        comments = []
                        for comment in item.itemvalue.declared_exps:
                            comments.append(comment["comment"] if isinstance(comment, dict) else comment)
                        MSGWND.set('\f'.join(comments))
                        self.check_exps_line = (self.check_exps_line[0], True)
                self.item_changed_lines.add(offset_y // 24)
                pygame.draw.rect(self.surface, self.RED if self.check_exps_line[0] == offset_y // 24 and self.check_exps_line[1] else self.WHITE, 
                                 pygame.Rect(0, offset_y, self.rect.width, 24))
            if item.index_exps is not None:
                is_item_changed = True
                if not MSGWND.is_visible and self.check_exps_line[0] == offset_y // 24:
                    if self.check_exps_line[1]:
                        self.check_exps_line = (-1, False)
                    else:
                        MSGWND.set('\f'.join(item.index_exps))
                        self.check_exps_line = (self.check_exps_line[0], True)
                self.item_changed_lines.add(offset_y // 24)
                pygame.draw.rect(self.surface, self.RED if self.check_exps_line[0] == offset_y // 24 and self.check_exps_line[1] else self.WHITE, 
                                 pygame.Rect(0, offset_y, self.rect.width, 24))
            if item.itemvalue.changed_exps is not None:
                is_item_changed = True
                if not MSGWND.is_visible and self.check_exps_line[0] == offset_y // 24:
                    if self.check_exps_line[1]:
                        self.check_exps_line = (-1, False)
                    else:
                        MSGWND.set('\f'.join(item.itemvalue.changed_exps))
                        self.check_exps_line = (self.check_exps_line[0], True)
                self.item_changed_lines.add(offset_y // 24)
                pygame.draw.rect(self.surface, self.RED if self.check_exps_line[0] == offset_y // 24 and self.check_exps_line[1] else self.CYAN, 
                                 pygame.Rect(0, offset_y, self.rect.width, 24))

            icon_x = 10
            if item.itemvalue.children and item.vartype != "FILE *":
                self.draw_string(icon_x, offset_y+4, '▼' if item.itemvalue.is_open else '▶', self.BLACK if is_item_changed else self.WHITE, 16)
                if self.is_inAction:
                    self.action_trigger_line_dict[offset_y // 24] = item.itemvalue
                icon_x += 15

            # 型に応じたアイコンを blit（描画）
            icon, constLock = self.itemChips.getChip(item.vartype)
            icon_y = offset_y
            text_x = icon_x + icon.get_width() + 10  # ← アイコン幅 + 余白（10px）

            if icon:
                self.surface.blit(icon, (icon_x, icon_y))

            if constLock:
                self.surface.blit(constLock, (icon_x + icon.get_width() - 12, icon_y))

            if item.itemvalue.value in PLAYER.address_to_size:
                self.draw_string(text_x - 12, offset_y + 6, PLAYER.address_to_size[item.itemvalue.value]["size"], self.BLACK if is_item_changed else self.WHITE)

            # アイコンの右に名前と値を描画
            self.draw_string(text_x, offset_y+4, f"{item.name:<8}", self.BLACK if is_item_changed else self.WHITE)

            if item.vartype == "FILE *" and item.itemvalue.value in PLAYER.address_to_fname:
                name_offset = self.myfont.get_rect(item.name).width + 30
                file_button = pygame.Rect(text_x + name_offset, offset_y + 2, 100, 20)
                pygame.draw.rect(self.surface, (100, 100, 100), file_button)  # グレーのボタン
                label_surf, _ = self.myfont.render(PLAYER.address_to_fname[item.itemvalue.value][1:-1], (255, 255, 255))
                label_rect = label_surf.get_rect(center=file_button.center)
                self.file_buttons[PLAYER.address_to_fname[item.itemvalue.value]] = file_button
                self.surface.blit(label_surf, label_rect)

            # 配列などの値がないvalueは表示しない
            if item.itemvalue.value is not None and item.vartype != "FILE *":
                value_color = self.BLACK if is_item_changed else self.WHITE 
                name_offset = self.myfont.get_rect(item.name).width + 20
                self.draw_string(text_x + name_offset, offset_y+4, f"({item.itemvalue.value})", value_color)
            
            offset_y += 24
            if item.itemvalue.is_open and item.vartype != "FILE *":
                offset_y = self.draw_values(item.itemvalue.children, offset_y, 24, 'local')

        if self.is_inAction:
            self.is_inAction = False
        self.file_window.draw(screen)
        Window.blit(self, screen)

    def draw_values(self, itemvalue_children: dict[str | int, "ItemValue"], offset_y: int, offset_x: int, type: str):
        text_x = offset_x
        for valuename, itemvalue in itemvalue_children.items():
            is_item_changed = False
            if itemvalue.declared_exps is not None:
                is_item_changed = True
                if not MSGWND.is_visible and self.check_exps_line and self.check_exps_line[0] == offset_y // 24:
                    if self.check_exps_line[1]:
                        self.check_exps_line = (-1, False)
                    else:
                        comments = []
                        for comment in itemvalue.declared_exps:
                            comments.append(comment["comment"] if isinstance(comment, dict) else comment)
                        MSGWND.set('\f'.join(comments))
                        self.check_exps_line = (self.check_exps_line[0], True)
                self.item_changed_lines.add(offset_y // 24)
                pygame.draw.rect(self.surface, self.RED if self.check_exps_line[0] == offset_y // 24 and self.check_exps_line[1] else self.WHITE,
                                pygame.Rect(0, offset_y, self.rect.width, 24))
            if itemvalue.changed_exps is not None:
                is_item_changed = True
                if not MSGWND.is_visible and self.check_exps_line[0] == offset_y // 24:
                    if self.check_exps_line[1]:
                        self.check_exps_line = (-1, False)
                    else:
                        MSGWND.set('\f'.join(itemvalue.changed_exps))
                        self.check_exps_line = (self.check_exps_line[0], True)
                self.item_changed_lines.add(offset_y // 24)
                pygame.draw.rect(self.surface, self.RED if self.check_exps_line[0] == offset_y // 24 and self.check_exps_line[1] else self.CYAN, 
                                 pygame.Rect(0, offset_y, self.rect.width, 24))
            # 型に応じたアイコンを blit（描画）(型はどのように取得するかまだ考えていないので、今はコメントアウト)
            # icon, constLock = self.itemChips.getChip(item.vartype)
            # icon_x = 10
            # icon_y = offset_y
            # text_x = icon_x + icon.get_width() + 10  # ← アイコン幅 + 余白（10px）

            # if icon:
            #     self.surface.blit(icon, (icon_x, icon_y))

            # if constLock:
            #     self.surface.blit(constLock, (icon_x + icon.get_width() - 12, icon_y))

            # アイコンの右に名前と値を描画
            if type == 'global':
                color = self.GREEN
            else:
                color = self.BLACK if is_item_changed else self.WHITE

            if itemvalue.children:
                self.draw_string(10, offset_y+4, '▼' if itemvalue.is_open else '▶', color, 16)
                if self.is_inAction:
                    self.action_trigger_line_dict[offset_y // 24] = itemvalue

            self.draw_string(text_x, offset_y+4, f"{valuename:<8}", color)
            name_offset = self.myfont.get_rect(valuename).width + 20
            if itemvalue.value is not None:
                self.draw_string(text_x + name_offset, offset_y+4, f"({itemvalue.value})", color)

            offset_y += 24

            if itemvalue.is_open:
                offset_y = self.draw_values(itemvalue.children, offset_y, offset_x+24, type)

        return offset_y
    
    def isCursorInWindow(self, pos : tuple[int, int]):
        if self.is_inAction:
            return False
        
        y_line = (pos[1] - self.y - 10) // 24
        local_pos = (pos[0] - self.x, pos[1] - self.y)
        for filename, button in self.file_buttons.items():
            if button.collidepoint(local_pos):
                self.file_window.toggle_is_visible(filename)
                return True
            
        if 10 <= pos[0] <= 30 and y_line in self.action_trigger_line_dict and not MSGWND.is_visible:
            self.action_trigger_line_dict[y_line].is_open = not self.action_trigger_line_dict[y_line].is_open
            self.is_inAction = True
            self.action_trigger_line_dict = {}
            return True
        
        if self.x <= pos[0] <= self.rect[2] and y_line in self.item_changed_lines:
            if not MSGWND.is_visible:
                self.check_exps_line = (y_line, False)
            return True
        else:
            return False

                                                                                                                                                   
# 88888888ba  88             88                                    I8,        8        ,8I 88                      88                                 
# 88      "8b ""             88   ,d                               `8b       d8b       d8' ""                      88                                 
# 88      ,8P                88   88                                "8,     ,8"8,     ,8"                          88                                 
# 88aaaaaa8P' 88  ,adPPYb,d8 88 MM88MMM ,adPPYba, 88,dPYba,,adPYba,  Y8     8P Y8     8P   88 8b,dPPYba,   ,adPPYb,88  ,adPPYba,  8b      db      d8  
# 88""""""8b, 88 a8"    `Y88 88   88   a8P_____88 88P'   "88"    "8a `8b   d8' `8b   d8'   88 88P'   `"8a a8"    `Y88 a8"     "8a `8b    d88b    d8'  
# 88      `8b 88 8b       88 88   88   8PP""""""" 88      88      88  `8a a8'   `8a a8'    88 88       88 8b       88 8b       d8  `8b  d8'`8b  d8'   
# 88      a8P 88 "8a,   ,d88 88   88,  "8b,   ,aa 88      88      88   `8a8'     `8a8'     88 88       88 "8a,   ,d88 "8a,   ,a8"   `8bd8'  `8bd8'    
# 88888888P"  88  `"YbbdP"Y8 88   "Y888 `"Ybbd8"' 88      88      88    `8'       `8'      88 88       88  `"8bbdP"Y8  `"YbbdP"'      YP      YP      
#                 aa,    ,88                                                                                                                          
#                  "Y8bbdP"                                                                                                                           

# class BigItemWindow(Window):
#     """ステータスウィンドウ"""
#     FONT_HEIGHT = 16
#     WHITE = Color(255, 255, 255, 255)
#     RED = Color(255, 31, 31, 255)
#     GREEN = Color(31, 255, 31, 255)
#     BLUE = Color(31, 31, 255, 255)
#     CYAN = Color(100, 248, 248, 255)

#     mapchip = 456  # アイテムのUI(テスト用)

#     def __init__(self, rect, player):
#         Window.__init__(self, rect)
#         self.text_rect = self.inner_rect.inflate(-2, -2)  # テキストを表示する矩形
#         self.myfont = pygame.freetype.Font(
#             FONT_DIR + FONT_NAME, self.FONT_HEIGHT)
#         self.color = self.WHITE
#         self.player = player
#         self.image = Map.images[self.mapchip]
#         self.itemChips = ItemChips()

#     def draw_string(self, x, y, string, color):
#         """文字列出力"""
#         surf, rect = self.myfont.render(string, color)
#         self.surface.blit(surf, (x, y+(self.FONT_HEIGHT+2)-rect[3]))

#     def draw(self, screen):
#         """メッセージを描画する
#         メッセージウィンドウが表示されていないときは何もしない"""
#         if not self.is_visible:
#             return
#         Window.draw(self)
#         for i,item in enumerate(PLAYER.commonItembag.items[-1]):
#             self.draw_string(10, 10 + i*25, f"{item.name:<8} ({item.value})", self.GREEN)
#         gvarnum = len(PLAYER.commonItembag.items[-1])
#         for j, item in enumerate(PLAYER.itembag.items[-1]):
#             y = 10 + (gvarnum + j) * 25

#             # 型に応じたアイコンを blit（描画）
#             icon, constLock = self.itemChips.getChip(item.vartype)
#             icon_x = 10
#             icon_y = y
#             text_x = icon_x + icon.get_width() + 6  # ← アイコン幅 + 余白（6px）

#             if icon:
#                 self.surface.blit(icon, (icon_x, icon_y))

#             if constLock:
#                 self.surface.blit(constLock, (icon_x + icon.get_width() - 12, icon_y))
#                 pass

#             # アイコンの右に名前と値を描画
#             self.draw_string(text_x, y, f"{item.name:<8}", self.WHITE)

#             value_color = self.RED if item.undefined else self.WHITE
#             value_offset = self.myfont.get_rect(item.name).width + 30
#             self.draw_string(text_x + value_offset, y, f"({item.value})", value_color)

#         Window.blit(self, screen)

#                                                                                                                                             
#  ad88888ba                                               I8,        8        ,8I 88                      88                                 
# d8"     "8b ,d                 ,d                        `8b       d8b       d8' ""                      88                                 
# Y8,         88                 88                         "8,     ,8"8,     ,8"                          88                                 
# `Y8aaaaa, MM88MMM ,adPPYYba, MM88MMM 88       88 ,adPPYba, Y8     8P Y8     8P   88 8b,dPPYba,   ,adPPYb,88  ,adPPYba,  8b      db      d8  
#   `"""""8b, 88    ""     `Y8   88    88       88 I8[    "" `8b   d8' `8b   d8'   88 88P'   `"8a a8"    `Y88 a8"     "8a `8b    d88b    d8'  
#         `8b 88    ,adPPPPP88   88    88       88  `"Y8ba,   `8a a8'   `8a a8'    88 88       88 8b       88 8b       d8  `8b  d8'`8b  d8'   
# Y8a     a8P 88,   88,    ,88   88,   "8a,   ,a88 aa    ]8I   `8a8'     `8a8'     88 88       88 "8a,   ,d88 "8a,   ,a8"   `8bd8'  `8bd8'    
#  "Y88888P"  "Y888 `"8bbdP"Y8   "Y888  `"YbbdP'Y8 `"YbbdP"'    `8'       `8'      88 88       88  `"8bbdP"Y8  `"YbbdP"'      YP      YP      
#                                                                                                                                             
#                                                                                                                                             
# 

class StatusWindow(Window):
    """ステータスウィンドウ"""
    FONT_HEIGHT = 16
    WHITE = Color(255, 255, 255, 255)
    RED = Color(255, 31, 31, 255)
    GREEN = Color(31, 255, 31, 255)
    BLUE = Color(31, 31, 255, 255)
    CYAN = Color(100, 248, 248, 255)

    def __init__(self, rect: pygame.Rect, player: Player):
        Window.__init__(self, rect)
        self.text_rect = self.inner_rect.inflate(-2, -2)  # テキストを表示する矩形
        self.myfont = pygame.freetype.Font(
            FONT_DIR + FONT_NAME, self.FONT_HEIGHT)
        self.color = self.WHITE
        self.player = player
        self.name = "あくあたん" + self.player.name

    def draw_string(self, x, y, string, color):
        """文字列出力"""
        surf, rect = self.myfont.render(string, color)
        self.surface.blit(surf, (x, y+(self.FONT_HEIGHT+2)-rect[3]))

    def draw_status(self,x,y,label):
        self.draw_string(x, y, label, self.WHITE)
        self.draw_string(x+40, y, f"{self.player.status[label]:>5}", self.WHITE)

    def draw(self, screen):
        """メッセージを描画する
        メッセージウィンドウが表示されていないときは何もしない"""
        if not self.is_visible:
            return
        Window.draw(self)
#        self.surface.blit(self.img_schedule, self.text_rect)
        self.draw_string(10, 10, self.name, self.WHITE)

        self.draw_status(10,30,"LV")
        self.draw_status(10,50,"HP")
        self.draw_status(100,50,"MP")
        self.draw_status(10,70,"ATK")
        self.draw_status(100,70,"DEF")
        self.draw_status(10,90,"AGI")

        self.draw_string(10, 110, f"現在地:　{self.player.func}", self.CYAN)
        Window.blit(self, screen)

#                                                                                                   
#        db                                      88888888888                                        
#       d88b                    ,d               88                                          ,d     
#      d8'`8b                   88               88                                          88     
#     d8'  `8b    88       88 MM88MMM ,adPPYba,  88aaaaa 8b       d8  ,adPPYba, 8b,dPPYba, MM88MMM  
#    d8YaaaaY8b   88       88   88   a8"     "8a 88""""" `8b     d8' a8P_____88 88P'   `"8a  88     
#   d8""""""""8b  88       88   88   8b       d8 88       `8b   d8'  8PP""""""" 88       88  88     
#  d8'        `8b "8a,   ,a88   88,  "8a,   ,a8" 88        `8b,d8'   "8b,   ,aa 88       88  88,    
# d8'          `8b `"YbbdP'Y8   "Y888 `"YbbdP"'  88888888888 "8"      `"Ybbd8"' 88       88  "Y888  
#                                                                                                   
#                                                                                                   
# 

class AutoEvent():
    """自動イベント"""
    def __init__(self, pos, mapchip, sequence):
        self.x, self.y = pos[0], pos[1]  # イベント座標
        self.mapchip = mapchip  # マップチップ
        self.sequence = sequence  # 移動シーケンス
        self.image = Map.images[self.mapchip]
        self.rect = self.image.get_rect(topleft=(self.x*GS, self.y*GS))

    def draw(self, screen, offset):
        """オフセットを考慮してイベントを描画"""
        offsetx, offsety = offset
        px = self.rect.topleft[0]
        py = self.rect.topleft[1]
        screen.blit(self.image, (px-offsetx, py-offsety))

    def __str__(self):
        return f"AUTO,{self.x},{self.y},{self.mapchip},{''.join(self.sequence)},{self.type}"

#                                                                                                                              
#   ,ad8888ba,  88                                           88888888ba                                                        
#  d8"'    `"8b 88                                           88      "8b             ,d                                        
# d8'           88                                           88      ,8P             88                                        
# 88            88,dPPYba,  ,adPPYYba, 8b,dPPYba, ,adPPYYba, 88aaaaaa8P' ,adPPYba, MM88MMM 88       88 8b,dPPYba, 8b,dPPYba,   
# 88            88P'    "8a ""     `Y8 88P'   "Y8 ""     `Y8 88""""88'  a8P_____88   88    88       88 88P'   "Y8 88P'   `"8a  
# Y8,           88       88 ,adPPPPP88 88         ,adPPPPP88 88    `8b  8PP"""""""   88    88       88 88         88       88  
#  Y8a.    .a8P 88       88 88,    ,88 88         88,    ,88 88     `8b "8b,   ,aa   88,   "8a,   ,a88 88         88       88  
#   `"Y8888Y"'  88       88 `"8bbdP"Y8 88         `"8bbdP"Y8 88      `8b `"Ybbd8"'   "Y888  `"YbbdP'Y8 88         88       88  
#                                                                                                                              
#                                                                                                                              
# 

class CharaReturn(Character):
    '''戻り値用のキャラクター'''
    def __init__(self, name, pos, direction, movetype, message, fromTo, func, funcWarp, exps, mapname):
        super().__init__(name, pos, direction, movetype, message)
        self.fromTo: list[int] = fromTo
        self.func: str = func
        self.funcWarp: dict = funcWarp
        self.exps = exps
        self.funcInfoWindow = FuncInfoWindow(self.funcWarp, (mapname, self.func, fromTo[0]))
        
    def __str__(self):
        return f"CHARARETURN,{self.name:s},{self.x:d},{self.y:d},"\
            f"{self.direction:d},{self.movetype:d},{self.message:s},{self.line:d}"
                                                                                                                                                                                                       
#   ,ad8888ba,  88                                             ,ad8888ba,  88                                88         ,ad8888ba,                                   88 88         88                          
#  d8"'    `"8b 88                                            d8"'    `"8b 88                                88        d8"'    `"8b                                  88 ""   ,d    ""                          
# d8'           88                                           d8'           88                                88       d8'                                            88      88                                
# 88            88,dPPYba,  ,adPPYYba, 8b,dPPYba, ,adPPYYba, 88            88,dPPYba,   ,adPPYba,  ,adPPYba, 88   ,d8 88             ,adPPYba,  8b,dPPYba,   ,adPPYb,88 88 MM88MMM 88  ,adPPYba,  8b,dPPYba,   
# 88            88P'    "8a ""     `Y8 88P'   "Y8 ""     `Y8 88            88P'    "8a a8P_____88 a8"     "" 88 ,a8"  88            a8"     "8a 88P'   `"8a a8"    `Y88 88   88    88 a8"     "8a 88P'   `"8a  
# Y8,           88       88 ,adPPPPP88 88         ,adPPPPP88 Y8,           88       88 8PP""""""" 8b         8888[    Y8,           8b       d8 88       88 8b       88 88   88    88 8b       d8 88       88  
#  Y8a.    .a8P 88       88 88,    ,88 88         88,    ,88  Y8a.    .a8P 88       88 "8b,   ,aa "8a,   ,aa 88`"Yba,  Y8a.    .a8P "8a,   ,a8" 88       88 "8a,   ,d88 88   88,   88 "8a,   ,a8" 88       88  
#   `"Y8888Y"'  88       88 `"8bbdP"Y8 88         `"8bbdP"Y8   `"Y8888Y"'  88       88  `"Ybbd8"'  `"Ybbd8"' 88   `Y8a  `"Y8888Y"'   `"YbbdP"'  88       88  `"8bbdP"Y8 88   "Y888 88  `"YbbdP"'  88       88  
                                                                                                                                                                                                                                                                                                                                                                                                           
class CharaCheckCondition(Character):
    '''条件文を確認するキャラクター'''
    def __init__(self, name, pos, direction, move_direction, movetype, message, type, fromTo, func, funcWarp, funcExps, detail, avoiding, mapname):
        super().__init__(name, pos, direction, movetype, message)
        self.initial_direction = direction
        self.move_direction = move_direction
        self.back_direction = None
        self.type = type
        self.fromTo = fromTo
        self.func = func
        self.funcWarp = funcWarp
        self.funcExps = funcExps
        self.detail: str = detail
        self.avoiding = avoiding
        self.funcInfoWindow = FuncInfoWindow(self.funcWarp, (mapname, self.func, fromTo[0]), detail)

    def update(self, mymap: Map):
        """キャラクター状態を更新する。
        mapは移動可能かの判定に必要。"""
        # プレイヤーの移動処理
        if self.moving:
            # ピクセル移動中ならマスにきっちり収まるまで移動を続ける
            self.rect.move_ip(self.vx, self.vy)
            if self.rect.left % GS == 0 and self.rect.top % GS == 0:  # マスにおさまったら移動完了
                if self.avoiding is True:
                    if self.direction == DOWN:
                        self.direction = UP
                    elif self.direction == LEFT:
                        self.direction = RIGHT
                    elif self.direction == RIGHT:
                        self.direction = LEFT
                    else:
                        self.direction = DOWN
                else:
                    self.direction = self.initial_direction
                self.moving = False
                self.x = self.rect.left // GS
                self.y = self.rect.top // GS
        # キャラクターアニメーション（frameに応じて描画イメージを切り替える）
        self.frame += 1
        self.image = self.images[self.name][self.direction *
                                            4 + (self.frame // self.animcycle  % 4)]
        
    def set_checked(self):
        self.avoiding = True
        self.moving = True
        if self.move_direction == DOWN:
            self.vx, self.vy = 0, self.speed
            self.direction = DOWN
            return {"x": self.x, "y": self.y, "avoiding_x": self.x, "avoiding_y": self.y+1, "avoiding_dir": UP}
        elif self.move_direction == LEFT:
            self.vx, self.vy = -self.speed, 0
            self.direction = LEFT
            return {"x": self.x, "y": self.y, "avoiding_x": self.x-1, "avoiding_y": self.y, "avoiding_dir": RIGHT}
        elif self.move_direction == RIGHT:
            self.vx, self.vy = self.speed, 0
            self.direction = RIGHT
            return {"x": self.x, "y": self.y, "avoiding_x": self.x+1, "avoiding_y": self.y, "avoiding_dir": LEFT}
        else:
            self.vx, self.vy = 0, -self.speed
            self.direction = UP
            return {"x": self.x, "y": self.y, "avoiding_x": self.x, "avoiding_y": self.y-1, "avoiding_dir": DOWN}

    def back_to_init_pos(self):
        self.avoiding = False
        self.moving = True
        if self.direction == DOWN:
            self.vx, self.vy = 0, self.speed
        elif self.direction == LEFT:
            self.vx, self.vy = -self.speed, 0
        elif self.direction == RIGHT:
            self.vx, self.vy = self.speed, 0
        else:
            self.vx, self.vy = 0, -self.speed
                                                                                                                                                             
#   ,ad8888ba,  88                                           88888888888                                                                   88                          
#  d8"'    `"8b 88                                           88                                                                            ""                          
# d8'           88                                           88                                                                                                        
# 88            88,dPPYba,  ,adPPYYba, 8b,dPPYba, ,adPPYYba, 88aaaaa     8b,     ,d8 8b,dPPYba,  8b,dPPYba,  ,adPPYba, ,adPPYba, ,adPPYba, 88  ,adPPYba,  8b,dPPYba,   
# 88            88P'    "8a ""     `Y8 88P'   "Y8 ""     `Y8 88"""""      `Y8, ,8P'  88P'    "8a 88P'   "Y8 a8P_____88 I8[    "" I8[    "" 88 a8"     "8a 88P'   `"8a  
# Y8,           88       88 ,adPPPPP88 88         ,adPPPPP88 88             )888(    88       d8 88         8PP"""""""  `"Y8ba,   `"Y8ba,  88 8b       d8 88       88  
#  Y8a.    .a8P 88       88 88,    ,88 88         88,    ,88 88           ,d8" "8b,  88b,   ,a8" 88         "8b,   ,aa aa    ]8I aa    ]8I 88 "8a,   ,a8" 88       88  
#   `"Y8888Y"'  88       88 `"8bbdP"Y8 88         `"8bbdP"Y8 88888888888 8P'     `Y8 88`YbbdP"'  88          `"Ybbd8"' `"YbbdP"' `"YbbdP"' 88  `"YbbdP"'  88       88  
#                                                                                    88                                                                                
#                                                                                    88                                                                                

class CharaExpression(Character):
    def __init__(self, name, pos, direction, movetype, message, func, exps_dict, mapname):
        super().__init__(name, pos, direction, movetype, message)
        self.func = func
        self.exps = exps_dict
        self.linenum = None
        self.funcInfoWindow_dict: dict[str, FuncInfoWindow] = {line: FuncInfoWindow(exp["funcWarp"], (mapname, self.func, int(line))) for line, exp in exps_dict.items()}

    def __str__(self):
        return f"CHARAEXPRESSION,{self.name:s},{self.x:d},{self.y:d},"\
            f"{self.direction:d},{self.movetype:d},{self.message:s},"

#                                                                                                         
# 88b           d88                                    88888888888                                        
# 888b         d888                                    88                                          ,d     
# 88`8b       d8'88                                    88                                          88     
# 88 `8b     d8' 88  ,adPPYba,  8b       d8  ,adPPYba, 88aaaaa 8b       d8  ,adPPYba, 8b,dPPYba, MM88MMM  
# 88  `8b   d8'  88 a8"     "8a `8b     d8' a8P_____88 88""""" `8b     d8' a8P_____88 88P'   `"8a  88     
# 88   `8b d8'   88 8b       d8  `8b   d8'  8PP""""""" 88       `8b   d8'  8PP""""""" 88       88  88     
# 88    `888'    88 "8a,   ,a8"   `8b,d8'   "8b,   ,aa 88        `8b,d8'   "8b,   ,aa 88       88  88,    
# 88     `8'     88  `"YbbdP"'      "8"      `"Ybbd8"' 88888888888 "8"      `"Ybbd8"' 88       88  "Y888  
#                                                                                                         
#                                                                                                         
# 

class MoveEvent():
    """移動イベント"""
    def __init__(self, pos, mapchip, dest_map, type, fromTo, dest_pos, func, exps, funcWarp, funcExps, detail, mapname):
        self.x, self.y = pos[0], pos[1]  # イベント座標
        self.mapchip = mapchip  # マップチップ
        self.dest_map = dest_map  # 移動先マップ名
        self.type: str = type
        self.fromTo: list[int | None] = fromTo
        self.dest_x, self.dest_y = dest_pos[0], dest_pos[1]  # 移動先座標
        self.func = func
        self.exps = exps
        self.funcWarp = funcWarp
        self.funcExps = funcExps
        self.detail: str = detail
        self.image = Map.images[self.mapchip]
        self.rect = self.image.get_rect(topleft=(self.x*GS, self.y*GS))
        self.funcInfoWindow = FuncInfoWindow(self.funcWarp, (mapname, self.func, fromTo[0]), detail)

    def draw(self, screen, offset):
        """オフセットを考慮してイベントを描画"""
        offsetx, offsety = offset
        px = self.rect.topleft[0]
        py = self.rect.topleft[1]
        screen.blit(self.image, (px-offsetx, py-offsety))

    def __str__(self):
        return f"MOVE,{self.x},{self.y},{self.mapchip},{self.dest_map},{self.dest_x},{self.dest_y}"
    


# 88888888888                                88               ad88          I8,        8        ,8I 88                      88                                 
# 88                                         88              d8"            `8b       d8b       d8' ""                      88                                 
# 88                                         88              88              "8,     ,8"8,     ,8"                          88                                 
# 88aaaaa 88       88 8b,dPPYba,   ,adPPYba, 88 8b,dPPYba, MM88MMM ,adPPYba,  Y8     8P Y8     8P   88 8b,dPPYba,   ,adPPYb,88  ,adPPYba,  8b      db      d8  
# 88""""" 88       88 88P'   `"8a a8"     "" 88 88P'   `"8a  88   a8"     "8a `8b   d8' `8b   d8'   88 88P'   `"8a a8"    `Y88 a8"     "8a `8b    d88b    d8'  
# 88      88       88 88       88 8b         88 88       88  88   8b       d8  `8a a8'   `8a a8'    88 88       88 8b       88 8b       d8  `8b  d8'`8b  d8'   
# 88      "8a,   ,a88 88       88 "8a,   ,aa 88 88       88  88   "8a,   ,a8"   `8a8'     `8a8'     88 88       88 "8a,   ,d88 "8a,   ,a8"   `8bd8'  `8bd8'    
# 88       `"YbbdP'Y8 88       88  `"Ybbd8"' 88 88       88  88    `"YbbdP"'     `8'       `8'      88 88       88  `"8bbdP"Y8  `"YbbdP"'      YP      YP      

class FuncInfoWindow(Window):
    """関数の遷移歴を表示するウィンドウ"""
    FONT_SIZE = 20
    NOT_CHECKED_COLOR = (255, 0, 0)
    SKIPPED_CHECK_COLOR = (0, 0, 255)
    CHECKED_COLOR = (0, 255, 0)
    TEXT_COLOR = (255, 255, 255, 255)
    LINE_COLOR = (255, 255, 255, 255)
    CYAN = Color(100, 248, 248, 255)

    class Detail:
        CYAN = Color(100, 248, 248, 255)
        RED = Color(255, 0, 0, 255)

        def __init__(self, detail: dict, font: pygame.freetype.Font):
            self.hoverLink_info_list: list[tuple[pygame.Surface, pygame.Rect]] = []
            self.baseComment_info_list: list[tuple[pygame.Surface, pygame.Rect]] = []
            self.hoverComment_list = detail["hover"]

            x, y = 50, 10
            split_detail: list[str] = detail["detail"].split('?')
            for i, detail in enumerate(split_detail):
                baseComment_surf, _ = font.render(detail, self.CYAN)
                baseComment_rect = baseComment_surf.get_rect(topleft=(x, y))
                self.baseComment_info_list.append((baseComment_surf, baseComment_rect))
                if i + 1 != len(split_detail):
                    x = baseComment_rect.right
                    hoverLink_surf, _ = font.render("条件", self.RED)
                    hoverLink_rect = hoverLink_surf.get_rect(topleft=(x, y))
                    self.hoverLink_info_list.append((hoverLink_surf, hoverLink_rect))
                    x = hoverLink_rect.right

        def draw(self, surface: pygame.Surface):
            for baseComment_info in self.baseComment_info_list:
                surface.blit(baseComment_info[0], baseComment_info[1])
            for hoverLink_info in self.hoverLink_info_list:
                surface.blit(hoverLink_info[0], hoverLink_info[1])

    def __init__(self, funcs, warpPos, detail: dict | None = None):
        Window.__init__(self, Rect(SCR_WIDTH // 5 + 10, 10, SCR_WIDTH // 5 * 4 - MIN_MAP_SIZE - 20, MIN_MAP_SIZE))
        # 日本語対応フォントの指定
        self.font = pygame.freetype.Font(FONT_DIR + FONT_NAME, self.FONT_SIZE)
        self.funcs: list[dict] = funcs
        self.warpPos = warpPos
        self.detail = self.Detail(detail, self.font) if detail else None
        self.left_arrow, _ = self.font.render("◀", (255, 255, 255, 255))
        self.right_arrow, _ = self.font.render("▶", (255, 255, 255, 255))
        self.left_rect = self.left_arrow.get_rect(center=(20, 140))
        self.right_rect = self.right_arrow.get_rect(center=(476, 140))
        self.show()

    def draw_string(self, x, y, string, color):
        """文字列出力"""
        surf, rect = self.font.render(string, color)
        self.surface.blit(surf, (x, y+(self.FONT_SIZE)-rect[3]))

    def draw_arrow(self, surface, color, start, end, width=3, arrow_size=10):
        # 直線を描画
        pygame.draw.line(surface, color, start, end, width)

        # ベクトル計算
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        angle = math.atan2(dy, dx)

        # 矢印の先端（三角形の座標）
        x1 = end[0] - arrow_size * math.cos(angle - math.pi / 6)
        y1 = end[1] - arrow_size * math.sin(angle - math.pi / 6)
        x2 = end[0] - arrow_size * math.cos(angle + math.pi / 6)
        y2 = end[1] - arrow_size * math.sin(angle + math.pi / 6)

        pygame.draw.polygon(surface, color, [(end[0], end[1]), (x1, y1), (x2, y2)])

    def draw(self, screen):
        if not (self.is_visible and (len(self.funcs) or self.detail)):
            return
        
        Window.draw(self)
        x_offset = 50
        y_offset = 10
        if self.detail:
            self.detail.draw(self.surface)
            y_offset += self.FONT_SIZE + 10
        checkedFuncs = PLAYER.checkedFuncs.get(self.warpPos, [])
        func_pos_list: list[tuple[int, int]] = []
        for i, func in enumerate(self.funcs):
            text = f"{func['name']} : {checkedFuncs[i][1]}" if i < len(checkedFuncs) and checkedFuncs[i][2] else func["name"]
            text_width = self.font.get_rect(text).width
            # 引数に関数が含まれる場合は段落をつけて関係を描画する
            x_pos_list = []
            y_pos_list = []
            for children in func['children']:
                for _ in children:
                    func_pos = func_pos_list.pop(0)
                    x_pos_list.append(func_pos[0])
                    y_pos_list.append(func_pos[1])
            x_pos = max(x_pos_list) + 60 if len(x_pos_list) else x_offset
            y_pos = sum(y_pos_list) // len(y_pos_list) if len(y_pos_list) else y_offset

            # 関数と関数(関数とその引数に含まれる関数)を繋げる矢印を描画する
            for x_pos_index, x_pos_start in enumerate(x_pos_list):
                self.draw_arrow(self.surface, self.LINE_COLOR, (x_pos_start+10, y_pos_list[x_pos_index]+(self.FONT_SIZE+2)//2), (x_pos-10, y_pos+(self.FONT_SIZE+2)//2))

            # 関数が遷移済みかどうかで背景色を変える
            if i < len(checkedFuncs):
                if checkedFuncs[i][2]:
                    highlightColor = self.CHECKED_COLOR
                else:
                    highlightColor = self.SKIPPED_CHECK_COLOR
            else:
                highlightColor = self.NOT_CHECKED_COLOR
            pygame.draw.rect(self.surface, highlightColor, pygame.Rect(x_pos, y_pos, text_width, self.FONT_SIZE + 4))
            
            # 関数名を描画する
            self.draw_string(x_pos, y_pos+2, text, self.TEXT_COLOR)
            # 現在の関数と次の関数に矢印を繋げるために先に登録しておく
            func_pos_list.append((x_pos+text_width, y_pos))
            # 引数に関数がない時は現在の関数の下に次の関数を描画する
            if len(y_pos_list) == 0:
                y_offset += self.FONT_SIZE + 10

        self.surface.blit(self.left_arrow, self.left_rect)
        self.surface.blit(self.right_arrow, self.right_rect)

        Window.blit(self, screen)

    def isCursorInWindow(self, pos: tuple[int, int]):
        if MSGWND.is_visible:
            return False
            
        local_pos = (pos[0] - self.x, pos[1] - self.y)
        if self.left_rect.collidepoint(local_pos):
            shift = -1
        elif self.right_rect.collidepoint(local_pos):
            shift = 1
        elif self.detail:
            for i, hoverLink_info in enumerate(self.detail.hoverLink_info_list):
                if hoverLink_info[1].collidepoint(local_pos):
                    MSGWND.set(self.detail.hoverComment_list[i])
                    return True
        else:
            return False

        if len(PLAYER.funcInfoWindow_list) != 1:
            self.funcInfoWindowIndex = (self.funcInfoWindowIndex + shift) % len(PLAYER.funcInfoWindow_list)
        else:
            self.funcInfoWindowIndex = 0

        return True

#                                                                                                                                 
# 88888888ba  88                                                               88888888888                                        
# 88      "8b 88                                                         ,d    88                                          ,d     
# 88      ,8P 88                                                         88    88                                          88     
# 88aaaaaa8P' 88 ,adPPYYba,  ,adPPYba,  ,adPPYba, ,adPPYba,  ,adPPYba, MM88MMM 88aaaaa 8b       d8  ,adPPYba, 8b,dPPYba, MM88MMM  
# 88""""""'   88 ""     `Y8 a8"     "" a8P_____88 I8[    "" a8P_____88   88    88""""" `8b     d8' a8P_____88 88P'   `"8a  88     
# 88          88 ,adPPPPP88 8b         8PP"""""""  `"Y8ba,  8PP"""""""   88    88       `8b   d8'  8PP""""""" 88       88  88     
# 88          88 88,    ,88 "8a,   ,aa "8b,   ,aa aa    ]8I "8b,   ,aa   88,   88        `8b,d8'   "8b,   ,aa 88       88  88,    
# 88          88 `"8bbdP"Y8  `"Ybbd8"'  `"Ybbd8"' `"YbbdP"'  `"Ybbd8"'   "Y888 88888888888 "8"      `"Ybbd8"' 88       88  "Y888  
#                                                                                                                                 
#                                                                                                                                 
# 

class PlacesetEvent():
    """場所セットイベント"""

    def __init__(self, pos, mapchip, place_label):
        self.x, self.y = pos[0], pos[1]  # イベント座標
        self.mapchip = mapchip  # マップチップ
        self.place_label = place_label  # 移動先マップ名
        self.image = Map.images[self.mapchip]
        self.rect = self.image.get_rect(topleft=(self.x*GS, self.y*GS))

    def draw(self, screen, offset):
        """オフセットを考慮してイベントを描画"""
        offsetx, offsety = offset
        px = self.rect.topleft[0]
        py = self.rect.topleft[1]
        screen.blit(self.image, (px-offsetx, py-offsety))

    def __str__(self):
        return f"PLACESET,{self.x},{self.y},{self.mapchip},{self.place_label}"


#                                                                                       
# 888888888888                                                                          
#      88                                                                               
#      88                                                                               
#      88 8b,dPPYba,  ,adPPYba, ,adPPYYba, ,adPPYba, 88       88 8b,dPPYba,  ,adPPYba,  
#      88 88P'   "Y8 a8P_____88 ""     `Y8 I8[    "" 88       88 88P'   "Y8 a8P_____88  
#      88 88         8PP""""""" ,adPPPPP88  `"Y8ba,  88       88 88         8PP"""""""  
#      88 88         "8b,   ,aa 88,    ,88 aa    ]8I "8a,   ,a88 88         "8b,   ,aa  
#      88 88          `"Ybbd8"' `"8bbdP"Y8 `"YbbdP"'  `"YbbdP'Y8 88          `"Ybbd8"'  
#                                                                                       
#                                                                                       
# 

class Treasure():
    """宝箱"""
    FONT_SIZE = 16

    def __init__(self, pos, item, exps, vartype, func, fromTo, funcWarp, mapname):
        self.font = pygame.freetype.SysFont("monospace", self.FONT_SIZE)
        self.x, self.y = pos[0], pos[1]  # 宝箱座標
        self.mapchip = 138  # 宝箱は138
        self.image = Map.images[self.mapchip]
        self.rect = self.image.get_rect(topleft=(self.x*GS, self.y*GS))
        self.item = item  # アイテム名
        self.exps = exps # アイテムの値の設定(計算)がどのように行われたかを説明するコメントや計算式を格納
        self.vartype = vartype # アイテムの型
        self.func = func
        self.fromTo = fromTo # 宝箱を開けるタイミング
        self.funcWarp = funcWarp # 関数による遷移
        self.funcInfoWindow = FuncInfoWindow(self.funcWarp, (mapname, self.func, fromTo[0]))

    def open(self, data: dict, line: int, exps: list[str]):
        """宝箱をあける"""
        # sounds["treasure"].play()
        # アイテムを追加する処理
        item = Item(self.item, line, data, exps, self.vartype)
        PLAYER.itembag.items[-1].append(item)

    def draw(self, screen, offset):
        """オフセットを考慮してイベントを描画"""
        offsetx, offsety = offset
        px = self.rect.topleft[0]
        py = self.rect.topleft[1]
        screen.blit(self.image, (px-offsetx, py-offsety))

        # アイテム名を描画（宝箱の上に）
        if self.item and PLAYER.x == self.x and PLAYER.y == self.y or PLAYER.itemNameShow:
            # 文字色（白）とアルファ付き背景（例: 半透明黒）
            text_surface, text_rect = self.font.render(
                self.item, 
                fgcolor=(255, 255, 255),         # 文字色：白
                bgcolor=(0, 0, 0, 128)           # 背景色：半透明黒（RGBA）
            )

            # パディング
            padding = 4
            # アイテム名表示枠の矩形
            bg_rect = pygame.Rect(
                text_rect.left - padding,
                text_rect.top - padding,
                text_rect.width + 2 * padding,
                text_rect.height + 2 * padding
            )

            # アイテム名表示枠をアイテムに対して中央上に寄せる
            bg_rect.centerx = self.rect.centerx - offsetx
            bg_rect.bottom = self.rect.top - offsety
            # テキストを枠の中央に配置
            text_rect.center = bg_rect.center

            # 背景を描画（半透明黒）
            pygame.draw.rect(screen, (0, 0, 0, 128), bg_rect)

            # テキストを描画
            screen.blit(text_surface, text_rect)

    def __str__(self):
        return f"TREASURE,{self.x},{self.y},{self.item}"

#                                         
#  ad88888ba  88                          
# d8"     "8b ""                          
# Y8,                                     
# `Y8aaaaa,   88  ,adPPYb,d8 8b,dPPYba,   
#   `"""""8b, 88 a8"    `Y88 88P'   `"8a  
#         `8b 88 8b       88 88       88  
# Y8a     a8P 88 "8a,   ,d88 88       88  
#  "Y88888P"  88  `"YbbdP"Y8 88       88  
#                 aa,    ,88              
#                  "Y8bbdP"               
# 

class Sign():
    """看板"""
    FONT_HEIGHT = 18
    WHITE = Color(255, 255, 255, 255)

    def __init__(self, pos, text):
        self.mapchip = 691
        self.mapchip_left = 691
        self.mapchip_right = 693
        self.mapchip_center = 692
        self.x, self.y = pos[0], pos[1]  # ドア座標
        self.text = text  # アイテム名
        self.myfont = pygame.freetype.Font(
            FONT_DIR + FONT_NAME, self.FONT_HEIGHT)

    def draw(self, screen, offset):
        """オフセットを考慮して看板を描画"""
        surf, rect = self.myfont.render(self.text, self.WHITE)
        panels = rect.width // 32 - 1
        #print(rect.width,panels)
        if panels < 0:
            panels = 0
        self._draw(screen,offset,0,0,self.mapchip_left)
        for i in range(panels):
            self._draw(screen,offset,1 + i,0,self.mapchip_center)
        self._draw(screen,offset,panels + 1,0,self.mapchip_right)
        offsetx, offsety = offset
        rect = surf.get_rect(topleft=((self.x)*GS, (self.y)*GS))
        px = rect.topleft[0]
        py = rect.topleft[1] + 10
        screen.blit(surf, (px-offsetx, py-offsety))

    def _draw(self, screen, offset, dx, dy, mchip):
        """mchipで指定される看板部品をオフセットを考慮して描画"""
        image = Map.images[mchip]
        offsetx, offsety = offset
        rect = image.get_rect(topleft=((self.x+dx)*GS, (self.y+dy)*GS))
        px = rect.topleft[0]
        py = rect.topleft[1]
        screen.blit(image, (px-offsetx, py-offsety))

    def __str__(self):
        return f"SIGN,{self.x},{self.y},{self.text}"

#                                                   
# 88888888ba,                                       
# 88      `"8b                                      
# 88        `8b                                     
# 88         88  ,adPPYba,   ,adPPYba,  8b,dPPYba,  
# 88         88 a8"     "8a a8"     "8a 88P'   "Y8  
# 88         8P 8b       d8 8b       d8 88          
# 88      .a8P  "8a,   ,a8" "8a,   ,a8" 88          
# 88888888Y"'    `"YbbdP"'   `"YbbdP"'  88          
#                                                   
#                                                   
# 

class Door():
    """ドア"""
    def __init__(self, pos, name):
        self.mapchip = 678
        self.mapchip_list = [[678,678,679,680,681,682],[637,638,639,640,641,642]]
        self.status = 0 # close
        self.x, self.y = pos[0], pos[1]  # ドア座標
        self.doorname = name  # アイテム名

    def name(self):
        """名前を返す"""
        return self.doorname

    def open(self):
        """ドアをあける"""
        self.status = 1 # open

    def close(self):
        """ドアを閉める"""
        self.status = 0 # close

    def draw(self, screen, offset):
        """オフセットを考慮してドアを描画"""
        for i,mchip in enumerate(self.mapchip_list[self.status]):
            self._draw(screen,offset,i%2,i//2,mchip)

    def _draw(self, screen, offset, dx, dy, mchip):
        """mchipで指定されるドア部品をオフセットを考慮して描画"""
        image = Map.images[mchip]
        offsetx, offsety = offset
        rect = image.get_rect(topleft=((self.x+dx)*GS, (self.y+dy)*GS))
        px = rect.topleft[0]
        py = rect.topleft[1]
        screen.blit(image, (px-offsetx, py-offsety))

    def __str__(self):
        return f"DOOR,{self.x},{self.y},{self.doorname}"

class SmallDoor(Door):
    """小さいドアクラス"""
    def __init__(self, pos, name, direction):
        self.mapchip = 27
        self.mapchip_list = [27,688]
        self.status = 0 # close
        self.x, self.y = pos[0], pos[1]  # ドア座標
        self.doorname = str(name)  # ドア名
        self.direction = direction
        self.key = ""

    def draw(self, screen, offset):
        """オフセットを考慮してイベントを描画"""
        offsetx, offsety = offset
        image = Map.images[self.mapchip_list[self.status]]
        rect = image.get_rect(topleft=(self.x*GS, self.y*GS))
        px = rect.topleft[0]
        py = rect.topleft[1]
        screen.blit(image, (px-offsetx, py-offsety))

    def __str__(self):
        return f"SDOOR,{self.x},{self.y},{self.doorname}"

#                                                
# 88          88             88                  
# 88          ""             88           ,d     
# 88                         88           88     
# 88          88  ,adPPYb,d8 88,dPPYba, MM88MMM  
# 88          88 a8"    `Y88 88P'    "8a  88     
# 88          88 8b       88 88       88  88     
# 88          88 "8a,   ,d88 88       88  88,    
# 88888888888 88  `"YbbdP"Y8 88       88  "Y888  
#                 aa,    ,88                     
#                  "Y8bbdP"                      
# 

class Light():
    """光源"""
    def __init__(self, pos, room):
        self.x, self.y = pos[0], pos[1]  # 光源座標
        self.mapchip = 1  # 光源は1
        self.surface = pygame.Surface((160, 160), pygame.SRCALPHA)
        self.image = Map.images[self.mapchip]
        self.rect = self.surface.get_rect(topleft=(self.x*GS-80, self.y*GS-80))
        self.lightroom = room  # 部屋名

    def room(self):
        """部屋名"""
        return self.lightroom

    def draw(self, screen, color, offset):
        """オフセットを考慮し光を描画"""
        offsetx, offsety = offset
        px = self.rect.topleft[0]
        py = self.rect.topleft[1]
#        screen.blit(self.image, (px-offsetx, py-offsety))
        pygame.draw.circle(self.surface,Color(color.r,color.g,color.b,color.a//6),
                           (80,80),80,0)
        pygame.draw.circle(self.surface,Color(color.r,color.g,color.b,color.a//4),
                           (80,80),70,0)
        pygame.draw.circle(self.surface,Color(color.r,color.g,color.b,color.a//2),
                           (80,80),60,0)
        pygame.draw.circle(self.surface,Color(0,0,0,color.a),(80,80),48,0)
        screen.blit(self.surface, (px-offsetx+15, py-offsety+15),
                    special_flags=BLEND_RGBA_SUB)

    def __str__(self):
        return f"ZLIGHT,{self.x},{self.y},{self.lightroom}"


#                                                              
#   ,ad8888ba,   88          88                                
#  d8"'    `"8b  88          ""                         ,d     
# d8'        `8b 88                                     88     
# 88          88 88,dPPYba,  88  ,adPPYba,  ,adPPYba, MM88MMM  
# 88          88 88P'    "8a 88 a8P_____88 a8"     ""   88     
# Y8,        ,8P 88       d8 88 8PP""""""" 8b           88     
#  Y8a.    .a8P  88b,   ,a8" 88 "8b,   ,aa "8a,   ,aa   88,    
#   `"Y8888Y"'   8Y"Ybbd8"'  88  `"Ybbd8"'  `"Ybbd8"'   "Y888  
#                           ,88                                
#                         888P"                                
# 

class Object:
    """一般オブジェクト"""

    def __init__(self, pos, mapchip):
        self.x, self.y = pos[0], pos[1]
        self.mapchip = mapchip
        self.image = Map.images[self.mapchip]
        self.rect = self.image.get_rect(topleft=(self.x*GS, self.y*GS))

    def draw(self, screen, offset):
        """オフセットを考慮してイベントを描画"""
        offsetx, offsety = offset
        px = self.rect.topleft[0]
        py = self.rect.topleft[1]
        screen.blit(self.image, (px-offsetx, py-offsety))

    def pos(self):
        """座標を返す"""
        return (self.x, self.y)

    def __str__(self):
        return f"OBJECT,{self.x},{self.y},{self.mapchip}"

#                                          
# 88                                       
# 88   ,d                                  
# 88   88                                  
# 88 MM88MMM ,adPPYba, 88,dPYba,,adPYba,   
# 88   88   a8P_____88 88P'   "88"    "8a  
# 88   88   8PP""""""" 88      88      88  
# 88   88,  "8b,   ,aa 88      88      88  
# 88   "Y888 `"Ybbd8"' 88      88      88  
#                                          
#                                          
#

class Item:
    """アイテム (配列や構造体、ポインタにも対応できるようにする)"""
    def __init__(self, name: str, line: int, data: dict, exps: dict, vartype: str):
        self.name = str(name)
        self.line = line
        self.index_exps = exps.get('indexes', None)
        ITEMWND.is_inAction = True
        self.itemvalue: ItemValue = ItemValue.from_dict(data, exps=exps["values"])
        self.vartype: str = vartype

    def get_value(self):
        """値を返す"""
        return self.itemvalue

    def set_value(self, vals: dict):
        """値をセット"""
        path: list[str] = vals["path"]
        temp_itemvalue = self.itemvalue
        while len(path) != 0:
            temp_itemvalue = temp_itemvalue.children[path.pop(0)]
        temp_itemvalue.value = vals["value"]

    def set_exps(self, path: list[str], comments: list[str]):
        """計算コメントをセット"""
        temp_itemvalue = self.itemvalue
        while len(path) != 0:
            temp_itemvalue = temp_itemvalue.children[path.pop(0)]
        temp_itemvalue.changed_exps = comments

    def update_value(self, data: dict):
        ITEMWND.is_inAction = True
        self.itemvalue = ItemValue.from_dict(data)

    def remove_itemvalue_exps(self):
        self.index_exps = None
        self.itemvalue.remove_exps()
                                                                                  
# 88                                   8b           d8          88                         
# 88   ,d                              `8b         d8'          88                         
# 88   88                               `8b       d8'           88                         
# 88 MM88MMM ,adPPYba, 88,dPYba,,adPYba, `8b     d8' ,adPPYYba, 88 88       88  ,adPPYba,  
# 88   88   a8P_____88 88P'   "88"    "8a `8b   d8'  ""     `Y8 88 88       88 a8P_____88  
# 88   88   8PP""""""" 88      88      88  `8b d8'   ,adPPPPP88 88 88       88 8PP"""""""  
# 88   88,  "8b,   ,aa 88      88      88   `888'    88,    ,88 88 "8a,   ,a88 "8b,   ,aa  
# 88   "Y888 `"Ybbd8"' 88      88      88    `8'     `"8bbdP"Y8 88  `"YbbdP'Y8  `"Ybbd8"'  
                                                                                         
class ItemValue:
    def __init__(self, value: str | None, exps: list[str] | None, children: dict[str | int, "ItemValue"]):
        self.value = value
        self.is_open = True if children else None
        self.declared_exps = exps
        self.changed_exps = None
        self.children = children

    @classmethod
    def from_dict(cls, data: dict, exps: dict | list[str] | None = None) -> "ItemValue":
        value: str | None = data["value"]
        itemvalue_exps: list[str] = exps if isinstance(exps, list) else None
        children_dict: dict[str | int, dict] = data["children"]
        children = {index: cls.from_dict(v, exps=exps.get(f"\"{index}\"", None) if isinstance(exps, dict) else None) for index, v in children_dict.items()}
        return cls(value, itemvalue_exps, children)
    
    def remove_exps(self):
        self.declared_exps = None
        self.changed_exps = None
        for itemvalue in self.children.values():
            itemvalue.remove_exps()

#                                                                             
# 88                                      88888888ba                          
# 88   ,d                                 88      "8b                         
# 88   88                                 88      ,8P                         
# 88 MM88MMM ,adPPYba, 88,dPYba,,adPYba,  88aaaaaa8P' ,adPPYYba,  ,adPPYb,d8  
# 88   88   a8P_____88 88P'   "88"    "8a 88""""""8b, ""     `Y8 a8"    `Y88  
# 88   88   8PP""""""" 88      88      88 88      `8b ,adPPPPP88 8b       88  
# 88   88,  "8b,   ,aa 88      88      88 88      a8P 88,    ,88 "8a,   ,d88  
# 88   "Y888 `"Ybbd8"' 88      88      88 88888888P"  `"8bbdP"Y8  `"YbbdP"Y8  
#                                                                 aa,    ,88  
#                                                                  "Y8bbdP"   
# 

class ItemBag:
    """アイテム袋(現在のマップによって中身を変える)"""
    def __init__(self):
        self.items: list[list[Item]] = [[]]

    def add(self, item: Item):
        """袋にアイテムを追加"""
        self.items[-1].append(item)

    def find(self, name: str, line: int) -> Item | None:
        """袋からアイテムを探す"""
        for i,n in enumerate(self.items[-1]):
            if n.name == name and n.line == line:
                return n
        return None

    def remove(self, name: str, line: int):
        """袋からアイテムを取り除く"""
        for i,n in enumerate(self.items[-1]):
            if n.name == name and n.line == line:
                return self.items[-1].pop(i)
        return None
    
    def remove_item_exps(self):
        for item in self.items[-1]:
            item.remove_itemvalue_exps()
                                                                                                                                                                                                     
#  ad88888ba                                          88888888ba                                                   I8,        8        ,8I 88                      88                                 
# d8"     "8b ,d                                      88      "8b               ,d      ,d                         `8b       d8b       d8' ""                      88                                 
# Y8,         88                                      88      ,8P               88      88                          "8,     ,8"8,     ,8"                          88                                 
# `Y8aaaaa, MM88MMM ,adPPYYba,  ,adPPYb,d8  ,adPPYba, 88aaaaaa8P' 88       88 MM88MMM MM88MMM ,adPPYba,  8b,dPPYba,  Y8     8P Y8     8P   88 8b,dPPYba,   ,adPPYb,88  ,adPPYba,  8b      db      d8  
#   `"""""8b, 88    ""     `Y8 a8"    `Y88 a8P_____88 88""""""8b, 88       88   88      88   a8"     "8a 88P'   `"8a `8b   d8' `8b   d8'   88 88P'   `"8a a8"    `Y88 a8"     "8a `8b    d88b    d8'  
#         `8b 88    ,adPPPPP88 8b       88 8PP""""""" 88      `8b 88       88   88      88   8b       d8 88       88  `8a a8'   `8a a8'    88 88       88 8b       88 8b       d8  `8b  d8'`8b  d8'   
# Y8a     a8P 88,   88,    ,88 "8a,   ,d88 "8b,   ,aa 88      a8P "8a,   ,a88   88,     88,  "8a,   ,a8" 88       88   `8a8'     `8a8'     88 88       88 "8a,   ,d88 "8a,   ,a8"   `8bd8'  `8bd8'    
#  "Y88888P"  "Y888 `"8bbdP"Y8  `"YbbdP"Y8  `"Ybbd8"' 88888888P"   `"YbbdP'Y8   "Y888   "Y888 `"YbbdP"'  88       88    `8'       `8'      88 88       88  `"8bbdP"Y8  `"YbbdP"'      YP      YP      
#                               aa,    ,88                                                                                                                                                            
#                                "Y8bbdP"                                                                                                                                                             

class StageButtonWindow:
    """ステージセレクトボタンウィンドウ"""
    code_names = ["01_int_variables", "02_scalar_operations", "03_complex_operators", "04_conditional_branch", "05_loops_and_break", "06_function_definition", "07_function_in_condition", "08_array_1d", "09_array_2d", "10_string_and_char_array", 
                  "11_string_operations", "12_struct", "13_modifiers", "14_recursion", "15_pointer", "16_array_pointer", "17_function_pointer", "18_stdio_input_output", "19_file_io", "20_memory_management"]
    SB_WIDTH = (SBW_WIDTH - 60) // 5
    SB_HEIGHT = SBW_HEIGHT // 2
    FONT_SIZE = 32
    MINI_BUTTON_FONT_SIZE = 12

    FONT_COLOR = (255, 255, 255)

    def __init__(self):
        self.rect = pygame.Rect(0, 0, SBW_WIDTH , SBW_HEIGHT)
        self.surface = pygame.Surface((self.rect[2], self.rect[3]))
        self.surface.fill((128, 128, 128))
        self.is_visible = False  # ウィンドウを表示中か？
        self.button_stages: list[StageButton] = []
        self.color_support_button_rect = pygame.Rect(self.rect.width - 220, 10, 100, 30)
        self.checking_lldb_button_rect = pygame.Rect(self.rect.width - 110, 10, 100, 30)
        self.scrollX = 0
        self.maxScrollX = (len(self.code_names) - 5) * (self.SB_WIDTH + 10)
        self.load_sb()
        self.font = pygame.freetype.Font(FONT_DIR + FONT_NAME, self.FONT_SIZE)
        self.mini_button_font = pygame.freetype.Font(FONT_DIR + FONT_NAME, self.MINI_BUTTON_FONT_SIZE)
        self.stage_selecting = True
        self.color_support = False

    def show(self):
        """ウィンドウを表示"""
        self.is_visible = True
    
    def hide(self):
        self.is_visible = False

    def load_sb(self):
        x = 10 - self.scrollX
        y = SBW_HEIGHT // 4
        self.button_stages = []
        for i, code_name in enumerate(self.code_names):
            self.button_stages.append(StageButton(code_name, i, x, y, self.SB_WIDTH, self.SB_HEIGHT))
            x += self.SB_WIDTH + 10

    def blit(self, screen):
        """blit"""
        screen.blit(self.surface, (self.rect[0], self.rect[1]))

    def draw(self, screen: pygame.Surface):
        if self.is_visible:
            self.blit(screen)
            self.font.render_to(screen, (SBW_WIDTH // 2 - self.FONT_SIZE * 3, SBW_HEIGHT // 8), "ステージ選択" if self.stage_selecting else "lldb　処理チェック", self.FONT_COLOR)
            for button in self.button_stages:
                button.draw(screen)

            # 色覚サポートのあり/なしボタン
            pygame.draw.rect(screen, (255, 255, 255) if self.color_support else (0, 0, 0), self.color_support_button_rect)
            color_support_label_surf, _ = self.mini_button_font.render("色覚サポートあり" if self.color_support else "色覚サポートなし", (0, 0, 0) if self.color_support else (255, 255, 255))
            color_support_label_rect = color_support_label_surf.get_rect(center=self.color_support_button_rect.center)
            screen.blit(color_support_label_surf, color_support_label_rect)

            # ゲームモード/デバッグモードのボタン
            pygame.draw.rect(screen, (0, 0, 255) if self.stage_selecting else (255, 0, 0), self.checking_lldb_button_rect)
            mode_change_label_surf, _ = self.mini_button_font.render("モード変更", (255, 255, 255))
            mode_change_label_rect = mode_change_label_surf.get_rect(center=self.checking_lldb_button_rect.center)
            screen.blit(mode_change_label_surf, mode_change_label_rect)

    def is_clicked(self,pos):
        for button in self.button_stages:
            if button.rect.collidepoint(pos):
                return button.code_name
            if self.color_support_button_rect.collidepoint(pos):
                return 'color support'
            if self.checking_lldb_button_rect.collidepoint(pos):
                return 'check lldb'
        return None
    
    def start_checking_lldb(self, host='localhost', port=9999, timeout=20.0, wait_timeout=10.0):
        start = time.time()
        last_error = None
        while time.time() - start < wait_timeout:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(timeout)
                self.sock.connect((host, port))
                print("[Client] 接続成功")
                break
            except (ConnectionRefusedError, OSError) as e:
                last_error = e
                time.sleep(0.1)
        else:
            print(f"[Client] 接続失敗: {last_error}")
            raise TimeoutError(f"{host}:{port} に {wait_timeout:.1f} 秒以内に接続できませんでした。")

    def step_into(self):
        self.sock.sendall(json.dumps({'step_into': True}).encode() + b'\n')  # 改行区切りで複数送信可能
        return self.receive_json()

    def receive_json(self):
        buffer = ""
        try:
            while True:
                data = self.sock.recv(1024)
                if not data:
                    break  # 接続が閉じられた
                buffer += data.decode()
                try:
                    msg = json.loads(buffer)
                    return msg["finished"]
                except json.JSONDecodeError:
                    continue  # JSONがまだ完全でないので続けて待つ
        except socket.timeout:
            print("ソケットの受信がタイムアウトしました。プログラム内の無限ループ、または処理の長さが問題だと考えられます。")
        except Exception as e:
            print(f"受信エラー: {e}")
        return False
            
    def close(self):
        self.sock.close()
        self.stage_selecting = True

                                                                                                                     
#  ad88888ba                                          88888888ba                                                      
# d8"     "8b ,d                                      88      "8b               ,d      ,d                            
# Y8,         88                                      88      ,8P               88      88                            
# `Y8aaaaa, MM88MMM ,adPPYYba,  ,adPPYb,d8  ,adPPYba, 88aaaaaa8P' 88       88 MM88MMM MM88MMM ,adPPYba,  8b,dPPYba,   
#   `"""""8b, 88    ""     `Y8 a8"    `Y88 a8P_____88 88""""""8b, 88       88   88      88   a8"     "8a 88P'   `"8a  
#         `8b 88    ,adPPPPP88 8b       88 8PP""""""" 88      `8b 88       88   88      88   8b       d8 88       88  
# Y8a     a8P 88,   88,    ,88 "8a,   ,d88 "8b,   ,aa 88      a8P "8a,   ,a88   88,     88,  "8a,   ,a8" 88       88  
#  "Y88888P"  "Y888 `"8bbdP"Y8  `"YbbdP"Y8  `"Ybbd8"' 88888888P"   `"YbbdP'Y8   "Y888   "Y888 `"YbbdP"'  88       88  
#                               aa,    ,88                                                                            
#                                "Y8bbdP"                                                                             

class StageButton:
    """ボタン"""
    BG_COLOR = (0, 0, 255)
    FONT_COLOR = (255, 255, 255)

    def __init__(self, code_name, stage_num, pos_x, pos_y, button_w, button_h):
        self.rect = pygame.Rect(pos_x, pos_y, button_w, button_h)
        self.surface = pygame.Surface((self.rect[2], self.rect[3]), pygame.SRCALPHA)
        self.code_name: str = code_name
        self.stage_num = stage_num + 1
        self.font = pygame.freetype.Font(FONT_DIR + FONT_NAME, 24)
    
    def draw(self, surface: pygame.Surface):
        pygame.draw.rect(self.surface, self.BG_COLOR, self.surface.get_rect(), border_radius=12)
        text_surf, _ = self.font.render(f"ステージ　{self.stage_num}", self.FONT_COLOR)
        text_rect = text_surf.get_rect(center=(self.rect.width // 2, self.rect.height // 2))
        self.surface.blit(text_surf, text_rect)
        surface.blit(self.surface, self.rect)

#        db                                                             88888888ba                                                   I8,        8        ,8I 88                      88                                 
#       d88b                                                            88      "8b               ,d      ,d                         `8b       d8b       d8' ""                      88                                 
#      d8'`8b                                                           88      ,8P               88      88                          "8,     ,8"8,     ,8"                          88                                 
#     d8'  `8b     8b,dPPYba, 8b,dPPYba,  ,adPPYba,  8b      db      d8 88aaaaaa8P' 88       88 MM88MMM MM88MMM ,adPPYba,  8b,dPPYba,  Y8     8P Y8     8P   88 8b,dPPYba,   ,adPPYb,88  ,adPPYba,  8b      db      d8  
#    d8YaaaaY8b    88P'   "Y8 88P'   "Y8 a8"     "8a `8b    d88b    d8' 88""""""8b, 88       88   88      88   a8"     "8a 88P'   `"8a `8b   d8' `8b   d8'   88 88P'   `"8a a8"    `Y88 a8"     "8a `8b    d88b    d8'  
#   d8""""""""8b   88         88         8b       d8  `8b  d8'`8b  d8'  88      `8b 88       88   88      88   8b       d8 88       88  `8a a8'   `8a a8'    88 88       88 8b       88 8b       d8  `8b  d8'`8b  d8'   
#  d8'        `8b  88         88         "8a,   ,a8"   `8bd8'  `8bd8'   88      a8P "8a,   ,a88   88,     88,  "8a,   ,a8" 88       88   `8a8'     `8a8'     88 88       88 "8a,   ,d88 "8a,   ,a8"   `8bd8'  `8bd8'    
# d8'          `8b 88         88          `"YbbdP"'      YP      YP     88888888P"   `"YbbdP'Y8   "Y888   "Y888 `"YbbdP"'  88       88    `8'       `8'      88 88       88  `"8bbdP"Y8  `"YbbdP"'      YP      YP      
                                                                                                                                                                                                                                                                                                                                                                                                                                      
class ArrowButtonWindow:
    """矢印ボタンウィンドウ"""
    def __init__(self):
        self.rect = pygame.Rect(SCR_WIDTH - 3*BUTTON_WIDTH, SCR_HEIGHT - 2*BUTTON_WIDTH, BUTTON_WIDTH, BUTTON_WIDTH)
        self.surface = pygame.Surface((self.rect[2], self.rect[3]), pygame.SRCALPHA)
        self.is_visible = False  # ウィンドウを表示中か？
        self.button_right = Button("arrow.png", self.rect[0] + BUTTON_WIDTH*2, self.rect[1] + BUTTON_WIDTH, 0)
        self.button_left = Button("arrow.png", self.rect[0] + 0, self.rect[1] + BUTTON_WIDTH, 180)
        self.button_up = Button("arrow.png", self.rect[0] + BUTTON_WIDTH, self.rect[1] + 0,90)
        self.button_down = Button("arrow.png", self.rect[0] + BUTTON_WIDTH, self.rect[1] + BUTTON_WIDTH,-90)
        self.button_pause = Button("pause.png", self.rect[0] + 0, self.rect[1] + 0, 0)
        self.button_return = Button("return.png", self.rect[0] + BUTTON_WIDTH*2, self.rect[1] + 0, 0)

    def blit(self,screen):
        """blit"""
        screen.blit(self.surface, (self.rect[0], self.rect[1]))
    
    def show(self):
        """ウィンドウを表示"""
        self.is_visible = True
    
    def hide(self):
        self.is_visible = False

    def draw(self,screen):
        self.button_right.draw(screen)
        self.button_left.draw(screen)
        self.button_up.draw(screen)
        self.button_down.draw(screen)
        self.button_pause.draw(screen)
        self.button_return.draw(screen)
        self.blit(screen)
    
    def is_clicked(self,pos):
        if self.button_right.rect.collidepoint(pos):
            return "right"
        elif self.button_left.rect.collidepoint(pos):
            return "left"
        elif self.button_up.rect.collidepoint(pos):
            return "up"
        elif self.button_down.rect.collidepoint(pos):
            return "down"
        elif self.button_pause.rect.collidepoint(pos):
            return "pause"
        elif self.button_return.rect.collidepoint(pos):
            return "action"
        else:
            return None
                                                 
# 88888888ba                                                      
# 88      "8b               ,d      ,d                            
# 88      ,8P               88      88                            
# 88aaaaaa8P' 88       88 MM88MMM MM88MMM ,adPPYba,  8b,dPPYba,   
# 88""""""8b, 88       88   88      88   a8"     "8a 88P'   `"8a  
# 88      `8b 88       88   88      88   8b       d8 88       88  
# 88      a8P "8a,   ,a88   88,     88,  "8a,   ,a8" 88       88  
# 88888888P"   `"YbbdP'Y8   "Y888   "Y888 `"YbbdP"'  88       88  
                                                                
class Button:
    """ボタン"""
    def __init__(self, file_plase, pos_x, pos_y, angle):
        self.button_image = pygame.image.load(file_plase).convert_alpha()
        self.button_image = pygame.transform.scale(self.button_image, (BUTTON_WIDTH, BUTTON_WIDTH))
        self.button_image = pygame.transform.rotate(self.button_image, angle)
        self.rect = pygame.Rect(pos_x, pos_y, BUTTON_WIDTH, BUTTON_WIDTH)
    
    def draw(self, surface):
        surface.blit(self.button_image, self.rect)

                                                                                                                                                                                   
#   ,ad8888ba,                                                                                    88 I8,        8        ,8I 88                      88                                 
#  d8"'    `"8b                                                                                   88 `8b       d8b       d8' ""                      88                                 
# d8'                                                                                             88  "8,     ,8"8,     ,8"                          88                                 
# 88             ,adPPYba,  88,dPYba,,adPYba,  88,dPYba,,adPYba,  ,adPPYYba, 8b,dPPYba,   ,adPPYb,88   Y8     8P Y8     8P   88 8b,dPPYba,   ,adPPYb,88  ,adPPYba,  8b      db      d8  
# 88            a8"     "8a 88P'   "88"    "8a 88P'   "88"    "8a ""     `Y8 88P'   `"8a a8"    `Y88   `8b   d8' `8b   d8'   88 88P'   `"8a a8"    `Y88 a8"     "8a `8b    d88b    d8'  
# Y8,           8b       d8 88      88      88 88      88      88 ,adPPPPP88 88       88 8b       88    `8a a8'   `8a a8'    88 88       88 8b       88 8b       d8  `8b  d8'`8b  d8'   
#  Y8a.    .a8P "8a,   ,a8" 88      88      88 88      88      88 88,    ,88 88       88 "8a,   ,d88     `8a8'     `8a8'     88 88       88 "8a,   ,d88 "8a,   ,a8"   `8bd8'  `8bd8'    
#   `"Y8888Y"'   `"YbbdP"'  88      88      88 88      88      88 `"8bbdP"Y8 88       88  `"8bbdP"Y8      `8'       `8'      88 88       88  `"8bbdP"Y8  `"YbbdP"'      YP      YP      
                                                                                                                                                                                                                                                                                                                                                                    
class CommandWindow(Window):
    """コマンドボックス"""
    FONT_HEIGHT = 28
    WHITE = Color(255, 255, 255, 255)
    MAX_LEN = 20

    def __init__(self, rect):
        Window.__init__(self, rect)
        self.myfont = pygame.freetype.Font(FONT_DIR + FONT_NAME, self.FONT_HEIGHT)
        self.color = self.WHITE
        self.txt = ""

    def read(self,screen,font):
        self.txt = ""
        isEnd = False
        while not isEnd:
            for event in pygame.event.get():
                if event.type == QUIT:
                    sys.exit()
                elif event.type == KEYDOWN:
                    if event.key == K_RETURN:
                        isEnd = True
                    elif event.key == K_ESCAPE:
                        self.txt = ""
                        isEnd = True
                    elif event.key in (K_LEFT, K_BACKSPACE):
                        self.txt = self.txt[:-1]

                    elif event.key == K_SPACE and len(self.txt) < self.MAX_LEN:
                        self.txt += " "

                    elif event.key == K_TAB and len(self.txt) < self.MAX_LEN - 4:
                        self.txt += "    "

                    elif len(self.txt) < self.MAX_LEN:
                        shift_held = bool(pygame.key.get_mods() & (KMOD_LSHIFT | KMOD_RSHIFT))
                        capslock_on = bool(event.mod & KMOD_CAPS)
                        isUpper = shift_held | capslock_on

                        key_char_map = {
                            K_PERIOD: ">" if isUpper else ".",
                            K_COMMA: "<" if isUpper else ",",
                            K_MINUS: "_" if isUpper else "-",
                            K_EQUALS: "+" if isUpper else "=",
                            K_1: "!" if isUpper else "1",
                            K_2: "@" if isUpper else "2",
                            K_3: "#" if isUpper else "3",
                            K_4: "$" if isUpper else "4",
                            K_5: "%" if isUpper else "5",
                            K_6: "^" if isUpper else "6",
                            K_7: "&" if isUpper else "7",
                            K_8: "*" if isUpper else "8",
                            K_9: "(" if isUpper else "9",
                            K_0: ")" if isUpper else "0",
                        }

                        # 数字・記号キーの入力処理
                        if event.key in key_char_map:
                            self.txt += key_char_map[event.key]

                        # アルファベットキー（大文字・小文字対応）
                        elif K_a <= event.key <= K_z:
                            char = chr(event.key)
                            self.txt += char.upper() if isUpper else char
            txtg = font.render(self.txt, True, (255,255,255))
            self.blit(screen)
            screen.blit(txtg, [5, SCR_HEIGHT-TXTBOX_HEIGHT+txtg.get_height() // 2])
            pygame.display.update()  # 描画反映
        return self.txt

    def draw(self, screen, font):
        if not self.is_visible:
            return
        Window.draw(self)
        result = self.read(screen, font)
        Window.blit(self, screen)
        return result
                                                                                                                                                        
# 88b           d88 88             88 88b           d88                      I8,        8        ,8I 88                      88                                 
# 888b         d888 ""             "" 888b         d888                      `8b       d8b       d8' ""                      88                                 
# 88`8b       d8'88                   88`8b       d8'88                       "8,     ,8"8,     ,8"                          88                                 
# 88 `8b     d8' 88 88 8b,dPPYba,  88 88 `8b     d8' 88 ,adPPYYba, 8b,dPPYba,  Y8     8P Y8     8P   88 8b,dPPYba,   ,adPPYb,88  ,adPPYba,  8b      db      d8  
# 88  `8b   d8'  88 88 88P'   `"8a 88 88  `8b   d8'  88 ""     `Y8 88P'    "8a `8b   d8' `8b   d8'   88 88P'   `"8a a8"    `Y88 a8"     "8a `8b    d88b    d8'  
# 88   `8b d8'   88 88 88       88 88 88   `8b d8'   88 ,adPPPPP88 88       d8  `8a a8'   `8a a8'    88 88       88 8b       88 8b       d8  `8b  d8'`8b  d8'   
# 88    `888'    88 88 88       88 88 88    `888'    88 88,    ,88 88b,   ,a8"   `8a8'     `8a8'     88 88       88 "8a,   ,d88 "8a,   ,a8"   `8bd8'  `8bd8'    
# 88     `8'     88 88 88       88 88 88     `8'     88 `"8bbdP"Y8 88`YbbdP"'     `8'       `8'      88 88       88  `"8bbdP"Y8  `"YbbdP"'      YP      YP      
#                                                                  88                                                                                           
#                                                                  88                                                                                           

class MiniMapWindow(Window, Map):
    """"ミニマップウィンドウ"""
    tile_num = 60
    offset_x = 0
    offset_y = 10
    radius = 0
    RED = (255, 0, 0)
    BLUE = (0, 0, 255)
    BLACK = (0, 0, 0)
    GREEN = (0, 255, 0)
    YELLOW = (255, 255, 0)

    def __init__(self, rect, name):
        self.offset_x = SCR_WIDTH - MIN_MAP_SIZE - 10
        self.radius = MIN_MAP_SIZE / self.tile_num
        Window.__init__(self, rect)
        Map.__init__(self, name)
        self.hide()

    def draw(self, screen, map : Map):
        if not self.is_visible:
            return
        Window.draw(self)
        Window.blit(self, screen)
        for y in range(0,self.tile_num):
            for x in range(0,self.tile_num):
                if 0 <= y < self.row and 0 <= x < self.col:
                    tile = self.map[y][x]
                else:
                    tile = self.default
                if tile >= 489 and 535 >= tile:
                    continue
                pos_x = x * MIN_MAP_SIZE / self.tile_num + self.offset_x
                pos_y = y * MIN_MAP_SIZE / self.tile_num + self.offset_y
                image = pygame.transform.scale(self.images[tile], (int(MIN_MAP_SIZE / self.tile_num), int(MIN_MAP_SIZE / self.tile_num)))
                screen.blit(image, (pos_x, pos_y))
        
        # Treasureの場所を表示　青丸
        for event in map.events:
            if isinstance(event, Treasure):
                tx = event.x * MIN_MAP_SIZE / self.tile_num + self.offset_x + MIN_MAP_SIZE/ self.tile_num  // 2
                ty = event.y * MIN_MAP_SIZE / self.tile_num + self.offset_y+ MIN_MAP_SIZE/ self.tile_num  // 2
                pygame.draw.circle(screen, self.BLUE, (tx, ty), self.radius)
            elif isinstance(event, MoveEvent):
                mx = event.x * MIN_MAP_SIZE / self.tile_num + self.offset_x + MIN_MAP_SIZE/ self.tile_num  // 2
                my = event.y * MIN_MAP_SIZE / self.tile_num + self.offset_y+ MIN_MAP_SIZE/ self.tile_num  // 2
                pygame.draw.circle(screen, self.GREEN, (mx, my), self.radius)

        # Playerの場所を表示　赤丸
        px = PLAYER.x * MIN_MAP_SIZE / self.tile_num + self.offset_x + MIN_MAP_SIZE/ self.tile_num  // 2
        py = PLAYER.y * MIN_MAP_SIZE / self.tile_num + self.offset_y+ MIN_MAP_SIZE/ self.tile_num  // 2
        pygame.draw.circle(screen, self.RED, (px, py), self.radius)

        # Player以外のCharacterの場所を表示　黒丸
        for chara in map.charas:
            if not isinstance(chara, Player):
                cx = chara.x * MIN_MAP_SIZE / self.tile_num + self.offset_x + MIN_MAP_SIZE/ self.tile_num  // 2
                cy = chara.y * MIN_MAP_SIZE / self.tile_num + self.offset_y+ MIN_MAP_SIZE/ self.tile_num  // 2
                pygame.draw.circle(screen, self.YELLOW if chara.name == "15161" else self.BLACK, (cx, cy), self.radius)
                                                                                                                                   
#   ,ad8888ba,                       88          I8,        8        ,8I 88                      88                                 
#  d8"'    `"8b                      88          `8b       d8b       d8' ""                      88                                 
# d8'                                88           "8,     ,8"8,     ,8"                          88                                 
# 88             ,adPPYba,   ,adPPYb,88  ,adPPYba, Y8     8P Y8     8P   88 8b,dPPYba,   ,adPPYb,88  ,adPPYba,  8b      db      d8  
# 88            a8"     "8a a8"    `Y88 a8P_____88 `8b   d8' `8b   d8'   88 88P'   `"8a a8"    `Y88 a8"     "8a `8b    d88b    d8'  
# Y8,           8b       d8 8b       88 8PP"""""""  `8a a8'   `8a a8'    88 88       88 8b       88 8b       d8  `8b  d8'`8b  d8'   
#  Y8a.    .a8P "8a,   ,a8" "8a,   ,d88 "8b,   ,aa   `8a8'     `8a8'     88 88       88 "8a,   ,d88 "8a,   ,a8"   `8bd8'  `8bd8'    
#   `"Y8888Y"'   `"YbbdP"'   `"8bbdP"Y8  `"Ybbd8"'    `8'       `8'      88 88       88  `"8bbdP"Y8  `"YbbdP"'      YP      YP      
                                                                                                                                                                                                                                                    
class CodeWindow(Window):
    """デバッグコードウィンドウ"""
    FONT_SIZE = 12
    HIGHLIGHT_COLOR = (0, 0, 255)
    TEXT_COLOR = (255, 255, 255, 255)

    def __init__(self, rect, name):
        Window.__init__(self, rect)
        self.maxX = self.x + self.width
        self.maxY = self.y + self.height
        self.scrollX = 0
        self.scrollY = 0
        
        # 日本語対応フォントの指定
        self.font = pygame.freetype.Font(FONT_DIR + FONT_NAME, self.FONT_SIZE)
        
        self.c_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mapdata", name.lower(), name.lower() + ".c")
        self.lines = self.load_code_lines()
        self.linenum = 1
        self.is_auto_scroll = True

        self.auto_scroll_button_rect = pygame.Rect(self.rect.width - 110, self.rect.height - 40, 100, 30)
        self.hide()

    def load_code_lines(self):
        """Cファイルからコードを読み込む"""
        if not os.path.exists(self.c_file_path):
            return ["// File not found"]
        with open(self.c_file_path, 'r', encoding="utf-8") as f:
            return f.readlines()
        
    def draw_string(self, x, y, string, color):
        """文字列出力"""
        surf, rect = self.font.render(string, color)
        self.surface.blit(surf, (x, y+(self.FONT_SIZE)-rect[3]))

    def update_code_line(self, linenum):
        self.linenum = linenum
        
    def draw(self, screen):
        if not self.is_visible:
            return
        Window.draw(self)
        x_offset = 10 - self.scrollX
        y_offset = 10 - self.scrollY
        for i, line in enumerate(self.lines):
            # 自動調整onの時は現在の行の3行前から表示するようにする
            if self.is_auto_scroll and i < self.linenum - 3:
                continue
            if y_offset > self.maxY:
                break
            text = line.rstrip()
            if (i + 1) == self.linenum:
                bg_rect = pygame.Rect(
                    x_offset - 5,
                    y_offset,
                    self.rect.width - 20,
                    self.FONT_SIZE + 4
                )
                pygame.draw.rect(self.surface, self.HIGHLIGHT_COLOR, bg_rect)
            # freetypeの描画 (Surfaceには直接描画) surface内の座標は本windowとの相対座標
            self.draw_string(x_offset, y_offset, text, self.TEXT_COLOR)
            y_offset += self.FONT_SIZE + 4
        if not self.is_auto_scroll:
            pygame.draw.rect(self.surface, (100, 100, 100), self.auto_scroll_button_rect)  # グレーのボタン
            label_surf, _ = self.font.render("自動スクロール", (255, 255, 255))
            label_rect = label_surf.get_rect(center=self.auto_scroll_button_rect.center)
            self.surface.blit(label_surf, label_rect)
        Window.blit(self, screen)
    
    def isCursorInWindow(self, pos : tuple[int, int]):
        if self.x <= pos[0] <= self.maxX and self.y <= pos[1] <= self.maxY:
            self.is_auto_scroll = False
            return True
        else:
            return False

# 88888888888                                        ad88888ba                                  88                        
# 88                                          ,d    d8"     "8b                                 88                        
# 88                                          88    Y8,                                         88                        
# 88aaaaa 8b       d8  ,adPPYba, 8b,dPPYba, MM88MMM `Y8aaaaa,    ,adPPYba, 8b,dPPYba,   ,adPPYb,88  ,adPPYba, 8b,dPPYba,  
# 88""""" `8b     d8' a8P_____88 88P'   `"8a  88      `"""""8b, a8P_____88 88P'   `"8a a8"    `Y88 a8P_____88 88P'   "Y8  
# 88       `8b   d8'  8PP""""""" 88       88  88            `8b 8PP""""""" 88       88 8b       88 8PP""""""" 88          
# 88        `8b,d8'   "8b,   ,aa 88       88  88,   Y8a     a8P "8b,   ,aa 88       88 "8a,   ,d88 "8b,   ,aa 88          
# 88888888888 "8"      `"Ybbd8"' 88       88  "Y888  "Y88888P"   `"Ybbd8"' 88       88  `"8bbdP"Y8  `"Ybbd8"' 88          

class EventSender:
    def __init__(self, code_window: CodeWindow, host='localhost', port=9999, timeout=20.0, wait_timeout=10.0):
        self.code_window = code_window

        start = time.time()
        last_error = None
        while time.time() - start < wait_timeout:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.settimeout(timeout)
                self.sock.connect((host, port))
                print("[Client] 接続成功")
                break
            except (ConnectionRefusedError, OSError) as e:
                last_error = e
                time.sleep(0.1)
        else:
            print(f"[Client] 接続失敗: {last_error}")
            raise TimeoutError(f"{host}:{port} に {wait_timeout:.1f} 秒以内に接続できませんでした。")

    def send_event(self, event):
        self.sock.sendall(json.dumps(event).encode() + b'\n')  # 改行区切りで複数送信可能

    def receive_json(self):
        buffer = ""
        try:
            while True:
                data = self.sock.recv(1024)
                if not data:
                    return None  # 接続が閉じられた
                buffer += data.decode()
                try:
                    msg = json.loads(buffer)
                    if "line" in msg:
                        self.code_window.update_code_line(msg["line"])
                    if "removed" in msg:
                        for item in msg["removed"]:
                            PLAYER.itembag.remove(item["name"], item["line"])
                    if "values" in msg:
                        PLAYER.remove_itemvalue()
                        for itemvalues in msg["values"]:
                            print(itemvalues)
                            item = PLAYER.commonItembag.find(itemvalues["item"]["name"], itemvalues["item"]["line"])
                            if item is None:
                                item = PLAYER.itembag.find(itemvalues["item"]["name"], itemvalues["item"]["line"])
                            if item:
                                item.set_value(itemvalues)
                    if "str" in msg:
                        for str_info in msg["str"]:
                            if str_info['value'] is None or str_info['copyFrom'] == str_info['value']:
                                MSGWND.str_messages.append(f"{str_info['copyFrom']}を{str_info['copyTo']}に代入しました!!")
                            else:
                                MSGWND.str_messages.append(f"{str_info['copyFrom']}({str_info['value'][1:-1]})を{str_info['copyTo']}に代入しました!!")
                    if "std" in msg and len(msg["std"]) > len(PLAYER.std_messages):
                        MSGWND.new_std_messages = msg["std"][len(PLAYER.std_messages):]
                        PLAYER.std_messages = msg["std"]
                    if "files" in msg:
                        for file_info in msg["files"]:
                            if file_info["type"] == "fopen":
                                PLAYER.address_to_fname[file_info["address"]] = file_info["filename"]
                                MSGWND.file_message = f"{file_info['filename'][1:-1]}　を変数　{file_info['varname']}　で開きました!!"
                            else:
                                MSGWND.file_message = f"{PLAYER.address_to_fname[file_info['address']][1:-1]}　を閉じました!!"
                                ITEMWND.file_window.filename = None
                                ITEMWND.file_window.is_visible = False
                                fname = PLAYER.address_to_fname.pop(file_info["address"])
                                ITEMWND.file_buttons.pop(fname, None)
                    if "memory" in msg:
                        for memory_info in msg["memory"]:
                            if memory_info["type"] == "malloc":
                                PLAYER.address_to_size[memory_info["address"]] = {"vartype": memory_info["vartype"], "size": memory_info["size"], "varname": [memory_info["varname"]]}
                            elif memory_info["type"] == "realloc":
                                PLAYER.address_to_size[memory_info["address"]] = {"vartype": memory_info["vartype"], "size": memory_info["size"], "varname": [memory_info["varname"]]}
                            else:
                                PLAYER.address_to_size.pop(memory_info["address"], None)
                    if ITEMWND:
                        ITEMWND.file_window.read_filelines()
                    return msg
                except json.JSONDecodeError:
                    continue  # JSONがまだ完全でないので続けて待つ
        except socket.timeout:
            raise TimeoutError("ソケットの受信がタイムアウトしました。プログラム内の無限ループ、または処理の長さが問題だと考えられます。")
        except Exception as e:
            print(f"受信エラー: {e}")
            raise 
        
    def close(self):
        self.sock.close()
  
if __name__ == "__main__":
    main()