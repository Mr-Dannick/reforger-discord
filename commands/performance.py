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

        # Load the stats_channel_id from the configuration file
        self.load_configuration()

        # Start the monitoring loop
        self.monitor_tmux.start()

    def cog_unload(self):
        """Cleanup when cog is unloaded."""
        self.monitor_tmux.cancel()

    def load_configuration(self):
        """Load stats_channel_id and other configurations."""
        if os.path.exists(config.CONFIG_FILE):
            try:
                with open(config.CONFIG_FILE, "r") as config_file:
                    configuration = json.load(config_file)
                    self.stats_channel_id = configuration.get("stats_channel", None)
                    if self.stats_channel_id:
                        logger.info(f"[Performance] Loaded stats_channel_id: {self.stats_channel_id}")
                    else:
                        logger.warning("[Performance] stats_channel_id not set in the configuration.")
            except json.JSONDecodeError:
                logger.error("[Performance] Configuration file is invalid or corrupted.")
            except Exception as e:
                logger.error(f"[Performance] Unexpected error loading configuration: {e}")
        else:
            logger.warning("[Performance] Configuration file not found.")

    @app_commands.command(name="set_stats_channel", description="Set the statistics channel.")
    async def set_stats_channel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Command to set the statistics channel and save it to the configuration."""
        await interaction.response.defer(ephemeral=True)

        try:
            if not os.path.exists(config.CONFIG_FILE):
                await interaction.followup.send("Configuration file not found.", ephemeral=True)
                logger.error("[set_stats_channel] Configuration file not found.")
                return

            try:
                with open(config.CONFIG_FILE, "r") as config_file:
                    configuration = json.load(config_file)
            except json.JSONDecodeError:
                await interaction.followup.send("Configuration file is corrupted.", ephemeral=True)
                logger.error("[set_stats_channel] Configuration file is invalid.")
                return

            admin_role_id = configuration.get("admin_role")
            if not admin_role_id or not any(role.id == admin_role_id for role in interaction.user.roles):
                await interaction.followup.send("You do not have permission to use this command.", ephemeral=True)
                logger.warning("[set_stats_channel] User does not have adequate permissions.")
                return

            configuration["stats_channel"] = channel.id
            with open(config.CONFIG_FILE, "w") as config_file:
                json.dump(configuration, config_file, indent=4)

            self.stats_channel_id = channel.id
            logger.info(f"[set_stats_channel] Stats channel updated to {channel.name} ({channel.id}).")
            await interaction.followup.send(f"Statistics channel updated to {channel.mention}.", ephemeral=True)

        except Exception as e:
            logger.error(f"[set_stats_channel] Unexpected error: {e}")
            await interaction.followup.send("An error occurred while updating the channel.", ephemeral=True)

    @tasks.loop(seconds=60)
    async def monitor_tmux(self):
        """Monitor the TMux session for server performance data and post updates."""
        if not self.stats_channel_id:
            logger.warning("[monitor_tmux] Statistics channel is not set.")
            return

        stats_channel = self.bot.get_channel(self.stats_channel_id)
        if not stats_channel:
            logger.error(f"[monitor_tmux] Channel with ID {self.stats_channel_id} not found.")
            return

        try:
            # Fetch performance data
            performance_data = self.fetch_tmux_performance_data(config.TMUX_SESSION)

            if not performance_data:
                logger.error("[monitor_tmux] No performance data retrieved.")
                return

            # Log the number of players and FPS detected
            logger.info(
                f"[monitor_tmux] Detected Players: {performance_data['players']}, FPS: {performance_data['fps']:.1f}"
            )

            # Update bot presence if player count changes
            if performance_data['players'] != self.current_players:
                self.current_players = performance_data['players']
                await self.update_presence(performance_data['players'])

            # Post or update statistics in the Discord channel
            new_message_id = await self.post_performance_statistics(stats_channel, performance_data,
                                                                    self.last_message_id)
            if new_message_id:
                self.last_message_id = new_message_id

        except Exception as e:
            logger.error(f"[monitor_tmux] Error fetching or posting performance data: {e}")

    @monitor_tmux.before_loop
    async def before_monitor_tmux(self):
        """Wait until the bot is ready before starting the monitor loop."""
        await self.bot.wait_until_ready()

    def fetch_tmux_performance_data(self, session_name):
        """Fetch and parse TMux session data."""
        try:
            cmd = f"tmux capture-pane -S -1000 -E -1 -t {session_name} -p"
            output = subprocess.check_output(cmd, shell=True).decode("utf-8")

            # Extract only relevant lines
            fps_lines = [line.strip() for line in output.split("\n") if 'Players connected' in line or 'FPS:' in line]
            if not fps_lines:
                logger.warning("[fetch_tmux_performance_data] No relevant output found.")
                return None

            return self.parse_fps_line(fps_lines)

        except subprocess.CalledProcessError as e:
            logger.error(f"[fetch_tmux_performance_data] TMux session error: {e}")
            return None
        except Exception as e:
            logger.error(f"[fetch_tmux_performance_data] Parsing error: {e}")
            return None

    def parse_fps_line(self, lines):
        """Parse performance data (FPS, players, etc.) from TMux output lines."""
        try:
            current_players = 0
            fps = 0.0
            frame_time_avg = 0.0
            frame_time_max = 0.0

            # Loop through relevant lines to extract data
            for line in lines:
                # Match FPS
                fps_match = re.search(r"FPS: ([\d.]+)", line)
                if fps_match:
                    fps = float(fps_match.group(1))

                # Match frame times
                frame_time_match = re.search(r"frame time \(avg: ([\d.]+) ms, .*max: ([\d.]+) ms\)", line)
                if frame_time_match:
                    frame_time_avg = float(frame_time_match.group(1))
                    frame_time_max = float(frame_time_match.group(2))

                # Match player count
                players_match = re.search(r"Players connected: (\d+)", line)
                if players_match:
                    current_players = int(players_match.group(1))

            return {
                'fps': fps,
                'frame_time_avg': frame_time_avg,
                'frame_time_max': frame_time_max,
                'players': current_players,
            }

        except Exception as e:
            logger.error(f"[parse_fps_line] Error parsing line: {e}")
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
        """Format the performance statistics message."""
        if not perf_data:
            return "**Error:** Unable to retrieve server performance data."

        return (
            "🖥️ **Server Performance Report**\n"
            f"FPS: **{perf_data['fps']:.1f}** (Avg Frame Time: {perf_data['frame_time_avg']:.1f}ms, "
            f"Max Frame Time: {perf_data['frame_time_max']:.1f}ms)\n"
            f"Players Connected: **{perf_data['players']}**"
        )

    async def update_presence(self, player_count):
        """Update the bot's presence to show the current player count."""
        try:
            await self.bot.change_presence(activity=discord.Game(name=f"{player_count} Players Connected"))
            logger.info(f"[update_presence] Updated presence to {player_count} Players Connected.")
        except Exception as e:
            logger.error(f"[update_presence] Failed to update presence: {e}")


async def setup(bot):
    """Cog setup entry point."""
    await bot.add_cog(Performance(bot))
