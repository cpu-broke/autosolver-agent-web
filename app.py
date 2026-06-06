import time
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from solver import solve


MAX_INPUT_CHARS = 5_000_000
SOLVE_TIMEOUT_SECONDS = 45

app = FastAPI(title="AutoSolver Agent API", version="1.0.0")
executor = ThreadPoolExecutor(max_workers=1)
started_at = time.time()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SolveRequest(BaseModel):
    input_text: str = Field(..., min_length=1)
    filename: str | None = None


def _normalize_rows(answer: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in answer or []:
        try:
            task = str(item[0])
            couriers = [str(x) for x in list(item[1])]
        except Exception:
            continue
        rows.append({"task": task, "couriers": couriers})
    return rows


def _rows_to_text(rows: list[dict[str, Any]]) -> str:
    return "\n".join(f"{row['task']}\t{','.join(row['couriers'])}" for row in rows)


def _build_stats(rows: list[dict[str, Any]], runtime: float, input_text: str) -> dict[str, Any]:
    task_ids: set[str] = set()
    courier_ids: set[str] = set()
    for row in rows:
        for task_id in str(row["task"]).split(","):
            task_id = task_id.strip()
            if task_id:
                task_ids.add(task_id)
        for courier_id in row["couriers"]:
            if courier_id:
                courier_ids.add(courier_id)
    return {
        "rows": len(rows),
        "tasks": len(task_ids),
        "couriers": len(courier_ids),
        "runtime": round(runtime, 4),
        "input_lines": len([line for line in input_text.splitlines() if line.strip()]),
    }


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "AutoSolver Agent API",
        "status": "ok",
        "health": "/api/health",
        "solve": "/api/solve",
    }


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "engine": "ready",
        "uptime_seconds": round(time.time() - started_at, 2),
    }


@app.post("/api/solve")
def solve_api(request: SolveRequest) -> dict[str, Any]:
    input_text = request.input_text.strip()
    if not input_text:
        raise HTTPException(status_code=400, detail="输入内容为空，请上传或粘贴赛题 txt 数据。")
    if len(input_text) > MAX_INPUT_CHARS:
        raise HTTPException(status_code=413, detail="输入文件过大，请控制在 5MB 以内。")

    started = time.time()
    future = executor.submit(solve, input_text)
    try:
        answer = future.result(timeout=SOLVE_TIMEOUT_SECONDS)
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="求解超时，请稍后重试或缩小数据规模。") from exc
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"算法运行失败：{exc}") from exc

    runtime = time.time() - started
    rows = _normalize_rows(answer)
    output_text = _rows_to_text(rows)
    return {
        "status": "completed",
        "filename": request.filename or "input.txt",
        "rows": rows,
        "output_text": output_text,
        "stats": _build_stats(rows, runtime, input_text),
    }
