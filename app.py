import os
import json
import asyncio
from typing import Dict, Any, AsyncGenerator
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

from rag import build_rag_pipeline

app = FastAPI(title="TubeMind AI API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

video_sessions: Dict[str, Dict[str, Any]] = {}
chat_histories: Dict[str, list] = {}

class ProcessVideoRequest(BaseModel):
    video_id: str

class AskRequest(BaseModel):
    video_id: str
    question: str

async def fetch_video_metadata(video_id: str) -> dict:
    url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(url)
            if r.status_code == 200:
                data = r.json()
                return {
                    "title": data.get("title", "Unknown Title"),
                    "channel": data.get("author_name", "Unknown Channel"),
                    "thumbnail": f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
                }
    except Exception:
        pass
    
    return {
        "title": "YouTube Video",
        "channel": "Unknown Channel",
        "thumbnail": f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
    }


@app.get("/")
async def serve_frontend():
    return FileResponse("static/index.html")

@app.post("/api/process_video")
async def process_video(req: ProcessVideoRequest):
    video_id = req.video_id.strip()
    if not video_id:
        raise HTTPException(status_code=400, detail="video_id is required.")

    try:
        result = build_rag_pipeline(video_id)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    meta = await fetch_video_metadata(video_id)

    video_sessions[video_id] = {
        "chain": result["chain"],
        **meta,
    }
    chat_histories[video_id] = []

    return {
        "success": True,
        "video_id": video_id,
        "title": meta["title"],
        "channel": meta["channel"],
        "thumbnail": meta["thumbnail"],
    }

@app.post("/api/ask")
async def ask_question(req: AskRequest):
    video_id = req.video_id.strip()
    question = req.question.strip()

    if video_id not in video_sessions:
        raise HTTPException(status_code=404, detail="Video not processed yet. Please load the video first.")
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    chain = video_sessions[video_id]["chain"]
    chat_histories.setdefault(video_id, []).append({"role": "user", "content": question})

    async def token_generator() -> AsyncGenerator[str, None]:
        full_response = []
        try:
            async for token in chain.astream(question):
                full_response.append(token)
                payload = json.dumps({"token": token, "done": False})
                yield f"data: {payload}\n\n"
                await asyncio.sleep(0)  
        except Exception as e:
            error_payload = json.dumps({"token": f"\n\n⚠️ Error: {str(e)}", "done": False})
            yield f"data: {error_payload}\n\n"

        chat_histories[video_id].append({"role": "assistant", "content": "".join(full_response)})
        yield f"data: {json.dumps({'token': '', 'done': True})}\n\n"

    return StreamingResponse(
        token_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )

@app.get("/api/history/{video_id}")
async def get_history(video_id: str):
    return {"history": chat_histories.get(video_id, [])}

@app.get("/api/sessions")
async def get_sessions():
    sessions = []
    for vid, data in video_sessions.items():
        sessions.append({
            "video_id": vid,
            "title": data["title"],
            "channel": data["channel"],
            "thumbnail": data["thumbnail"],
            "message_count": len(chat_histories.get(vid, [])),
        })
    return {"sessions": sessions}

@app.delete("/api/session/{video_id}")
async def delete_session(video_id: str):
    video_sessions.pop(video_id, None)
    chat_histories.pop(video_id, None)
    return {"success": True}

app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
