/* ============================================================
   Test Center Guide —— 站点脚本
   1) 中英切换（记忆在 localStorage，纯本机）
   2) 导航当前页高亮
   3) 代码块复制按钮（含 HTTP 下的降级方案）
   4) 部署助手：在本机生成 .env 与整套部署命令

   注意：本文件必须在外部引入（CSP 禁内联脚本），
   且不能使用内联 onclick —— 一律 addEventListener。
   ============================================================ */
(function () {
  "use strict";

  var LANG_KEY = "tc-guide-lang";
  /* 切语言时要重建部署助手的输出，由 initGenerator 注册 */
  var rerenderGenerator = null;

  /* ---------- 语言 ----------
     中文 = 页面 HTML 里的原文（首次应用时记下来，切回中文就还原）；
     英文 = assets/i18n.js 的字典。这样中文只有一份来源，不会漂移。 */
  function readLang() {
    try {
      return localStorage.getItem(LANG_KEY) === "en" ? "en" : "zh";
    } catch (e) {
      return "zh";
    }
  }

  function saveLang(lang) {
    try {
      localStorage.setItem(LANG_KEY, lang);
    } catch (e) {
      /* 隐私模式下写不进去也无妨 */
    }
  }

  function orig(el, prop, get) {
    if (el[prop] === undefined) { el[prop] = get(); }
    return el[prop];
  }

  /* 取文案：中文返回源码里的默认值，英文查字典（查不到退回默认值） */
  function L(key, zhDefault) {
    if (readLang() !== "en") { return zhDefault; }
    var d = (window.TC_I18N || {}).en || {};
    return d[key] !== undefined ? d[key] : zhDefault;
  }

  function applyLang(lang) {
    var dict = (window.TC_I18N || {})[lang] || {};
    var isEn = lang === "en";

    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      var fallback = orig(el, "__tcText", function () { return el.textContent; });
      var key = el.getAttribute("data-i18n");
      el.textContent = (isEn && dict[key] !== undefined) ? dict[key] : fallback;
    });

    document.querySelectorAll("[data-i18n-html]").forEach(function (el) {
      var fallback = orig(el, "__tcHtml", function () { return el.innerHTML; });
      var key = el.getAttribute("data-i18n-html");
      el.innerHTML = (isEn && dict[key] !== undefined) ? dict[key] : fallback;
    });

    document.querySelectorAll("[data-i18n-code]").forEach(function (el) {
      var code = el.querySelector("code") || el;
      var fallback = orig(code, "__tcText", function () { return code.textContent; });
      var key = el.getAttribute("data-i18n-code");
      code.textContent = (isEn && dict[key] !== undefined) ? dict[key] : fallback;
    });

    document.querySelectorAll("[data-i18n-ph]").forEach(function (el) {
      var fallback = orig(el, "__tcPh", function () { return el.getAttribute("placeholder") || ""; });
      var key = el.getAttribute("data-i18n-ph");
      el.setAttribute("placeholder", (isEn && dict[key] !== undefined) ? dict[key] : fallback);
    });

    var toggle = document.querySelector(".lang-toggle");
    if (toggle) {
      toggle.textContent = isEn ? (dict["lang.toggle"] || "中文") : "English";
    }

    document.querySelectorAll(".copy-btn").forEach(function (btn) {
      if (!btn.classList.contains("done") && !btn.hasAttribute("data-keep-label")) {
        btn.textContent = isEn ? (dict["common.copy"] || "Copy") : "复制";
      }
    });

    document.documentElement.lang = isEn ? "en" : "zh-CN";

    /* 部署助手生成的命令注释也随语言走，重建一次输出 */
    if (typeof rerenderGenerator === "function") { rerenderGenerator(); }
  }

  /* ---------- 复制（HTTP 环境下 clipboard API 不可用，必须有降级） ---------- */
  function copyText(text, onDone) {
    function fallback() {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.top = "-1000px";
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand("copy");
      } catch (e) {
        /* 忽略：极少数浏览器完全禁用复制 */
      }
      document.body.removeChild(ta);
      if (onDone) { onDone(); }
    }

    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(onDone, fallback);
    } else {
      fallback();
    }
  }

  function flashLabel(btn) {
    var dict = (window.TC_I18N || {})[readLang()] || {};
    var original = btn.getAttribute("data-original-label") || btn.textContent;
    btn.setAttribute("data-original-label", original);
    btn.textContent = dict["common.copied"] || "已复制";
    btn.classList.add("done");
    window.setTimeout(function () {
      btn.textContent = original;
      btn.classList.remove("done");
    }, 1600);
  }

  /* ---------- 复制按钮：<pre> 内容 ---------- */
  function initCopyButtons() {
    document.querySelectorAll(".code-wrap").forEach(function (wrap) {
      var pre = wrap.querySelector("pre");
      if (!pre || wrap.querySelector(".copy-btn")) { return; }

      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "copy-btn";
      btn.textContent = "复制";
      btn.addEventListener("click", function () {
        copyText(pre.innerText, function () { flashLabel(btn); });
      });
      wrap.appendChild(btn);
    });
  }

  /* ---------- 部署助手 ---------- */
  var DEFAULTS = {
    srvIp: "",
    webPort: "19613",
    dbHost: "",
    dbPort: "3306",
    dbName: "test-center",
    dbUser: "root",
    dbPassword: "",
    redisHost: "",
    redisPort: "6379",
    redisPassword: "",
    backendContainer: "test_center_backend",
    mysqlContainer: "test_center_mysql",
    adminUser: "admin",
    adminEmail: "test@example.com",
    adminPassword: "",
    secretKey: ""
  };

  function val(id, fallback) {
    var el = document.getElementById(id);
    if (!el) { return fallback || ""; }
    var v = (el.value || "").trim();
    return v === "" ? (fallback || "") : v;
  }

  function randomSecret() {
    var bytes = new Uint8Array(48);
    if (window.crypto && window.crypto.getRandomValues) {
      window.crypto.getRandomValues(bytes);
    } else {
      for (var i = 0; i < bytes.length; i++) {
        bytes[i] = Math.floor(Math.random() * 256);
      }
    }
    var out = "";
    for (var j = 0; j < bytes.length; j++) {
      out += ("0" + bytes[j].toString(16)).slice(-2);
    }
    return out.slice(0, 64);
  }

  function buildEnv() {
    var ip = val("srvIp", L("gen.out.ph.serverIp", "你的服务器IP"));
    var webPort = val("webPort", "19613");
    var secret = val("secretKey") || randomSecret();
    var bar = L("gen.out.env.header1", "# ============================================================");

    return [
      bar,
      L("gen.out.env.title", "# Test Center 环境配置"),
      L("gen.out.env.by", "# 由「Test Center 上手指南 · 部署助手」在本机生成"),
      L("gen.out.env.warn", "# 提示：本文件含口令，建议 chmod 600 .env，不要提交到代码仓库"),
      bar,
      "",
      L("gen.out.env.ip", "# 对外访问地址（浏览器用它拼出前端地址）"),
      "SERVER_PUBLIC_IP=" + ip,
      "",
      L("gen.out.env.mode", "# 部署模式：1 = 使用已有的 MySQL / Redis"),
      "MYSQL_DEPLOY_MODE=1",
      "REDIS_DEPLOY_MODE=1",
      "",
      "# ---- MySQL ----",
      "DB_HOST=" + val("dbHost", L("gen.out.ph.mysql", "你的MySQL地址")),
      "DB_PORT=" + val("dbPort", "3306"),
      "DB_NAME=" + val("dbName", "test-center"),
      "DB_USER=" + val("dbUser", "root"),
      "DB_PASSWORD=" + val("dbPassword", L("gen.out.ph.dbPass", "你的MySQL密码")),
      "",
      "# ---- Redis ----",
      "REDIS_HOST=" + val("redisHost", L("gen.out.ph.redis", "你的Redis地址")),
      "REDIS_PORT=" + val("redisPort", "6379"),
      "REDIS_PASSWORD=" + val("redisPassword", L("gen.out.ph.redisPass", "你的Redis密码")),
      "",
      "# ---- 应用 ----",
      "SECRET_KEY=" + secret,
      "SESSION_COOKIE_SECURE=False",
      "WEB_PORT=" + webPort
    ].join("\n");
  }

  function buildCommands() {
    var ip = val("srvIp", L("gen.out.ph.serverIp", "你的服务器IP"));
    var webPort = val("webPort", "19613");
    var dbName = val("dbName", "test-center");
    var dbUser = val("dbUser", "root");
    var dbPassword = val("dbPassword", L("gen.out.ph.dbPass", "你的MySQL密码"));
    var backend = val("backendContainer", "test_center_backend");
    var mysql = val("mysqlContainer", "test_center_mysql");
    var adminUser = val("adminUser", "test");
    var adminEmail = val("adminEmail", "test@example.com");
    var adminPassword = val("adminPassword", L("gen.out.ph.adminPass", "请换成一个强密码"));
    var bar = L("gen.out.env.header1", "# ============================================================");

    return [
      bar,
      L("gen.out.cmd.title", "# Test Center 手动部署命令序列"),
      L("gen.out.cmd.by", "# 由「Test Center 上手指南 · 部署助手」在本机生成"),
      L("gen.out.cmd.hint", "# 把 <尖括号> 的内容换成你的实际值后再执行"),
      bar,
      "",
      L("gen.out.cmd.s0", "# ---------- 0. 进入部署目录，准备 .env ----------"),
      "cd /path/to/test-center",
      L("gen.out.cmd.s0a", "ls -l .env      # 确认为上一步生成的配置文件"),
      L("gen.out.cmd.s0b", "chmod 600 .env  # 含口令，收紧权限"),
      "",
      L("gen.out.cmd.s1", "# ---------- 1. 创建专用网络 ----------"),
      "docker network create test_center_network",
      "",
      L("gen.out.cmd.s2", "# ---------- 2. 登录镜像仓库并拉取镜像 ----------"),
      L("gen.out.cmd.s2a", "# 镜像仓库地址与登录凭据由项目方提供（本指南不内置任何凭据）"),
      "docker login " + L("gen.out.ph.registry", "<镜像仓库地址>"),
      "docker pull " + L("gen.out.ph.backendImg", "<后端镜像>"),
      "docker pull " + L("gen.out.ph.frontendImg", "<前端镜像>"),
      "",
      L("gen.out.cmd.s2b", "# 同时确认 MySQL / Redis 容器已加入该网络（用已有的可跳过）"),
      "docker network connect test_center_network " + mysql + " || true",
      "",
      L("gen.out.cmd.s3", "# ---------- 3. 创建数据库 ----------"),
      "docker exec -i " + mysql + " mysql -u" + dbUser + " -p'" + dbPassword + "' -e \\",
      "  \"CREATE DATABASE IF NOT EXISTS \\`" + dbName + "\\` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\"",
      "",
      L("gen.out.cmd.s4", "# ---------- 4. 启动服务 ----------"),
      L("gen.out.cmd.s4a", "# 数据库迁移由后端容器启动时自动执行，无需手动 migrate"),
      "docker compose --env-file .env up -d",
      "docker compose ps",
      "",
      L("gen.out.cmd.s5", "# ---------- 5. 初始化基础数据（缺一不可） ----------"),
      "docker exec " + backend + " python manage.py init_locator_strategies",
      "docker exec " + backend + " python manage.py init_system_tasks",
      "docker exec " + backend + " python manage.py init_notification_templates",
      "docker exec " + backend + " python manage.py load_component_pack",
      "docker exec " + backend + " python manage.py sync_agent_builtin_docs",
      "",
      L("gen.out.cmd.s6", "# ---------- 6. 创建管理员账号 ----------"),
      "docker exec -i " + backend + " python manage.py shell << 'EOSHELL'",
      "from django.contrib.auth import get_user_model",
      "User = get_user_model()",
      "if not User.objects.filter(username='" + adminUser + "').exists():",
      "    User.objects.create_superuser('" + adminUser + "', '" + adminEmail + "', '" + adminPassword + "')",
      L("gen.out.cmd.s6a", "    print('管理员账号已创建')"),
      "else:",
      L("gen.out.cmd.s6b", "    print('管理员账号已存在')"),
      "EOSHELL",
      "",
      L("gen.out.cmd.s7", "# ---------- 7. 验证 ----------"),
      "curl -I http://" + ip + ":" + webPort + "/",
      L("gen.out.cmd.s7a", "# 浏览器打开 http://" + ip + ":" + webPort + "/ ，看到登录页即为部署成功"),
      L("gen.out.cmd.s7b", "# 首次登录后请立即修改默认密码")
    ].join("\n");
  }

  function setOutput(preId, text) {
    var pre = document.getElementById(preId);
    if (!pre) { return; }
    var code = pre.querySelector("code");
    if (code) { code.textContent = text; } else { pre.textContent = text; }
  }

  function initGenerator() {
    var form = document.getElementById("generator-form");
    if (!form) { return; }

    var secretInput = document.getElementById("secretKey");
    var rollBtn = document.getElementById("btn-secret");
    var genBtn = document.getElementById("btn-generate");
    var copyEnvBtn = document.getElementById("btn-copy-env");
    var copyCmdBtn = document.getElementById("btn-copy-cmd");
    var dlBtn = document.getElementById("btn-download");

    function generate() {
      if (secretInput && !secretInput.value.trim()) {
        secretInput.value = randomSecret();
      }
      setOutput("out-env", buildEnv());
      setOutput("out-cmd", buildCommands());
    }

    if (rollBtn) {
      rollBtn.addEventListener("click", function () {
        if (secretInput) { secretInput.value = randomSecret(); }
        generate();
      });
    }

    if (genBtn) { genBtn.addEventListener("click", generate); }

    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      generate();
    });

    if (copyEnvBtn) {
      copyEnvBtn.addEventListener("click", function () {
        copyText(buildEnv(), function () { flashLabel(copyEnvBtn); });
      });
    }

    if (copyCmdBtn) {
      copyCmdBtn.addEventListener("click", function () {
        copyText(buildCommands(), function () { flashLabel(copyCmdBtn); });
      });
    }

    if (dlBtn) {
      dlBtn.addEventListener("click", function () {
        var blob = new Blob([buildEnv() + "\n"], { type: "text/plain;charset=utf-8" });
        var url = URL.createObjectURL(blob);
        var a = document.createElement("a");
        a.href = url;
        a.download = ".env";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
      });
    }

    /* 表单里的默认值：只填能被安全推断的项 */
    Object.keys(DEFAULTS).forEach(function (id) {
      var el = document.getElementById(id);
      if (el && !el.value && DEFAULTS[id]) { el.value = DEFAULTS[id]; }
    });

    /* 注册给 applyLang：切换语言时按新语言重建命令注释 */
    rerenderGenerator = generate;

    generate();
  }

  /* ---------- 导航高亮 ---------- */
  function markCurrentNav() {
    var here = window.location.pathname.split("/").pop() || "index.html";
    document.querySelectorAll("nav.main-nav a").forEach(function (a) {
      var target = a.getAttribute("href");
      if (target === here || (here === "index.html" && target === "./")) {
        a.setAttribute("aria-current", "page");
      }
    });
  }

  /* ---------- 入口 ---------- */
  document.addEventListener("DOMContentLoaded", function () {
    var lang = readLang();
    applyLang(lang);

    var toggle = document.querySelector(".lang-toggle");
    if (toggle) {
      toggle.addEventListener("click", function () {
        var next = readLang() === "zh" ? "en" : "zh";
        saveLang(next);
        applyLang(next);
      });
    }

    markCurrentNav();
    initCopyButtons();
    initGenerator();
  });
})();
