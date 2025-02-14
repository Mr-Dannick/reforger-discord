import discord
from discord import app_commands
from discord.ext import commands
import subprocess
import json
from logger import logger
from config import SERVICE_NAME  # Import SERVICE_NAME from config.py
import config


class AdminCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="restart", description=f"Restart the service: {SERVICE_NAME}.")
    async def restart(self, interaction: discord.Interaction):
        """Slash command to restart a predefined service on the server."""

        # Acknowledge the interaction to prevent timeout
        await interaction.response.defer(ephemeral=True)

        try:
            # Load the latest configuration dynamically
            with open("config.json", "r") as file:
                config = json.load(file)

            admin_role_id = config.get("admin_role")

            # Check if admin role is set
            if not admin_role_id:
                await interaction.followup.send(
                    "❌ Admin role is not set! Please ask the server owner to set it using `/set-admin-role`.",
                    ephemeral=True,
                )
                logger.warning("Admin role not set in config.")
                return

            # Check if the user has the admin role
            user_roles = [role.id for role in interaction.user.roles]
            if admin_role_id not in user_roles:
                await interaction.followup.send(
                    "❌ You don't have the required role to use this command.",
                    ephemeral=True,
                )
                logger.warning(f"Unauthorized user {interaction.user} tried to execute /restart.")
                return

            # Restart the predefined service asynchronously
            logger.info(f"Attempting to restart service: {SERVICE_NAME}")
            process = await subprocess.create_subprocess_shell(
                f"sudo systemctl restart {SERVICE_NAME}",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                logger.info(f"Service '{SERVICE_NAME}' restarted successfully.")
                await interaction.followup.send(
                    f"✅ Service `{SERVICE_NAME}` restarted successfully.",
                    ephemeral=True
                )
            else:
                # There was an error while restarting the service
                error_message = stderr.decode().strip()
                logger.error(f"Failed to restart service '{SERVICE_NAME}': {error_message}")
                await interaction.followup.send(
                    f"❌ Failed to restart service `{SERVICE_NAME}`. Error: `{error_message}`",
                    ephemeral=True
                )

        except Exception as error:
            # Catch unexpected errors and log them
            logger.exception("An error occurred while handling the /restart command")
            await interaction.followup.send(
                f"❌ An unexpected error occurred: {str(error)}",
                ephemeral=True,
            )


# Function to add this cog to the bot
async def setup(bot):
    await bot.add_cog(AdminCommands(bot))
