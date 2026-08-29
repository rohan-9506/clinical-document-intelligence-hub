# Firstsource Clinical Document Intelligence Hub (PoC)

An advanced Proof-of-Concept (PoC) built for Firstsource to demonstrate how Dual-LLM Vision models can securely ingest unstructured, fragmented clinical documents and automatically surface structured, decision-ready intelligence.

This solution directly addresses the massive manual burden of reviewing healthcare data by transforming complex documents (intake forms, handwritten doctor's notes, lab reports, ECG scans) into standardized outputs, reducing a 15-minute chart review into a 10-second automated workflow.

## 🚀 Live Demonstration
🔥 **The application is fully deployed and live on Render (Free Tier):**
👉 [https://medilyft-ai.onrender.com](https://medilyft-ai.onrender.com)

---

## 🏗️ Solution Architecture & Design Flow

1. **Ingestion (Frontend)**: A bespoke, glassmorphism dark-mode UI built entirely in Vanilla HTML/CSS/JS (no heavy frameworks). Users can drag-and-drop multiple fragmented files (`.pdf`, `.jpg`, `.png`, `.txt`) simultaneously.
2. **Processing (FastAPI Backend)**: A high-performance Python server parses the documents. Raw text files are intelligently rendered into image matrices, allowing them to be processed by Vision models seamlessly.
3. **Dual-LLM Extraction Engine**: 
   - Uses `ThreadPoolExecutor` to simultaneously fire both **Google Gemini 2.5 Flash** and **Groq Llama 3.2 Vision** in parallel.
   - We utilize a highly efficient **Single-Pass prompt** that extracts demographics, summarizes clinical history, extracts risk flags, and automatically codes ICD-10 billing data—all while simultaneously assigning an AI confidence score to every field.
4. **Dynamic Consensus Merging**: The backend mathematically merges the two JSON responses. If models disagree on critical data (like a medication status), the field is flagged and downgraded in confidence to enforce human-in-the-loop review.
5. **Storage & Visualization**: 
   - Extracted JSON records are stored in **MongoDB Atlas**.
   - Raw, multi-megabyte PDF binaries are shredded and securely stored in **MongoDB GridFS**, streaming directly to the frontend's split-screen viewer for auditing.

---

## 🛠️ Implementation Highlights & Optimizations

- **Dynamic Timeout & Fallback Loops**: Free-tier AI endpoints are notorious for rate limits and timeouts. We implemented an automatic fallback loop. If the primary Llama 90B Vision model throws a `429 Quota Exceeded`, the system instantly pivots to a backup 11B model. If a model hangs, a dynamic timeout abandons the thread to prevent the UI from freezing.
- **Hardware-Aware Caps**: Groq Vision has a strict hardware limitation of 3 images per request. The backend actively monitors document length and safely truncates the payload to prevent `400 Bad Request` crashes when processing massive PDFs.
- **Token Efficiency**: We increased `max_output_tokens` to `4096` to completely eliminate JSON truncation errors that were occurring during the generation of complex medical arrays.
- **Feature Flag Architecture**: Includes a `USE_GEMINI` toggle in the backend, allowing developers to safely disable unstable models during live demos and route 100% of traffic to the hyper-fast Groq engine.

---

## 💻 Setup Instructions

1. **Prerequisites**: 
   - Python 3.10+
   - MongoDB Community Server running locally on port `27017`.
   - API Keys from [Google AI Studio](https://aistudio.google.com/) and [Groq Console](https://console.groq.com/).

2. **Install Dependencies**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: .\venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**:
   Create a `.env` file in the `backend/` directory:
   ```env
   GEMINI_API_KEY="your_google_gemini_key"
   GROQ_API_KEY="your_groq_api_key"
   MONGO_URI="mongodb://localhost:27017"
   ```

4. **Start the Application**:
   Run the FastAPI server using Uvicorn:
   ```bash
   python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
   ```
   Open your browser and navigate to: `http://127.0.0.1:8000`

---

## 🧪 How to use the Demo

1. **Single File Upload**: On the upload screen, drag and drop the provided `Advanced_Clinical_Report_v2.pdf` from the `sample_documents/` folder.
2. **Multiple File Upload**: You can drag and drop multiple files at the same time (e.g., a PDF lab report, a `.txt` file, AND a JPEG ECG scan). The AI will dynamically combine and merge the fragmented data into a single, comprehensive patient profile. *(Note: This feature is designed to fuse data for a **single patient**. Do not upload documents for different patients at the same time).*
3. Click **Generate Intelligence**.
4. The Split-Screen dashboard will render, allowing you to review the native document streamed from MongoDB alongside the AI-extracted patient info, risk flags, and auto-generated ICD codes.

---

## 🔮 Business Impact & Next Steps

This PoC proves that unstructured clinical data ingestion can be securely automated with high accuracy. 

**Next Steps for Production:**
1. Upgrading from free-tier APIs to Enterprise provisioned instances for unlimited document lengths and guaranteed uptime.
2. Integrating directly with Electronic Health Record (EHR) systems like EPIC or Cerner via standard FHIR APIs.
3. Implementing continuous alignment loops where human physician corrections in the dashboard are used to fine-tune the extraction models.
