# ============================================================
# Test Center Guide —— 静态站点镜像
#
# 基础镜像：Docker Hub 官方 nginx（alpine 变体，体积小、漏洞面最小），
#           锁定到具体 minor 版本 tag，不使用浮动 latest。
#
# 非 root 运行（TOS 规范硬性要求，root 运行一票否决）：
#   - 进程 uid/gid = 1000，与 docker-compose.yml 的 user: "1000:1000" 对齐
#   - 容器内监听 8080：非 root 无法绑定 1024 以下特权端口
#   - pid / 临时目录 / 日志目录全部落到可写位置（详见 nginx.conf）
#
# 构建（CI 或本地，构建上下文 = 本仓库根目录）：
#   docker build -t <dockerhub_user>/test-center-guide:<version> .
# ============================================================
FROM nginx:1.27-alpine

LABEL org.opencontainers.image.title="Test Center Guide" \
      org.opencontainers.image.description="Offline onboarding guide and deployment helper for Test Center" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/RyanYang163/test-center-guide-docker"

# 用我们自己的 nginx.conf 整体替换官方配置（不 include conf.d，默认站点不生效）
COPY nginx.conf /etc/nginx/nginx.conf

# 站点内容
COPY web/ /usr/share/nginx/html/

# 非 root 适配：
#   - 删掉官方镜像自带的默认站点（本镜像不 include conf.d，留着只会误导）
#   - 预建日志目录并归属 1000：这样即使宿主机挂载进来的是空目录，
#     或本地 docker run 不带挂载，nginx 都能直接起，不会因写不了日志而退出
#   - 静态文件统一可读，避免非 root 用户读不到
RUN rm -f /etc/nginx/conf.d/default.conf \
 && mkdir -p /var/log/nginx \
 && rm -f /var/log/nginx/access.log /var/log/nginx/error.log \
 && touch /var/log/nginx/access.log \
 && chown -R 1000:1000 /var/log/nginx /usr/share/nginx/html \
 && chmod -R a+rX /usr/share/nginx/html

# 不继承官方镜像的 docker-entrypoint.sh：它按 root 前提做 envsubst 与权限调整，
# 非 root 下会告警甚至中断。直接起 nginx 更干净、行为可预期。
ENTRYPOINT ["nginx", "-g", "daemon off;"]

USER 1000:1000

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q --spider http://127.0.0.1:8080/healthz || exit 1
