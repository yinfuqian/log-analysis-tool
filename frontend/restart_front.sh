#!/bin/bash


docker ps |grep "front" | awk '{print $1}' | xargs -I {} docker restart {}

docker ps -a |grep "front" | awk '{print $1}' | xargs -I {} docker logs {} -f  --tail 100
