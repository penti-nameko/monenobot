import discord
from discord.ext import commands
from discord import app_commands

class Moderation(commands.Cog):
    """Kick / Ban 管理者用 Cog"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Kick コマンド
    @app_commands.command(name="kick", description="指定ユーザーをサーバーからキック")
    @app_commands.describe(user="キックするユーザー", reason="理由 (任意)")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, user: discord.Member, reason: str = None):
        try:
            await user.kick(reason=reason)
            await interaction.response.send_message(f"{user.mention} をキックしました。理由: {reason}", ephemeral=False)
        except discord.Forbidden:
            await interaction.response.send_message("権限が不足しています。", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"エラーが発生しました: {e}", ephemeral=True)

    # Ban コマンド
    @app_commands.command(name="ban", description="指定ユーザーをサーバーからBAN")
    @app_commands.describe(user="BANするユーザー", reason="理由 (任意)", delete_days="メッセージ削除日数(0-7)")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, user: discord.Member, reason: str = None, delete_days: int = 0):
        try:
            await user.ban(reason=reason, delete_message_days=delete_days)
            await interaction.response.send_message(f"{user.mention} をBANしました。理由: {reason}", ephemeral=False)
        except discord.Forbidden:
            await interaction.response.send_message("権限が不足しています。", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"エラーが発生しました: {e}", ephemeral=True)

# CogをBotに追加
async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
