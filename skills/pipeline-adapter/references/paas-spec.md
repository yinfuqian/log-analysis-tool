# PAAS（docker-compose）规范速查

## 核心文件
- `docker-compose.yml`

## docker-compose.yml 规范
- `version` 建议 `"3.4"`。
- 镜像名强制格式：
  ```yaml
  image: "$REGISTRY_ADDR{group}/{repo}:${REPO_NAME_UPPER_HYPHEN}_IMAGE_TAG"
  ```
  其中 `REPO_NAME_UPPER_HYPHEN` 为模块名大写、保留中划线。
- **字符串值使用双引号**。
- **环境变量必须使用带默认值的形式 `${VAR:-default}`**，以下情况**严禁**加默认值：
  - `$REGISTRY_ADDR`（流水线注入）
  - `$XXX_WORKING_DIR`（运行时工作目录占位符）
  - `$XXX_IMAGE_TAG`（运行时镜像标签占位符）——**禁止写成 `${XXX_IMAGE_TAG:-latest}`，必须保持纯 `$XXX_IMAGE_TAG`**
- `networks` 统一使用 `default_bridge`（external: true）。

## resource 目录（可选）
- 与 `docker-compose.yml` 同级，用于存放初始化 SQL、静态数据等需要导入的文件。
- 若存在，流水线创建时会自动将该目录打包上传到 Nexus。
- 常见用途：应用启动依赖数据库时，存放建表/初始数据 SQL。

## hook.sh（可选）
提供安装及卸载前后的自定义操作入口，支持以下四个子命令：
- `pre_install`
- `post_install`
- `pre_uninstall`
- `post_uninstall`

### 参数引用规范
主控调用方式示例：
```bash
bash hook.sh pre_install --mysql-master-host=127.0.0.1 --mysql-master-port=3306
```

脚本内部通过 `${ARGS_MAP["key"]}` 获取参数值（参数 key 中的中划线会自动转为下划线）：
```bash
${ARGS_MAP["mysql_master_host"]}
```

### 注意事项
1. SQL 脚本必须保证**可重复执行不报错**，最好不要有清数据的 SQL，否则会导致数据丢失。
2. 引用其他模块 host 时，参数名为 `模块名_host`（全部小写，中划线转下划线），例如 `${ARGS_MAP["demo_host"]}`。
3. `hook.sh` 默认读取同级的 `resource/` 目录，若调整目录结构需同步修改脚本中的路径引用。

## 与 K8S 的兼容
在 CI v3 且 `orchestration.type: docker-compose-and-kubernetes` 时：
- `docker-compose.yml` 仍然需要保留（一键部署 3.0 未完全上线）。
- `docker-compose.yml` 中挂载卷的目标路径若不确定运行时工作目录，可使用占位符 `$MODULE_WORKING_DIR`。
