import discord
from discord.ext import commands
from discord import app_commands

class VcMove(commands.Cog):
    """VCにいるメンバーを一括移動するコグ"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -----------------------------
    # /vcmove（スラッシュ）
    # -----------------------------
    @app_commands.command(
        name="vcmove",
        description="指定したVCのメンバーを別のVCに一括移動します。"
    )
    @app_commands.describe(
        source_channel="移動元のVC",
        destination_channel="移動先のVC"
    )
    @app_commands.checks.has_permissions(move_members=True)
    async def vcmove(self, interaction: discord.Interaction, source_channel: discord.VoiceChannel, destination_channel: discord.VoiceChannel):
        """
        指定したVCのメンバーを別のVCに一括移動します。
        
        Args:
            interaction: Discordとのやり取りを表すInteractionオブジェクト。
            source_channel: 移動元のVoiceChannel。
            destination_channel: 移動先のVoiceChannel。
        """
        if not source_channel.members:
            await interaction.response.send_message("移動元のVCにメンバーがいません。", ephemeral=True)
            return

        moved_members = []
        # 移動元のメンバーを順番に移動
        for member in source_channel.members:
            try:
                await member.move_to(destination_channel)
                moved_members.append(member.display_name)
            except discord.Forbidden:
                await interaction.response.send_message("権限がないためメンバーを移動できません。", ephemeral=True)
                return
            except discord.HTTPException as e:
                await interaction.response.send_message(f"メンバーの移動中にエラーが発生しました: {e}", ephemeral=True)
                return

        moved_count = len(moved_members)
        if moved_count > 0:
            members_list = ", ".join(moved_members)
            embed = discord.Embed(
                title="メンバー一括移動完了",
                description=f"✅ {moved_count}名のメンバーを移動しました。",
                color=discord.Color.green()
            )
            embed.add_field(name="移動元VC", value=source_channel.mention, inline=False)
            embed.add_field(name="移動先VC", value=destination_channel.mention, inline=False)
            embed.add_field(name="移動したメンバー", value=members_list, inline=False)
            
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("メンバーを移動できませんでした。", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(VcMove(bot))
