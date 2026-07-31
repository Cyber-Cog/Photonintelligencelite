# ZenMux integration

PIC Lite uses [ZenMux](https://zenmux.ai) as an OpenAI-compatible gateway for the **PIC Analyst** custom agent.

## In-app PIC Analyst (backend)

Set these environment variables on Render (or in local `.env`):

| Variable | Value |
|----------|--------|
| `ZENMUX_API_KEY` | Chat API key from ZenMux console (usually `sk-ai-v1-…`) |
| `ZENMUX_BASE_URL` | `https://zenmux.ai/api/v1` |
| `ZENMUX_MODEL` | Model slug, e.g. `google/gemini-2.5-flash` |

Endpoints:

- `GET /api/agent/status` — whether the agent is enabled
- `POST /api/agent/chat` — authenticated chat with optional `job_id` for upload/validation context

**Note:** Management keys (`sk-mg-v1-…`) are for billing/usage APIs, not chat. Use a chat API key for `ZENMUX_API_KEY`.

## Cursor custom agent

1. **Cursor Settings → Models**
   - Enable **OpenAI API Key** → paste your ZenMux key
   - Enable **Override OpenAI Base URL** → `https://zenmux.ai/api/v1`
   - **Add custom model** → `google/gemini-2.5-flash` (or any slug from [zenmux.ai/models](https://zenmux.ai/models))

2. **Project subagent:** `.cursor/agents/pic-lite-analyst.md`  
   Invoke with `/pic-lite-analyst` or `@pic-lite-analyst` in Cursor chat.

Cursor Pro is typically required for custom third-party models — see [ZenMux Cursor guide](https://docs.zenmux.ai/best-practices/cursor).

## Security

- Never commit API keys to git
- Rotate any key that was pasted into chat or tickets
- Keys live only in `.env` (local) or Render encrypted env vars (production)
