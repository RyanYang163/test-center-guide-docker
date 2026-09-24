#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提交前核对：docker-compose.yml 里引用的镜像 tag 是否真实存在于 Docker Hub。

为什么必须做这一步：tag 写错不会在本地报错，但平台安装时 compose pull 阶段会直接
失败、安装卡死（历史踩坑）。所以提交前查一次线上。

查的是 Docker Hub 官方 API，无需登录、无需第三方库：
    https://hub.docker.com/v2/repositories/<namespace>/<repo>/tags/<tag>

退出码：
    0 = 全部 tag 都在线上确认存在
    1 = 有 tag 不存在（必须修正）
    2 = 网络不可达/被拦，无法确认（不视为失败，但要人工确认）

用法：
    python scripts/verify-images.py
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(HERE)
API = "https://hub.docker.com/v2/repositories/%s/tags/%s"
TIMEOUT = 8


def read_text(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return f.read().replace("\r\n", "\n")


def load_versions(path):
    raw = {}
    for line in read_text(path).split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        raw[k.strip()] = v.strip()

    def expand(value):
        if "${" not in value:
            return value
        out = value
        for k, v in raw.items():
            out = out.replace("${%s}" % k, v)
        return out

    return {k: expand(v) for k, v in raw.items()}


def compose_images():
    """从 compose 模板里取出所有 image: 行（含未替换的占位符，替换后即为真实值）。"""
    text = read_text(os.path.join(APP_ROOT, "docker-compose.yml"))
    versions = load_versions(os.path.join(APP_ROOT, "versions.env"))
    for k, v in versions.items():
        text = text.replace("@@%s@@" % k, v)
    imgs = []
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("#"):
            continue
        m = re.match(r"^image:\s*(\S+)", s)
        if m:
            imgs.append(m.group(1).strip('"\''))
    return imgs, versions


def split_ref(ref):
    """nginx:1.27-alpine -> ('library', 'nginx', '1.27-alpine')"""
    name, _, tag = ref.rpartition(":")
    if "/" in name:
        namespace, repo = name.split("/", 1)
    else:
        namespace, repo = "library", name
    return namespace, repo, tag


def tag_exists(namespace, repo, tag):
    """返回 True/False；无法确认时抛 URLError。"""
    url = API % (namespace + "/" + repo, tag)
    req = urllib.request.Request(url, headers={"User-Agent": "tos-app-verify/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return bool(data.get("name"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise


def main():
    imgs, versions = compose_images()
    if not imgs:
        print("[ERROR] compose 里没有找到任何 image:")
        return 1

    print("=" * 66)
    print("镜像 tag 在线核对（Docker Hub）")
    print("=" * 66)

    missing, unreachable = [], []

    for ref in imgs:
        if "@@" in ref:
            print("  [ERROR] 占位符未替换：%s" % ref)
            missing.append(ref)
            continue
        namespace, repo, tag = split_ref(ref)
        if not tag:
            print("  [ERROR] %s 没有指定 tag（禁 :latest）" % ref)
            missing.append(ref)
            continue
        if tag == "latest":
            print("  [ERROR] %s 用了 :latest —— 必须锁定具体版本" % ref)
            missing.append(ref)
            continue
        try:
            ok = tag_exists(namespace, repo, tag)
        except Exception as e:                                    # noqa: BLE001
            print("  [ ?? ] %-46s 无法确认（%s）" % (ref, type(e).__name__))
            unreachable.append(ref)
            continue
        if ok:
            print("  [ OK ] %-46s 存在" % ref)
        else:
            print("  [FAIL] %-46s 线上不存在这个 tag" % ref)
            missing.append(ref)

    print("-" * 66)
    print("compose 引用的镜像：%d 个" % len(imgs))
    print("当前版本：%s   目标架构：%s   镜像：%s"
          % (versions.get("TOS_VERSION"), versions.get("TOS_PLATFORM"),
             versions.get("APP_IMAGE")))

    if missing:
        print("结论：有 %d 个 tag 必须修正 —— %s" % (len(missing), ", ".join(missing)))
        return 1
    if unreachable:
        print("结论：%d 个 tag 因网络不可达未能确认（%s）。"
              % (len(unreachable), ", ".join(unreachable)))
        print("      本机无法访问 hub.docker.com 时属正常；请在能联网的机器上重跑，")
        print("      或至少确认该 tag 是刚推送成功的版本（自建镜像以 CI 推送结果为准）。")
        return 2
    print("结论：全部 tag 已在 Docker Hub 确认存在。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
