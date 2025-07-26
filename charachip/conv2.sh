#!/bin/sh
convert $1.png \
  -alpha set \
  -background none \
  -channel RGBA \
  -fill '#00000000' \
  -fuzz 5% \
  -draw 'matte 1,1 floodfill' \
  $1_trans.png
convert -crop 32x32+0+0 $1_trans.png $1_cropped_0.png
convert -crop 32x32+64+32 $1_trans.png $1_cropped_1.png
convert -crop 32x32+32+64 $1_trans.png $1_cropped_2.png
convert -crop 32x32+0+96 $1_trans.png $1_cropped_3.png
convert +append $1_cropped_0.png $1_cropped_3.png $1_cropped_03.png
convert +append $1_cropped_1.png $1_cropped_2.png $1_cropped_12.png
convert -append $1_cropped_03.png $1_cropped_12.png $1_cropped.png
convert $1_cropped.png -sample 200% final_$1.png
rm -f $1_*.png
