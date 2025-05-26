#!/bin/sh
cd /home/pi/rpg-aquatan/
sudo /usr/local/bin/python3 monitor.py -a -b /dev/fb1 -i rpg.ini
