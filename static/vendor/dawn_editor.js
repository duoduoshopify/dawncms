/* DawnCMS 后台文章编辑器（Vditor IR 即时渲染 + Ghost 式 / 菜单 + 自定义块）
 * 存储格式保持 Markdown，与服务端渲染管线完全一致。
 */
(function () {
  "use strict";

  var CTA_SVG = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="6" width="18" height="12" rx="2"/><path d="M7 12h10M12 9v6"/></svg>';
  var VIDEO_SVG = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M10 9l5 3-5 3z" fill="currentColor"/></svg>';

  /* ---- Ghost 式 / 斜杠菜单数据源 ---- */
  var SLASH_ITEMS = [
    { k: "图片", s: "image img tupian", v: "![图片描述](图片地址)\n" },
    { k: "CTA 转化块", s: "cta 转化 按钮", v: ":::cta\ntitle: 标题\ndesc: 一句话描述\nbutton_text: 按钮文字\nbutton_url: https://\n:::\n\n" },
    { k: "YouTube 视频", s: "youtube yt 视频", v: ":::embed youtube https://www.youtube.com/watch?v=视频ID :::\n\n" },
    { k: "本地视频", s: "video 视频 shipin", v: ":::embed video /uploads/blog/视频.mp4 :::\n\n" },
    { k: "提示块", s: "callout 提示 tips", v: ":::callout\nicon: 💡\n提示内容，支持 **粗体** 和 [链接](https://)\n:::\n\n" },
    { k: "折叠块", s: "toggle 折叠 展开", v: ":::toggle\ntitle: 点击展开\n折叠的内容\n:::\n\n" },
    { k: "按钮", s: "button 按钮", v: ":::button\ntext: 按钮文字\nurl: https://\n:::\n\n" },
    { k: "书签卡片", s: "bookmark 书签 链接卡片", v: ":::bookmark\nurl: https://\ntitle: 链接标题\ndesc: 链接描述\n:::\n\n" },
    { k: "表格", s: "table 表格 biaoge", v: "| 列1 | 列2 | 列3 |\n| --- | --- | --- |\n|  |  |  |\n\n" },
    { k: "代码块", s: "code 代码 daima", v: "```\n\n```\n" },
    { k: "分割线", s: "hr 分割线 fenge", v: "\n---\n\n" }
  ];

  function slashHint(word) {
    word = (word || "").toLowerCase();
    return SLASH_ITEMS.filter(function (it) {
      return !word || it.k.toLowerCase().indexOf(word) >= 0 || it.s.indexOf(word) >= 0;
    }).map(function (it) {
      return {
        value: it.v,
        html: '<div style="padding:4px 0"><div style="font-weight:600">' + it.k + '</div>' +
              '<div style="font-size:11px;opacity:.55">' + it.s.split(" ")[0] + '</div></div>'
      };
    });
  }

  /* ---- 自定义块弹窗 ---- */
  function openModal(title, fields, onOk) {
    var light = true;
    try { light = (localStorage.getItem("dawn_adm_theme") || "light") === "light"; } catch (e) {}
    var C = light
      ? { box: "#fdfcf9", line: "#e6e3da", title: "#3a3f46", label: "#6e747c", inputBg: "#f5f4ef", inputLine: "#d9d5c9", inputText: "#3a3f46", cancelText: "#6e747c" }
      : { box: "#0f172a", line: "#1e293b", title: "#ffffff", label: "#94a3b8", inputBg: "#1e293b", inputLine: "#334155", inputText: "#e2e8f0", cancelText: "#94a3b8" };
    var ov = document.createElement("div");
    ov.style.cssText = "position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center";
    var box = document.createElement("div");
    box.style.cssText = "width:380px;background:" + C.box + ";border:1px solid " + C.line + ";border-radius:14px;padding:20px;box-shadow:0 20px 60px rgba(0,0,0,.5)";
    box.innerHTML = '<div style="color:' + C.title + ';font-weight:800;font-size:14px;margin-bottom:14px">' + title + "</div>";
    var inputs = {};
    fields.forEach(function (f) {
      var lb = document.createElement("label");
      lb.style.cssText = "display:block;color:" + C.label + ";font-size:12px;margin:10px 0 4px";
      lb.textContent = f.label;
      var ip = document.createElement("input");
      ip.style.cssText = "width:100%;box-sizing:border-box;background:" + C.inputBg + ";border:1px solid " + C.inputLine + ";border-radius:8px;color:" + C.inputText + ";font-size:13px;padding:8px 10px;outline:none";
      ip.value = f.def || "";
      ip.placeholder = f.ph || "";
      inputs[f.key] = ip;
      box.appendChild(lb); box.appendChild(ip);
    });
    var row = document.createElement("div");
    row.style.cssText = "display:flex;justify-content:flex-end;gap:8px;margin-top:16px";
    var cancel = document.createElement("button");
    cancel.textContent = "取消";
    cancel.style.cssText = "padding:7px 14px;border-radius:8px;border:1px solid " + C.line + ";background:transparent;color:" + C.cancelText + ";font-size:13px;cursor:pointer";
    cancel.onclick = function () { ov.remove(); };
    var ok = document.createElement("button");
    ok.textContent = "插入";
    ok.style.cssText = "padding:7px 16px;border-radius:8px;border:0;background:#4f46e5;color:#fff;font-size:13px;font-weight:700;cursor:pointer";
    ok.onclick = function () {
      var vals = {};
      for (var k in inputs) vals[k] = inputs[k].value.trim();
      ov.remove();
      onOk(vals);
    };
    row.appendChild(cancel); row.appendChild(ok);
    box.appendChild(row);
    ov.appendChild(box);
    ov.onclick = function (e) { if (e.target === ov) ov.remove(); };
    document.body.appendChild(ov);
    var first = fields[0] && inputs[fields[0].key];
    if (first) first.focus();
  }

  function insertCta(vditor) {
    openModal("插入 CTA 转化块", [
      { key: "title", label: "标题", def: "立即咨询" },
      { key: "desc", label: "描述", ph: "一句话说明价值" },
      { key: "button_text", label: "按钮文字", def: "查看详情" },
      { key: "button_url", label: "按钮链接", def: "/contact" }
    ], function (v) {
      vditor.insertValue(
        ":::cta\ntitle: " + (v.title || "立即咨询") +
        "\ndesc: " + v.desc +
        "\nbutton_text: " + (v.button_text || "查看详情") +
        "\nbutton_url: " + (v.button_url || "#") + "\n:::\n\n", true);
    });
  }

  function insertVideo(vditor) {
    openModal("插入视频（YouTube 地址或站内视频文件地址）", [
      { key: "url", label: "视频地址", ph: "https://www.youtube.com/watch?v=... 或 /uploads/blog/xxx.mp4" }
    ], function (v) {
      if (!v.url) return;
      var provider = /youtube\.com|youtu\.be/.test(v.url) ? "youtube" : "video";
      vditor.insertValue(":::embed " + provider + " " + v.url + " :::\n\n", true);
    });
  }

  /* ---- 草稿（localStorage，5s 防抖） ---- */
  function draftKey(postId) { return "dawn_draft_post_" + (postId || "new"); }

  window.dawnInitEditor = function (postId) {
    var ta = document.getElementById("post-content");
    var holder = document.getElementById("dawn-vditor");
    if (!ta || !holder || typeof Vditor === "undefined") return;
    var form = ta.closest("form");
    var original = ta.value || "";
    var saveTimer = null;
    var isLight = false;
    try { isLight = (localStorage.getItem("dawn_adm_theme") || "light") === "light"; } catch (e) { isLight = true; }

    var vditor = new Vditor(holder, {
      cdn: "/static/vendor/vditor",
      lang: "zh_CN",
      mode: "ir",
      theme: isLight ? "classic" : "dark",
      icon: "material",
      height: 620,
      minHeight: 480,
      value: original,
      cache: { enable: false },
      counter: { enable: true, type: "text" },
      toolbarConfig: { pin: true },
      toolbar: [
        "headings", "bold", "italic", "strike", "|",
        "quote", "list", "ordered-list", "check", "|",
        "link", "upload", "table", "code", "inline-code", "|",
        { name: "cta", tip: "插入 CTA 转化块", className: "vditor-tooltipped vditor-tooltipped__n", icon: CTA_SVG,
          click: function () { insertCta(vditor); } },
        { name: "dvideo", tip: "插入视频", className: "vditor-tooltipped vditor-tooltipped__n", icon: VIDEO_SVG,
          click: function () { insertVideo(vditor); } },
        "|",
        "undo", "redo", "outline", "preview", "edit-mode", "fullscreen"
      ],
      hint: {
        emoji: false,
        extend: [{ key: "/", hint: slashHint }]
      },
      upload: {
        url: "/dadmin/api/media/upload",
        fieldName: "file",
        max: 8 * 1024 * 1024,
        accept: "image/*",
        format: function (files, responseText) { return responseText; }
      },
      preview: {
        theme: { current: isLight ? "light" : "dark" },
        hljs: { style: isLight ? "github" : "github-dark" },
        maxWidth: 100000
      },
      after: function () {
        /* 草稿恢复提示 */
        try {
          var raw = localStorage.getItem(draftKey(postId));
          if (raw) {
            var d = JSON.parse(raw);
            if (d && d.content && d.content !== original) {
              var bar = document.createElement("div");
              bar.style.cssText = "margin:0 0 10px;padding:10px 14px;border-radius:10px;background:#312e81;color:#c7d2fe;font-size:12px;display:flex;align-items:center;justify-content:space-between";
              bar.innerHTML = '<span>📝 发现未保存的草稿（' + (d.ts || "") + "）</span>";
              var btns = document.createElement("span");
              var b1 = document.createElement("button");
              b1.textContent = "恢复草稿"; b1.type = "button";
              b1.style.cssText = "margin-left:10px;padding:4px 12px;border-radius:6px;border:0;background:#4f46e5;color:#fff;font-size:12px;cursor:pointer";
              b1.onclick = function () { vditor.setValue(d.content); ta.value = d.content; bar.remove(); };
              var b2 = document.createElement("button");
              b2.textContent = "忽略"; b2.type = "button";
              b2.style.cssText = "margin-left:8px;padding:4px 12px;border-radius:6px;border:1px solid #4338ca;background:transparent;color:#a5b4fc;font-size:12px;cursor:pointer";
              b2.onclick = function () { localStorage.removeItem(draftKey(postId)); bar.remove(); };
              btns.appendChild(b1); btns.appendChild(b2);
              bar.appendChild(btns);
              holder.parentNode.insertBefore(bar, holder);
            }
          }
        } catch (e) {}
        ta.value = vditor.getValue();
      },
      input: function (md) {
        ta.value = md;
        clearTimeout(saveTimer);
        saveTimer = setTimeout(function () {
          try {
            localStorage.setItem(draftKey(postId), JSON.stringify({
              content: md, ts: new Date().toLocaleString("zh-CN", { hour12: false })
            }));
          } catch (e) {}
        }, 5000);
      }
    });

    /* 保存成功后清草稿（页面跳转前）；Ctrl+S 快捷保存 */
    if (form) {
      form.addEventListener("submit", function () {
        ta.value = vditor.getValue();
        localStorage.removeItem(draftKey(postId));
      });
    }
    document.addEventListener("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        var ae = document.activeElement;
        if (holder.contains(ae) || (ae && ae.closest && ae.closest("#dawn-vditor"))) {
          e.preventDefault();
          ta.value = vditor.getValue();
          if (form) { localStorage.removeItem(draftKey(postId)); form.requestSubmit(); }
        }
      }
    });
  };
})();
