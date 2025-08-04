#!/usr/bin/env python3
"""RPGあくあたん"""
import codecs
import os
import subprocess
import random
import struct
import sys
import re
# socket通信を行う
import socket
import json
import time
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
                        # ステージのボタンを押した場合
                        if code_name is not None and scroll_start == False and code_name == SBWND.is_clicked(event.pos):
                            SBWND.hide()
                            stage_name = code_name
                        mouse_down = False
                        scroll_start = False
                if mouse_down:
                    if event.type == pygame.MOUSEMOTION:
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
                SBWND.draw(screen)
                pygame.display.update()
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
        # if args.universal:
        #     cfcode.append("-u")
        subprocess.run(cfcode, cwd="mapdata_generator")

        subprocess.run(["gcc", "-g", "-o", programpath, " ".join(cfiles)])

        # サーバを立てる
        env = os.environ.copy()
        env["PYTHONPATH"] = os.path.abspath("modules") + (
            ":" + env["PYTHONPATH"] if "PYTHONPATH" in env else ""
        )
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
        ##pygame.mouse.set_visible(0)
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
        # このevalはast.literal_evalを使った方が良いかもしれません
        items = eval(config.get("game", "items"))

        ## コードウィンドウを作る
        CODEWND = CodeWindow(MCODE_RECT, mapname)

        sender = EventSender(CODEWND)
        
        PLAYER = Player(player_chara, (player_x, player_y), DOWN, sender)
        _ = sender.receive_json()

        BTNWND = ArrowButtonWindow()
        BTNWND.show()
        mouse_down = False
        
        # 初期アイテムの設定(グローバル変数)
        for itemName in items.keys():
            # このitemValueをアイテムの初期値として設定するつもりです!!
            # ここも後のグローバル変数の解析を考える時に修正する
            item = Item(itemName)
            # ここで変数名を送信してその初期値を取得する(グローバル変数のみ)
            item.set_value(get_exp_value(items[itemName]))
            PLAYER.commonItembag.add(item)

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

        ITEMWND = ItemWindow(Rect(10, 10 + SCR_HEIGHT // 5 ,
                                    SCR_WIDTH // 5 - 10, SCR_HEIGHT // 5 * 3 - 10),PLAYER)
        ITEMWND.show()

        CMNDWND = CommandWindow(TXTBOX_RECT)
        CMNDWND.show()

        ## ミニマップを作る
        MMAPWND = MiniMapWindow(MMAP_RECT, mapname)
        MMAPWND.show()

        # endregion
        clock = pygame.time.Clock()
        print("5")

        PLAYER.append_automove(e)
        db_check_count = 0

        print("6")
        lightrooms = []
        messages = []
        lightrooms = list(set(lightrooms))
        LIGHTWND.set_rooms(lightrooms)
        if len(messages) > 0:
            MSGWND.set("/".join(messages))

        PLAYER.fp.write("start," + mapname + "," + str(PLAYER.x)+", " + str(PLAYER.y) + "\n")

    #    if args.screenshot:
    #        MSGWND.hide()
    #        offset = calc_offset(PLAYER)
    #        fieldmap.update()
    #        fieldmap.draw(screen, offset)
    #        pygame.display.update()
    #        pygame.image.save(screen, "screenshot.png")
    #        sys.exit()

        #current_place = OMZN_STATUS.current_place()

        last_mouse_pos = None
        
        while not PLAYER.goaled:
            messages = []
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

            # For every interval
            if db_check_count > DB_CHECK_WAIT:
                db_check_count = 0
                lightrooms = []
                lightrooms = list(set(lightrooms))
                LIGHTWND.set_rooms(lightrooms)
                if len(messages) > 0:
                    MSGWND.set("/".join(messages))

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

            n_move = PLAYER.get_next_automove()
            if n_move is not None and n_move == 's':
                PLAYER.pop_automove()
                # 足元にあるのが宝箱かワープゾーンかを調べる
                event_underfoot = PLAYER.search(fieldmap)
                if isinstance(event_underfoot, Treasure):
                    ### 宝箱を開けることの情報を送信する
                    sender.send_event({"item": event_underfoot.item, "funcWarp": event_underfoot.funcWarp})
                    itemResult = sender.receive_json()
                    if itemResult is not None:
                        if itemResult['status'] == "ok":
                            event_underfoot.open(itemResult['value'], itemResult['undefined'])
                            item_comments = "%".join(event_underfoot.comments)
                            if item_comments:
                                item_get_message = f"宝箱を開けた！/「{event_underfoot.item}」を手に入れた！%" + item_comments
                            else:
                                item_get_message = f"宝箱を開けた！/「{event_underfoot.item}」を手に入れた！"
                            fieldmap.remove_event(event_underfoot)
                            if itemResult.get('skip', False):
                                item_get_message += f"%{itemResult['message']}"
                                MSGWND.set(item_get_message, (['はい', 'いいえ'], 'func_skip'))
                            else:
                                MSGWND.set(item_get_message)
                            PLAYER.fp.write("itemget, " + mapname + "," + str(PLAYER.x)+", " + str(PLAYER.y) + "," + event_underfoot.item + "\n")
                        else:
                            MSGWND.set(itemResult['message'])
                    continue
                elif isinstance(event_underfoot, MoveEvent):
                    ### ワープゾーンに入ろうとしていることの情報を送信する
                    sender.send_event({"type": event_underfoot.type, "fromTo": event_underfoot.fromTo})
                    moveResult = sender.receive_json()
                    if moveResult and moveResult['status'] == "ok":
                        dest_map = event_underfoot.dest_map
                        dest_x = event_underfoot.dest_x
                        dest_y = event_underfoot.dest_y

                        # region command
                        from_map = fieldmap.name
                        PLAYER.move5History.append({'mapname': from_map, 'x': PLAYER.x, 'y': PLAYER.y, 'cItems': PLAYER.commonItembag.items[-1], 'items': PLAYER.itembag.items[-1], 'return':False})
                        if len(PLAYER.move5History) > 5:
                            PLAYER.move5History.pop(0)
                        # endregion
                        # 暗転
                        DIMWND.setdf(200)
                        DIMWND.show()
                        fieldmap.create(dest_map)  # 移動先のマップで再構成
                        PLAYER.set_pos(dest_x, dest_y, DOWN)  # プレイヤーを移動先座標へ
                        fieldmap.add_chara(PLAYER)  # マップに再登録
                        PLAYER.fp.write("jump, " + dest_map + "," + str(PLAYER.x)+", " + str(PLAYER.y) + "\n")
                        # skipアクション
                        if moveResult.get('skip', False):
                            MSGWND.set(moveResult['message'], (['はい', 'いいえ'], 'loop_skip'))
                    else:
                        MSGWND.set(moveResult['message'])
                    continue

                chara = PLAYER.talk(fieldmap)
                if chara is not None:
                    ### ここで話しかけたことの情報を送信する
                    msg = chara.message
                    MSGWND.set(msg)
                else:
                    MSGWND.set("そのほうこうには　だれもいない。")
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
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
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
                        cmd = BTNWND.is_clicked(event.pos)
                    
                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 1:
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

                                    if event.type == pygame.MOUSEBUTTONDOWN:
                                        if event.button == 1 and PAUSEWND.is_visible:
                                            local_pos = (event.pos[0] - PAUSEWND.x, event.pos[1] - PAUSEWND.y)
                                            if PAUSEWND.button_toGame_rect.collidepoint(local_pos):
                                                cmd = ""
                                                PAUSEWND.hide()
                                                print('ゲームに戻る')
                                            elif PAUSEWND.button_toStageSelect_rect.collidepoint(local_pos):
                                                cmd = ""    
                                                PAUSEWND.hide()
                                                PLAYER.goaled = True 
                                                print('ステージ選択に戻る')       

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
                    cmd = BTNWND.is_clicked(pygame.mouse.get_pos())
                # endregion
                
                # region keydown event
                ## open map
                if event.type == KEYDOWN and event.key == K_i:
                    PLAYER.set_game_mode("item")
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
                        PLAYER.fp.write( "restart, " + mapname + "," + str(PLAYER.x)+", " + str(PLAYER.y) + "\n")
                    elif cmd == "echo":
                        MSGWND.set(atxt)
                        atxt = "\0"
                        cmd = "\0"
                    elif cmd == "itemget":
                        try:
                            itemname = atxt.strip()
                            if not itemname:
                                raise ValueError("No item name provided.")
                            item = PLAYER.commonItembag.find(itemname)
                            if item is None:
                                item = PLAYER.itembag.find(itemname)
                            if item:
                                if(item.get_value() != None):
                                    MSGWND.set(f"アイテム {itemname} の値は {str(item.get_value())} です")
                            else:
                                MSGWND.set(f"アイテム {itemname} は持っていません!!")
                        except Exception:
                            MSGWND.set("ERROR...")
                        cmd = "\0"
                        atxt = "\0"
                    elif cmd == "itemset":
                        ## suit for integer item
                        ## "itemset <var> num" ,"itemset <var> +<num>" or "item <var> ++"
                        try:
                            parts = atxt.split(' ', 1)
                            itemname = parts[0]
                            value = parts[1]
                            item = PLAYER.commonItembag.find(itemname)
                            if item is None:
                                item = PLAYER.itembag.find(itemname)
                            if item:
                                current_value = item.get_value()
                                if value == "++":
                                    value = str(int(current_value) + 1)
                                elif value == "--":
                                    value = str(int(current_value) - 1)
                                # この下の計算式コマンドは j = -5 と被るので今は無視
                                # elif value.startswith("+"):
                                #     value = str(int(current_value) + int(value[1:]))
                                # elif value.startswith("-"):
                                #     value = str(int(current_value) - int(value[1:]))

                                sender.send_event({"itemset": [itemname, value]})
                                itemsetResult = sender.receive_json()
                                if itemsetResult is not None:
                                    if itemsetResult['status'] == "ok":
                                        item.set_value(value)
                                    MSGWND.set(itemsetResult['message'])
                            else:
                                MSGWND.set(f"アイテム {itemname} は持っていません!!")
                        except (IndexError, ValueError):
                            MSGWND.set("ERROR...")
                        cmd = "\0"
                        atxt = "\0"
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
                    elif cmd == "jump":
                        ## 関数の入り口まで飛ばしてくれる　同じマップ内だけ hogehoge
                        msg = "\u95a2\u6570 " + atxt + " \u306b\u9077\u79fb\u3057\u307e\u3059!!"
                        MSGWND.set("Jump to \'"+atxt+"\' !!")
                        for chara in fieldmap.charas:
                            if chara.message is not None:
                                if chara.message == msg:
                                    target_chara = chara
                                    ##print(chara.message)
                        chara = target_chara
                        if chara is None:
                            MSGWND.set("Function \'"+atxt+"\' is not found...")
                        else:
                            if isinstance(chara, Character):
                                msg = chara.message
                                MSGWND.set(msg)
                                if isinstance(chara, CharaMoveEvent):
                                    if isinstance(chara, CharaMoveItemsEvent):
                                        itemsLacked_list = []
                                        for items in chara.items:
                                            if (itemsLacked := set(items) - set([item.name for item in (PLAYER.itembag.items[-1] + PLAYER.commonItembag.items[-1])])):
                                                itemsLacked_list.append(itemsLacked)
                                        #アイテムが不足
                                        if itemsLacked_list:
                                            itemsLackedmessage_list = []
                                            for itemsLacked in itemsLacked_list:
                                                itemsLackedmessage_list.append(','.join(item for item in itemsLacked))
                                            MSGWND.set(f"{chara.errmessage}/変数 {','.join(itemsLackedmessage_list)} が不足しています!!")
                                        #必要なアイテムが存在
                                        else:
                                            PLAYER.move5History.append({'mapname': mapname, 'x': PLAYER.x, 'y': PLAYER.y, 'cItems': PLAYER.commonItembag.items[-1], 'items': PLAYER.itembag.items[-1], 'return': False})
                                            if len(PLAYER.move5History) > 5:
                                                PLAYER.move5History.pop(0)
                                            #グローバル変数のアイテムを設定する
                                            newItems = []
                                            for argument in chara.arguments:
                                                # ここは後に関数キャラを考える時に修正する
                                                item = Item(argument)
                                                item.value = 1
                                                newItems.append(item)
                                            PLAYER.itembag.items.append(newItems)
                                            PLAYER.waitingMove = chara
                                            PLAYER.moveHistory.append({'mapname': mapname, 'x': PLAYER.x, 'y': PLAYER.y, 'line': CODEWND.linenum})
                                    else:
                                        PLAYER.waitingMove = chara
                                        PLAYER.moveHistory.append({'mapname': mapname, 'x': PLAYER.x, 'y': PLAYER.y, 'line': CODEWND.linenum})
                                        PLAYER.move5History.append({'mapname': mapname, 'x': PLAYER.x, 'y': PLAYER.y, 'cItems': PLAYER.commonItembag.items[-1], 'items': PLAYER.itembag.items[-1], 'return': False})
                                        if len(PLAYER.move5History) > 5:
                                            PLAYER.move5History.pop(0)
                                elif isinstance(chara, CharaReturn):
                                    PLAYER.set_waitingMove_return(mapname, chara, chara.line)
                        PLAYER.fp.write( "jump:" + atxt + ", " + mapname + "," + str(PLAYER.x)+", " + str(PLAYER.y) + "\n")
                        cmd = "\0"
                        atxt = "\0"
                    elif cmd == "aquatan":
                        MSGWND.set("Make aquatan/Grate Again!!!")
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
                                        print('ゲームに戻る')
                                    elif PAUSEWND.button_toStageSelect_rect.collidepoint(local_pos):
                                        cmd = ""    
                                        PAUSEWND.hide()
                                        PLAYER.goaled = True 
                                        print('ステージ選択に戻る')       


                if MSGWND.selectMsgText is not None and (event.type == KEYDOWN and event.key in [K_LEFT, K_RIGHT]):
                    MSGWND.selectMsg(-1 if event.key == K_LEFT else 1)

                if (event.type == KEYDOWN and (event.key == K_SPACE or event.key == K_RETURN)) or cmd == "action":
                    cmd = ""
                    if MSGWND.is_visible:
                        # メッセージウィンドウ表示中なら次ページへ
                        MSGWND.next(fieldmap, force_next=True)
                    else:
                        # 足元にあるのが宝箱かワープゾーンかを調べる
                        event_underfoot = PLAYER.search(fieldmap)
                        if isinstance(event_underfoot, Treasure):
                            ### 宝箱を開けることの情報を送信する
                            sender.send_event({"item": event_underfoot.item, "funcWarp": event_underfoot.funcWarp})
                            itemResult = sender.receive_json()
                            if itemResult is not None:
                                if itemResult['status'] == "ok":
                                    event_underfoot.open(itemResult['value'], itemResult['undefined'])
                                    item_comments = "%".join(event_underfoot.comments)
                                    if item_comments:
                                        item_get_message = f"宝箱を開けた！/「{event_underfoot.item}」を手に入れた！%" + item_comments
                                    else:
                                        item_get_message = f"宝箱を開けた！/「{event_underfoot.item}」を手に入れた！"
                                    fieldmap.remove_event(event_underfoot)
                                    if itemResult.get('skip', False):
                                        item_get_message += f"%{itemResult['message']}"
                                        MSGWND.set(item_get_message, (['はい', 'いいえ'], 'func_skip'))
                                    else:
                                        MSGWND.set(item_get_message)
                                    PLAYER.fp.write("itemget, " + mapname + "," + str(PLAYER.x)+", " + str(PLAYER.y) + "," + event_underfoot.item + "\n")
                                else:
                                    MSGWND.set(itemResult['message'])
                            continue
                        elif isinstance(event_underfoot, MoveEvent):
                            sender.send_event({"type": event_underfoot.type, "fromTo": event_underfoot.fromTo})
                            moveResult = sender.receive_json()
                            if moveResult and moveResult['status'] == "ok":
                                dest_map = event_underfoot.dest_map
                                dest_x = event_underfoot.dest_x
                                dest_y = event_underfoot.dest_y

                                from_map = fieldmap.name
                                PLAYER.move5History.append({'mapname': from_map, 'x': PLAYER.x, 'y': PLAYER.y, 'cItems': PLAYER.commonItembag.items[-1], 'items': PLAYER.itembag.items[-1], 'return':False})
                                if len(PLAYER.move5History) > 5:
                                    PLAYER.move5History.pop(0)

                                # 暗転
                                DIMWND.setdf(200)
                                DIMWND.show()
                                fieldmap.create(dest_map)  # 移動先のマップで再構成
                                PLAYER.set_pos(dest_x, dest_y, DOWN)  # プレイヤーを移動先座標へ
                                fieldmap.add_chara(PLAYER)  # マップに再登録
                                PLAYER.fp.write("jump, " + dest_map + "," + str(PLAYER.x)+", " + str(PLAYER.y) + "\n")
                                # skipアクション
                                if moveResult.get('skip', False):
                                    MSGWND.set(moveResult['message'], (['はい', 'いいえ'], 'loop_skip'))
                            else:
                                MSGWND.set(moveResult['message'])
                            continue

                        # ドアを開ける
                        door = PLAYER.unlock(fieldmap)
                        if door is not None:
                            continue

                        # 表示中でないならはなす
                        chara = PLAYER.talk(fieldmap)
                        if chara is not None:
                            if isinstance(chara, Character):
                                msg = chara.message
                                MSGWND.set(msg)
                                # CharaMoveItemsEvent→CharaMoveEventと範囲が大きくなるのでこの順で確認する(ネストを解除)
                                if isinstance(chara, CharaMoveItemsEvent):
                                    itemsLacked_list = []
                                    for items in chara.items:
                                        if (itemsLacked := set(items) - set([item.name for item in (PLAYER.itembag.items[-1] + PLAYER.commonItembag.items[-1])])):
                                            itemsLacked_list.append(itemsLacked)
                                    #アイテムが不足
                                    if itemsLacked_list:
                                        itemsLackedmessage_list = []
                                        for itemsLacked in itemsLacked_list:
                                            itemsLackedmessage_list.append(','.join(item for item in itemsLacked))
                                        MSGWND.set(f"{chara.errmessage}/変数 {','.join(itemsLackedmessage_list)} が不足しています!!")
                                    #必要なアイテムが存在
                                    else:
                                        # ここでchara.itemsとchara情報?を送信してその合致を確かめる
                                        # グローバル変数のアイテムを設定する
                                        PLAYER.move5History.append({'mapname': mapname, 'x': PLAYER.x, 'y': PLAYER.y, 'cItems': PLAYER.commonItembag.items[-1], 'items': PLAYER.itembag.items[-1], 'return': False})
                                        if len(PLAYER.move5History) > 5:
                                            PLAYER.move5History.pop(0)
                                        newItems = []
                                        for argument in chara.arguments:
                                            # ここも関数を考える時に後々修正する
                                            item = Item(argument)
                                            item.value = 1
                                            newItems.append(item)
                                        PLAYER.itembag.items.append(newItems)
                                        PLAYER.waitingMove = chara
                                        PLAYER.moveHistory.append({'mapname': mapname, 'x': PLAYER.x, 'y': PLAYER.y, 'line': CODEWND.linenum})
                                        msg = chara.message
                                        parts = msg.split(" ", 1)
                                        parts1 = parts[1].split(" ",1)
                                        PLAYER.fp.write("movein:" + parts1[0] + "," + mapname + "," + str(PLAYER.x)+", " + str(PLAYER.y) + "\n")
                                elif isinstance(chara, CharaMoveEvent):   
                                    PLAYER.waitingMove = chara
                                    PLAYER.moveHistory.append({'mapname': mapname, 'x': PLAYER.x, 'y': PLAYER.y})
                                    PLAYER.move5History.append({'mapname': mapname, 'x': PLAYER.x, 'y': PLAYER.y, 'cItems': PLAYER.commonItembag.items[-1], 'items': PLAYER.itembag.items[-1], 'return': False})
                                    if len(PLAYER.move5History) > 5:
                                        PLAYER.move5History.pop(0)
                                    msg = chara.message
                                    parts = msg.split(" ", 1)
                                    parts1 = parts[1].split(" ",1)
                                    PLAYER.fp.write("movein:" + parts1[0] + "," + mapname + "," + str(PLAYER.x)+", " + str(PLAYER.y) + "\n")
                                elif isinstance(chara, CharaReturn):
                                    PLAYER.set_waitingMove_return(mapname, chara, chara.line)
                        else:
                            MSGWND.set("そのほうこうには　だれもいない。")
                # endregion
            MSGWND.next(fieldmap)
            pygame.display.flip()

        server.terminate()

def get_exp_value(expList):
    value = None
    if (itemsLacked := set(expList[1]) - set(PLAYER.itembag.items[-1])):
        MSGWND.set(f"このアイテムを取得するには　{','.join([item for item in itemsLacked])}　が足りません!!")
    else:
        value = 1
    return value

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
        self.name = name
        self.row = -1  # 行数
        self.col = -1  # 列数
        self.map = []  # マップデータ（2次元リスト）
        self.charas = []  # マップにいるキャラクターリスト
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

    def draw(self, screen, offset):
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
            elif chara_type == "CHARAMOVE":  # キャラクター+移動
                self.create_charamove_j(chara)
            elif chara_type == "CHARAMOVEITEMS": # キャラクター+アイテムが条件の遷移
                self.create_charamoveitems_j(chara)
            elif chara_type == "CHARARETURN": #キャラクター+遷移元に戻る
                self.create_charareturn_j(chara)
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
                if PLAYER.commonItembag.find(event["item"]) is None and PLAYER.itembag.find(event["item"]) is None:
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
        exp = data["exp"]
        refs = data["refs"]
        comments = data["comments"]
        vartype = data["vartype"]
        linenum = data["linenum"]
        funcWarp = data["funcWarp"]
        treasure = Treasure((x, y), item, exp, refs, comments, vartype, linenum, funcWarp)
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
        line = data["line"]
        chara = CharaReturn(name, (x, y), direction, movetype, message, line)
        #print(chara)
        self.charas.append(chara)

    def create_charamove_j(self, data):
        """キャラクター(移動付き)を作成してcharasに追加する"""
        name = data["name"]
        x, y = int(data["x"]), int(data["y"])
        direction = int(data["dir"])
        movetype = int(data["movetype"])
        message = data["message"]
        dest_map = data["dest_map"]
        dest_x, dest_y = int(data["dest_x"]), int(data["dest_y"])
        chara = CharaMoveEvent(name, (x, y), direction, movetype, message,
                                dest_map, (dest_x, dest_y))
        #print(chara)
        self.charas.append(chara)

    def create_charamoveitems_j(self, data):
        """キャラクター(移動付き)を作成してcharasに追加する"""
        name = data["name"]
        x, y = int(data["x"]), int(data["y"])
        direction = int(data["dir"])
        movetype = int(data["movetype"])
        message = data["message"]
        errmessage = data["errmessage"]
        dest_map = data["dest_map"]
        dest_x, dest_y = int(data["dest_x"]), int(data["dest_y"])
        items = data["items"]
        funcName = data["funcName"]
        arguments = data["arguments"]
        chara = CharaMoveItemsEvent(name, (x, y), direction, movetype, message, errmessage,
                                dest_map, (dest_x, dest_y), items, funcName, arguments)
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
        move = MoveEvent((x, y), mapchip, dest_map, type, fromTo, (dest_x, dest_y))
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
        type = data.get("autoType", "")
        fromTo = data.get("fromTo", [0,0])
        auto = AutoEvent((x, y), mapchip, sequence, type, fromTo)
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
        self.automoveFromTo: list[tuple[str, list[int | None]]] = []
        self.waitingMove = None
        self.moveHistory = []
        self.move5History = []
        self.status = {"LV":1, "HP":100, "MP":20, "ATK":10, "DEF":10}
        self.itembag = ItemBag()
        self.commonItembag = ItemBag()
        self.sender : EventSender = sender
        self.itemNameShow = False
        self.door : SmallDoor = None # スモールドアイベントがNoneでない(扉の上にいる)時に移動したら扉を閉じるようにする。
        self.goaled = False

        ## start
        self.fp = open(PATH, mode='w')
        ## end

    def update(self, mymap):
        """プレイヤー状態を更新する。
        mapは移動可能かの判定に必要。"""
        # プレイヤーの移動処理
        if self.moving:
            # ピクセル移動中ならマスにきっちり収まるまで移動を続ける
            self.rect.move_ip(self.vx, self.vy)
            if self.rect.left % GS == 0 and self.rect.top % GS == 0:  # マスにおさまったら移動完了
                ##self.fp.write( str(self.x)+", " + str(self.y) + "\n")
                self.moving = False
                self.x = self.rect.left // GS
                self.y = self.rect.top // GS

                if self.door is not None:
                    if ((self.door.direction == DOWN and (self.door.x, self.door.y-1) == (self.x, self.y)) or (self.door.direction == UP and (self.door.x, self.door.y+1) == (self.x, self.y)) or
                        (self.door.direction == LEFT and (self.door.x+1, self.door.y) == (self.x, self.y)) or (self.door.direction == RIGHT and (self.door.x-1, self.door.y) == (self.x, self.y))):
                        self.door.close()
                        self.door = None

                # 接触イベントチェック
                event = mymap.get_event(self.x, self.y)
                if isinstance(event, PlacesetEvent):  # PlacesetEventなら
                    self.place_label = event.place_label
                elif isinstance(event, AutoEvent):  # AutoEvent
                    self.append_automove(event.sequence, type=event.type, fromTo=event.fromTo)
                    return
                elif isinstance(event, SmallDoor):
                    self.door = event

        elif self.waitingMove is not None:
#           print(f"waitingMove:{self.waitingMove}")
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
                cmd = "\0"
            elif cmd == "left":
                direction = 'l'
                cmd = "\0"
            elif cmd == "right":
                direction = 'r'
                cmd = "\0"
            elif cmd == "up":
                direction = 'u'
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
            if direction in ('u', 'd', 'l', 'r'):
                # ifやwhileの部屋侵入時の暫定のイベント送信
                if len(self.automoveFromTo):
                    if ((self.y - self.prevPos[0][1] == -1 and direction == 'd')
                    or (self.x - self.prevPos[0][0] == 1 and direction == 'l')
                    or (self.x - self.prevPos[0][0] == -1 and direction == 'r')
                    or (self.y - self.prevPos[0][1] == 1 and direction == 'u')):
                        tempPrevPos = [None, self.prevPos[0]]
                        MSGWND.set("ここから先は進入できません!!")
                    else:
                        automoveFromTo = self.get_next_automoveFromTo()
                        type, fromTo = automoveFromTo
                        self.sender.send_event({"type": type, "fromTo": fromTo})
                        automoveResult = self.sender.receive_json()
                        if automoveResult and automoveResult['status'] == "ng":
                            MSGWND.set(automoveResult['message'])
                            if self.y - self.prevPos[0][1] == 1:
                                direction = 'u'
                            elif self.x - self.prevPos[0][0] == -1:
                                direction = 'r'
                            elif self.x - self.prevPos[0][0] == 1:
                                direction = 'l'
                            else:
                                direction = 'd'                            
                            self.prevPos = [None, self.prevPos[0]]
                        else:
                            if self.door is not None:
                                self.door.close()
                                self.door = None
                            # skipアクション
                            if automoveResult.get('skip', False):
                                MSGWND.set(automoveResult['message'],(['はい', 'いいえ'], 'loop_skip'))
                    self.pop_automoveFromTo()
                    self.pop_automove()
            elif direction == 'x':
                self.wait += 1
                if self.wait > 60:
                    self.wait = 0
                    self.pop_automove()

            if direction == 'd' or (pressed_keys and pressed_keys[K_DOWN]):
                self.direction = DOWN  # 移動できるかに関係なく向きは変える
                if mymap.is_movable(self.x, self.y+1):
                    self.vx, self.vy = 0, self.speed
                    self.moving = True
                    self.prevPos = tempPrevPos if tempPrevPos else [self.prevPos[1], (self.x, self.y+1)]
            elif direction == 'l' or (pressed_keys and pressed_keys[K_LEFT]):
                self.direction = LEFT
                if mymap.is_movable(self.x-1, self.y):
                    self.vx, self.vy = -self.speed, 0
                    self.moving = True
                    self.prevPos = tempPrevPos if tempPrevPos else [self.prevPos[1], (self.x-1, self.y)]
            elif direction == 'r' or (pressed_keys and pressed_keys[K_RIGHT]):
                self.direction = RIGHT
                if mymap.is_movable(self.x+1, self.y):
                    self.vx, self.vy = self.speed, 0
                    self.moving = True
                    self.prevPos = tempPrevPos if tempPrevPos else  [self.prevPos[1], (self.x+1, self.y)]
            elif direction == 'u' or (pressed_keys and pressed_keys[K_UP]):
                self.direction = UP
                if mymap.is_movable(self.x, self.y-1):
                    self.vx, self.vy = 0, -self.speed
                    self.moving = True
                    self.prevPos = tempPrevPos if tempPrevPos else [self.prevPos[1], (self.x, self.y-1)]

        # キャラクターアニメーション（frameに応じて描画イメージを切り替える）
        self.frame += 1
        self.image = self.images[self.name][self.direction *
                                            4+(self.frame // self.animcycle % 4)]

    def set_automove(self, seq):
        """自動移動シーケンスをセットする"""
        self.automove = seq
        #print(self.automove)

    def get_next_automove(self):
        """次の移動先を得る"""
        if len(self.automove) > 0:
            return self.automove[0]
        return None

    def get_next_automoveFromTo(self):
        """一方通行パネルがどの部屋からどの部屋に行くのかを確かめる"""
        if len(self.automoveFromTo) > 0:
            return self.automoveFromTo[0]
        return None
    
    def pop_automove(self):
        """自動移動を1つ取り出す"""
        self.automove.pop(0)

    def pop_automoveFromTo(self):
        """自動移動に付随してfromTo情報を取得"""
        self.automoveFromTo.pop(0)

    def append_automove(self, ch, type='', fromTo=None):
        """自動移動に追加する"""
        self.automove.extend(ch)
        if fromTo:
            self.automoveFromTo.append((type, fromTo))

    def search(self, mymap):
        """足もとに宝箱またはワープゾーンがあるか調べる"""
        event = mymap.get_event(self.x, self.y)
        if isinstance(event, Treasure) or isinstance(event, MoveEvent):
            return event
        return None

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
                        MSGWND.set(f"{event.doorname}を開けた！")
                        if self.door is not None:
                            self.door.close()
                            self.door = None
                    else:
                        MSGWND.set('この方向から扉は開けません!!')
                else:
                    return None
            else:
                mymap.remove_event(event)
            return event
        return None

    def talk(self, mymap):
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
        return chara

    def set_waitingMove_return(self, mapname: str, chara: Character, fromLine):
        """returnの案内人に話しかけた時、動的にwaitingMoveを設定する"""
        # main以外のreturnキャラ
        if self.moveHistory != []:
            self.sender.send_event({"type": 'return', "fromTo": [fromLine, self.moveHistory[-1]['line']]})
            returnResult = self.sender.receive_json()
            if returnResult['status'] == 'ok':
                self.move5History.append({'mapname': mapname, 'x': self.x, 'y': self.y, 'cItems': self.commonItembag.items[-1], 'items': self.itembag.items[-1], 'return':True})
                if len(self.move5History) > 5:
                    self.move5History.pop(0)
                move = self.moveHistory.pop()
                self.itembag.items.pop()
                for name, value in returnResult["items"].items():
                    if (item := self.itembag.find(name)) is not None:
                        item.set_value(value)
                self.waitingMove = chara
                self.waitingMove.dest_map = move['mapname']
                self.waitingMove.dest_x = move['x']
                self.waitingMove.dest_y = move['y']
                self.fp.write("moveout, " + mapname + "," + str(self.x)+", " + str(self.y) + "\n")
                return      
        # mainのreturnキャラ
        else:
            self.sender.send_event({"return": fromLine})
            returnResult = self.sender.receive_json()
            if returnResult['status'] == 'ok' and returnResult.get('finished', False):
                MSGWND.set(returnResult['message'], (['ステージ選択画面に戻る'], 'finished'))
                self.fp.write("finished\n")
                return
        MSGWND.set(returnResult['message'])
    
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
#        self.surface.convert_alpha()
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
        self.sender = sender
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

    def set(self, message, selectMessages=None):
        """メッセージをセットしてウィンドウを画面に表示する"""
        if message:
            if selectMessages is not None:
                self.selectMsgText, self.select_type = selectMessages
            self.cur_pos = 0
            self.cur_page = 0
            self.next_flag = False
            self.hide_flag = False
            print(message)
            # 全角スペースで初期化
            self.text = ""
            # メッセージをセット
            p = 0
            for ch in enumerate(message):
                if ch[1] == "/":  # /は改行文字
                    self.text += "/"
                    self.text += "　" * (self.max_chars_per_line - (p+1) % self.max_chars_per_line)
                    p = int(p//self.max_chars_per_line+1)*self.max_chars_per_line
                elif ch[1] == "%":  # \fは改ページ文字
                    self.text += "%"
                    self.text += "　" * (self.max_chars_per_page - (p+1) % self.max_chars_per_page)
                    p = int(p//self.max_chars_per_page+1)*self.max_chars_per_page
                else:
                    self.text += ch[1]
                    p += 1
            self.text += "$"  # 終端文字
            self.show()

    def update(self):
        """メッセージウィンドウを更新する
        メッセージが流れるように表示する"""
        if self.is_visible:
            if self.next_flag is False and self.hide_flag is False:
                self.cur_pos += 1  # 1文字流す
                # テキスト全体から見た現在位置
                p = self.cur_page * self.max_chars_per_page + self.cur_pos
                if self.text[p] == "/":  # 改行文字
                    self.cur_pos += self.max_chars_per_line
                    self.cur_pos = self.cur_pos//self.max_chars_per_line * self.max_chars_per_line
                elif self.text[p] == "%":  # 改ページ文字
                    self.cur_pos += self.max_chars_per_page
                    self.cur_pos = self.cur_pos//self.max_chars_per_page * self.max_chars_per_page
                elif self.text[p] == "$":  # 終端文字
                    self.hide_flag = True
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
            if ch == "/" or ch == "%" or ch == "$":
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
                        self.sender.send_event({"skip": True})
                        skipResult = self.sender.receive_json()
                        if skipResult.get('type', None) == 'doWhile':
                            move = PLAYER.move5History.pop()
                            # 暗転
                            DIMWND.setdf(200)
                            DIMWND.show()
                            fieldmap.create(move['mapname'])  # 移動先のマップで再構成
                            PLAYER.set_pos(move['x'], move['y'], DOWN)  # プレイヤーを移動先座標へ
                            PLAYER.commonItembag.items[-1] = move['cItems']
                            PLAYER.itembag.items[-1] = move['items']
                            fieldmap.add_chara(PLAYER)  # マップに再登録
                        self.set(skipResult['message'])
                        for itemName in skipResult.get('items', {}):
                            item = PLAYER.commonItembag.find(itemName)
                            if item is None:
                                item = PLAYER.itembag.find(itemName)
                            if item is not None:
                                if item.get_value() != skipResult['items'][itemName]:
                                    item.set_value(skipResult['items'][itemName])
                    else:
                        self.sender.send_event({"skip": False})
                        skipResult = self.sender.receive_json()
                        self.set(skipResult['message'])
                elif self.select_type == 'func_skip':
                    if self.selectMsgText[self.selectingIndex] == "はい":
                        self.sender.send_event({"skip": True})
                        skipResult = self.sender.receive_json()
                        self.set(skipResult['message'])
                        for name, value in skipResult["items"].items():
                            if (item := PLAYER.itembag.find(name)) is not None:
                                item.set_value(value)
                    else:
                        self.sender.send_event({"skip": False})
                        skipResult = self.sender.receive_json()
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
                        
                        newItems = []
                        for name, itemInfo in skipResult["skipTo"]["items"].items():
                            item = Item(name, itemInfo["value"], itemInfo["type"], False)
                            newItems.append(item)
                        PLAYER.itembag.items.append(newItems)
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
    """ポーズウィンドウ"""
    FONT_SIZE = 16
    TEXT_COLOR = (255, 255, 255)
    TO_GAME_BG_COLOR = (0, 0, 255) 
    TO_GAME_FONT_COLOR = (255, 255, 255)
    TO_SSELECT_BG_COLOR = (255, 0, 0) 
    TO_SSELECT_FONT_COLOR = (255, 255, 255)   

    def __init__(self, rect):
        Window.__init__(self, rect)
        self.font = pygame.freetype.Font(FONT_DIR + FONT_NAME, self.FONT_SIZE)
        self.button_toGame_rect = pygame.Rect(self.rect.width // 2 - 210, self.rect.height // 2 - 30, 200, 60)
        self.button_toStageSelect_rect = pygame.Rect(self.rect.width // 2 + 10, self.rect.height // 2 - 30, 200, 60)

    def draw(self, screen):
        """ポーズ画面を描画する"""
        Window.draw(self)
        if self.is_visible is False:
            return

        surf, rect = self.font.render("Pause", self.TEXT_COLOR)
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

    def draw_string(self, x, y, string, color):
        """文字列出力"""
        surf, rect = self.myfont.render(string, color)
        self.surface.blit(surf, (x, y+(self.FONT_HEIGHT+2)-rect[3]))

    def draw(self, screen):
        """メッセージを描画する
        メッセージウィンドウが表示されていないときは何もしない"""
        if not self.is_visible:
            return
        Window.draw(self)
        for i,item in enumerate(PLAYER.commonItembag.items[-1]):
            self.draw_string(10, 10 + i*25, f"{item.name:<8} ({item.value})", self.GREEN)
        gvarnum = len(PLAYER.commonItembag.items[-1])
        for j, item in enumerate(PLAYER.itembag.items[-1]):
            y = 10 + (gvarnum + j) * 25

            # 型に応じたアイコンを blit（描画）
            icon, constLock = self.itemChips.getChip(item.vartype)
            icon_x = 10
            icon_y = y
            text_x = icon_x + icon.get_width() + 6  # ← アイコン幅 + 余白（6px）

            if icon:
                self.surface.blit(icon, (icon_x, icon_y))

            if constLock:
                self.surface.blit(constLock, (icon_x + icon.get_width() - 12, icon_y))
                pass

            # アイコンの右に名前と値を描画
            self.draw_string(text_x, y, f"{item.name:<8}", self.WHITE)

            value_color = self.RED if item.undefined else self.WHITE
            value_offset = self.myfont.get_rect(item.name).width + 30
            self.draw_string(text_x + value_offset, y, f"({item.value})", value_color)

        Window.blit(self, screen)

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

    def __init__(self, rect, player):
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
    def __init__(self, pos, mapchip, sequence, type, fromTo):
        self.x, self.y = pos[0], pos[1]  # イベント座標
        self.mapchip = mapchip  # マップチップ
        self.sequence = sequence  # 移動シーケンス
        self.type = type # if, while, forで種類分け
        self.fromTo = fromTo
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
    def __init__(self, name, pos, direction, movetype, message, line):
        super().__init__(name, pos, direction, movetype, message)
        self.line = line
        
    def __str__(self):
        return f"CHARARETURN,{self.name:s},{self.x:d},{self.y:d},"\
            f"{self.direction:d},{self.movetype:d},{self.message:s},{self.line:d}"
    

#                                                                                                                                                                    
#   ,ad8888ba,  88                                           88b           d88                                    88888888888                                        
#  d8"'    `"8b 88                                           888b         d888                                    88                                          ,d     
# d8'           88                                           88`8b       d8'88                                    88                                          88     
# 88            88,dPPYba,  ,adPPYYba, 8b,dPPYba, ,adPPYYba, 88 `8b     d8' 88  ,adPPYba,  8b       d8  ,adPPYba, 88aaaaa 8b       d8  ,adPPYba, 8b,dPPYba, MM88MMM  
# 88            88P'    "8a ""     `Y8 88P'   "Y8 ""     `Y8 88  `8b   d8'  88 a8"     "8a `8b     d8' a8P_____88 88""""" `8b     d8' a8P_____88 88P'   `"8a  88     
# Y8,           88       88 ,adPPPPP88 88         ,adPPPPP88 88   `8b d8'   88 8b       d8  `8b   d8'  8PP""""""" 88       `8b   d8'  8PP""""""" 88       88  88     
#  Y8a.    .a8P 88       88 88,    ,88 88         88,    ,88 88    `888'    88 "8a,   ,a8"   `8b,d8'   "8b,   ,aa 88        `8b,d8'   "8b,   ,aa 88       88  88,    
#   `"Y8888Y"'  88       88 `"8bbdP"Y8 88         `"8bbdP"Y8 88     `8'     88  `"YbbdP"'      "8"      `"Ybbd8"' 88888888888 "8"      `"Ybbd8"' 88       88  "Y888  
#                                                                                                                                                                    
#                                                                                                                                                                    
# 

class CharaMoveEvent(Character):
    """キャラ＋移動"""
    def __init__(self, name, pos, direction, movetype, message, dest_map, dest_pos):
        super().__init__(name, pos, direction, movetype, message)
        self.dest_map = dest_map  # 移動先マップ名
        self.dest_x, self.dest_y = dest_pos[0], dest_pos[1]  # 移動先座標

    def __str__(self):
        return f"CHARAMOVE,{self.name:s},{self.x:d},{self.y:d},"\
            f"{self.direction:d},{self.movetype:d},{self.message:s},"\
            f"{self.dest_map},{self.dest_x},{self.dest_y}"
    
class CharaMoveItemsEvent(CharaMoveEvent):
    """キャラ＋移動(アイテム込み)"""
    def __init__(self, name, pos, direction, movetype, message, errmessage, dest_map, dest_pos, items, funcName, arguments):
        super().__init__(name, pos, direction, movetype, message, dest_map, dest_pos)
        self.items = items
        self.errmessage = errmessage
        self.funcName = funcName
        self.arguments = arguments

    def __str__(self):
        return f"CHARAMOVEITEMS,{self.name:s},{self.x:d},{self.y:d},"\
            f"{self.direction:d},{self.movetype:d},{self.message:s},{self.errmessage:s}"\
            f"{self.dest_map},{self.dest_x},{self.dest_y},{self.items},{self.funcName:s},{','.join(self.arguments)}"

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

    def __init__(self, pos, mapchip, dest_map, type, fromTo, dest_pos):
        self.x, self.y = pos[0], pos[1]  # イベント座標
        self.mapchip = mapchip  # マップチップ
        self.dest_map = dest_map  # 移動先マップ名
        self.type: str = type
        self.fromTo: list[int | None] = fromTo
        self.dest_x, self.dest_y = dest_pos[0], dest_pos[1]  # 移動先座標
        self.image = Map.images[self.mapchip]
        self.rect = self.image.get_rect(topleft=(self.x*GS, self.y*GS))

    def draw(self, screen, offset):
        """オフセットを考慮してイベントを描画"""
        offsetx, offsety = offset
        px = self.rect.topleft[0]
        py = self.rect.topleft[1]
        screen.blit(self.image, (px-offsetx, py-offsety))

    def __str__(self):
        return f"MOVE,{self.x},{self.y},{self.mapchip},{self.dest_map},{self.dest_x},{self.dest_y}"


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

    def __init__(self, pos, item, exp, refs, comments, vartype, linenum, funcWarp):
        self.font = pygame.freetype.SysFont("monospace", self.FONT_SIZE)
        self.x, self.y = pos[0], pos[1]  # 宝箱座標
        self.mapchip = 138  # 宝箱は138
        self.image = Map.images[self.mapchip]
        self.rect = self.image.get_rect(topleft=(self.x*GS, self.y*GS))
        self.item = item  # アイテム名
        self.exp = exp # アイテムの値の代入式
        self.refs = refs # アイテムを取得するのに必要なアイテム (変数)
        self.comments = comments # アイテムの値の設定(計算)がどのように行われたかを説明するコメント
        self.vartype = vartype # アイテムの型
        self.linenum = linenum # 宝箱を開けるタイミング
        self.funcWarp = funcWarp # 関数による遷移

    def open(self, value, undefined):
        """宝箱をあける"""
#        sounds["treasure"].play()
#        アイテムを追加する処理
        item = Item(self.item, value, self.vartype, undefined)
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
            # パディング値（上下左右の余白）
            padding = 4

            # 背景用の矩形（テキストサイズ + パディング）
            bg_rect = pygame.Rect(
                text_rect.left - padding,
                text_rect.top - padding,
                text_rect.width + 2 * padding,
                text_rect.height + 2 * padding
            )

            # 表示位置（中央寄せ）
            bg_rect.centerx = self.rect.centerx - offsetx
            bg_rect.bottom = self.rect.top - offsety  # 宝箱の上

            text_rect.center = bg_rect.center  # テキストを背景中央に配置

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
    """アイテム"""

    def __init__(self, name, value, vartype, undefined):
        self.name = str(name)
        self.value = value
        self.vartype = vartype
        self.undefined = undefined

    def get_value(self):
        """値を返す"""
        return self.value

    def set_value(self,val):
        """値をセット"""
        if val is not None:
            self.value = val
            self.undefined = False

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
        self.items = [[]]

    def add(self,item):
        """袋にアイテムを追加"""
        inbag = self.find(item.name)
        if inbag:
            inbag.value += 1
            #print(f"append item {item.name} + 1")
        else:
            self.items[-1].append(item)
            #print(f"append item {item.name}")

    def find(self,name) -> Item | None:
        """袋からアイテムを探す"""
        for i,n in enumerate(self.items[-1]):
            if n.name == name:
                return n
        return None

    def remove(self,name):
        """袋からアイテムを取り除く"""
        for i,n in enumerate(self.items[-1]):
            if n.name == name:
                return self.items[-1].pop(i)
        return None
    
                                                                                                                                                                                                     
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
    code_names = ["01_int_variables", "02_scalar_operations", "03_complex_operators", "04_conditional_branch", "05_loops_and_break", "06_function_definition", "07_function_in_condition", "08_array_1d"]
    SB_WIDTH = (SBW_WIDTH - 60) // 5
    SB_HEIGHT = SBW_HEIGHT // 2
    FONT_SIZE = 32
    FONT_COLOR = (255, 255, 255)

    def __init__(self):
        self.rect = pygame.Rect(0, 0, SBW_WIDTH , SBW_HEIGHT)
        self.surface = pygame.Surface((self.rect[2], self.rect[3]))
        self.surface.fill((128, 128, 128))
        self.is_visible = False  # ウィンドウを表示中か？
        self.button_stages: list[StageButton] = []
        self.scrollX = 0
        self.maxScrollX = (len(self.code_names) - 5) * (self.SB_WIDTH + 10)
        self.load_sb()
        self.font = pygame.freetype.Font(FONT_DIR + FONT_NAME, self.FONT_SIZE)

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

    def draw(self, screen):
        if self.is_visible:
            self.blit(screen)
            self.font.render_to(screen, (SBW_WIDTH // 2 - self.FONT_SIZE * 3, SBW_HEIGHT // 8), "ステージ選択", self.FONT_COLOR)
            for button in self.button_stages:
                button.draw(screen)

    def is_clicked(self,pos):
        for button in self.button_stages:
            if button.rect.collidepoint(pos):
                return button.code_name
        return None
    

                                                                                                                     
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
        self.code_name = code_name
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
        Window.draw(self)
        if not self.is_visible:
            return
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
    offset_y = 0
    radius = 0
    RED = (255, 0, 0)
    BLUE = (0, 0, 255)
    BLACK = (0, 0, 0)

    def __init__(self, rect, name):
        self.offset_x = SCR_WIDTH - MIN_MAP_SIZE
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
                pos_x = x * MIN_MAP_SIZE/ self.tile_num + self.offset_x
                pos_y = y * MIN_MAP_SIZE / self.tile_num + self.offset_y
                image = pygame.transform.scale(self.images[tile], (int(MIN_MAP_SIZE / self.tile_num), int(MIN_MAP_SIZE / self.tile_num)))
                screen.blit(image, (pos_x, pos_y))
        
        # Playerの場所を表示　赤丸
        px = PLAYER.x * MIN_MAP_SIZE / self.tile_num + self.offset_x + MIN_MAP_SIZE/ self.tile_num  // 2
        py = PLAYER.y * MIN_MAP_SIZE / self.tile_num + self.offset_y+ MIN_MAP_SIZE/ self.tile_num  // 2
        pygame.draw.circle(screen, self.RED, (px, py), self.radius)

        # Player以外のCharacterの場所を表示　黒丸
        for chara in map.charas:
            if not isinstance(chara, Player):
                cx = chara.x * MIN_MAP_SIZE / self.tile_num + self.offset_x + MIN_MAP_SIZE/ self.tile_num  // 2
                cy = chara.y * MIN_MAP_SIZE / self.tile_num + self.offset_y+ MIN_MAP_SIZE/ self.tile_num  // 2
                pygame.draw.circle(screen, self.BLACK, (cx, cy), self.radius)
        # Treasureの場所を表示　青丸
        for event in map.events:
            if isinstance(event, Treasure):
                tx = event.x * MIN_MAP_SIZE / self.tile_num + self.offset_x + MIN_MAP_SIZE/ self.tile_num  // 2
                ty = event.y * MIN_MAP_SIZE / self.tile_num + self.offset_y+ MIN_MAP_SIZE/ self.tile_num  // 2
                pygame.draw.circle(screen, self.BLUE, (tx, ty), self.radius)
    


                                                                                                                                   
#   ,ad8888ba,                       88          I8,        8        ,8I 88                      88                                 
#  d8"'    `"8b                      88          `8b       d8b       d8' ""                      88                                 
# d8'                                88           "8,     ,8"8,     ,8"                          88                                 
# 88             ,adPPYba,   ,adPPYb,88  ,adPPYba, Y8     8P Y8     8P   88 8b,dPPYba,   ,adPPYb,88  ,adPPYba,  8b      db      d8  
# 88            a8"     "8a a8"    `Y88 a8P_____88 `8b   d8' `8b   d8'   88 88P'   `"8a a8"    `Y88 a8"     "8a `8b    d88b    d8'  
# Y8,           8b       d8 8b       88 8PP"""""""  `8a a8'   `8a a8'    88 88       88 8b       88 8b       d8  `8b  d8'`8b  d8'   
#  Y8a.    .a8P "8a,   ,a8" "8a,   ,d88 "8b,   ,aa   `8a8'     `8a8'     88 88       88 "8a,   ,d88 "8a,   ,a8"   `8bd8'  `8bd8'    
#   `"Y8888Y"'   `"YbbdP"'   `"8bbdP"Y8  `"Ybbd8"'    `8'       `8'      88 88       88  `"8bbdP"Y8  `"YbbdP"'      YP      YP      
                                                                                                                                                                                                                                                    
class CodeWindow(Window, Map):
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
                            PLAYER.itembag.remove(item)
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