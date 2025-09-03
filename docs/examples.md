# Examples

This document provides practical examples of using the Slop Bot in Discord, including command usage, output descriptions, and visual placeholders for demonstrations.

## Table of Contents

- [Basic Commands](#basic-commands)
- [Admin Dashboard](#admin-dashboard)
- [Advanced Usage](#advanced-usage)
- [Visual Examples](#visual-examples)
- [Error Handling](#error-handling)

## Basic Commands

### Imagine Command

The `/imagine` command generates images based on text prompts using AI models.

**Syntax:**
```
/imagine prompt:<your-description-here> [style:<style-name>] [quality:<1-10>]
```

**Example 1: Simple Prompt**
```
/imagine prompt:a futuristic cityscape at sunset
```

This command will generate an image of a futuristic city with buildings and sunset colors.

**Example 2: Styled Image**
```
/imagine prompt:a portrait of a cat in watercolor style quality:9
```

Generates a high-quality watercolor-style cat portrait.

**Example 3: Collaborative Creation**
```
/imagine prompt:an astronaut riding a horse on Mars
```

Creates imaginative scenes combining real and fictional elements.

**Command Output Example:**
```
/imagine prompt:a futuristic cityscape at sunset

Bot Response:
📋 Validating images... ✓
🔄 Preparing Images... ✓
🎨 Generating Images... ✓
🔧 Post-processing 1 generated image... ✓

🎉 Generated Image Details:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• **Prompt:** a futuristic cityscape at sunset
• **Model:** google/gemini-2.5-flash-image-preview
• **Style:** default
• **Seed:** random
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Attached: High-resolution image of a futuristic city with towering skyscrapers, flying vehicles, and a vibrant sunset sky with orange and purple hues]
```

*Figure 1: Sample output showing the complete workflow of the /imagine command with progress indicators and metadata*

### Blend Command

Blend two images together to create composite art.

**Syntax:**
```
/blend image1:<url-or-attachment> image2:<url-or-attachment> [mode:add|multiply|overlay]
```

**Example 1: Portrait Blending**
```
/blend image1:<attached-photo.jpg> image2:<celebrity-face.jpg>
```

Blends your photo with a famous person's face for fun recreations.

**Example 2: Landscape Composition**
Upload two landscape images and blend them for a panoramic effect.

**Command Output Example:**
```
/blend image1:[sunset-sky.jpg] image2:[ocean.jpg]

Bot Response:
📋 Validating images... ✓
🔄 Preparing Images... ✓
🎨 Generating Blended Image... ✓
🔧 Processing Blended Image... ✓

🎉 Blended Image Details:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• **Prompt:** a blended image
• **Sources:** 2 images
• **Strength:** 0.5 (moderate blend)
• **Model:** google/gemini-2.5-flash-image-preview
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Before Blending:
├── Image 1: Vibrant sunset sky with clouds
└── Image 2: Ocean waves with gentle motion

After Blending:
└── Seamless composition of sunset sky merging into ocean scene, creating a surreal landscape where the horizon line becomes fluid
```

*Figure 2: Before and after blending showing how two separate images become one cohesive scene*

### Edit Command

Edit existing images by describing changes you want to make.

**Syntax:**
```
/edit image:<url-or-attachment> prompt:<describe-changes> [strength:0.5]
```

**Example 1: Object Addition**
```
/edit image:<picture.jpg> prompt:add fireworks to the night sky
```

Adds fireworks to a night scene photo.

**Example 2: Style Transformation**
```
/edit image:<photo.jpg> prompt:transform to cyberpunk style
```

Changes the image's aesthetic from realistic to cyberpunk.

**Example 3: Fix Issues**
```
/edit image:<damaged-scan.jpg> prompt:remove scratches and improve clarity
```

Restaurates old damaged images.

**Command Output Example:**
```
/edit image:[original.jpg] prompt:add a majestic lion sitting on the grass, photorealistic detail

Bot Response:
📋 Validating images... ✓
🔄 Preparing Images... ✓
🎨 Generating Edited Image... ✓
🔧 Processing Edited Image... ✓

🎉 Edited Image Details:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• **Prompt:** add a majestic lion sitting on the grass, photorealistic detail
• **Sources:** 1 image
• **Model:** google/gemini-2.5-flash-image-preview
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Original Scene:
└── Peaceful grassland at sunset with no animals

Edited Scene:
└── Same grassland with a majestic lion now present, sitting proudly looking at the horizon, photorealistic fur detail, shadows cast naturally on the grass, maintaining the original lighting and atmosphere
```

*Figure 3: Before and after comparison showing how the /edit command intelligently adds complex elements to an existing image while maintaining natural lighting and perspective*

### Info Command

Check bot status, credits, or get information about available models.

**Syntax:**
```
/info [topic:models|status|usage]
```

**Example 1: Model Information**
```
/info topic:models
```

Lists available AI models with their capabilities and costs.

## Admin Dashboard

The bot includes a comprehensive admin dashboard accessible through Discord slash commands. All admin commands require users to be included in the `ADMIN_USER_IDS` allowlist.

### Generate Dashboard Access

Generate a secure one-time URL to access the admin dashboard.

**Syntax:**
```
/admin dashboard
```

**Example Command:**
```
/admin dashboard
```

**Bot Response:**
```
🔐 *Generating secure admin access link...*

✅ Access link created (expires in 5 minutes)

🔗 Dashboard URL: https://yourdomain.com/admin/auth/abc123defg

*This link is for your eyes only. It will expire automatically for security.*
```

**Security Notes:**
- Link expires in 5 minutes by default
- Can only be used once
- Requires Discord OAuth2 authentication
- Only works for authorized admin users

### Check Dashboard Status

Monitor dashboard availability and system health.

**Syntax:**
```
/admin status
```

**Example Command:**
```
/admin status
```

**Bot Response:**
```
📊 *Dashboard Status Report*

🟢 Dashboard Ready
- URL: https://yourdomain.com/admin/auth/
- Sessions: 1 active
- Last activity: 2 minutes ago

🤖 Bot Status
- Queue: 3 pending / 2 processing
- Health: 99.8% uptime
- API: OpenRouter responding

⚙️ Settings
- Hot reload: Enabled
- Audit logging: Active
- Rate limits: 5 per 5 minutes (default)
```

### Generate Custom Access Link

Create a dashboard access link with a custom TTL period.

**Syntax:**
```
/admin invite ttl:<minutes>
```

**Example Command:**
```
/admin invite ttl:15
```

**Bot Response:**
```
⏰ *Generating extended admin access link...*

✅ Custom access link created (expires in 15 minutes)

🔗 Dashboard URL: https://yourdomain.com/admin/auth/custom456xyz

*Link expires in 15 minutes. Use for extended admin sessions.*
```

**TTL Limits:**
- Minimum: 1 minute
- Maximum: 60 minutes default (configurable)
- Recommended: 5-10 minutes for standard use

### Dashboard Administration Workflows

#### Settings Management
**Update Rate Limits:**
```
Dashboard → Rate Limits → Edit User Overrides
└─ Add user ID + custom limits → Save & Reload
```

**Modify Bot Settings:**
```
Dashboard → Settings → Runtime Configuration
└─ Edit image settings, queue limits, timeouts → Hot Reload
```

#### Security Administration
**Update API Keys:**
```
Dashboard → Secrets → OpenRouter API Key
└─ Enter new key (masked input) → Validate & Save
```

**Review Audit Logs:**
```
Dashboard → Audit → Filter by action type
└─ Review user actions, timestamps, IP addresses → Export CSV
```

#### System Monitoring
**Real-time Health Check:**
```
Dashboard → Status → Live Metrics
└─ Monitor queue depth, response times, error rates
```

### Setup Examples

#### Initial Configuration
```bash
# 1. Add to .env file
ADMIN_USER_IDS=123456789,987654321
OAUTH_CLIENT_ID=your_app_id
OAUTH_CLIENT_SECRET=your_secret

# 2. Initialize dashboard
docker compose up --build

# 3. Test access
/admin dashboard
```

#### Production Deployment
```bash
# 1. Configure reverse proxy
proxy_pass http://localhost:8000/admin/;

# 2. Enable HTTPS
ssl_certificate /path/to/cert.pem;
```

## Advanced Usage

### Batch Operations

Use multiple commands in sequence for complex workflows.

**Example Workflow: Create and Edit**
1. `/imagine prompt:base foundation scene`
2. `/edit image:<generated-image> prompt:add detailed elements`
3. Continue iterating until satisfied.

### Quality Settings

Experiment with quality parameters for different use cases:

- Quality 1-3: Fast, rough drafts
- Quality 4-7: Balanced speed/quality
- Quality 8-10: Maximum fidelity (slower, more credits)

### Prompt Engineering Tips

- Be specific with subject, style, lighting, composition
- Use reference styles: "in the style of Salvador Dali"
- Specify aspect ratios: "wide panoramic view"
- Include mood: "serene, mysterious atmosphere"

## Visual Examples

### Live Demonstrations

While visual GIFs would be ideal, here are detailed walkthroughs of typical bot interactions:

**Live Command Execution:**
1. User types `/imagine prompt:a steampunk city`
2. Bot responds with `📋 Validating images... ✓`
3. Progress updates show `🎨 Generating Images... ✓`
4. Final result: High-resolution steampunk city image
5. Metadata display shows generation parameters

**Before/After Transitions:**
- Original: Empty canvas or basic sketch
- Command: `/edit prompt:add complex architecture and mechanical details`
- Result: Transformed image with intricate steampunk elements integrated seamlessly

**Demo Walkthrough:**
Complete workflow from command entry to final delivery takes approximately 15-30 seconds, depending on queue position and image complexity.

### Sample Command Patterns

**Pattern 1: Creative Generation**
```
Command: /imagine prompt:fantasy portrait, elven archer with glowing runes, mystical forest background
Style: digital art
Quality: 9
Expected: High-fidelity fantasy character with glowing runic tattoos and detailed magical elements
```

**Pattern 2: Realistic Enhancement**
```
Command: /edit image:[product-photo.jpg] prompt:enhance lighting, professional studio setup, shadow depth
Expected: Photo studio-quality enhancement with proper lighting and dramatic shadows
```

**Pattern 3: Artistic Conversion**
```
Command: /blend image1:[watercolor-sketch.jpg] image2:[color-palette.jpg] mode:add
Expected: Seamless merge of pencil sketch with vibrant color palette, creating painterly effect
```

**Pattern 4: Text and Graphics**
```
Command: /imagine prompt:create an infographic about renewable energy, clean design, infographic style
Expected: Professional infographic with charts, icons, and clean typography
```

## Error Handling

### Common Issues and Solutions

**Rate Limit Exceeded:**
Wait a few minutes and try again. Upgrade plan for higher limits.

**Invalid Prompt:**
Use more descriptive language, avoid offensive content.

**Image Upload Failures:**
Ensure images are under 10MB, supported formats (PNG/JPG/WebP).

**Moderation Flags:**
Review content policies, reword prompts to be appropriate.

**Timeout Errors:**
Break complex prompts into simpler parts, use basic quality first.

### Troubleshooting Steps

1. Check `/info status` for bot availability
2. Verify your permissions in the server
3. Try commands in DM first to isolate issues
4. Clear image cache with member role clear command
5. Contact support with error codes and timestamps

## Performance Tips

- Use lower quality for quick iterations
- Batch similar commands together
- Save successful prompts as templates
- Study existing examples for inspiration
- Join community channels for peer assistance

---

For more advanced examples, visit our community Discord server or GitHub repository.