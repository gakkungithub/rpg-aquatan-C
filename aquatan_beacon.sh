sudo hciconfig hci0 up
sudo hcitool -i hci0 cmd 0x08 0x0008 1E 02 01 1A 1A FF 4C 00 02 15 B7 65 40 E0 EF 3C 11 E4 95 C9 00 02 A5 D5 C5 1B 05 DC 3A 99 C8 00
sleep 5
sudo hciconfig hci0 leadv