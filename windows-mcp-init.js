#!/usr/bin/env node

const { StdioClientTransport } = require('@modelcontextprotocol/sdk/client/stdio.js');
const { Server } = require('@modelcontextprotocol/sdk/server/index.js');
const { ListResourcesRequestSchema, ReadResourceRequestSchema, ListToolsRequestSchema, CallToolRequestSchema } = require('@modelcontextprotocol/sdk/types.js');
const Docker = require('dockerode');
const path = require('path');
const os = require('os');
require('dotenv').config();

// Configuration
const DOCKER_SOCKET = process.env.MCP_DOCKER_SOCKET || getDefaultDockerSocket();
const KALI_CONTAINER = process.env.MCP_KALI_CONTAINER || 'kali-linux';
const LOG_LEVEL = process.env.MCP_LOG_LEVEL || 'info';

// Docker client
let docker = null;
let containerReady = false;

// Available Kali tools reference
const KALI_TOOLS = {
  reconnaissance: ['nmap', 'masscan', 'netdiscover', 'shodan-cli', 'whois', 'dig', 'host'],
  web: ['burp-suite', 'sqlmap', 'nikto', 'dirbuster', 'gobuster', 'zaproxy', 'w3af'],
  exploitation: ['metasploit', 'searchsploit', 'exploit-db'],
  passwords: ['hydra', 'john', 'hashcat', 'medusa', 'crunch'],
  wireless: ['aircrack-ng', 'bettercap', 'airmon-ng', 'wireshark'],
  privilege_escalation: ['linpeas', 'winpeas', 'lse'],
  osint: ['theHarvester', 'recon-ng', 'maltego'],
  reverse_engineering: ['ghidra', 'radare2', 'objdump', 'strings']
};

// Logger utility
function log(level, message, data = {}) {
  const levels = { error: 0, warn: 1, info: 2, debug: 3 };
  if (levels[level] <= levels[LOG_LEVEL]) {
    const timestamp = new Date().toISOString();
    const msg = data && Object.keys(data).length > 0
      ? `[${timestamp}] ${level.toUpperCase()}: ${message} ${JSON.stringify(data)}`
      : `[${timestamp}] ${level.toUpperCase()}: ${message}`;
    console.error(msg); // Use stderr for logging (stdout is for MCP protocol)
  }
}

// Get default Docker socket based on platform
function getDefaultDockerSocket() {
  if (process.platform === 'win32') {
    return 'npipe:////./pipe/docker_engine';
  }
  // For Linux/Mac and WSL2
  return '/var/run/docker.sock';
}

// Initialize Docker connection
async function initializeDocker() {
  try {
    log('info', 'Initializing Docker connection', { socket: DOCKER_SOCKET });

    let dockerOptions = {};

    if (process.platform === 'win32' && DOCKER_SOCKET.startsWith('npipe://')) {
      // Windows named pipe
      const pipePath = DOCKER_SOCKET.replace('npipe://', '');
      dockerOptions = { socketPath: pipePath };
    } else if (DOCKER_SOCKET.startsWith('http://') || DOCKER_SOCKET.startsWith('https://')) {
      // HTTP connection
      const url = new URL(DOCKER_SOCKET);
      dockerOptions = {
        host: url.hostname,
        port: url.port || (url.protocol === 'https:' ? 443 : 2375),
        protocol: url.protocol.replace(':', '')
      };
    } else if (DOCKER_SOCKET.startsWith('ssh://')) {
      // SSH connection - requires agent running
      log('warn', 'SSH Docker connections require Docker context to be set up externally');
      dockerOptions = { socketPath: '/var/run/docker.sock' };
    } else {
      // Unix socket
      dockerOptions = { socketPath: DOCKER_SOCKET };
    }

    docker = new Docker(dockerOptions);

    // Test connection
    await docker.ping();
    log('info', 'Docker connection successful');

    // Verify Kali container
    const containers = await docker.listContainers({ all: true });
    const kaliContainer = containers.find(c => c.Names.includes('/' + KALI_CONTAINER));

    if (!kaliContainer) {
      log('error', `Kali container '${KALI_CONTAINER}' not found`);
      process.exit(1);
    }

    if (kaliContainer.State !== 'running') {
      log('error', `Kali container '${KALI_CONTAINER}' is not running (state: ${kaliContainer.State})`);
      process.exit(1);
    }

    containerReady = true;
    log('info', 'Kali container verified and ready');
  } catch (error) {
    log('error', 'Failed to initialize Docker', { error: error.message });
    process.exit(1);
  }
}

// Execute command in Kali container
async function executeKaliCommand(command, timeout = 30000) {
  if (!containerReady) {
    throw new Error('Kali container not ready');
  }

  try {
    const container = docker.getContainer(KALI_CONTAINER);

    const exec = await container.exec({
      Cmd: ['bash', '-c', command],
      AttachStdout: true,
      AttachStderr: true,
    });

    const stream = await exec.start({ Detach: false });

    let output = '';
    let error = '';

    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        reject(new Error(`Command timeout after ${timeout}ms`));
      }, timeout);

      stream.on('data', (chunk) => {
        output += chunk.toString();
      });

      stream.on('error', (err) => {
        clearTimeout(timer);
        reject(err);
      });

      stream.on('end', async () => {
        clearTimeout(timer);

        try {
          const inspect = await exec.inspect();
          resolve({
            success: true,
            output: output,
            exitCode: inspect.ExitCode,
            command: command
          });
        } catch (err) {
          reject(err);
        }
      });
    });
  } catch (error) {
    throw new Error(`Execution failed: ${error.message}`);
  }
}

// Get list of available tools
function getAvailableTools() {
  const tools = [];
  for (const [category, toolList] of Object.entries(KALI_TOOLS)) {
    tools.push({
      category,
      tools: toolList
    });
  }
  return tools;
}

// Create MCP Server
const server = new Server({
  name: 'tipistore-windows-mcp',
  version: '1.0.0',
});

// Resource handlers
server.setRequestHandler(ListResourcesRequestSchema, async () => {
  log('debug', 'ListResourcesRequest received');

  return {
    resources: [
      {
        uri: 'kali://tools',
        name: 'Available Kali Tools',
        description: 'List of available penetration testing tools in Kali Linux',
        mimeType: 'application/json'
      },
      {
        uri: 'kali://status',
        name: 'Kali Container Status',
        description: 'Current status and information about the Kali container',
        mimeType: 'application/json'
      },
      {
        uri: 'kali://container-info',
        name: 'Container Information',
        description: 'Detailed information about the Kali container',
        mimeType: 'application/json'
      }
    ]
  };
});

server.setRequestHandler(ReadResourceRequestSchema, async (request) => {
  log('debug', 'ReadResourceRequest', { uri: request.params.uri });

  const uri = request.params.uri;

  if (uri === 'kali://tools') {
    return {
      contents: [
        {
          uri: uri,
          mimeType: 'application/json',
          text: JSON.stringify(getAvailableTools(), null, 2)
        }
      ]
    };
  }

  if (uri === 'kali://status') {
    try {
      const container = docker.getContainer(KALI_CONTAINER);
      const data = await container.inspect();

      return {
        contents: [
          {
            uri: uri,
            mimeType: 'application/json',
            text: JSON.stringify({
              containerName: data.Name,
              state: data.State.Status,
              running: data.State.Running,
              pid: data.State.Pid,
              image: data.Image,
              created: data.Created
            }, null, 2)
          }
        ]
      };
    } catch (error) {
      throw new Error(`Failed to get container status: ${error.message}`);
    }
  }

  if (uri === 'kali://container-info') {
    try {
      const container = docker.getContainer(KALI_CONTAINER);
      const data = await container.inspect();

      return {
        contents: [
          {
            uri: uri,
            mimeType: 'application/json',
            text: JSON.stringify({
              id: data.Id.substring(0, 12),
              name: data.Name,
              image: data.Image,
              created: data.Created,
              state: {
                status: data.State.Status,
                running: data.State.Running,
                exitCode: data.State.ExitCode
              },
              mounts: data.Mounts.map(m => ({
                source: m.Source,
                destination: m.Destination,
                mode: m.Mode,
                rw: m.RW
              })),
              networkSettings: {
                ipAddress: data.NetworkSettings.IPAddress,
                gateway: data.NetworkSettings.Gateway
              }
            }, null, 2)
          }
        ]
      };
    } catch (error) {
      throw new Error(`Failed to get container info: ${error.message}`);
    }
  }

  throw new Error(`Unknown resource: ${uri}`);
});

// Tool handlers
server.setRequestHandler(ListToolsRequestSchema, async () => {
  log('debug', 'ListToolsRequest received');

  return {
    tools: [
      {
        name: 'execute_kali_command',
        description: 'Execute a bash command in the Kali Linux container',
        inputSchema: {
          type: 'object',
          properties: {
            command: {
              type: 'string',
              description: 'The bash command to execute in Kali container'
            },
            timeout: {
              type: 'number',
              description: 'Command timeout in milliseconds (default: 30000)',
              default: 30000
            }
          },
          required: ['command']
        }
      },
      {
        name: 'list_kali_tools',
        description: 'List all available penetration testing tools organized by category',
        inputSchema: {
          type: 'object',
          properties: {
            category: {
              type: 'string',
              description: 'Optional category filter (reconnaissance, web, exploitation, etc.)'
            }
          }
        }
      },
      {
        name: 'get_tool_help',
        description: 'Get help/usage information for a specific tool',
        inputSchema: {
          type: 'object',
          properties: {
            tool: {
              type: 'string',
              description: 'Name of the tool to get help for'
            }
          },
          required: ['tool']
        }
      },
      {
        name: 'get_container_logs',
        description: 'Retrieve the last N lines of the Kali container logs',
        inputSchema: {
          type: 'object',
          properties: {
            lines: {
              type: 'number',
              description: 'Number of log lines to retrieve (default: 100)',
              default: 100
            }
          }
        }
      }
    ]
  };
});

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  log('debug', 'CallToolRequest', { tool: name, args });

  try {
    if (name === 'execute_kali_command') {
      if (!args.command) {
        throw new Error('command parameter is required');
      }

      const result = await executeKaliCommand(args.command, args.timeout || 30000);
      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify(result, null, 2)
          }
        ]
      };
    }

    if (name === 'list_kali_tools') {
      const tools = getAvailableTools();

      if (args.category) {
        const filtered = tools.filter(t => t.category === args.category);
        if (filtered.length === 0) {
          throw new Error(`Category '${args.category}' not found`);
        }
        return {
          content: [
            {
              type: 'text',
              text: JSON.stringify(filtered, null, 2)
            }
          ]
        };
      }

      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify(tools, null, 2)
          }
        ]
      };
    }

    if (name === 'get_tool_help') {
      if (!args.tool) {
        throw new Error('tool parameter is required');
      }

      const result = await executeKaliCommand(`${args.tool} --help 2>&1 || ${args.tool} -h 2>&1 || echo "Tool not found or no help available"`, 5000);
      return {
        content: [
          {
            type: 'text',
            text: result.output
          }
        ]
      };
    }

    if (name === 'get_container_logs') {
      try {
        const container = docker.getContainer(KALI_CONTAINER);
        const logs = await container.logs({
          stdout: true,
          stderr: true,
          tail: args.lines || 100
        });

        return {
          content: [
            {
              type: 'text',
              text: logs.toString()
            }
          ]
        };
      } catch (error) {
        throw new Error(`Failed to get logs: ${error.message}`);
      }
    }

    throw new Error(`Unknown tool: ${name}`);
  } catch (error) {
    log('error', 'Tool execution failed', { tool: name, error: error.message });
    return {
      content: [
        {
          type: 'text',
          text: `Error: ${error.message}`,
          isError: true
        }
      ]
    };
  }
});

// Main startup
async function main() {
  try {
    log('info', 'Starting Tipistore Windows MCP Server');
    log('info', 'Configuration', {
      dockerSocket: DOCKER_SOCKET,
      kaliContainer: KALI_CONTAINER,
      platform: process.platform
    });

    // Initialize Docker
    await initializeDocker();

    // Connect to stdio transport
    const transport = new StdioClientTransport();
    await server.connect(transport);

    log('info', 'MCP Server started and connected');
  } catch (error) {
    log('error', 'Failed to start MCP server', { error: error.message });
    process.exit(1);
  }
}

// Handle shutdown gracefully
process.on('SIGINT', async () => {
  log('info', 'Shutting down MCP server');
  process.exit(0);
});

process.on('SIGTERM', async () => {
  log('info', 'Received SIGTERM, shutting down');
  process.exit(0);
});

// Start the server
main();
