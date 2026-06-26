# Gemini Image Mode Documentation

This folder explains the image-generation flow that was added to the local Gemini client and how to use it from other scripts.

Files:
- [architecture.md](/Volumes/hard-drive/gemini-cli-test/documentation/architecture.md): how the image flow works internally
- [usage.md](/Volumes/hard-drive/gemini-cli-test/documentation/usage.md): how to call it from Python and CLI
- [interactive-client.md](/Volumes/hard-drive/gemini-cli-test/documentation/interactive-client.md): how the terminal test client behaves

Short version:
- Normal text generation uses the standard Gemini chat flow.
- Image generation uses `image=True`.
- When `image=True`, the client now switches to Gemini's dedicated `/images` surface before sending the request.
- That means other scripts do not need custom image logic. They only need to call the normal client methods with `image=True`.
