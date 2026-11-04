# ============================================================
# DawnCMS — 独立博客内容管理系统
# Copyright (c) 2026 DawnCMS. All rights reserved.
# ============================================================
# plugins/__init__.py
# 插件加载器：扫描 plugins/ 下含 plugin.py 的子目录并挂载

import importlib
import sys
from pathlib import Path

DAWN_PLUGIN_META_KEYS = ("key", "label", "group", "icon", "url")

_dawn_loaded: list = []


def dawn_load_plugins(app) -> list:
    """加载所有插件，返回已加载插件元信息列表。插件约定：

    plugins/{name}/plugin.py 内定义：
        DAWN_PLUGIN = {"key": "...", "label": "显示名", "group": "插件",
                  "icon": "🧩", "url": "/dadmin/plugins/xxx"}   # 可选
        def dawn_setup(app): ...                                    # 注册路由
    """
    global _dawn_loaded
    if _dawn_loaded:
        return _dawn_loaded

    base = Path(__file__).parent
    sys.path.insert(0, str(base))
    try:
        for child in sorted(base.iterdir()):
            plugin_file = child / "plugin.py"
            if not child.is_dir() or child.name.startswith("_") or not plugin_file.exists():
                continue
            try:
                mod = importlib.import_module(f"{child.name}.plugin")
                meta = {k: getattr(mod, "DAWN_PLUGIN", {}).get(k) for k in DAWN_PLUGIN_META_KEYS}
                if hasattr(mod, "dawn_setup"):
                    mod.dawn_setup(app)
                meta["name"] = child.name
                meta["status"] = "ok"
                _dawn_loaded.append(meta)
                print(f"[plugins] 已加载: {child.name}")
            except Exception as e:
                _dawn_loaded.append({"name": child.name, "status": f"error: {e}"})
                print(f"[plugins] 加载失败 {child.name}: {e}")
    finally:
        sys.path.remove(str(base))
    return _dawn_loaded


def dawn_get_loaded_plugins() -> list:
    return _dawn_loaded


# ---------- 钩子机制：主程序在关键节点呼叫插件 ----------

DAWN_HOOKS: dict = {}


def dawn_register_hook(name: str, func) -> None:
    """插件注册钩子。当前支持的钩子：
    - article_render(article=dict, session=dict) -> dict | None
      文章页渲染前调用，返回的 dict 会合入模板上下文（如 article_banner、extra_head）
    - sitemap_urls() -> list[str]
      生成 sitemap.xml 时调用，返回额外的 <url>...</url> XML 片段列表
    - lang_switch(page_type=str, slug=str, cat_slug=str, current=str) -> list
      前台导航语言下拉的切换项（url/label/code/current），按当前页面类型给出对应语言链接
    - admin_post_panel(post_id=int, post=dict) -> component | None
      后台文章编辑页底部追加面板（如多语言译文 tab 编辑器），返回值直接并入页面
    - seo_ctx(ctx=dict) -> None（同步钩子）
      前台渲染前调用，原地修改模板上下文（如覆盖 page_title/page_desc/robots_meta）
    - head_extra(ctx=dict) -> str | None（同步钩子）
      前台渲染时调用，返回的 HTML 片段并入 <head> 的 extra_head 插槽
      （ctx 含 a=文章字典 / is_home / current_cat / tag / series 等定位信息）
    """
    DAWN_HOOKS.setdefault(name, []).append(func)


async def dawn_collect_hooks(name: str, **kwargs) -> list:
    """调用某钩子的全部注册函数（支持同步/异步），返回非空结果列表"""
    import inspect
    results = []
    for func in DAWN_HOOKS.get(name, []):
        try:
            res = func(**kwargs)
            if inspect.isawaitable(res):
                res = await res
            if res:
                results.append(res)
        except Exception as e:
            print(f"[plugins] 钩子 {name} 执行失败: {e}")
    return results


def dawn_collect_hooks_sync(name: str, **kwargs) -> list:
    """同步场景调用钩子（仅同步函数生效）：
    - nav_links() -> list[dict]  追加头部导航项 [{"label":..., "url":...}]
    """
    import inspect
    results = []
    for func in DAWN_HOOKS.get(name, []):
        if inspect.iscoroutinefunction(func):
            continue
        try:
            res = func(**kwargs)
            if res:
                results.append(res)
        except Exception as e:
            print(f"[plugins] 钩子 {name} 执行失败: {e}")
    return results
