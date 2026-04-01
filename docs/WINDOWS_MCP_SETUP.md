# Windows MCP Server Setup Guide

This guide explains how to set up and use the Tipistore Windows MCP (Model Context Protocol) server to interact with the Kali Linux container from Claude on Windows.

## Prerequisites

- **Windows 10/11** with WSL2 enabled (for local Docker Desktop setup)
- **Docker Desktop for Windows** (with WSL2 backend) OR access to a remote Docker host
- **Node.js 18+** installed on Windows
- **uv** package manager (optional but recommended)
- **Claude app** on Windows with MCP server support

## Installation

### Step 1: Clone or Update Tipistore Repository

If you haven't already, clone the tipistore repository:

```bash
git clone https://github.com/crashcart/tipistore.git
cd tipistore
```

Or update to the latest version with Windows MCP support:

```bash
git pull origin main
```

### Step 2: Install Dependencies

Using npm:

```bash
npm install
```

Or using uv (faster):

```bash
uv pip install
# Then install Node dependencies
npm install
```

The installation includes the `@modelcontextprotocol/sdk` package required for the MCP server.

### Step 3: Verify Docker is Running

Ensure Docker Desktop is running with WSL2 backend:

```bash
docker ps
```

You should see output showing running containers. If Docker isn't available, see [Docker Desktop Setup](#docker-desktop-setup) below.

### Step 4: Start the Kali Container

If the Kali container isn't already running:

```bash
docker-compose up -d kali-linux
```

Verify it's running:

```bash
docker ps | grep kali-linux
```

You should see a `kali-linux` container in the running state.

## Running the Windows MCP Server

### Using npm

```bash
npm run mcp:windows
```

### Using uv

```bash
uv run --directory . node windows-mcp-init.js
```

### Using Node directly

```bash
node windows-mcp-init.js
```

You should see output similar to:

```
[timestamp] INFO: Starting Tipistore Windows MCP Server
[timestamp] INFO: Configuration { dockerSocket: 'npipe:////./pipe/docker_engine', kaliContainer: 'kali-linux', platform: 'win32' }
[timestamp] INFO: Initializing Docker connection
[timestamp] INFO: Docker connection successful
[timestamp] INFO: Kali container verified and ready
[timestamp] INFO: MCP Server started and connected
```

If you see errors, consult the [Troubleshooting](#troubleshooting) section.

## Configuration

### Environment Variables

Configure the MCP server using environment variables:

```bash
# In .env or as shell environment variables
MCP_DOCKER_SOCKET=npipe:////./pipe/docker_engine    # Windows Docker Desktop (default)
MCP_KALI_CONTAINER=kali-linux                        # Container name (default)
MCP_LOG_LEVEL=info                                   # Log level: debug, info, warn, error
```

### Docker Connection Modes

The MCP server supports multiple Docker connection modes:

#### 1. Local Docker Desktop (Default)

For Windows 10/11 with Docker Desktop and WSL2:

```bash
MCP_DOCKER_SOCKET=npipe:////./pipe/docker_engine
```

This is the default and works automatically on Windows.

#### 2. Remote Docker via HTTP

For a Docker daemon running on a remote machine (e.g., Linux server):

```bash
MCP_DOCKER_SOCKET=http://192.168.1.100:2375
# For HTTPS:
MCP_DOCKER_SOCKET=https://192.168.1.100:2376
```

⚠️ **Warning**: Ensure your remote Docker daemon is properly secured or use SSH tunneling instead.

#### 3. Remote Docker via SSH (Advanced)

For SSH connections to a remote Docker host, set up Docker context first:

```bash
# On Windows PowerShell
docker context create remote --docker "host=ssh://user@remote-host"
docker context use remote
```

Then the MCP server will use that context.

## Integrating with Claude

### Adding the MCP Server to Claude

1. Open Claude on Windows
2. Go to **Settings** → **Developer** → **MCP Servers**
3. Click **Add MCP Server**
4. Configure:
   - **Name**: `Tipistore Windows MCP`
   - **Type**: `stdio`
   - **Command**: `node` (or full path)
   - **Arguments**: `"path/to/tipistore/windows-mcp-init.js"`
   - **Environment Variables**:
     ```
     MCP_DOCKER_SOCKET=npipe:////./pipe/docker_engine
     MCP_KALI_CONTAINER=kali-linux
     MCP_LOG_LEVEL=info
     ```

5. Click **Save** and restart Claude

### Using Kali Tools in Claude

Once configured, Claude will have access to the following resources and tools:

**Resources:**
- `kali://tools` - List of available Kali tools
- `kali://status` - Container status
- `kali://container-info` - Detailed container information

**Tools:**
- `execute_kali_command` - Run bash commands in Kali
- `list_kali_tools` - List tools by category
- `get_tool_help` - Get help for a specific tool
- `get_container_logs` - View container logs

**Example Claude Prompts:**

```
"List all reconnaissance tools available in Kali"
```

```
"Execute: nmap -sV 192.168.1.1"
```

```
"Show me the help for sqlmap"
```

```
"Run 'whoami' in the Kali container"
```

## Docker Desktop Setup

If you don't have Docker Desktop installed:

### Windows 10/11 Pro, Enterprise, or Education:

1. Download [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop)
2. Run the installer
3. Enable WSL2 when prompted
4. Restart your computer
5. Open Docker Desktop and wait for it to initialize

### Windows 10/11 Home:

1. Enable WSL2 (Windows Subsystem for Linux 2):
   ```powershell
   wsl --install
   # Then restart your computer
   ```

2. Install Docker Desktop for Windows Home edition
3. Configure Docker to use WSL2 as the backend

### Verify Installation

```bash
docker --version
docker run hello-world
```

## Troubleshooting

### Error: "Docker connection failed" or "ENOENT"

**Cause**: Docker Desktop is not running or docker socket is not available

**Solution**:
1. Open Docker Desktop application
2. Wait 30 seconds for initialization
3. Verify Docker is running: `docker ps`
4. Restart the MCP server

### Error: "Kali container not found"

**Cause**: The Kali container is not running or has a different name

**Solution**:
```bash
# Check running containers
docker ps

# If not running, start it
docker-compose up -d kali-linux

# Verify it's named correctly
docker ps | grep -i kali
```

If the container has a different name, set the environment variable:

```bash
MCP_KALI_CONTAINER=your-custom-container-name npm run mcp:windows
```

### Error: "Command timeout"

**Cause**: The command is taking longer than 30 seconds

**Solution**:
- Increase the timeout in Claude when executing the command:
  ```
  Execute with timeout 60000: nmap -sV -p 1-10000 192.168.1.100
  ```

### Error: "Permission denied" or "Access denied"

**Cause**: Docker socket permissions issue

**Solution** (Windows):
- Ensure Docker Desktop is running as an administrator
- Restart Docker Desktop
- Check that your Windows user has Docker permissions

### MCP Server Won't Start

**Debug Steps**:

1. Check logs by setting debug level:
   ```bash
   MCP_LOG_LEVEL=debug npm run mcp:windows
   ```

2. Verify all prerequisites:
   ```bash
   node --version  # Should be v18 or higher
   docker --version
   npm --version
   ```

3. Try direct execution:
   ```bash
   node windows-mcp-init.js
   ```

4. Check Docker connectivity:
   ```bash
   docker ps
   docker info
   ```

### Claude Can't Find MCP Server

1. Verify the path to `windows-mcp-init.js` is correct in Claude settings
2. Use full absolute path instead of relative path
3. Ensure `node` or `node.exe` is in your PATH
4. Restart Claude completely
5. Check Claude's logs in `%APPDATA%\Claude\logs\`

## Advanced Configuration

### Using with a Remote Linux Server

If you have tipistore running on a Linux server and want to access it from Windows:

1. **Option A: SSH Tunneling**
   ```bash
   # Create SSH tunnel
   ssh -L 2375:localhost:2375 user@remote-server
   
   # Then configure MCP server
   MCP_DOCKER_SOCKET=http://localhost:2375 npm run mcp:windows
   ```

2. **Option B: Enable Remote Docker API (Less Secure)**
   ```bash
   # On remote server, enable Docker remote API
   # Then connect from Windows
   MCP_DOCKER_SOCKET=http://remote-server:2375 npm run mcp:windows
   ```

### Rate Limiting

By default, the MCP server doesn't rate limit. For production, consider:
- Claude's native rate limits
- Docker daemon rate limits
- Manual command throttling

### Logging

Control verbosity with `MCP_LOG_LEVEL`:

- `error` - Only errors
- `warn` - Warnings and errors
- `info` - General information (default)
- `debug` - Detailed debug output

Example:
```bash
MCP_LOG_LEVEL=debug npm run mcp:windows
```

## Security Considerations

### ⚠️ Important Security Notes

1. **Docker Socket Access**: The Docker socket gives full control over containers. Only run the MCP server on trusted machines.

2. **Command Execution**: The MCP server executes arbitrary bash commands in the Kali container. Ensure only trusted users can access Claude.

3. **Remote Connections**: If using remote Docker (SSH or HTTP), ensure:
   - SSH keys are properly secured
   - HTTPS is used with proper certificates
   - Firewall rules restrict access to Docker daemon

4. **Container Isolation**: The Kali container has access to the Docker socket. Be cautious with credentials stored in containers.

### Best Practices

1. Run the MCP server on the same machine as Docker Desktop
2. Use strong authentication for Claude
3. Regularly update Docker, Node.js, and npm packages
4. Monitor and log command execution
5. Use SSH tunneling for remote access
6. Restrict MCP server process to necessary privileges

## Performance Tips

1. **Local Docker**: Best performance - run Docker Desktop and MCP server on same Windows machine

2. **WSL2 Optimization**: 
   - Allocate sufficient RAM to WSL2 in `.wslconfig`
   - Keep WSL2 updated

3. **Command Optimization**:
   - Use appropriate timeouts (not too long for quick commands)
   - Reduce output verbosity when possible
   - Use filters in nmap/scanning commands to reduce data

4. **Container Resources**:
   - Allocate sufficient Docker resources in Docker Desktop settings
   - Monitor container CPU/memory usage

## Uninstalling

To remove the MCP server:

1. Remove from Claude settings (Settings → Developer → MCP Servers)
2. Delete `windows-mcp-init.js` (optional)
3. Keep other tipistore components intact

The MCP server is independent and won't affect the web interface.

## Support & Troubleshooting

For additional help:

1. Check the [Troubleshooting](#troubleshooting) section
2. Review logs with `MCP_LOG_LEVEL=debug`
3. Consult [MCP Protocol Documentation](https://modelcontextprotocol.io/)
4. Report issues on the tipistore GitHub repository

## Next Steps

- Configure Claude to use the MCP server
- Test basic commands (e.g., `nmap -h`)
- Explore available Kali tools through Claude
- Set up for remote access if needed

Happy hacking! 🔓
