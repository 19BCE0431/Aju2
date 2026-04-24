import streamlit as st
import requests
import pandas as pd

API_URL = "https://your-railway-url"

st.title("📊 Financial PDF Smart Search")

file = st.file_uploader("Upload PDF")

if file:
    try:
        res = requests.post(
            f"{API_URL}/upload",
            files={"file": (file.name, file.getvalue(), "application/pdf")},
            timeout=60
        )

        if res.status_code == 200:
            st.success("✅ PDF processed")
        else:
            st.error(res.text)

    except Exception as e:
        st.error(f"Backend error: {e}")

query = st.text_input("🔍 Search")

if query:
    res = requests.get(f"{API_URL}/search", params={"q": query})

    if res.status_code == 200:
        data = res.json()["results"]

        if not data:
            st.warning("No results found")
        else:
            df = pd.DataFrame(data)

            for col in ["debit", "credit", "balance"]:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

            st.dataframe(df, use_container_width=True)

            st.markdown(f"### 💰 Total Credit: ₹ {res.json()['total_credit']}")
    else:
        st.error(res.text)
