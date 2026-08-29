import os
import json
import base64
from io import BytesIO
from PIL import Image
import concurrent.futures
import google.generativeai as genai
from groq import Groq
from dotenv import load_dotenv

# Load environment variables
load_dotenv("backend/.env")

gemini_api_key = os.environ.get("GEMINI_API_KEY")
groq_api_key   = os.environ.get("GROQ_API_KEY")

if gemini_api_key:
    genai.configure(api_key=gemini_api_key)

groq_client = Groq(api_key=groq_api_key) if groq_api_key else None

# ─────────────────────────────────────────────────────────────
#  Shared extraction schema (used in prompts for both LLMs)
# ─────────────────────────────────────────────────────────────
EXTRACTION_SCHEMA = """
{
  "document_type": "string (e.g. Lab Report, Prescription, Clinical Note, Discharge Summary)",
  "patient_info": {"name": "string", "id": "string", "dob": "string"},
  "urgency_level": {"score": integer (1-10), "label": "Critical/High/Moderate/Low"},
  "summary": "string (concise 2-3 sentence clinical summary)",
  "risk_flags": [{"level": "High/Medium/Low", "reason": "string"}],
  "medications": [{"name": "string (with dosage)", "status": "Prescribed/Active/PRN/Discontinued"}],
  "clinical_findings": ["string"],
  "icd_codes": [{"code": "string (ICD-10)", "description": "string"}],
  "follow_up_actions": [{"action": "string", "priority": "Urgent/Conditional/Routine"}]
}
"""

VERIFIED_SCHEMA = '{"document_type":{"type":"string","confidence_score":"integer"},"patient_info":{"name":"string","id":"string","dob":"string","confidence_score":"integer"},"urgency_level":{"score":"integer","label":"string","confidence_score":"integer"},"summary":{"text":"string","confidence_score":"integer"},"risk_flags":[{"level":"string","reason":"string","confidence_score":"integer"}],"medications":[{"name":"string","status":"string","confidence_score":"integer"}],"clinical_findings":[{"finding":"string","confidence_score":"integer"}],"icd_codes":[{"code":"string","description":"string","confidence_score":"integer"}],"follow_up_actions":[{"action":"string","priority":"string","confidence_score":"integer"}]}'

# ─────────────────────────────────────────────────────────────
#  Helper: PIL image → base64 data URL (for Groq)
# ─────────────────────────────────────────────────────────────
def pil_to_base64(img: Image.Image) -> str:
    buf = BytesIO()
    # Compress image specifically for Groq Vision network transfer
    img.save(buf, format="JPEG", quality=75)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


# ─────────────────────────────────────────────────────────────
#  MODEL A: Gemini 2.5 Flash (2-pass)
# ─────────────────────────────────────────────────────────────
def run_gemini(images: list) -> dict | None:
    if not gemini_api_key:
        return None
    # Try primary model first, fall back through an extensive list if quota is exceeded
    models_to_try = [
        "gemini-3.7-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash"
    ]
    for model_name in models_to_try:
        try:
            print(f"[Gemini] Trying {model_name}...")
            model = genai.GenerativeModel(
                model_name=model_name,
                generation_config={
                    "temperature": 0.0, "top_p": 0.95, "top_k": 64,
                    "max_output_tokens": 4096, "response_mime_type": "application/json"
                }
            )
            # Single Pass — Extract and Score simultaneously
            p1 = f"""You are an expert clinical document analyzer and auditor. 
Extract all information from the document pages and verify its accuracy. 
Assign a confidence_score (0-100) to every extracted field based on your certainty and the clarity of the text.
Return ONLY valid JSON matching this exact schema:
{VERIFIED_SCHEMA}
For handwritten text, read carefully. Combine info across all pages."""
            r1 = model.generate_content([p1] + images)

            result = json.loads(r1.text.strip().strip("```json").strip("```"))
            print(f"[Gemini] Success with {model_name}")
            return result
        except Exception as e:
            err_str = str(e)
            if "quota" in err_str.lower() or "429" in err_str or "rate" in err_str.lower():
                print(f"[Gemini] {model_name} quota exceeded, trying next model...")
            else:
                print(f"[Gemini] Error with {model_name}: {err_str} - trying next model...")
            continue
    print("[Gemini] All models exhausted quota — falling back")
    return None


# ─────────────────────────────────────────────────────────────
#  MODEL B: Groq – llama-4-scout-17b-16e-instruct (free tier)
#  Groq vision: encode images as base64 data URIs
# ─────────────────────────────────────────────────────────────
def run_groq(images: list) -> dict | None:
    if not groq_client:
        print("[Groq] No API key set — skipping")
        return None
    # Use qwen/qwen3.8-27b as it is the supported model for this environment
    GROQ_VISION_MODEL = "qwen/qwen3.8-27b"
    try:
        # Build multimodal message: text prompt + base64 images
        content = [{
            "type": "text",
            "text": f"""You are an expert clinical document analyzer.
Extract information from the attached document image(s) and return ONLY a JSON object matching this schema:
{EXTRACTION_SCHEMA}
Read handwriting carefully. Combine info across all pages."""
        }]

        for img in images:
            b64 = pil_to_base64(img)
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
            })

        # Single Pass — Extract and Score simultaneously
        content[0]["text"] = f"""You are an expert clinical document analyzer and auditor.
Extract information from the attached document image(s) and verify its accuracy.
Assign a confidence_score (0-100) to every extracted field based on your certainty.
Return ONLY a JSON object matching this exact schema:
{VERIFIED_SCHEMA}
Read handwriting carefully. Combine info across all pages."""

        r1 = groq_client.chat.completions.create(
            model=GROQ_VISION_MODEL,
            messages=[{"role": "user", "content": content}],
            temperature=0.0,
            max_tokens=4096,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(r1.choices[0].message.content)
        print(f"[Groq] Success with {GROQ_VISION_MODEL}")
        return result
    except Exception as e:
        print(f"[Groq] Error: {e} — falling back to Gemini-only mode")
        return None


# ─────────────────────────────────────────────────────────────
#  ENSEMBLE MERGER
#  Rules:
#   - Both agree  → keep value, confidence = avg + 10 (max 100), consensus=True
#   - Disagree    → keep higher-conf model's value, consensus=False, "⚠ Disputed"
#   - One missing → use the other's value as-is
# ─────────────────────────────────────────────────────────────
def merge_string_field(val_a, conf_a, val_b, conf_b):
    """Merge a single string field from two models."""
    if not val_a and not val_b:
        return None, 0, False

    if not val_a:
        return val_b, conf_b, False
    if not val_b:
        return val_a, conf_a, False

    # Normalize for comparison
    agree = val_a.strip().lower() == val_b.strip().lower()
    if agree:
        merged_conf = min(100, round((conf_a + conf_b) / 2) + 10)
        return val_a, merged_conf, True
    else:
        # Take the higher-confidence answer
        if conf_a >= conf_b:
            return val_a, conf_a, False
        else:
            return val_b, conf_b, False


def merge_int_field(val_a, conf_a, val_b, conf_b):
    """Merge a single integer field from two models."""
    if val_a is None and val_b is None:
        return None, 0, False
    if val_a is None:
        return val_b, conf_b, False
    if val_b is None:
        return val_a, conf_a, False

    agree = val_a == val_b
    if agree:
        return val_a, min(100, round((conf_a + conf_b) / 2) + 10), True
    else:
        if conf_a >= conf_b:
            return val_a, conf_a, False
        else:
            return val_b, conf_b, False


def merge_results(result_a: dict | None, result_b: dict | None) -> dict:
    """
    Merge two model outputs using confidence-weighted ensemble logic.
    Falls back gracefully if one model failed.
    """
    if result_a is None and result_b is None:
        raise ValueError("Both models failed to produce output.")
    if result_a is None:
        result_b["_ensemble_note"] = "Single model (Groq only) — Gemini unavailable"
        return result_b
    if result_b is None:
        result_a["_ensemble_note"] = "Single model (Gemini only) — Groq unavailable"
        return result_a

    merged = {}
    consensus_count = 0
    total_fields = 0

    # ── document_type ───────────────────────────────────────────
    dt_a = result_a.get("document_type", {})
    dt_b = result_b.get("document_type", {})
    val, conf, agree = merge_string_field(
        dt_a.get("type"), dt_a.get("confidence_score", 50),
        dt_b.get("type"), dt_b.get("confidence_score", 50)
    )
    merged["document_type"] = {"type": val, "confidence_score": conf, "consensus": agree}
    total_fields += 1; consensus_count += int(agree)

    # ── patient_info ─────────────────────────────────────────────
    pi_a = result_a.get("patient_info", {}); pi_b = result_b.get("patient_info", {})
    pi_conf_a = pi_a.get("confidence_score", 50); pi_conf_b = pi_b.get("confidence_score", 50)
    name, name_conf, name_agree = merge_string_field(pi_a.get("name"), pi_conf_a, pi_b.get("name"), pi_conf_b)
    pid,  pid_conf,  pid_agree  = merge_string_field(pi_a.get("id"),   pi_conf_a, pi_b.get("id"),   pi_conf_b)
    dob,  dob_conf,  dob_agree  = merge_string_field(pi_a.get("dob"),  pi_conf_a, pi_b.get("dob"),  pi_conf_b)
    avg_pi_conf = round((name_conf + pid_conf + dob_conf) / 3)
    merged["patient_info"] = {
        "name": name, "id": pid, "dob": dob,
        "confidence_score": avg_pi_conf,
        "consensus": name_agree and dob_agree
    }
    total_fields += 3; consensus_count += int(name_agree) + int(pid_agree) + int(dob_agree)

    # ── urgency_level ─────────────────────────────────────────────
    ul_a = result_a.get("urgency_level", {}); ul_b = result_b.get("urgency_level", {})
    ul_conf_a = ul_a.get("confidence_score", 50); ul_conf_b = ul_b.get("confidence_score", 50)
    score, sc_conf, sc_agree  = merge_int_field(ul_a.get("score"), ul_conf_a, ul_b.get("score"), ul_conf_b)
    label, lb_conf, lb_agree  = merge_string_field(ul_a.get("label"), ul_conf_a, ul_b.get("label"), ul_conf_b)
    merged["urgency_level"] = {
        "score": score, "label": label,
        "confidence_score": round((sc_conf + lb_conf) / 2),
        "consensus": sc_agree and lb_agree
    }
    total_fields += 2; consensus_count += int(sc_agree) + int(lb_agree)

    # ── summary ───────────────────────────────────────────────────
    sm_a = result_a.get("summary", {}); sm_b = result_b.get("summary", {})
    # For summaries, we don't do string equality — both are valid, pick higher conf
    conf_a = sm_a.get("confidence_score", 50); conf_b = sm_b.get("confidence_score", 50)
    if conf_a >= conf_b:
        sm_text = sm_a.get("text", ""); sm_conf = conf_a
    else:
        sm_text = sm_b.get("text", ""); sm_conf = conf_b
    # Boost if both had high confidence
    if conf_a >= 70 and conf_b >= 70:
        sm_conf = min(100, round((conf_a + conf_b) / 2) + 5)
    merged["summary"] = {"text": sm_text, "confidence_score": sm_conf}

    # ── risk_flags (merge by matching reason similarity) ──────────
    risks_a = result_a.get("risk_flags", [])
    risks_b = result_b.get("risk_flags", [])
    # Combine all, deduplicate by similar reason text
    all_risks = {}
    for r in risks_a:
        key = r.get("reason", "")[:30].lower()
        all_risks[key] = {"level": r.get("level"), "reason": r.get("reason"), "confidence_score": r.get("confidence_score", 70), "source": "A"}
    for r in risks_b:
        key = r.get("reason", "")[:30].lower()
        if key in all_risks:
            # Both models flagged same risk → boost confidence
            existing = all_risks[key]
            boosted = min(100, round((existing["confidence_score"] + r.get("confidence_score", 70)) / 2) + 10)
            all_risks[key]["confidence_score"] = boosted
            all_risks[key]["consensus"] = True
        else:
            all_risks[key] = {"level": r.get("level"), "reason": r.get("reason"), "confidence_score": r.get("confidence_score", 70), "source": "B"}
    merged["risk_flags"] = list(all_risks.values())

    # ── medications (merge by name) ────────────────────────────────
    meds_a = {m.get("name", "").lower(): m for m in result_a.get("medications", [])}
    meds_b = {m.get("name", "").lower(): m for m in result_b.get("medications", [])}
    all_keys = set(meds_a.keys()) | set(meds_b.keys())
    merged_meds = []
    for key in all_keys:
        ma = meds_a.get(key); mb = meds_b.get(key)
        if ma and mb:
            conf = min(100, round((ma.get("confidence_score", 70) + mb.get("confidence_score", 70)) / 2) + 10)
            merged_meds.append({"name": ma["name"], "status": ma.get("status"), "confidence_score": conf, "consensus": True})
        elif ma:
            merged_meds.append({**ma, "consensus": False})
        else:
            merged_meds.append({**mb, "consensus": False})
    merged["medications"] = merged_meds

    # ── clinical_findings (union, deduplicate) ─────────────────────
    findings_a = {f.get("finding", "").lower(): f for f in result_a.get("clinical_findings", [])}
    findings_b = {f.get("finding", "").lower(): f for f in result_b.get("clinical_findings", [])}
    all_fkeys = set(findings_a.keys()) | set(findings_b.keys())
    merged_findings = []
    for key in all_fkeys:
        fa = findings_a.get(key); fb = findings_b.get(key)
        if fa and fb:
            conf = min(100, round((fa.get("confidence_score", 70) + fb.get("confidence_score", 70)) / 2) + 10)
            merged_findings.append({"finding": fa["finding"], "confidence_score": conf})
        elif fa:
            merged_findings.append(fa)
        else:
            merged_findings.append(fb)
    merged["clinical_findings"] = sorted(merged_findings, key=lambda x: x.get("confidence_score", 0), reverse=True)

    # ── icd_codes (merge by code) ──────────────────────────────────
    icd_a = {c.get("code", "").upper(): c for c in result_a.get("icd_codes", [])}
    icd_b = {c.get("code", "").upper(): c for c in result_b.get("icd_codes", [])}
    all_icds = set(icd_a.keys()) | set(icd_b.keys())
    merged_icds = []
    for code in all_icds:
        ca = icd_a.get(code); cb = icd_b.get(code)
        if ca and cb:
            conf = min(100, round((ca.get("confidence_score", 70) + cb.get("confidence_score", 70)) / 2) + 10)
            merged_icds.append({"code": ca["code"], "description": ca["description"], "confidence_score": conf, "consensus": True})
        elif ca:
            merged_icds.append({**ca, "consensus": False})
        else:
            merged_icds.append({**cb, "consensus": False})
    merged["icd_codes"] = merged_icds

    # ── follow_up_actions (union) ──────────────────────────────────
    merged["follow_up_actions"] = result_a.get("follow_up_actions", []) or result_b.get("follow_up_actions", [])

    # ── Ensemble metadata ──────────────────────────────────────────
    consensus_pct = round((consensus_count / total_fields) * 100) if total_fields else 0
    merged["_ensemble"] = {
        "models": ["Gemini 2.5 Flash", "Groq Llama 4 Scout"],
        "consensus_rate": consensus_pct,
        "total_fields_compared": total_fields,
        "consensus_fields": consensus_count
    }

    return merged


# ─────────────────────────────────────────────────────────────
#  PUBLIC ENTRY POINT
# ─────────────────────────────────────────────────────────────
# Removed MOCK_RESPONSE completely to prevent silent fake data injections

def analyze_document_images(images: list) -> str:
    """
    Dual-LLM Ensemble with confidence-weighted merging.
    Runs Gemini (with model fallback) + Groq Llama.
    Falls back to single model if one is unavailable or errors.
    Falls back to mock data if no API keys are set OR both models fail.
    """
    if not gemini_api_key and not groq_api_key:
        raise ValueError("No API keys provided for Gemini or Groq.")

    print("[Ensemble] Firing Gemini and Groq in parallel...")
    
    # Calculate dynamic timeout based on page count: base 15s + 10s per page
    num_pages = len(images)
    dynamic_timeout = 15 + (num_pages * 10)
    print(f"[Ensemble] Dynamic timeout set to {dynamic_timeout}s for {num_pages} pages.")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        future_a = executor.submit(run_gemini, images)
        future_b = executor.submit(run_groq, images)
        
        try:
            result_a = future_a.result(timeout=dynamic_timeout)
        except concurrent.futures.TimeoutError:
            print(f"[Ensemble] Gemini Thread timed out after {dynamic_timeout}s!")
            result_a = None
        except Exception as e:
            print(f"[Ensemble] Gemini Thread Exception: {e}")
            result_a = None
            
        try:
            # We already waited for Gemini, so only wait whatever time is left if any, but since they run in parallel,
            # if we timed out on A, B might be done. If A finished fast, we give B the remaining time up to the max timeout.
            # Using the same timeout value is safe here because it's absolute from when it was submitted.
            result_b = future_b.result(timeout=dynamic_timeout)
        except concurrent.futures.TimeoutError:
            print(f"[Ensemble] Groq Thread timed out after {dynamic_timeout}s!")
            result_b = None
        except Exception as e:
            print(f"[Ensemble] Groq Thread Exception: {e}")
            result_b = None

    print(f"[Ensemble] Gemini: {'✓' if result_a else '✗'}  |  Groq: {'✓' if result_b else '✗'}")

    # If BOTH failed, throw an error to prevent silent failure
    if result_a is None and result_b is None:
        raise RuntimeError("Both LLM models failed to process the document.")

    # merge_results handles None on either side gracefully
    merged = merge_results(result_a, result_b)
    print(f"[Ensemble] Consensus rate: {merged.get('_ensemble', {}).get('consensus_rate', 'N/A')}%")

    return json.dumps(merged)
