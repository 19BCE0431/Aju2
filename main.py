from fastapi import FastAPI, UploadFile, File
import fitz  # PyMuPDF
import re
from rapidfuzz import fuzz

app = FastAPI()

documents = []

# ---------------------------
# CLEAN TEXT
# ---------------------------
def clean_text(x):
    x = x.lower()
    x = re.sub(r"[^\w\s]", " ", x)
    return " ".join(x.split())


# ---------------------------
# PARSE PDF (STABLE VERSION)
# ---------------------------
def parse_pdf(content):
    doc = fitz.open(stream=content, filetype="pdf")

    lines = []

    for page in doc:
        text = page.get_text()
        lines.extend([l.strip() for l in text.split("\n") if l.strip()])

    transactions = []
    current = ""

    for line in lines:
        # new transaction starts with date
        if re.match(r"\d{2}/\d{2}/\d{2}", line):
            if current:
                transactions.append(current)
            current = line
        else:
            current += " " + line

    if current:
        transactions.append(current)

    final = []

    for t in transactions:
        text = t

        # date
        date_match = re.search(r"\d{2}/\d{2}/\d{2}", text)
        if not date_match:
            continue

        date = date_match.group()

        # amounts
        nums = re.findall(r"\d{1,3}(?:,\d{3})*\.\d{2}", text)
        nums = [float(n.replace(",", "")) for n in nums]

        if len(nums) < 2:
            continue

        balance = nums[-1]
        amount = nums[-2]

        # description = KEEP FULL TEXT (key fix)
        desc = clean_text(text)

        # simple debit/credit
        debit, credit = 0, 0
        if any(k in desc for k in ["deposit", "credit", "cr"]):
            credit = amount
        elif any(k in desc for k in ["atm", "withdraw", "purchase"]):
            debit = amount
        elif any(k in desc for k in ["imps", "neft"]):
            credit = amount
        else:
            debit = amount

        final.append({
            "date": date,
            "description": desc,
            "debit": debit,
            "credit": credit,
            "balance": balance
        })

    return final


# ---------------------------
# UPLOAD API
# ---------------------------
@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    global documents

    content = await file.read()
    documents = parse_pdf(content)

    return {"message": f"{len(documents)} transactions loaded"}


# ---------------------------
# SEARCH API
# ---------------------------
@app.get("/search")
def search(q: str):
    q = clean_text(q)

    results = []

    for doc in documents:
        text = doc["description"]

        score = max(
            fuzz.token_set_ratio(q, text),
            fuzz.partial_ratio(q, text)
        )

        if score > 50:
            item = doc.copy()
            item["score"] = score
            results.append(item)

    results.sort(key=lambda x: x["score"], reverse=True)

    return {
        "results": results[:20],
        "total_credit": sum(r["credit"] for r in results)
    }


# ---------------------------
# HEALTH CHECK (IMPORTANT)
# ---------------------------
@app.get("/")
def root():
    return {"status": "ok"}
