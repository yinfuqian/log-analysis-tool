#/bin/bash
# TODO: gosu
demo
APP_DIR=${APP_DIR:-"/opt"}
ENTRYPOINT_DIR=${ENTRYPOINT_DIR:-"/entrypoint.d"}
# gosu/usr/local/bin/
cp -f /${APP_DIR}/deployments/dependences/gosu-amd64 /usr/local/bin/gosu || exit 1 && echo "install gosu success"
chmod +x /usr/local/bin/gosu
# entrypoint.sh
mkdir -p /${ENTRYPOINT_DIR}/ && cp -f /${APP_DIR}/deployments/entrypoint.d/entrypoint.sh /${ENTRYPOINT_DIR}/ && chmod +x /${ENTRYPOINT_DIR}/entrypoint.sh
