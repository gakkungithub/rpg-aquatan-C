#!/usr/bin/env python3
"""マップエディタ"""
import os
import struct
import sys
import codecs
import json
import argparse
from typing import List
from operator import attrgetter
import pygame
from pygame.locals import *
import pygame.freetype

parser = argparse.ArgumentParser()
parser.add_argument('-m','--map', action="store", help="Specify map name")
parser.add_argument('--screenshot-file', dest="scrfile",
                    action="store", default="sshot.png", help="Specify screenshot file")
args = parser.parse_args()

SCR_RECT = Rect(0, 0, 2560, 1440)
INPUT_RECT = Rect(240, 302, 320, 36)
GS = 32
TRANS_COLOR = (190, 179, 145)  # マップチップの透明色
MAX_FRAME_PER_SEC = 24

DOOR_SIZE = 0

SELECT_MODE_MAP = 0
SELECT_MODE_OBJECT = 1
SELECT_MODE_TREASURE = 2
SELECT_MODE_CHARA = 3
SELECT_MODE_NPC = 4
SELECT_MODE_DOOR = 5
SELECT_MODE_SMALLDOOR = 6
SELECT_MODE_LIGHT = 7
SELECT_MODE_MOVE = 8
SELECT_MODE_AUTO = 9

SELECT_MODE = SELECT_MODE_MAP

FONT_DIR = './font/'

#FONT_NAME = "Boku2-Regular.otf"
#FONT_NAME = "logotypejp_mp_b_1.ttf"
FONT_NAME = "rounded-mgenplus-1cp-bold.ttf"

SHOW_GRID = True  # グリッドを表示するか？
SHOW_EVENT = True
SHOW_CHARA = True

RELEASED_BS = False
RELEASED_ESC = False

def main():
    """main"""
    global SELECT_MODE, RELEASED_BS, RELEASED_ESC
    pygame.init()

    screen = pygame.display.set_mode(SCR_RECT.size)
    pygame.display.set_caption("Map editor")

    load_mapchips("data", "mapchip.dat")
    load_charachips("data", "charachip.dat")

    cursor = Cursor(0, 0)
    msg_engine = MessageEngine()
    input_wnd = InputWindow(INPUT_RECT, msg_engine)

    palette = MapchipPalette()
    cpalette = CharachipPalette()
    mmap = Map("NEW", 64, 64, 152, palette,cpalette,screen,input_wnd)

    if args.map:
        # マップをロード
        try:
            mmap.load_json(args.map)
        except IOError:
            print(f"Cannot load: {args.map}")

    clock = pygame.time.Clock()
    while True:
        clock.tick(60)
        if palette.display_flag:  # パレットが表示中なら
            palette.update()
            palette.draw(screen)
        elif cpalette.display_flag:
            cpalette.update()
            cpalette.draw(screen)
        else:
            offset = calc_offset(cursor)
            # 更新
            cursor.update()
            mmap.update(offset)
            # 描画
            mmap.draw(screen, offset)
            #cursor.draw(screen, offset)
            # 選択マップチップを左上に描画
            screen.blit(Map.images[palette.selected_mapchip], (10,30))
            pygame.draw.rect(screen, (255,255,255), (10,30,32,32), 2)
            screen.blit(Map.images[palette.selected_eventchip], (45,30))
            pygame.draw.rect(screen, (255,255,255), (45,30,32,32), 2)
            screen.blit(Character.images[cpalette.selected_charachip][0], (80,30))
            pygame.draw.rect(screen, (255,255,255), (80,30,32,32), 2)
            if SELECT_MODE == SELECT_MODE_MAP:
                pygame.draw.rect(screen, (0,255,0), (10,30,32,32), 3)
                msg_engine.draw_string(screen, (10,2), "MAP")
                msg_engine.draw_string(screen, (10,136), "[X] Draw")
                msg_engine.draw_string(screen, (10,166), "[Z] Pick")
            elif SELECT_MODE == SELECT_MODE_OBJECT:
                pygame.draw.rect(screen, (0,255,0), (45,30,32,32), 3)
                msg_engine.draw_string(screen, (10,2), "OBJECT")
                msg_engine.draw_string(screen, (10,136), "[X] Draw")
                msg_engine.draw_string(screen, (10,166), "[Z] Pick")
                msg_engine.draw_string(screen, (10,196), "[BS] Delete")
            elif SELECT_MODE == SELECT_MODE_TREASURE:
                pygame.draw.rect(screen, (0,255,0), (45,30,32,32), 3)
                msg_engine.draw_string(screen, (10,2), "TREASURE")
                msg_engine.draw_string(screen, (10,136), "[X] Draw")
                msg_engine.draw_string(screen, (10,166), "[BS] Delete")
            elif SELECT_MODE == SELECT_MODE_DOOR:
                msg_engine.draw_string(screen, (10,2), "DOOR LARGE")
                msg_engine.draw_string(screen, (10,136), "[X] Draw")
                msg_engine.draw_string(screen, (10,196), "[BS] Delete")
            elif SELECT_MODE == SELECT_MODE_SMALLDOOR:
                msg_engine.draw_string(screen, (10,2), "DOOR SMALL")
                msg_engine.draw_string(screen, (10,136), "[X] Draw")
                msg_engine.draw_string(screen, (10,196), "[BS] Delete")
            elif SELECT_MODE == SELECT_MODE_MOVE:
                pygame.draw.rect(screen, (0,255,0), (45,30,32,32), 3)
                msg_engine.draw_string(screen, (10,2), "WARP/STAIRS")
                msg_engine.draw_string(screen, (10,136), "[X] Draw")
                msg_engine.draw_string(screen, (10,196), "[BS] Delete")
            elif SELECT_MODE == SELECT_MODE_AUTO:
                pygame.draw.rect(screen, (0,255,0), (45,30,32,32), 3)
                msg_engine.draw_string(screen, (10,2), "AUTO MOVE")
                msg_engine.draw_string(screen, (10,136), "[X] Draw")
                msg_engine.draw_string(screen, (10,196), "[BS] Delete")
            elif SELECT_MODE == SELECT_MODE_CHARA:
                pygame.draw.rect(screen, (0,255,0), (80,30,32,32), 3)
                msg_engine.draw_string(screen, (10,2), "CHARA")
                msg_engine.draw_string(screen, (10,136), "[X] Draw")
                msg_engine.draw_string(screen, (10,166), "[BS] Delete")
            elif SELECT_MODE == SELECT_MODE_NPC:
                pygame.draw.rect(screen, (0,255,0), (80,30,32,32), 3)
                msg_engine.draw_string(screen, (10,2), "NPC")
                msg_engine.draw_string(screen, (10,136), "[X] Draw")
                msg_engine.draw_string(screen, (10,166), "[Z] Pick")
                msg_engine.draw_string(screen, (10,196), "[P] Set Place")
                msg_engine.draw_string(screen, (10,226), "[BS] Delete")
            elif SELECT_MODE == SELECT_MODE_LIGHT:
                msg_engine.draw_string(screen, (10,2), "LIGHT SOURCE")
                msg_engine.draw_string(screen, (10,136), "[X] Draw")
                msg_engine.draw_string(screen, (10,166), "[BS] Delete")
            # マウスの座標を描画
            px, py = pygame.mouse.get_pos()
            selectx = int((px + offset[0]) // GS)
            selecty = int((py + offset[1]) // GS)
            px = px // GS
            py = py // GS
            pygame.draw.rect(screen, (0,255,0), (px*GS,py*GS,GS,GS), 3)
            msg_engine.draw_string(screen, (10,76), mmap.name)
            msg_engine.draw_string(screen, (10,106), f"{selectx:d}　{selecty:d}")
            msg_engine.draw_string(screen, (10,286), "[0] MAP")
            msg_engine.draw_string(screen, (10,316), "[1] OBJECT")
            msg_engine.draw_string(screen, (10,346), "[2] TREASURE")
            msg_engine.draw_string(screen, (10,376), "[3] CHARA")
            msg_engine.draw_string(screen, (10,406), "[4] NPC")
            msg_engine.draw_string(screen, (10,436), "[5] DOOR")
            msg_engine.draw_string(screen, (10,466), "[6] SMALL DOOR")
            msg_engine.draw_string(screen, (10,496), "[7] LIGHT")
            msg_engine.draw_string(screen, (10,526), "[8] WARP/STAIRS")
            msg_engine.draw_string(screen, (10,556), "[9] AUTO MOVE")
            msg_engine.draw_string(screen, (10,616), "[S] Save")
            msg_engine.draw_string(screen, (10,646), "[L] Load")
            msg_engine.draw_string(screen, (10,676), "[G] Grid")
            msg_engine.draw_string(screen, (10,706), "[E] Events")
            msg_engine.draw_string(screen, (10,736), "[C] Charas")
            msg_engine.draw_string(screen, (10,766), "[D] Lightsources")
            msg_engine.draw_string(screen, (10,796), "[Q] Quit")
        pygame.display.update()
        RELEASED_BS = RELEASED_ESC = False
        for event in pygame.event.get():
            if event.type == QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == KEYDOWN and event.key == K_q:
                pygame.quit()
                sys.exit()
            elif event.type == KEYDOWN and event.key == K_0:
                SELECT_MODE = SELECT_MODE_MAP
                palette.display_flag = not palette.display_flag
            elif event.type == KEYDOWN and event.key == K_1:
                SELECT_MODE = SELECT_MODE_OBJECT
                palette.display_flag = not palette.display_flag
            elif event.type == KEYDOWN and event.key == K_2:
                SELECT_MODE = SELECT_MODE_TREASURE
#                palette.display_flag = not palette.display_flag
            elif event.type == KEYDOWN and event.key == K_3:
                SELECT_MODE = SELECT_MODE_CHARA
                cpalette.display_flag = not cpalette.display_flag
            elif event.type == KEYDOWN and event.key == K_4:
                SELECT_MODE = SELECT_MODE_NPC
                cpalette.display_flag = not cpalette.display_flag
            elif event.type == KEYDOWN and event.key == K_5:
                SELECT_MODE = SELECT_MODE_DOOR
            elif event.type == KEYDOWN and event.key == K_6:
                SELECT_MODE = SELECT_MODE_SMALLDOOR
            elif event.type == KEYDOWN and event.key == K_7:
                SELECT_MODE = SELECT_MODE_LIGHT
            elif event.type == KEYDOWN and event.key == K_8:
                SELECT_MODE = SELECT_MODE_MOVE
                palette.display_flag = not palette.display_flag
            elif event.type == KEYDOWN and event.key == K_9:
                SELECT_MODE = SELECT_MODE_AUTO
                palette.display_flag = not palette.display_flag
            elif event.type == KEYDOWN and event.key == K_g:
                global SHOW_GRID  # show_gridはグローバル変数
                SHOW_GRID = not SHOW_GRID
            elif event.type == KEYDOWN and event.key == K_e:
                global SHOW_EVENT
                SHOW_EVENT = not SHOW_EVENT
            elif event.type == KEYDOWN and event.key == K_c:
                global SHOW_CHARA
                SHOW_CHARA = not SHOW_CHARA
            elif event.type == KEYDOWN and event.key == K_n:
                # 新規マップ
                try:
                    name = input_wnd.ask(screen, "NAME?")
                    row = int(input_wnd.ask(screen, "ROW?"))
                    col = int(input_wnd.ask(screen, "COL?"))
                    default = int(input_wnd.ask(screen, "DEFAULT?"))
                except ValueError:
                    print("Cannot create map")
                    continue
                mmap = Map(name, row, col, default, palette, cpalette, input_wnd, screen)
            elif event.type == KEYDOWN and event.key == K_s:
                # マップをセーブ
                name = input_wnd.ask(screen, "SAVE JSON?")
                mmap.save_json(name)
            elif event.type == KEYDOWN and event.key == K_l:
                # マップをロード
                try:
                    name = input_wnd.ask(screen, "LOAD JSON?")
                    mmap.load_json(name)
                except IOError:
                    print(f"Cannot load: {name}")
                    continue
            if event.type == KEYDOWN and event.key == K_x:
                pygame.image.save(screen, args.scrfile)
            elif event.type == KEYUP and event.key == K_BACKSPACE:
                RELEASED_BS = True
            elif event.type == KEYUP and event.key == K_ESCAPE:
                RELEASED_ESC = True

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

def calc_offset(cursor):
    """cursorを中心としてオフセットを計算する"""
    offsetx = cursor.rect.topleft[0] - SCR_RECT.width/2
    offsety = cursor.rect.topleft[1] - SCR_RECT.height/2
    return offsetx, offsety

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

def load_mapchips(directory, file):
    """マップチップをロードしてMap.imagesに格納"""
    file = os.path.join(directory, file)
    with open(file, "r", encoding="utf-8") as fp:
        for line in fp:
            line = line.rstrip()
            if line.startswith("#"):
                continue  # コメント行は無視
            data = line.split(",")
            name = data[1]
            movable = int(data[2])
            transparent = int(data[3])
            if transparent == 0:
                Map.images.append(load_image("mapchip", f"{name:s}.png"))
            else:
                Map.images.append(load_image("mapchip", f"{name:s}.png",TRANS_COLOR))
            Map.movable_type.append(movable)
        fp.close()

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

def load_charachips(directory, file):
    """キャラクターチップをロードしてCharacter.imagesに格納"""
    file = os.path.join(directory, file)
    with open(file, "r", encoding="utf-8") as fp:
        for line in fp:
            line = line.rstrip()
            if line.startswith("#"):
                continue  # コメント行は無視
            data = line.split(",")
            chara_name = data[1]
            Character.images[chara_name] = split_image(
                load_image("charachip", f"{chara_name:s}.png", TRANS_COLOR))
        fp.close()

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
            surface.set_colorkey(surface.get_at((0, 0)), RLEACCEL)
            surface.convert()
            image_list.append(surface)
    return image_list


#                                                                        
#   ,ad8888ba,                                                           
#  d8"'    `"8b                                                          
# d8'                                                                    
# 88            88       88 8b,dPPYba, ,adPPYba,  ,adPPYba,  8b,dPPYba,  
# 88            88       88 88P'   "Y8 I8[    "" a8"     "8a 88P'   "Y8  
# Y8,           88       88 88          `"Y8ba,  8b       d8 88          
#  Y8a.    .a8P "8a,   ,a88 88         aa    ]8I "8a,   ,a8" 88          
#   `"Y8888Y"'   `"YbbdP'Y8 88         `"YbbdP"'  `"YbbdP"'  88          
#                                                                        
#                                                                        
# 

class Cursor:
    """カーソルクラス"""
    COLOR = (0,0,255)  # 緑色
    WIDTH = 3  # 太さ
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.rect = Rect(x*GS, y*GS, GS, GS)
    def update(self):
        """キー入力でカーソルを移動"""
        pressed_keys = pygame.key.get_pressed()
        if pressed_keys[K_DOWN]:
            self.y += 1
        elif pressed_keys[K_LEFT]:
            self.x -= 1
        elif pressed_keys[K_RIGHT]:
            self.x += 1
        elif pressed_keys[K_UP]:
            self.y -= 1
        self.rect = Rect(self.x*GS, self.y*GS, GS, GS)
    def draw(self, screen, offset):
        """オフセットを考慮してカーソルを描画"""
        offsetx, offsety = offset
        px = self.rect.topleft[0]
        py = self.rect.topleft[1]
        pygame.draw.rect(screen, self.COLOR, (px-offsetx,py-offsety,GS,GS), self.WIDTH)

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
    """マップクラス"""
    images = []
    movable_type = []  # マップチップが移動可能か？（0:移動不可, 1:移動可）
    def __init__(self, name, row, col, default, palette,cpalette,scr,inputw):
        self.name = name
        self.row = row
        self.col = col
        self.default = default  # デフォルトのマップチップ番号
        self.map = [[self.default for c in range(self.col)] for r in range(self.row)]
        self.palette = palette
        self.cpalette = cpalette
        self.events = []
        self.charas = []
        self.screen = scr
        self.inputwnd = inputw

    def __str__(self):
        return f"{self.name:s},{self.row:d},{self.col:d},{self.default:d}"

    def update(self, offset):
        """マップ更新"""
        offsetx, offsety = offset
        for chara in self.charas:
            chara.update(self)
        mouse_pressed = pygame.mouse.get_pressed()
        pressed_keys = pygame.key.get_pressed()

        if mouse_pressed[0] or pressed_keys[K_x]:
            px, py = pygame.mouse.get_pos()
            # 全体マップ上での座標はoffsetを足せばよい
            # GSで割るのはピクセルをマスに直すため
            selectx = int((px + offsetx) // GS)
            selecty = int((py + offsety) // GS)
            # マップ範囲外だったら無視
            if selectx < 0 or selecty < 0 or selectx > self.col-1 or selecty > self.row-1:
                return
            if SELECT_MODE == SELECT_MODE_MAP:
                # パレットで選択中のマップチップでマップを更新
                self.map[selecty][selectx] = self.palette.selected_mapchip
            elif SELECT_MODE == SELECT_MODE_OBJECT:
                for event in self.events:
                    ox, oy = event.pos()
                    if ox == selectx and oy == selecty and \
                        event.mapchip == self.palette.selected_eventchip:
                        return
                data = {}
                data["type"] = "OBJECT"
                data["x"] = selectx
                data["y"] = selecty
                data["mapchip"] = self.palette.selected_eventchip
                self.create_obj_j(data)
            elif SELECT_MODE == SELECT_MODE_TREASURE:
                for event in self.events:
                    ox, oy = event.pos()
                    if ox == selectx and oy == selecty and event.mapchip == 138:
                        return
                data = {}
                data["type"] = "TREASURE"
                data["x"] = selectx
                data["y"] = selecty
                data["item"] = "宝箱"
                self.create_treasure_j(data)
            elif SELECT_MODE == SELECT_MODE_LIGHT:
                for event in self.events:
                    ox, oy = event.pos()
                    if ox == selectx and oy == selecty and event.mapchip == 1:
                        return
                data = {}
                data["type"] = "ZLIGHT"
                data["x"] = selectx
                data["y"] = selecty
                roomname = str(self.inputwnd.ask(self.screen, "ROOM?"))
                data["roomname"] = roomname
                self.create_light_j(data)

            elif SELECT_MODE == SELECT_MODE_DOOR:
                for event in self.events:
                    ox, oy = event.pos()
                    if ox == selectx and oy == selecty - 2 and event.mapchip == 678:
                        return
                data = {}
                data["type"] = "DOOR"
                data["x"] = selectx
                data["y"] = selecty - 2
                data["doorname"] = str(self.inputwnd.ask(self.screen, "DOOR NAME?"))
                self.create_door_j(data)

            elif SELECT_MODE == SELECT_MODE_SMALLDOOR:
                for event in self.events:
                    ox, oy = event.pos()
                    if ox == selectx and oy == selecty and event.mapchip == 27:
                        return
                data = {}
                data["type"] = "SDOOR"
                data["x"] = selectx
                data["y"] = selecty
                roomname = str(self.inputwnd.ask(self.screen, "DOOR NAME?"))
                data["doorname"] = roomname
                self.create_smalldoor_j(data)

            elif SELECT_MODE == SELECT_MODE_MOVE:
                for event in self.events:
                    ox, oy = event.pos()
                    if ox == selectx and oy == selecty and \
                        event.mapchip == self.palette.selected_eventchip:
                        return
                data = {}
                data["type"] = "MOVE"
                data["mapchip"] = int(self.palette.selected_eventchip)
                data["x"] = selectx
                data["y"] = selecty
                mapname = str(self.inputwnd.ask(self.screen, "JUMP MAP NAME?"))
                data["dest_map"] = mapname
                dest_x = self.inputwnd.ask(self.screen, "MAP X?")
                data["dest_x"] = int(dest_x)
                dest_y = self.inputwnd.ask(self.screen, "MAP Y?")
                data["dest_y"] = int(dest_y)
                self.create_move_j(data)

            elif SELECT_MODE == SELECT_MODE_AUTO:
                for event in self.events:
                    ox, oy = event.pos()
                    if ox == selectx and oy == selecty and \
                        event.mapchip == self.palette.selected_eventchip:
                        return
                data = {}
                data["type"] = "AUTO"
                data["mapchip"] = int(self.palette.selected_eventchip)
                data["x"] = selectx
                data["y"] = selecty
                seq = str(self.inputwnd.ask(self.screen, "SEQUENCE?"))
                data["sequence"] = seq
                self.create_auto_j(data)

            elif SELECT_MODE == SELECT_MODE_CHARA:
                for ch in self.charas:
                    ox, oy = ch.pos()
                    if ox == selectx and oy == selecty and \
                        ch.name == self.cpalette.selected_charachip:
                        return
                data = {}
                data["type"] = "CHARA"
                data["name"] = self.cpalette.selected_charachip
                data["x"] = selectx
                data["y"] = selecty
                data["dir"] = int(self.inputwnd.ask(self.screen, "DIR(0-3)?"))
                movetype = self.inputwnd.ask(self.screen, "MOVE(y/n)?")
                data["movetype"] = 1 if movetype.lower() == "y" else 0
                data["message"] = str(self.inputwnd.ask(self.screen, "MSG?"))
                self.create_chara_j(data)
            elif SELECT_MODE == SELECT_MODE_NPC:
                npcname = ""
                msg = ""
                direction = 0
                movetype = 1
                for ch in self.charas:
                    ox, oy = ch.pos()
                    if ox == selectx and oy == selecty and \
                        ch.name == self.cpalette.selected_charachip:
                        return
                    if ch.__class__.__name__ == "NPCharacter":
                        if ch.name == self.cpalette.selected_charachip:
                            npcname = ch.npcname
                            msg = ch.message
                            direction = ch.direction
                            movetype = ch.movetype
                            self.charas.remove(ch)
                data = {}
                data["type"] = "NPC"
                data["name"] = self.cpalette.selected_charachip
                if npcname == "":
                    npcname = str(self.inputwnd.ask(self.screen, "NAME?"))
                data["npcname"] = npcname
                data["x"] = selectx
                data["y"] = selecty
                data["dir"] = direction
                data["movetype"] = movetype
                if msg == "":
                    msg = str(self.inputwnd.ask(self.screen, "MSG?"))
                data["message"] = msg
                self.create_npc_j(data)
        elif pressed_keys[K_p]:
            px, py = pygame.mouse.get_pos()
            selectx = int((px + offsetx) // GS)
            selecty = int((py + offsety) // GS)
            if selectx < 0 or selecty < 0 or selectx > self.col-1 or selecty > self.row-1:
                return
            if SELECT_MODE == SELECT_MODE_NPC:
                for ch in self.charas:
                    ox, oy = ch.pos()
                    if ox == selectx and oy == selecty and \
                          isinstance(ch,NPCpath) and ch.name == self.cpalette.selected_charachip:
                        return
                pathname = self.inputwnd.ask(self.screen, "PLACE?")
                if pathname is None:
                    return
                for ch in self.charas:
                    if isinstance(ch,NPCpath) and ch.name == self.cpalette.selected_charachip and \
                          ch.pathname == pathname:
                        self.charas.remove(ch)
                data = {}
                data["type"] = "NPCPATH"
                data["name"] = self.cpalette.selected_charachip
                data["pathname"] = pathname
                data["x"] = selectx
                data["y"] = selecty
                self.create_npcpath_j(data)

        elif mouse_pressed[2] or pressed_keys[K_z]:  # 右クリック（マップチップ抽出）
            px, py = pygame.mouse.get_pos()
            selectx = int((px + offsetx) // GS)
            selecty = int((py + offsety) // GS)
            if selectx < 0 or selecty < 0 or selectx > self.col-1 or selecty > self.row-1:
                return
            if SELECT_MODE == SELECT_MODE_MAP:
                self.palette.selected_mapchip = self.map[selecty][selectx]
            elif SELECT_MODE == SELECT_MODE_OBJECT:
                for event in reversed(self.events):
                    ox, oy = event.pos()
                    if not isinstance(event, Door) and not isinstance(event, Treasure) and\
                          ox == selectx and oy == selecty:
                        self.palette.selected_eventchip = event.mapchip
                        return
            elif SELECT_MODE == SELECT_MODE_NPC:
                for chara in reversed(self.charas):
                    ox, oy = chara.pos()
                    if (isinstance(chara, NPCharacter) or isinstance(chara, NPCpath)) and \
                          ox == selectx and oy == selecty:
                        self.cpalette.selected_charachip = chara.name
                        return
                return

        elif RELEASED_BS:  # BS（イベント削除）
            # イベント→キャラの順で消す．1回のBSでは1つだけ．
            px, py = pygame.mouse.get_pos()
            selectx = int((px + offsetx) // GS)
            selecty = int((py + offsety) // GS)
            if selectx < 0 or selecty < 0 or selectx > self.col-1 or selecty > self.row-1:
                return
            for event in reversed(self.events):
                ox, oy = event.pos()
#                if isinstance(event, Door) and ox == selectx and oy == selecty - 2:
                if isinstance(event, Door) and \
                    selectx in range(ox,ox+2) and selecty in range(oy,oy+3):
                    #         ox  ox+1
                    # oy      D    D
                    # oy+1    D    D
                    # oy+2    D    D
                    self.events.remove(event)
                    return
                if ox == selectx and oy == selecty:
                    self.events.remove(event)
                    return
            for chara in self.charas:
                ox, oy = chara.pos()
                if ox == selectx and oy == selecty:
                    self.charas.remove(chara)
                    return

    def draw(self, screen, offset):
        """マップ描画"""
        offsetx, offsety = offset
        # マップの描画範囲を計算
        startx = int(offsetx // GS)
        endx = int(startx + SCR_RECT.width//GS + 2)
        starty = int(offsety // GS)
        endy = int(starty + SCR_RECT.height//GS + 2)
        # マップの描画
        for y in range(starty, endy):
            for x in range(startx, endx):
                # マップの範囲外はマップチップ番号0で描画
                if x < 0 or y < 0 or x > self.col-1 or y > self.row-1:
                    screen.blit(self.images[0], (x*GS-offsetx,y*GS-offsety))
                else:
                    screen.blit(self.images[self.map[y][x]], (x*GS-offsetx,y*GS-offsety))
                    if SHOW_GRID:
                        pygame.draw.rect(screen, (0,0,0), (x*GS-offsetx,y*GS-offsety,GS,GS), 1)
        for event in self.events:
            if SHOW_EVENT:
                event.draw(screen, offset)
            #print(event)
        for chara in self.charas:
            if SHOW_CHARA:
                chara.draw(screen, offset)

    def add_chara(self, chara):
        """キャラクターをマップに追加する"""
        self.charas.append(chara)

    def create_chara_j(self, data):
        """キャラクターを作成してcharasに追加する"""
        name = data["name"]
        x, y = int(data["x"]), int(data["y"])
        direction = int(data["dir"])
        movetype = int(data["movetype"])
        message = data["message"]
        chara = Character(name, (x, y), direction, movetype, message)
        print(chara)
        self.charas.append(chara)

    def create_npc_j(self, data):
        """NPCを作成してcharasに追加する"""
        name = data["name"]
        npcname = data["npcname"]
        dest = (int(data["x"]), int(data["y"]))
        direction = int(data["dir"])
        movetype = int(data["movetype"])
        message = data["message"]
        chara = NPCharacter(name, dest, direction, movetype, message, npcname)
        print(chara)
        self.charas.append(chara)

    def create_npcpath_j(self, data):
        """NPCの部屋での目的地を設定する"""
        npcpath = NPCpath(data["name"],data["pathname"],(int(data["x"]), int(data["y"])))
        print(npcpath)
        self.charas.append(npcpath)

    def create_sign_j(self, data):
        """看板を作成してeventsに追加する"""
        sign = Sign((int(data["x"]), int(data["y"])),data["text"])
        print(sign)
        self.events.append(sign)

    def create_treasure_j(self, data):
        """宝箱を作成してeventsに追加する"""
        treasure = Treasure((int(data["x"]), int(data["y"])), data["item"])
        print(treasure)
        self.events.append(treasure)

    def create_light_j(self, data):
        """光源を作成してeventsに追加する"""
        light = Light((int(data["x"]), int(data["y"])), data["room"])
        print(light)
        self.events.append(light)

    def create_door_j(self, data):
        """ドアを作成してeventsに追加する"""
        door = Door((int(data["x"]), int(data["y"])), data["doorname"])
        door.open()
        print(door)
        self.events.append(door)

    def create_smalldoor_j(self, data):
        """小さいドアを作成してeventsに追加する"""
        door = SmallDoor((int(data["x"]), int(data["y"])), data["doorname"])
        door.close()
        print(door)
        self.events.append(door)

    def create_obj_j(self, data):
        """一般オブジェクトを作成してeventsに追加する"""
        obj = Object((int(data["x"]), int(data["y"])), int(data["mapchip"]))
        print(obj)
        self.events.append(obj)

    def create_move_j(self, data):
        """移動イベントを作成してeventsに追加する"""
        move = MoveEvent((int(data["x"]), int(data["y"])), int(data["mapchip"]),
                          data["dest_map"], (int(data["dest_x"]), int(data["dest_y"])))
        print(move)
        self.events.append(move)

    def create_plpath_j(self, data):
        """プレイヤーの目的地を設定する"""
        pathname = data["pathname"]
        dest = (int(data["x"]),int(data["y"]))
        plpath = PlayerPath(pathname,dest)
        print(plpath)
        self.events.append(plpath)

    def create_placeset_j(self, data):
        """移動イベントを作成してeventsに追加する"""
        x, y = int(data["x"]), int(data["y"])
        mapchip = int(data["mapchip"])
        place_label = data["place_label"]
        place = PlacesetEvent((x, y), mapchip, place_label)
        print(place)
        self.events.append(place)

    def create_auto_j(self, data):
        """自動イベントを作成してeventsに追加する"""
        x, y = int(data["x"]), int(data["y"])
        mapchip = int(data["mapchip"])
        sequence = list(data["sequence"])
        auto = AutoEvent((x, y), mapchip, sequence)
        print(auto)
        self.events.append(auto)

    def save_json(self, name):
        """マップ・イベントをjson形式でfileに保存"""
        file = os.path.join("data", name.lower() + ".json")
        json_data = {}
        json_data["row"] = self.row
        json_data["col"] = self.row
        json_data["default"] = self.default
        json_data["map"] = self.map
        json_data["characters"] = []
        json_data["events"] = []
        self.charas.sort(key=attrgetter('__class__.__name__','name'))
        for chara in self.charas:
            json_data["characters"].append(chara.json())
        self.events.sort(key=attrgetter('z_axis'))
        for event in self.events:
            json_data["events"].append(event.json())
        with codecs.open(file,"w","utf-8") as fp:
            fp.write(json.dumps(json_data,indent=2))

    def load_json(self, name):
        """json形式のマップ・イベントを読み込む"""
        file = os.path.join("data", name.lower() + ".json")
        with codecs.open(file, "r", "utf-8") as fp:
            json_data = json.load(fp)
        self.name = name
        # unpack()はタプルが返されるので[0]だけ抽出
        self.row = json_data["row"]
        self.col = json_data["col"]
        self.default = json_data["default"]
        self.map = json_data["map"]
        self.events = []
        self.charas = []
        for chara in json_data["characters"]:
            chara_type = chara["type"]
            if chara_type in ["CHARA", "CHARARETURN","CHARAMOVEITEMS"]:  # キャラクター
                self.create_chara_j(chara)
            elif chara_type == "NPC":  # NPC
                self.create_npc_j(chara)
            elif chara_type == "NPCPATH":  # NPCPATH
                self.create_npcpath_j(chara)
        for event in json_data["events"]:
            event_type = event["type"]
            if event_type == "OBJECT":  # 一般オブジェクト
                self.create_obj_j(event)
            elif event_type == "SIGN":  # 看板
                self.create_sign_j(event)
            elif event_type == "TREASURE":  # 宝箱
                self.create_treasure_j(event)
            elif event_type == "DOOR":  # ドア
                self.create_door_j(event)
            elif event_type == "SDOOR":  # ドア
                self.create_smalldoor_j(event)
            elif event_type == "ZLIGHT":  # 光源
                self.create_light_j(event)
            elif event_type == "MOVE":  # マップ間移動イベント
                self.create_move_j(event)
            elif event_type == "AUTO":  # 移動
                self.create_auto_j(event)
            elif event_type == "PLPATH":  # player path
                self.create_plpath_j(event)
            elif event_type == "PLACESET":  # placeset
                self.create_placeset_j(event)


#                                                                                                                                                
# 88b           d88                                   88          88             88888888ba             88                                       
# 888b         d888                                   88          ""             88      "8b            88              ,d      ,d               
# 88`8b       d8'88                                   88                         88      ,8P            88              88      88               
# 88 `8b     d8' 88 ,adPPYYba, 8b,dPPYba,   ,adPPYba, 88,dPPYba,  88 8b,dPPYba,  88aaaaaa8P' ,adPPYYba, 88  ,adPPYba, MM88MMM MM88MMM ,adPPYba,  
# 88  `8b   d8'  88 ""     `Y8 88P'    "8a a8"     "" 88P'    "8a 88 88P'    "8a 88""""""'   ""     `Y8 88 a8P_____88   88      88   a8P_____88  
# 88   `8b d8'   88 ,adPPPPP88 88       d8 8b         88       88 88 88       d8 88          ,adPPPPP88 88 8PP"""""""   88      88   8PP"""""""  
# 88    `888'    88 88,    ,88 88b,   ,a8" "8a,   ,aa 88       88 88 88b,   ,a8" 88          88,    ,88 88 "8b,   ,aa   88,     88,  "8b,   ,aa  
# 88     `8'     88 `"8bbdP"Y8 88`YbbdP"'   `"Ybbd8"' 88       88 88 88`YbbdP"'  88          `"8bbdP"Y8 88  `"Ybbd8"'   "Y888   "Y888 `"Ybbd8"'  
#                              88                                    88                                                                          
#                              88                                    88                                                                          
# 

class MapchipPalette:
    """マップチップパレット"""
    ROW = 24  # パレットの行数
    COL = 32  # パレットの列数
    COLOR = (0,255,0)  # 緑
    WIDTH = 3  # カーソルの太さ
    PALETTE_X = 1920//2 - (GS*COL//2)
    PALETTE_Y = 1080//2 - (GS*ROW//2)
    def __init__(self):
#        self.select_mode = 0  # 0: map 1: event
        self.display_flag = False  # Trueのときパレット表示
        self.selected_mapchip = 3  # 選択しているマップチップ番号
        self.selected_eventchip = 3  # 選択しているマップチップ番号

    def update(self):
        """更新"""
        if RELEASED_ESC:
            self.display_flag = False
            pygame.time.wait(500)
            return
        mouse_pressed = pygame.mouse.get_pressed()
        if mouse_pressed[0]:
            mouse_pos = pygame.mouse.get_pos()
            x = (mouse_pos[0] - self.PALETTE_X) // GS
            y = (mouse_pos[1] - self.PALETTE_Y) // GS
            n = int(y * self.COL + x)
            if n < len(Map.images) and Map.images[n] is not None:
                if SELECT_MODE == SELECT_MODE_MAP:
                    self.selected_mapchip = n
                elif SELECT_MODE in (SELECT_MODE_OBJECT, SELECT_MODE_MOVE, SELECT_MODE_AUTO):
                    self.selected_eventchip = n
                self.display_flag = False
                pygame.time.wait(500)

    def draw(self, screen):
        """パレットを描画する"""
        # 枠を描画
        pygame.draw.rect(screen, (255,255,255),
                         (self.PALETTE_X - 3,self.PALETTE_Y - 3,
                          GS*self.COL + 6, GS*self.ROW + 6), self.WIDTH, 3)
        # パレットを描画
        for i in range(self.ROW * self.COL):
            x = self.PALETTE_X + (i % self.COL) * GS
            y = self.PALETTE_Y + (i // self.COL) * GS
            image = Map.images[0]
            try:
                if Map.images[i] is not None:
                    image = Map.images[i]
            except IndexError:  # イメージが登録されてないとき
                image = Map.images[0]
            screen.blit(Map.images[0], (x,y))
            screen.blit(image, (x,y))
            try:
                if Map.movable_type[i] == 1:
                    pygame.draw.rect(screen, (0,255,255), (x,y,GS,GS), self.WIDTH)
            except Exception:
                pass
        mouse_pos = pygame.mouse.get_pos()
        mx = mouse_pos[0] // GS
        my = mouse_pos[1] // GS
        if mx >= self.PALETTE_X // GS and my > self.PALETTE_Y // GS and \
              mx < self.PALETTE_X // GS + self.COL and my <= self.PALETTE_Y // GS + self.ROW:
            pygame.draw.rect(screen, self.COLOR, (mx*GS,my*GS,GS,GS), self.WIDTH)

#                                                                                                                                                                  
#   ,ad8888ba,  88                                                      88          88             88888888ba             88                                       
#  d8"'    `"8b 88                                                      88          ""             88      "8b            88              ,d      ,d               
# d8'           88                                                      88                         88      ,8P            88              88      88               
# 88            88,dPPYba,  ,adPPYYba, 8b,dPPYba, ,adPPYYba,  ,adPPYba, 88,dPPYba,  88 8b,dPPYba,  88aaaaaa8P' ,adPPYYba, 88  ,adPPYba, MM88MMM MM88MMM ,adPPYba,  
# 88            88P'    "8a ""     `Y8 88P'   "Y8 ""     `Y8 a8"     "" 88P'    "8a 88 88P'    "8a 88""""""'   ""     `Y8 88 a8P_____88   88      88   a8P_____88  
# Y8,           88       88 ,adPPPPP88 88         ,adPPPPP88 8b         88       88 88 88       d8 88          ,adPPPPP88 88 8PP"""""""   88      88   8PP"""""""  
#  Y8a.    .a8P 88       88 88,    ,88 88         88,    ,88 "8a,   ,aa 88       88 88 88b,   ,a8" 88          88,    ,88 88 "8b,   ,aa   88,     88,  "8b,   ,aa  
#   `"Y8888Y"'  88       88 `"8bbdP"Y8 88         `"8bbdP"Y8  `"Ybbd8"' 88       88 88 88`YbbdP"'  88          `"8bbdP"Y8 88  `"Ybbd8"'   "Y888   "Y888 `"Ybbd8"'  
#                                                                                      88                                                                          
#                                                                                      88                                                                          
# 

class CharachipPalette:
    """キャラクタチップパレット"""
    ROW = 24  # パレットの行数
    COL = 32  # パレットの列数
    COLOR = (0,255,0)  # 緑
    WIDTH = 3  # カーソルの太さ
    PALETTE_X = 1920//2 - (GS*COL//2)
    PALETTE_Y = 1080//2 - (GS*ROW//2)

    def __init__(self):
        self.display_flag = False
        k = list(Character.images.keys())
        self.selected_charachip = k[0]
    def update(self):
        """更新"""
        if RELEASED_ESC:
            self.display_flag = False
            pygame.time.wait(500)
            return
        mouse_pressed = pygame.mouse.get_pressed()
        if mouse_pressed[0]:
            mouse_pos = pygame.mouse.get_pos()
            x = (mouse_pos[0] - self.PALETTE_X) // GS
            y = (mouse_pos[1] - self.PALETTE_Y) // GS
            n = int(y * self.COL + x)
            k = list(Character.images.keys())
            if n < len(k) and k[n] is not None:
                self.selected_charachip = k[n]
                self.display_flag = False
                pygame.time.wait(500)
    def draw(self, screen):
        """パレットを描画"""
        # 枠を描画
        pygame.draw.rect(screen, (255,255,255),
                         (self.PALETTE_X - 3,self.PALETTE_Y - 3,
                          GS*self.COL + 6, GS*self.ROW + 6), self.WIDTH, 3)
        # パレットを描画
        for i in range(self.ROW * self.COL):
            x = self.PALETTE_X + (i % self.COL) * GS
            y = self.PALETTE_Y + (i // self.COL) * GS
            k = list(Character.images.keys())
            image = Character.images[k[0]][0]
            try:
                if Character.images[k[i]] is not None:
                    image = Character.images[k[i]][0]
            except IndexError:
                image = Map.images[0]
            screen.blit(Map.images[0], (x,y))
            screen.blit(image, (x,y))
        mouse_pos = pygame.mouse.get_pos()
        x = mouse_pos[0] // GS
        y = mouse_pos[1] // GS
        if x >= self.PALETTE_X // GS and y > self.PALETTE_Y // GS and \
              x < self.PALETTE_X // GS + self.COL and y <= self.PALETTE_Y // GS + self.ROW:
            pygame.draw.rect(screen, self.COLOR, (x*GS,y*GS,GS,GS), self.WIDTH)

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
    animcycle = MAX_FRAME_PER_SEC // 4 # アニメーション速度
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
        """座標"""
        return (self.x, self.y)

    def set_speed(self, s):
        """スピードを設定"""
        self.speed = s

    def update(self, mmap):
        """キャラクター状態を更新する。
        mapは移動可能かの判定に必要。"""
        # キャラクターアニメーション（frameに応じて描画イメージを切り替える）
        self.frame += 1
        self.image = self.images[self.name][self.direction *
                                            4+(self.frame // self.animcycle % 4)]

    def draw(self, screen, offset):
        """オフセットを考慮してプレイヤーを描画"""
        offsetx, offsety = offset
        px = self.rect.topleft[0]
        py = self.rect.topleft[1]
        screen.blit(self.image, (px-offsetx, py-offsety))
        #screen.blit(MYFONT18.render(self.npcname, Color(255, 255, 255, 255))[
        #            0], (px-offsetx, py-offsety-18))
        #screen.blit(MYFONT18.render(str(self.hp), self.hp_color)
        #            [0], (px-offsetx+32, py-offsety))

    def set_pos(self, x, y, direction):
        """キャラクターの位置と向きをセット"""
        self.x, self.y = x, y
        self.rect = self.image.get_rect(topleft=(self.x*GS, self.y*GS))
        self.direction = direction

    def __str__(self):
        return json.dumps(self.json(),indent=2)

    def json(self):
        """returns data for json"""
        json_data = {}
        json_data["type"] = "CHARA"
        json_data["name"] = self.name
        json_data["x"] = self.x
        json_data["y"] = self.y
        json_data["dir"] = self.direction
        json_data["movetype"] = self.movetype
        json_data["message"] = self.message
        return json_data

#                                                                                                                              
# 888b      88 88888888ba    ,ad8888ba,  88                                                                                    
# 8888b     88 88      "8b  d8"'    `"8b 88                                                        ,d                          
# 88 `8b    88 88      ,8P d8'           88                                                        88                          
# 88  `8b   88 88aaaaaa8P' 88            88,dPPYba,  ,adPPYYba, 8b,dPPYba, ,adPPYYba,  ,adPPYba, MM88MMM ,adPPYba, 8b,dPPYba,  
# 88   `8b  88 88""""""'   88            88P'    "8a ""     `Y8 88P'   "Y8 ""     `Y8 a8"     ""   88   a8P_____88 88P'   "Y8  
# 88    `8b 88 88          Y8,           88       88 ,adPPPPP88 88         ,adPPPPP88 8b           88   8PP""""""" 88          
# 88     `8888 88           Y8a.    .a8P 88       88 88,    ,88 88         88,    ,88 "8a,   ,aa   88,  "8b,   ,aa 88          
# 88      `888 88            `"Y8888Y"'  88       88 `"8bbdP"Y8 88         `"8bbdP"Y8  `"Ybbd8"'   "Y888 `"Ybbd8"' 88          
#                                                                                                                              
#                                                                                                                              
# 

class NPCharacter(Character):
    """NPCharacterクラス"""
    FONT_WIDTH = 16
    FONT_HEIGHT = 22

    def __init__(self, name, pos, direction, movetype, message, npcname):
        super().__init__(name, pos, direction, movetype, message)
        self.npcname = npcname  # 頭の上の名前
        self.myfont = pygame.freetype.Font(FONT_DIR + FONT_NAME, self.FONT_HEIGHT)

    def draw(self, screen, offset):
        """オフセットを考慮してプレイヤーを描画"""
        offsetx, offsety = offset
        px = self.rect.topleft[0]
        py = self.rect.topleft[1]
        screen.blit(self.image, (px-offsetx, py-offsety))
        screen.blit(self.myfont.render(self.npcname, Color(255, 255, 255, 255))[0],
                    (px-offsetx, py-offsety-18))

    def json(self):
        """returns data for json"""
        json_data = {}
        json_data["type"] = "NPC"
        json_data["name"] = self.name
        json_data["npcname"] = self.npcname
        json_data["x"] = self.x
        json_data["y"] = self.y
        json_data["dir"] = self.direction
        json_data["movetype"] = self.movetype
        json_data["message"] = self.message
        return json_data

    def __str__(self):
        return json.dumps(self.json(),indent=2)

#                                                                                    
# 888b      88 88888888ba    ,ad8888ba,                                 88           
# 8888b     88 88      "8b  d8"'    `"8b                          ,d    88           
# 88 `8b    88 88      ,8P d8'                                    88    88           
# 88  `8b   88 88aaaaaa8P' 88            8b,dPPYba,  ,adPPYYba, MM88MMM 88,dPPYba,   
# 88   `8b  88 88""""""'   88            88P'    "8a ""     `Y8   88    88P'    "8a  
# 88    `8b 88 88          Y8,           88       d8 ,adPPPPP88   88    88       88  
# 88     `8888 88           Y8a.    .a8P 88b,   ,a8" 88,    ,88   88,   88       88  
# 88      `888 88            `"Y8888Y"'  88`YbbdP"'  `"8bbdP"Y8   "Y888 88       88  
#                                        88                                          
#                                        88                                          
# 

class NPCpath(NPCharacter):
    """NPCpathクラス"""
    def __init__(self, name, pathname, pos):
        super().__init__(name, pos, 0, 0, "", "")
        self.pathname = pathname  # 行き先

    def draw(self, screen, offset):
        """オフセットを考慮してプレイヤーを描画"""
        offsetx, offsety = offset
        px = self.rect.topleft[0]
        py = self.rect.topleft[1]
        screen.blit(self.image, (px-offsetx, py-offsety))
        screen.blit(self.myfont.render(self.pathname,
                                    Color(255, 255, 255, 255))[0], (px-offsetx, py-offsety+32+2))

    def json(self):
        """returns data for json"""
        json_data = {}
        json_data["type"] = "NPCPATH"
        json_data["name"] = self.name
        json_data["pathname"] = self.pathname
        json_data["x"] = self.x
        json_data["y"] = self.y
        return json_data

    def __str__(self):
        return json.dumps(self.json(),indent=2)

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
    FONT_HEIGHT = 22
    WHITE = Color(255,255,255,255)
    RED = Color(255,31,31,255)
    GREEN = Color(31,255,31,255)
    BLUE = Color(31,31,255,255)
    def __init__(self):
        self.color = self.WHITE
        self.myfont = pygame.freetype.Font(FONT_DIR + FONT_NAME, self.FONT_HEIGHT)
    def set_color(self, color):
        """文字色をセット"""
        self.color = color
        # 変な値だったらWHITEにする
        if not self.color in [self.WHITE,self.RED,self.GREEN,self.BLUE]:
            self.color = self.WHITE
    def draw_character(self, screen, pos, ch):
        """1文字だけ描画する"""
        x, y = pos
        try:
            surf,rect = self.myfont.render(ch,self.color)
            screen.blit(surf,(x,y+(self.FONT_HEIGHT)-rect[3]))
#            screen.blit(self.myfont.render(ch,True,self.WHITE),(x,y))
        except KeyError:
            print(f"描画できない文字があります:{ch}")
            return
    def draw_string(self, screen, pos, string):
        """文字列を描画"""
        x, y = pos
        screen.blit(self.myfont.render(string,self.WHITE)[0],(x,y))
#        for i, ch in enumerate(str):
#            dx = x + self.FONT_WIDTH * i
#            self.draw_character(screen, (dx,y), ch)

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
        self.rect = rect  # 一番外側の白い矩形
        self.inner_rect = self.rect.inflate(-self.EDGE_WIDTH*2, -self.EDGE_WIDTH*2)  # 内側の黒い矩形
        self.is_visible = False  # ウィンドウを表示中か？
    def draw(self, screen):
        """ウィンドウを描画"""
        if not self.is_visible:
            return
        pygame.draw.rect(screen, (255,255,255), self.rect, 0)
        pygame.draw.rect(screen, (0,0,0), self.inner_rect, 0)
    def show(self):
        """ウィンドウを表示"""
        self.is_visible = True
    def hide(self):
        """ウィンドウを隠す"""
        self.is_visible = False

#                                                                                                                                 
# 88                                           I8,        8        ,8I 88                      88                                 
# 88                                       ,d  `8b       d8b       d8' ""                      88                                 
# 88                                       88   "8,     ,8"8,     ,8"                          88                                 
# 88 8b,dPPYba,  8b,dPPYba,  88       88 MM88MMM Y8     8P Y8     8P   88 8b,dPPYba,   ,adPPYb,88  ,adPPYba,  8b      db      d8  
# 88 88P'   `"8a 88P'    "8a 88       88   88    `8b   d8' `8b   d8'   88 88P'   `"8a a8"    `Y88 a8"     "8a `8b    d88b    d8'  
# 88 88       88 88       d8 88       88   88     `8a a8'   `8a a8'    88 88       88 8b       88 8b       d8  `8b  d8'`8b  d8'   
# 88 88       88 88b,   ,a8" "8a,   ,a88   88,     `8a8'     `8a8'     88 88       88 "8a,   ,d88 "8a,   ,a8"   `8bd8'  `8bd8'    
# 88 88       88 88`YbbdP"'   `"YbbdP'Y8   "Y888    `8'       `8'      88 88       88  `"8bbdP"Y8  `"YbbdP"'      YP      YP      
#                88                                                                                                               
#                88                                                                                                               
# 

class InputWindow(Window):
    """入力ウィンドウクラス"""
    def __init__(self, rect, msg_engine):
        Window.__init__(self, rect)
        self.msg_engine = msg_engine
    def get_key(self):
        """キー入力を読み取る"""
        while True:
            event = pygame.event.poll()
            if event.type == KEYDOWN:
                return event
    def draw(self, screen, message):
        """描画"""
        Window.draw(self, screen)
        if len(message) != 0:
            self.msg_engine.draw_string(screen, self.inner_rect.topleft, message)
            pygame.display.flip()

    def ask_text(self, screen, question):
        """確認ダイアログ"""
        cur_str = []
        self.show()
        self.draw(screen, question)
        while True:
            ev = self.get_key()
            if ev.key == K_BACKSPACE:
                cur_str = cur_str[0:-1]
            elif ev.key == K_ESCAPE:
                return None
            elif ev.key == K_RETURN:
                break
            else:
                cur_str.append(chr(ev.key))
            self.draw(screen, question + " " + "".join(cur_str))
        return "".join(cur_str)
    def ask(self, screen, question):
        """入力処理"""
        text = Text()  # テキスト処理のロジックTextクラスをインスタンス化
        # テキスト入力時のキーとそれに対応するイベント
        call_trigger = {
            K_BACKSPACE: text.delete_left_of_cursor,
            K_DELETE: text.delete_right_of_cursor,
            K_LEFT: text.move_cursor_left,
            K_RIGHT: text.move_cursor_right,
            K_RETURN: text.enter,
        }
        pygame.key.start_text_input()  # input, editingイベントをキャッチするようにする
        input_text = format(text)
        cur_str = ""
        self.show()
        self.draw(screen, question)
        while True:
            for event in pygame.event.get():
                if event.type == KEYDOWN and not text.is_editing:
                    if event.key in call_trigger.keys():
                        input_text = call_trigger[event.key]()
                    # 入力の確定
                    if event.unicode in ("\r", "") and event.key == K_RETURN:
                        print(input_text)  # 確定した文字列を表示
                        cur_str = input_text
                        self.draw(screen, f"{question:s} {format(text):s}")
                        input_text = format(text)  # "|"に戻す
                        return cur_str
                elif event.type == TEXTEDITING:  # 全角入力
                    input_text = text.edit(event.text, event.start)
                elif event.type == TEXTINPUT:  # 半角入力、もしくは全角入力時にenterを押したとき
                    input_text = text.input(event.text)
                # 描画しなおす必要があるとき
                if event.type in [KEYDOWN, TEXTEDITING, TEXTINPUT]:
                    self.draw(screen, f"{question:s} {input_text:s}")

                #self.draw(screen, f"{question:s} {cur_str:s}")

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
        self.z_axis = 1

    def pos(self):
        """座標"""
        return (self.x, self.y)

    def draw(self, screen, offset):
        """オフセットを考慮してイベントを描画"""
        offsetx, offsety = offset
        px = self.rect.topleft[0]
        py = self.rect.topleft[1]
        screen.blit(self.image, (px-offsetx, py-offsety))

    def json(self):
        """json data"""
        json_data = {}
        json_data["type"] = "OBJECT"
        json_data["x"] = self.x
        json_data["y"] = self.y
        json_data["mapchip"] = self.mapchip
        return json_data

    def __str__(self):
        return json.dumps(self.json(),indent=2)

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

class Treasure(Object):
    """宝箱"""

    def __init__(self, pos, item):
        self.x, self.y = pos[0], pos[1]  # 宝箱座標
        self.mapchip = 138  # 宝箱は138
        self.image = Map.images[self.mapchip]
        self.rect = self.image.get_rect(topleft=(self.x*GS, self.y*GS))
        self.item = item  # アイテム名
        self.z_axis = 2

    def json(self):
        """json data"""
        json_data = {}
        json_data["type"] = "TREASURE"
        json_data["x"] = self.x
        json_data["y"] = self.y
        json_data["item"] = self.item
        return json_data

    def __str__(self):
        return json.dumps(self.json(),indent=2)

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

class Light(Object):
    """光源"""

    def __init__(self, pos, item):
        self.x, self.y = pos[0], pos[1]  # 座標
        self.mapchip = 1  # 光源は1
        self.image = Map.images[self.mapchip]
        self.rect = self.image.get_rect(topleft=(self.x*GS, self.y*GS))
        self.room = str(item)  # 部屋名
        self.z_axis = 5

    def json(self):
        """json data"""
        json_data = {}
        json_data["type"] = "ZLIGHT"
        json_data["x"] = self.x
        json_data["y"] = self.y
        json_data["room"] = self.room
        return json_data

    def __str__(self):
        return json.dumps(self.json(),indent=2)
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
        self.z_axis = 3

    def pos(self):
        """座標を返す"""
        return (self.x, self.y)

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

    def json(self):
        """json data"""
        json_data = {}
        json_data["type"] = "DOOR"
        json_data["x"] = self.x
        json_data["y"] = self.y
        json_data["doorname"] = self.doorname
        return json_data

    def __str__(self):
        return json.dumps(self.json(),indent=2)

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
        self.mapchip_list = [27,688]
        self.status = 0 # close
        self.x, self.y = pos[0], pos[1]  # ドア座標
        self.doorname = str(name)  # ドア名
        self.z_axis = 3

    def draw(self, screen, offset):
        """オフセットを考慮してイベントを描画"""
        offsetx, offsety = offset
        image = Map.images[self.mapchip_list[self.status]]
        rect = image.get_rect(topleft=(self.x*GS, self.y*GS))
        px = rect.topleft[0]
        py = rect.topleft[1]
        screen.blit(image, (px-offsetx, py-offsety))

    def json(self):
        """json data"""
        json_data = {}
        json_data["type"] = "SDOOR"
        json_data["x"] = self.x
        json_data["y"] = self.y
        json_data["doorname"] = str(self.doorname)
        return json_data

    def __str__(self):
        return json.dumps(self.json(),indent=2)

class Sign(Object):
    """看板"""
    FONT_HEIGHT = 18
    WHITE = Color(255, 255, 255, 255)

    def __init__(self, pos, text):
        self.mapchip = 691
        self.mapchip_left = 691
        self.mapchip_right = 693
        self.mapchip_center = 692
        self.x, self.y = pos[0], pos[1]  # 座標
        self.text = text  # アイテム名
        self.myfont = pygame.freetype.Font(
            FONT_DIR + FONT_NAME, self.FONT_HEIGHT)
        self.z_axis = 1

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
        return json.dumps(self.json(),indent=2)

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
class AutoEvent(Object):
    """自動イベント"""

    def __init__(self, pos, mapchip, sequence):
        self.x, self.y = pos[0], pos[1]  # イベント座標
        self.mapchip = mapchip  # マップチップ
        self.image = Map.images[self.mapchip]
        self.rect = self.image.get_rect(topleft=(self.x*GS, self.y*GS))
        self.sequence = sequence  # 移動シーケンス
        self.z_axis = 1

    def json(self):
        """json data"""
        json_data = {}
        json_data["type"] = "AUTO"
        json_data["x"] = self.x
        json_data["y"] = self.y
        json_data["mapchip"] = self.mapchip
        json_data["sequence"] = ''.join(self.sequence)
        return json_data

    def __str__(self):
        return json.dumps(self.json(),indent=2)


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

class MoveEvent(Object):
    """移動イベント"""

    def __init__(self, pos, mapchip, dest_map, dest_pos):
        self.x, self.y = pos[0], pos[1]  # イベント座標
        self.mapchip = mapchip  # マップチップ
        self.dest_map = dest_map  # 移動先マップ名
        self.dest_x, self.dest_y = dest_pos[0], dest_pos[1]  # 移動先座標
        self.image = Map.images[self.mapchip]
        self.rect = self.image.get_rect(topleft=(self.x*GS, self.y*GS))
        self.z_axis = 4

    def json(self):
        """json data"""
        json_data = {}
        json_data["type"] = "MOVE"
        json_data["x"] = self.x
        json_data["y"] = self.y
        json_data["mapchip"] = self.mapchip
        json_data["dest_map"] = self.dest_map
        json_data["dest_x"] = self.dest_x
        json_data["dest_y"] = self.dest_y
        return json_data

    def __str__(self):
        return json.dumps(self.json(),indent=2)

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
        self.z_axis = 1

    def draw(self, screen, offset):
        """オフセットを考慮してイベントを描画"""
        offsetx, offsety = offset
        px = self.rect.topleft[0]
        py = self.rect.topleft[1]
        screen.blit(self.image, (px-offsetx, py-offsety))

    def json(self):
        """json data"""
        json_data = {}
        json_data["type"] = "PLACESET"
        json_data["x"] = self.x
        json_data["y"] = self.y
        json_data["mapchip"] = self.mapchip
        json_data["place_label"] = self.place_label
        return json_data

    def __str__(self):
        return json.dumps(self.json(),indent=2)

class PlayerPath():
    """プレイヤーパスイベント"""
    # マップエディッタにしか存在しないクラス

    def __init__(self, pathname, pos):
        self.x, self.y = pos[0], pos[1]  # イベント座標
        self.pathname = pathname  # パス名
        self.z_axis = 1

    def draw(self, screen, offset):
        """オフセットを考慮してイベントを描画"""
        return

    def json(self):
        """json data"""
        json_data = {}
        json_data["type"] = "PLPATH"
        json_data["x"] = self.x
        json_data["y"] = self.y
        json_data["pathname"] = self.pathname
        return json_data

    def __str__(self):
        return json.dumps(self.json(),indent=2)

#                                         
# 888888888888                            
#      88                          ,d     
#      88                          88     
#      88  ,adPPYba, 8b,     ,d8 MM88MMM  
#      88 a8P_____88  `Y8, ,8P'    88     
#      88 8PP"""""""    )888(      88     
#      88 "8b,   ,aa  ,d8" "8b,    88,    
#      88  `"Ybbd8"' 8P'     `Y8   "Y888  
#                                         
#                                         
# 

class Text:
    """
    PygameのINPUT、EDITINGイベントで使うクラス
    カーソル操作や文字列処理に使う
    """

    def __init__(self) -> None:
        self.text = ["|"]  # 入力されたテキストを格納していく変数
        self.editing: List[str] = []  # 全角の文字編集中(変換前)の文字を格納するための変数
        self.is_editing = False  # 編集中文字列の有無(全角入力時に使用)
        self.cursor_pos = 0  # 文字入力のカーソル(パイプ|)の位置

    def __str__(self) -> str:
        """self.textリストを文字列にして返す"""
        return "".join(self.text)

    def edit(self, text: str, editing_cursor_pos: int) -> str:
        """
        edit(編集中)であるときに呼ばれるメソッド
        全角かつ漢字変換前の確定していないときに呼ばれる
        """
        if text:  # テキストがあるなら
            self.is_editing = True
            for x in text:
                self.editing.append(x)  # 編集中の文字列をリストに格納していく
            self.editing.insert(editing_cursor_pos, "|")  # カーソル位置にカーソルを追加
            disp = "[" + "".join(self.editing) + "]"
        else:
            self.is_editing = False  # テキストが空の時はFalse
            disp = "|"
        self.editing = []  # 次のeditで使うために空にする
        # self.cursorを読み飛ばして結合する
        return (
            format(self)[0 : self.cursor_pos]
            + disp
            + format(self)[self.cursor_pos + 1 :]
        )

    def input(self, text: str) -> str:
        """半角文字が打たれたとき、もしくは全角で変換が確定したときに呼ばれるメソッド"""
        self.is_editing = False  # 編集中ではなくなったのでFalseにする
        for x in text:
            self.text.insert(self.cursor_pos, x)  # カーソル位置にテキストを追加
            # 現在のカーソル位置にテキストを追加したので、カーソル位置を後ろにずらす
            self.cursor_pos += 1
        return format(self)

    def delete_left_of_cursor(self) -> str:
        """カーソルの左の文字を削除するためのメソッド"""
        # カーソル位置が0であるとき
        if self.cursor_pos == 0:
            return format(self)
        self.text.pop(self.cursor_pos - 1)  # カーソル位置の一個前(左)を消す
        self.cursor_pos -= 1  # カーソル位置を前にずらす
        return format(self)

    def delete_right_of_cursor(self) -> str:
        """カーソルの右の文字を削除するためのメソッド"""
        # カーソル位置より後ろに文字がないとき
        if len(self.text[self.cursor_pos+1:]) == 0:
            return format(self)
        self.text.pop(self.cursor_pos + 1)  # カーソル位置の一個後(右)を消す
        return format(self)

    def enter(self) -> str:
        """入力文字が確定したときに呼ばれるメソッド"""
        # カーソルを読み飛ばす
        entered = (
            format(self)[0 : self.cursor_pos] + format(self)[self.cursor_pos + 1 :]
        )
        self.text = ["|"]  # 次回の入力で使うためにself.textを空にする
        self.cursor_pos = 0  # self.text[0] == "|"となる
        return entered

    def move_cursor_left(self) -> str:
        """inputされた文字のカーソル(パイプ|)の位置を左に動かすメソッド"""
        if self.cursor_pos > 0:
            # カーソル位置をカーソル位置の前の文字と交換する
            self.text[self.cursor_pos], self.text[self.cursor_pos - 1] = (
                self.text[self.cursor_pos - 1],
                self.text[self.cursor_pos],
            )
            self.cursor_pos -= 1  # カーソルが1つ前に行ったのでデクリメント
        return format(self)

    def move_cursor_right(self) -> str:
        """inputされた文字のカーソル(パイプ|)の位置を右に動かすメソッド"""
        if len(self.text) - 1 > self.cursor_pos:
            # カーソル位置をカーソル位置の後ろの文字と交換する
            self.text[self.cursor_pos], self.text[self.cursor_pos + 1] = (
                self.text[self.cursor_pos + 1],
                self.text[self.cursor_pos],
            )
            self.cursor_pos += 1  # カーソルが1つ後ろに行ったのでインクリメント
        return format(self)

if __name__ == "__main__":
    main()
