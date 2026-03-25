"""Pipeline run + SSE progress stream."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from src.api.schemas import PipelineRunRequest, PipelineRunResponse
from src.api.services.jobs import JobRegistry
from src.api.services.pipeline import run_pipeline_events

router = APIRouter()


@router.post("/v1/applications/{application_id}/pipeline/run", response_model=PipelineRunResponse)
async def start_pipeline(
    application_id: str,
    body: PipelineRunRequest,
    request: Request,
) -> PipelineRunResponse:
    store = request.app.state.store
    anthropic = request.app.state.anthropic
    jobs: JobRegistry = request.app.state.jobs

    job_id = jobs.create()
    st = jobs.get(job_id)
    assert st is not None

    stages = body.stages

    async def worker() -> None:
        try:
            async for ev in run_pipeline_events(application_id, store, anthropic, stages):
                await st.queue.put(ev)
        except Exception as e:
            await st.queue.put({"type": "error", "message": str(e), "application_id": application_id})
        finally:
            st.done = True
            await st.queue.put(None)

    asyncio.create_task(worker())
    return PipelineRunResponse(job_id=job_id, stream_url=f"/v1/jobs/{job_id}/stream")


@router.get("/v1/jobs/{job_id}/stream")
async def stream_job(job_id: str, request: Request) -> StreamingResponse:
    jobs: JobRegistry = request.app.state.jobs
    st = jobs.get(job_id)
    if st is None:
        raise HTTPException(status_code=404, detail="job not found")

    async def event_gen() -> Any:
        while True:
            item = await st.queue.get()
            if item is None:
                break
            yield f"data: {json.dumps(item, default=str)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")

