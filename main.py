import discord
from discord.ext import commands
from logger import logger
import os


class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.messages = True
        intents.message_content = True

        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Sync slash commands with Discord
        await self.tree.sync()  # Ensure commands are synced once globally
        logger.info("Slash commands synced with Discord.")

    async def on_ready(self):
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        print(f"Bot is logged in as {self.user}")


# Initialize the bot
bot = MyBot()


# Example of a slash command
@bot.tree.command(name="ping", description="Check if the bot is online.")
async def ping(interaction: discord.Interaction):
    """Slash command to test if the bot is online."""
    await interaction.response.send_message("Pong!", ephemeral=True)


async def main():
    """Main asynchronous entry point for the bot."""
    try:
        # Load additional extensions (cogs)
        await bot.load_extension("commands.owner_commands")
        logger.info("Loaded owner_commands extension successfully.")
        await bot.load_extension("commands.admin_commands")
        logger.info("Loaded admin_commands extension successfully.")
    except Exception as e:
        logger.error(f"Failed to load extension: {e}")
        raise

    # Get the bot token from environment variables
    TOKEN = os.getenv("DISCORD_TOKEN")
    if not TOKEN:
        logger.error("DISCORD_TOKEN environment variable not set")
        raise ValueError("Please set the DISCORD_TOKEN environment variable.")

    # Start the bot
    logger.info("Starting bot...")
    await bot.start(TOKEN)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
