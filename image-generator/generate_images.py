#!/usr/bin/env python3
import os
import re
import sys
import time
import json
import random
import asyncio
import argparse
import warnings
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, Any

# Suppress all repeating python warnings (DeprecationWarning, UserWarning, etc.)
warnings.filterwarnings("ignore")

# Automatically detect if Gemini-API/src is nearby and add it to sys.path
script_dir = Path(__file__).resolve().parent
parent_dir = script_dir.parent
api_src_path = parent_dir / "src"

if api_src_path.exists():
    sys.path.insert(0, str(api_src_path))
else:
    alt_src_path = parent_dir / "Gemini-API" / "src"
    if alt_src_path.exists():
        sys.path.insert(0, str(alt_src_path))

# Regex to find:
# 1. <!-- IMAGE_PROMPT: <prompt> -->
# 2. followed by whitespace/newlines
# 3. ![<caption>](<image_path>)
PROMPT_PATTERN = re.compile(
    r'<!--\s*IMAGE_PROMPT:\s*([\s\S]*?)\s*-->\s*(!\[(.*?)\]\((.*?)\))',
    re.MULTILINE
)

# Terminal coloring helpers
def get_timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")

def log_info(msg: str):
    print(f"[{get_timestamp()}] [INFO] {msg}")

def log_success(msg: str):
    print(f"[{get_timestamp()}] [SUCCESS] \033[92m{msg}\033[0m")

def log_warning(msg: str):
    print(f"[{get_timestamp()}] [WARNING] \033[93m{msg}\033[0m")

def log_error(msg: str):
    print(f"[{get_timestamp()}] [ERROR] \033[91m{msg}\033[0m", file=sys.stderr)


class ImageGeneratorApp:
    def __init__(self, target_dir: str, log_file: str, num_workers: int):
        self.target_dir = Path(target_dir).resolve()
        self.log_file = Path(log_file).resolve()
        self.num_workers = num_workers
        self.completed_keys: Set[Tuple[str, str]] = set()
        self.session_mappings: Dict[int, List[Any]] = {}
        self.file_locks: Dict[Path, asyncio.Lock] = {}
        self.load_log()

    def load_log(self):
        """Loads the JSONL log file to track completed image generations and restore session states for workers."""
        if not self.log_file.exists():
            log_info(f"No existing log file found. Creating new log at: {self.log_file}")
            return
        
        log_info(f"Reading generation log: {self.log_file}")
        try:
            target_folder_str = str(self.target_dir)
            with open(self.log_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        if entry.get("folder") == target_folder_str:
                            entry_type = entry.get("type", "image_generation")
                            
                            if entry_type == "image_generation" and entry.get("status") == "success":
                                markdown_rel = entry.get("markdown_file")
                                image_path = entry.get("image_path")
                                if markdown_rel and image_path:
                                    self.completed_keys.add((markdown_rel, image_path))
                                    
                            elif entry_type == "session_state":
                                worker_id = entry.get("worker_id")
                                metadata = entry.get("metadata")
                                if worker_id is not None and isinstance(metadata, list):
                                    self.session_mappings[int(worker_id)] = metadata
                                    
                    except json.JSONDecodeError:
                        continue
                        
            log_success(f"Log loaded. Verified {len(self.completed_keys)} previously completed images.")
            if self.session_mappings:
                log_info(f"Loaded {len(self.session_mappings)} active worker chat window(s) from log.")
        except Exception as e:
            log_warning(f"Failed to parse generation log fully: {e}")

    def log_image_generation(self, markdown_file: str, image_path: str, prompt: str, status: str, error: str = None):
        """Writes an image generation entry to the JSONL log file."""
        entry = {
            "type": "image_generation",
            "folder": str(self.target_dir),
            "markdown_file": markdown_file,
            "image_path": image_path,
            "prompt": prompt,
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "error": error
        }
        self._write_entry(entry)

    def log_session_state(self, worker_id: int, metadata: List[Any]):
        """Writes a session state entry to the JSONL log file mapping a worker to a chat window."""
        entry = {
            "type": "session_state",
            "folder": str(self.target_dir),
            "worker_id": worker_id,
            "metadata": metadata,
            "timestamp": datetime.now().isoformat()
        }
        self._write_entry(entry)

    def _write_entry(self, entry: Dict[str, Any]):
        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            log_error(f"Disk write error: Failed to append to log file: {e}")

    def find_image_prompts(self) -> List[Dict]:
        """Scans the target directory for markdown files and extracts IMAGE_PROMPT blocks."""
        prompts = []
        if not self.target_dir.exists():
            log_error(f"Target directory {self.target_dir} does not exist.")
            return prompts

        markdown_files = list(self.target_dir.glob("*.md"))
        if not markdown_files:
            markdown_files = list(self.target_dir.rglob("*.md"))

        log_info(f"Scanning folder for markdown files: {self.target_dir}")

        for md_path in sorted(markdown_files):
            try:
                content = md_path.read_text(encoding='utf-8')
            except Exception as e:
                log_warning(f"Could not read file {md_path.name}: {e}")
                continue

            rel_md_path = str(md_path.relative_to(self.target_dir))
            
            file_count = 0
            for match in PROMPT_PATTERN.finditer(content):
                prompt_text = match.group(1).strip()
                full_image_tag = match.group(2).strip()
                caption = match.group(3).strip()
                image_path = match.group(4).strip()
                
                prompts.append({
                    "md_path": md_path,
                    "rel_md_path": rel_md_path,
                    "prompt": prompt_text,
                    "full_image_tag": full_image_tag,
                    "caption": caption,
                    "image_path": image_path,
                    "match_start": match.start(),
                    "match_end": match.end(),
                    "raw_match": match.group(0)
                })
                file_count += 1
            
            if file_count > 0:
                log_info(f"  - {md_path.name}: Found {file_count} image prompt(s)")

        log_success(f"Scan complete. Total image prompts found across files: {len(prompts)}")
        return prompts

    async def worker_task(self, worker_id: int, client: Any, queue: asyncio.Queue):
        """Worker task processing image prompts from the queue using its own persistent ChatSession."""
        try:
            from gemini_webapi import ChatSession
            from gemini_webapi.exceptions import GeminiError
        except ImportError:
            return

        # Restore or create the ChatSession for this worker
        if worker_id in self.session_mappings:
            metadata = self.session_mappings[worker_id]
            chat = client.start_chat(metadata=metadata)
            log_success(f"Worker {worker_id}: Restored existing chat window (CID: {chat.cid})")
        else:
            chat = client.start_chat()
            log_info(f"Worker {worker_id}: Started new chat window")

        while True:
            try:
                p = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            md_path = p["md_path"]
            rel_md_path = p["rel_md_path"]
            prompt = p["prompt"]
            image_path = p["image_path"]
            caption = p["caption"]
            full_image_tag = p["full_image_tag"]
            
            abs_image_path = md_path.parent / image_path
            image_dir = abs_image_path.parent
            image_filename = abs_image_path.name

            # Check if another worker completed it while we were waiting
            key = (rel_md_path, image_path)
            if key in self.completed_keys and abs_image_path.exists():
                log_info(f"Worker {worker_id}: Skipping {image_path} (already completed by another worker)")
                queue.task_done()
                continue

            success = False
            last_error = ""
            
            # Attempt 1: Initial Attempt (Same Chat)
            # Attempt 2: 1st Retry (Same Chat)
            # Attempt 3: 2nd Retry (Same Chat)
            # Attempt 4: 3rd Retry (New Chat Window)
            max_attempts = 4

            for attempt in range(1, max_attempts + 1):
                delay = random.uniform(2, 5)
                
                if attempt == max_attempts:
                    log_warning(f"Worker {worker_id}: Same-chat retries failed. Spawning a new chat window for the final retry attempt...")
                    chat = client.start_chat()
                    delay += 5  # Add extra delay before prompting in the new chat window
                elif attempt > 1:
                    # Exponential backoff for same-chat retries
                    delay += (attempt * 3)
                    log_warning(f"Worker {worker_id}: Retrying attempt {attempt}/{max_attempts} (same chat) for {image_filename} after error: {last_error}")

                log_info(f"Worker {worker_id}: Waiting {delay:.2f}s delay before sending prompt...")
                await asyncio.sleep(delay)

                chat_desc = f"CID: {chat.cid or 'NEW'}"
                log_info(f"Worker {worker_id}: Generating image ({chat_desc}, Attempt {attempt}/{max_attempts}) for {rel_md_path} -> {image_path}")
                
                start_time = time.time()
                try:
                    # Request image generation
                    response = await chat.send_message(prompt, image=True)
                    
                    if response.images:
                        img = response.images[0]
                        elapsed = time.time() - start_time
                        log_info(f"Worker {worker_id}: Image generated in {elapsed:.2f}s. Fetching high-resolution asset...")
                        
                        image_dir.mkdir(parents=True, exist_ok=True)
                        
                        saved_path = await img.save(
                            path=str(image_dir),
                            filename=image_filename,
                            verbose=False
                        )

                        if os.path.exists(saved_path) and os.path.getsize(saved_path) > 0:
                            file_size = os.path.getsize(saved_path)
                            log_success(f"Worker {worker_id}: Saved {abs_image_path.name} ({file_size} bytes)")
                            
                            # Log success in JSONL
                            self.log_image_generation(rel_md_path, image_path, prompt, "success")
                            self.completed_keys.add(key)

                            # Update log with the latest session metadata state for this worker
                            self.log_session_state(worker_id, chat.metadata)

                            # Remove the image prompt comment from the markdown
                            await self.remove_prompt_comment_locked(p)
                            
                            # Validate markdown modification
                            await self.validate_markdown_locked(md_path, full_image_tag)
                            success = True
                            break
                        else:
                            raise FileNotFoundError("Saved file not found or is empty.")
                    else:
                        raise GeminiError("No images returned in response.")
                        
                except Exception as e:
                    last_error = str(e)
                    log_error(f"Worker {worker_id} (Attempt {attempt}/{max_attempts}) Failed: {last_error}")

            if not success:
                log_error(f"Worker {worker_id}: All {max_attempts} attempts failed for {image_filename}. Logging failure and moving to next task.")
                self.log_image_generation(rel_md_path, image_path, prompt, "failed", last_error)

            queue.task_done()

    async def remove_prompt_comment_locked(self, prompt_info: Dict):
        """Removes the IMAGE_PROMPT comment block from the markdown file, using file lock."""
        md_path = prompt_info["md_path"]
        raw_match = prompt_info["raw_match"]
        full_image_tag = prompt_info["full_image_tag"]

        lock = self.file_locks.setdefault(md_path, asyncio.Lock())
        async with lock:
            try:
                content = md_path.read_text(encoding='utf-8')
                updated_content = content.replace(raw_match, full_image_tag)
                md_path.write_text(updated_content, encoding='utf-8')
                log_info(f"  File System: Cleaned IMAGE_PROMPT comment block in {md_path.name}")
            except Exception as e:
                log_error(f"  File System Error: Failed to write to {md_path.name}: {e}")

    async def validate_markdown_locked(self, md_path: Path, full_image_tag: str):
        """Validates that the image tag is still correctly embedded in the markdown file."""
        lock = self.file_locks.setdefault(md_path, asyncio.Lock())
        async with lock:
            try:
                content = md_path.read_text(encoding='utf-8')
                if full_image_tag in content:
                    log_success(f"  Validation: Found expected image tag '{full_image_tag}' in file.")
                else:
                    log_warning(f"  Validation: Could not find target image tag '{full_image_tag}' in modified file.")
            except Exception as e:
                log_error(f"  Validation Error: Failed to read file for verification: {e}")

    def remove_comments_from_markdown(self, prompts: List[Dict]):
        """Cleans up multiple prompt comments from files (run sequentially at start)."""
        by_file: Dict[Path, List[Dict]] = {}
        for p in prompts:
            by_file.setdefault(p["md_path"], []).append(p)

        for md_path, file_prompts in by_file.items():
            try:
                content = md_path.read_text(encoding='utf-8')
                initial_len = len(content)
                for p in file_prompts:
                    content = content.replace(p["raw_match"], p["full_image_tag"])
                if len(content) != initial_len:
                    md_path.write_text(content, encoding='utf-8')
                    log_success(f"  Cleaned leftover prompt comments in {md_path.name}")
            except Exception as e:
                log_error(f"  Failed to clean {md_path.name}: {e}")

    async def run(self):
        """Runs the parallel generation pipeline."""
        try:
            from gemini_webapi import GeminiClient, set_log_level
            # Silence internal library success and info logs so they don't clutter the terminal
            set_log_level("WARNING")
        except ImportError:
            log_error("'gemini_webapi' package is not installed in the active environment.")
            log_error("Please activate your virtual environment (.venv) first.")
            sys.exit(1)

        prompts = self.find_image_prompts()
        if not prompts:
            log_info("No image prompts found to process in this folder.")
            return

        to_process = []
        skipped_comments_to_remove = []

        for p in prompts:
            key = (p["rel_md_path"], p["image_path"])
            abs_image_path = p["md_path"].parent / p["image_path"]

            if key in self.completed_keys and abs_image_path.exists():
                skipped_comments_to_remove.append(p)
            else:
                to_process.append(p)

        log_info(f"Filter Stats: {len(prompts) - len(to_process)} already completed, {len(to_process)} remaining.")

        if skipped_comments_to_remove:
            log_info("Cleaning up leftover comments for already completed images...")
            self.remove_comments_from_markdown(skipped_comments_to_remove)

        if not to_process:
            log_success("All images in this folder are already generated and up to date!")
            return

        # Initialize Gemini Client
        log_info("Initializing GeminiClient and loading browser cookies automatically...")
        client = GeminiClient(prefer_browser_cookies=True, skip_cookie_cache=True)
        try:
            await client.init()
            log_success("Gemini client successfully initialized.")
        except Exception as e:
            log_error(f"Initialization failure: {e}")
            log_error("Please verify that you are logged into gemini.google.com in your web browser.")
            return

        try:
            # Build queue
            queue = asyncio.Queue()
            for p in to_process:
                queue.put_nowait(p)

            # Spawn concurrent workers
            log_info(f"Spawning {self.num_workers} parallel generation workers (Max attempts per task: 4)...")
            workers = [
                asyncio.create_task(self.worker_task(i, client, queue))
                for i in range(self.num_workers)
            ]

            # Wait for all tasks to be processed
            await asyncio.gather(*workers)
            log_success("All parallel tasks completed.")

        finally:
            log_info("Closing client connections and cleaning resources...")
            await client.close()
            log_success("Session closed cleanly.")

    def print_stats(self):
        """Prints current stats from log and files."""
        prompts = self.find_image_prompts()
        
        remaining = 0
        completed = 0
        
        for p in prompts:
            key = (p["rel_md_path"], p["image_path"])
            abs_image_path = p["md_path"].parent / p["image_path"]
            if key in self.completed_keys and abs_image_path.exists():
                completed += 1
            else:
                remaining += 1

        print("\n" + "="*50)
        print(" IMAGE GENERATION RUN SUMMARY")
        print("="*50)
        print(f"Target Directory:    {self.target_dir}")
        print(f"Log File:            {self.log_file}")
        print(f"Total Prompts Found: {len(prompts)}")
        print(f"Completed / Synced:  \033[92m{completed}\033[0m")
        print(f"Remaining / Queued:  \033[93m{remaining}\033[0m")
        print(f"Parallel Workers:    {self.num_workers}")
        print(f"Max Attempts Per Image: 4 (3 in same chat, 4th in new chat)")
        if self.session_mappings:
            print(f"Active Chat Windows Mapped: {list(self.session_mappings.keys())}")
        print("="*50)


def main():
    parser = argparse.ArgumentParser(description="Automated book image generator using Gemini Web API with parallel chat windows.")
    parser.add_argument(
        "folder", 
        type=str, 
        nargs="?",
        default=".",
        help="Path to the folder containing the book chapter markdown files."
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=3,
        help="Number of parallel generation chat windows (default: 3)."
    )
    parser.add_argument(
        "--log", 
        type=str, 
        default="image_generation_log.jsonl",
        help="Path to the JSONL log file (default: image_generation_log.jsonl in current directory)."
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Only display current progress/statistics and exit."
    )
    parser.add_argument(
        "--usage",
        action="store_true",
        help="Query and print your Gemini usage metrics/quotas and exit."
    )

    args = parser.parse_args()

    if args.usage:
        async def show_usage():
            try:
                from gemini_webapi import GeminiClient, set_log_level
                set_log_level("WARNING")
            except ImportError:
                log_error("'gemini_webapi' package is not installed in the active environment.")
                return
            
            log_info("Initializing client and loading cookies...")
            client = GeminiClient(prefer_browser_cookies=True, skip_cookie_cache=True)
            await client.init()
            
            log_info("Querying usage limits from gemini.google.com...")
            usage = await client.get_usage()
            await client.close()
            
            if usage.get("success"):
                print("\n" + "="*50)
                print(" GEMINI USAGE METRICS & QUOTAS")
                print("="*50)
                for meter in usage.get("meters", []):
                    feature = meter.get("feature_id")
                    use = meter.get("usage")
                    lim = meter.get("limit")
                    reset = meter.get("reset_time")
                    
                    if feature == 44973:
                        feature_name = "Premium/Image Generation"
                        use_str = f"{use * 100:.2f}% used" if isinstance(use, (int, float)) else str(use)
                        lim_str = f"Max capacity group {lim}"
                    else:
                        feature_name = f"General Quota (ID {feature})"
                        use_str = str(use)
                        lim_str = str(lim)
                    
                    print(f"Feature:    {feature_name}")
                    print(f"Usage:      {use_str}")
                    print(f"Limit:      {lim_str}")
                    if reset:
                        print(f"Resets At:  {reset}")
                    print("-" * 50)
            else:
                log_error(f"Failed to query usage limits: {usage.get('error')}")
                
        asyncio.run(show_usage())
        sys.exit(0)

    app = ImageGeneratorApp(target_dir=args.folder, log_file=args.log, num_workers=args.workers)

    if args.stats:
        app.print_stats()
    else:
        app.print_stats()
        asyncio.run(app.run())


if __name__ == "__main__":
    main()
