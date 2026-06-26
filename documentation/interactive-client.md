# Interactive Terminal Client

File:
- [test_image_mode_interactive.py](/Volumes/hard-drive/gemini-cli-test/output/test_image_mode_interactive.py:1)

## What It Does

This script is a terminal front end over the full Gemini client.

It can:
- initialize the client automatically
- load fresh browser cookies when available
- list recent chats
- label chats as `image`, `web-image`, or `text` based on the latest model turn
- open an old chat and show recent history
- continue talking inside an old chat
- start a brand new chat
- generate images
- save generated images into `output/generated_images`

## How Chat Detection Works

Gemini does not appear to expose a permanent chat-level image flag that can be read back directly.

So the script infers chat mode from the latest model response:
- if the latest response contains a `GeneratedImage`, the chat is labeled `image`
- if it contains only `WebImage`, the chat is labeled `web-image`
- otherwise it is labeled `text`

That logic is in:
- [test_image_mode_interactive.py](/Volumes/hard-drive/gemini-cli-test/output/test_image_mode_interactive.py:72)
- [test_image_mode_interactive.py](/Volumes/hard-drive/gemini-cli-test/output/test_image_mode_interactive.py:117)

## How Image Requests Behave In Existing Chats

The script intentionally treats image generation as a fresh chat boundary.

Behavior:
- if the user is already inside an existing chat
- and chooses image mode
- the script starts a new chat for that image request
- the old chat is left unchanged

This behavior is implemented in:
- [test_image_mode_interactive.py](/Volumes/hard-drive/gemini-cli-test/output/test_image_mode_interactive.py:332)

## Why This Was Done

This makes the terminal behavior cleaner:
- old text chat stays clean
- image requests become their own chat threads
- the user can reopen them later and see that they were image chats

## Main Flow

At startup:
1. initialize client
2. fetch fresh cookies if available
3. show recent chats
4. let user open a chat or start new

Then in the main loop:
1. choose action
2. enter prompt
3. choose image or text mode
4. send request
5. save any returned images
6. keep going until exit

## Folder Outputs

Generated images are saved to:
- `/Volumes/hard-drive/gemini-cli-test/output/generated_images`

Fresh browser cookies are exported to:
- `/Volumes/hard-drive/gemini-cli-test/output/latest_browser_cookies.json`
