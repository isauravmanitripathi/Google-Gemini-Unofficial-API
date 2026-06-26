# Usage

## Python API

### Normal text

```python
from gemini_webapi import GeminiClient

client = GeminiClient()
await client.init()

response = await client.generate_content(
    "Explain how PostgreSQL RLS works",
    image=False,
)

print(response.text)
await client.close()
```

### Image generation

```python
from gemini_webapi import GeminiClient

client = GeminiClient(
    prefer_browser_cookies=True,
    skip_cookie_cache=True,
)
await client.init()

response = await client.generate_content(
    "An infographic technical diagram of how PostgreSQL RLS works",
    image=True,
)

print(response.text)
for image in response.images:
    print(image.url)

await client.close()
```

## ChatSession API

If you want to continue a conversation:

```python
chat = client.start_chat()

first = await chat.send_message("Explain RLS", image=False)
second = await chat.send_message("Now draw it as an infographic", image=True)
```

Important behavior:
- in the terminal test client, image mode inside an existing chat starts a new chat intentionally
- in raw library code, you can still call `chat.send_message(..., image=True)` directly if you want

## CLI

The CLI now supports `--image-mode`.

Example:

```bash
python -m Gemini-API.cli ask "draw a fox astronaut" --image-mode
```

Relevant code:
- [cli.py](/Volumes/hard-drive/gemini-cli-test/Gemini-API/cli.py:580)

## Automatic Behavior

When you pass `image=True`, callers do not need to manually:
- choose `/images`
- set image headers
- set the Gemini image mode id
- rewrite prompts

That is already done inside the client.

## Fallback Behavior

The interactive test script also has an optional fallback:
- if image mode returns no images
- it can retry with a rewritten prompt like `Generate an image: ...`

That fallback is a script-level behavior, not a required library behavior.

## Returned Data

Responses can contain:
- text
- generated images
- web images
- other media types

For the dedicated `/images` flow, the expected success path is usually:
- no text or minimal text
- one or more `GeneratedImage` objects

## Recommended Initialization For Local Testing

For local runs where browser cookies are available:

```python
client = GeminiClient(
    prefer_browser_cookies=True,
    skip_cookie_cache=True,
)
```

That gives the best chance of using fresh authenticated cookies on each run.
