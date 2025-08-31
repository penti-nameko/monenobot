import discord
from discord.ext import commands
from discord import app_commands
import random
import re
from typing import Optional

class Dice(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="roll",
        description="TRPGで一般的なダイスロール（XdY+Z）を実行します。"
    )
    @app_commands.describe(
        dice="振るダイスの形式（例: 2d6, 1d100+10）"
    )
    async def roll(self, interaction: discord.Interaction, dice: str):
        await interaction.response.defer()

        # 正規表現でXdY+Zの形式を解析
        match = re.match(r'(\d+)d(\d+)(?:([+\-]\d+))?', dice.lower())
        if not match:
            await interaction.followup.send("ダイス形式が無効です。（例: 2d6, 1d100+10）", ephemeral=True)
            return

        num_dice = int(match.group(1))
        num_faces = int(match.group(2))
        modifier = int(match.group(3)) if match.group(3) else 0

        if num_dice <= 0 or num_faces <= 0:
            await interaction.followup.send("ダイスの数と面数は1以上で指定してください。", ephemeral=True)
            return

        rolls = [random.randint(1, num_faces) for _ in range(num_dice)]
        total = sum(rolls) + modifier
        
        rolls_str = ", ".join(map(str, rolls))
        modifier_str = f" + {modifier}" if modifier > 0 else f" - {abs(modifier)}" if modifier < 0 else ""

        embed = discord.Embed(
            title="🎲 ダイスロール",
            description=f"**{dice}**",
            color=discord.Color.blue()
        )
        embed.add_field(name="ロール結果", value=f"```fix\n{rolls_str}{modifier_str} = {total}```")
        embed.set_footer(text=f"実行者: {interaction.user.display_name}")

        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="check",
        description="クトゥルフ神話TRPGの成功判定（1d100）を実行します。"
    )
    @app_commands.describe(
        skill="判定の目標値（技能値や能力値など）"
    )
    async def check(self, interaction: discord.Interaction, skill: int):
        await interaction.response.defer()

        if not 1 <= skill <= 100:
            await interaction.followup.send("目標値は1から100の範囲で指定してください。", ephemeral=True)
            return

        roll = random.randint(1, 100)
        result_type = "失敗"
        color = discord.Color.red()
        
        # 判定ロジック
        if roll <= skill:
            if roll <= 5: # 5%以下の確率はスペシャル
                if roll <= (skill / 5): # 技能値の1/5以下はスペシャル（ハウスルール）
                    result_type = "スペシャル成功"
                    color = discord.Color.green()
                else: # 技能値の1/5以下はスペシャル、その他は通常成功
                    result_type = "成功"
                    color = discord.Color.green()
            elif roll == 1: # 厳密なクリティカル
                result_type = "クリティカル"
                color = discord.Color.gold()
            else:
                result_type = "成功"
                color = discord.Color.green()
        elif roll >= 96:
            result_type = "ファンブル"
            color = discord.Color.dark_red()
        else:
            result_type = "失敗"
            color = discord.Color.red()
            
        # 簡易判定
        if roll == 1:
            result_type = "クリティカル"
            color = discord.Color.gold()
        elif roll >= 96:
            result_type = "ファンブル"
            color = discord.Color.dark_red()
        elif roll <= skill / 2: # 技能値の半分以下はスペシャル
            result_type = "スペシャル成功"
            color = discord.Color.green()
        elif roll <= skill:
            result_type = "成功"
            color = discord.Color.green()

        embed = discord.Embed(
            title="🎯 成功判定",
            description=f"**目標値: {skill}**",
            color=color
        )
        embed.add_field(name="ロール結果", value=f"```fix\n1d100 = {roll}```")
        embed.add_field(name="判定結果", value=f"**{result_type}**", inline=False)
        embed.set_footer(text=f"実行者: {interaction.user.display_name}")

        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(Dice(bot))
