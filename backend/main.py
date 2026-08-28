from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from typing import List
import json
import uvicorn
import os
from bson import ObjectId
from contextlib import asynccontextmanager
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket
from datetime import datetime

from backend.document_parser import process_file
from backend.ai_processor import analyze_document_images

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Connect to MongoDB
    mongo_uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    app.mongodb_client = AsyncIOMotorClient(mongo_uri)
    app.mongodb = app.mongodb_client["medilyft"]
    app.gridfs = AsyncIOMotorGridFSBucket(app.mongodb)
    print("Connected to MongoDB with GridFS!")
    yield
    # Disconnect on shutdown
    app.mongodb_client.close()
    print("Disconnected from MongoDB.")

app = FastAPI(title="Clinical Document Intelligence Hub", lifespan=lifespan)

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/patients")
async def get_patients():
    """Returns a list of all historically processed patients from MongoDB."""
    patients = []
    cursor = app.mongodb["patients"].find().sort("created_at", -1)
    async for document in cursor:
        document["_id"] = str(document["_id"]) # Convert ObjectId to string
        patients.append(document)
    return {"status": "success", "data": patients}

@app.get("/api/documents/{file_id}")
async def get_document(file_id: str):
    """Retrieves a source document (PDF) from GridFS."""
    try:
        grid_out = await app.gridfs.open_download_stream(ObjectId(file_id))
        
        async def file_stream():
            while True:
                chunk = await grid_out.readchunk()
                if not chunk:
                    break
                yield chunk
                
        return StreamingResponse(file_stream(), media_type="application/pdf")
    except Exception as e:
        raise HTTPException(status_code=404, detail="Document not found")

@app.delete("/api/patients/{patient_id}")
async def delete_patient(patient_id: str):
    """Deletes a patient record and its associated document from GridFS."""
    try:
        # Find the patient to get the file_id
        patient = await app.mongodb["patients"].find_one({"_id": ObjectId(patient_id)})
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")

        # Delete from GridFS if it exists
        file_id = patient.get("file_id")
        if file_id:
            try:
                await app.gridfs.delete(ObjectId(file_id))
            except Exception as gridfs_error:
                print(f"Error deleting file from GridFS: {gridfs_error}")

        # Delete the patient document
        result = await app.mongodb["patients"].delete_one({"_id": ObjectId(patient_id)})
        if result.deleted_count == 1:
            return {"status": "success", "message": "Patient deleted successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to delete patient record")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/analyze")
async def analyze_documents(files: List[UploadFile] = File(...)):
    """
    Receives multiple clinical documents (PDFs or Images), converts them to images,
    and runs them through the AI consensus engine.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    all_images = []
    
    for file in files:
        contents = await file.read()
        filename = file.filename.lower()
        
        try:
            # Save raw file to GridFS
            grid_in = app.gridfs.open_upload_stream(filename)
            await grid_in.write(contents)
            await grid_in.close()
            saved_file_id = str(grid_in._id)

            # Process for AI Extraction
            images = process_file(contents, filename)
            all_images.extend(images)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error processing {filename}: {str(e)}")

    if not all_images:
        raise HTTPException(status_code=400, detail="No valid images could be extracted")

    # Run the extracted images through the Multi-Pass AI Critic Pattern
    try:
        json_result_str = analyze_document_images(all_images)
        # Parse the JSON string from Gemini back into a Python dictionary
        try:
            # Clean up the response in case Gemini wrapped it in markdown code blocks
            clean_json_str = json_result_str.strip().strip('```json').strip('```')
            result_dict = json.loads(clean_json_str)
            
            # Save to MongoDB
            db_record = {
                **result_dict,
                "created_at": datetime.utcnow(),
                "file_id": saved_file_id # Link to GridFS document
            }
            inserted = await app.mongodb["patients"].insert_one(db_record)
            result_dict["_id"] = str(inserted.inserted_id)

            return {"status": "success", "data": result_dict}
        except json.JSONDecodeError:
            return {"status": "error", "detail": "AI returned invalid JSON", "raw_output": json_result_str}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Processing Error: {str(e)}")

# Create frontend directory if it doesn't exist
os.makedirs("frontend", exist_ok=True)
# Mount the frontend directory to serve static files (HTML, CSS, JS) at the root
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
