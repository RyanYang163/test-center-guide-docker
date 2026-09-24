#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 TOS 7 Docker 应用提交包。

做四件事：
  1. 替换 docker-compose.yml 里的 @@VAR@@ 占位符（取自 versions.env）
  2. 按《TOS 7 Application Development Guide》第 9 章做合规自检
  3. 用 LF 行尾写出 dist/ 下的 4 个文件
  4. 打成 <appid>.tar.gz 并生成 <appid>.tar.gz.sha256

零第三方依赖，只用标准库 —— 任何带 Python 3.8+ 的机器直接可跑。

用法：
    python scripts/build-package.py
    python scripts/build-package.py --skip-verify     # 跳过镜像在线校验（离线环境）
    python scripts/build-package.py --keep-dist       # 保留上一次 dist/
"""
import argparse
import hashlib
import json
import os
import re
import sys
import tarfile
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(HERE)

REQUIRED_LANGS = ["zh-cn", "zh-hk", "en-us", "fr-fr", "de-de", "it-it",
                  "es-es", "hu-hu", "ja-jp", "ko-kr", "pl-pl", "ru-ru",
                  "tr-tr", "pt-pt"]

# TOS 系统保留端口（应用不得占用）
RESERVED_PORTS = {22, 80, 443, 445, 3306, 5050, 5432, 6379, 8181, 8443}

# config.ini 必需字段（第 9 章 §9.5 + 第 4 章字段表）
REQUIRED_CONFIG_FIELDS = ["id", "icon", "publisher", "exec", "version", "low_version",
                          "category", "depend", "platform", "application_type",
                          "user", "all_user_display", "allow_open_in_mobile"]

HTML_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
             "link", "meta", "param", "source", "track", "wbr"}

ERRORS, WARNS = [], []


def err(msg):
    ERRORS.append(msg)


def warn(msg):
    WARNS.append(msg)


# ----------------------------------------------------------------------
def load_versions(path):
    raw = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            raw[k.strip()] = v.strip()

    def expand(value, depth=0):
        if depth > 5 or "${" not in value:
            return value
        out = value
        for k, v in raw.items():
            out = out.replace("${%s}" % k, v)
        return out

    return {k: expand(v) for k, v in raw.items()}


def read_text(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return f.read().replace("\r\n", "\n").replace("\r", "\n")


def write_lf(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def strip_yaml_comments(text):
    """去掉整行注释与行内注释。

    必须去掉：编排文件的注释头里写着「禁止 privileged / network_mode / :latest」
    这类规则说明，若把注释一起扫，会把这些字面量当成真实配置误报。
    """
    out = []
    for line in text.split("\n"):
        if line.lstrip().startswith("#"):
            continue
        if " #" in line:
            line = line.split(" #", 1)[0].rstrip()
        out.append(line)
    return "\n".join(out)


def strip_ini_comments(text):
    """去掉 .lang / .ini 里的 # 注释行（注释里会写 <appid> 这类示例文本）。"""
    return "\n".join(l for l in text.split("\n") if not l.lstrip().startswith("#"))


# ----------------------------------------------------------------------
def check_config_ini(cfg, versions):
    for field in REQUIRED_CONFIG_FIELDS:
        if field not in cfg:
            err("config.ini 缺字段：%s" % field)

    appid = cfg.get("id", "")
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,49}", appid):
        err("config.ini id 非法：%r（须以小写字母开头，仅含小写字母/数字/连字符，≤50 字符）" % appid)

    if cfg.get("icon") != "/images/icons/%s.svg" % appid:
        err("config.ini icon 必须是 /images/icons/%s.svg，实际 %r" % (appid, cfg.get("icon")))

    if cfg.get("application_type") != "docker":
        err("config.ini application_type 必须是 docker")

    if cfg.get("compose_project") != appid:
        err("config.ini compose_project 必须与 id 一致")

    if cfg.get("recommend") is not False:
        err("config.ini recommend 必须为 false（由平台运营设置）")

    if cfg.get("platform") != versions.get("TOS_PLATFORM"):
        err("config.ini platform=%r 与 versions.env 的 TOS_PLATFORM=%r 不一致"
            % (cfg.get("platform"), versions.get("TOS_PLATFORM")))

    if cfg.get("version") != versions.get("TOS_VERSION"):
        err("config.ini version=%r 与 versions.env 的 TOS_VERSION=%r 不一致"
            % (cfg.get("version"), versions.get("TOS_VERSION")))

    ver = str(cfg.get("version", ""))
    if not re.fullmatch(r"\d+(\.\d+){0,2}", ver) or len(ver) > 20:
        err("版本号 %r 不合法（1-3 段数字、总长 ≤20、禁字母/连字符/前导零）" % ver)
    elif any(seg != "0" and seg.startswith("0") for seg in ver.split(".")):
        err("版本号 %r 含前导零 —— 平台按整数逐段比较，1.0.01 会被判成 1.0.1" % ver)

    cats = cfg.get("category", [])
    if not isinstance(cats, list) or not cats:
        err("config.ini category 必须是非空数组")
    elif len(cats) > 3:
        err("config.ini category 最多 3 个，实际 %d 个" % len(cats))
    else:
        allowed = {"Audio_Video_Entertainment", "Photography_Video", "Backup_Sync",
                   "Development_Tools", "Utilities", "Web_Services", "Security",
                   "Download", "Driver", "Artificial_Intelligence"}
        for c in cats:
            if c not in allowed:
                err("config.ini category %r 不在附录 A 的 10 个固定值内" % c)

    if "type" in cfg and "open_path" in cfg:
        err("config.ini 的 type 与 open_path 互斥，不得同时出现")

    if cfg.get("exec") is True and not cfg.get("path"):
        err("config.ini exec=true 时 path 必填")

    path = cfg.get("path", "")
    if path and "${ip}" not in path:
        err("config.ini path 必须用 ${ip} 占位符，禁止硬编码 IP/域名：%r" % path)

    dep = cfg.get("depend", [])
    if "DockerEngine" not in dep:
        warn("config.ini depend 建议包含 DockerEngine（DockerEngine 未预装，需先安装）")

    if cfg.get("user") in ("", "root", None):
        err("config.ini user 不得为空或 root")

    # system_id / package：官方 Docker 示例不写，但已过审的同批 Docker 应用
    # （shh1/3/5）都填成了 appid，平台并未报错。这里只拦「填了别的值」。
    for f in ("system_id", "package"):
        v = cfg.get(f)
        if v not in ("", None, appid):
            warn("config.ini %s=%r 既不是空串也不等于 id（%s），确认平台是否接受" % (f, v, appid))


def check_lang(text, appid):
    for lang in REQUIRED_LANGS:
        if "[%s]" % lang not in text:
            err("语言文件缺语言节点：[%s]" % lang)

    cur, fields = None, {}
    blocks = {}
    for line in text.split("\n"):
        m = re.match(r"^\[([a-z]{2}-[a-z]{2})\]\s*$", line.strip())
        if m:
            if cur:
                blocks[cur] = fields
            cur, fields = m.group(1), {}
            continue
        if cur:
            m2 = re.match(r"^(\w+)\s*=\s*\"(.*)\"\s*$", line.strip())
            if m2:
                fields[m2.group(1)] = m2.group(2)
    if cur:
        blocks[cur] = fields

    for lang in REQUIRED_LANGS:
        f = blocks.get(lang)
        if f is None:
            continue
        for key in ("name", "auth", "descript"):
            if not f.get(key, "").strip():
                err("语言 %s 的 %s 为空" % (lang, key))
        if len(f.get("name", "")) > 64:
            err("语言 %s 的 name 超过 64 字符" % lang)
        if len(f.get("auth", "")) > 64:
            err("语言 %s 的 auth 超过 64 字符" % lang)
        if len(f.get("descript", "")) > 512:
            err("语言 %s 的 descript 超过 512 字符（%d）" % (lang, len(f.get("descript", ""))))
        if len(f.get("important", "")) > 512:
            warn("语言 %s 的 important 超过 512 字符（%d）" % (lang, len(f.get("important", ""))))

    body = strip_ini_comments(text)
    for tag in re.findall(r"<(?!/br>)([a-zA-Z/][^>]*)>", body):
        warn("语言文件出现非 </br> 的 HTML 标签：<%s>" % tag)


def check_svg(text, appid):
    if "viewBox" not in text:
        err("SVG 缺 viewBox 属性")
    if not re.search(r"<svg[\s>]", text, re.I):
        err("SVG 根元素缺失")
    if "<text" in text.lower():
        warn("SVG 含 <text> 元素：平台侧渲染若不加载字体，文字可能不显示（本图标未使用文字）")


def check_compose(raw_text, cfg, versions):
    appid = cfg["id"]
    web_port = int(versions["WEB_PORT"])

    text = strip_yaml_comments(raw_text)

    names = re.findall(r"^\s{4}container_name:\s*(\S+)", text, re.M)
    svc_count = len(names)
    if svc_count == 0:
        err("compose 未解析到任何服务（没找到 container_name）")
        return

    if re.search(r"^\s*privileged:", text, re.M) or "privileged: true" in text:
        err("compose 出现 privileged —— 一票否决项")
    if re.search(r"^\s*network_mode:", text, re.M):
        err("compose 出现 network_mode —— host 网络一票否决，且本编排不应使用该字段")
    if re.search(r":latest\b", text):
        err("compose 出现 :latest tag —— 必须锁定具体版本")

    n_health = len(re.findall(r"^\s{4}healthcheck:", text, re.M))
    n_user = len(re.findall(r'^\s{4}user:\s*"1000:1000"', text, re.M))
    n_restart = len(re.findall(r"^\s{4}restart:\s*unless-stopped", text, re.M))
    n_image = len(re.findall(r"^\s{4}image:", text, re.M))

    for label, n in (("healthcheck", n_health), ("user", n_user),
                     ("restart: unless-stopped", n_restart), ("image", n_image)):
        if n != svc_count:
            err("compose 有 %d 个服务，但只有 %d 处 %s —— 规范要求每个服务都有"
                % (svc_count, n, label))

    if len(names) != len(set(names)):
        err("compose 存在重复的 container_name：%s" % names)
    if appid not in names:
        err("compose 中没有任何 container_name 等于应用 id（%s）——主容器应命名为 id" % appid)

    for host, _cont in re.findall(r'^\s{6}-\s*"(\d+):(\d+)"', text, re.M):
        hp = int(host)
        if hp in RESERVED_PORTS:
            err("compose 发布了系统保留端口 %d —— 不得占用" % hp)
        elif not (8000 <= hp <= 19999):
            warn("宿主机端口 %d 不在推荐区间 8000-19999" % hp)

    idx_meta = text.find("\nx-app-meta:")
    if idx_meta < 0 and not text.startswith("x-app-meta:"):
        err("compose 缺 x-app-meta（带 Web UI 的 Docker 应用必需）")
    else:
        idx_services = text.find("\nservices:")
        if 0 <= idx_meta < idx_services:
            err("x-app-meta 出现在 services 之前 —— 应作为顶层键放在 services 之后")
        body = text[idx_meta:]
        pm = re.search(r"^\s{4}port:\s*(\d+)", body, re.M) or re.search(r"port:\s*(\d+)", body)
        if not pm:
            err("x-app-meta 缺 web.port")
        elif int(pm.group(1)) != web_port:
            err("x-app-meta 的 web.port=%s 与 versions.env 的 WEB_PORT=%d 不一致"
                % (pm.group(1), web_port))
        if "protocol:" not in body:
            err("x-app-meta 缺 web.protocol")

    vols = re.findall(r"^\s{6}-\s*(/\S+?):(?!//)", text, re.M)
    bad = [v for v in vols if not v.startswith("/Volume*/DockerAppData/%s/" % appid)]
    if bad:
        err("compose 存在未挂到 /Volume*/DockerAppData/%s/ 的挂载：%s" % (appid, bad))
    if not vols:
        warn("compose 未见任何绑定挂载 —— 确认该应用确实无持久化数据")

    for img in re.findall(r"^\s{4}image:\s*(\S+)", text, re.M):
        if "@@" in img:
            err("镜像 %r 的占位符未替换（versions.env 里 DOCKERHUB_USER 还是占位符？）" % img)
            continue
        parts = img.split("/")
        if len(parts) > 1:
            first = parts[0]
            if "." in first or ":" in first or first == "localhost":
                err("镜像 %s 来自非 Docker Hub 仓库 —— 平台只接受 Docker Hub 镜像" % img)
        else:
            err("镜像 %s 没有命名空间 —— 自建镜像必须推到你自己的 Docker Hub 账号下" % img)

    if "@@" in text:
        left = sorted(set(re.findall(r"@@(\w+)@@", text)))
        err("compose 仍有未替换的占位符：%s" % left)

    if "\r" in raw_text:
        err("compose 含 CRLF 行尾 —— 必须是 LF")


def check_i18n_coverage():
    """英文模式会不会漏出中文。

    页面里任何中文文本节点，都必须落在带 data-i18n / -html / -code / -ph 的元素内
    （或其祖先元素上）。漏一个，切到英文就会在英文页面里冒出一行中文。
    """
    pages = ["index.html", "features.html", "deploy.html", "generator.html", "faq.html"]
    web = os.path.join(APP_ROOT, "web")
    attrs = ("data-i18n", "data-i18n-html", "data-i18n-code", "data-i18n-ph")

    class Scan(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.stack = []
            self.covered = 0
            self.leftovers = []

        def handle_starttag(self, tag, attrs_):
            if tag in HTML_VOID:
                return
            d = dict(attrs_)
            parent = self.covered > 0
            if any(a in d for a in attrs):
                self.covered += 1
                self.stack.append((tag, True))
            else:
                self.stack.append((tag, parent))

        def handle_endtag(self, tag):
            if tag in HTML_VOID or not self.stack:
                return
            _t, cov = self.stack.pop()
            if cov and not any(c for _, c in self.stack):
                self.covered -= 1

        def handle_data(self, data):
            if self.covered:
                return
            if re.search(r"[一-鿿]", data) and data.strip():
                self.leftovers.append(data.strip()[:60])

    for name in pages:
        p = os.path.join(web, name)
        if not os.path.isfile(p):
            continue
        s = Scan()
        s.feed(read_text(p))
        for frag in s.leftovers:
            err("%s 有中文没接字典：%r —— 切到英文会漏出中文，给所在元素加 data-i18n*" % (name, frag))


def check_web_dir():
    """站点源文件必须存在，否则镜像里会是空的 nginx 默认页。

    顺带把三类「只在浏览器里才暴露」的问题拦在提交前：
      - data-i18n 用了字典里没有的键（切换语言时文字不换）
      - href/src 指向不存在的本地文件（404）
      - 内联 <script> 或 on* 事件属性（被 CSP 拦掉，页面直接没有交互）
    """
    web = os.path.join(APP_ROOT, "web")
    if not os.path.isdir(web):
        err("缺少 web/ 目录（镜像要伺服它）")
        return

    pages = ["index.html", "features.html", "deploy.html", "generator.html", "faq.html"]
    required = pages + [os.path.join("assets", "style.css"),
                        os.path.join("assets", "app.js"),
                        os.path.join("assets", "i18n.js")]
    for name in required:
        if not os.path.isfile(os.path.join(web, name)):
            err("web/ 下缺少 %s" % name)
    if not os.path.isfile(os.path.join(APP_ROOT, "Dockerfile")):
        err("缺少 Dockerfile（镜像构建入口）")
    if not os.path.isfile(os.path.join(web, "assets", "favicon.svg")):
        warn("web/assets/favicon.svg 缺失（页面 <link rel=icon> 会 404）")

    # ---- i18n 键对账 ----
    # 中文是页面 HTML 里的原文（唯一来源），i18n.js 只放英文。
    # 所以这里只核对「页面用到的键在英文词典里都有」，不做中英键对称性检查。
    i18n_path = os.path.join(web, "assets", "i18n.js")
    if os.path.isfile(i18n_path):
        js = read_text(i18n_path)
        try:
            en_block = js.split("window.TC_I18N = {", 1)[1].split("en: {", 1)[1].rsplit("\n  }", 1)[0]
        except IndexError:
            err("i18n.js 结构不符预期（找不到 window.TC_I18N / en: { 块）")
            en_block = ""

        en_keys = set(re.findall(r'"([a-zA-Z0-9._-]+)":', en_block))

        used = set()
        for name in pages:
            p = os.path.join(web, name)
            if os.path.isfile(p):
                used |= set(re.findall(r'data-i18n(?:-html|-code|-ph)?="([^"]+)"', read_text(p)))

        for k in sorted(used - en_keys):
            err("页面用到文案键 %r，但 i18n.js 的英文词典里没有 —— 切到英文会露出中文" % k)

    # ---- 本地资源引用 + CSP 合规 ----
    for name in pages:
        p = os.path.join(web, name)
        if not os.path.isfile(p):
            continue
        text = read_text(p)

        if re.search(r"<script(?![^>]*\bsrc=)", text, re.I):
            err("%s 含内联 <script> —— CSP 的 script-src 'self' 会拦掉它" % name)
        for attr in re.findall(r"<[^>]+\son([a-z]+)\s*=", text, re.I):
            err("%s 使用了内联事件属性 on%s= —— CSP 会拦掉，请改 addEventListener" % (name, attr))

        for ref in re.findall(r'(?:href|src)="([^"]+)"', text):
            if ref.startswith(("http://", "https://", "#", "mailto:", "data:")):
                continue
            target = os.path.join(web, ref.lstrip("/"))
            if ref.endswith("/"):
                target = target.rstrip("/")
            if not os.path.exists(target):
                err("%s 引用了不存在的文件：%s" % (name, ref))


# ----------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--versions", default=os.path.join(APP_ROOT, "versions.env"))
    ap.add_argument("--skip-verify", action="store_true", help="跳过镜像在线校验")
    ap.add_argument("--keep-dist", action="store_true", help="不清理旧的 dist/")
    args = ap.parse_args()

    print("=" * 66)
    print("TOS 7 Docker 应用打包 —— test-center-guide-docker")
    print("=" * 66)

    versions = load_versions(args.versions)
    appid = None
    try:
        cfg = json.loads(read_text(os.path.join(APP_ROOT, "config.ini")))
        appid = cfg.get("id", "")
    except Exception as e:                                   # noqa: BLE001
        err("config.ini 不是合法 JSON：%s" % e)
        cfg = {}

    if cfg:
        check_config_ini(cfg, versions)
    if appid:
        check_lang(read_text(os.path.join(APP_ROOT, "%s.lang" % appid)), appid)
        check_svg(read_text(os.path.join(APP_ROOT, "%s.svg" % appid)), appid)

    compose_raw = read_text(os.path.join(APP_ROOT, "docker-compose.yml"))
    compose = compose_raw
    for k, v in versions.items():
        compose = compose.replace("@@%s@@" % k, v)

    if cfg:
        check_compose(compose, cfg, versions)

    check_web_dir()
    check_i18n_coverage()

    if not args.skip_verify:
        import subprocess
        r = subprocess.run([sys.executable, os.path.join(HERE, "verify-images.py")],
                           capture_output=True, text=True)
        sys.stdout.write(r.stdout)
        if r.returncode != 0:
            warn("镜像在线校验未通过/未完成（见上方输出）。可用 --skip-verify 显式跳过。")

    print("-" * 66)
    for w in WARNS:
        print("  [WARN] %s" % w)
    for e in ERRORS:
        print("  [ERROR] %s" % e)

    if ERRORS:
        print("-" * 66)
        print("自检未通过：%d 个 ERROR。修正后重跑。" % len(ERRORS))
        return 1
    print("自检通过（%d 个 WARN）。" % len(WARNS))

    dist = os.path.join(APP_ROOT, "dist")
    os.makedirs(dist, exist_ok=True)
    if not args.keep_dist:
        for name in os.listdir(dist):
            p = os.path.join(dist, name)
            if os.path.isfile(p):
                os.remove(p)

    files = ["config.ini", "%s.lang" % appid, "%s.svg" % appid]
    for name in files:
        write_lf(os.path.join(dist, name), read_text(os.path.join(APP_ROOT, name)))
    write_lf(os.path.join(dist, "docker-compose.yml"), compose)

    tarname = "%s.tar.gz" % appid
    tarpath = os.path.join(dist, tarname)
    with tarfile.open(tarpath, "w:gz") as tar:
        for name in sorted(files + ["docker-compose.yml"]):
            tar.add(os.path.join(dist, name), arcname=name)

    with tarfile.open(tarpath, "r:gz") as tar:
        members = sorted(m.name for m in tar.getmembers())
    expected = sorted(files + ["docker-compose.yml"])
    if members != expected:
        err("归档根层文件不是预期的 4 个：%s" % members)
        return 1

    digest = hashlib.sha256(open(tarpath, "rb").read()).hexdigest()
    write_lf(tarpath + ".sha256", "%s  %s\n" % (digest, tarname))

    print("-" * 66)
    print("归档根层文件：%s" % ", ".join(members))
    print("产物：")
    print("  %s" % tarpath)
    print("  %s.sha256" % tarpath)
    print("  sha256 = %s" % digest)
    print()
    print("下一步：把 %s 与 %s.sha256 一起上传到公开仓库的 Release 资产" % (tarname, tarname))
    print("（tag 必须等于 config.ini 的 version）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
