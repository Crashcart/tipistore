# Runtipi App Store

A custom Runtipi app store featuring containerized applications optimized for self-hosted deployment.

## Installation

### Add to Runtipi

1. Open Runtipi dashboard
2. Go to **Settings** → **App Stores**
3. Click **Add Custom Store**
4. Enter: `https://github.com/Crashcart/tipistore`
5. The store will appear in your app library

## Available Apps

### Olama — Intel GPU LLM Stack

**ID:** `olama-intel-gpu`
**Category:** AI
**Description:** Complete self-hosted AI stack with Ollama LLM engine, Open WebUI chat interface, web search, RAG, voice I/O, and custom pipelines.

**Features:**
- Chat with any Ollama-compatible model (Mistral, LLaMA, Phi, etc.)
- Vision/Multimodal support (upload images)
- Tool/Function calling
- Document Q&A (RAG)
- YouTube transcript loading
- Web search with SearXNG
- Voice input (STT) with Whisper
- Voice output (TTS)
- Custom Python pipelines
- Multi-user authentication
- Community prompt sharing

**Requirements:**
- Intel GPU (Arc, Iris Xe, or integrated graphics)
- Kernel with Intel GPU drivers (`i915` or `xe`)

**Configuration:**
- Ollama API port (configurable)
- Default LLM model selection
- GPU parallel request slots
- Authentication settings
- Whisper STT model selection

**Source:** [GitHub - Crashcart/Olama-intelgpu](https://github.com/Crashcart/Olama-intelgpu)

## Store Structure

```
tipistore/
├── apps/
│   ├── schema.json                    # JSON Schema for config.json validation
│   └── olama-intel-gpu/
│       ├── config.json                # App metadata and configuration form
│       ├── docker-compose.yml         # Service definitions
│       └── metadata/
│           └── description.md         # Detailed app documentation
└── README.md                          # This file
```

## Adding New Apps

To add a new app to this store:

1. Create a directory under `apps/` with your app's unique ID:
   ```
   mkdir apps/my-app-id
   ```

2. Create required files:
   - `config.json` - App metadata and configuration
   - `docker-compose.yml` - Docker Compose service definitions
   - `metadata/description.md` - App documentation

3. Ensure `config.json` includes:
   ```json
   {
     "id": "my-app-id",
     "name": "My App Name",
     "tipiVersion": 2,
     "port": 3000,
     "categories": ["utilities"],
     "version": "latest",
     "available": true
   }
   ```

4. Commit and push changes

## Schema Reference

See `apps/schema.json` for the complete JSON Schema that validates `config.json` files.

### Required Fields in config.json

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique app identifier (lowercase, hyphens only) |
| `name` | string | Display name |
| `tipiVersion` | integer | Schema version (1 or 2) |
| `port` | integer | Exposed port number |
| `categories` | array | App categories for discovery |

### Optional but Recommended Fields

| Field | Type | Description |
|-------|------|-------------|
| `short_desc` | string | Brief description for store listings |
| `description` | string | Full description |
| `author` | string | Developer/maintainer name |
| `tags` | array | Search keywords |
| `version` | string | App version |
| `source` | string | GitHub repository URL |
| `website` | string | Project website |
| `supported_architectures` | array | Supported CPU types (amd64, arm64, armv7) |
| `form_fields` | array | Configuration options shown to users |

## Development

### Cloning and Local Testing

```bash
# Clone this repository
git clone https://github.com/Crashcart/tipistore.git
cd tipistore

# Create a new app
mkdir -p apps/my-app/metadata

# Add required files
# - apps/my-app/config.json
# - apps/my-app/docker-compose.yml
# - apps/my-app/metadata/description.md

# Validate your config.json (optional)
python3 -c "import json; json.load(open('apps/my-app/config.json'))"

# Commit and push
git add apps/my-app/
git commit -m "Add my-app"
git push
```

## Validation

All `config.json` files must be valid JSON and conform to the JSON Schema in `apps/schema.json`.

### Validate Manually

```bash
# Check JSON syntax
python3 -c "import json; json.load(open('apps/olama-intel-gpu/config.json')); print('✓ Valid JSON')"

# Validate against schema
python3 -c "
import json
import jsonschema

with open('apps/schema.json') as f:
    schema = json.load(f)
with open('apps/olama-intel-gpu/config.json') as f:
    config = json.load(f)

jsonschema.validate(config, schema)
print('✓ Valid config')
"
```

## Support

For issues or questions about specific apps, refer to their source repositories or GitHub issues.

## License

Each app maintains its own license. See individual app repositories for details.
