<<<<<<< HEAD
C言語プログラム探索RPG_あくあたん
=========================

* 水槽モニターRPG
* 行き先表示RPG

Original program is taken from http://aidiary.hatenablog.com/entry/20080507/1269694935

Scripts
----------

* monitor.py: メインプログラム
* omznmon.sh: pi95用omzn在室表示
* aquamon.sh: pi96用学生在室表示

年次更新手順
-----------

1. charchip に対応するNPCのID名(例:15160.png)でPNGを置く．
2. data/charachip.datに新しいpng(15160.png)を登録する
3. mapeditor.pyでroomを読み込み，NPCを新規登録する．("4"コマンド)
4. 新規NPC一人につき，かならず各部屋の居場所を"p"で登録する．PLACE?と訊かれたところでは，{away, 8-302, 8-302, 8-303, 8-321, 8-322, 8-417} を登録．足りないと実行時にエラーとなる．

GUIここまで

4. IDのビーコンを作成する
5. aqualog:ble_tagにIDを登録する
6. aqualog:logにtarget_id_status=Lostを覚えさせる

7. 部屋を増やす場合は ibeacon_scannerで対応するconfigを増やすして，detectorを設置すれば勝手に増える．
8. 増えた部屋に対する定義をroom.evtに書かないと，keyerrorになる．

部屋のロック状態の反映
-------
/api/lock/status から，各部屋のロック状態を取得できる．
RPG側では，DOORオブジェクトに部屋の名前を与え，-l オプションを付けて起動することでロック状態の反映がなされる．

なお，DOORオブジェクトには開閉に関わらず当たり判定は無い．これはNPCが経路判定するときにドアが閉まっていると解が得られなくなり，謎の挙動を起こすためである．

## バグ

linuxで実行する時，monitor.pyのload_charachipsにて
load_imageの引数にTRANS_COLORを入れるとキャラクタの透過処理が為されない．
たぶん，convertを2回やってるからだと思われるが…

## Acknowledgment

マップチップ素材はぴぽ屋さん(pipoya.net)のものを利用しています．

=========================

rpg-aquqtan for OJT
=========================
## commands
キーボードでcを入力するとコマンドラインが表示されて入力できます.

undo        : 関数からの出入りと井戸ワープの巻き戻し機能　最大５回まで巻き戻せます
break       : 関数から出ます　returnキャラに話すのと同じ意味です
restart     : ゲームの初期状態に戻ります
itemget [x] : アイテム[x : アイテム名]を取得
itemset [x] [y] : アイテム[x : アイテム名]に値（今の所integerのみ）をセット
goto x,y    : 任意の座標x,yにワープ（壁の中にも行けてしまう）
jumo [x]    : 関数[x : 関数名]の入り口にワープ　必要アイテムが不足しているとワープできない(その関数がない時エラーになってしまうので要修正)
up, down, right, left   : 指定の方向へ動けるならば１マス動く

## TCP connection to the debug system by socket module
senderクラスでソケットによるTCP通信を管理しています.
=========================

tips for developing this system
=========================
インストールが必要なライブラリは、clang, python-astar, graphviz, ephemです (後々、インストールされていない場合は自動インストールできるようにする)
"region 〇〇" のコメントアウトは折り畳めます. 
コードが見やすくなるのでなるべく使いたいです.

コード内の巨大アスキーアートは「VScode Banner Comment Generator」拡張機能で生成できます.
拡張機能を追加した後、figletを忘れずにインストールしてください.

効果音:
otosozai.com　https://otosozai.com/ (商用でのご利用の際は、メールフォームより連絡すること。)
OtoLogic
=========================

>>>>>>> 4a58b39d7f3c703ddffc2ef1a0809085e7d3db6c
