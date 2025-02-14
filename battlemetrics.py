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
        self.ban_check_task = None

    async def cog_load(self):
        """Async method to start the ban check loop when the cog is loaded."""
        self.ban_check_task = asyncio.create_task(self.start_ban_check_loop())

    def load_config(self):
        """Load configuration from JSON file."""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                    logger.info("BattleMetrics configuration loaded successfully")
                    return config
            else:
                logger.warning("BattleMetrics configuration file not found. Creating default.")
                default_config = {
                    'BATTLEMETRICS_TOKEN': '',
                    'ORGANIZATION_ID': '',
                    'DISCORD_BAN_CHANNEL': '',
                    'LAST_BAN_TIMESTAMP': None
                }
                with open(CONFIG_FILE, 'w') as f:
                    json.dump(default_config, f, indent=4)
                return default_config
        except Exception as e:
            logger.error(f"Error loading BattleMetrics configuration: {e}")
            logger.error(traceback.format_exc())
            return {}

    def save_config(self, updated_config):
        """Save configuration to JSON file."""
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(updated_config, f, indent=4)

            self.config = updated_config
            logger.info("BattleMetrics configuration updated successfully")
            return True
        except Exception as e:
            logger.error(f"Error saving BattleMetrics configuration: {e}")
            logger.error(traceback.format_exc())
            return False

    def cog_unload(self):
        """Cancel the ban check task when the cog is unloaded."""
        if self.ban_check_task:
            self.ban_check_task.cancel()

    async def start_ban_check_loop(self):
        """Wait for bot to be ready, then start periodic ban checks."""
        await self.bot.wait_until_ready()
        logger.info("Starting BattleMetrics ban check loop")

        while True:
            try:
                await self.check_battlemetrics_bans()
                await asyncio.sleep(60)  # Check every 1 minutes
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in ban check loop: {e}")
                logger.error(traceback.format_exc())
                await asyncio.sleep(60)

    async def check_battlemetrics_bans(self):
        """Periodically check for new bans in the organization."""
        if not (self.config.get('BATTLEMETRICS_TOKEN') and
                self.config.get('SERVER_ID') and
                self.config.get('DISCORD_BAN_CHANNEL')):
            logger.warning("BattleMetrics configuration is incomplete. Skipping ban check.")
            return

        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {self.config['BATTLEMETRICS_TOKEN']}",
                    "Accept": "application/json"
                }

                # Correct endpoint and parameters (GET method)
                url = "https://api.battlemetrics.com/bans"
                params = {
                    "filter[server]": self.config['SERVER_ID'],
                    "filter[expired]": "false",
                    "include": "user,server"
                }

                async with session.get(url, headers=headers, params=params) as response:
                    response_text = await response.text()
                    logger.info(f"Full API Response: {response_text}")

                    if response.status == 403:
                        logger.error("Access Forbidden - Check token or permissions.")
                        await self.validate_battlemetrics_token()
                        return

                    if response.status == 405:
                        logger.error("405 Method Not Allowed: Invalid request method for the given endpoint.")
                        logger.info("Ensure the request is using the correct HTTP method (GET).")
                        return

                    if response.status != 200:
                        logger.error(f"Unexpected API error. Status: {response.status}")
                        logger.error(f"Response content: {response_text}")
                        return

                    data = await response.json()
                    await self.process_new_bans(data)

        except Exception as e:
            logger.error(f"Unexpected error checking BattleMetrics bans: {e}")
            logger.error(traceback.format_exc())

    async def validate_battlemetrics_token(self):
        """Validate the BattleMetrics API token."""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": f"Bearer {self.config['BATTLEMETRICS_TOKEN']}",
                    "Accept": "application/json",
                    "User-Agent": "DiscordBanMonitorBot/1.0"
                }

                # Lightweight endpoint for validation as an alternative
                url = "https://api.battlemetrics.com/ping"

                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        logger.info("BattleMetrics API token validated successfully.")
                        return True

                    logger.error(f"Token validation failed. Status: {response.status}")
                    logger.error(f"Response content: {await response.text()}")
                    return False
        except Exception as e:
            logger.error(f"Error validating token: {e}")
            logger.error(traceback.format_exc())
            return False

    async def process_new_bans(self, ban_data):
        """Process and post new bans to Discord."""
        if not ban_data.get('data'):
            return

        try:
            channel = self.bot.get_channel(int(self.config['DISCORD_BAN_CHANNEL']))
            if not channel:
                logger.error("Could not find specified Discord channel")
                return
        except ValueError:
            logger.error("Invalid Discord channel ID")
            return

        most_recent_timestamp = None

        for ban in ban_data['data']:
            try:
                attributes = ban.get('attributes', {})
                timestamp = attributes.get('timestamp')
                reason = attributes.get('reason', 'No reason provided')

                user_data = ban.get('relationships', {}).get('user', {}).get('data', {})
                user_id = user_data.get('id')
                user_name = user_data.get('name', 'Unknown User')

                embed = discord.Embed(
                    title="🚫 New BattleMetrics Ban",
                    color=discord.Color.red()
                )
                embed.add_field(name="User", value=f"{user_name} (ID: {user_id})", inline=False)
                embed.add_field(name="Reason", value=reason, inline=False)
                embed.add_field(name="Banned At", value=timestamp, inline=False)

                await channel.send(embed=embed)

                if not most_recent_timestamp or timestamp > most_recent_timestamp:
                    most_recent_timestamp = timestamp

            except Exception as e:
                logger.error(f"Error processing individual ban: {e}")
                logger.error(traceback.format_exc())

        if most_recent_timestamp:
            updated_config = self.config.copy()
            updated_config['LAST_BAN_TIMESTAMP'] = most_recent_timestamp
            self.save_config(updated_config)

    @commands.command(name="bmconfig")
    @commands.has_permissions(administrator=True)
    async def battlemetrics_config(self, ctx):
        """Create a configuration interface for BattleMetrics settings."""
        embed = discord.Embed(
            title="BattleMetrics Configuration",
            description="Configure BattleMetrics settings using these commands:",
            color=discord.Color.blue()
        )
        embed.add_field(name="Set BattleMetrics Token", value="`!bmtoken <token>`", inline=False)
        embed.add_field(name="Set Organization ID", value="`!bmorgid <org_id>`", inline=False)
        embed.add_field(name="Set Ban Notification Channel", value="`!bmchannel #channel`", inline=False)

        await ctx.send(embed=embed)

    @commands.command(name="bmtoken")
    @commands.has_permissions(administrator=True)
    async def set_bm_token(self, ctx, token: str):
        """Set BattleMetrics API token."""
        updated_config = self.config.copy()
        updated_config['BATTLEMETRICS_TOKEN'] = token
        if self.save_config(updated_config):
            await ctx.send("✅ BattleMetrics Token updated successfully!")
        else:
            await ctx.send("❌ Failed to update BattleMetrics Token.")

    @commands.command(name="bmorgid")
    @commands.has_permissions(administrator=True)
    async def set_org_id(self, ctx, org_id: str):
        """Set BattleMetrics Organization ID."""
        updated_config = self.config.copy()
        updated_config['ORGANIZATION_ID'] = org_id
        if self.save_config(updated_config):
            await ctx.send("✅ Organization ID updated successfully!")
        else:
            await ctx.send("❌ Failed to update Organization ID.")

    @commands.command(name="bmchannel")
    @commands.has_permissions(administrator=True)
    async def set_ban_channel(self, ctx, channel: discord.TextChannel):
        """Set Discord channel for ban notifications."""
        updated_config = self.config.copy()
        updated_config['DISCORD_BAN_CHANNEL'] = str(channel.id)
        if self.save_config(updated_config):
            await ctx.send(f"✅ Ban notification channel set to {channel.mention}!")
        else:
            await ctx.send("❌ Failed to update ban notification channel.")

    @commands.command(name="bmtest")
    @commands.has_permissions(administrator=True)
    async def battlemetrics_test(self, ctx):
        """Test the current BattleMetrics configuration."""
        config = self.config

        embed = discord.Embed(
            title="BattleMetrics Configuration Test",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="BattleMetrics Token",
            value="✅ Configured" if config.get('BATTLEMETRICS_TOKEN') else "❌ Not Set",
            inline=False
        )
        embed.add_field(
            name="Organization ID",
            value="✅ Configured" if config.get('ORGANIZATION_ID') else "❌ Not Set",
            inline=False
        )
        embed.add_field(
            name="Discord Ban Channel",
            value=f"✅ {config.get('DISCORD_BAN_CHANNEL')}" if config.get('DISCORD_BAN_CHANNEL') else "❌ Not Set",
            inline=False
        )

        await ctx.send(embed=embed)

    @commands.command(name="bmvalidate")
    @commands.has_permissions(administrator=True)
    async def validate_token(self, ctx):
        """Validate the current BattleMetrics token."""
        is_valid = await self.validate_battlemetrics_token()
        if is_valid:
            await ctx.send("✅ BattleMetrics API token is valid!")
        else:
            await ctx.send("❌ BattleMetrics API token is invalid. Please update your token.")

    @commands.command(name="bmdiagnose")
    @commands.has_permissions(administrator=True)
    async def diagnose_battlemetrics(self, ctx):
        """Comprehensive BattleMetrics configuration diagnosis."""
        await ctx.send("Running comprehensive BattleMetrics diagnostics...")

        embed = discord.Embed(title="BattleMetrics Diagnostics", color=discord.Color.orange())

        # Token validation
        token_valid = await self.validate_battlemetrics_token()
        embed.add_field(
            name="Token Validation",
            value="✅ Valid" if token_valid else "❌ Invalid",
            inline=False
        )

        # Configuration check
        config_complete = all([
            self.config.get('BATTLEMETRICS_TOKEN'),
            self.config.get('ORGANIZATION_ID'),
            self.config.get('DISCORD_BAN_CHANNEL')
        ])
        embed.add_field(
            name="Configuration",
            value="✅ Complete" if config_complete else "❌ Incomplete",
            inline=False
        )

        await ctx.send(embed=embed)


async def setup(bot):
    """Setup function for the BattleMetrics extension."""
    try:
        await bot.add_cog(BattleMetrics(bot))
        logger.info("BattleMetrics extension loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load BattleMetrics extension: {e}")
        logger.error(traceback.format_exc())
