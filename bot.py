# Import required Discord.py libraries for bot functionality
import discord
from discord import app_commands, Activity, ActivityType
from discord.ext import commands, tasks
import subprocess
import re
import json
import os
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
import aiohttp

# Constants
CONFIG_FILE = 'config.json' #name of the config file. The file will be created on the first run of the bot.
TMUX_SESSION = 'arma_reforger' #give the name of the tmux session that is used for your game server
LOG_FILE = 'bot.log' #Name of the log file. Created in the same directory

# Set up logging
logger = logging.getLogger('TMuxBot')
logger.setLevel(logging.INFO)
handler = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=5)  # 5MB per file, keep 5 files
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

class TMuxMonitorBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)
        
        self.config = self.load_config()
        self.last_message_id = None
        self.current_players = 0
        self.session = None  # aiohttp session for API requests
    
    async def setup_hook(self):
        logger.info(f"Bot is ready and monitoring TMux session: {TMUX_SESSION}")
        self.session = aiohttp.ClientSession()  # Initialize API session
        self.monitor_tmux.start()
        await self.tree.sync()

    async def close(self):
        if self.session:
            await self.session.close()
        await super().close()

    def load_config(self):
        default_config = {
            'fps_channel': None, #Separate channel for performance notifications
            'bans_channel': None,  # Separate channel for ban notifications
            'owner_id': None, #ID of the bot owner
            'admin_role': None, #Admins that can use the /restart command
            'service_name': 'arma3server', #Ubuntu service name that can be restarted with /restart
            'last_message_id': None,
            'posted_bans': [],  # Track which bans we've posted
            'battlemetrics_token': None, #battlemetrics token you can generate at: https://www.battlemetrics.com/developers
            'battlemetrics_server_id': None #server id you can find by going to your server page at battle metrics exapmle: https://www.battlemetrics.com/servers/reforger/31762279 31762279 is the server id
        }
        
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                saved_config = json.load(f)
                default_config.update(saved_config)
        logger.info(f"Loaded config: {default_config}")
        
        self.last_message_id = default_config.get('last_message_id')
        return default_config

    def save_config(self):
        self.config['last_message_id'] = self.last_message_id
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.config, f)
        logger.info(f"Saved config: {self.config}")

    async def fetch_bans(self):
        """Fetch current bans from BattleMetrics API"""
        if not self.config['battlemetrics_token'] or not self.config['battlemetrics_server_id']:
            logger.error("BattleMetrics configuration is incomplete")
            return None

        headers = {
            'Authorization': f"Bearer {self.config['battlemetrics_token']}",
            'Accept': 'application/json'
        }

        try:
            url = f"https://api.battlemetrics.com/bans"
            params = {
                'filter[server]': self.config['battlemetrics_server_id'],
                'filter[expired]': 'false',
                'include': 'user,server'
            }

            async with self.session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"Failed to fetch bans: {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching bans: {str(e)}")
            return None

    def format_performance_message(self, perf_data):
        if not perf_data:
            return "Error parsing server status"

        message = [
            "🖥️ **Server Performance Report**",
            f"FPS: **{perf_data['fps']:.1f}** (Frame Time: avg {perf_data['frame_time_avg']:.1f}ms, max {perf_data['frame_time_max']:.1f}ms)",
            f"Memory: **{perf_data['memory'] // 1024:,} MB**",
            "",
            "👥 **Server Population**",
            f"Players: **{perf_data['players']}**",
            f"AI Units: **{perf_data['ai']}**",
            f"Vehicles: **{perf_data['vehicles']}**",
            "",
            "🌐 **Network Status**",
            f"Connected Clients: **{perf_data['total_clients']}**",
            f"Clients with Packet Loss: **{perf_data['packet_loss_clients']}**"
        ]

        return "\n".join(message)

    async def handle_bans(self, channel, bans_data):
        """Handle posting of new bans"""
        if not bans_data or 'data' not in bans_data:
            return

        for ban in bans_data['data']:
            try:
                ban_id = ban.get('id')
                
                # Skip if we've already posted this ban
                if ban_id in self.config['posted_bans']:
                    continue

                # Get ban attributes
                attributes = ban['attributes']
                reason = attributes.get('reason', 'No reason provided')
                expires = attributes.get('expires')
                
                # Get the name identifier
                identifier = None
                identifiers = attributes.get('identifiers', [])
                for id_entry in identifiers:
                    if id_entry.get('type') == 'name':
                        identifier = id_entry.get('identifier')
                        break
                
                if not identifier:
                    identifier = 'Unknown'
                
                # Format expiration time
                if expires:
                    expires = datetime.fromisoformat(expires.replace('Z', '+00:00'))
                    expires_str = expires.strftime("%Y-%m-%d %H:%M UTC")
                else:
                    expires_str = "Permanent"
                
                ban_message = (
                    "🚫 **New Ban**\n"
                    f"**Player**: {identifier}\n"
                    f"**Reason**: {reason}\n"
                    f"**Expires**: {expires_str}"
                )
                
                # Post the ban message
                await channel.send(ban_message)
                
                # Add to posted bans
                self.config['posted_bans'].append(ban_id)
                self.save_config()
                logger.info(f"Posted new ban for player: {identifier}")

            except Exception as e:
                logger.error(f"Error posting ban entry: {str(e)}")
                continue

    @tasks.loop(seconds=60)
    async def monitor_tmux(self):
        logger.info("Running monitoring loop...")
        
        if self.config['fps_channel'] is None:
            logger.warning("No FPS channel configured")
            return
            
        try:
            # Get TMux performance data
            cmd = f"tmux capture-pane -S -1000 -E -1 -t {TMUX_SESSION} -p"
            output = subprocess.check_output(cmd, shell=True).decode('utf-8')
            
            # Look for player count
            player_lines = [line.strip() for line in output.split('\n') 
                        if 'NETWORK' in line and 'Players connected:' in line]
            player_count = 0
            if player_lines:
                player_match = re.search(r'Players connected: (\d+)', player_lines[-1])
                if player_match:
                    player_count = int(player_match.group(1))
                    logger.info(f"Found player count: {player_count}")
            
            fps_lines = [line.strip() for line in output.split('\n') 
                        if line.strip().startswith('DEFAULT') and 'FPS:' in line]
            
            if fps_lines:
                latest_fps_line = fps_lines[-1]
                parsed_data = self.parse_fps_line(latest_fps_line)
                
                if parsed_data:
                    parsed_data['players'] = player_count
                    
                    if player_count != self.current_players:
                        self.current_players = player_count
                        await self.update_presence()

                    # Handle performance updates
                    performance_channel = self.get_channel(self.config['fps_channel'])
                    if performance_channel:
                        if self.last_message_id:
                            try:
                                previous_message = await performance_channel.fetch_message(self.last_message_id)
                                await previous_message.delete()
                                logger.info(f"Deleted previous performance message: {self.last_message_id}")
                            except discord.NotFound:
                                logger.warning(f"Previous performance message not found: {self.last_message_id}")
                            except Exception as e:
                                logger.error(f"Error deleting previous performance message: {str(e)}")
                        
                        perf_message = self.format_performance_message(parsed_data)
                        new_perf_message = await performance_channel.send(perf_message)
                        self.last_message_id = new_perf_message.id
                        self.save_config()

                    # Handle ban updates
                    if (self.config['battlemetrics_token'] and 
                        self.config['battlemetrics_server_id'] and 
                        self.config['bans_channel']):
                        bans_channel = self.get_channel(self.config['bans_channel'])
                        if bans_channel:
                            bans_data = await self.fetch_bans()
                            if bans_data:
                                await self.handle_bans(bans_channel, bans_data)

                        logger.info("Successfully updated all messages")
                    else:
                        logger.error(f"Could not find required channels or BattleMetrics configuration")
                else:
                    logger.error("Failed to parse FPS data")
            else:
                logger.warning("No FPS lines found in TMux output")
        
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to read TMux session: {TMUX_SESSION}")
            logger.error(f"Error: {str(e)}")
        except Exception as e:
            logger.error(f"Error in monitor loop: {str(e)}")

    @monitor_tmux.before_loop
    async def before_monitor(self):
        await self.wait_until_ready()

    async def on_ready(self):
        await self.update_presence()
        logger.info("Bot presence updated successfully")
    
    def get_current_time(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async def update_presence(self):
        try:
            activity = Activity(
                type=ActivityType.playing,
                name=f"{self.current_players}/128 Playing"
            )
            await self.change_presence(activity=activity)
            logger.info(f"Updated presence: {self.current_players}/128 playing")
        except Exception as e:
            logger.error(f"Error updating presence: {str(e)}")
    
    def has_role(self, member, role_id):
        if role_id is None:
            return False
        return any(role.id == role_id for role in member.roles)
    
    def is_owner(self, user_id):
        return str(user_id) == str(self.config['owner_id'])
    
    def parse_fps_line(self, line):
        try:
            fps_match = re.search(r'FPS: ([\d.]+)', line)
            frame_time_match = re.search(r'frame time \(avg: ([\d.]+) ms, min: ([\d.]+) ms, max: ([\d.]+) ms\)', line)
            mem_match = re.search(r'Mem: (\d+)', line)
            ai_match = re.search(r'AI: (\d+)', line)
            veh_match = re.search(r'Veh: (\d+)\s*\(', line)

            if not fps_match:
                logger.warning("No FPS match found in line")
                return None

            ai_count = int(ai_match.group(1)) if ai_match else 0
            vehicle_count = int(veh_match.group(1)) if veh_match else 0

            data = {
                'fps': float(fps_match.group(1)),
                'frame_time_avg': float(frame_time_match.group(1)) if frame_time_match else 0.0,
                'frame_time_min': float(frame_time_match.group(2)) if frame_time_match else 0.0,
                'frame_time_max': float(frame_time_match.group(3)) if frame_time_match else 0.0,
                'memory': int(mem_match.group(1)) if mem_match else 0,
                'ai': ai_count,
                'vehicles': vehicle_count,
                'total_clients': len(re.findall(r'\[C\d+\]', line)),
                'packet_loss_clients': len(re.findall(r'PktLoss: ([1-9]\d*)/100', line))
            }
            
            logger.debug(f"Parsed data: {data}")
            return data
        except Exception as e:
            logger.error(f"Error parsing FPS line: {str(e)}")
            return None
# Create the bot instance
bot = TMuxMonitorBot()

@bot.tree.command(name="set-owner", description="Set the owner user ID (Can only be used once if owner not set)")
async def set_owner(interaction: discord.Interaction, user_id: str):
    if bot.config['owner_id'] is not None:
        await interaction.response.send_message("Owner has already been set!", ephemeral=True)
        return
    
    bot.config['owner_id'] = user_id
    bot.save_config()
    await interaction.response.send_message(f"Owner has been set to user ID: {user_id}", ephemeral=True)

@bot.tree.command(name="fps-channel", description="Set the channel for performance updates")
async def set_fps_channel(interaction: discord.Interaction):
    bot.config['fps_channel'] = interaction.channel_id
    bot.save_config()
    await interaction.response.send_message(f"Performance updates will now be sent to this channel!", ephemeral=True)

@bot.tree.command(name="set-bans-channel", description="Set the channel for ban notifications")
async def set_bans_channel(interaction: discord.Interaction):
    if not bot.has_role(interaction.user, bot.config['admin_role']) and not bot.is_owner(interaction.user.id):
        await interaction.response.send_message("You need the admin role to use this command!", ephemeral=True)
        return
    
    bot.config['bans_channel'] = interaction.channel_id
    bot.save_config()
    await interaction.response.send_message(f"Ban notifications will now be sent to this channel!", ephemeral=True)

@bot.tree.command(name="set-admin-role", description="Set the admin role (Owner only)")
async def set_admin_role(interaction: discord.Interaction, role: discord.Role):
    if not bot.is_owner(interaction.user.id):
        await interaction.response.send_message("Only the owner can use this command!", ephemeral=True)
        return
    
    bot.config['admin_role'] = role.id
    bot.save_config()
    await interaction.response.send_message(f"Admin role has been set to {role.name}", ephemeral=True)

@bot.tree.command(name="set-service", description="Set the service name to restart")
async def set_service(interaction: discord.Interaction, service_name: str):
    if not bot.has_role(interaction.user, bot.config['admin_role']):
        await interaction.response.send_message("You need the admin role to use this command!", ephemeral=True)
        return
    
    bot.config['service_name'] = service_name
    bot.save_config()
    await interaction.response.send_message(f"Service name has been set to {service_name}", ephemeral=True)

@bot.tree.command(name="restart", description="Restart the server service")
async def restart_service(interaction: discord.Interaction):
    if not bot.has_role(interaction.user, bot.config['admin_role']):
        await interaction.response.send_message("You don't have permission to restart the service!", ephemeral=True)
        return
    
    service_name = bot.config['service_name']
    
    try:
        cmd = f"sudo systemctl restart {service_name}"
        subprocess.run(cmd, shell=True, check=True)
        await interaction.response.send_message(f"Service {service_name} has been restarted successfully!", ephemeral=False)
    except subprocess.CalledProcessError as e:
        await interaction.response.send_message(f"Failed to restart service: {str(e)}", ephemeral=True)

@bot.tree.command(name="set-battlemetrics", description="Set BattleMetrics API configuration (Owner only)")
async def set_battlemetrics(
    interaction: discord.Interaction,
    api_token: str,
    server_id: str
):
    if not bot.is_owner(interaction.user.id):
        await interaction.response.send_message("Only the owner can use this command!", ephemeral=True)
        return
    
    bot.config['battlemetrics_token'] = api_token
    bot.config['battlemetrics_server_id'] = server_id
    bot.save_config()
    await interaction.response.send_message("BattleMetrics configuration has been updated!", ephemeral=True)

@bot.tree.command(name="clear-bans", description="Clear the list of posted bans (Owner only)")
async def clear_bans(interaction: discord.Interaction):
    if not bot.is_owner(interaction.user.id):
        await interaction.response.send_message("Only the owner can use this command!", ephemeral=True)
        return
    
    bot.config['posted_bans'] = []
    bot.save_config()
    await interaction.response.send_message("Posted bans list has been cleared!", ephemeral=True)

if __name__ == "__main__":
    TOKEN = os.getenv('DISCORD_TOKEN')
    if not TOKEN:
        logger.error("DISCORD_TOKEN environment variable not set")
        raise ValueError("Please set the DISCORD_TOKEN environment variable")
    
    logger.info("Starting bot...")
    bot.run(TOKEN)