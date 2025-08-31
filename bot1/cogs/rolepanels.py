import discord
from discord.ext import commands
from discord import app_commands
import mysql.connector
import os
import asyncio
from typing import Optional, List, Dict, Tuple, Any
import re

# DBヘルパーメソッド（非同期対応）
async def execute_db_operation(query: str, params: Optional[Tuple[Any, ...]] = None, is_read: bool = False):
    conn = None
    cursor = None
    try:
        conn = mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
            port=int(os.getenv("DB_PORT", 3306))
        )
        cursor = conn.cursor()
        
        await asyncio.to_thread(cursor.execute, query, params)
        
        if is_read:
            result = await asyncio.to_thread(cursor.fetchall)
            return result
        else:
            await asyncio.to_thread(conn.commit)
            return None
    except mysql.connector.Error as err:
        print(f"データベースエラー: {err}")
        if conn and conn.is_connected():
            await asyncio.to_thread(conn.rollback)
        raise err
    finally:
        if cursor:
            await asyncio.to_thread(cursor.close)
        if conn and conn.is_connected():
            await asyncio.to_thread(conn.close)

# 絵文字ヘルパー
def get_emoji_id(emoji_string: str) -> str:
    match = re.match(r'<a?:[a-zA-Z0-9_]+:(\d+)>', emoji_string)
    if match:
        return match.group(1)
    return emoji_string

class RolePanels(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None or payload.member.bot:
            return

        emoji_id = str(payload.emoji.id) if payload.emoji.id else payload.emoji.name
        
        query = "SELECT role_id FROM role_panels WHERE panel_message_id = %s AND emoji = %s"
        try:
            results = await execute_db_operation(query, (payload.message_id, emoji_id), is_read=True)
            if results:
                role_id = results[0][0]
                guild = self.bot.get_guild(payload.guild_id)
                if not guild: return
                role = guild.get_role(role_id)
                member = guild.get_member(payload.user_id)
                if role and member:
                    await member.add_roles(role)
        except Exception as e:
            print(f"リアクション追加時のエラー: {e}")

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None or self.bot.get_user(payload.user_id).bot:
            return

        emoji_id = str(payload.emoji.id) if payload.emoji.id else payload.emoji.name

        query = "SELECT role_id FROM role_panels WHERE panel_message_id = %s AND emoji = %s"
        try:
            results = await execute_db_operation(query, (payload.message_id, emoji_id), is_read=True)
            if results:
                role_id = results[0][0]
                guild = self.bot.get_guild(payload.guild_id)
                if not guild: return
                role = guild.get_role(role_id)
                member = guild.get_member(payload.user_id)
                if role and member:
                    await member.remove_roles(role)
        except Exception as e:
            print(f"リアクション削除時のエラー: {e}")

    # -----------------------------
    # スラッシュコマンドグループ
    # -----------------------------
    panel_group = app_commands.Group(name="panel", description="ロールパネルを管理します。")

    @panel_group.command(name="create", description="新しいロールパネルメッセージを作成します。")
    @app_commands.describe(title="パネルのタイトル", description="パネルの説明")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def create_panel(self, interaction: discord.Interaction, title: str, description: str):
        embed = discord.Embed(title=title, description=description, color=discord.Color.blue())
        panel_message = await interaction.channel.send(embed=embed)
        await interaction.response.send_message(f"パネルメッセージを作成しました！ID: `{panel_message.id}`", ephemeral=True)

    @panel_group.command(name="add", description="既存のパネルにリアクションと役職を追加します。")
    @app_commands.describe(message_id="パネルメッセージのID", emoji="追加する絵文字", role="付与する役職")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def add_role(self, interaction: discord.Interaction, message_id: str, emoji: str, role: discord.Role):
        await interaction.response.defer(ephemeral=True)
        
        try:
            message_id = int(message_id)
            panel_message = await interaction.channel.fetch_message(message_id)
            
            emoji_id = get_emoji_id(emoji)
            
            query = "INSERT INTO role_panels (guild_id, panel_message_id, emoji, role_id) VALUES (%s, %s, %s, %s)"
            params = (interaction.guild_id, panel_message.id, emoji_id, role.id)
            
            await execute_db_operation(query, params)
            
            await panel_message.add_reaction(emoji)
            
            await interaction.followup.send(f"パネルに`{emoji}`と`{role.name}`を追加しました。", ephemeral=True)
            
        except discord.NotFound:
            await interaction.followup.send("指定されたパネルメッセージが見つかりません。", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"エラーが発生しました: {e}", ephemeral=True)

    @panel_group.command(name="remove", description="既存のパネルからリアクションと役職を削除します。")
    @app_commands.describe(message_id="パネルメッセージのID", emoji="削除する絵文字")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def remove_role(self, interaction: discord.Interaction, message_id: str, emoji: str):
        await interaction.response.defer(ephemeral=True)
        
        try:
            message_id = int(message_id)
            panel_message = await interaction.channel.fetch_message(message_id)
            
            emoji_id = get_emoji_id(emoji)
            
            query = "DELETE FROM role_panels WHERE panel_message_id = %s AND emoji = %s"
            params = (panel_message.id, emoji_id)
            await execute_db_operation(query, params)
            
            await panel_message.clear_reaction(emoji)
            
            await interaction.followup.send(f"パネルから`{emoji}`を削除しました。", ephemeral=True)
        
        except discord.NotFound:
            await interaction.followup.send("指定されたパネルメッセージが見つかりません。", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"エラーが発生しました: {e}", ephemeral=True)

    @panel_group.command(name="delete", description="ロールパネルメッセージとDBの記録を完全に削除します。")
    @app_commands.describe(message_id="削除するパネルメッセージのID")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def delete_panel(self, interaction: discord.Interaction, message_id: str):
        await interaction.response.defer(ephemeral=True)

        try:
            message_id = int(message_id)
            
            # DBからパネル情報を削除
            query = "DELETE FROM role_panels WHERE panel_message_id = %s"
            await execute_db_operation(query, (message_id,))
            
            # Discord上のメッセージを削除
            panel_message = await interaction.channel.fetch_message(message_id)
            await panel_message.delete()
            
            await interaction.followup.send("パネルを正常に削除しました。", ephemeral=True)
        
        except discord.NotFound:
            await interaction.followup.send("指定されたパネルメッセージが見つかりません。", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"エラーが発生しました: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(RolePanels(bot))
