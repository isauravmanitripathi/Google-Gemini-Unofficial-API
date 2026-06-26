# Architecture

## Goal

The goal was to make image generation work the way the Gemini web app does, instead of treating image prompts as normal text prompts.

Earlier, simply setting an image-like prompt was not enough. Gemini could reply with:
- normal text
- web-searched images
- mixed text plus images

The fix was to reproduce the dedicated Gemini Images flow seen in the web client.

## What Changed

The image behavior now lives in the core client, not only in a test script.

Main implementation points:
- [constants.py](/Volumes/hard-drive/gemini-cli-test/Gemini-API/src/gemini_webapi/constants.py:34)
- [client.py](/Volumes/hard-drive/gemini-cli-test/Gemini-API/src/gemini_webapi/client.py:471)
- [client.py](/Volumes/hard-drive/gemini-cli-test/Gemini-API/src/gemini_webapi/client.py:1448)
- [client.py](/Volumes/hard-drive/gemini-cli-test/Gemini-API/src/gemini_webapi/client.py:879)

## Normal Text Flow

For a normal call:
1. `client.init()` gets session values and cookies.
2. The client warms up the standard `/app` surface.
3. `generate_content(..., image=False)` sends the normal generation request.

## Image Flow

For an image call:
1. `client.init()` still initializes the normal session first.
2. When the actual request uses `image=True`, the client runs `_prepare_image_surface()`.
3. `_prepare_image_surface()` loads `https://gemini.google.com/images`.
4. It refreshes volatile values from that page such as:
   - access token
   - build label
   - session id
   - language
   - push id
5. It sends warmup RPCs with `source-path=/images`.
6. It persists Gemini's selected mode to the image mode id.
7. It sends `StreamGenerate` with the image-specific request shape and headers.

This is what makes the request behave like the Gemini Images tool rather than regular chat.

## Why `/images` Matters

The important change is not only "set a flag".

The client now does both:
- switch to the `/images` surface
- send the image-specific generation payload

That is why the results improved from mixed chat behavior to actual generated images.

## Automatic Initialization

The client still initializes through the same public `init()` call.

Relevant code:
- [get_access_token.py](/Volumes/hard-drive/gemini-cli-test/Gemini-API/src/gemini_webapi/utils/get_access_token.py:35)
- [client.py](/Volumes/hard-drive/gemini-cli-test/Gemini-API/src/gemini_webapi/client.py:171)

The image logic is automatic after initialization. Callers do not need to manually:
- fetch `/images`
- set `source-path=/images`
- build special headers
- manage the image mode id

## Cookies and Session Handling

The client supports:
- cached cookies
- base cookies passed directly
- fresh browser cookies

The interactive test client uses:
- `prefer_browser_cookies=True`
- `skip_cookie_cache=True`

That means each run prefers fresh cookies from the browser instead of stale cached cookies.

## What Another Script Needs To Know

Another script only needs:
1. `await client.init()`
2. call `generate_content(..., image=True)` for image generation
3. call `generate_content(..., image=False)` for normal text

The rest is handled by the library.
