"""
Minecraft Wiki RSS 翻译推送服务 - 后端 v2
功能：抓取 Fandom Minecraft Wiki RSS → 保留原始 HTML → 按需翻译 → HTTP API
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
from urllib.parse import urlencode, urlparse, parse_qs
from html import unescape
import threading

# ============ 配置 ============
RSS_URL = "https://minecraft.fandom.com/api.php?action=feedrecentchanges&feedformat=rss"
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "translated_items.json")
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8765
MAX_CACHE_ITEMS = 200

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("mcwiki")


# ============ MC 专有名词保护 ============
MC_TERMS = {
    "Block": "§BLOCK§", "blocks": "§BLOCKS§", "Blocks": "§BLOCKS§",
    "Creeper": "§CREEPER§", "Zombie": "§ZOMBIE§", "Skeleton": "§SKELETON§",
    "Enderman": "§ENDERMAN§", "Blaze": "§BLAZE§", "Ghast": "§GHAST§",
    "Villager": "§VILLAGER§", "Iron Golem": "§IRON_GOLEM§",
    "Wither": "§WITHER§", "Ender Dragon": "§ENDER_DRAGON§",
    "Warden": "§WARDEN§", "Allay": "§ALLAY§",
    "Copper": "§COPPER§", "copper": "§COPPER§",
    "Redstone": "§REDSTONE§", "redstone": "§REDSTONE§",
    "Netherite": "§NETHERITE§", "netherite": "§NETHERITE§",
    "Diamond": "§DIAMOND§", "diamond": "§DIAMOND§",
    "Emerald": "§EMERALD§", "Obsidian": "§OBSIDIAN§",
    "Bedrock": "§BEDROCK§", "Cobblestone": "§COBBLESTONE§",
    "Sandstone": "§SANDSTONE§", "Stairs": "§STAIRS§", "stairs": "§STAIRS§",
    "Nether": "§NETHER§", "The End": "§THE_END§",
    "Overworld": "§OVERWORLD§",
    "Minecraft": "§MC§", "Java Edition": "§JAVA_ED§", "Bedrock Edition": "§BEDROCK_ED§",
    "Bukkit": "§BUKKIT§", "Spigot": "§SPIGOT§", "Fabric": "§FABRIC§", "Forge": "§FORGE§",
    "waxed": "§WAXED§",
}
_MC_RESTORE = {v: k for k, v in MC_TERMS.items()}


def _protect_terms(text):
    for en, ph in sorted(MC_TERMS.items(), key=lambda x: -len(x[0])):
        text = re.sub(re.escape(en), ph, text)
    return text


def _restore_terms(text):
    for ph, en in _MC_RESTORE.items():
        text = text.replace(ph, en)
    return text


# ============ MediaWiki 链接清理（用于纯文本摘要） ============
def _clean_wikilinks(text):
    text = re.sub(r"\[\[(?:File|Image|wikipedia):[^\]]*\]\]", "", text)
    text = re.sub(r"\[\[[^|\]]+\|([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    return text


def _html_to_text(html):
    """HTML 转纯文本（用于摘要预览）"""
    text = unescape(html)
    text = re.sub(r"<table.*?</table>", " [差异表格] ", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = _clean_wikilinks(text)
    text = re.sub(r"\{\{[^}]*\}\}", "", text)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:200] + "..." if len(text) > 200 else text


# ============ 翻译引擎 ============
_translate_use_fallback = False


def _translate_google(text):
    from deep_translator import GoogleTranslator
    return GoogleTranslator(source="en", target="zh-CN").translate(text) or text


def _translate_mymemory(text):
    url = f"https://api.mymemory.translated.net/get?{urlencode({'q': text[:500], 'langpair': 'en|zh-CN'})}"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["responseData"]["translatedText"]


def translate_text(text):
    """按需翻译：MC 名词保护 + 多引擎降级"""
    global _translate_use_fallback
    if not text or not text.strip():
        return text
    if len(text) > 3000:
        text = text[:3000] + "...(已截断)"
    text = _protect_terms(text)
    try:
        result = _translate_google(text) if not _translate_use_fallback else _translate_mymemory(text)
        return _restore_terms(result) if result else _restore_terms(text)
    except Exception as e:
        logger.warning(f"翻译失败: {e}")
        if not _translate_use_fallback:
            _translate_use_fallback = True
            logger.info("切换到 MyMemory 备用引擎")
            try:
                return _restore_terms(_translate_mymemory(text))
            except Exception:
                pass
        return _restore_terms(text) + " [翻译失败]"


# ============ RSS 抓取（保留原始数据） ============
def fetch_and_process_rss():
    logger.info("抓取 Minecraft Wiki RSS...")
    try:
        req = Request(RSS_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=20) as resp:
            xml_data = resp.read().decode("utf-8")
    except Exception as e:
        logger.error(f"抓取失败: {e}")
        return []

    root = ET.fromstring(xml_data)
    channel = root.find("channel")
    items = channel.findall("item")

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

        item_hash = hashlib.md5(f"{title}:{link}".encode()).hexdigest()[:12]
        if item_hash in existing_hashes:
            continue

        # 保留原始 HTML，同时生成纯文本预览
        entry = {
            "hash": item_hash,
            "title": title,
            "title_translated": None,  # 按需翻译，初始为空
            "description_html": desc_raw,  # 完整原始 HTML，供 WebView 渲染
            "description_preview": _html_to_text(desc_raw),  # 纯文本预览
            "description_translated": None,  # 按需翻译
            "link": link,
            "author": creator,
            "pub_date": pub_date,
            "fetch_time": datetime.now(timezone.utc).isoformat(),
        }
        new_items.append(entry)
        logger.info(f"新增: {title}")

    if new_items:
        existing = (new_items + existing)[:MAX_CACHE_ITEMS]
        save_data(existing)
        logger.info(f"新增 {len(new_items)} 条")
    else:
        logger.info("无新条目")
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


def find_item(hash_id):
    for item in load_data():
        if item.get("hash") == hash_id:
            return item
    return None


def update_item(hash_id, updates):
    data = load_data()
    for item in data:
        if item.get("hash") == hash_id:
            item.update(updates)
            save_data(data)
            return item
    return None


# ============ HTTP API ============
class WikiHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/" or path == "":
            self._handle_index()
        elif path == "/api/feed":
            self._handle_feed(qs)
        elif path == "/api/item":
            self._handle_item(qs)
        elif path == "/api/status":
            self._handle_status()
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/translate":
            self._handle_translate()
        else:
            self._send_json({"error": "not found"}, 404)

    def _handle_feed(self, qs):
        """列表 API：返回轻量摘要（不含完整 HTML）"""
        since = qs.get("since", [None])[0]
        limit = int(qs.get("limit", ["50"])[0])
        data = load_data()
        if since:
            data = [i for i in data if i.get("fetch_time", "") > since]
        # 列表只返回预览，不含完整 HTML
        light = [{
            "hash": i["hash"],
            "title": i["title"],
            "title_translated": i.get("title_translated"),
            "preview": i.get("description_preview", ""),
            "author": i.get("author", ""),
            "pub_date": i.get("pub_date", ""),
            "fetch_time": i.get("fetch_time", ""),
            "link": i.get("link", ""),
        } for i in data[:limit]]
        self._send_json({"items": light, "total": len(light),
                         "server_time": datetime.now(timezone.utc).isoformat()})

    def _handle_item(self, qs):
        """详情 API：返回完整 HTML，按需翻译"""
        hash_id = qs.get("hash", [None])[0]
        if not hash_id:
            self._send_json({"error": "missing hash"}, 400)
            return
        item = find_item(hash_id)
        if not item:
            self._send_json({"error": "not found"}, 404)
            return
        self._send_json(item)

    def _handle_translate(self):
        """按需翻译 API：POST {hash, field} 或 {text}"""
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

        # 模式1：翻译指定条目的指定字段
        if "hash" in body:
            item = find_item(body["hash"])
            if not item:
                self._send_json({"error": "item not found"}, 404)
                return
            field = body.get("field", "title")  # title 或 description
            if field == "title":
                if not item.get("title_translated"):
                    item["title_translated"] = translate_text(item["title"])
                    update_item(body["hash"], {"title_translated": item["title_translated"]})
                self._send_json({"translated": item["title_translated"]})
            else:  # description
                if not item.get("description_translated"):
                    # 翻译纯文本版本，不翻译 HTML
                    preview = item.get("description_preview", "")
                    item["description_translated"] = translate_text(preview)
                    update_item(body["hash"], {"description_translated": item["description_translated"]})
                self._send_json({"translated": item["description_translated"]})
            return

        # 模式2：直接翻译任意文本
        text = body.get("text", "")
        self._send_json({"translated": translate_text(text)})

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
h1{color:#5dade2}.api{background:#0f3460;border-radius:8px;padding:16px;margin:20px 0;font-family:monospace;font-size:0.85em}
.item{background:#16213e;border-radius:8px;padding:14px;margin:10px 0;border-left:4px solid #5dade2;cursor:pointer}
.item:hover{background:#1a2845}
.title{font-weight:bold;color:#f0c040}.meta{font-size:0.8em;color:#888;margin:4px 0}
.preview{font-size:0.9em;color:#ccc}
</style></head><body>
<h1>⛏ Minecraft Wiki 翻译推送 v2</h1>
<div class="api">
GET /api/feed — 条目列表（轻量）<br>
GET /api/item?hash=xxx — 条目详情（含完整 HTML）<br>
POST /api/translate — 按需翻译 {hash, field} 或 {text}<br>
GET /api/status — 服务状态
</div>
<h2>最新条目</h2>
<div id="list">加载中...</div>
<script>
fetch('/api/feed?limit=30').then(r=>r.json()).then(d=>{
  document.getElementById('list').innerHTML=d.items.map(i=>
    `<div class="item" onclick="location.href='${i.link}'">
      <div class="title">${i.title_translated||i.title}</div>
      <div class="meta">${i.author} | ${i.pub_date}</div>
      <div class="preview">${i.preview}</div>
    </div>`).join('')||'暂无数据';
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
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send_json({"ok": True})

    def log_message(self, format, *args):
        logger.debug(f"HTTP: {args[0]}")


# ============ 定时任务 ============
class Scheduler:
    def __init__(self, interval_seconds, target):
        self.interval = interval_seconds
        self.target = target
        self.thread = None
        self.running = False

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        logger.info(f"定时任务启动，间隔 {self.interval} 秒")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)

    def _loop(self):
        while self.running:
            try:
                self.target()
            except Exception as e:
                logger.error(f"定时任务出错: {e}")
            for _ in range(self.interval):
                if not self.running:
                    break
                time.sleep(1)


def main():
    fetch_and_process_rss()
    scheduler = Scheduler(3600, fetch_and_process_rss)
    scheduler.start()
    server = HTTPServer((SERVER_HOST, SERVER_PORT), WikiHandler)
    logger.info(f"HTTP 服务启动: http://{SERVER_HOST}:{SERVER_PORT}")
    print(f"\n✅ 服务运行中!")
    print(f"   管理页面: http://localhost:{SERVER_PORT}")
    print(f"   列表 API: http://localhost:{SERVER_PORT}/api/feed")
    print(f"   详情 API: http://localhost:{SERVER_PORT}/api/item?hash=xxx")
    print(f"   翻译 API: POST http://localhost:{SERVER_PORT}/api/translate")
    print(f"   每 60 分钟自动抓取\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        scheduler.stop()
        server.server_close()


if __name__ == "__main__":
    main()