# 通过 Watchtower 实现自动更新
1. 下载配置了 Watchtower 的 docker-compose.yml
```bash
wget wget https://raw.githubusercontent.com/Hamster-Prime/Telegram_Anti-harassment_two-way_chatbot/main/watchtower/docker-compose.yml
```
2. 编辑 docker-compose.yml 文件，填入您的配置
```bash
nano docker-compose.yml
```

# 通过 Telegram 告知是否完成更新（可选）

### 如何获取 BOT_TOKEN 和 CHAT_ID？

- BOT_TOKEN  
用 BotFather 创建 bot 后收到的 Token，如：
```json
123456789:ABCDEF_xxxxx-yyyy
```

- CHAT_ID  
给你的 Bot 发一条消息，然后访问：
```bash
https://api.telegram.org/bot<BOT_TOKEN>/getUpdates
```
- 在里面能看到：
```json
"chat": {"id": 12345678}
```
这就是你的 CHAT_ID。

正确格式：
```json
WATCHTOWER_NOTIFICATION_URL=telegram://123456789:ABCDEF_xxxxx-yyyy@telegram/?channels=12345678
```

# 配置解析
> - `WATCHTOWER_NOTIFICATIONS=shoutrrr`: Watchtower 使用 shoutrrr 作为统一通知系统。
> - `WATCHTOWER_NOTIFICATION_URL`: Watchtower 通过 Telegram 进行通知
> - `--cleanup`:更新容器镜像并重启容器成功后,自动删除旧镜像
> - `--interval 3600`: 每隔 3600 秒（1 小时）检查一次镜像是否有更新。
> - `TG-Antiharassment-Bot`: 容器名，如果自定义过，记得修改。
> - `max-size`： 单个日志文件最大 10MB
> - `max-file`： 最多保留 3 个日志文件