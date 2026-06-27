#!/bin/bash

# 如果 /app/log-analyze 目录不存在，则创建 Vue 项目
if [ ! -d "/app/log-analyze" ]; then
  echo "Vue 项目不存在，正在创建项目..."
  echo "y" | vue create log-analyze --default --packageManager=npm --no-git
else
  echo "项目已存在"
fi

# 切换到项目目录并启动 Vue 服务
cd /app/log-analyze
npm cache clean --force
npm install
npm run serve

