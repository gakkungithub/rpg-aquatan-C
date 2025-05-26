RPG風あくあたん simple.py
=========================
Original program is taken from http://aidiary.hatenablog.com/entry/20080507/1269694935

Scripts
----------
* simple.py: メインプログラム

```
pipenv run python simple.py -h
usage: simple.py [-h] [-f] [-S INTERVAL] [--screenshot_file FILE] [-j] [--light] [-d] [-i FILE] [-b FRAMEBUFFER] [-t TIME] [-D]

options:
  -h, --help            show this help message and exit
  -f, --fullscreen      show in fullscreen mode (Mac)
  -S INTERVAL, --screenshot INTERVAL
                        Take a screenshot by specified secs
  --screenshot_file FILE
                        specify screenshot file
  -j, --json            use json format as map data
  --light               use time info and light control 
  -d, --dark            use spotlight mode in dark dangeon
  -i FILE, --inifile FILE
                        specify ini file
  -b FRAMEBUFFER, --fb FRAMEBUFFER
                        specify framebuffer
  -t TIME, --time TIME  set fixed datetime
  -D, --debug           debug mode
```
注記: 
-j はデフォルトでTrue
-d 闇の中で自分の周りがすこしだけ見えるモードになる
--light 時間経過に応じて画面の雰囲気が変わるモード(光源を配置すると夜になると光る，など)

プレイヤーの初期位置は simple.ini に記述.
以下はマップsimpleの(3,3)からキャラクター15070をプレーヤーにして実行
```
[screen]
width = 1024
height = 768

[game]
player = 15070
player_x = 3
player_y = 3
map = simple
```

普通の実行
```
pipenv run python simple.py 
```

ゲーム中に「s」キーを押すとスクショを撮ります．(sshot.pngに上書きしていきます．)

## イベントの種類

### SDOOR

小さいドア．そちらに向かってスペースを押すと開く．
```
{
  "type": "SDOOR",
  "x": 12,
  "y": 12,
  "doorname": "door2"
}
```
アイテムなどとはこれから連携．

### MOVE

移動イベント．マップ内移動からマップ間移動まで任意の場所へ移動可能．
```
{
  "type": "MOVE",
  "x": 14,
  "y": 17,
  "mapchip": 158,
  "dest_map": "simple",
  "dest_x": 3,
  "dest_y": 3
}
```
(x,y)にmapchipで描画．mapchipは進入可能でなくてはならない．
dest_mapの(dest_x,dest_y)に移動する．

### AUTO

自動移動イベント．指定された動きを行う．(強制的に進む方向が変わる床みたいなの)
```
{
  "type": "AUTO",
  "x": 4,
  "y": 14,
  "mapchip": 6,
  "sequence": "d"
}
```
(x,y)にmapchipで描画．mapchipは進入可能でなくてはならない．
踏むと，sequenceに指定された動き('u','d','l','r','x')をする．複数の場合は文字列で記述．
```
"sequence": "uxllll"
```
上(u)に移動，しばらく立ち止まって(x), 左に4歩移動(llll)


## Acknowledgment

マップチップ素材はぴぽ屋さん(pipoya.net)のものを利用しています．

