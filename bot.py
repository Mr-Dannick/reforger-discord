import os
import json
import discord
import aiohttp
import traceback
import asyncio
from discord.ext import commands
from logger import logger
from config import CONFIG_FILE


class BattleMetrics(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = self.load_config()
        self.session = None  # aiohttp session for API requests

    async def cog_load(self):
        """Async method to initialize on cog load."""
        logger.info("BattleMetrics cog loaded successfully")
        self.session = aiohttp.ClientSession()

    def cog_unload(self):
        """Cleanup when the cog is unloaded."""
        asyncio.create_task(self.close_session())

    async def close_session(self):
        """Close the aiohttp session."""
        if self.session:
            await self.session.close()

    def load_config(self):
        default_config = {
            'BATTLEMETRICS_TOKEN': None,
            'SERVER_ID': None,
            'DISCORD_BAN_CHANNEL': None,
            'POSTED_BANS': []
        }

        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                saved_config = json.load(f)
                default_config.update(saved_config)
        else:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(default_config, f, indent=4)

        logger.info(f"Loaded BattleMetrics config: {default_config}")
        return default_config

    def save_config(self):
        """Save the updated configuration."""
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.config, f, indent=4)
        logger.info("Saved BattleMetrics configuration.")

    async def fetch_bans(self):
        """Fetch current bans from BattleMetrics API."""
        if not self.config['BATTLEMETRICS_TOKEN'] or not self.config['SERVER_ID']:
            logger.error("BattleMetrics configuration is incomplete (missing token or server ID).")
            return None

        headers = {
            'Authorization': f"Bearer {self.config['BATTLEMETRICS_TOKEN']}",
            'Accept': 'application/json'
        }

        try:
            url = "https://api.battlemetrics.com/bans"
            params = {
                'filter[server]': self.config['SERVER_ID'],
                'filter[expired]': 'false',
                'include': 'user,server'
            }

            async with self.session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"Failed to fetch bans: {response.status} - {await response.text()}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching bans: {str(e)}")
            return None

    async def process_new_bans(self):
        """Fetch and process BattleMetrics bans."""
        if not self.config['DISCORD_BAN_CHANNEL']:
            logger.error("Discord ban channel is not set in the configuration.")
            return

        bans_channel = self.bot.get_channel(int(self.config['DISCORD_BAN_CHANNEL']))
        if not bans_channel:
            logger.error("Failed to find the Discord ban channel.")
            return

        # Fetch bans from the API
        bans_data = await self.fetch_bans()
        if not bans_data or 'data' not in bans_data:
            logger.info("No bans data found.")
            return

        for ban in bans_data['data']:
            ban_id = ban.get('id')
            if ban_id in self.config['POSTED_BANS']:
                continue  # Skip already posted bans

            attributes = ban.get('attributes', {})
            reason = attributes.get('reason', 'No reason provided')
            expires = attributes.get('expires', None)

            # Get identifier
            identifier = 'Unknown'
            identifiers = attributes.get('identifiers', [])
            for id_entry in identifiers:
                if id_entry.get('type') == 'name':
                    identifier = id_entry.get('identifier')
                    break

            # Ban expiration information
            if expires:
                from datetime import datetime
                expires_dt = datetime.fromisoformat(expires.replace('Z', '+00:00'))
                expires_str = expires_dt.strftime("%Y-%m-%d %H:%M UTC")
            else:
                expires_str = "Permanent"

            ban_message = (
                "🚫 **New Ban**\n"
                f"**Player**: {identifier}\n"
                f"**Reason**: {reason}\n"
                f"**Expires**: {expires_str}"
            )

            # Post the ban message to Discord
            await bans_channel.send(ban_message)

            # Add the ban ID to the posted list and save config
            self.config['POSTED_BANS'].append(ban_id)
            self.save_config()

            logger.info(f"Posted new ban: {identifier}")

    @commands.command(name="set_bm_token")
    @commands.has_permissions(administrator=True)
    async def set_bm_token(self, ctx, token: str):
        """Set the BattleMetrics API token."""
        self.config['BATTLEMETRICS_TOKEN'] = token
        self.save_config()
        await ctx.send("BattleMetrics token updated successfully.")

    @commands.command(name="set_server_id")
    @commands.has_permissions(administrator=True)
    async def set_server_id(self, ctx, server_id: str):
        """Set the BattleMetrics server ID."""
        self.config['SERVER_ID'] = server_id
        self.save_config()
        await ctx.send(f"BattleMetrics Server ID set to: {server_id}")

    @commands.command(name="set_ban_channel")
    @commands.has_permissions(administrator=True)
    async def set_ban_channel(self, ctx, channel: discord.TextChannel):
        """Set the channel for ban notifications."""
        self.config['DISCORD_BAN_CHANNEL'] = str(channel.id)
        self.save_config()
        await ctx.send(f"Ban notifications will now be sent to {channel.mention}")

    @commands.command(name="check_bans")
    async def check_bans(self, ctx):
        """Manually check and post new bans."""
        await self.process_new_bans()


async def setup(bot):
    """Setup function for the BattleMetrics cog."""
    await bot.add_cog(BattleMetrics(bot))
