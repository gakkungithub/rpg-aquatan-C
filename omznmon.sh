#!/bin/bash
cd /home/pi/rpg-aquatan/
python3 monitor.py -b /dev/fb1 -i room.ini -s
