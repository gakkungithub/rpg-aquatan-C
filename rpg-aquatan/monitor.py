#!/usr/bin/env python3
"""RPGあくあたん"""
import codecs
import os
import re
import random
import struct
import sys
import json
import time
import datetime
import argparse
from threading import Thread
from time import strftime
from configparser import ConfigParser
import ephem
#from genericpath import exists
import requests
import pygame
import pygame.freetype
from pygame.locals import *


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
parser.add_argument('-j', '--json', dest='json', default=True,
                  action="store_true",
                  help='use json format as map data')
parser.add_argument('-i', '--inifile', dest='inifile', default="room.ini",
                  action="store",
                  metavar="FILE",
                  help='specify ini file')
parser.add_argument('-b', '--fb', dest='fb', default="/dev/fb1",
                  action="store",
                  metavar="FRAMEBUFFER",
                  help='specify framebuffer')
parser.add_argument('-s', '--schedule', dest='schedule',
                  action="store_true",
                  help='show schedule window and track omzn status')
parser.add_argument('-a', '--aquadata', dest='aquadata',
                  action="store_true",
                  help='get aquarium data')
parser.add_argument('-l', '--lockdata', dest='lockdata',
                  action="store_true",
                  help='get lock data')
parser.add_argument('-t', '--time', dest='fixedtime',
                  action="store", metavar="TIME",
                  help='set fixed datetime')
parser.add_argument('-D', '--debug', dest='debug',
                  action="store_true",
                  help='debug mode')
args = parser.parse_args()

config = ConfigParser()
config.read(os.path.dirname(os.path.abspath(__file__))+'/' + args.inifile)

FONT_DIR = './font/'
if os.uname()[0] != 'Darwin':
    os.environ["SDL_FBDEV"] = args.fb

#FONT_NAME = "Boku2-Regular.otf"
#FONT_NAME = "logotypejp_mp_b_1.ttf"
FONT_NAME = "rounded-mgenplus-1cp-bold.ttf"

SCHEDULE = args.schedule
AQUADATA = args.aquadata

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
students = {}

URL = str(config.get('api', 'url'))

MSGWND = None
DIMWND = None
LIGHTWND = None
BEACON_STATUS = None
OMZN_STATUS = None
AQUA_STATUS = None
LOCK_STATUS = None
PLAYER = None

e = []
AUTOMOVE = 1

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
    global MSGWND, BEACON_STATUS, OMZN_STATUS, AQUA_STATUS, LOCK_STATUS, PLAYER, DIMWND, LIGHTWND
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
        screen = pygame.display.set_mode(SCR_RECT.size, FULLSCREEN)
    else:
        if args.fullscreen:
            print("Full screen mode")
            scropt = FULLSCREEN | DOUBLEBUF | HWSURFACE
        else:
            scropt = DOUBLEBUF | HWSURFACE
        screen = pygame.display.set_mode(SCR_RECT.size, scropt)

    print("0")
    BEACON_STATUS = Beacons()
    if SCHEDULE is True:
        OMZN_STATUS = OmznStatus()
    if AQUADATA is True:
        AQUA_STATUS = Aqua()
    if args.lockdata:
        LOCK_STATUS = Lock()

    print("1")
    pygame.mouse.set_visible(0)
    print("2")
    # pygame.display.set_caption("あくあたんクエスト")
    # キャラクターチップをロード
    load_charachips("data", "charachip.dat")
    print("3")
    # マップチップをロード
    load_mapchips("data", "mapchip.dat")
    # マップとプレイヤー作成
    print("4")

    player_chara = str(config.get("game", "player"))
    player_x = int(config.get("game", "player_x"))
    player_y = int(config.get("game", "player_y"))
    mapname = str(config.get("game", "map"))

    PLAYER = Player(player_chara, (player_x, player_y), DOWN)
    fieldmap = Map(mapname)
    fieldmap.add_chara(PLAYER)
    # メッセージウィンドウ
    message_engine = MessageEngine()
    MSGWND = MessageWindow(
        Rect(20, SCR_HEIGHT/2, SCR_WIDTH-40, SCR_HEIGHT/2-20), message_engine)
    if SCHEDULE is True:
        schwnd = ScheduleWindow(Rect(10, 10, 228, 170))
        schwnd.update(OMZN_STATUS)
        schwnd.show()
#    DIMWND = DimWindow(Rect(0, 0, SCR_WIDTH, SCR_HEIGHT), screen)
#    DIMWND.hide()
    LIGHTWND = LightWindow(Rect(0, 0, SCR_WIDTH, SCR_HEIGHT), screen, fieldmap)
    LIGHTWND.set_color_scene("normal")
    LIGHTWND.show()
    clock = pygame.time.Clock()
    print("5")

    PLAYER.set_automove(e)
    msgwincount = 0
    db_check_count = 0
    ss_check_count = 0

    print("6")
    lightrooms = []
    messages = []
    for student in students.items():
        m = student[1].detect()
        if m != "":
            messages.append(m)
        if student[1].room != 'away':
            lightrooms.append(student[1].room)
    lightrooms = list(set(lightrooms))
    LIGHTWND.set_rooms(lightrooms)
    if len(messages) > 0:
        MSGWND.set("/".join(messages))

    print("7")
    dl1 = DataLoader(BEACON_STATUS, 30)
    dl1.daemon = True
    dl1.start()

    if SCHEDULE is True:
        dl2 = DataLoader(OMZN_STATUS, 30)
        dl2.daemon = True
        dl2.start()
    if AQUADATA is True:
        dl3 = DataLoader(AQUA_STATUS, 30)
        dl3.daemon = True
        dl3.start()
    if args.lockdata:
        dl4 = DataLoader(LOCK_STATUS, 30)
        dl4.daemon = True
        dl4.start()

#    if args.screenshot:
#        MSGWND.hide()
#        offset = calc_offset(PLAYER)
#        fieldmap.update()
#        fieldmap.draw(screen, offset)
#        pygame.display.update()
#        pygame.image.save(screen, "screenshot.png")
#        sys.exit()

    #current_place = OMZN_STATUS.current_place()
    while True:
        messages = []
        clock.tick(MAX_FRAME_PER_SEC)
        # メッセージウィンドウ表示中は更新を中止
        if not MSGWND.is_visible:
            fieldmap.update()
#        if not args.screenshot:
        MSGWND.update()
        offset = calc_offset(PLAYER)
#        if not DIMWND.is_visible:
        fieldmap.draw(screen, offset)
#        else:
#            DIMWND.dim()

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
        LIGHTWND.set_color_scene(light_mode)

        if SCHEDULE is True:
            schwnd.draw(screen)
            if len(PLAYER.automove) == 0 and not MSGWND.is_visible:
                schwnd.show()
            else:
                schwnd.hide()
        # For every interval
        if db_check_count > DB_CHECK_WAIT:
            db_check_count = 0
            if SCHEDULE is True:
                current_place = OMZN_STATUS.current_place()
                schwnd.update(OMZN_STATUS)
                if len(PLAYER.automove) == 0 and PLAYER.place_label != current_place:
                    #print(f"Player: moving {PLAYER.place_label} to {current_place}")
                    messages.append(f"omznが{current_place}へ移動中。")
                    schwnd.hide()
                    # calculate route
                    route = search_route(
                        fieldmap, (PLAYER.x, PLAYER.y), PLAYER.dest.get(current_place))
                    #print(route)
                    # convert route to automove sequence
                    r1 = route.pop(0)
                    # set automove sequence to player
                    while len(route) > 0:
                        r2 = route.pop(0)
                        dx = r2[0] - r1[0]
                        dy = r2[1] - r1[1]
                        if dx == 1 and dy == 0:
                            PLAYER.append_automove(["r"])
                        elif dx == -1 and dy == 0:
                            PLAYER.append_automove(["l"])
                        elif dx == 0 and dy == 1:
                            PLAYER.append_automove(["d"])
                        elif dx == 0 and dy == -1:
                            PLAYER.append_automove(["u"])
                        r1 = r2
#                    print(player.automove)

            lightrooms = []
            for student in students.items():
                m = student[1].detect()
                if m != "":
                    messages.append(m)
                if student[1].room != 'away':
                    lightrooms.append(student[1].room)
            lightrooms = list(set(lightrooms))
            LIGHTWND.set_rooms(lightrooms)
            if len(messages) > 0:
                MSGWND.set("/".join(messages))

        db_check_count = db_check_count + 1

        LIGHTWND.draw(offset)
        MSGWND.draw(screen)
        show_info(screen, PLAYER, clock, current_date, sunrize, sunset, light_mode)
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
                MSGWND.set(f"宝箱を開けた！/「{treasure.item}」を手に入れた。")
                fieldmap.remove_event(treasure)
                continue
            chara = PLAYER.talk(fieldmap)
            if chara is not None:
                msg = chara.message
                MSGWND.set(msg)
            else:
                MSGWND.set("そのほうこうには　だれもいない。")
        for event in pygame.event.get():
            if event.type == QUIT:
                sys.exit()
            if event.type == KEYDOWN and event.key == K_ESCAPE:
                sys.exit()
            if event.type == KEYDOWN and event.key == K_s:
                pygame.image.save(screen, args.scrfile)
            if event.type == KEYDOWN and event.key == K_SPACE:
                if MSGWND.is_visible:
                    # メッセージウィンドウ表示中なら次ページへ
                    MSGWND.next()
                    msgwincount = 0
                else:
                    # 宝箱を調べる
                    treasure = PLAYER.search(fieldmap)
                    if treasure is not None:
                        # treasure.open()
                        MSGWND.set(f"{treasure.item}を手に入れた。")
                        fieldmap.remove_event(treasure)
                        continue
                    # 表示中でないならはなす
                    chara = PLAYER.talk(fieldmap)
                    if chara is not None:
                        msg = chara.message
                        MSGWND.set(msg)
                    else:
                        MSGWND.set("そのほうこうには　だれもいない。")
        if msgwincount > MSGWAIT:
            # 5秒ほったらかし
            if MSGWND.is_visible:
                # メッセージウィンドウ表示中なら次ページへ
                MSGWND.next()
            msgwincount = 0



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

def show_info(screen,  player, clock, now, sunrize, sunset, light_mode):
    """デバッグ情報を表示"""
    ts_now = now.strftime("%Y-%m-%d %H:%M")
    ts_sunrize = sunrize.strftime("%H:%M")
    ts_sunset = sunset.strftime("%H:%M")
    draw_string(screen, 0, 10, f"Current:{ts_now} {light_mode}",Color(255, 255, 255, 128))
    draw_string(screen, 0, 30, f"Sunrize:{ts_sunrize}",Color(255, 0, 0, 128))
    draw_string(screen, 0, 50, f"Sunset: {ts_sunset}",Color(0, 0, 255, 128))
    draw_string(screen, SCR_WIDTH-60, 10,
                f"{player.x},{player.y}", Color(255, 255, 255, 128))  # プレイヤー座標
#    draw_string(screen, SCR_WIDTH-60,30, "%s" % player.place_label, Color(0,255,255,128))
#    draw_string(screen, SCR_WIDTH-60,50, "%s" % OMZN_STATUS.current_place(), Color(255,255,0,128))
    draw_string(screen, SCR_WIDTH-60, 30, f"{clock.get_fps():.1f}", Color(255, 255, 255, 128))


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
            chara_name = data[1]
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
    offsety = p.rect.topleft[1] - SCR_RECT.height//4*3
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
#    ad88                                    88                                
#   d8"                                      ""                                
#   88                                                                         
# MM88MMM             8b,dPPYba,  8b,dPPYba, 88 88,dPYba,,adPYba,   ,adPPYba,  
#   88                88P'    "8a 88P'   "Y8 88 88P'   "88"    "8a a8P_____88  
#   88                88       d8 88         88 88      88      88 8PP"""""""  
#   88                88b,   ,a8" 88         88 88      88      88 "8b,   ,aa  
#   88                88`YbbdP"'  88         88 88      88      88  `"Ybbd8"'  
#                     88                                                       
#        888888888888 88                                                       
# 

def f_prime(n, m):
    """A*探索の一部"""
    def g_star(n, m):
        """G*"""
        return n.f_star - n.h_star
    def h_star(m):
        """H*"""
        return m.h_star
    def cost(n, m):
        return (m.x - n.x) + (m.y - n.y)
    return g_star(n, m) + h_star(m) + cost(n, m)

#                                                                                                                                   
#                                                       88                                                                          
#                                                       88                                                         ,d               
#                                                       88                                                         88               
# ,adPPYba,  ,adPPYba, ,adPPYYba, 8b,dPPYba,  ,adPPYba, 88,dPPYba,            8b,dPPYba,  ,adPPYba,  88       88 MM88MMM ,adPPYba,  
# I8[    "" a8P_____88 ""     `Y8 88P'   "Y8 a8"     "" 88P'    "8a           88P'   "Y8 a8"     "8a 88       88   88   a8P_____88  
#  `"Y8ba,  8PP""""""" ,adPPPPP88 88         8b         88       88           88         8b       d8 88       88   88   8PP"""""""  
# aa    ]8I "8b,   ,aa 88,    ,88 88         "8a,   ,aa 88       88           88         "8a,   ,a8" "8a,   ,a88   88,  "8b,   ,aa  
# `"YbbdP"'  `"Ybbd8"' `"8bbdP"Y8 88          `"Ybbd8"' 88       88           88          `"YbbdP"'   `"YbbdP'Y8   "Y888 `"Ybbd8"'  
#                                                                                                                                   
#                                                                  888888888888                                                     
# 

def search_route(mmap, start, goal):
    """経路探索(A*)"""
    directions = [(0, 1), (1, 0), (-1, 0), (0, -1)]
    Node.start = start
    Node.goal = goal
    start_node = Node(*Node.start)
    start_node.f_star = start_node.h_star
    #Goal = Node(*Node.goal)
    open_list = NodeList()
    close_list = NodeList()
    open_list.append(start_node)
    while open_list:
        n = min(open_list, key=lambda x: x.f_star)
        open_list.remove(n)
        close_list.append(n)
        end_node = n
        if n.pos == Node.goal:
            end_node = n
            break
        for direction in directions:
            m = Node(n.x + direction[0], n.y + direction[1])
            if not mmap.is_movable_but_chara(n.x, n.y):
                continue
            om = open_list.find(m)
            cm = close_list.find(m)
            fp = f_prime(n, m)
            om_fp = f_prime(n, om) if om else None
            cm_fp = f_prime(n, cm) if cm else None
            if om is None and cm is None:
                m.parent_node = n
                m.f_star = fp
                open_list.append(m)
            elif not om is None and om_fp < om.f_star:
                om.parent_node = n
                om.f_star = om_fp
            elif not cm is None and cm_fp < cm.f_star:
                cm.f_star = cm_fp
                close_list.remove(cm)
                open_list.append(cm)
    retval = [goal]
    n = end_node.parent_node
    while n:
        retval.append((n.x, n.y))
        n = n.parent_node
    retval.reverse()
    return retval

#                                                  
# 888b      88                      88             
# 8888b     88                      88             
# 88 `8b    88                      88             
# 88  `8b   88  ,adPPYba,   ,adPPYb,88  ,adPPYba,  
# 88   `8b  88 a8"     "8a a8"    `Y88 a8P_____88  
# 88    `8b 88 8b       d8 8b       88 8PP"""""""  
# 88     `8888 "8a,   ,a8" "8a,   ,d88 "8b,   ,aa  
# 88      `888  `"YbbdP"'   `"8bbdP"Y8  `"Ybbd8"'  
#                                                  
#                                                  
# 

class Node:
    """探索ノード"""
    start = None
    goal = []

    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.pos = (x, y)
        self.parent_node = None
        self.h_star = abs(x - self.goal[0]) + abs(y - self.goal[1])
        self.f_star = 0

#                                                                                   
# 888b      88                      88            88          88                    
# 8888b     88                      88            88          ""             ,d     
# 88 `8b    88                      88            88                         88     
# 88  `8b   88  ,adPPYba,   ,adPPYb,88  ,adPPYba, 88          88 ,adPPYba, MM88MMM  
# 88   `8b  88 a8"     "8a a8"    `Y88 a8P_____88 88          88 I8[    ""   88     
# 88    `8b 88 8b       d8 8b       88 8PP""""""" 88          88  `"Y8ba,    88     
# 88     `8888 "8a,   ,a8" "8a,   ,d88 "8b,   ,aa 88          88 aa    ]8I   88,    
# 88      `888  `"YbbdP"'   `"8bbdP"Y8  `"Ybbd8"' 88888888888 88 `"YbbdP"'   "Y888  
#                                                                                   
#                                                                                   
# 

class NodeList(list):
    """ノードリスト"""

    def find(self, n):
        """経路を見つける"""
        l = [t for t in self if t.pos == n.pos]
        return l[0] if l != [] else None

    def remove(self, node):
        """ノードを削除する"""
        del self[self.index(node)]

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
#        db                                           
#       d88b                                          
#      d8'`8b                                         
#     d8'  `8b     ,adPPYb,d8 88       88 ,adPPYYba,  
#    d8YaaaaY8b   a8"    `Y88 88       88 ""     `Y8  
#   d8""""""""8b  8b       88 88       88 ,adPPPPP88  
#  d8'        `8b "8a    ,d88 "8a,   ,a88 88,    ,88  
# d8'          `8b `"YbbdP'88  `"YbbdP'Y8 `"8bbdP"Y8  
#                          88                         
#                          88                         
# 

class Aqua:
    """水槽情報を保持"""
    def __init__(self):
        self.temp = {}
        self.light = {}
        self.fan = {}
        self.feed = {}
        self.pressure = 0
        self.get_data()

    def get_data(self):
        """データ取得"""
        try:
            response = requests.get(f"https://{URL}/api/aqua/status",timeout=30)
            response.encoding = response.apparent_encoding
            self.data = response.json()
        except Exception:
            pass

        temp = self.data['temp']
        tempkeys = temp.keys()
        tempkeys = sorted(tempkeys)
        for k in tempkeys:
            self.temp[k] = temp[k]['current']
        self.pressure = self.data['pressure']['current']
        for k in ['light1', 'light2']:
            self.light[k] = self.data[k]['status']
        for k in ['ac1', 'fan1', 'fan2', 'fan3']:
            self.fan[k] = self.data[k]['current']
        for k in ['tank_0', 'tank_1', 'tank_2', 'tank_3']:
            try:
                self.feed[k] = self.data['feed'][k]
            except Exception:
                pass

    def replace_message(self, message):
        """定型メッセージを置換"""
        message = message.replace('{temp_air}', str(self.temp['air']))
        message = message.replace('{temp_water1}', str(self.temp['water1']))
        message = message.replace('{temp_water2}', str(self.temp['water2']))
        message = message.replace('{temp_water3}', str(self.temp['water3']))
        message = message.replace('{feed_tank0}', str(self.feed['tank_0']))
        message = message.replace('{feed_tank1}', str(self.feed['tank_1']))
        message = message.replace('{feed_tank2}', str(self.feed['tank_2']))
        message = message.replace('{feed_tank3}', str(self.feed['tank_3']))
        message = message.replace('{light1}', self.light['light1'])
        message = message.replace('{light2}', self.light['light2'])
        message = message.replace('{ac1}', self.fan['ac1'])
        message = message.replace('{fan1}', self.fan['fan1'])
        message = message.replace('{fan2}', self.fan['fan1'])
        message = message.replace('{fan3}', self.fan['fan1'])
        message = message.replace('{pressure}', str(self.pressure))
        return message

#                                                                                 
# 88888888ba                                                                      
# 88      "8b                                                                     
# 88      ,8P                                                                     
# 88aaaaaa8P'  ,adPPYba, ,adPPYYba,  ,adPPYba,  ,adPPYba,  8b,dPPYba,  ,adPPYba,  
# 88""""""8b, a8P_____88 ""     `Y8 a8"     "" a8"     "8a 88P'   `"8a I8[    ""  
# 88      `8b 8PP""""""" ,adPPPPP88 8b         8b       d8 88       88  `"Y8ba,   
# 88      a8P "8b,   ,aa 88,    ,88 "8a,   ,aa "8a,   ,a8" 88       88 aa    ]8I  
# 88888888P"   `"Ybbd8"' `"8bbdP"Y8  `"Ybbd8"'  `"YbbdP"'  88       88 `"YbbdP"'  
#                                                                                 
#                                                                                 
# 

class Beacons:
    """ビーコンの状態を保持"""
    def __init__(self):
        self.data = {}
        self.get_data()

    def target(self, bid):
        """bidの状態を返す"""
        try:
            return self.data['target'][f"bt{bid}"]['status']
        except Exception:
            return 'Lost'

    def duration(self, bid):
        """在室時間を返す"""
        try:
            return self.data['target'][f"bt{bid}"]['stay']
        except Exception:
            return 0

    def get_data(self):
        """データ取得"""
        try:
            response = requests.get(f"https://{URL}/api/beacon/status", timeout=30)
            response.encoding = response.apparent_encoding
            tmpdata = response.json()
        except Exception as exc:
            # set some dummy data
            print(type(exc))
            print(exc)
            print(response)
            data = '{"target":{"bt15001":{"status":"Lost","time":"2017-12-19 16:40:09"},'\
                   '"bt15070":{"status":"Lost","time":"2017-04-11 11:50:33"}}}'
            self.data = json.loads(data)
        else:
            for k in tmpdata['target'].keys():
                n = k[2:]
                try:
                    response = requests.get(f"https://{URL}/api/beacon/stay/{n}", timeout=30)
                    response.encoding = response.apparent_encoding
                    stay = response.json()
                    tmpdata['target'][k]['stay'] = stay["elapsed"]
                except Exception as exc:
                    print(type(exc))
                    print(exc)
                    print(response)
                    self.data['target'][k]['stay'] = 0
            self.data = tmpdata

#                                              
# 88                                88         
# 88                                88         
# 88                                88         
# 88          ,adPPYba,   ,adPPYba, 88   ,d8   
# 88         a8"     "8a a8"     "" 88 ,a8"    
# 88         8b       d8 8b         8888[      
# 88         "8a,   ,a8" "8a,   ,aa 88`"Yba,   
# 88888888888 `"YbbdP"'   `"Ybbd8"' 88   `Y8a  
#                                              
#                                              
# 

class Lock:
    """ドアロックの状態を保持"""
    def __init__(self):
        self.data = {}
        self.get_data()

    def room(self, room_id):
        """部屋のLock状態を返す"""
        try:
            return self.data[room_id]
        except Exception:
            return "unlock"

    def get_data(self):
        """データ取得"""
        ts = {}
        try:
            response = requests.get(f"https://{URL}/api/lock/status", timeout=30)
            response.encoding = response.apparent_encoding
            rawdata = response.json()
        except Exception as exc:
            # set some dummy data
            print(type(exc))
            print(exc)
            print(response)
            data = '{}'
            self.data = json.loads(data)
        else:
            for d in rawdata:
                if d['room'] in ts:
                    if d['timestamp'] > ts[d['room']]:
                        self.data[d['room']] = d['lockstate']
                else:
                    ts[d['room']] = d['timestamp']
                    self.data[d['room']] = d['lockstate']
#                self.data[d['room']] = d['lockstate']
#            print(self.data)



#                                                                                                                     
#   ,ad8888ba,                                             ad88888ba                                                  
#  d8"'    `"8b                                           d8"     "8b ,d                 ,d                           
# d8'        `8b                                          Y8,         88                 88                           
# 88          88 88,dPYba,,adPYba,  888888888 8b,dPPYba,  `Y8aaaaa, MM88MMM ,adPPYYba, MM88MMM 88       88 ,adPPYba,  
# 88          88 88P'   "88"    "8a      a8P" 88P'   `"8a   `"""""8b, 88    ""     `Y8   88    88       88 I8[    ""  
# Y8,        ,8P 88      88      88   ,d8P'   88       88         `8b 88    ,adPPPPP88   88    88       88  `"Y8ba,   
#  Y8a.    .a8P  88      88      88 ,d8"      88       88 Y8a     a8P 88,   88,    ,88   88,   "8a,   ,a88 aa    ]8I  
#   `"Y8888Y"'   88      88      88 888888888 88       88  "Y88888P"  "Y888 `"8bbdP"Y8   "Y888  `"YbbdP'Y8 `"YbbdP"'  
#                                                                                                                     
#                                                                                                                     
# 

class OmznStatus:
    """博士の状態を保持"""
    def __init__(self):
        self.data = {}
        self.get_data()

    def current_event_title(self):
        """現在の予定のタイトル"""
        try:
            return self.data['current_event']['title']
        except Exception:
            return None

    def event_title(self):
        """イベントのタイトル"""
        try:
            if not self.current_event_title():
                return self.data['incoming_event']['title']
            else:
                return self.data['current_event']['title']
        except IndexError:
            return None

    def event_start_time(self):
        """イベントの開始時刻"""
        try:
            if not self.data['current_event']:
                return self.data['incoming_event']['start_time']
            else:
                return self.data['current_event']['start_time']
        except IndexError:
            return None

    def event_end_time(self):
        """イベントの終了時刻"""
        try:
            if not self.data['current_event']:
                return self.data['incoming_event']['end_time']
            else:
                return self.data['current_event']['end_time']
        except IndexError:
            return None

    def event_duration(self):
        """イベントの時間"""
        if not self.data['current_event']:
            dt = "incoming_event"
        else:
            dt = "current_event"

        stt = int(self.data[dt]['start_time'])
        edt = int(self.data[dt]['end_time'])

        if self.data[dt]['all_day'] == 0:
            return f'{strftime("%m-%d %H:%M",time.gmtime(stt))} - '\
                    f'{strftime("%H:%M", time.gmtime(edt))}'
        return f'{strftime("%Y-%m-%d", time.gmtime(stt))} - '\
                    f'{strftime("%Y-%m-%d", time.gmtime(edt))}'

    def event_place(self):
        """イベントの場所"""
        try:
            if not self.data['current_event']:
                return self.data['incoming_event']['place']
            return self.data['current_event']['place']
        except IndexError:
            return None

    def event(self):
        """現在のイベント"""
        try:
            if not self.data['current_event']:
                return self.data['incoming_event']
            return self.data['current_event']
        except IndexError:
            return None

    def room(self):
        """部屋の情報"""
        try:
            return self.data['room']
        except IndexError:
            return 'Lost'

    def location(self):
        """場所の情報"""
        try:
            if self.data['location']['time'] < self.data['lastlocation']['time']:
                return ''
            return self.data['location']['place']
        except IndexError:
            return ''

    def lastlocation(self):
        """最後に居たところ"""
        try:
            return self.data['lastlocation']['place']
        except IndexError:
            return ''

    def current_place(self):
        """現在居るところ"""
        if self.room() != "Lost":
            return self.room()[6:]
        if self.location() == 'KIT':
            return "KIT"
        if self.location() == "":
            if self.lastlocation() != "Ikeda":
                return self.lastlocation()
        return "away"

    def get_data(self):
        """データ取得"""
        try:
            response = requests.get(f"https://{URL}/api/beacon/status/15070", timeout=30)
            response.encoding = response.apparent_encoding
            st = response.json()
            self.data["room"] = st["note"]
            response = requests.get(f"https://{URL}/api/omzn/schedule/current", timeout=30)
            response.encoding = response.apparent_encoding
            self.data["current_event"] = response.json()
            response = requests.get(f"https://{URL}/api/omzn/schedule/incoming", timeout=30)
            response.encoding = response.apparent_encoding
            self.data["incoming_event"] = response.json()
            response = requests.get(f"https://{URL}/api/aqua/location_omzn_entered", timeout=30)
            response.encoding = response.apparent_encoding
            loc = response.json()
            self.data["location"] = {}
            self.data["location"]["time"] = loc["timestamp"]
            self.data["location"]["place"] = loc["note"]
            response = requests.get(f"https://{URL}/api/aqua/location_omzn_exited", timeout=30)
            response.encoding = response.apparent_encoding
            loc = response.json()
            self.data["lastlocation"] = {}
            self.data["lastlocation"]["time"] = loc["timestamp"]
            self.data["lastlocation"]["place"] = loc["note"]
            #print(self.data)
        except Exception as exc:
            # set some dummy data
            data = '{"location":{"time":"2017-12-22 10:22:50","place":"KIT"},'\
                        '"incoming_event":{"place":"","start_time":"1514127600",'\
                        '"title":"Dummy","all_day":1,"end_time":"1514473199","description":""},'\
                        '"lastlocation":{"place":"KIT","time":"2017-12-22 10:22:50"},'\
                        '"room":"Found_8-320",'\
                        '"current_event":{}}'
            self.data = json.loads(data)
            print(exc)
            #print(self.data)

#                                                                          
#  ad88888ba                             88                                
# d8"     "8b ,d                         88                         ,d     
# Y8,         88                         88                         88     
# `Y8aaaaa, MM88MMM 88       88  ,adPPYb,88  ,adPPYba, 8b,dPPYba, MM88MMM  
#   `"""""8b, 88    88       88 a8"    `Y88 a8P_____88 88P'   `"8a  88     
#         `8b 88    88       88 8b       88 8PP""""""" 88       88  88     
# Y8a     a8P 88,   "8a,   ,a88 "8a,   ,d88 "8b,   ,aa 88       88  88,    
#  "Y88888P"  "Y888  `"YbbdP'Y8  `"8bbdP"Y8  `"Ybbd8"' 88       88  "Y888  
#                                                                          
#                                                                          
# 

class Student:
    """学生オブジェクト"""
    def __init__(self, name, minor, character, beacons, mymap):
        self.name = name
        self.minor = minor
        self.character = character
        self.map = mymap
        self.beacons = beacons
        self.room = 'away'
        self.dest = {}

    def detect(self):
        """検知"""
        status = self.beacons.target(self.minor)
        if status is not None:
            if re.match(r"Found", status):
                robj = re.search(r"_(.*)$", status)
                r = robj.group()
                if r[0] == '_':
                    newroom = r[1:]
                else:
                    newroom = 'away'
            else:
                newroom = 'away'
        else:
            return ""
        message = ""
        if newroom != self.room:
            message = f"{self.name}が{newroom}へ移動中。"
            if newroom == 'away':
                message = f"{self.name}が退出中。"
                #print(f"{self.minor}: moving: {self.room} to {newroom}")
            r = self.dest.get(newroom)
            p = search_route(self.map, (self.character.x, self.character.y), r)
#            if args.screenshot is True:
#                self.character.set_pos(r[0],r[1],0)
#            else:
            self.character.append_moveto(p)
            #print(p)

            if newroom == 'away':
                self.character.movetype = 0
            else:
                self.character.movetype = 1
            self.room = newroom

        existingtime = self.beacons.duration(self.minor)

        if existingtime is not None and self.room != 'away':
            hh = float(existingtime) / 3600.0
            self.character.hp = f"{hh:3.1f}"
            if hh > 24.0:
                self.character.hp_color = Color(0, 0, 0, 255)
                self.character.set_speed = 2
            elif hh > 12.0:
                self.character.hp_color = Color(255, 0, 0, 255)
                self.character.set_speed = 4
            elif hh > 6.0:
                self.character.hp_color = Color(255, 255, 0, 255)
                self.character.set_speed = 6
            elif hh > 2.0:
                self.character.hp_color = Color(0, 255, 0, 255)
                self.character.set_speed = 8
            else:
                self.character.hp_color = Color(0, 255, 255, 255)
                self.character.set_speed = 10

        else:
            self.character.hp = ""
        return message


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
        file = os.path.join("data", self.name.lower() + ".json")
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
        students[str(name)] = Student(
            npcname, str(name), chara, BEACON_STATUS, self)

    def create_npcpath_j(self, data):
        """NPCの部屋での目的地を設定する"""
        npcname = data["name"]
        pathname = data["pathname"]
        dest = (int(data["x"]), int(data["y"]))
        students[str(npcname)].dest[str(pathname)] = dest

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
        room = data["room"]
        light = Light((x, y), room)
        self.lights.append(light)

    def create_door_j(self, data):
        """ドアを作成してeventsに追加する"""
        x, y = int(data["x"]), int(data["y"])
        name = data["doorname"]
        door = Door((x, y), name)
        door.open()
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

    def create_move_j(self, data):
        """移動イベントを作成してeventsに追加する"""
        x, y = int(data["x"]), int(data["y"])
        mapchip = int(data["mapchip"])
        dest_map = data["dest_map"]
        dest_x, dest_y = int(data["dest_x"]), int(data["dest_y"])
        move = MoveEvent((x, y), mapchip, dest_map, (dest_x, dest_y))
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

    def __init__(self, name, pos, direction):
        Character.__init__(self, name, pos, direction, False, None)
        self.moves = []
        self.wait = 0
        self.dest = {}
        self.place_label = "away"
        self.automove = []

    def update(self, mymap):
        """プレイヤー状態を更新する。
        mapは移動可能かの判定に必要。"""
        # プレイヤーの移動処理
        if self.moving:
            # ピクセル移動中ならマスにきっちり収まるまで移動を続ける
            self.rect.move_ip(self.vx, self.vy)
            if self.rect.left % GS == 0 and self.rect.top % GS == 0:  # マスにおさまったら移動完了
                self.moving = False
                self.x = self.rect.left // GS
                self.y = self.rect.top // GS
                # TODO: ここに接触イベントのチェックを入れる
                event = mymap.get_event(self.x, self.y)
                if isinstance(event, MoveEvent):  # MoveEventなら
                    dest_map = event.dest_map
                    dest_x = event.dest_x
                    dest_y = event.dest_y
                    # 暗転
#                    DIMWND.setdf(200)
#                    DIMWND.show()
                    mymap.create(dest_map)  # 移動先のマップで再構成
                    self.set_pos(dest_x, dest_y, DOWN)  # プレイヤーを移動先座標へ
                    mymap.add_chara(self)  # マップに再登録
                elif isinstance(event, PlacesetEvent):  # PlacesetEventなら
                    self.place_label = event.place_label
                elif isinstance(event, AutoEvent):  # AutoEvent
                    self.append_automove(event.sequence)
        else:
            # ここで自動移動の判定
            direction = -1
            if len(self.automove) > 0:
                direction = self.get_next_automove()
                if direction == 'u' or direction == 'd' or direction == 'l' or direction == 'r':
                    self.pop_automove()
                elif direction == 'x':
                    self.wait += 1
                    if self.wait > 60:
                        self.wait = 0
                        self.pop_automove()

            # プレイヤーの場合、キー入力があったら移動を開始する
            pressed_keys = pygame.key.get_pressed()
            if (pressed_keys[K_DOWN] or direction == 'd'):
                self.direction = DOWN  # 移動できるかに関係なく向きは変える
                if mymap.is_movable(self.x, self.y+1):
                    self.vx, self.vy = 0, self.speed
                    self.moving = True
            elif (pressed_keys[K_LEFT] or direction == 'l'):
                self.direction = LEFT
                if mymap.is_movable(self.x-1, self.y):
                    self.vx, self.vy = -self.speed, 0
                    self.moving = True
            elif (pressed_keys[K_RIGHT] or direction == 'r'):
                self.direction = RIGHT
                if mymap.is_movable(self.x+1, self.y):
                    self.vx, self.vy = self.speed, 0
                    self.moving = True
            elif (pressed_keys[K_UP] or direction == 'u'):
                self.direction = UP
                if mymap.is_movable(self.x, self.y-1):
                    self.vx, self.vy = 0, -self.speed
                    self.moving = True
        # キャラクターアニメーション（frameに応じて描画イメージを切り替える）
        self.frame += 1
        self.image = self.images[self.name][self.direction *
                                            4+(self.frame // self.animcycle % 4)]

    def set_automove(self, seq):
        """自動移動シーケンスをセットする"""
        self.automove = seq

    def get_next_automove(self):
        """次の移動先を得る"""
        if len(self.automove) > 0:
            return self.automove[0]
        return None

    def pop_automove(self):
        """自動移動を1つ取り出す"""
        self.automove.pop(0)

    def append_automove(self, seq):
        """自動移動に追加する"""
        self.automove.extend(seq)

    def search(self, mymap):
        """足もとに宝箱があるか調べる"""
        event = mymap.get_event(self.x, self.y)
        if isinstance(event, Treasure):
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
                screen.blit(surf, (x, y+(self.FONT_HEIGHT)-rect[3]))
#                screen.blit(self.myfont.render(ch,self.color)[0],(x,y))
            except KeyError:
                print(f"描画できない文字があります:{ch}")
                return

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
#  ad88888ba             88                              88             88          I8,        8        ,8I 88                      88                                 
# d8"     "8b            88                              88             88          `8b       d8b       d8' ""                      88                                 
# Y8,                    88                              88             88           "8,     ,8"8,     ,8"                          88                                 
# `Y8aaaaa,    ,adPPYba, 88,dPPYba,   ,adPPYba,  ,adPPYb,88 88       88 88  ,adPPYba, Y8     8P Y8     8P   88 8b,dPPYba,   ,adPPYb,88  ,adPPYba,  8b      db      d8  
#   `"""""8b, a8"     "" 88P'    "8a a8P_____88 a8"    `Y88 88       88 88 a8P_____88 `8b   d8' `8b   d8'   88 88P'   `"8a a8"    `Y88 a8"     "8a `8b    d88b    d8'  
#         `8b 8b         88       88 8PP""""""" 8b       88 88       88 88 8PP"""""""  `8a a8'   `8a a8'    88 88       88 8b       88 8b       d8  `8b  d8'`8b  d8'   
# Y8a     a8P "8a,   ,aa 88       88 "8b,   ,aa "8a,   ,d88 "8a,   ,a88 88 "8b,   ,aa   `8a8'     `8a8'     88 88       88 "8a,   ,d88 "8a,   ,a8"   `8bd8'  `8bd8'    
#  "Y88888P"   `"Ybbd8"' 88       88  `"Ybbd8"'  `"8bbdP"Y8  `"YbbdP'Y8 88  `"Ybbd8"'    `8'       `8'      88 88       88  `"8bbdP"Y8  `"YbbdP"'      YP      YP      
#                                                                                                                                                                      
#                                                                                                                                                                      
# 

class ScheduleWindow(Window):
    """予定・在室ウィンドウ"""
    FONT_HEIGHT = 16
    WHITE = Color(255, 255, 255, 255)
    RED = Color(255, 31, 31, 255)
    GREEN = Color(31, 255, 31, 255)
    BLUE = Color(31, 31, 255, 255)
    CYAN = Color(218, 248, 255, 255)

    def __init__(self, rect):
        Window.__init__(self, rect)
        self.text_rect = self.inner_rect.inflate(-2, -2)  # テキストを表示する矩形
        self.img_schedule = load_image("images", "welcome.png", -1)  # 画像
        self.myfont = pygame.freetype.Font(
            FONT_DIR + FONT_NAME, self.FONT_HEIGHT)
        self.color = self.WHITE
        self.title = ''
        self.place = ''
        self.duration = ''

    def draw_string(self, x, y, string, color):
        """文字列出力"""
        surf, rect = self.myfont.render(string, color)
        self.surface.blit(surf, (x, y+(self.FONT_HEIGHT+2)-rect[3]))

    def update(self, omzn):
        """更新"""
        ttl = omzn.current_event_title()
        if ttl is None:
            if omzn.room() == "Lost":
                if omzn.location() == "KIT":
                    self.img_schedule = load_image("images", "campus.png", -1)
                else:
                    self.img_schedule = load_image("images", "away.png", -1)
            elif omzn.room() == "Found_8-320":
                self.img_schedule = load_image("images", "welcome.png", -1)
            else:
                self.img_schedule = load_image("images", "laboratory.png", -1)
            ttl = omzn.event_title()
            robj = re.search(r"\[.*\]", ttl)
            if robj:
                self.title = "[Next]" + ttl[robj.end():]
            else:
                self.title = "[Next]" + ttl
        else:
            robj = re.search(r"\[.*\]", ttl)
            if robj:
                typ = robj.group()[1:-1]
                if typ == "Meeting":
                    self.img_schedule = load_image("images", "meeting.png", -1)
                elif typ == "Seminar":
                    self.img_schedule = load_image("images", "seminar.png", -1)
                elif typ == "Guest":
                    self.img_schedule = load_image("images", "guest.png", -1)
                elif typ == "Lecture":
                    self.img_schedule = load_image("images", "lecture.png", -1)
                self.title = "[Now]" + ttl[robj.end():]
            else:
                if omzn.room() == "Lost":
                    if omzn.location() == "KIT":
                        self.img_schedule = load_image(
                            "images", "campus.png", -1)
                    else:
                        self.img_schedule = load_image(
                            "images", "away.png", -1)
                elif omzn.room() == "Found_8-320":
                    self.img_schedule = load_image("images", "welcome.png", -1)
                else:
                    self.img_schedule = load_image(
                        "images", "laboratory.png", -1)
                self.title = "[Now]" + ttl

        self.place = omzn.event_place()
        self.duration = omzn.event_duration()

    def draw(self, screen):
        """メッセージを描画する
        メッセージウィンドウが表示されていないときは何もしない"""
        if not self.is_visible:
            return
        Window.draw(self)
        self.surface.blit(self.img_schedule, self.text_rect)
        self.draw_string(30, 95, self.title, self.CYAN)
        self.draw_string(30, 117, self.place, self.CYAN)
        self.draw_string(30, 139, self.duration, self.CYAN)

        Window.blit(self, screen)


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
        return f"AUTO,{self.x},{self.y},{self.mapchip},{''.join(self.sequence)}"


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

    def __init__(self, pos, mapchip, dest_map, dest_pos):
        self.x, self.y = pos[0], pos[1]  # イベント座標
        self.mapchip = mapchip  # マップチップ
        self.dest_map = dest_map  # 移動先マップ名
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

    def open(self):
        """宝箱をあける"""
#        sounds["treasure"].play()
#        TODO: アイテムを追加する処理

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
        if args.lockdata:
            if LOCK_STATUS.room(self.doorname) == 'lock':
                self.close()
            else:
                self.open()
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

#                                                                                                   
#  ad88888ba                                88 88 88888888ba,                                       
# d8"     "8b                               88 88 88      `"8b                                      
# Y8,                                       88 88 88        `8b                                     
# `Y8aaaaa,   88,dPYba,,adPYba,  ,adPPYYba, 88 88 88         88  ,adPPYba,   ,adPPYba,  8b,dPPYba,  
#   `"""""8b, 88P'   "88"    "8a ""     `Y8 88 88 88         88 a8"     "8a a8"     "8a 88P'   "Y8  
#         `8b 88      88      88 ,adPPPPP88 88 88 88         8P 8b       d8 8b       d8 88          
# Y8a     a8P 88      88      88 88,    ,88 88 88 88      .a8P  "8a,   ,a8" "8a,   ,a8" 88          
#  "Y88888P"  88      88      88 `"8bbdP"Y8 88 88 88888888Y"'    `"YbbdP"'   `"YbbdP"'  88          
#                                                                                                   
#                                                                                                   
# 

class SmallDoor(Door):
    """小さいドアクラス"""
    def __init__(self, pos, name):
        self.mapchip = 27
        self.mapchip_list = [27,689]
        self.status = 0 # close
        self.x, self.y = pos[0], pos[1]  # ドア座標
        self.doorname = str(name)  # ドア名

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


if __name__ == "__main__":
    main()
