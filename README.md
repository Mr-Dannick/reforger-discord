# Arma Reforger Discord Bot

A Discord bot for managing Arma Reforger servers on Ubuntu with BattleMetrics integration, performance monitoring, and server management capabilities.

## Features

- **Real-time Performance Monitoring**
  - FPS tracking and reporting
  - Memory usage monitoring
  - Player count tracking
  - AI and vehicle count monitoring
  - Network status and packet loss detection

- **BattleMetrics Integration**
  - Automatic ban notifications
  - Real-time ban synchronization
  - Configurable ban notification channel

- **Server Management**
  - Remote server restart capability
  - Role-based access control
  - Customizable service management

- **Rich Presence**
  - Live player count display (updates every 60 seconds)
  - Server status integration

## Requirements

- Ubuntu Server
- Python 3
- Discord Bot Token
- tmux
- BattleMetrics API Token (optional)
- Arma Reforger Server running in tmux

## Installation

1. Clone this repository to your Ubuntu server:
   ```bash
   git clone [repository-url]
   cd [repository-name]
   ```

2. Install Python dependencies:
   ```bash
   pip3 install discord.py aiohttp
   ```

3. Configure the service file:
   - Copy `discordbot.service` to systemd:
     ```bash
     sudo cp discordbot.service /etc/systemd/system/
     ```
   - Edit the service file to include your Discord token use the field Environment=DISCORD_TOKEN=: 
     ```bash
     sudo nano /etc/systemd/system/discordbot.service
     ```

4. Enable and start the service:
   ```bash
   sudo systemctl enable discordbot.service
   sudo systemctl start discordbot.service
   ```

## Configuration

### Initial Setup
The bot will create a `config.json` file on first run with these default values:
```json
{
    "fps_channel": null,
    "bans_channel": null,
    "owner_id": null,
    "admin_role": null,
    "service_name": "arma3server",
    "last_message_id": null,
    "posted_bans": [],
    "battlemetrics_token": null,
    "battlemetrics_server_id": null
}
```

### tmux Configuration
The bot expects your Arma Reforger server to run in a tmux session. Default session name is `arma_reforger`. You can modify this in `bot.py`:
```python
TMUX_SESSION = 'arma_reforger'  # Change this to your tmux session name
```

## Available Commands

### Owner Commands
- `/set-owner [user_id]` - Set the bot owner (one-time use)
- `/set-admin-role [@role]` - Set the admin role for privileged commands
- `/set-battlemetrics [api_token] [server_id]` - Configure BattleMetrics integration
- `/clear-bans` - Clear the list of posted bans

### Admin Commands
- `/restart` - Restart the Arma Reforger server service
- `/set-service [service_name]` - Set the service name for restart command
- `/set-bans-channel` - Set the channel for ban notifications

### General Commands
- `/fps-channel` - Set the current channel for performance updates

## Performance Monitoring

The bot monitors and reports:
- Server FPS
- Frame time (average, min, max)
- Memory usage
- Player count
- AI unit count
- Vehicle count
- Connected clients
- Packet loss statistics

Updates are posted every 60 seconds to the designated FPS channel.

## BattleMetrics Integration

To enable BattleMetrics integration:
1. Get your API token from [BattleMetrics Developers](https://www.battlemetrics.com/developers)
2. Find your server ID (URL format: `https://www.battlemetrics.com/servers/reforger/[SERVER-ID]`)
3. Use `/set-battlemetrics` command to configure

## Logging

The bot maintains logs in `bot.log` with rotation (5MB per file, keeping 5 files). Logs include:
- Performance data
- Command usage
- Error tracking
- Configuration changes

## Troubleshooting

1. Check service status:
   ```bash
   sudo systemctl status discordbot.service
   ```

2. View logs:
   ```bash
   tail -f bot.log
   ```

3. Common issues:
   - Verify tmux session name matches configuration
   - Ensure proper Discord bot permissions
   - Check service user permissions for restart command

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

Feel free to submit issues and enhancement requests.

## Support

For support, please open an issue on the GitHub repository.