from fastapi import FastAPI, UploadFile, File
import fitz  # PyMuPDF
import re
from rapidfuzz import fuzz

app = FastAPI()
documents = []

# ---------------------------
# HELPERS
# ---------------------------

def is_date(text):
    return re.match(r"\d{2}/\d{2}/\d{2}", text)

def is_amount(text):
    return re.match(r"\d{1,3}(?:,\d{3})*\.\d{2}", text)

def clean_amount(x):
    return float(x.replace(",", ""))

# ---------------------------
# CORE PARSER (LAYOUT BASED)
# ---------------------------

def extract_transactions(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    rows = []

    for page in doc:
        words = page.get_text("words")  
        # words = [x0, y0, x1, y1, "text", block_no, line_no, word_no]

        # Sort by vertical position
        words.sort(key=lambda w: (round(w[1], 1), w[0]))

        # Group into lines (same Y ≈ same row)
        lines = {}
        for w in words:
            y = round(w[1], 1)
            lines.setdefault(y, []).append(w)

        # Convert to sorted rows
        sorted_lines = [lines[k] for k in sorted(lines.keys())]

        current = None

        for line in sorted_lines:
            texts = [w[4] for w in sorted(line, key=lambda x: x[0])]
            line_text = " ".join(texts)

            # New transaction starts
            if any(is_date(t) for t in texts):
                if current:
                    rows.append(current)

                current = {
                    "date": next(t for t in texts if is_date(t)),
                    "desc_parts": [],
                    "amounts": []
                }

            if not current:
                continue

            # Collect amounts
            amounts = [clean_amount(t) for t in texts if is_amount(t)]
            current["amounts"].extend(amounts)

            # Collect description (exclude numbers + dates)
            desc = [
                t for t in texts
                if not is_date(t) and not is_amount(t)
            ]
            if desc:
                current["desc_parts"].extend(desc)

        if current:
            rows.append(current)

    # ---------------------------
    # FINAL STRUCTURED ROWS
    # ---------------------------
    final = []

    for r in rows:
        nums = r["amounts"]

        if len(nums) < 2:
            continue

        balance = nums[-1]
        amount = nums[-2]

        # Debit/Credit detection using balance change is ideal,
        # but fallback heuristic:
        debit, credit = 0, 0
        if "cr" in " ".join(r["desc_parts"]).lower():
            credit = amount
        else:
            debit = amount

        name = " ".join(r["desc_parts"]).lower()
        name = re.sub(r"[^\w\s]", " ", name)
        name = " ".join(name.split())

        final.append({
            "date": r["date"],
            "name": name,
            "debit": debit,
            "credit": credit,
            "balance": balance,
            "raw_text": name
        })

    return final


# ---------------------------
# UPLOAD
# ---------------------------

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    global documents

    content = await file.read()
    documents = extract_transactions(content)

    print("PARSED:", len(documents))
    print("SAMPLE:", documents[:2])

    return {"message": f"{len(documents)} rows processed"}


# ---------------------------
# SEARCH (CLEAN + RELIABLE)
# ---------------------------

@app.get("/search")
def search(q: str):
    q = re.sub(r"[^a-zA-Z ]", "", q.lower())
    q = " ".join(q.split())

    results = []

    for doc in documents:
        text = doc["raw_text"]

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
