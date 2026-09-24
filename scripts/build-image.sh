#!/bin/bash
# ============================================================
# 构建镜像 → 本地自测 → 推送到 Docker Hub
#
# 在哪跑：有 Docker 且能访问 hub.docker.com 的机器。
# 你的 Windows 开发机两样都没有 —— 最顺手的是 NAS 的终端
# （TOS 装好 Docker Engine 后，Terminal 里直接跑本脚本）。
#
# 用法：
#   bash scripts/build-image.sh              # 构建 + 自测 + 推送
#   bash scripts/build-image.sh --no-push    # 只构建 + 自测，不推送
#   bash scripts/build-image.sh --no-test    # 跳过本地自测
#
# 首次推送前需要 Docker Hub 账号的 Access Token（不是登录密码）：
#   hub.docker.com → Account settings → Personal access tokens → 新建（Read & Write）
#   然后 docker login -u <用户名>  密码处粘 token
# ============================================================
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
cd "$ROOT"

DO_PUSH=1
DO_TEST=1
for arg in "$@"; do
  case "$arg" in
    --no-push) DO_PUSH=0 ;;
    --no-test) DO_TEST=0 ;;
    *) echo "未知参数：$arg"; exit 2 ;;
  esac
done

# ---- 读 versions.env（含 ${VAR} 引用，按文件顺序展开） ----
set -a
# shellcheck disable=SC1091
. ./versions.env
set +a

: "${DOCKERHUB_USER:?versions.env 里的 DOCKERHUB_USER 未设置}"
: "${TOS_VERSION:?versions.env 里的 TOS_VERSION 未设置}"
IMAGE="${DOCKERHUB_USER}/test-center-guide:${TOS_VERSION}"
PLATFORM_FLAG=""
case "${TOS_PLATFORM:-x86_64}" in
  x86_64)  PLATFORM_FLAG="linux/amd64" ;;
  aarch64) PLATFORM_FLAG="linux/arm64" ;;
  *) echo "ERROR: TOS_PLATFORM 只能是 x86_64 或 aarch64，当前 ${TOS_PLATFORM}"; exit 1 ;;
esac

command -v docker >/dev/null 2>&1 || {
  echo "ERROR: 找不到 docker —— 本脚本必须在装有 Docker 的机器上跑（例如 NAS 的终端）。"
  exit 1
}

echo "============================================================"
echo "目标镜像：${IMAGE}"
echo "目标架构：${PLATFORM_FLAG}"
echo "============================================================"

# ---- 1. 构建 ----
echo ""
echo "--- 1/4 构建镜像 ---"
docker build --pull --platform "${PLATFORM_FLAG}" -t "${IMAGE}" -f Dockerfile .

# ---- 2. 本地自测：非 root 能否起来、健康检查是否通过 ----
if [ "$DO_TEST" = "1" ]; then
  echo ""
  echo "--- 2/4 本地自测（非 root + 健康检查） ---"
  docker rm -f tcg-selftest >/dev/null 2>&1 || true
  # 刻意用 --user 1000:1000，与 compose 里的 user 字段一致；
  # 不挂载日志目录，模拟最差情况（宿主机目录不存在）
  docker run -d --name tcg-selftest --user "1000:1000" -p 127.0.0.1:18013:8080 "${IMAGE}" >/dev/null

  ok=0
  for _ in $(seq 1 15); do
    if curl -fsS --max-time 3 http://127.0.0.1:18013/healthz >/dev/null 2>&1; then
      ok=1
      break
    fi
    sleep 1
  done

  if [ "$ok" = "1" ]; then
    echo "健康检查通过：/healthz 返回 200"
    for p in / /features.html /deploy.html /generator.html /faq.html /assets/style.css /assets/app.js; do
      code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:18013${p}")
      printf '  %-22s HTTP %s\n' "$p" "$code"
    done
  else
    echo "自测失败 —— 容器起不来，日志如下："
    docker logs tcg-selftest || true
    docker rm -f tcg-selftest >/dev/null 2>&1 || true
    exit 1
  fi

  echo "容器内进程用户（应为 uid=1000）："
  docker exec tcg-selftest id || true
  docker rm -f tcg-selftest >/dev/null 2>&1 || true
fi

# ---- 3. 推送 ----
if [ "$DO_PUSH" = "1" ]; then
  echo ""
  echo "--- 3/4 推送到 Docker Hub ---"
  echo "提示：密码处粘 Docker Hub 的 Access Token，不是账号登录密码。"
  docker login -u "${DOCKERHUB_USER}"
  docker push "${IMAGE}"
  echo "已推送：${IMAGE}"
else
  echo ""
  echo "--- 3/4 跳过推送（--no-push） ---"
fi

# ---- 4. 出包 ----
echo ""
echo "--- 4/4 生成 TOS 应用包 ---"
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "WARN: 没找到 python3/python，跳过出包。可稍后手动跑："
  echo "      python scripts/build-package.py --skip-verify"
  exit 0
fi
"$PY" scripts/build-package.py --skip-verify

echo ""
echo "============================================================"
echo "完成。产物："
ls -lh dist/ 2>/dev/null || true
echo ""
echo "下一步：确认镜像已推成功（${IMAGE}），"
echo "        再把 dist/test-center-guide-docker.tar.gz 与 .sha256 传到仓库 Release。"
echo "============================================================"
