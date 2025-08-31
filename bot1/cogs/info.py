import discord
from discord.ext import commands, tasks
from discord import app_commands
import psutil
import platform
import asyncio
import time

class Info(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.start_time = time.time()  # ← Bot起動時間を記録
        self.update_status.start()

    def cog_unload(self):
        self.update_status.cancel()

    # /info コマンド
    @app_commands.command(name="info", description="Botの情報を表示します")
    async def info(self, interaction: discord.Interaction):
        cpu = psutil.cpu_percent(interval=0.5)
        memory = psutil.virtual_memory().percent
        uptime = self.get_bot_uptime()

        embed = discord.Embed(title="🤖 Bot情報", color=discord.Color.blue())
        embed.add_field(name="サーバー数", value=f"{len(self.bot.guilds)}", inline=True)
        embed.add_field(name="ユーザー数", value=f"{len(self.bot.users)}", inline=True)
        embed.add_field(name="CPU使用率", value=f"{cpu}%", inline=True)
        embed.add_field(name="メモリ使用率", value=f"{memory}%", inline=True)
        embed.add_field(name="稼働時間", value=uptime, inline=False)
        embed.add_field(name="Python", value=platform.python_version(), inline=True)
        embed.add_field(name="discord.py", value=discord.__version__, inline=True)

        await interaction.response.send_message(embed=embed)

    # ステータスを定期的に更新
    @tasks.loop(minutes=1)
    async def update_status(self):
        servers = len(self.bot.guilds)
        users = len(self.bot.users)
        cpu = psutil.cpu_percent(interval=0.5)

        statuses = [
            discord.Game(f"{servers} サーバーに導入中"),
            discord.Game(f"{users} ユーザー監視中"),
            discord.Game(f"CPU {cpu}%使用中"),
        ]

        for status in statuses:
            await self.bot.change_presence(activity=status)
            await asyncio.sleep(20)  # 20秒ごとに切り替え

    @update_status.before_loop
    async def before_update_status(self):
        await self.bot.wait_until_ready()

    def get_bot_uptime(self):
        uptime_seconds = int(time.time() - self.start_time)
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}時間 {minutes}分 {seconds}秒"

async def setup(bot: commands.Bot):
    await bot.add_cog(Info(bot))
