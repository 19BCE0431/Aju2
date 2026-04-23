import streamlit as st
import requests
import pandas as pd

API_URL = "https://aju2-production.up.railway.app"

st.title("📊 Financial PDF Smart Search")

# ✅ ADD DEBUG TOGGLE HERE
DEBUG = st.checkbox("Show debug data (numbers)")

# ---------------------------
# UPLOAD
# ---------------------------
file = st.file_uploader("Upload your PDF")

if file:
    files = {
        "file": (file.name, file.getvalue(), "application/pdf")
    }

    res = requests.post(f"{API_URL}/upload", files=files)

    if res.status_code == 200:
        st.success("✅ PDF uploaded & processed")
    else:
        st.error(f"❌ Upload failed: {res.text}")

# ---------------------------
# SEARCH
# ---------------------------
query = st.text_input("🔍 Search (example: chethana)")

if query:
    res = requests.get(
        f"{API_URL}/search",
        params={"q": query, "debug": DEBUG}   # ✅ PASS DEBUG HERE
    )

    if res.status_code == 200:
        response = res.json()
        data = response.get("results", [])

        if not data:
            st.warning("No results found")
        else:
            df = pd.DataFrame(data)

            # ✅ CLEAN numeric columns
            for col in ["debit", "credit", "balance"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

            # ✅ HIDE debug column if not enabled
            if not DEBUG and "numbers" in df.columns:
                df = df.drop(columns=["numbers"])

            st.subheader("Results")
            st.dataframe(df)

            st.markdown(f"### 💰 Total Credit: ₹ {response.get('total_credit', 0)}")

    else:
        st.error(f"Search failed: {res.text}")
