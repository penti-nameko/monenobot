import discord
from discord.ext import commands
from discord import app_commands
import mysql.connector
import os
import asyncio
from typing import Optional, List, Dict, Tuple, Any

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

class TempVoice(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -----------------------------
    # 内部ヘルパーメソッド
    # -----------------------------
    async def _handle_voice_join(self, member: discord.Member, channel: discord.VoiceChannel):
        """ユーザーが親VCに参加した際の処理"""
        query = "SELECT parent_channel_id FROM temp_vc_channels WHERE parent_channel_id = %s"
        is_parent = await execute_db_operation(query, (channel.id,), is_read=True)

        if not is_parent:
            return

        channel_name = f"{member.display_name}のボイス"

        # チャンネルを作成する際に、親チャンネルにカテゴリがあるか確認
        if channel.category:
            new_channel = await channel.category.create_voice_channel(channel_name)
        else:
            # カテゴリがない場合はギルドのトップレベルに作成
            new_channel = await member.guild.create_voice_channel(channel_name)

        # ユーザーを新しいチャンネルに移動
        await member.move_to(new_channel)

        # データベースに所有者情報を記録
        insert_query = "INSERT INTO owned_vc_channels (vc_channel_id, owner_id) VALUES (%s, %s)"
        await execute_db_operation(insert_query, (new_channel.id, member.id))

    async def _handle_voice_leave(self, member: discord.Member, channel: discord.VoiceChannel):
        """ユーザーがVCから退出した際の処理"""
        is_owned = await execute_db_operation(
            "SELECT owner_id FROM owned_vc_channels WHERE vc_channel_id = %s", 
            (channel.id,), 
            is_read=True
        )

        if is_owned and len(channel.members) == 0:
            try:
                delete_query = "DELETE FROM owned_vc_channels WHERE vc_channel_id = %s"
                await execute_db_operation(delete_query, (channel.id,))
                
                await channel.delete()
            except discord.errors.NotFound:
                pass
            except Exception as e:
                print(f"一時ボイスチャンネルの削除中にエラーが発生しました: {e}")

    # -----------------------------
    # イベントリスナー
    # -----------------------------
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return

        if after.channel and before.channel != after.channel:
            await self._handle_voice_join(member, after.channel)
        
        if before.channel:
            await self._handle_voice_leave(member, before.channel)
            
    # -----------------------------
    # スラッシュコマンド
    # -----------------------------
    tempvc_group = app_commands.Group(name="tempvc", description="一時ボイスチャンネルを管理します。")

    @tempvc_group.command(
        name="create",
        description="新しいボイスチャンネルを作成し、一時ボイスチャンネルの親に設定します。"
    )
    @app_commands.describe(
        channel_name="作成するボイスチャンネルの名前",
        category="チャンネルを作成するカテゴリ"
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    async def create_tempvc_channel(self, interaction: discord.Interaction, channel_name: str, category: Optional[discord.CategoryChannel] = None):
        await interaction.response.defer(ephemeral=True)

        try:
            delete_query = "DELETE FROM temp_vc_channels WHERE guild_id = %s"
            await execute_db_operation(delete_query, (interaction.guild_id,))

            if category:
                new_channel = await category.create_voice_channel(channel_name)
            else:
                new_channel = await interaction.guild.create_voice_channel(channel_name)

            query = "INSERT INTO temp_vc_channels (guild_id, parent_channel_id) VALUES (%s, %s)"
            await execute_db_operation(query, (interaction.guild_id, new_channel.id))
            
            await interaction.followup.send(f"新しいボイスチャンネル`{new_channel.name}`を作成し、一時ボイスチャンネルの親として設定しました。", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"チャンネルの作成中にエラーが発生しました: {e}", ephemeral=True)

    @tempvc_group.command(
        name="set",
        description="現在のボイスチャンネルを一時ボイスチャンネルの親に設定します。"
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    async def set_tempvc_channel(self, interaction: discord.Interaction):
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("このコマンドを実行するには、ボイスチャンネルに参加している必要があります。", ephemeral=True)
            return

        parent_channel = interaction.user.voice.channel
        await interaction.response.defer(ephemeral=True)

        try:
            delete_query = "DELETE FROM temp_vc_channels WHERE guild_id = %s"
            await execute_db_operation(delete_query, (interaction.guild_id,))

            query = "INSERT INTO temp_vc_channels (guild_id, parent_channel_id) VALUES (%s, %s)"
            await execute_db_operation(query, (interaction.guild.id, parent_channel.id))
            
            await interaction.followup.send(f"`{parent_channel.name}`を一時ボイスチャンネルの親として設定しました。", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"エラーが発生しました: {e}", ephemeral=True)

    @tempvc_group.command(
        name="delete",
        description="一時ボイスチャンネルの親を削除します。"
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    async def delete_tempvc_channel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            query = "DELETE FROM temp_vc_channels WHERE guild_id = %s"
            await execute_db_operation(query, (interaction.guild_id,))
            
            await interaction.followup.send("一時ボイスチャンネルの親を削除しました。", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"削除中にエラーが発生しました: {e}", ephemeral=True)

    @tempvc_group.command(
        name="list",
        description="現在設定されている一時ボイスチャンネルの親を表示します。"
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    async def list_tempvc_channel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            query = "SELECT parent_channel_id FROM temp_vc_channels WHERE guild_id = %s"
            result = await execute_db_operation(query, (interaction.guild_id,), is_read=True)

            if not result:
                await interaction.followup.send("このギルドには一時ボイスチャンネルの親が設定されていません。", ephemeral=True)
                return

            parent_channel_id = result[0][0]
            parent_channel = interaction.guild.get_channel(parent_channel_id)

            if parent_channel:
                await interaction.followup.send(f"現在の親チャンネル: `{parent_channel.name}`", ephemeral=True)
            else:
                await interaction.followup.send("データベースに登録されていますが、Discord上では見つかりません。`/tempvc delete`で削除してください。", ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"情報の取得中にエラーが発生しました: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(TempVoice(bot))
