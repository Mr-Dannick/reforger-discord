import json
import discord
from discord.ext import commands
from discord import app_commands
from config import CONFIG_FILE
from logger import logger


def load_config():
    """Helper function to load the configuration file."""
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error("Configuration file not found.")
        return {}
    except json.JSONDecodeError:
        logger.error("Configuration file is invalid. Please fix the JSON syntax.")
        return {}


def save_config(config):
    """Helper function to save the configuration file."""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        logger.error(f"Failed to save configuration file: {e}")


class BattleMetrics(commands.Cog):
    """Cog for managing BattleMetrics-related functionality."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name='set-ban-channel', description="Set the channel to send ban notifications to.")
    async def set_ban_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """
        Sets the ban notification channel in the configuration file.

        Note:
        - Only the bot's owner can execute this command.
        """
        # Load configuration file
        config = load_config()

        # Ensure the owner ID is set in the configuration file
        owner_id = config.get('owner_id')
        if owner_id is None:
            await interaction.response.send_message(
                "The owner has not been set. Please run `/set-owner` first.",
                ephemeral=True
            )
            return

        # Check if the command executor is the bot's owner
        if interaction.user.id != owner_id:
            await interaction.response.send_message(
                "You are not authorized to execute this command.",
                ephemeral=True
            )
            return

        # Update and save the configuration with the new ban channel
        config['ban_channel'] = channel.id
        save_config(config)

        # Confirmation message
        await interaction.response.send_message(
            f"Ban notification channel set to {channel.mention}."
        )


async def setup(bot):
    """Asynchronously sets up the BattleMetrics cog."""
    await bot.add_cog(BattleMetrics(bot))
