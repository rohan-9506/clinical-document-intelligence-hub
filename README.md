# Clinical Document Intelligence Hub (MediLyft)

A complete Proof-of-Concept demonstrating how AI can ingest unstructured clinical documents and surface structured, actionable intelligence. This solution addresses the manual burden of reviewing fragmented healthcare data by transforming documents (like intake forms, handwritten notes, and ECG reports) into consistent, decision-ready outputs.

## Live Demonstration
🔥 **The application is fully deployed and live on Render (Free Tier):**
👉 [https://medilyft-ai.onrender.com](https://medilyft-ai.onrender.com)

## Architecture & Design Notes

- **Frontend (Vanilla HTML/CSS/JS)**: A bespoke, glassmorphism dark-mode UI with dynamic micro-animations. Features a split-screen dashboard to read the native document on the left while reviewing extracted intelligence on the right.
- **Backend (FastAPI)**: A high-performance Python backend serving the web application. It handles PDF-to-Image parsing, orchestration of AI models, and database communication.
- **Database (MongoDB Atlas Cloud + GridFS)**: Uses MongoDB to permanently store extracted patient JSON records. Uses **GridFS** to break down and securely store the raw multi-megabyte PDF binaries, streaming them directly to the frontend viewer.
- **Dual-LLM Consensus Engine (Optimized)**: 
  - The AI processor leverages both **Google Gemini Flash** and **Groq Vision** simultaneously. 
  - **Performance**: We optimized the AI pipeline by collapsing multi-pass extraction into a highly efficient **Single-Pass extraction and scoring prompt**, effectively cutting AI latency in half.
  - Using Python's `ThreadPoolExecutor`, both LLM requests are fired **in parallel**. The results are mathematically merged to compute a `consensus_rate`, flagging contradictory data for human review.

## Prerequisites

1. **Python 3.10+**
2. **MongoDB Community Server**: Must be installed and running locally on the default port (`27017`).
3. **API Keys**: You will need free API keys from [Google AI Studio (Gemini)](https://aistudio.google.com/) and [Groq Console](https://console.groq.com/).

## Setup Instructions

1. **Activate the Virtual Environment**:
   ```powershell
   # Windows
   .\venv\Scripts\Activate.ps1
   # Mac/Linux
   source venv/bin/activate
   ```

2. **Install Dependencies**:
   ```powershell
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**:
   Create a `.env` file in the `backend/` folder (or set them in your terminal) with the following keys:
   ```env
   GEMINI_API_KEY="your_google_gemini_key"
   GROQ_API_KEY="your_groq_api_key"
   MONGO_URI="mongodb://localhost:27017"
   ```

4. **Start the Application**:
   Run the FastAPI server using Uvicorn:
   ```powershell
   python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
   ```

5. **Access the Dashboard**:
   Open your browser and navigate to: `http://127.0.0.1:8000`

## How to use the Demo

1. On the upload screen, drag and drop the provided `Advanced_Clinical_Report_v2.pdf` from the `sample_documents/` folder.
2. Click **Generate Intelligence**.
3. The backend will parse the PDF, save it to GridFS, and run the Dual-LLM Vision models in parallel to extract structured data.
4. The Split-Screen dashboard will render, allowing you to review the native PDF streamed from MongoDB alongside the AI-extracted patient info, risk flags, and ICD codes.
5. Do a "Hard Refresh" (Ctrl+Shift+R). Your patient's historical data and PDF will automatically load from the database into the sidebar!
