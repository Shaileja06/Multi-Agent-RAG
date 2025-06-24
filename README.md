
# 🧠 Multi-Agent RAG System for Natural Language SQL Querying

This project implements a **Multi-Agent Retrieval-Augmented Generation (RAG)** system that interprets **natural language queries**, transforms them into **structured SQL queries**, executes them against a **relational database**, and returns **human-readable answers**.

Built using **Flask**, **SQLite**, and **Gemini Pro** via the `langchain-google-genai` integration.

---

## 🚀 Features

- 📊 Query any structured relational database using natural language
- 🤖 Modular agent design:
  - **Schema Agent** – fetches database schema
  - **SQL Generator Agent** – uses LLM to generate SQL from questions
  - **Retriever Agent** – executes SQL and fetches results
  - **Synthesizer Agent** – converts result to natural language
- 📦 JSON API with detailed intermediate steps
- 🌐 Simple web interface (via `index.html`)

---

## 🏗️ System Architecture

```
graph TD
A[User Question] --> B[Schema Agent<br/>Reads schema DDL]
B --> C[SQL Generator Agent<br/>LLM-based prompt generation]
C --> D[Retriever Agent<br/>Executes SQL on SQLite DB]
D --> E[Synthesizer Agent<br/>Generates final answer]
E --> F[Response (JSON/API + UI)]
```

---

## 🛠️ Setup Instructions

### 1. Clone the Repo

```bash
git clone https://github.com/your-username/your-repo.git
cd your-repo
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

> Ensure your `.env` contains:
```env
GOOGLE_API_KEY=your_google_gemini_api_key
```

## ▶️ Running the Application

```bash
python app.py
```

Visit: [http://localhost:5001](http://localhost:5001)

---

## 🧪 API Usage

### POST `/ask`

**Request Body:**
```json
{
  "question": "How many employees were hired last year?"
}
```

**Response:**
```json
{
  "natural_language_answer": "There are 25 employees hired last year.",
  "intermediate_steps": {
    "relevant_schema": "...",
    "generated_sql_query": "...",
    "result_rows": [...]
  },
  "error_message": null
}
```

---

## 📂 Project Structure

```
├── app.py                   # Main Flask application
├── .env                     # Contains Google API Key
├── requirements.txt         # Python dependencies
├── README.md                # Project documentation
├── templates/
│   └── index.html           # Web UI
└── data/
    ├── office_rag.db        # SQLite database
    └── sqlite.py            # Script to generate mock data for DB
```

---

## 📘 Agents Overview

| Agent             | Description |
|------------------|-------------|
| **Schema Agent** | Extracts schema using `sqlite_master`. |
| **SQL Generator**| Uses Gemini Pro (`langchain_google_genai`) to turn natural queries into SQL. |
| **Retriever Agent** | Executes generated SQL using `sqlite3`. |
| **Synthesizer Agent** | Uses Gemini to turn results into human-readable answers. |

---

## 🧠 Supported Query Types

- Direct lookups (e.g., "List all products")
- Conditional filters (e.g., "Employees in HR")
- Aggregates (e.g., "Average salary")
- Joins (e.g., Orders with customer names)
- Date filters (e.g., "Orders last month", "Q1 2023")

---

## ⚠️ Error Handling

Gracefully manages:
- SQL errors or malformed queries
- No matching data
- Schema access issues
- Model or execution failures

---

## 💡 Optional Enhancements

- ✅ Vector database fallback (e.g., FAISS or Chroma)
- ✅ Document-based RAG (PDF or internal notes ingestion)
- 🌍 Web hosting (e.g., Render, Vercel, or HuggingFace Spaces)

---

## 🧪 Example Questions

- "Show total sales in Q2 2023"
- "Who are the top 3 highest paid employees?"
- "List products in the 'Electronics' category"

---

## 📜 License

MIT – feel free to fork and build on top!
