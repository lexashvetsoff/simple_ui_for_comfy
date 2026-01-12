import time
import json
import asyncio
import websockets
from loguru import logger
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.models.comfy_node import ComfyNode


@dataclass
class PromptProgress:
    prompt_id: str
    node_id: str
    percent: float          # 0..100
    value: Optional[float]  # текущий
    max: Optional[float]    # максимум
    status: str             # RUNNING | DONE | ERROR
    updated_at: float
    message: Optional[str] = None


# prompt_id -> progress
_PROGRESS: Dict[str, PromptProgress] = {}
_LOCK = asyncio.Lock()


# prompt_id -> task (чтобы не запускать 10 трекеров на один prompt)
_TASKS: Dict[str, asyncio.Task] = {}
_TASKS_LOCK = asyncio.Lock()


async def get_progress(prompt_id: str) -> Optional[dict]:
    async with _LOCK:
        p = _PROGRESS.get(prompt_id)
        if not p:
            return None
        return {
            "prompt_id": p.prompt_id,
            "node_id": p.node_id,
            "percent": p.percent,
            "value": p.value,
            "max": p.max,
            "status": p.status,
            "updated_at": p.updated_at,
            "message": p.message,
        }


async def set_progress(p: PromptProgress) -> None:
    async with _LOCK:
        _PROGRESS[p.prompt_id] = p


async def clear_progress(prompt_id: str) -> None:
    async with _LOCK:
        _PROGRESS.pop(prompt_id, None)


def _node_ws_url(node: ComfyNode) -> str:
    """
    node.url может быть:
      http://host:8188
      https://host
    -> ws://host:8188/ws
    """
    url = (node.base_url or "").strip().rstrip("/")
    if url.startswith("https://"):
        ws_base = "wss://" + url[len("https://"):]
    elif url.startswith("http://"):
        ws_base = "ws://" + url[len("http://"):]
    else:
        # если вдруг прилетит просто host:port
        ws_base = "ws://" + url

    return ws_base + "/ws"


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _calc_percent(value: Optional[float], maxv: Optional[float]) -> float:
    if value is None or maxv is None or maxv <= 0:
        return 0.0
    return max(0.0, min(100.0, (value / maxv) * 100.0))


async def track_prompt_progress(
    *,
    node: ComfyNode,
    prompt_id: str,
    client_id: Optional[str] = None,
) -> None:
    """
    Подписывается на WS ComfyUI и обновляет progress cache.
    Остановится сам, когда увидит DONE/ERROR или когда соединение закроется.
    """
    ws_url = _node_ws_url(node)
    if client_id:
        ws_url = ws_url + f"?clientId={client_id}"

    # init
    await set_progress(
        PromptProgress(
            prompt_id=prompt_id,
            node_id=str(node.id),
            percent=0.0,
            value=None,
            max=None,
            status="RUNNING",
            updated_at=time.time(),
        )
    )

    try:
        async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20) as ws:
            logger.info(f"[progress] WS connected: node={node.id} prompt={prompt_id}")

            # В ComfyUI события могут приходить как JSON строки
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue

                # В разных версиях ComfyUI формат может отличаться.
                # Мы обрабатываем наиболее типичные:
                # - {"type":"progress","data":{"prompt_id":"...","value":..,"max":..}}
                # - {"type":"executing","data":{"prompt_id":"...","node":"6"}} / и т.п.
                # - {"type":"executed","data":{"prompt_id":"..."}}
                # - {"type":"status","data":...}
                mtype = msg.get("type")
                data = msg.get("data") or {}

                # фильтруем только наш prompt
                pid = data.get("prompt_id") or data.get("promptId") or data.get("prompt")
                if pid and str(pid) != str(prompt_id):
                    continue

                # progress
                if mtype == "progress":
                    v = _safe_float(data.get("value"))
                    mx = _safe_float(data.get("max"))
                    pct = _calc_percent(v, mx)

                    await set_progress(
                        PromptProgress(
                            prompt_id=prompt_id,
                            node_id=str(node.id),
                            percent=pct,
                            value=v,
                            max=mx,
                            status="RUNNING",
                            updated_at=time.time(),
                        )
                    )
                    continue

                # done-ish (зависит от версии, иногда приходит "executed"/"execution_success"/etc)
                if mtype in {"executed", "execution_success", "done"}:
                    await set_progress(
                        PromptProgress(
                            prompt_id=prompt_id,
                            node_id=str(node.id),
                            percent=100.0,
                            value=None,
                            max=None,
                            status="DONE",
                            updated_at=time.time(),
                        )
                    )
                    return

                # error-ish
                if mtype in {"execution_error", "error"}:
                    err = data.get("error") or data.get("message") or "ComfyUI execution error"
                    await set_progress(
                        PromptProgress(
                            prompt_id=prompt_id,
                            node_id=str(node.id),
                            percent=100.0,
                            value=None,
                            max=None,
                            status="ERROR",
                            updated_at=time.time(),
                            message=str(err),
                        )
                    )
                    return

    except Exception as e:
        logger.warning(f"[progress] WS failed: node={node.id} prompt={prompt_id} err={e}")
        # не валим job, просто фиксируем что прогресс-канал умер
        await set_progress(
            PromptProgress(
                prompt_id=prompt_id,
                node_id=str(node.id),
                percent=0.0,
                value=None,
                max=None,
                status="RUNNING",
                updated_at=time.time(),
                message="progress_ws_disconnected",
            )
        )


async def ensure_prompt_tracking(node: ComfyNode, prompt_id: str) -> None:
    """
    Гарантирует что для prompt_id запущена только одна задача трекинга.
    """
    async with _TASKS_LOCK:
        t = _TASKS.get(prompt_id)
        if t and not t.done():
            return

        task = asyncio.create_task(track_prompt_progress(node=node, prompt_id=prompt_id))
        _TASKS[prompt_id] = task
