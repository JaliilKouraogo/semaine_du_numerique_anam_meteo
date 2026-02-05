
from fastapi import FastAPI, File, UploadFile, HTTPException
from typing import Dict
import sys
import os
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))
from engine import recognize_icons

app = FastAPI(
    title="ANAM Weather Icon Recognition API",
    description="API to extract weather icons from Burkina Faso weather maps using VLM (MiniCPM-V).",
    version="1.0.0"
)

@app.get("/")
async def root():
    return {"message": "ANAM Weather API is running. Go to /docs for Swagger documentation."}

@app.post("/recognize", response_model=Dict[str, str])
async def recognize(file: UploadFile = File(...)):
    """
    Upload a weather map image (PNG/JPG) and get recognized icons for major cities.
    """
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image.")
    
    try:
        content = await file.read()
        results = recognize_icons(content)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
