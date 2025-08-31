import discord
from discord.ext import commands
from discord import app_commands
import mysql.connector
import os
import asyncio
from typing import Optional, List, Dict, Tuple, Any
from datetime import datetime, timedelta

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

class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _get_economy_data(self, user_id: int, guild_id: Optional[int] = None, is_global: bool = False):
        """ユーザーの残高データを取得または作成するヘルパー関数"""
        if is_global:
            query = "SELECT balance, last_daily FROM global_economy WHERE user_id = %s"
            params = (user_id,)
            create_query = "INSERT INTO global_economy (user_id) VALUES (%s)"
        else:
            query = "SELECT balance, last_daily FROM server_economy WHERE user_id = %s AND guild_id = %s"
            params = (user_id, guild_id)
            create_query = "INSERT INTO server_economy (user_id, guild_id) VALUES (%s, %s)"
        
        result = await execute_db_operation(query, params, is_read=True)
        if result:
            return result[0]
        else:
            await execute_db_operation(create_query, params)
            return (0, datetime.now() - timedelta(days=1))

    # -----------------------------
    # スラッシュコマンド
    # -----------------------------
    economy_group = app_commands.Group(name="eco", description="経済システムを管理します。")

    @economy_group.command(
        name="daily",
        description="デイリーボーナスを受け取ります。"
    )
    async def daily(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id
        guild_id = interaction.guild.id

        # サーバー経済のデイリーチェック
        server_data = await self._get_economy_data(user_id, guild_id)
        server_last_daily = server_data[1]
        
        # グローバル経済のデイリーチェック
        global_data = await self._get_economy_data(user_id, is_global=True)
        global_last_daily = global_data[1]

        now = datetime.now()
        server_daily_ready = now - server_last_daily >= timedelta(hours=24)
        global_daily_ready = now - global_last_daily >= timedelta(hours=24)
        
        message = ""
        if server_daily_ready:
            await execute_db_operation(
                "UPDATE server_economy SET balance = balance + 1000, last_daily = %s WHERE user_id = %s AND guild_id = %s",
                (now, user_id, guild_id)
            )
            message += "💰 サーバー通貨で**1000**を受け取りました！\n"
        
        if global_daily_ready:
            await execute_db_operation(
                "UPDATE global_economy SET balance = balance + 500, last_daily = %s WHERE user_id = %s",
                (now, user_id)
            )
            message += "🌐 グローバル通貨で**500**を受け取りました！\n"

        if not message:
            server_next_daily = server_last_daily + timedelta(hours=24)
            global_next_daily = global_last_daily + timedelta(hours=24)
            message = "まだデイリーボーナスを受け取れません。\n"
            message += f"サーバー通貨は {server_next_daily.strftime('%H:%M')}頃、\n"
            message += f"グローバル通貨は {global_next_daily.strftime('%H:%M')}頃に受け取れます。"
            
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.followup.send(message, ephemeral=True)

    @economy_group.command(
        name="balance",
        description="あなたの残高を確認します。"
    )
    @app_commands.describe(member="残高を確認するメンバー")
    async def balance(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        await interaction.response.defer()
        
        target_member = member or interaction.user
        
        server_data = await self._get_economy_data(target_member.id, interaction.guild.id)
        global_data = await self._get_economy_data(target_member.id, is_global=True)
        
        server_balance = server_data[0]
        global_balance = global_data[0]

        embed = discord.Embed(
            title="💰 残高",
            description=f"{target_member.mention} の現在の残高",
            color=discord.Color.gold()
        )
        embed.add_field(name="サーバー通貨", value=f"**{server_balance}**", inline=False)
        embed.add_field(name="グローバル通貨", value=f"**{global_balance}**", inline=False)
        embed.set_thumbnail(url=target_member.avatar.url)
        embed.set_footer(text=f"要求者: {interaction.user.display_name}", icon_url=interaction.user.avatar.url)
        
        await interaction.followup.send(embed=embed)


    @economy_group.command(
        name="give",
        description="通貨を他のユーザーに送金します。"
    )
    @app_commands.describe(
        member="送金先のメンバー",
        amount="送金する金額",
        economy_type="送金する通貨の種類（サーバー/グローバル）"
    )
    @app_commands.choices(
        economy_type=[
            app_commands.Choice(name="サーバー通貨", value="server"),
            app_commands.Choice(name="グローバル通貨", value="global")
        ]
    )
    async def give(self, interaction: discord.Interaction, member: discord.Member, amount: int, economy_type: str):
        await interaction.response.defer(ephemeral=True)
        
        if amount <= 0:
            await interaction.followup.send("送金金額は1以上である必要があります。", ephemeral=True)
            return
        
        if interaction.user.id == member.id:
            await interaction.followup.send("自分自身に送金することはできません。", ephemeral=True)
            return

        conn = None
        try:
            conn = mysql.connector.connect(
                host=os.getenv("DB_HOST"),
                user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASSWORD"),
                database=os.getenv("DB_NAME"),
                port=int(os.getenv("DB_PORT", 3306))
            )
            cursor = conn.cursor()
            
            if economy_type == "server":
                # サーバー経済の送金処理
                cursor.execute("SELECT balance FROM server_economy WHERE user_id = %s AND guild_id = %s", (interaction.user.id, interaction.guild.id))
                sender_balance = cursor.fetchone()
                if not sender_balance or sender_balance[0] < amount:
                    await interaction.followup.send("サーバー通貨の残高が足りません。", ephemeral=True)
                    return

                # トランザクションの開始
                conn.start_transaction()
                try:
                    cursor.execute("UPDATE server_economy SET balance = balance - %s WHERE user_id = %s AND guild_id = %s", (amount, interaction.user.id, interaction.guild.id))
                    cursor.execute("INSERT INTO server_economy (user_id, guild_id) VALUES (%s, %s) ON DUPLICATE KEY UPDATE balance = balance + %s", (member.id, interaction.guild.id, amount))
                    conn.commit()
                    await interaction.followup.send(f"✅ {member.mention}にサーバー通貨**{amount}**を送金しました。", ephemeral=True)
                except Exception as e:
                    conn.rollback()
                    await interaction.followup.send(f"送金中にエラーが発生しました: {e}", ephemeral=True)
            else: # global
                # グローバル経済の送金処理
                cursor.execute("SELECT balance FROM global_economy WHERE user_id = %s", (interaction.user.id,))
                sender_balance = cursor.fetchone()
                if not sender_balance or sender_balance[0] < amount:
                    await interaction.followup.send("グローバル通貨の残高が足りません。", ephemeral=True)
                    return

                # トランザクションの開始
                conn.start_transaction()
                try:
                    cursor.execute("UPDATE global_economy SET balance = balance - %s WHERE user_id = %s", (amount, interaction.user.id))
                    cursor.execute("INSERT INTO global_economy (user_id) VALUES (%s) ON DUPLICATE KEY UPDATE balance = balance + %s", (member.id, amount))
                    conn.commit()
                    await interaction.followup.send(f"✅ {member.mention}にグローバル通貨**{amount}**を送金しました。", ephemeral=True)
                except Exception as e:
                    conn.rollback()
                    await interaction.followup.send(f"送金中にエラーが発生しました: {e}", ephemeral=True)
        
        except Exception as e:
            await interaction.followup.send(f"データベース接続エラーが発生しました: {e}", ephemeral=True)
        finally:
            if conn and conn.is_connected():
                conn.close()


    @economy_group.command(
        name="leaderboard",
        description="通貨のランキングを表示します。"
    )
    async def leaderboard(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        server_leaderboard_query = "SELECT user_id, balance FROM server_economy WHERE guild_id = %s ORDER BY balance DESC LIMIT 10"
        server_leaderboard_data = await execute_db_operation(server_leaderboard_query, (interaction.guild.id,), is_read=True)

        global_leaderboard_query = "SELECT user_id, balance FROM global_economy ORDER BY balance DESC LIMIT 10"
        global_leaderboard_data = await execute_db_operation(global_leaderboard_query, is_read=True)

        embed = discord.Embed(
            title="👑 通貨ランキング",
            color=discord.Color.gold()
        )
        
        server_rank_str = ""
        for i, (user_id, balance) in enumerate(server_leaderboard_data):
            user = self.bot.get_user(user_id)
            if user:
                server_rank_str += f"`{i+1}.` {user.name} - **{balance}**\n"
        if not server_rank_str:
            server_rank_str = "データがありません。"
        
        embed.add_field(name="サーバーランキング", value=server_rank_str, inline=False)
        
        global_rank_str = ""
        for i, (user_id, balance) in enumerate(global_leaderboard_data):
            user = self.bot.get_user(user_id)
            if user:
                global_rank_str += f"`{i+1}.` {user.name} - **{balance}**\n"
        if not global_rank_str:
            global_rank_str = "データがありません。"

        embed.add_field(name="グローバルランキング", value=global_rank_str, inline=False)
        embed.set_footer(text=f"要求者: {interaction.user.display_name}", icon_url=interaction.user.avatar.url)

        await interaction.followup.send(embed=embed)


    @economy_group.command(
        name="additem",
        description="ショップに新しいアイテムを追加します。(管理者限定)"
    )
    @app_commands.describe(
        name="アイテムの名前",
        price="価格（サーバー通貨）",
        description="アイテムの説明"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def additem(self, interaction: discord.Interaction, name: str, price: int, description: str):
        await interaction.response.defer(ephemeral=True)

        if price <= 0:
            await interaction.followup.send("価格は1以上である必要があります。", ephemeral=True)
            return

        try:
            query = "INSERT INTO shop_items (guild_id, item_name, price, description) VALUES (%s, %s, %s, %s)"
            params = (interaction.guild.id, name, price, description)
            await execute_db_operation(query, params)
            await interaction.followup.send(f"✅ アイテム「**{name}**」をショップに追加しました。価格: {price}", ephemeral=True)
        except mysql.connector.Error as err:
            if "Duplicate entry" in str(err):
                await interaction.followup.send(f"アイテム「**{name}**」はすでにショップに存在します。", ephemeral=True)
            else:
                await interaction.followup.send(f"データベースエラーが発生しました: {err}", ephemeral=True)

    @economy_group.command(
        name="shop",
        description="サーバーのショップアイテム一覧を表示します。"
    )
    async def shop(self, interaction: discord.Interaction):
        await interaction.response.defer()

        query = "SELECT item_name, price, description FROM shop_items WHERE guild_id = %s ORDER BY price"
        items = await execute_db_operation(query, (interaction.guild.id,), is_read=True)

        embed = discord.Embed(
            title=f"🛍️ {interaction.guild.name} ショップ",
            color=discord.Color.blue()
        )

        if not items:
            embed.description = "現在、ショップにアイテムはありません。"
        else:
            for item in items:
                name, price, desc = item
                embed.add_field(name=f"**{name}**", value=f"価格: {price}\n{desc}", inline=False)
        
        await interaction.followup.send(embed=embed)

    @economy_group.command(
        name="buy",
        description="ショップのアイテムを購入します。"
    )
    @app_commands.describe(item_name="購入したいアイテムの名前")
    async def buy(self, interaction: discord.Interaction, item_name: str):
        await interaction.response.defer(ephemeral=True)

        conn = None
        try:
            conn = mysql.connector.connect(
                host=os.getenv("DB_HOST"),
                user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASSWORD"),
                database=os.getenv("DB_NAME"),
                port=int(os.getenv("DB_PORT", 3306))
            )
            cursor = conn.cursor()
            
            cursor.execute("SELECT price FROM shop_items WHERE guild_id = %s AND item_name = %s", (interaction.guild.id, item_name))
            item_data = cursor.fetchone()
            
            if not item_data:
                await interaction.followup.send("そのアイテムはショップに存在しません。", ephemeral=True)
                return

            price = item_data[0]

            cursor.execute("SELECT balance FROM server_economy WHERE user_id = %s AND guild_id = %s", (interaction.user.id, interaction.guild.id))
            user_balance_data = cursor.fetchone()
            
            user_balance = user_balance_data[0] if user_balance_data else 0

            if user_balance < price:
                await interaction.followup.send(f"残高が足りません。現在の残高は**{user_balance}**です。", ephemeral=True)
                return
            
            # トランザクションの開始
            conn.start_transaction()
            try:
                cursor.execute("UPDATE server_economy SET balance = balance - %s WHERE user_id = %s AND guild_id = %s", (price, interaction.user.id, interaction.guild.id))
                await interaction.followup.send(f"🎉 アイテム「**{item_name}**」を**{price}**で購入しました！", ephemeral=False)
                conn.commit()
            except Exception as e:
                conn.rollback()
                await interaction.followup.send(f"購入中にエラーが発生しました: {e}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"データベース接続エラーが発生しました: {e}", ephemeral=True)
        finally:
            if conn and conn.is_connected():
                conn.close()


async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))
