import discord
from discord.ext import commands
from discord import app_commands
import mysql.connector
import os
from datetime import datetime

class Welcome(commands.Cog):
    """高度なWelcomeメッセージ管理Cog"""

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

    # メンバー参加時
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        self.cursor.execute(
            "SELECT channel_id, message, role_id FROM welcome_settings WHERE guild_id=%s AND deleted_at IS NULL",
            (member.guild.id,)
        )
        result = self.cursor.fetchone()
        if result:
            channel_id, message, role_id = result
            channel = member.guild.get_channel(channel_id)
            role = member.guild.get_role(role_id) if role_id else None
            if channel:
                # プレースホルダ置換
                msg = message.replace("{member}", member.mention)
                msg = msg.replace("{guild_name}", member.guild.name)
                msg = msg.replace("{count}", str(member.guild.member_count))
                if role:
                    msg = msg.replace("{stuff}", role.mention)
                else:
                    msg = msg.replace("{stuff}", "")
                await channel.send(msg)

                # DBに参加ログを記録
                self.cursor.execute(
                    "INSERT INTO welcome_logs (guild_id, member_id, joined_at, member_count) VALUES (%s, %s, %s, %s)",
                    (member.guild.id, member.id, datetime.now(), member.guild.member_count)
                )
                self.conn.commit()

    # Welcome登録
    @app_commands.command(name="setwelcome", description="Welcomeメッセージを設定")
    @app_commands.describe(channel="メッセージを送るチャンネル", message="Welcomeメッセージ", role="任意のロール")
    @app_commands.checks.has_permissions(administrator=True)
    async def setwelcome(self, interaction: discord.Interaction, channel: discord.TextChannel, message: str, role: discord.Role = None):
        # 既存のWelcomeを無効化
        self.cursor.execute(
            "UPDATE welcome_settings SET deleted_at=%s WHERE guild_id=%s AND deleted_at IS NULL",
            (datetime.now(), interaction.guild.id)
        )
        self.conn.commit()

        role_id = role.id if role else None
        # 新規登録
        self.cursor.execute(
            "INSERT INTO welcome_settings (guild_id, channel_id, message, role_id, created_at) VALUES (%s, %s, %s, %s, %s)",
            (interaction.guild.id, channel.id, message, role_id, datetime.now())
        )
        self.conn.commit()

        await interaction.response.send_message(f"{channel.mention} に Welcomeメッセージを設定しました。", ephemeral=True)

    # Welcome削除
    @app_commands.command(name="delwelcome", description="Welcomeメッセージを削除")
    @app_commands.checks.has_permissions(administrator=True)
    async def delwelcome(self, interaction: discord.Interaction):
        self.cursor.execute(
            "UPDATE welcome_settings SET deleted_at=%s WHERE guild_id=%s AND deleted_at IS NULL",
            (datetime.now(), interaction.guild.id)
        )
        self.conn.commit()
        await interaction.response.send_message("Welcomeメッセージを削除しました。", ephemeral=True)

# CogをBotに追加するsetup関数
async def setup(bot: commands.Bot):
    await bot.add_cog(Welcome(bot))
