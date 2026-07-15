# ARPT-Bot-New

基于 Telethon + Docker Compose 的 Telegram 下载机器人。复刻 [ARPT-Bot](https://github.com/666wcy/ARPT-Bot) 核心功能，采用多容器架构重写。

## 功能

| 命令 | 说明 |
|------|------|
| `/mirror <URL>` | 直链 → Aria2 下载 → Rclone 上传网盘 |
| `/mirrortg <URL>` | 直链 → Aria2 下载 → 发送到 Telegram |
| `/magnet <链接>` | 磁力链接下载并上传 |
| `/tgdown` | 发送/转发 TG 文件，下载并上传网盘 |
| `/list` | 查看下载列表 |
| `/cancel <gid>` | 取消下载 |
| `/rclonecopy <src> <dst>` | 远程盘间复制 |
| `/rclonelsd [路径]` | 列出远程目录 |
| `/rclonels [路径]` | 列出远程文件 |
| `/rclonecopyurl <URL>` | 直链上传（不走本地） |
| `/start` | 查看 Bot 状态 |
| `/help` | 帮助 |

**特性：**
- 实时下载/上传进度条，大文件不误判
- 磁力链接和 .torrent 文件自动识别
- 上传完成后自动清理本地文件
- 行内按钮（暂停/取消）
- AriaNg Web 管理面板

## 架构

```
                    Telegram
                        │
                    ┌───▼───┐
                    │  bot   │  Telethon 异步 Bot (Python 3.12)
                    └─┬─┬─┬─┘
           ┌──────────┘ │ └──────────┐
    ┌──────▼──────┐ ┌───▼───┐ ┌──────▼──────┐
    │    aria2    │ │ rclone│ │ AriaNg Web  │
    │  下载引擎    │ │ 上传   │ │  管理面板    │
    │  (p3terx)   │ │(official)│ │   :8080    │
    └──────┬──────┘ └───┬───┘ └──────────────┘
           └──────┬─────┘
              ┌───▼───────┐
              │ /downloads │  共享 Volume
              └───────────┘
```

## 快速部署

### 前提

- Docker & Docker Compose v2
- Telegram API 凭证（[my.telegram.org](https://my.telegram.org)）
- Bot Token（[@BotFather](https://t.me/BotFather)）
- rclone 配置文件

### 步骤

```bash
# 1. 克隆
git clone https://github.com/nrxbo/arpt-bot-new.git
cd arpt-bot-new

# 2. 配置
cp .env.example .env
# 编辑 .env 填入你的凭证
# 将 rclone.conf 放入 ./rclone/ 目录

# 3. 启动
docker compose up -d

# 4. 访问 AriaNg
# http://localhost:8080
```

### 环境变量

| 变量 | 必需 | 说明 |
|------|------|------|
| `API_ID` | ✅ | Telegram API ID |
| `API_HASH` | ✅ | Telegram API Hash |
| `BOT_TOKEN` | ✅ | Bot Token |
| `OWNER_ID` | ✅ | 授权用户或群组 ID |
| `ARIA2_SECRET` | ✅ | Aria2 RPC 密钥 |
| `RCLONE_REMOTE` | ✅ | rclone 远程盘符 |
| `RCLONE_UPLOAD_DIR` | | 上传目标文件夹 |
| `RCLONE_SHARE` | | 上传后返回 OneDrive 分享链接 |
| `ARIA2_WEB_PORT` | | AriaNg 端口（默认 8080） |
| `ERROR_USER_INFO` | | 未授权用户提示 |

### 运维

```bash
docker compose logs -f bot     # 实时日志
docker compose restart bot     # 重启 Bot（代码改动后）
docker compose down            # 停止全部
```

## 技术栈

| 组件 | 技术 |
|------|------|
| Bot 框架 | [Telethon](https://github.com/LonamiWebs/Telethon) 1.44 |
| 下载引擎 | [Aria2](https://github.com/aria2/aria2) + [p3terx/aria2-pro](https://github.com/P3TERX/Aria2-Pro-Docker) |
| 云存储 | [Rclone](https://github.com/rclone/rclone) RC API |
| 反向代理 | Docker Compose 内部网络 |
| 语言 | Python 3.12 + asyncio |
| 容器化 | Docker Compose v2（4 容器） |

## TODO

- [ ] Pixiv 画师/排行榜下载
- [ ] YouTube/Bilibili 视频下载（yt-dlp）
- [ ] 网易云音乐下载
- [ ] nhentai/e-hentai/哔咔 本子搜索下载
- [ ] saucenao/ascii2d/WhatAnime 识图
- [ ] OneDrive/SharePoint 分享链接下载
- [ ] RcloneNg Web 面板
- [ ] RSS 自动下载
- [ ] 多用户/群组白名单

## 致谢

原项目 [666wcy/ARPT-Bot](https://github.com/666wcy/ARPT-Bot) 是功能丰富的 Telegram 下载机器人，本项目是对其核心功能的 Docker 化复刻。

## License

MIT
