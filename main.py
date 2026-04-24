from fastapi import FastAPI, UploadFile, File
import pandas as pd
import re
import camelot
from rapidfuzz import fuzz
import tempfile
import os

app = FastAPI()
documents = []

# ---------------------------
# CLEAN HELPERS
# ---------------------------

def clean_amount(x):
    try:
        return float(str(x).replace(",", "").strip())
    except:
        return 0.0

def clean_text(x):
    x = str(x).lower()
    x = re.sub(r"[^\w\s]", " ", x)
    return " ".join(x.split())


# ---------------------------
# TABLE EXTRACTION (MAIN LOGIC)
# ---------------------------

def extract_tables(pdf_path):
    tables = camelot.read_pdf(pdf_path, pages="all", flavor="stream")

    all_rows = []

    for table in tables:
        df = table.df

        # Normalize columns (remove empty rows)
        df = df.replace("", pd.NA).dropna(how="all")

        # Try to identify columns dynamically
        for _, row in df.iterrows():
            row = [str(x).strip() for x in row.tolist()]

            text = " ".join(row)

            # detect date
            date_match = re.search(r"\d{2}/\d{2}/\d{2}", text)
            if not date_match:
                continue

            date = date_match.group()

            # extract amounts
            nums = re.findall(r"\d{1,3}(?:,\d{3})*\.\d{2}", text)
            nums = [clean_amount(n) for n in nums]

            if len(nums) < 2:
                continue

            balance = nums[-1]
            amount = nums[-2]

            desc = clean_text(text)

            # debit/credit logic
            debit, credit = 0, 0

            if "cr" in desc or "deposit" in desc:
                credit = amount
            elif "atm" in desc or "withdraw" in desc:
                debit = amount
            elif "imps" in desc or "neft" in desc:
                credit = amount
            else:
                debit = amount

            all_rows.append({
                "date": date,
                "name": desc,
                "debit": debit,
                "credit": credit,
                "balance": balance,
                "raw_text": desc
            })

    return all_rows


# ---------------------------
# UPLOAD API
# ---------------------------

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    global documents
    documents = []

    # save temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        documents = extract_tables(tmp_path)
    finally:
        os.remove(tmp_path)

    print("PARSED:", len(documents))
    print("SAMPLE:", documents[:2])

    return {"message": f"{len(documents)} rows processed"}


# ---------------------------
# SEARCH API
# ---------------------------

@app.get("/search")
def search(q: str):
    q = clean_text(q)

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
