

from fastapi import FastAPI, UploadFile, File
import fitz  # PyMuPDF
import re
from rapidfuzz import fuzz

app = FastAPI()

documents = []


def parse_row(text):
    text = " ".join(text.split())

    # Skip headers
    if "date" in text.lower() and "balance" in text.lower():
        return None

    # Extract date
    date_match = re.search(r"\d{2}/\d{2}/\d{2}", text)
    if not date_match:
        return None

    date = date_match.group()

    # Extract ONLY monetary values
    numbers = re.findall(r"\d{1,3}(?:,\d{3})*\.\d{2}", text)
    numbers = [float(n.replace(",", "")) for n in numbers]

    debit, credit, balance = 0, 0, 0

    if len(numbers) >= 2:
        balance = numbers[-1]
        txn = numbers[-2]

        # 🔥 SMART RULE:
        # If name suggests outgoing → debit
        # else → credit
        lower = text.lower()

        if any(k in lower for k in ["upi", "pay", "amazon", "swiggy", "debit"]):
            debit = txn
        else:
            credit = txn

    # Clean name
    name = text

    name = re.sub(r"\d{2}/\d{2}/\d{2}", "", name)
    name = re.sub(r"\d{1,3}(?:,\d{3})*\.\d{2}", "", name)
    name = re.sub(r"[^\w\s]", "", name)
    name = " ".join(name.split())

    if len(name) < 3:
        return None

    return {
        "date": date,
        "name": name,
        "debit": debit,
        "credit": credit,
        "balance": balance,
        "text": text.lower()
    }


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    global documents
    documents = []

    content = await file.read()
    doc = fitz.open(stream=content, filetype="pdf")

    lines = []

    for page in doc:
        lines.extend(page.get_text().split("\n"))

    current_block = ""

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if re.match(r"\d{2}/\d{2}/\d{2}", line):
            if current_block:
                parsed = parse_row(current_block)
                if parsed:
                    documents.append(parsed)
            current_block = line
        else:
            current_block += " " + line

    if current_block:
        parsed = parse_row(current_block)
        if parsed:
            documents.append(parsed)

    return {"message": f"{len(documents)} rows processed"}


@app.get("/search")
def search(q: str):
    q = q.lower().strip()

    results = []

    for doc in documents:
        name = doc.get("name", "").lower()
        score = fuzz.partial_ratio(q, name)

        if score > 70:
            doc["score"] = score
            results.append(doc)

    results.sort(key=lambda x: x["score"], reverse=True)

    return {
        "results": results,
        "total_credit": sum(r["credit"] for r in results)
    }
