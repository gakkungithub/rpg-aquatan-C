#!/bin/sh
cd /home/pi/rpg-aquatan/
/usr/local/bin/python3 monitor.py -b /dev/fb0 -i room1280.ini -l -j
