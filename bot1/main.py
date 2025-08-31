import discord
from discord.ext import commands, tasks
import traceback
import os
import asyncio
from dotenv import load_dotenv
import requests
import datetime
import signal
import sys

FASTAPI_URL = "http://127.0.0.1:8000/api/bot_status"
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

BOT_NAME = "咲萌音botテスト2"  # このBotの名前を設定

DiscordBot_Cogs = [
    'cogs.welcome',
    'cogs.leave',
    'cogs.level',
    'cogs.membermod',
    'cogs.info',
    'cogs.dice',
    'cogs.userinfo',
    'cogs.ticket',
    'cogs.vcmove',
    'cogs.pins',
    'cogs.rolepanels',
    'cogs.tempvoice',
    'cogs.economy'
]

def send_bot_status(running=True):
    """Bot の稼働状況を FastAPI に送信"""
    data = {
        "name": BOT_NAME,
        "running": running,
        "timestamp": datetime.datetime.now().isoformat()
    }
    try:
        requests.post(FASTAPI_URL, json=data, timeout=3)
    except Exception:
        pass

class MyBot(commands.Bot):
    def __init__(self, command_prefix):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(command_prefix=command_prefix, intents=intents)
        self.heartbeat_task = self.heartbeat_loop.start()  # 心拍ループ開始

    async def setup_hook(self):
        # Cogs をロード
        for cog in DiscordBot_Cogs:
            try:
                await self.load_extension(cog)
                print(f"✅ {cog} をロードしました")
            except Exception:
                traceback.print_exc()

        # スラッシュコマンド同期
        try:
            synced = await self.tree.sync()
            print(f"🌐 スラッシュコマンド同期: {len(synced)} 件")
        except Exception as e:
            print(f"❌ スラッシュコマンド同期失敗: {e}")

    async def on_ready(self):
        print(f"BOT起動: {self.user}")
        send_bot_status(True)  # 起動直後に通知

    # 非同期で心拍を送るタスク
    @tasks.loop(seconds=5)
    async def heartbeat_loop(self):
        send_bot_status(True)

# 安全終了処理
def shutdown_handler(bot: MyBot):
    print("Botを停止中...")
    send_bot_status(False)  # 停止状態を通知
    asyncio.create_task(bot.close())

async def main():
    bot = MyBot(command_prefix="/")

    # シグナル登録
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: shutdown_handler(bot))

    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
