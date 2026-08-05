#!/bin/bash
find /home/solinfnet/TempDB/ -type f -name '*.ptemp' -print0 | xargs -0 rename 's/.ptemp$/.Packet/'
find /home/solinfnet/TempDB/A -type f -name '*.ptemp' -print0 | xargs -0 rename 's/.ptemp$/.Packet/'
find /home/solinfnet/TempDB/B -type f -name '*.ptemp' -print0 | xargs -0 rename 's/.ptemp$/.Packet/'
find /home/solinfnet/TempDB/C -type f -name '*.ptemp' -print0 | xargs -0 rename 's/.ptemp$/.Packet/'
