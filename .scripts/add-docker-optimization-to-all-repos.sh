#!/bin/bash

# Script to add Docker optimization guide to all Crashcart repositories
# Usage: GITHUB_TOKEN=your_token ./add-docker-optimization-to-all-repos.sh

set -e

OWNER="Crashcart"
REPOS=("Kali-AI-term" "RPG-Bot" "MusicBot" "discord-chromecast" "Ollama-intelgpu" "qbittorrent-monitor.sh" "Claud")
TOKEN="${GITHUB_TOKEN}"
BRANCH="main"

if [ -z "$TOKEN" ]; then
    echo "Error: GITHUB_TOKEN environment variable not set"
    echo "Usage: GITHUB_TOKEN=your_token ./add-docker-optimization-to-all-repos.sh"
    exit 1
fi

# Docker optimization content
read -r -d '' DOCKER_CONTENT << 'EOF' || true
# Docker Image Optimization Guide

Reduce Docker image size from GB to MB using proven techniques. Target: 90%+ size reduction.

## Quick Wins

| Technique | Impact | Effort |
|-----------|--------|--------|
| Multi-stage builds | 50-80% | Medium |
| Alpine base image | 30-50% | Low |
| Remove build tools | 20-40% | Low |
| Clean caches | 10-30% | Low |
| .dockerignore | 5-20% | Low |

---

## 1. Use Lightweight Base Images

### Alpine Linux (5MB)
\`\`\`dockerfile
FROM alpine:3.19
\`\`\`
- 95% smaller than ubuntu
- Ideal for most applications
- Has most standard tools available

### Distroless (10-50MB)
\`\`\`dockerfile
FROM gcr.io/distroless/base
\`\`\`
- No shell, no package manager
- Maximum security and minimal size
- Best for compiled binaries

---

## 2. Multi-Stage Builds

### Before (Single Stage - 500MB)
\`\`\`dockerfile
FROM ubuntu:22.04
RUN apt-get update && apt-get install -y gcc make cmake
COPY . /app
WORKDIR /app
RUN make build
CMD ["./app"]
\`\`\`

### After (Multi-Stage - 25MB)
\`\`\`dockerfile
# Stage 1: Build
FROM ubuntu:22.04 AS builder
RUN apt-get update && apt-get install -y gcc make cmake
COPY . /app
WORKDIR /app
RUN make build

# Stage 2: Runtime (only copy binary)
FROM alpine:3.19
COPY --from=builder /app/app /app/app
CMD ["/app/app"]
\`\`\`

**Result:** 95% size reduction by discarding build tools in final image.

---

## 3. Remove Build Dependencies

### Clean Package Manager Caches

\`\`\`dockerfile
# ❌ Bloated (leaves cache)
FROM alpine:3.19
RUN apk add --no-cache gcc make

# ✅ Optimized (cleans cache)
FROM alpine:3.19
RUN apk add --no-cache gcc make && \\
    apk del gcc make
\`\`\`

### Combine Commands in One Layer

\`\`\`dockerfile
# ❌ Multiple layers (each adds size)
RUN apk add --no-cache gcc
RUN apk add --no-cache make
RUN gcc --version

# ✅ Single layer (smaller)
RUN apk add --no-cache gcc make && \\
    gcc --version
\`\`\`

### Clean APK Cache Explicitly

\`\`\`dockerfile
RUN apk add --no-cache python3 && \\
    pip install -r requirements.txt && \\
    rm -rf /root/.cache /var/cache/apk/* && \\
    find / -name "*.pyc" -delete
\`\`\`

---

## 4. Create .dockerignore

Prevents copying unnecessary files into build context.

\`\`\`
# .dockerignore
node_modules/
.git/
.github/
.gitignore
README.md
*.md
.DS_Store
.env
.env.local
.vscode/
.idea/
*.log
dist/
build/
coverage/
.pytest_cache/
__pycache__/
*.pyc
.venv/
venv/
\`\`\`

**Impact:** Reduces build context by 50%+ on first build.

---

## 5. Layer Ordering

Put frequently-changing code LAST to maximize cache hits.

\`\`\`dockerfile
# ✅ Optimal order
FROM alpine:3.19

# Static dependencies first (changes rarely)
RUN apk add --no-cache python3 py3-pip

# Copy requirements (changes occasionally)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy code last (changes frequently)
COPY . /app
WORKDIR /app

CMD ["python3", "app.py"]
\`\`\`

---

## 6. Remove Unnecessary Files After Install

\`\`\`dockerfile
# Node.js example
RUN npm install --production && \\
    npm cache clean --force && \\
    rm -rf /usr/local/lib/node_modules/npm

# Python example
RUN pip install --no-cache-dir -r requirements.txt && \\
    find /usr/local/lib/python3.9/site-packages -name "*.dist-info" -type d -exec rm -rf {} + 2>/dev/null || true

# General cleanup
RUN rm -rf /tmp/* /var/tmp/* /var/cache/apk/*
\`\`\`

---

## 7. Use .dockerignore for Large Files

\`\`\`
# .dockerignore
*.zip
*.tar.gz
*.iso
node_modules/
.git/
coverage/
dist/
build/
docs/
\`\`\`

---

## 8. Specific Language Optimizations

### Node.js
\`\`\`dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production

FROM node:20-alpine
WORKDIR /app
COPY --from=builder /app/node_modules ./node_modules
COPY . .
CMD ["node", "index.js"]
\`\`\`

### Python
\`\`\`dockerfile
FROM python:3.11-alpine AS builder
RUN apk add --no-cache gcc musl-dev
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.11-alpine
COPY --from=builder /root/.local /root/.local
COPY . /app
WORKDIR /app
ENV PATH=/root/.local/bin:\$PATH
CMD ["python", "app.py"]
\`\`\`

### Java
\`\`\`dockerfile
FROM eclipse-temurin:21-jdk AS builder
WORKDIR /app
COPY . .
RUN ./gradlew build

FROM eclipse-temurin:21-jre-alpine
COPY --from=builder /app/build/libs/*.jar app.jar
ENTRYPOINT ["java", "-jar", "app.jar"]
\`\`\`

### Go
\`\`\`dockerfile
FROM golang:1.21-alpine AS builder
WORKDIR /app
COPY . .
RUN go build -ldflags="-s -w" -o app

FROM alpine:3.19
COPY --from=builder /app/app /app
CMD ["/app"]
\`\`\`

---

## 9. Use Scratch for Compiled Binaries

For languages that compile to single binary (Go, Rust, C++):

\`\`\`dockerfile
FROM golang:1.21-alpine AS builder
WORKDIR /app
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o app

# Scratch = empty image, only your binary
FROM scratch
COPY --from=builder /app/app /app
ENTRYPOINT ["/app"]
\`\`\`

**Result:** ~10-50MB instead of 300MB+

---

## 10. Advanced: Strip Binaries

For compiled code, remove debug symbols:

\`\`\`dockerfile
# Go
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o app

# C/C++
RUN gcc -o app main.c && strip app

# General (Unix)
RUN strip /app/binary
\`\`\`

**Impact:** 20-50% smaller binaries.

---

## Verification & Analysis

### Check Image Size
\`\`\`bash
docker images | grep your-image

# Output: your-image    latest    a1b2c3d4e5f6    10 minutes ago    24MB
\`\`\`

### Analyze Layers
\`\`\`bash
docker history your-image

# Shows size of each layer
\`\`\`

### Deep Analysis with Dive
\`\`\`bash
# Install: brew install dive

dive your-image
# Interactive analysis of what's taking space
\`\`\`

### Docker Slim (Automated)
\`\`\`bash
# Automatically removes unused files
docker-slim build your-image:latest
\`\`\`

---

## Real-World Examples

### Python Flask App
- **Before:** 850MB (Python 3.11 full, pip cache, build tools)
- **After:** 85MB (Alpine, multi-stage, cleaned cache)
- **Reduction:** 90%

### Node.js App
- **Before:** 450MB (Node 18 full, node_modules in final, dev deps)
- **After:** 45MB (Alpine, prod-only deps)
- **Reduction:** 90%

### Go App
- **Before:** 300MB (Go SDK, source, debug symbols)
- **After:** 15MB (scratch, stripped binary)
- **Reduction:** 95%

### Java App
- **Before:** 650MB (JDK, source, build artifacts)
- **After:** 180MB (JRE-alpine, multi-stage)
- **Reduction:** 72%

---

## Checklist

Before pushing a Docker image:

- [ ] Using lightweight base image (Alpine/Distroless)?
- [ ] Multi-stage build separating build from runtime?
- [ ] Build tools removed from final image?
- [ ] .dockerignore file created and working?
- [ ] Package manager caches cleaned?
- [ ] Temporary files removed?
- [ ] Layers ordered optimally (static → dynamic)?
- [ ] Specific version tags (not :latest)?
- [ ] Binary stripped if compiled language?
- [ ] Image analyzed with \`docker history\` or \`dive\`?

---

## References

- [My Docker Image Was 2.4GB. I Cut It to 24MB](https://medium.com/engineering-playbook/my-docker-image-was-2-4gb-i-cut-it-to-24mb-heres-every-optimization-that-actually-worked-46792bd23da4)
- [Optimise Docker Images — from GBs to MBs](https://ravishtiwari.medium.com/optimise-docker-images-from-gbs-to-mbs-4645ccea6be6)
- [Docker Best Practices](https://docs.docker.com/develop/develop-images/dockerfile_best-practices/)
- [Dive - Image Layer Analysis](https://github.com/wagoodman/dive)
- [Docker Slim - Automated Optimization](https://github.com/slimtoolkit/slim)
EOF

echo "Starting deployment to ${#REPOS[@]} repositories..."
echo ""

SUCCESS=0
FAILED=0

for REPO in "${REPOS[@]}"; do
    echo "Processing: $REPO"
    
    # Get the SHA of main branch
    SHA=$(curl -s -H "Authorization: token $TOKEN" \
        "https://api.github.com/repos/$OWNER/$REPO/commits/$BRANCH" \
        | grep -o '"sha":"[^"]*' | head -1 | cut -d'"' -f4)
    
    if [ -z "$SHA" ]; then
        echo "  ✗ Failed to get branch SHA (may not exist or no access)"
        ((FAILED++))
        continue
    fi
    
    # Check if file already exists
    EXISTING_SHA=$(curl -s -H "Authorization: token $TOKEN" \
        "https://api.github.com/repos/$OWNER/$REPO/contents/.github/docker-optimization.md?ref=$BRANCH" \
        2>/dev/null | grep -o '"sha":"[^"]*' | head -1 | cut -d'"' -f4)
    
    # Prepare the content (base64 encoded)
    CONTENT_B64=$(echo -n "$DOCKER_CONTENT" | base64 -w 0)
    
    # Create or update the file
    if [ -n "$EXISTING_SHA" ]; then
        # Update existing file
        RESPONSE=$(curl -s -X PUT \
            -H "Authorization: token $TOKEN" \
            -H "Content-Type: application/json" \
            "https://api.github.com/repos/$OWNER/$REPO/contents/.github/docker-optimization.md" \
            -d "{
                \"message\": \"Update Docker image optimization guidelines\",
                \"content\": \"$CONTENT_B64\",
                \"sha\": \"$EXISTING_SHA\",
                \"branch\": \"$BRANCH\"
            }")
    else
        # Create new file
        RESPONSE=$(curl -s -X PUT \
            -H "Authorization: token $TOKEN" \
            -H "Content-Type: application/json" \
            "https://api.github.com/repos/$OWNER/$REPO/contents/.github/docker-optimization.md" \
            -d "{
                \"message\": \"Add Docker image optimization guidelines\",
                \"content\": \"$CONTENT_B64\",
                \"branch\": \"$BRANCH\"
            }")
    fi
    
    # Check if successful
    if echo "$RESPONSE" | grep -q '"commit"'; then
        echo "  ✓ Success"
        ((SUCCESS++))
    else
        echo "  ✗ Failed"
        echo "    Response: $(echo $RESPONSE | cut -c1-100)..."
        ((FAILED++))
    fi
done

echo ""
echo "=========================================="
echo "Deployment Complete!"
echo "✓ Successful: $SUCCESS"
echo "✗ Failed: $FAILED"
echo "=========================================="
