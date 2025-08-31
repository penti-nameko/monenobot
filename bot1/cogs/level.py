import discord
from discord.ext import commands
from discord import app_commands
import mysql.connector
import os
from datetime import datetime

class Level(commands.Cog):
    """XP・レベル管理＋通知チャンネル＋サーバー/グローバルランキング"""

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

    # メッセージ送信でXP付与
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        guild_id = message.guild.id
        user_id = message.author.id

        # 対象外チャンネル確認
        self.cursor.execute(
            "SELECT 1 FROM level_ignore_channels WHERE guild_id=%s AND channel_id=%s",
            (guild_id, message.channel.id)
        )
        if self.cursor.fetchone():
            return  # XP付与対象外

        # ユーザー情報取得
        self.cursor.execute(
            "SELECT xp, level, xp_per_message, notify_channel_id FROM user_levels WHERE guild_id=%s AND user_id=%s",
            (guild_id, user_id)
        )
        user_result = self.cursor.fetchone()

        if user_result:
            xp, level, xp_per_msg, notify_channel_id = user_result
            xp_per_msg = xp_per_msg or 10
            notify_channel_id = notify_channel_id
            xp += xp_per_msg
        else:
            xp = 10
            level = 1
            xp_per_msg = 10
            notify_channel_id = None
            self.cursor.execute(
                "INSERT INTO user_levels (guild_id, user_id, xp, level, xp_per_message, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (guild_id, user_id, xp, level, xp_per_msg, datetime.now())
            )
            self.conn.commit()

        # レベル計算
        new_level = int(xp ** (1/4))
        leveled_up = False
        if new_level > level:
            level = new_level
            leveled_up = True

            # レベルアップ通知
            if notify_channel_id:
                channel = message.guild.get_channel(notify_channel_id)
                if channel:
                    await channel.send(f"🎉 {message.author.mention} がレベル {level} に上がりました！")
            else:
                await message.channel.send(f"🎉 {message.author.mention} がレベル {level} に上がりました！")

            # レベル到達でロール付与
            self.cursor.execute(
                "SELECT role_id FROM level_roles WHERE guild_id=%s AND level=%s",
                (guild_id, level)
            )
            role_row = self.cursor.fetchone()
            if role_row:
                role_id = role_row[0]
                role = message.guild.get_role(role_id)
                if role:
                    await message.author.add_roles(role, reason=f"レベル {level} 到達による自動付与")

        # DB更新
        if leveled_up:
            self.cursor.execute(
                "UPDATE user_levels SET xp=%s, level=%s, updated_at=%s WHERE guild_id=%s AND user_id=%s",
                (xp, level, datetime.now(), guild_id, user_id)
            )
        else:
            self.cursor.execute(
                "UPDATE user_levels SET xp=%s, updated_at=%s WHERE guild_id=%s AND user_id=%s",
                (xp, datetime.now(), guild_id, user_id)
            )
        self.conn.commit()

    # 管理者向け：XP設定
    @app_commands.command(name="setxp", description="1メッセージあたりのXP量を設定")
    @app_commands.describe(xp="XPの値")
    @app_commands.checks.has_permissions(administrator=True)
    async def setxp(self, interaction: discord.Interaction, xp: int):
        self.cursor.execute(
            "UPDATE user_levels SET xp_per_message=%s WHERE guild_id=%s",
            (xp, interaction.guild.id)
        )
        self.conn.commit()
        await interaction.response.send_message(f"1メッセージあたりのXPを {xp} に設定しました。", ephemeral=True)

    # 管理者向け：通知チャンネル設定
    @app_commands.command(name="setnotify", description="レベルアップ通知チャンネルを設定")
    @app_commands.describe(channel="通知を送るチャンネル")
    @app_commands.checks.has_permissions(administrator=True)
    async def setnotify(self, interaction: discord.Interaction, channel: discord.TextChannel):
        self.cursor.execute(
            "UPDATE user_levels SET notify_channel_id=%s WHERE guild_id=%s",
            (channel.id, interaction.guild.id)
        )
        self.conn.commit()
        await interaction.response.send_message(f"レベルアップ通知チャンネルを {channel.mention} に設定しました。", ephemeral=True)

    # 管理者向け：XP付与対象外チャンネル設定
    @app_commands.command(name="ignore_channel", description="XP付与対象外チャンネルを追加")
    @app_commands.describe(channel="対象外にするチャンネル")
    @app_commands.checks.has_permissions(administrator=True)
    async def ignore_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        self.cursor.execute(
            "INSERT IGNORE INTO level_ignore_channels (guild_id, channel_id) VALUES (%s, %s)",
            (interaction.guild.id, channel.id)
        )
        self.conn.commit()
        await interaction.response.send_message(f"{channel.mention} をXP付与対象外に設定しました。", ephemeral=True)

    # サーバー内ランキング
    @app_commands.command(name="rank", description="サーバー内ランキングを表示")
    async def rank(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        self.cursor.execute(
            "SELECT user_id, level, xp FROM user_levels WHERE guild_id=%s ORDER BY level DESC, xp DESC LIMIT 10",
            (guild_id,)
        )
        top_users = self.cursor.fetchall()
        embed = discord.Embed(title="サーバー内ランキング", color=discord.Color.green())
        for i, (user_id, level, xp) in enumerate(top_users, 1):
            member = interaction.guild.get_member(user_id)
            name = member.display_name if member else str(user_id)
            embed.add_field(name=f"#{i} {name}", value=f"Level {level} / XP {xp}", inline=False)
        await interaction.response.send_message(embed=embed)

    # グローバルランキング
    @app_commands.command(name="rank_global", description="Bot導入サーバー全体のランキングを表示")
    async def rank_global(self, interaction: discord.Interaction):
        self.cursor.execute(
            "SELECT user_id, level, xp FROM user_levels ORDER BY level DESC, xp DESC LIMIT 10"
        )
        top_users = self.cursor.fetchall()
        embed = discord.Embed(title="グローバルランキング", color=discord.Color.gold())
        for i, (user_id, level, xp) in enumerate(top_users, 1):
            user = self.bot.get_user(user_id)
            name = user.name if user else str(user_id)
            embed.add_field(name=f"#{i} {name}", value=f"Level {level} / XP {xp}", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="reset_xp", description="サーバー内全ユーザーのXPをリセット")
    @app_commands.checks.has_permissions(administrator=True)
    async def reset_xp(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        self.cursor.execute(
            "UPDATE user_levels SET xp=0, level=1, updated_at=NOW() WHERE guild_id=%s",
            (guild_id,)
        )
        self.conn.commit()
        await interaction.response.send_message("サーバー内全ユーザーのXPとレベルをリセットしました。", ephemeral=True)

    @app_commands.command(name="reset_user_xp", description="特定ユーザーのXPをリセット")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(user="XPをリセットするユーザー")
    async def reset_user_xp(self, interaction: discord.Interaction, user: discord.Member):
        guild_id = interaction.guild.id
        user_id = user.id
        self.cursor.execute(
            "UPDATE user_levels SET xp=0, level=1, updated_at=NOW() WHERE guild_id=%s AND user_id=%s",
            (guild_id, user_id)
        )
        self.conn.commit()
        await interaction.response.send_message(f"{user.display_name} のXPとレベルをリセットしました。", ephemeral=True)


# CogをBotに追加するsetup関数
async def setup(bot: commands.Bot):
    await bot.add_cog(Level(bot))
