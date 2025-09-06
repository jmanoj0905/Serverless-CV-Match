import json, math, time
import boto3
from urllib.parse import unquote_plus

# ---- HARD-CODED CONFIG ----
BUCKET = "resume-match-jmanoj0905-ap-south-1"
JOBS_KEY = "jobs/jobs.json"
EMBED_MODEL = "amazon.titan-embed-text-v1"
LLM_MODEL = "anthropic.claude-3-sonnet-20240229-v1:0"
RESUMES_PREFIX = "resumes/"
RESULTS_PREFIX = "results/"

s3 = boto3.client("s3")
textract = boto3.client("textract")
bedrock = boto3.client("bedrock-runtime")

def cos_sim(a, b):
    num = sum(x * y for x, y in zip(a, b))
    da = math.sqrt(sum(x * x for x in a))
    db = math.sqrt(sum(y * y for y in b))
    return num / (da * db + 1e-9)

def embed(text: str):
    body = json.dumps({"inputText": text[:8000]})
    resp = bedrock.invoke_model(
        modelId=EMBED_MODEL,
        body=body,
        accept="application/json",
        contentType="application/json",
    )
    out = json.loads(resp["body"].read())
    return out["embedding"]

def call_llm(resume_text, job):
    prompt = f"""
You are a hiring assistant. Given RESUME and JOB:

RESUME:
{resume_text[:4000]}

JOB:
Title: {job['title']}
Company: {job['company']}
Location: {job.get('location','')}
Type: {job.get('type','')}
Description: {job['description'][:2000]}
Skills: {', '.join(job.get('skills',[]))}

1) Give a concise match analysis (3–4 sentences).
2) List 5 strongest aligned skills/experiences (short bullets).
3) List 3–5 gaps (short bullets).
4) Provide a Fit Score (0–100) with one line reasoning.

Return strict JSON with keys: reasons (string), strengths (array), gaps (array), fit_score (int).
"""
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 450,
        "temperature": 0,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
    })
    r = bedrock.invoke_model(
        modelId=LLM_MODEL,
        body=body,
        accept="application/json",
        contentType="application/json",
    )
    msg = json.loads(r["body"].read())
    text = "".join(part.get("text", "") for part in msg.get("content", []))
    try:
        parsed = json.loads(text)
        # normalize types
        parsed["strengths"] = parsed.get("strengths", []) or []
        parsed["gaps"] = parsed.get("gaps", []) or []
        parsed["reasons"] = parsed.get("reasons", "") or ""
        parsed["fit_score"] = int(parsed.get("fit_score", 50) or 50)
        return parsed
    except Exception:
        return {"reasons": text[:800], "strengths": [], "gaps": [], "fit_score": 50}

def extract_text(bucket, key):
    """Try Textract for PDFs; fallback to plain text if possible."""
    s3obj = s3.get_object(Bucket=bucket, Key=key)
    b = s3obj["Body"].read()
    if not b.startswith(b"%PDF"):
        try:
            return b.decode("utf-8", errors="ignore")
        except Exception:
            return ""

    r = textract.start_document_text_detection(
        DocumentLocation={"S3Object": {"Bucket": bucket, "Name": key}}
    )
    job_id = r["JobId"]

    while True:
        time.sleep(2.5)
        jr = textract.get_document_text_detection(JobId=job_id, MaxResults=1000)
        status = jr.get("JobStatus")
        if status in ("SUCCEEDED", "FAILED"):
            if status == "FAILED":
                return ""
            blocks = jr.get("Blocks", [])
            return "\n".join(b.get("Text", "") for b in blocks if b.get("BlockType") == "LINE")

def handler(event, context):
    for rec in event.get("Records", []):
        key = unquote_plus(rec["s3"]["object"]["key"])
        if not key.startswith(RESUMES_PREFIX):
            continue

        # 1) Extract text from the uploaded resume
        resume_text = extract_text(BUCKET, key) or ""
        # 2) Embed the resume
        v_resume = embed(resume_text)

        # 3) Load jobs dataset
        jobs_obj = s3.get_object(Bucket=BUCKET, Key=JOBS_KEY)
        jobs = json.loads(jobs_obj["Body"].read())

        # 4) Embed each job and compute similarity
        scored = []
        for job in jobs:
            text = f"{job['title']} at {job['company']}. {job['description']}"
            v_job = embed(text)
            sim = cos_sim(v_resume, v_job)
            scored.append((sim, job))

        # 5) Take top-k and generate explanations
        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:5]

        final = []
        for sim, job in top:
            expl = call_llm(resume_text, job)
            final.append({
                "job_id": job["job_id"],
                "title": job["title"],
                "company": job["company"],
                "location": job.get("location", ""),
                "score": float(sim),
                "fit_score": int(expl.get("fit_score", 50)),
                "reasons": expl.get("reasons", ""),
                "strengths": expl.get("strengths", []),
                "gaps": expl.get("gaps", []),
            })

        # 6) Write result JSON back to S3 under results/<same-name>.json
        out = {"matches": final}
        original_name = key.split("/", 1)[1]  # remove 'resumes/'
        result_key = f"{RESULTS_PREFIX}{original_name}.json"
        s3.put_object(
            Bucket=BUCKET,
            Key=result_key,
            Body=json.dumps(out).encode("utf-8"),
            ContentType="application/json",
        )

    return {"ok": True}
