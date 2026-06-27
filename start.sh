#!/bin/bash
# 构建镜像
# docker compose --env-file .env build
# 初始化数据库
# docker compose --env-file .env --profile tools run --rm migrate
docker compose --env-file .env up -d api worker



# 第二版本启动

#source .env
#docker-compose up -d