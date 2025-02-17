import os
import json
import discord
from discord.ext import commands, tasks
from discord import app_commands
from logger import logger
import config
import subprocess
import re


class Performance(commands.Cog):
    """A cog for performance-related commands and monitoring."""

    def __init__(self, bot):
        self.bot = bot
        self.stats_channel_id = None
        self.last_message_id = None
        self.current_players = 0
        self.monitor_tmux.start()  # Start the monitoring task

    def cog_unload(self):
        """Cleanup when cog is unloaded."""
        self.monitor_tmux.cancel()

    @app_commands.command(name="set_stats_channel", description="Set the statistics channel.")
    async def set_stats_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        try:
            # Step 1: Defer the response
            await interaction.response.defer(ephemeral=True)

            # Step 2: Check if the configuration file exists
            if not os.path.exists(config.CONFIG_FILE):
                error_message = "The configuration file could not be found."
                logger.error(f"[set_stats_channel] {error_message}")
                await interaction.followup.send(error_message, ephemeral=True)
                return

            # Step 3: Load the configuration file
            try:
                with open(config.CONFIG_FILE, "r") as config_file:
                    configuration = json.load(config_file)
            except json.JSONDecodeError:
                error_message = "Configuration file is invalid or corrupted."
                logger.error(f"[set_stats_channel] {error_message}")
                await interaction.followup.send(error_message, ephemeral=True)
                return

            # Step 4: Verify admin role is correctly set up
            admin_role_id = configuration.get("admin_role")
            if not admin_role_id:
                error_message = "Admin role ID is missing in the configuration."
                logger.error(f"[set_stats_channel] {error_message}")
                await interaction.followup.send(error_message, ephemeral=True)
                return

            # Step 5: Verify the user has the admin role
            if not any(role.id == admin_role_id for role in interaction.user.roles):
                error_message = "You do not have permission to use this command."
                logger.warning(f"[set_stats_channel] Permission denied for user {interaction.user}.")
                await interaction.followup.send(error_message, ephemeral=True)
                return

            # Step 6: Validate the channel is accessible
            if not isinstance(channel, discord.TextChannel):
                error_message = "The selected channel is not a text channel."
                logger.error(f"[set_stats_channel] {error_message}")
                await interaction.followup.send(error_message, ephemeral=True)
                return

            # Step 7: Update the configuration with the channel ID
            configuration["stats_channel"] = channel.id
            with open(config.CONFIG_FILE, "w") as config_file:
                json.dump(configuration, config_file, indent=4)

            # Update the cog's channel ID
            self.stats_channel_id = channel.id

            logger.info(f"[set_stats_channel] Channel updated to {channel.name} ({channel.id}) by {interaction.user}.")
            await interaction.followup.send(
                f"The statistics channel has been successfully updated to {channel.mention}.",
                ephemeral=True
            )

        except discord.Forbidden:
            error_message = "The bot does not have sufficient permissions to perform this action."
            logger.error(f"[set_stats_channel] {error_message}")
            await interaction.followup.send(error_message, ephemeral=True)

        except Exception as e:
            error_message = f"An unexpected error occurred: {e}"
            logger.error(f"[set_stats_channel] {error_message}")
            await interaction.followup.send(
                f"An unexpected error occurred while processing the command. Please try again later.",
                ephemeral=True
            )

    @tasks.loop(seconds=60)
    async def monitor_tmux(self):
        """Monitor the TMux session for server performance data."""
        if not self.stats_channel_id:
            logger.warning("[monitor_tmux] No statistics channel configured.")
            return

        try:
            stats_channel = self.bot.get_channel(self.stats_channel_id)
            if not stats_channel:
                logger.error(f"[monitor_tmux] Could not find channel with ID {self.stats_channel_id}.")
                return

            # Fetch TMux server performance data
            performance_data = self.fetch_tmux_performance_data(config.TMUX_SESSION)

            if not performance_data:
                logger.error("[monitor_tmux] Failed to retrieve performance data.")
                return

            # Update presence (showing player count)
            if performance_data['players'] != self.current_players:
                self.current_players = performance_data['players']
                await self.update_presence(performance_data['players'])

            # Post the performance statistics
            new_message_id = await self.post_performance_statistics(stats_channel, performance_data,
                                                                    self.last_message_id)
            if new_message_id:
                self.last_message_id = new_message_id

        except Exception as e:
            logger.error(f"[monitor_tmux] Error occurred: {e}")

    @monitor_tmux.before_loop
    async def before_monitor_tmux(self):
        """Wait until the bot is ready before starting the monitor loop."""
        await self.bot.wait_until_ready()

    def fetch_tmux_performance_data(self, session_name):
        """Parse TMux performance data."""
        try:
            cmd = f"tmux capture-pane -S -1000 -E -1 -t {session_name} -p"
            output = subprocess.check_output(cmd, shell=True).decode('utf-8')

            fps_lines = [line.strip() for line in output.split('\n') if
                         line.strip().startswith('DEFAULT') and 'FPS:' in line]

            if fps_lines:
                latest_fps_line = fps_lines[-1]
                return self.parse_fps_line(latest_fps_line)
            else:
                logger.warning("[fetch_tmux_performance_data] No FPS lines found in TMux output")
                return None
        except subprocess.CalledProcessError as e:
            logger.error(f"[fetch_tmux_performance_data] Failed to read TMux session: {session_name}")
            logger.error(f"Error: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"[fetch_tmux_performance_data] Error occurred: {str(e)}")
            return None

    def parse_fps_line(self, line):
        """Parse the FPS line from TMux output."""
        try:
            fps_match = re.search(r'FPS: ([\d.]+)', line)
            frame_time_match = re.search(r'frame time \(avg: ([\d.]+) ms, min: ([\d.]+) ms, max: ([\d.]+) ms\)', line)
            mem_match = re.search(r'Mem: (\d+)', line)
            ai_match = re.search(r'AI: (\d+)', line)
            veh_match = re.search(r'Veh: (\d+)\s*\(', line)

            if not fps_match:
                logger.warning("[parse_fps_line] No FPS match found in line")
                return None

            return {
                'fps': float(fps_match.group(1)),
                'frame_time_avg': float(frame_time_match.group(1)) if frame_time_match else 0.0,
                'frame_time_max': float(frame_time_match.group(3)) if frame_time_match else 0.0,
                'memory': int(mem_match.group(1)) if mem_match else 0,
                'ai': int(ai_match.group(1)) if ai_match else 0,
                'vehicles': int(veh_match.group(1)) if veh_match else 0,
                'players': len(re.findall(r'Players connected: (\d+)', line)),
            }
        except Exception as e:
            logger.error(f"[parse_fps_line] Error parsing FPS line: {e}")
            return None

    async def post_performance_statistics(self, channel, performance_data, last_message_id=None):
        """Post or update the performance statistics message in Discord."""
        try:
            if last_message_id:
                try:
                    previous_message = await channel.fetch_message(last_message_id)
                    await previous_message.delete()
                    logger.info(
                        f"[post_performance_statistics] Deleted previous performance message: {last_message_id}")
                except discord.NotFound:
                    pass

            message = self.format_performance_message(performance_data)
            new_message = await channel.send(message)
            return new_message.id
        except Exception as e:
            logger.error(f"[post_performance_statistics] Error occurred: {e}")
            return None

    def format_performance_message(self, perf_data):
        """Format the performance data for display."""
        if not perf_data:
            return "Error parsing server status"

        return (
            "🖥️ **Server Performance Report**\n"
            f"FPS: **{perf_data['fps']:.1f}** (Avg Frame Time: {perf_data['frame_time_avg']:.1f}ms, "
            f"Max Frame Time: {perf_data['frame_time_max']:.1f}ms)\n"
            f"Memory: **{perf_data['memory'] // 1024:,} MB**\n\n"
            "👥 **Server Population**\n"
            f"Players: **{perf_data['players']}**\n"
            f"AI Units: **{perf_data['ai']}**\n"
            f"Vehicles: **{perf_data['vehicles']}**"
        )

    async def update_presence(self, player_count):
        """Update the bot's presence with the current player count."""
        try:
            await self.bot.change_presence(activity=discord.Game(name=f"{player_count}/128 Playing"))
            logger.info(f"[update_presence] Updated presence to {player_count}/128 Playing")
        except Exception as e:
            logger.error(f"[update_presence] Error occurred: {e}")


async def setup(bot):
    """Entry point for bot to load this cog."""
    await bot.add_cog(Performance(bot))
