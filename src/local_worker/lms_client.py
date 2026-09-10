"""LM Studio client: REST API for inference + CLI for model load/unload."""

from __future__ import annotations

import asyncio
import logging
import subprocess
from dataclasses import dataclass
from typing import Literal

import aiohttp

from .config import WorkerProfile

log = logging.getLogger(__name__)

HANDOFF_SYSTEM = (
    "You are a worker that has hit your context limit. "
    "Produce a compact handoff summary of what you established, key findings, "
    "what remains unresolved, and your recommendation for what should happen next. "
    "Be concise — maximum 300 words."
)
HANDOFF_PROMPT = (
    "Your context is about to be truncated. Write a compact handoff summary "
    "covering: what you found, important conclusions, what is still unresolved, "
    "and your recommendation for next steps."
)


@dataclass
class ChatResult:
    text: str
    finish_reason: str          # "stop" | "length" | "error" | "timeout"
    input_tokens: int | None
    output_tokens: int | None


class LMSClient:
    """Wraps LM Studio REST API and lms CLI."""

    def __init__(self, base_url: str, cli_path: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._cli_path = cli_path
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=None)  # per-request timeouts used instead
        )

    async def stop(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    # ──────────────────────────────────────────────
    # Model management (via lms CLI)
    # ──────────────────────────────────────────────

    async def load_model(self, profile: WorkerProfile) -> None:
        """Load a model via lms CLI. Blocks until loaded.

        Strategy when VRAM is tight:
          1. Retry 'max' up to MAX_GPU_RETRIES times with short waits — VRAM
             usage from other apps fluctuates, so a brief wait often frees enough.
          2. Step through high partial-GPU fractions (0.90 → 0.85 → 0.75).
             These keep most layers on GPU for usable performance.
          3. Only fall back to CPU ('off') if profile.gpu_fallback_cpu is True.
             CPU inference on a 27B model is extremely slow; prefer a clean
             model_error so the caller can decide what to do.
        """
        MAX_GPU_RETRIES = 3
        RETRY_WAIT = 5  # seconds between max-offload retries

        # Build the attempt sequence
        if profile.gpu_offload == "max":
            # Retry full-GPU first, then step down through high-GPU fractions
            attempts = [("max", RETRY_WAIT)] * MAX_GPU_RETRIES
            attempts += [(f, 2) for f in ("0.90", "0.85", "0.75")]
        else:
            # Use the configured value directly (no retries for explicit fractions)
            attempts = [(profile.gpu_offload, 0)]

        # Optionally allow CPU fallback
        if getattr(profile, "gpu_fallback_cpu", False):
            attempts += [("off", 0)]

        last_error: str = ""
        seen_gpu_settings: list[str] = []
        for gpu_setting, wait_on_fail in attempts:
            cmd = [
                self._cli_path, "load", profile.lms_model_key,
                "-y",
                "--context-length", str(profile.context_length),
                "--parallel", str(profile.parallel),
                "--gpu", gpu_setting,
                "--identifier", profile.worker_class,
            ]
            attempt_label = f"gpu={gpu_setting}" + (
                f" (retry {seen_gpu_settings.count(gpu_setting) + 1}/{MAX_GPU_RETRIES})"
                if gpu_setting == "max" and seen_gpu_settings.count(gpu_setting) > 0
                else ""
            )
            log.info("Loading model [%s]: %s %s",
                     attempt_label, profile.lms_model_key, profile.worker_class)
            seen_gpu_settings.append(gpu_setting)

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                log.info("Model loaded: %s as '%s' [%s]",
                         profile.lms_model_key, profile.worker_class, attempt_label)
                return

            msg = stdout.decode(errors="replace").strip() if stdout else "unknown error"
            last_error = msg
            is_vram_oom = "unable to allocate CUDA" in msg or "CUDA0 buffer" in msg

            if is_vram_oom:
                log.warning("VRAM OOM [%s] — waiting %ds before next attempt...",
                            attempt_label, wait_on_fail)
                if wait_on_fail > 0:
                    await asyncio.sleep(wait_on_fail)
                continue

            # Non-VRAM error — don't retry
            log.error("Non-VRAM load error [%s]: %s", attempt_label, msg[:200])
            break

        raise RuntimeError(
            f"lms load failed for {profile.lms_model_key} after all attempts. "
            f"Last error: {last_error[-300:] if last_error else 'unknown'}"
        )

    async def unload_model(self, identifier: str) -> None:
        """Unload a model by its identifier."""
        cmd = [self._cli_path, "unload", identifier]
        log.info("Unloading model identifier: %s", identifier)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            msg = stdout.decode(errors="replace").strip() if stdout else "unknown error"
            log.warning("lms unload rc=%d: %s", proc.returncode, msg)
            # Non-fatal: model may already be unloaded

    async def unload_all(self) -> None:
        """Unload all loaded models."""
        cmd = [self._cli_path, "unload", "--all"]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        await proc.communicate()

    async def get_model_state(
        self, model_key: str
    ) -> Literal["loaded", "not-loaded", "unknown"]:
        """Query model load state from LM Studio REST API."""
        encoded = model_key.replace("/", "%2F")
        try:
            async with self._session.get(
                f"{self._base_url}/api/v0/models/{encoded}",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 404:
                    return "not-loaded"
                data = await resp.json()
                return data.get("state", "not-loaded")
        except Exception as e:
            log.debug("get_model_state error: %s", e)
            return "unknown"

    # ──────────────────────────────────────────────
    # Inference
    # ──────────────────────────────────────────────

    async def chat_complete(
        self,
        model_identifier: str,
        messages: list[dict],
        max_tokens: int,
        timeout: float,
    ) -> ChatResult:
        """Run a chat completion. Returns ChatResult with finish_reason."""
        payload = {
            "model": model_identifier,
            "messages": messages,
            "max_tokens": max_tokens,
            "stream": False,
        }
        try:
            async with self._session.post(
                f"{self._base_url}/v1/chat/completions",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    return ChatResult(
                        text="",
                        finish_reason="error",
                        input_tokens=None,
                        output_tokens=None,
                    )
                data = await resp.json()

            choice = data["choices"][0]
            usage = data.get("usage", {})
            return ChatResult(
                text=choice["message"]["content"],
                finish_reason=choice.get("finish_reason", "stop"),
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=usage.get("completion_tokens"),
            )
        except asyncio.TimeoutError:
            return ChatResult(text="", finish_reason="timeout",
                              input_tokens=None, output_tokens=None)
        except Exception as e:
            log.warning("chat_complete error: %s", e)
            return ChatResult(text="", finish_reason="error",
                              input_tokens=None, output_tokens=None)

    async def generate_handoff_summary(
        self, model_identifier: str, original_prompt: str, partial_result: str
    ) -> str:
        """Ask the model for a compact handoff summary when context is exhausted."""
        messages = [
            {"role": "system", "content": HANDOFF_SYSTEM},
            {"role": "user", "content": original_prompt},
            {"role": "assistant", "content": partial_result},
            {"role": "user", "content": HANDOFF_PROMPT},
        ]
        result = await self.chat_complete(
            model_identifier=model_identifier,
            messages=messages,
            max_tokens=512,
            timeout=60.0,
        )
        return result.text or "(no handoff summary generated)"

    # ──────────────────────────────────────────────
    # Health / observability
    # ──────────────────────────────────────────────

    async def is_reachable(self) -> bool:
        """Check if LM Studio REST API is responding."""
        try:
            async with self._session.get(
                f"{self._base_url}/api/v0/models",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                return resp.status == 200
        except Exception:
            return False

    async def get_vram_free_mb(self) -> int | None:
        """Query free VRAM via nvidia-smi."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "nvidia-smi",
                "--query-gpu=memory.free",
                "--format=csv,noheader,nounits",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0 and stdout:
                return int(stdout.decode().strip().split("\n")[0])
        except Exception:
            pass
        return None
