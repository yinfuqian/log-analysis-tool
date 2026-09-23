# ci.yaml v3 规范速查

## 核心原则
- `version` 必须为 `v3`，否则不属于"编译与部署分离"模式。
- `orchestration.type` 可选值：`none`、`docker-compose`、`kubernetes`、`docker-compose-and-kubernetes`。
- **默认推荐使用 `docker-compose-and-kubernetes`**（同时支持 docker-compose 和 K8S），除非用户明确说明只需要其中一种，或仅出镜像不需要编排。

## 必填字段

| 字段 | 说明 | 示例 |
|------|------|------|
| `version` | 流水线版本 | `v3` |
| `framework` | 技术栈 | `go` / `java` / `cpp` / `web` / `python` |
| `orchestration.type` | 编排类型 | 见下表说明 |
| `buildParameters.buildFrom` | 构建类型 | `dockerfile` / `jib` / `none` |
| `buildParameters.packageType` | 制品类型 | `service` / `tar` / `image` |
| `buildParameters.modules` | 单仓库多模块时填写子模块名；**单仓库单服务时必须为空字符串**。多模块时，根目录 Dockerfile 需命名为 `Dockerfile.{模块名}` | `""` 或 `"moduleA,moduleB"` |

### `orchestration.type` 取值与生成文件对照

| 取值 | 说明 | 生成的编排文件 |
|------|------|----------------|
| `none` | 仅出镜像/制品，不需要编排部署 | 不生成 docker-compose / K8S YAML（通常配合 `packageType: image`） |
| `docker-compose` | 仅使用 docker-compose 部署 | `docker-compose.yml`、`hook.sh`（按需） |
| `kubernetes` | 仅使用 K8S 部署 | `*_deployment.yaml`、`*_service.yaml`、`*_ingress.yaml`（按需）、`*_job.yaml`（按需） |
| `docker-compose-and-kubernetes` | 同时支持 docker-compose 和 K8S | 上述两类文件全部生成 |

## 多架构编译
```yaml
buildParameters:
  platform:
    - "linux/amd64"
    - "linux/arm64"
  # builderPlatform: "linux/amd64"
```
- `platform`：最终**产出物**支持的平台架构列表。
  - 可选值：`"linux/amd64"`、`"linux/arm64"`、`"arch-independent"`
  - 默认：`["linux/amd64", "linux/arm64"]`
  - 示例：Go 项目交叉编译时可在 `linux/amd64` 节点上同时产出 `linux/amd64` 和 `linux/arm64` 两种包；与架构无关的技术栈（如 Java）可直接填 `"arch-independent"`，表示只产出一份通用包。
- `builderPlatform`：执行 `docker build` 命令的**构建节点平台架构**。适用于以下场景：
  1. **项目支持交叉编译**（如 Go）：可指定仅在 `linux/amd64` 节点上运行构建，通过 `TARGETARCH` 在 Dockerfile 中完成多架构产出，减少构建节点资源消耗。
  2. **产出物与架构无关**（如 Java、`arch-independent`）：可直接指定 `builderPlatform`，避免在 arm64 节点上重复构建。
- `arch-independent` 说明：与架构无关的技术栈（如 Java）在 `platform` 中声明此项时，无论目标平台如何，流水线只产出一份通用包。

## 常用可选字段
- `compileOption`: `"--build-arg COMMIT=${IMAGE_TAG}"` — 透传 commit id 给 Dockerfile。
- `registryGroup`: 对应 GitLab 仓库所在组名。
- `skip_build_default_image: true` — 大模型仓库等可跳过默认 alpine v2 镜像构建。

## 单元测试（unitTest）
- **Java 模块**：无需指定 `image`。
- **非 Java 模块**：若需要指定 `image`（构建/单测镜像），**必须使用** `registry01.wezhuiyi.com/standard/centos-builder:v1.8.0`。
- 必须指定 `cmd`。

### Go 示例
```yaml
unitTest:
  cmd: "sh -c 'go mod tidy && go test ./... -coverprofile=./cov.out service-sonar'"
  image: "registry01.wezhuiyi.com/standard/centos-builder:v1.8.0"
  workdir: "/src"
  envs:
    - GOPROXY: http://pkg.in.wezhuiyi.com/repository/golang/,direct
    - GOPRIVATE: code.in.wezhuiyi.com
    - GOSUMDB: 'off'
    - GO111MODULE: 'on'
    - GOPATH: "/tmp/go"
    - XDG_CACHE_HOME: "/tmp/.cache"
  volumes:
    - $PWD: /src
```

### Web 前端示例
```yaml
unitTest:
  cmd: "sh -c 'npm install && npm run test:ci'"
  image: "registry01.wezhuiyi.com/library/alpine-chrome:86-with-node-12"
  workdir: "/usr/src/app"
  envs:
    - SASS_BINARY_PATH: /usr/src/app/vendor/node-sass/v4.14.1/linux_musl-x64-72_binding.node
  volumes:
    - $PWD: /usr/src/app
```

## `packageType` 与 `orchestration.type` 的约束关系
- 当 `orchestration.type` 为 `docker-compose`、`kubernetes` 或 `docker-compose-and-kubernetes` 时，`packageType` **必须为 `service`**。
- 仅当 `orchestration.type: none`（不需要编排部署）时，`packageType` 才可填 `tar` 或 `image`。

## 常见错误
- `orchestration.type` 与实际需求不匹配：
  - 若需要 K8S 部署，不能写 `docker-compose` 或 `none`；
  - 若仅出镜像不需要编排，应写 `none` 并配合 `packageType: image`；
  - 若需要同时支持 docker-compose 和 K8S，必须写 `docker-compose-and-kubernetes`。
- `version` 留空或写 `v1`，导致不走 v3 编译与部署分离逻辑。
