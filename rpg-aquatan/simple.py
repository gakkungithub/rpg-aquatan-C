#!/usr/bin/env python3
"""RPGあくあたん"""
import codecs
import os
import random
import struct
import sys
import re
# socket通信を行う
import socket
import json
import time
import datetime
import argparse
from threading import Thread
from configparser import ConfigParser
import ephem
#from genericpath import exists
import pygame
import pygame.freetype
from pygame.locals import *

import time

parser = argparse.ArgumentParser()
parser.add_argument('-f', '--fullscreen', dest='fullscreen',
                  action='store_true', default=False,
                  help='show in fullscreen mode (Mac)')
parser.add_argument('-S', '--screenshot', dest='screenshot', type=int,
                  action='store', default=0, metavar = 'INTERVAL',
                  help='Take a screenshot by specified secs')
parser.add_argument('--screenshot_file', dest='scrfile', default="sshot.png",
                  action="store",
                  metavar="FILE",
                  help='specify screenshot file')
parser.add_argument('--light', dest='light', default=False,
                  action="store_true",
                  help='use time info and light control')
parser.add_argument('-d', '--dark', dest='dark',
                  action="store_true",
                  help='use spotlight mode in dark dangeon')
parser.add_argument('-i', '--inifile', dest='inifile', default="simple.ini",
                  action="store",
                  metavar="FILE",
                  help='specify ini file')
parser.add_argument('-b', '--fb', dest='fb', default="/dev/fb1",
                  action="store",
                  metavar="FRAMEBUFFER",
                  help='specify framebuffer')
parser.add_argument('-t', '--time', dest='fixedtime',
                  action="store", metavar="TIME",
                  help='set fixed datetime')
parser.add_argument('-D', '--debug', dest='debug',
                  action="store_true",
                  help='debug mode')
args = parser.parse_args()

config = ConfigParser()
config.read(args.inifile)

FONT_DIR = './font/'
if os.uname()[0] != 'Darwin':
    os.environ["SDL_FBDEV"] = args.fb

#FONT_NAME = "Boku2-Regular.otf"
#FONT_NAME = "logotypejp_mp_b_1.ttf"
#FONT_NAME = "rounded-mgenplus-1cp-bold.ttf"
FONT_NAME = "PixelMplus12-Bold.ttf"

SCR_WIDTH = int(config.get('screen', 'width'))
SCR_HEIGHT = int(config.get('screen', 'height'))

MAX_FRAME_PER_SEC = config.getint('screen', 'fps', fallback=24)
CURRENT_FRAME_PER_SEC = 24
SCR_RECT = Rect(0, 0, SCR_WIDTH, SCR_HEIGHT)
GS = 32
DOWN, LEFT, RIGHT, UP = 0, 1, 2, 3
MSGWAIT = 3 * MAX_FRAME_PER_SEC
DB_CHECK_WAIT = 30 * MAX_FRAME_PER_SEC
SS_CHECK_WAIT = args.screenshot * MAX_FRAME_PER_SEC

STOP, MOVE = 0, 1  # 移動タイプ
PROB_MOVE = 0.0075  # 移動確率
TRANS_COLOR = (190, 179, 145)  # マップチップの透明色

URL = str(config.get('api', 'url'))

MSGWND = None
DIMWND = None
LIGHTWND = None
STATUSWND = None
ITEMWND = None

PLAYER = None

e = []
AUTOMOVE = 1



## start

BUTTON_WINDOW = None
BUTTON_WIDTH = 50
PATH = 'foot_print.csv'
TXTBOX_HEIGHT = 40
SCR_RECT_WITH_TXTBOX = Rect(0, 0, SCR_WIDTH, SCR_HEIGHT)
TXTBOX_RECT = Rect(0, SCR_HEIGHT - TXTBOX_HEIGHT, SCR_WIDTH, TXTBOX_HEIGHT)

## JK add here!!
## ミニマップの表示座標を設定する
MIN_MAP_SIZE = 300
MMAP_RECT = Rect(SCR_WIDTH - MIN_MAP_SIZE - 10, 10, MIN_MAP_SIZE, MIN_MAP_SIZE)

## デバッグコードの表示座標を設定する
MIN_CODE_SIZE_Y = 600
MCODE_RECT = Rect(SCR_WIDTH - MIN_MAP_SIZE - 10, 10, MIN_MAP_SIZE, MIN_CODE_SIZE_Y)


cmd = "aquatan"
# time [ms]
INTERVAL = 100
mouse_down = False
last_action_time = 0

LONGPRESS_EVENT = pygame.USEREVENT + 1

def start_timer():
    pygame.time.set_timer(LONGPRESS_EVENT, 200)
def end_timer():
    pygame.time.set_timer(LONGPRESS_EVENT, 0)
## end 

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
    pygame.init()

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
        if args.fullscreen:
            print("Full screen mode")
            scropt = FULLSCREEN | DOUBLEBUF | HWSURFACE
        else:
            scropt = DOUBLEBUF | HWSURFACE
        screen = pygame.display.set_mode(SCR_RECT_WITH_TXTBOX.size, scropt)

    # region コマンドラインの設定
    pygame.draw.rect(screen, (0,0,0), TXTBOX_RECT)

    font = pygame.font.Font(None, 36)
    text_surface = font.render("Command Box:", True, (255, 255, 255))
    screen.blit(text_surface, (10, SCR_RECT.height + 10))
    input_text = "hogehoge"
    input_surface = font.render(input_text, True, (255, 255, 255))
    screen.blit(input_surface, (10, SCR_RECT.height + 40))

    pygame.display.update()
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
    # endregion

    BTNWND = buttonWindow()
    BTNWND.show()
    mouse_down = False
    
    # 初期アイテムの設定(グローバル変数)
    for itemName in items.keys():
        #このitemValueをアイテムの初期値として設定するつもりです!!
        item = Item(itemName)
        # ここで変数名を送信してその初期値を取得する(グローバル変数のみ)
        item.set_value(get_exp_value(items[itemName]))
        PLAYER.commonItembag.add(item)

    fieldmap = Map(mapname)
    fieldmap.add_chara(PLAYER)

    # region ウィンドウの設定
    message_engine = MessageEngine()
    MSGWND = MessageWindow(
        Rect( SCR_WIDTH // 4 , SCR_HEIGHT // 3 * 2, 
             SCR_WIDTH // 2, SCR_HEIGHT // 4), message_engine)
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
    msgwincount = 0
    db_check_count = 0
    ss_check_count = 0

    print("6")
    lightrooms = []
    messages = []
    lightrooms = list(set(lightrooms))
    LIGHTWND.set_rooms(lightrooms)
    if len(messages) > 0:
        MSGWND.set("/".join(messages))

    PLAYER.fp.write( "start," + mapname + "," + str(PLAYER.x)+", " + str(PLAYER.y) + "\n")
    start_time = time.time()

#    if args.screenshot:
#        MSGWND.hide()
#        offset = calc_offset(PLAYER)
#        fieldmap.update()
#        fieldmap.draw(screen, offset)
#        pygame.display.update()
#        pygame.image.save(screen, "screenshot.png")
#        sys.exit()

    #current_place = OMZN_STATUS.current_place()
    # 並列処理の接続開始はこれの前、データの送受信処理はこれ以降に書くことになる。

    # # main関数開始時の処理を送信する(今は何もない想定でパスする)。
    # sender.send_event({"pass": "begin"})

    while True:
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

        # region 時間の設定
        if args.fixedtime:
            current_utc_date = datetime.datetime.strptime(
                datetime.datetime.strptime(args.fixedtime,"%Y-%m-%d %H:%M").strftime("%Y-%m-%d")
                                           + " 12:00 +0900",
                                                           "%Y-%m-%d %H:%M %z")
            current_date = datetime.datetime.strptime(args.fixedtime, "%Y-%m-%d %H:%M")
        else:
            current_utc_date = datetime.datetime.strptime(
                datetime.datetime.now().strftime("%Y-%m-%d") + " 12:00 +0900",
                                                           "%Y-%m-%d %H:%M %z")
            current_date = datetime.datetime.now()
        sunrize, sunset = get_sunrise_sunset(current_utc_date)
#        print(sunrize.strftime("%Y-%m-%d %H:%M"))
#        print(sunset.strftime("%Y-%m-%d %H:%M"))
        td = (sunset - sunrize) / 8.0
#        print(td.total_seconds())
#        print((sunrize + td ).strftime("%Y-%m-%d %H:%M"))
        if current_date < sunrize - td / 2:
            light_mode = "night"
        elif current_date >= sunrize - td / 2 and current_date < sunrize + td * 2:
            light_mode = "morning"
        elif current_date >= sunset - td * 3 / 2 and current_date < sunset:
            light_mode = "evening"
        elif current_date >= sunset and current_date < sunset + td / 2:
            light_mode = "dusk"
        elif current_date >= sunset + td / 2:
            light_mode = "night"
        else:
            light_mode = "normal"
        if args.dark:
            LIGHTWND.set_color_scene("midnight")
        elif args.light:
            LIGHTWND.set_color_scene(light_mode)
        else:
            LIGHTWND.set_color_scene("normal")
        # endregion

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

        ## JK add here!!
        MMAPWND.draw(screen)
        CODEWND.draw(screen)

        show_info(screen, PLAYER, clock, current_date, sunrize, sunset, light_mode, start_time)
        pygame.display.update()

        if args.screenshot > 0 :
            if ss_check_count > SS_CHECK_WAIT:
                ss_check_count = 0
                pygame.image.save(screen, args.scrfile)
            ss_check_count = ss_check_count + 1

        if MSGWND.is_visible:
            msgwincount = msgwincount + 1

        n_move = PLAYER.get_next_automove()
        if n_move is not None and n_move == 's':
            PLAYER.pop_automove()
            treasure = PLAYER.search(fieldmap)
            if treasure is not None:
                ### ここで宝箱を開けたことの情報を送信する
                sender.send_event({"item": treasure.item})
                itemResult = sender.receive_json()
                if itemResult is not None:
                    if itemResult['status'] == "ok":
                        treasure.open(itemResult['value'])
                        MSGWND.set(f"宝箱を開けた！/「{treasure.item}」を手に入れた！")
                        fieldmap.remove_event(treasure)
                    else:
                        MSGWND.set(itemResult['message'])
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
                sys.exit()
            if event.type == KEYDOWN and event.key == K_ESCAPE:
                PLAYER.fp.write( "end, " + mapname + "," + str(PLAYER.x)+", " + str(PLAYER.y) + "\n")
                PLAYER.fp.close()
                sys.exit()

            # region mouse click event
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    mouse_down = True
                    start_timer()
                    cmd = BTNWND.is_clicked(event.pos)
            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    mouse_down = False
                    end_timer()
            if mouse_down:
                if mouse_down:
                    cmd = BTNWND.is_clicked(pygame.mouse.get_pos())
            # endregion
            
            # region keydown event
            ## open map
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
                    PLAYER.fp.write( "undo, " + mapname + "," + str(PLAYER.x)+", " + str(PLAYER.y) + "\n")
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
                            elif value.startswith("+"):
                                value = str(int(current_value) + int(value[1:]))
                            elif value.startswith("-"):
                                value = str(int(current_value) - int(value[1:]))

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
                                            item = Item(argument)
                                            item.value = 1
                                            newItems.append(item)
                                        PLAYER.itembag.items.append(newItems)
                                        PLAYER.waitingMove = chara
                                        PLAYER.moveHistory.append({'mapname': mapname, 'x': PLAYER.x, 'y': PLAYER.y})
                                else:
                                    PLAYER.waitingMove = chara
                                    PLAYER.moveHistory.append({'mapname': mapname, 'x': PLAYER.x, 'y': PLAYER.y})
                                    PLAYER.move5History.append({'mapname': mapname, 'x': PLAYER.x, 'y': PLAYER.y, 'cItems': PLAYER.commonItembag.items[-1], 'items': PLAYER.itembag.items[-1], 'return': False})
                                    if len(PLAYER.move5History) > 5:
                                        PLAYER.move5History.pop(0)
                            elif isinstance(chara, CharaReturn):
                                PLAYER.move5History.append({'mapname': mapname, 'x': PLAYER.x, 'y': PLAYER.y, 'cItems': PLAYER.commonItembag.items[-1], 'items': PLAYER.itembag.items[-1], 'return':True})
                                if len(PLAYER.move5History) > 5:
                                    PLAYER.move5History.pop(0)
                                PLAYER.waitingMove = chara
                                PLAYER.set_waitingMove_return()
                                if len(PLAYER.itembag.items) != 1:
                                    PLAYER.itembag.items.pop()
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

            if event.type == KEYDOWN and event.key == K_s:
                pygame.image.save(screen, args.scrfile)

            if (event.type == KEYDOWN and (event.key == K_SPACE or event.key == K_RETURN)) or cmd == "action":
                cmd = ""
                if MSGWND.is_visible:
                    # メッセージウィンドウ表示中なら次ページへ
                    MSGWND.next()
                    msgwincount = 0
                else:
                    # 宝箱を調べる
                    treasure = PLAYER.search(fieldmap)
                    if treasure is not None:
                        ### ここで宝箱を開けたことの情報を送信する
                        sender.send_event({"item": treasure.item})
                        itemResult = sender.receive_json()
                        if itemResult is not None:
                            if itemResult['status'] == "ok":
                                treasure.open(itemResult['value'])
                                MSGWND.set(f"宝箱を開けた！/「{treasure.item}」を手に入れた！")
                                fieldmap.remove_event(treasure)
                                PLAYER.fp.write( "itemget, " + mapname + "," + str(PLAYER.x)+", " + str(PLAYER.y) + "," + treasure.item + "\n")
                            else:
                                MSGWND.set(itemResult['message'])
                        continue

                    # ドアを開ける
                    door = PLAYER.unlock(fieldmap)
                    if door is not None:
                        door.open()
                        MSGWND.set(f"{door.doorname}を開けた！")
                        fieldmap.remove_event(door)
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
                                        item = Item(argument)
                                        item.value = 1
                                        newItems.append(item)
                                    PLAYER.itembag.items.append(newItems)
                                    PLAYER.waitingMove = chara
                                    PLAYER.moveHistory.append({'mapname': mapname, 'x': PLAYER.x, 'y': PLAYER.y})
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
                                # ここでreturnの是非を確かめる (キャラ分けは行数で行う)
                                sender.send_event({"return": chara.line})
                                returnResult = sender.receive_json()
                                if returnResult['status'] == 'ok':
                                    PLAYER.move5History.append({'mapname': mapname, 'x': PLAYER.x, 'y': PLAYER.y, 'cItems': PLAYER.commonItembag.items[-1], 'items': PLAYER.itembag.items[-1], 'return':True})
                                    if len(PLAYER.move5History) > 5:
                                        PLAYER.move5History.pop(0)
                                    PLAYER.waitingMove = chara
                                    PLAYER.set_waitingMove_return()
                                    if len(PLAYER.itembag.items) != 1:
                                        PLAYER.itembag.items.pop()
                                    PLAYER.fp.write("moveout, " + mapname + "," + str(PLAYER.x)+", " + str(PLAYER.y) + "\n")
                                MSGWND.set(returnResult['message'])
                    else:
                        MSGWND.set("そのほうこうには　だれもいない。")
            # endregion
        if msgwincount > MSGWAIT:
            # 5秒ほったらかし
            if MSGWND.is_visible:
                # メッセージウィンドウ表示中なら次ページへ
                MSGWND.next()
            msgwincount = 0
        pygame.display.flip()

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
#           88                                                   88               ad88             
#           88                                                   ""              d8"               
#           88                                                                   88                
# ,adPPYba, 88,dPPYba,   ,adPPYba,  8b      db      d8           88 8b,dPPYba, MM88MMM ,adPPYba,   
# I8[    "" 88P'    "8a a8"     "8a `8b    d88b    d8'           88 88P'   `"8a  88   a8"     "8a  
#  `"Y8ba,  88       88 8b       d8  `8b  d8'`8b  d8'            88 88       88  88   8b       d8  
# aa    ]8I 88       88 "8a,   ,a8"   `8bd8'  `8bd8'             88 88       88  88   "8a,   ,a8"  
# `"YbbdP"' 88       88  `"YbbdP"'      YP      YP               88 88       88  88    `"YbbdP"'   
#                                                                                                  
#                                                     888888888888                                 
# 

def show_info(screen,  player, clock, now, sunrize, sunset, light_mode, start_time):
    """デバッグ情報を表示"""
#    ts_now = now.strftime("%Y-%m-%d %H:%M")
#    ts_sunrize = sunrize.strftime("%H:%M")
#    ts_sunset = sunset.strftime("%H:%M")
#    draw_string(screen, 0, 10, f"Current:{ts_now} {light_mode}",Color(255, 255, 255, 128))
#    draw_string(screen, 0, 30, f"Sunrize:{ts_sunrize}",Color(255, 0, 0, 128))
#    draw_string(screen, 0, 50, f"Sunset: {ts_sunset}",Color(0, 0, 255, 128))
    draw_string(screen, SCR_WIDTH-60, 10,
                f"{player.x},{player.y}", Color(255, 255, 255, 128))  # プレイヤー座標
#    draw_string(screen, SCR_WIDTH-60,30, "%s" % player.place_label, Color(0,255,255,128))
#    draw_string(screen, SCR_WIDTH-60,50, "%s" % OMZN_STATUS.current_place(), Color(255,255,0,128))
    draw_string(screen, SCR_WIDTH-60, 30, f"{clock.get_fps():.1f}", Color(255, 255, 255, 128))
    current_time =  time.time() - start_time
    draw_string(screen, SCR_WIDTH-60, 50, f"{current_time:.1f}", Color(255, 255, 255, 128))


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
            if transparent == 0:
                Map.images.append(load_image("mapchip", f"{mapchip_name}.png", -1))
            else:
                Map.images.append(load_image("mapchip", f"{mapchip_name}.png", TRANS_COLOR))
            Map.movable_type.append(movable)


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
        file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", self.name.lower(), self.name.lower() + ".json")
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
        treasure = Treasure((x, y), item)
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
        door = SmallDoor((x, y), name)
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

    def update(self, mymap):
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

                # 接触イベントチェック
                event = mymap.get_event(self.x, self.y)
                if isinstance(event, MoveEvent):  # MoveEventなら
                    self.sender.send_event({"type": event.type, "fromTo": event.fromTo})
                    moveResult = self.sender.receive_json()
                    if moveResult and moveResult['status'] == "ok":
                        dest_map = event.dest_map
                        dest_x = event.dest_x
                        dest_y = event.dest_y

                        # region command
                        from_map = mymap.name
                        self.move5History.append({'mapname': from_map, 'x': self.x, 'y': self.y, 'cItems': self.commonItembag.items[-1], 'items': self.itembag.items[-1], 'return':False})
                        if len(self.move5History) > 5:
                            self.move5History.pop(0)
                        # endregion
                        # 暗転
                        DIMWND.setdf(200)
                        DIMWND.show()
                        mymap.create(dest_map)  # 移動先のマップで再構成
                        self.set_pos(dest_x, dest_y, DOWN)  # プレイヤーを移動先座標へ
                        mymap.add_chara(self)  # マップに再登録
                        self.fp.write("jump, " + dest_map + "," + str(self.x)+", " + str(self.y) + "\n")
                    else:
                        if self.prevPos[1][1] - self.prevPos[0][1] == 1:
                            self.vx, self.vy = 0, -self.speed
                            self.moving = True
                        elif self.prevPos[1][0] - self.prevPos[0][0] == -1:
                            self.vx, self.vy = self.speed, 0
                            self.moving = True
                        elif self.prevPos[1][0] - self.prevPos[0][0] == 1:
                            self.vx, self.vy = -self.speed, 0
                            self.moving = True
                        else:
                            self.vx, self.vy = 0, self.speed
                            self.moving = True
                                                    
                        self.prevPos = [None, self.prevPos[0]]
                        MSGWND.set(moveResult['message'])
                elif isinstance(event, PlacesetEvent):  # PlacesetEventなら
                    self.place_label = event.place_label
                elif isinstance(event, AutoEvent):  # AutoEvent
#                    print(f"append_automove({event.sequence})")
                    self.append_automove(event.sequence, type=event.type, fromTo=event.fromTo)
                    return
        elif self.waitingMove is not None:
#                print(f"waitingMove:{self.waitingMove}")
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
        """足もとに宝箱があるか調べる"""
        event = mymap.get_event(self.x, self.y)
        if isinstance(event, Treasure):
            return event
        return None

    def unlock(self, mymap):
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
        if isinstance(event, Door) or isinstance(event, SmallDoor) :
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

    def set_waitingMove_return(self):
        """returnの案内人に話しかけた時、動的にwaitingMoveを設定する"""
        if self.moveHistory != []:
            move = self.moveHistory.pop()
            self.waitingMove.dest_map = move['mapname']
            self.waitingMove.dest_x = move['x']
            self.waitingMove.dest_y = move['y']
        else:
            self.waitingMove = None



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

    def __init__(self, rect, msg_eng):
        Window.__init__(self, rect)
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

    def set(self, message):
        """メッセージをセットしてウィンドウを画面に表示する"""
        self.cur_pos = 0
        self.cur_page = 0
        self.next_flag = False
        self.hide_flag = False
        # 全角スペースで初期化
        self.text = ['　'] * (self.MAX_LINES*self.max_chars_per_line)
        # メッセージをセット
        p = 0
        for ch in enumerate(message):
            if ch[1] == "/":  # /は改行文字
                self.text[p] = "/"
                p += self.max_chars_per_line
                p = int(p//self.max_chars_per_line)*self.max_chars_per_line
            elif ch[1] == "%":  # \fは改ページ文字
                self.text[p] = "%"
                p += self.max_chars_per_page
                p = int(p//self.max_chars_per_page)*self.max_chars_per_page
            else:
                self.text[p] = ch[1]
                p += 1
        self.text[p] = "$"  # 終端文字
        self.show()

    def update(self):
        """メッセージウィンドウを更新する
        メッセージが流れるように表示する"""
        if self.is_visible:
            if self.next_flag is False:
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
        Window.blit(self, screen)

    def next(self):
        """メッセージを先に進める"""
        # 現在のページが最後のページだったらウィンドウを閉じる
        if self.hide_flag:
            self.hide()
        # ▼が表示されてれば次のページへ
        if self.next_flag:
            self.cur_page += 1
            self.cur_pos = 0
            self.next_flag = False

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

    def __init__(self, rect,player):
        Window.__init__(self, rect)
        self.text_rect = self.inner_rect.inflate(-2, -2)  # テキストを表示する矩形
        self.myfont = pygame.freetype.Font(
            FONT_DIR + FONT_NAME, self.FONT_HEIGHT)
        self.color = self.WHITE
        self.player = player

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
            self.draw_string(10, 10 + i*20, f"{item.name:<8} ({item.value})", self.GREEN)
        gvarnum = len(PLAYER.commonItembag.items[-1])
        for j,item in enumerate(PLAYER.itembag.items[-1]):
            self.draw_string(10, 10 + (gvarnum+j)*20, f"{item.name:<8} ({item.value})", self.WHITE)

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

    def __init__(self, pos, item):
        self.x, self.y = pos[0], pos[1]  # 宝箱座標
        self.mapchip = 138  # 宝箱は138
        self.image = Map.images[self.mapchip]
        self.rect = self.image.get_rect(topleft=(self.x*GS, self.y*GS))
        self.item = item  # アイテム名

    def open(self, value):
        """宝箱をあける"""
#        sounds["treasure"].play()
#        アイテムを追加する処理
        item = Item(self.item, value)
        PLAYER.itembag.items[-1].append(item)

    def draw(self, screen, offset):
        """オフセットを考慮してイベントを描画"""
        offsetx, offsety = offset
        px = self.rect.topleft[0]
        py = self.rect.topleft[1]
        screen.blit(self.image, (px-offsetx, py-offsety))

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
    def __init__(self, pos, name):
        self.mapchip = 27
        self.mapchip_list = [27,688]
        self.status = 0 # close
        self.x, self.y = pos[0], pos[1]  # ドア座標
        self.doorname = str(name)  # ドア名
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

    def find(self,name):
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

    def __init__(self,name,value):
        self.name = str(name)
        self.value = value

    def get_value(self):
        """値を返す"""
        return self.value

    def set_value(self,val):
        """値をセット"""
        if val is not None:
            self.value = val

                                                                                                                                              
# 88                                                           I8,        8        ,8I 88                      88                                 
# 88                        ,d      ,d                         `8b       d8b       d8' ""                      88                                 
# 88                        88      88                          "8,     ,8"8,     ,8"                          88                                 
# 88,dPPYba,  88       88 MM88MMM MM88MMM ,adPPYba,  8b,dPPYba,  Y8     8P Y8     8P   88 8b,dPPYba,   ,adPPYb,88  ,adPPYba,  8b      db      d8  
# 88P'    "8a 88       88   88      88   a8"     "8a 88P'   `"8a `8b   d8' `8b   d8'   88 88P'   `"8a a8"    `Y88 a8"     "8a `8b    d88b    d8'  
# 88       d8 88       88   88      88   8b       d8 88       88  `8a a8'   `8a a8'    88 88       88 8b       88 8b       d8  `8b  d8'`8b  d8'   
# 88b,   ,a8" "8a,   ,a88   88,     88,  "8a,   ,a8" 88       88   `8a8'     `8a8'     88 88       88 "8a,   ,d88 "8a,   ,a8"   `8bd8'  `8bd8'    
# 8Y"Ybbd8"'   `"YbbdP'Y8   "Y888   "Y888 `"YbbdP"'  88       88    `8'       `8'      88 88       88  `"8bbdP"Y8  `"YbbdP"'      YP      YP      

class buttonWindow:
    """ボタンウィンドウ"""
    def __init__(self):
        self.rect = pygame.Rect(SCR_WIDTH - 3*BUTTON_WIDTH, SCR_HEIGHT - 2*BUTTON_WIDTH, BUTTON_WIDTH, BUTTON_WIDTH)
        self.surface = pygame.Surface((self.rect[2], self.rect[3]), pygame.SRCALPHA)
        self.is_visible = False  # ウィンドウを表示中か？
        self.button_right = Button("arrow.png", self.rect[0] + BUTTON_WIDTH*2, self.rect[1] + BUTTON_WIDTH, 0)
        self.button_left = Button("arrow.png", self.rect[0] + 0, self.rect[1] + BUTTON_WIDTH, 180)
        self.button_up = Button("arrow.png", self.rect[0] + BUTTON_WIDTH, self.rect[1] + 0,90)
        self.button_down = Button("arrow.png", self.rect[0] + BUTTON_WIDTH, self.rect[1] + BUTTON_WIDTH,-90)
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

    def __init__(self,file_plase,pos_x,pos_y,angle):
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


## JK add here!!
class MiniMapWindow(Window, Map):
    """"ミニマップウィンドウ"""
    tile_num = 60
    offset_x = 0
    offset_y = 0
    border = 20
    radius = 0
    RED = (255, 0, 0)

    def __init__(self, rect, name):
        self.offset_x = SCR_WIDTH - MIN_MAP_SIZE - self.border
        self.offset_y = self.border
        self.radius = MIN_MAP_SIZE / self.tile_num
        Window.__init__(self, rect)
        Map.__init__(self, name)
        self.hide()

    def draw(self, screen):
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
        px = PLAYER.x * MIN_MAP_SIZE/ self.tile_num + self.offset_x + MIN_MAP_SIZE/ self.tile_num  // 2
        py = PLAYER.y * MIN_MAP_SIZE / self.tile_num + self.offset_y+ MIN_MAP_SIZE/ self.tile_num  // 2
        pygame.draw.circle(screen, self.RED, (px, py), self.radius)
    


                                                                                                                                   
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
    FONT_SIZE = 16
    HIGHLIGHT_COLOR = (0, 0, 255)
    TEXT_COLOR = (255, 255, 255)
    BG_COLOR = (30, 30, 30)

    def __init__(self, rect, name, highlight_lines=None):
        Window.__init__(self, rect)
        Map.__init__(self, name)
        self.font = pygame.font.SysFont("monospace", self.FONT_SIZE)
        self.c_file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", name.lower(), name.lower() + ".c")
        self.lines = self.load_code_lines()
        self.linenum = self.load_first_code_line()
        self.hide()

    def load_code_lines(self):
        """Cファイルからコードを読み込む"""
        if not os.path.exists(self.c_file_path):
            return ["// File not found"]
        with open(self.c_file_path, 'r') as f:
            return f.readlines()

    def load_first_code_line(self):
        cnt = 0
        for idx, line in enumerate(self.lines):
            if line.strip() and not line.strip().startswith('//') and not line.strip().startswith('#'):
                cnt += 1
                if cnt == 2:
                    return idx + 1  # 行番号として返す
        return 1  # fallback
    
    def update_code_line(self, linenum):
        self.linenum = linenum

    def draw(self, screen):
        if not self.is_visible:
            return
        Window.draw(self)
        Window.blit(self, screen)

        x_offset = SCR_WIDTH - MIN_MAP_SIZE
        y_offset = 20

        # iは行数なので、これと現在の行数-1が合致した場合光かがやかせる
        for i, line in enumerate(self.lines):
            rendered_line = self.font.render(line.rstrip(), True, self.TEXT_COLOR)

            if (i + 1) == self.linenum:
                # ハイライト背景描画
                bg_rect = pygame.Rect(
                    x_offset - 5,
                    y_offset,
                    self.rect.width - 20,
                    self.FONT_SIZE + 4
                )
                pygame.draw.rect(screen, self.HIGHLIGHT_COLOR, bg_rect)

            screen.blit(rendered_line, (x_offset, y_offset))
            y_offset += self.FONT_SIZE + 4

# 88888888888                                        ad88888ba                                  88                        
# 88                                          ,d    d8"     "8b                                 88                        
# 88                                          88    Y8,                                         88                        
# 88aaaaa 8b       d8  ,adPPYba, 8b,dPPYba, MM88MMM `Y8aaaaa,    ,adPPYba, 8b,dPPYba,   ,adPPYb,88  ,adPPYba, 8b,dPPYba,  
# 88""""" `8b     d8' a8P_____88 88P'   `"8a  88      `"""""8b, a8P_____88 88P'   `"8a a8"    `Y88 a8P_____88 88P'   "Y8  
# 88       `8b   d8'  8PP""""""" 88       88  88            `8b 8PP""""""" 88       88 8b       88 8PP""""""" 88          
# 88        `8b,d8'   "8b,   ,aa 88       88  88,   Y8a     a8P "8b,   ,aa 88       88 "8a,   ,d88 "8b,   ,aa 88          
# 88888888888 "8"      `"Ybbd8"' 88       88  "Y888  "Y88888P"   `"Ybbd8"' 88       88  `"8bbdP"Y8  `"Ybbd8"' 88          

class EventSender:
    def __init__(self, code_window: CodeWindow, host='localhost', port=9999):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.code_window = code_window
        try:
            self.sock.connect((host, port))
        except Exception as e:
            print(f"Error connecting to {host}:{port} -> {e}")
            raise

    def send_event(self, event):
        self.sock.sendall(json.dumps(event).encode() + b'\n')  # 改行区切りで複数送信可能

    def receive_json(self):
        buffer = ""
        while True:
            data = self.sock.recv(1024)
            if not data:
                return None  # 接続が閉じられた
            buffer += data.decode()
            try:
                msg = json.loads(buffer)
                if "line" in msg:
                    self.code_window.update_code_line(msg["line"])
                return msg
            except json.JSONDecodeError:
                continue  # JSONがまだ完全でないので続けて待つ
        
    def close(self):
        self.sock.close()
  
if __name__ == "__main__":
    main()