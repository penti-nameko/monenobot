import discord
from discord.ext import commands
from discord import app_commands
import mysql.connector
import os
from datetime import datetime
from typing import Optional

class Leave(commands.Cog):
    """高度なLeaveメッセージ管理Cog（/ と prefix 両対応）"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.conn = mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
            port=int(os.getenv("DB_PORT", 3306))
        )
        self.cursor = self.conn.cursor()

    # -----------------------------
    # 退出時の送信（共通処理）
    # -----------------------------
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        self.cursor.execute(
            "SELECT channel_id, message FROM leave_settings WHERE guild_id=%s AND deleted_at IS NULL",
            (member.guild.id,)
        )
        result = self.cursor.fetchone()
        if not result:
            return

        channel_id, message = result
        channel = member.guild.get_channel(channel_id)
        if not channel:
            return

        # プレースホルダ置換
        msg = (message or "")
        msg = msg.replace("{member}", member.mention)
        msg = msg.replace("{guild_name}", member.guild.name)
        msg = msg.replace("{count}", str(member.guild.member_count))
        # 退出メッセージにはロールメンションは不要なため、{stuff}の置換は削除

        await channel.send(msg)

        # 退出ログ
        self.cursor.execute(
            "INSERT INTO leave_logs (guild_id, member_id, left_at, member_count) VALUES (%s, %s, %s, %s)",
            (member.guild.id, member.id, datetime.now(), member.guild.member_count)
        )
        self.conn.commit()

    # -----------------------------
    # 内部: 設定の保存（共通化）
    # -----------------------------
    def _save_leave(self, guild_id: int, channel_id: int, message: str):
        # 既存有効設定を無効化
        self.cursor.execute(
            "UPDATE leave_settings SET deleted_at=%s WHERE guild_id=%s AND deleted_at IS NULL",
            (datetime.now(), guild_id)
        )
        self.conn.commit()
        # 新規作成
        self.cursor.execute(
            "INSERT INTO leave_settings (guild_id, channel_id, message, created_at) VALUES (%s, %s, %s, %s)",
            (guild_id, channel_id, message, datetime.now())
        )
        self.conn.commit()

    # -----------------------------
    # /setleave（スラッシュ）
    # -----------------------------
    @app_commands.command(
        name="setleave",
        description="Leaveメッセージを設定。{member} {guild_name} {count} が使えます"
    )
    @app_commands.describe(
        channel="メッセージを送るチャンネル",
        message="Leaveメッセージ（プレースホルダ対応）"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setleave(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str):
        self._save_leave(interaction.guild.id, channel.id, message)
        await interaction.response.send_message(f"{channel.mention} に Leaveメッセージを設定しました。", ephemeral=True)

    # -----------------------------
    # mo!setleave（プレフィックス）
    # 使い方: mo!setleave #チャンネル メッセージ...
    # -----------------------------
    @commands.command(name="setleave")
    @commands.has_permissions(administrator=True)
    async def setleave_prefix(self, ctx: commands.Context, channel: discord.TextChannel, *, message: str = ""):
        if not message:
            return await ctx.send("使い方: `mo!setleave #チャンネル メッセージ...`\n例: `mo!setleave #general {member} さんが去りました`")
        self._save_leave(ctx.guild.id, channel.id, message)
        await ctx.send(f"{channel.mention} に Leaveメッセージを設定しました。")

    # -----------------------------
    # /delleave（スラッシュ）
    # -----------------------------
    @app_commands.command(name="delleave", description="Leaveメッセージを削除")
    @app_commands.checks.has_permissions(administrator=True)
    async def delleave(self, interaction: discord.Interaction):
        self.cursor.execute(
            "UPDATE leave_settings SET deleted_at=%s WHERE guild_id=%s AND deleted_at IS NULL",
            (datetime.now(), interaction.guild.id)
        )
        self.conn.commit()
        await interaction.response.send_message("Leaveメッセージを削除しました。", ephemeral=True)

    # -----------------------------
    # mo!delleave（プレフィックス）
    # -----------------------------
    @commands.command(name="delleave")
    @commands.has_permissions(administrator=True)
    async def delleave_prefix(self, ctx: commands.Context):
        self.cursor.execute(
            "UPDATE leave_settings SET deleted_at=%s WHERE guild_id=%s AND deleted_at IS NULL",
            (datetime.now(), ctx.guild.id)
        )
        self.conn.commit()
        await ctx.send("Leaveメッセージを削除しました。")

async def setup(bot: commands.Bot):
    await bot.add_cog(Leave(bot))
