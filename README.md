# Minecraft Wiki 翻译推送

自动抓取 Fandom Minecraft Wiki RSS 更新，通过 Google Translate 翻译为中文，推送至 Android 客户端。

## 架构

```
Fandom Wiki RSS → Python 后端(翻译+API) → Android 客户端(通知+展示)
```

## 后端部署

```bash
cd server
pip install -r requirements.txt
python3 server.py
# 服务运行在 http://0.0.0.0:8765
```

### systemd 常驻

```bash
sudo cp mcwiki-translator.service /etc/systemd/system/
sudo systemctl enable --now mcwiki-translator
```

## Android 客户端

用 Android Studio 打开 `android/` 目录构建。在 App 中填入服务器地址并开启监控即可。

## API

| 接口 | 说明 |
|------|------|
| `GET /api/feed` | 获取翻译条目 |
| `GET /api/feed?since=ISO时间` | 增量获取 |
| `GET /api/feed?limit=N` | 限制数量 |
| `GET /api/status` | 服务状态 |

## License

MIT