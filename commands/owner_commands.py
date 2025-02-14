import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import config


class OwnerCommands(commands.Cog):
    """Commands related to managing bot ownership using slash commands."""

    def is_user_owner(self, user_id: int) -> bool:
        """Returns True if the provided user ID matches the owner ID in the config."""
        return self.config.get("owner_id") == user_id
    def __init__(self, bot):
        self.bot = bot
        self.config_file = config.CONFIG_FILE
        self.config = self.load_config()

    def load_config(self):
        """Load the configuration from the configuration file."""
        if not os.path.exists(self.config_file):
            with open(self.config_file, "w") as file:
                json.dump({"owner_id": None}, file, indent=4)
        with open(self.config_file, "r") as file:
            return json.load(file)

    def save_config(self, config_data):
        """Save the configuration to the configuration file."""
        with open(self.config_file, "w") as file:
            json.dump(config_data, file, indent=4)

    @app_commands.command(name="setowner", description="Set the bot's owner (can only be set once).")
    async def set_owner(self, interaction: discord.Interaction, user: discord.User):
        if self.config["owner_id"] is not None:
            await interaction.response.send_message(
                f"Owner already set to user with ID: {self.config['owner_id']}.",
                ephemeral=True,
            )
            return
        self.config["owner_id"] = user.id
        self.save_config(self.config)
        await interaction.response.send_message(
            f"Owner set to user with ID: {user.id}", ephemeral=True
        )

    @app_commands.command(name="getowner", description="Get the current owner's ID.")
    async def get_owner(self, interaction: discord.Interaction):
        owner_id = self.config.get("owner_id")
        if owner_id is None:
            await interaction.response.send_message(
                "No owner has been set yet.", ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"The current owner is user with ID: {owner_id}", ephemeral=True
            )

    @app_commands.command(name="set-moderator", description="set the rank that is allowed to restart the gameserver.")
    async def set_moderator(self, interaction: discord.Interaction, role: discord.Role):
        if not self.is_user_owner(interaction.user.id):
            await interaction.response.send_message("You are not the bot owner! And can't use this command", ephemeral=True)
            return
        self.config["admin_role"] = role.id
        self.save_config(self.config)
        await interaction.response.send_message(
            f"Moderator rank set to: {role.name}", ephemeral=True
        )

    @commands.Cog.listener()
    async def on_command(self, ctx):
        owner_id = self.config.get("owner_id")
        if owner_id and ctx.command.name != "setowner" and ctx.author.id != owner_id:
            await ctx.send("You are not allowed to use this command.")
            ctx.command.reset_cooldown(ctx)


async def setup(bot: commands.Bot):
    cog = OwnerCommands(bot)
    await bot.add_cog(cog)



