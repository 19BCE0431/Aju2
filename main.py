from fastapi import FastAPI, UploadFile, File
import fitz  # PyMuPDF
import re
from rapidfuzz import fuzz

app = FastAPI()

documents = []

# ---------------------------
# KEYWORD EXTRACTION
# ---------------------------
def extract_keywords(text):
    words = re.findall(r"[a-zA-Z]+", text.lower())

    stopwords = {
        "upi","imps","neft","hdfc","bank","ltd","india",
        "personal","etbank","mum","mumbai","txn","transfer",
        "dr","cr","chq","pos","ref","no"
    }

    keywords = [w for w in words if w not in stopwords and len(w) > 2]
    return " ".join(keywords)


# ---------------------------
# PARSE TRANSACTION BLOCK
# ---------------------------
def parse_row(text):
    original_text = text
    text = " ".join(text.split())

    # Date
    date_match = re.search(r"\d{2}/\d{2}/\d{2}", text)
    if not date_match:
        return None

    date = date_match.group()

    # Numbers
    numbers = re.findall(r"\d{1,3}(?:,\d{3})*\.\d{2}", text)
    numbers = [float(n.replace(",", "")) for n in numbers]

    if len(numbers) < 2:
        return None

    balance = numbers[-1]
    amount = numbers[-2]

    debit, credit = 0, 0
    lower = text.lower()

    if any(k in lower for k in ["deposit", "credit", "received"]):
        credit = amount
    elif any(k in lower for k in ["atm", "debit", "purchase", "payment", "emi"]):
        debit = amount
    elif "imps" in lower or "neft" in lower:
        credit = amount  # usually incoming
    else:
        debit = amount  # fallback

    # Clean name
    name = re.sub(r"\d{2}/\d{2}/\d{2}", "", text)
    name = re.sub(r"\d{1,3}(?:,\d{3})*\.\d{2}", "", name)
    name = re.sub(r"\d+", "", name)
    name = re.sub(r"[^\w\s]", " ", name)
    name = " ".join(name.split()).lower()

    if len(name) < 3:
        return None

    return {
        "date": date,
        "name": name,
        "debit": debit,
        "credit": credit,
        "balance": balance,
        "raw_text": original_text.lower(),
        "text": name,
        "keywords": extract_keywords(original_text)
    }


# ---------------------------
# UPLOAD API
# ---------------------------
@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    global documents
    documents = []

    content = await file.read()
    doc = fitz.open(stream=content, filetype="pdf")

    lines = []
    for page in doc:
        text = page.get_text()
        lines.extend([l.strip() for l in text.split("\n") if l.strip()])

    blocks = []
    current_block = []

    for line in lines:
        if re.match(r"\d{2}/\d{2}/\d{2}", line):
            if current_block:
                blocks.append(" ".join(current_block))
            current_block = [line]
        else:
            current_block.append(line)

    if current_block:
        blocks.append(" ".join(current_block))

    for block in blocks:
        parsed = parse_row(block)
        if parsed:
            documents.append(parsed)

    print("TOTAL PARSED:", len(documents))
    print("SAMPLE:", documents[:3])

    return {"message": f"{len(documents)} rows processed"}


# ---------------------------
# SEARCH API (SMART)
# ---------------------------
@app.get("/search")
def search(q: str):
    q = re.sub(r"[^a-zA-Z ]", "", q.lower())
    q = " ".join(q.split())

    results = []

    for doc in documents:
        raw = doc.get("raw_text", "")
        clean = doc.get("text", "")
        keywords = doc.get("keywords", "")

        score = 0

        # 1. Exact match boost
        if q in raw:
            score += 100

        # 2. Keyword match (strong)
        score += fuzz.token_set_ratio(q, keywords) * 0.8

        # 3. Clean text
        score += fuzz.token_set_ratio(q, clean) * 0.5

        # 4. Partial fallback
        score += fuzz.partial_ratio(q, raw) * 0.3

        # 5. Token boost
        if any(word in keywords for word in q.split()):
            score += 30

        if score > 40:
            item = doc.copy()
            item["score"] = round(score, 2)
            results.append(item)

    results.sort(key=lambda x: x["score"], reverse=True)

    return {
        "results": results[:20],
        "total_credit": sum(r["credit"] for r in results)
    }
