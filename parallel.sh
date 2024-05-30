#!/bin/bash

o=0


python testclient.py --id 0 --stream 0 --output $o
for i in $(seq 0 20);
do
    e=$(($i%2))
    n=$(($i%10))
    if [ $n -eq 0 ]; then
        sleep 5
    fi
    echo $i
    python testclient.py --id $i --stream $e --output $o & \
done
