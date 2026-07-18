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


# ============ HTML/Diff 智能清理 ============
def clean_html(html_text: str) -> str:
    """
    智能清理 Wiki diff HTML，提取可翻译的有意义内容。
    拦截策略：
    1. 删除整个 diff 表格（太复杂，翻译无意义）
    2. 提取纯文本变更摘要（+/- 行）
    3. 过滤 MediaWiki 模板标记
    4. 保留简短的可读变更说明
    """
    text = unescape(html_text)

    # 1. 删除 diff 表格（最大噪音源）
    text = re.sub(r"<table.*?</table>", "", text, flags=re.DOTALL)

    # 2. 提取 <p> 标签中的简短说明（通常是编辑摘要）
    p_texts = re.findall(r"<p>(.*?)</p>", text, re.DOTALL)
    summary_parts = []
    for p in p_texts:
        p_clean = re.sub(r"<[^>]+>", "", p).strip()
        if p_clean and len(p_clean) > 2:
            summary_parts.append(p_clean)

    # 3. 去掉所有 HTML 标签
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # 4. 过滤 MediaWiki 模板/标记噪音
    noise_patterns = [
        r"\{\{subst:[^}]*\}\}",
        r"\{\{[^}]*\}\}",
        r"\[\[File:[^\]]*\]\]",
        r"\[\[Image:[^\]]*\]\]",
        r"\[\[wikipedia:[^\]]*\]\]",
        r"<!--.*?-->",
        r"Revision as of .*?\|",
        r"Older revision",
        r"New page",
        r"Created page with",
        r"\(undo\)",
        r"data-mw=\"[^\"]*\"",
        r"class=\"[^\"]*\"",
        r"style=\"[^\"]*\"",
    ]
    for pat in noise_patterns:
        text = re.sub(pat, "", text, flags=re.DOTALL | re.IGNORECASE)

    text = re.sub(r"\s+", " ", text).strip()

    # 5. 如果提取到了 <p> 摘要，优先使用（通常更短更准）
    if summary_parts:
        summary = " | ".join(summary_parts)
        # 截断过长摘要
        if len(summary) > 300:
            summary = summary[:300] + "..."
        return summary

    # 6. 没有摘要时，取清理后文本的前 300 字符
    if not text or len(text) < 5:
        return "(无详细描述，请查看原文)"

    if len(text) > 300:
        text = text[:300] + "..."
    return text


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
        clean_desc = clean_html(desc_raw)
        logger.info(f"翻译: {title}")
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