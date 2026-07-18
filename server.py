"""
Minecraft Wiki RSS 自动翻译推送服务 - 后端
功能：抓取 Fandom Minecraft Wiki RSS → Google 翻译为中文 → HTTP API 供 Android 客户端拉取
"""

import xml.etree.ElementTree as ET
import json
import hashlib
import time
import os
import re
import logging
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from html import unescape
import threading

# ============ 配置 ============
RSS_URL = "https://minecraft.fandom.com/api.php?action=feedrecentchanges&feedformat=rss"
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "translated_items.json")
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8765
MAX_CACHE_ITEMS = 200  # 最多缓存条目数

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("mcwiki")


# ============ 翻译引擎（多引擎自动降级） ============
# 优先 deep-translator (Google)，失败则降级到 MyMemory API
_translate_use_fallback = False


def _translate_deep_translator(text: str) -> str:
    """方案1: deep-translator (Google Translate)"""
    from deep_translator import GoogleTranslator
    t = GoogleTranslator(source="en", target="zh-CN")
    return t.translate(text) or text


def _translate_mymemory(text: str) -> str:
    """方案2: MyMemory 免费翻译 API (无需 Key)"""
    url = f"https://api.mymemory.translated.net/get?{urlencode({'q': text[:500], 'langpair': 'en|zh-CN'})}"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["responseData"]["translatedText"]


def google_translate(text: str) -> str:
    """翻译文本为中文，多引擎自动降级 + MC 专有名词保护"""
    global _translate_use_fallback
    if not text or not text.strip():
        return text
    if len(text) > 3000:
        text = text[:3000] + "...(已截断)"
    # 翻译前保护 MC 专有名词
    text = _protect_terms(text)
    try:
        if not _translate_use_fallback:
            result = _translate_deep_translator(text)
        else:
            result = _translate_mymemory(text)
        # 翻译后还原
        return _restore_terms(result) if result else text
    except Exception as e:
        logger.warning(f"翻译失败({_translate_use_fallback}): {e}")
        if not _translate_use_fallback:
            _translate_use_fallback = True
            logger.info("切换到 MyMemory 备用翻译引擎")
            try:
                result = _translate_mymemory(text)
                return _restore_terms(result) if result else text
            except Exception as e2:
                logger.warning(f"MyMemory 也失败: {e2}")
        return _restore_terms(text) + " [翻译失败]"


# ============ Minecraft 专有名词保护词典 ============
# 翻译前替换为占位符，翻译后还原，避免专有名词被乱翻
MC_TERMS = {
    # 方块/物品
    "Block": "§BLOCK§", "blocks": "§BLOCKS§", "Blocks": "§BLOCKS§",
    "item": "§ITEM§", "items": "§ITEMS§",
    "entity": "§ENTITY§", "entities": "§ENTITIES§",
    "mob": "§MOB§", "mobs": "§MOBS§",
    "Creeper": "§CREEPER§", "Zombie": "§ZOMBIE§", "Skeleton": "§SKELETON§",
    "Spider": "§SPIDER§", "Enderman": "§ENDERMAN§", "Blaze": "§BLAZE§",
    "Ghast": "§GHAST§", "Slime": "§SLIME§", "Witch": "§WITCH§",
    "Villager": "§VILLAGER§", "Iron Golem": "§IRON_GOLEM§",
    "Snow Golem": "§SNOW_GOLEM§", "Wither": "§WITHER§", "Ender Dragon": "§ENDER_DRAGON§",
    "Warden": "§WARDEN§", "Allay": "§ALLAY§", "Frog": "§FROG§",
    "Copper": "§COPPER§", "copper": "§COPPER§",
    "Redstone": "§REDSTONE§", "redstone": "§REDSTONE§",
    "Netherite": "§NETHERITE§", "netherite": "§NETHERITE§",
    "Diamond": "§DIAMOND§", "diamond": "§DIAMOND§",
    "Emerald": "§EMERALD§", "emerald": "§EMERALD§",
    "Gold": "§GOLD§", "Iron": "§IRON§", "Coal": "§COAL§",
    "Lapis Lazuli": "§LAPIS§", "Lapis": "§LAPIS§",
    "Obsidian": "§OBSIDIAN§", "obsidian": "§OBSIDIAN§",
    "Bedrock": "§BEDROCK§", "bedrock": "§BEDROCK§",
    "Cobblestone": "§COBBLESTONE§", "cobblestone": "§COBBLESTONE§",
    "Sandstone": "§SANDSTONE§", "sandstone": "§SANDSTONE§",
    "Stairs": "§STAIRS§", "stairs": "§STAIRS§",
    "Slab": "§SLAB§", "slabs": "§SLABS§", "Slabs": "§SLABS§",
    "Snow": "§SNOW§", "snow": "§SNOW§",
    "Ladder": "§LADDER§", "ladder": "§LADDER§",
    "Vine": "§VINE§", "vines": "§VINES§", "Vines": "§VINES§",
    "Turtle Egg": "§TURTLE_EGG§", "Sea Pickle": "§SEA_PICKLE§",
    "Coral": "§CORAL§", "coral": "§CORAL§",
    "Enchanting": "§ENCHANTING§", "enchanting": "§ENCHANTING§",
    "enchantment": "§ENCHANTMENT§", "enchantments": "§ENCHANTMENTS§",
    "potion": "§POTION§", "potions": "§POTIONS§",
    "crafting": "§CRAFTING§", "Crafting": "§CRAFTING§",
    "smelting": "§SMELTING§", "Smelting": "§SMELTING§",
    "brewing": "§BREWING§", "Brewing": "§BREWING§",
    "Nether": "§NETHER§", "nether": "§NETHER§",
    "End": "§END§", "The End": "§THE_END§",
    "Overworld": "§OVERWORLD§", "overworld": "§OVERWORLD§",
    "dimension": "§DIMENSION§",
    "biome": "§BIOME§", "biomes": "§BIOMES§",
    "chunk": "§CHUNK§", "chunks": "§CHUNKS§",
    "tick": "§TICK§", "ticks": "§TICKS§",
    "experience": "§XP§", "Experience": "§XP§",
    "hunger": "§HUNGER§", "Hunger": "§HUNGER§",
    "health": "§HEALTH§",
    "armor": "§ARMOR§", "Armor": "§ARMOR§",
    "damage": "§DAMAGE§", "Damage": "§DAMAGE§",
    "durability": "§DURABILITY§",
    "creative mode": "§CREATIVE§", "survival mode": "§SURVIVAL§",
    "hardcore": "§HARDCORE§", "spectator mode": "§SPECTATOR§",
    "Minecraft": "§MC§", "Wiki": "§WIKI§",
    "Java Edition": "§JAVA_ED§", "Bedrock Edition": "§BEDROCK_ED§",
    "Bukkit": "§BUKKIT§", "Spigot": "§SPIGOT§", "Paper": "§PAPER§",
    "Fabric": "§FABRIC§", "Forge": "§FORGE§",
    "command": "§COMMAND§", "commands": "§COMMANDS§",
    "data pack": "§DATAPACK§", "resource pack": "§RESOURCEPACK§",
    "behavior pack": "§BEHAVIORPACK§",
    "Transparent": "§TRANSPARENT§", "Opaque": "§OPAQUE§",
    "Explosion": "§EXPLOSION§", "explosion": "§EXPLOSION§",
    "explosions": "§EXPLOSIONS§", "Explosions": "§EXPLOSIONS§",
    "waxed": "§WAXED§",
    # 常见模板/分类名
    "Template:": "§TPL§:", "Category:": "§CAT§:",
    "Talk:": "§TALK§:", "User:": "§USER§:",
    "User talk:": "§USERTALK§:", "Special:": "§SPECIAL§:",
    "Minecraft Wiki:": "§MCWIKI§:",
}

# 翻译后还原用
_MC_RESTORE = {v: k for k, v in MC_TERMS.items()}


def _protect_terms(text: str) -> str:
    """翻译前：将 MC 专有名词替换为占位符"""
    # 按长度降序排列，优先匹配长词
    for en, placeholder in sorted(MC_TERMS.items(), key=lambda x: -len(x[0])):
        text = re.sub(re.escape(en), placeholder, text)
    return text


def _restore_terms(text: str) -> str:
    """翻译后：将占位符还原为 MC 专有名词"""
    for placeholder, en in _MC_RESTORE.items():
        text = text.replace(placeholder, en)
    return text


# ============ 需要跳过的非内容页面 ============
SKIP_TITLE_PREFIXES = (
    "User talk:", "User:", "User blog comment:",
    "Template:", "Template talk:",
    "Minecraft Wiki:", "Minecraft Wiki talk:",
    "Help:", "Help talk:",
    "Forum:", "Thread:",
    "Category talk:",
)

# ============ MediaWiki 内部链接清理 ============
def _clean_wikilinks(text: str) -> str:
    """处理 [[目标页面|显示文本]] → 显示文本，[[目标页面]] → 目标页面"""
    # [[File:xxx|...]] → 整个删除
    text = re.sub(r"\[\[File:[^\]]*\]\]", "", text)
    text = re.sub(r"\[\[Image:[^\]]*\]\]", "", text)
    text = re.sub(r"\[\[wikipedia:[^\]]*\]\]", "", text)
    # [[xxx|yyy]] → yyy
    text = re.sub(r"\[\[[^|\]]+\|([^\]]+)\]\]", r"\1", text)
    # [[xxx]] → xxx
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    return text


# ============ HTML/Diff 智能清理 ============
def clean_html(html_text: str, title: str = "") -> str:
    """
    基于 RSS 实际结构的智能清理。

    RSS <description> 的真实结构：
      <p>编辑摘要</p>                           ← 最有用，优先提取
      <table>diff差异表格</table>                ← 最大噪音源，但 <ins> 里有新增内容
      <div>...</div>                             ← 新建页面时的模板内容

    策略：
    1. 非条目页面直接跳过
    2. 优先提取 <p> 编辑摘要
    3. 无摘要时从 diff 表格提取 <ins> 新增内容
    4. 清理 MediaWiki 标记语法
    """
    text = unescape(html_text)

    # ---- 0. 跳过非内容页面 ----
    if any(title.startswith(p) for p in SKIP_TITLE_PREFIXES):
        return "(系统/用户页面，已跳过)"

    # ---- 1. 提取 diff 表格中的 <ins> 新增内容（在删表之前） ----
    ins_contents = []
    for m in re.finditer(r"<ins[^>]*>(.*?)</ins>", text, re.DOTALL):
        ins_text = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        ins_text = _clean_wikilinks(ins_text)
        ins_text = re.sub(r"\s+", " ", ins_text).strip()
        if ins_text and len(ins_text) > 2:
            ins_contents.append(ins_text)

    # ---- 2. 删除 diff 表格（最大噪音源） ----
    text_no_table = re.sub(r"<table.*?</table>", "", text, flags=re.DOTALL)
    # 删除 HTML 注释
    text_no_table = re.sub(r"<!--.*?-->", "", text_no_table, flags=re.DOTALL)

    # ---- 3. 提取 <p> 编辑摘要 ----
    p_texts = re.findall(r"<p>(.*?)</p>", text_no_table, re.DOTALL)
    summary_parts = []
    for p in p_texts:
        p_clean = re.sub(r"<[^>]+>", "", p).strip()
        p_clean = _clean_wikilinks(p_clean)
        p_clean = re.sub(r"\{\{[^}]*\}\}", "", p_clean).strip()
        # 过滤无意义摘要
        if not p_clean or len(p_clean) <= 2:
            continue
        # "New page"、"Created page with" 后面跟模板的，只保留模板名
        p_clean = re.sub(r"^Created page with\s*\"", "", p_clean).strip()
        p_clean = re.sub(r"^New page$", "", p_clean).strip()
        p_clean = p_clean.rstrip('"').strip()
        if p_clean and p_clean not in ("", "New page"):
            summary_parts.append(p_clean)

    # ---- 4. 确定最终输出 ----
    # 优先级：p 摘要 > ins 新增内容 > 兜底
    if summary_parts:
        result = " | ".join(summary_parts)
    elif ins_contents:
        result = "+ " + "; + ".join(ins_contents[:3])
    else:
        # 从剩余文本中提取 <div> 内容作为最后手段
        div_texts = re.findall(r"<div>(.*?)</div>", text_no_table, re.DOTALL)
        div_clean = ""
        for d in div_texts:
            dc = re.sub(r"<[^>]+>", "", d).strip()
            dc = _clean_wikilinks(dc)
            dc = re.sub(r"\{\{[^}]*\}\}", "", dc).strip()
            if len(dc) > 10:
                div_clean = dc
                break
        if div_clean:
            result = div_clean
        else:
            return "(无详细描述，请查看原文)"

    # ---- 5. 最终清理 ----
    result = re.sub(r"\s+", " ", result).strip()
    if len(result) > 300:
        result = result[:300] + "..."
    return result


# ============ RSS 抓取与处理 ============
def fetch_and_process_rss():
    """抓取 RSS 并翻译，返回新增条目列表"""
    logger.info("开始抓取 Minecraft Wiki RSS...")
    try:
        req = Request(RSS_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=20) as resp:
            xml_data = resp.read().decode("utf-8")
    except Exception as e:
        logger.error(f"抓取 RSS 失败: {e}")
        return []

    root = ET.fromstring(xml_data)
    channel = root.find("channel")
    items = channel.findall("item")

    # 加载已有数据
    existing = load_data()
    existing_hashes = {item["hash"] for item in existing}

    new_items = []
    for item in items:
        title_el = item.find("title")
        link_el = item.find("link")
        desc_el = item.find("description")
        pub_date_el = item.find("pubDate")
        creator_el = item.find("{http://purl.org/dc/elements/1.1/}creator")

        if title_el is None or link_el is None:
            continue

        title = title_el.text or ""
        link = link_el.text or ""
        desc_raw = desc_el.text or "" if desc_el is not None else ""
        pub_date = pub_date_el.text or "" if pub_date_el is not None else ""
        creator = creator_el.text or "未知" if creator_el is not None else "未知"

        # 生成哈希去重
        item_hash = hashlib.md5(f"{title}:{link}".encode()).hexdigest()[:12]

        if item_hash in existing_hashes:
            continue

        # 清理并翻译
        clean_desc = clean_html(desc_raw, title)

        # 跳过非内容页面的翻译
        if clean_desc == "(系统/用户页面，已跳过)":
            continue

        logger.info(f"翻译: {title} → {clean_desc[:60]}")
        title_zh = google_translate(title)
        desc_zh = google_translate(clean_desc)

        new_entry = {
            "hash": item_hash,
            "title_original": title,
            "title_translated": title_zh,
            "description_original": clean_desc,
            "description_translated": desc_zh,
            "link": link,
            "author": creator,
            "pub_date": pub_date,
            "fetch_time": datetime.now(timezone.utc).isoformat(),
        }
        new_items.append(new_entry)

    if new_items:
        existing = (new_items + existing)[:MAX_CACHE_ITEMS]
        save_data(existing)
        logger.info(f"新增 {len(new_items)} 条翻译条目")
    else:
        logger.info("没有新条目")

    return new_items


# ============ 数据持久化 ============
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ============ HTTP API 服务 ============
class WikiHandler(BaseHTTPRequestHandler):
    """供 Android 客户端调用的 HTTP API"""

    def do_GET(self):
        if self.path == "/api/feed" or self.path == "/api/feed/":
            self._handle_feed()
        elif self.path == "/api/status" or self.path == "/api/status/":
            self._handle_status()
        elif self.path == "/" or self.path == "":
            self._handle_index()
        else:
            self._send_json({"error": "not found"}, 404)

    def _handle_feed(self):
        """返回翻译后的条目列表，支持 ?since=timestamp 增量拉取"""
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(self.path).query)
        since = qs.get("since", [None])[0]
        limit = int(qs.get("limit", ["50"])[0])

        data = load_data()
        if since:
            data = [item for item in data if item.get("fetch_time", "") > since]
        data = data[:limit]
        self._send_json({"items": data, "total": len(data), "server_time": datetime.now(timezone.utc).isoformat()})

    def _handle_status(self):
        data = load_data()
        self._send_json({
            "status": "running",
            "total_cached": len(data),
            "latest_fetch": data[0]["fetch_time"] if data else None,
            "rss_source": RSS_URL,
        })

    def _handle_index(self):
        html = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Minecraft Wiki 翻译推送</title>
<style>
body{font-family:system-ui,sans-serif;max-width:800px;margin:0 auto;padding:20px;background:#1a1a2e;color:#e0e0e0}
h1{color:#5dade2}h2{color:#48c9b0;border-bottom:1px solid #333;padding-bottom:8px}
.item{background:#16213e;border-radius:8px;padding:16px;margin:12px 0;border-left:4px solid #5dade2}
.item .title{font-size:1.1em;font-weight:bold;color:#f0c040}
.item .meta{font-size:0.8em;color:#888;margin:4px 0}
.item .desc{font-size:0.9em;line-height:1.5;color:#ccc}
.item .link{color:#5dade2;text-decoration:none;font-size:0.85em}
.api-info{background:#0f3460;border-radius:8px;padding:16px;margin:20px 0;font-family:monospace;font-size:0.85em}
</style></head><body>
<h1>⛏ Minecraft Wiki 翻译推送服务</h1>
<div class="api-info">
<b>Android 客户端 API：</b><br>
GET /api/feed — 获取翻译条目<br>
GET /api/feed?since=2026-01-01T00:00:00 — 增量获取<br>
GET /api/feed?limit=20 — 限制数量<br>
GET /api/status — 服务状态
</div>
<h2>最新翻译</h2>
<div id="items">加载中...</div>
<script>
fetch('/api/feed?limit=30').then(r=>r.json()).then(d=>{
  let html='';
  d.items.forEach(i=>{
    html+=`<div class="item"><div class="title">${i.title_translated}</div>
    <div class="meta">原文: ${i.title_original} | 作者: ${i.author} | ${i.pub_date}</div>
    <div class="desc">${i.description_translated}</div>
    <a class="link" href="${i.link}" target="_blank">查看原文 →</a></div>`;
  });
  document.getElementById('items').innerHTML=html||'暂无数据';
});
</script></body></html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        logger.debug(f"HTTP: {args[0]}")


# ============ 定时任务 ============
class Scheduler:
    def __init__(self, interval_seconds: int, target):
        self.interval = interval_seconds
        self.target = target
        self.thread = None
        self.running = False

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        logger.info(f"定时任务已启动，间隔 {self.interval} 秒")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)

    def _loop(self):
        while self.running:
            try:
                self.target()
            except Exception as e:
                logger.error(f"定时任务执行出错: {e}")
            # 每小时执行一次
            for _ in range(self.interval):
                if not self.running:
                    break
                time.sleep(1)


# ============ 启动 ============
def main():
    # 首次启动立即抓取一次
    fetch_and_process_rss()

    # 启动每小时定时抓取
    scheduler = Scheduler(interval_seconds=3600, target=fetch_and_process_rss)
    scheduler.start()

    # 启动 HTTP 服务
    server = HTTPServer((SERVER_HOST, SERVER_PORT), WikiHandler)
    logger.info(f"HTTP 服务已启动: http://{SERVER_HOST}:{SERVER_PORT}")
    print(f"\n✅ 服务运行中!")
    print(f"   管理页面: http://localhost:{SERVER_PORT}")
    print(f"   API 地址: http://localhost:{SERVER_PORT}/api/feed")
    print(f"   每 60 分钟自动抓取并翻译\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("正在关闭服务...")
        scheduler.stop()
        server.server_close()


if __name__ == "__main__":
    main()