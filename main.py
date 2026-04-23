from fastapi import FastAPI, UploadFile, File
import fitz  # PyMuPDF
import re
from rapidfuzz import fuzz

app = FastAPI()

# dd

documents = []

# ---------------------------
# PARSE FUNCTION (CLEAN)
# ---------------------------
def parse_row(text):
    original_text = text

    text = " ".join(text.split())

    # Extract date
    date_match = re.search(r"\d{2}/\d{2}/\d{2}", text)
    if not date_match:
        return None

    date = date_match.group()

    # Extract numbers
    numbers = re.findall(r"\d{1,3}(?:,\d{3})*\.\d{2}", text)
    numbers = [float(n.replace(",", "")) for n in numbers]

    if len(numbers) < 2:
        return None

    # Last number = balance
    balance = numbers[-1]

    # Second last = txn amount
    amount = numbers[-2]

    debit, credit = 0, 0

    lower = text.lower()

    if any(k in lower for k in ["imps", "deposit", "credit", "received", "refund"]):
        credit = amount
    elif any(k in lower for k in ["upi", "debit", "purchase", "payment", "withdrawal", "emi"]):
        debit = amount
    else:
        # fallback → detect by balance movement later (optional)
        debit = amount

    # 🔥 CLEAN NAME (IMPORTANT)
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
        "text": name   # 🔥 use clean text only
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
        # New transaction starts when line starts with date
        if re.match(r"\d{2}/\d{2}/\d{2}", line):
            if current_block:
                blocks.append(" ".join(current_block))
            current_block = [line]
        else:
            current_block.append(line)

    if current_block:
        blocks.append(" ".join(current_block))

    # 🔥 Parse blocks
    for block in blocks:
        parsed = parse_row(block)
        if parsed:
            documents.append(parsed)

    print("TOTAL PARSED:", len(documents))
    print("SAMPLE:", documents[:3])

    return {"message": f"{len(documents)} rows processed"}



# ---------------------------
# SEARCH API (FUZZY)
# ---------------------------
@app.get("/search")
def search(q: str, debug: bool = False):
    q = re.sub(r"[^a-zA-Z ]", "", q.lower())
    q = " ".join(q.split())

    results = []

    for doc in documents:
        text = doc.get("text", "")

        score = max(
            fuzz.token_set_ratio(q, text),
            fuzz.token_sort_ratio(q, text)
        )

        if score > 40:
            item = doc.copy()
            item["score"] = score
            results.append(item)

    results.sort(key=lambda x: x["score"], reverse=True)

    return {
        "results": results,
        "total_credit": sum(r["credit"] for r in results)
    }
    
