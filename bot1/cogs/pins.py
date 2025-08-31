import discord
from discord.ext import commands
from discord import app_commands
import mysql.connector
import os
from datetime import datetime
import asyncio

class Pins(commands.Cog):
    """メッセージピン留め管理コグ"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -----------------------------
    # 内部: DB接続とクエリ実行を行うヘルパーメソッド
    # -----------------------------
    async def _execute_db_operation(self, query: str, params: tuple = None, is_read: bool = False):
        """
        データベース操作を実行する非同期ヘルパーメソッド。

        :param query: 実行するSQLクエリ
        :param params: クエリに渡すパラメータ
        :param is_read: 読み取り操作（SELECT）であるか
        :return: 読み取り操作の場合は結果を返し、書き込み操作の場合はNone
        """
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
            print(f"データベースエラーが発生しました: {err}")
            if conn:
                await asyncio.to_thread(conn.rollback)
            raise err
        finally:
            if cursor:
                await asyncio.to_thread(cursor.close)
            if conn:
                await asyncio.to_thread(conn.close)

    # -----------------------------
    # メッセージ送信時の自動更新
    # -----------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        try:
            # データベースから既存のピン留め情報を取得
            results = await self._execute_db_operation(
                "SELECT message_id, content, author_id FROM pinned_messages WHERE channel_id = %s",
                (message.channel.id,),
                is_read=True
            )

            if results:
                old_message_id, content, author_id = results[0]
                
                # 古いピン留めメッセージを削除
                try:
                    old_pinned_message = await message.channel.fetch_message(old_message_id)
                    await old_pinned_message.delete()
                except (discord.NotFound, discord.Forbidden):
                    pass
                
                # 新しいピン留めメッセージを送信
                embed = discord.Embed(
                    title="📌 ピン留めメッセージ",
                    description=content,
                    color=discord.Color.blue()
                )
                author = self.bot.get_user(author_id)
                if author:
                    embed.set_author(name=f"{author.display_name}の投稿", icon_url=author.avatar.url)
                else:
                    embed.set_author(name=f"不明なユーザー (ID: {author_id})の投稿")
                
                new_pinned_message = await message.channel.send(embed=embed)
                
                # データベースのピン留めメッセージIDを更新
                await self._execute_db_operation(
                    """
                    UPDATE pinned_messages
                    SET message_id = %s, created_at = %s
                    WHERE channel_id = %s
                    """,
                    (new_pinned_message.id, datetime.now(), message.channel.id)
                )

        except mysql.connector.Error:
            pass # データベースエラーはログ出力済みのため、ここでは何もしない

    # -----------------------------
    # /pin（スラッシュコマンド）
    # -----------------------------
    @app_commands.command(
        name="pin",
        description="メッセージをデータベースにピン留めします。"
    )
    @app_commands.describe(
        message_id="ピン留めするメッセージのID"
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def pin_command(self, interaction: discord.Interaction, message_id: str):
        try:
            message_id = int(message_id)
        except ValueError:
            await interaction.response.send_message("無効なメッセージIDです。", ephemeral=True)
            return

        try:
            target_message = await interaction.channel.fetch_message(message_id)
        except discord.NotFound:
            await interaction.response.send_message("指定されたメッセージが見つかりません。", ephemeral=True)
            return
        except discord.Forbidden:
            await interaction.response.send_message("このチャンネルのメッセージを読み取る権限がありません。", ephemeral=True)
            return
        
        new_pinned_message = None

        try:
            # 既存のピン留めメッセージを取得して削除
            existing_pins = await self._execute_db_operation(
                "SELECT message_id FROM pinned_messages WHERE channel_id = %s",
                (interaction.channel.id,),
                is_read=True
            )
            
            if existing_pins:
                try:
                    old_pinned_message = await interaction.channel.fetch_message(existing_pins[0][0])
                    await old_pinned_message.delete()
                except (discord.NotFound, discord.Forbidden):
                    pass

            # 新しいピン留めメッセージを送信
            embed = discord.Embed(
                title="📌 ピン留めメッセージ",
                description=target_message.content,
                color=discord.Color.blue()
            )
            embed.set_author(name=f"{target_message.author.display_name}の投稿", icon_url=target_message.author.avatar.url)

            new_pinned_message = await interaction.channel.send(embed=embed)

            # データベースに新しいピン留め情報を挿入または更新
            await self._execute_db_operation(
                """
                INSERT INTO pinned_messages (message_id, guild_id, channel_id, author_id, pinned_by_id, content, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE message_id = VALUES(message_id), content = VALUES(content), author_id = VALUES(author_id), pinned_by_id = VALUES(pinned_by_id), created_at = VALUES(created_at)
                """,
                (
                    new_pinned_message.id,
                    interaction.guild.id,
                    interaction.channel.id,
                    target_message.author.id,
                    interaction.user.id,
                    target_message.content,
                    datetime.now()
                ),
                is_read=False
            )

            await interaction.response.send_message(f"メッセージをピン留めしました！", ephemeral=True)

        except mysql.connector.Error:
            await interaction.response.send_message("データベースエラーが発生しました。時間を置いて再度お試しください。", ephemeral=True)
            try:
                if new_pinned_message:
                    await new_pinned_message.delete()
            except:
                pass

    @app_commands.command(
        name="unpin",
        description="このチャンネルのピン留めメッセージを削除します。"
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def unpin_command(self, interaction: discord.Interaction):
        try:
            # データベースから既存のピン留め情報を取得
            results = await self._execute_db_operation(
                "SELECT message_id FROM pinned_messages WHERE channel_id = %s",
                (interaction.channel.id,),
                is_read=True
            )

            if not results:
                await interaction.response.send_message("このチャンネルにはピン留めされたメッセージがありません。", ephemeral=True)
                return

            old_message_id = results[0][0]
            
            # Discord上のメッセージを削除
            try:
                old_pinned_message = await interaction.channel.fetch_message(old_message_id)
                await old_pinned_message.delete()
            except (discord.NotFound, discord.Forbidden):
                pass

            # データベースからピン留め情報を削除
            await self._execute_db_operation(
                "DELETE FROM pinned_messages WHERE channel_id = %s",
                (interaction.channel.id,),
                is_read=False
            )

            await interaction.response.send_message("ピン留めメッセージを削除しました。", ephemeral=True)
        except mysql.connector.Error:
            await interaction.response.send_message("データベースエラーが発生しました。時間を置いて再度お試しください。", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Pins(bot))
