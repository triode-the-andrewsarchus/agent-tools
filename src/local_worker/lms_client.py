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


class ModelLoadError(RuntimeError):
    """Raised when model loading fails on GPU with diagnostics and downgrade advice."""

    def __init__(
        self,
        message: str,
        *,
        model_key: str,
        worker_class: str,
        vram_info: dict[str, int] | None = None,
        is_oom: bool = False,
        suggestions: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.model_key = model_key
        self.worker_class = worker_class
        self.vram_info = vram_info
        self.is_oom = is_oom
        self.suggestions = suggestions or []


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
        """Load a model via lms CLI on GPU only. Blocks until loaded.

        Strict GPU-only policy:
          1. Retries 'max' up to MAX_GPU_RETRIES times with short waits — VRAM
             usage from desktop apps fluctuates, so a brief wait often frees enough.
          2. Steps through high partial-GPU fractions (0.90 -> 0.85 -> 0.75).
             These keep 75%+ of layers on GPU for acceptable performance.
          3. NO CPU fallback: if all GPU attempts fail, raises ModelLoadError
             with VRAM diagnostics and concrete downgrade suggestions (e.g.
             downgrade to cheap 9B model, reduce context length, or handle in supervisor).
        """
        MAX_GPU_RETRIES = 3
        RETRY_WAIT = 5  # seconds between max-offload retries

        if profile.gpu_offload == "max":
            attempts = [("max", RETRY_WAIT)] * MAX_GPU_RETRIES
            attempts += [(f, 2) for f in ("0.90", "0.85", "0.75")]
        else:
            attempts = [(profile.gpu_offload, 0)]

        last_error: str = ""
        seen_gpu_settings: list[str] = []
        is_vram_oom: bool = False

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
            is_vram_oom = ("unable to allocate CUDA" in msg or "CUDA0 buffer" in msg or "out of memory" in msg.lower())

            if is_vram_oom:
                log.warning("VRAM OOM [%s] — waiting %ds before next attempt...",
                            attempt_label, wait_on_fail)
                if wait_on_fail > 0:
                    await asyncio.sleep(wait_on_fail)
                continue

            # Non-VRAM error — don't retry
            log.error("Non-VRAM load error [%s]: %s", attempt_label, msg[:200])
            break

        # If we reached here, GPU load failed. No CPU fallback.
        vram_info = await self.get_vram_info()
        free_mb = vram_info.get("free_mb") if vram_info else None
        total_mb = vram_info.get("total_mb") if vram_info else None

        suggestions: list[str] = []
        if profile.worker_class == "smart":
            if free_mb is not None and free_mb >= 3500:
                suggestions.append(
                    f"Downgrade to 'cheap' worker class: Qwen3.5-9B requires ~6.1 GB VRAM and can fit in current VRAM ({free_mb} MB free)."
                )
            suggestions.append(
                f"Reduce context length for smart model from {profile.context_length} (e.g. 4096 or 2048) to lower KV cache memory."
            )
            suggestions.append("Close GPU-heavy desktop applications to free VRAM for 27B model.")
            suggestions.append("Do not offload to local LLM; handle directly via Antigravity supervisor.")
        else:
            suggestions.append(f"Free desktop GPU memory: currently only {free_mb if free_mb else 'unknown'} MB free.")
            suggestions.append(f"Reduce context length from {profile.context_length} to 4096 or 2048.")
            suggestions.append("Do not offload to local LLM; handle directly via Antigravity supervisor.")

        vram_desc = f"{free_mb} MB free / {total_mb} MB total" if free_mb and total_mb else "unknown"
        clean_last_err = last_error.strip().splitlines()[-1] if last_error.strip() else "unknown"
        error_msg = (
            f"GPU load failed for '{profile.lms_model_key}' ({profile.worker_class} worker). "
            f"No CPU fallback (GPU-only policy). VRAM status: {vram_desc}. "
            f"Attempts: {', '.join(seen_gpu_settings)}. Last error: {clean_last_err}. "
            f"Actionable alternatives: " + " | ".join(suggestions)
        )

        raise ModelLoadError(
            error_msg,
            model_key=profile.lms_model_key,
            worker_class=profile.worker_class,
            vram_info=vram_info,
            is_oom=is_vram_oom,
            suggestions=suggestions,
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

    async def get_vram_info(self) -> dict[str, int] | None:
        """Query total, used, and free VRAM in MB via nvidia-smi."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "nvidia-smi",
                "--query-gpu=memory.total,memory.used,memory.free",
                "--format=csv,noheader,nounits",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0 and stdout:
                parts = [int(p.strip()) for p in stdout.decode().strip().split("\n")[0].split(",")]
                if len(parts) == 3:
                    return {
                        "total_mb": parts[0],
                        "used_mb": parts[1],
                        "free_mb": parts[2],
                    }
        except Exception:
            pass
        return None

    async def get_vram_free_mb(self) -> int | None:
        """Query free VRAM in MB via nvidia-smi."""
        info = await self.get_vram_info()
        return info["free_mb"] if info else None
