import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

class UserInfoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="userinfo", description="ユーザー情報を表示します")
    async def userinfo(self, interaction: discord.Interaction, user: discord.Member = None):
        user = user or interaction.user  # デフォルトは自分

        embed = discord.Embed(
            title=f"👤 ユーザー情報 - {user.display_name}",
            color=discord.Color.blurple(),
            timestamp=datetime.now()
        )
        embed.set_thumbnail(url=user.avatar.url if user.avatar else user.default_avatar.url)

        embed.add_field(name="ユーザー名", value=f"{user} (`{user.id}`)", inline=False)
        embed.add_field(name="サーバーニックネーム", value=user.display_name, inline=True)
        embed.add_field(name="アカウント作成日", value=user.created_at.strftime("%Y/%m/%d %H:%M:%S"), inline=True)
        embed.add_field(name="サーバー参加日", value=user.joined_at.strftime("%Y/%m/%d %H:%M:%S") if user.joined_at else "不明", inline=True)
        
        # ロール一覧
        roles = [role.mention for role in user.roles if role.name != "@everyone"]
        embed.add_field(name="ロール", value=", ".join(roles) if roles else "なし", inline=False)

        embed.set_footer(text=f"Requested by {interaction.user}", icon_url=interaction.user.avatar.url if interaction.user.avatar else None)

        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(UserInfoCog(bot))
