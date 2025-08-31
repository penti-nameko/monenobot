# cogs/ticket.py
import discord
from discord.ext import commands
from discord import app_commands

# --- チケット作成ボタン用View ---
class TicketView(discord.ui.View):
    def __init__(self, role: discord.Role = None, title: str = "サポートチケット"):
        super().__init__(timeout=None)  # 永続化
        self.role = role
        self.title = title

    @discord.ui.button(label="🎫 チケットを作成", style=discord.ButtonStyle.green, custom_id="create_ticket_button")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user

        # 権限設定
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
        }

        # サポートロールが指定されている場合
        if self.role:
            overwrites[self.role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        # チャンネル作成
        ticket_channel = await guild.create_text_channel(
            name=f"{self.title}-{user.name}",
            overwrites=overwrites,
            category=None  # 必要ならカテゴリIDを指定
        )

        # role にメンションを付与してメッセージ送信
        mention_text = self.role.mention if self.role else ""
        await ticket_channel.send(
            content=f"{user.mention} さんのチケットが作成されました！ {mention_text}\n管理者が対応するまでお待ちください。",
            view=CloseTicketView()
        )

        # ユーザーへの返信（ephemeral）
        await interaction.response.send_message(
            f"✅ チケットを作成しました: {ticket_channel.mention}",
            ephemeral=True
        )

# --- チケット閉鎖ボタン用View ---
class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 チケットを閉じる", style=discord.ButtonStyle.red, custom_id="close_ticket_button")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("⏳ チケットを削除します...", ephemeral=True)
        await interaction.channel.delete()

# --- Cog ---
class TicketCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # 永続View登録
        self.bot.add_view(TicketView())
        self.bot.add_view(CloseTicketView())

    @app_commands.command(name="ticketpanel", description="チケット作成パネルを設置します（管理者専用）")
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_panel(
        self, interaction: discord.Interaction, role: discord.Role = None, title: str = "サポートチケット"
    ):
        """管理者がチケットパネルを設置する"""
        view = TicketView(role=role, title=title)
        embed = discord.Embed(
            title="🎫 サポートチケット",
            description="下のボタンを押すとチケットが作成されます。",
            color=discord.Color.green()
        )
        await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("✅ チケットパネルを設置しました。", ephemeral=True)

# --- setup ---
async def setup(bot: commands.Bot):
    await bot.add_cog(TicketCog(bot))
