#!/bin/sh


count=0
row=0
for i in 15070 15096 15097 15098 15099 15103 15104 15106 15113 15114 15115 15116 15117 15118 15119 15070; do
    ./conv2.sh $i;
    if [ $count -ne 0 ]; then
	convert +append row_${row}.png final_${i}.png row_${row}.png
    else
	cp final_${i}.png row_${row}.png
    fi
    count=$((++count))
    if [ $count -ge 4 ]; then
	count=0
	row=$((++row))
    fi
done
for ((i=0; i < $row; i++)); do
    if [ $i -eq 0 ]; then
	cp row_${i}.png final.png
    else
	convert -append final.png row_${i}.png final.png
    fi
done
rm -f row_*.png final_*.png
