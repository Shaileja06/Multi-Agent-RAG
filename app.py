# app.py
import os
import sqlite3
import json
from datetime import datetime, timedelta

from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI #, GoogleGenerativeAIEmbeddings (for bonus)

# --- Configuration ---
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY not found in .env file. Please set it.")

DB_FILENAME = "data/office_rag.db" # Make sure this path is correct

# Initialize Flask app
app = Flask(__name__)

# Initialize LLM (Gemini Pro)
# Make sure you are using a model that supports function calling or good structured output if needed.
# For text-to-SQL, "gemini-pro" is generally capable.
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", google_api_key=GOOGLE_API_KEY, temperature=0.1)
# For more complex tasks or if gemini-pro struggles, you might try "gemini-1.5-pro-latest" or "gemini-1.0-pro"

# --- Database Utility Functions ---
def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(DB_FILENAME)
    conn.row_factory = sqlite3.Row # Access columns by name
    # Enable foreign key enforcement for this connection
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def get_schema_description():
    """
    Retrieves the DDL (CREATE TABLE statements) for all tables in the database.
    This serves as the 'Relevant Schema' for the SQL Generator Agent.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    schema_rows = cursor.fetchall()
    conn.close()
    if not schema_rows:
        return "Error: No tables found in the database."
    
    schema_ddl = "\n\n".join([row['sql'] for row in schema_rows if row['sql']])
    
    # Add hints about date columns for the LLM
    date_hints = """
-- Important Notes for SQL Generation:
-- Dates in 'employees.hire_date' and 'customers.registration_date' are stored as TEXT in 'YYYY-MM-DD' format.
-- Dates in 'orders.order_date' are stored as TEXT in 'YYYY-MM-DD HH:MM:SS' format.
-- Use SQLite date functions like `date()`, `strftime()` for comparisons.
-- For example, to get orders from 2023: `strftime('%Y', order_date) = '2023'`
-- For "last year" (assuming current year is YYYY), use `strftime('%Y', order_date) = 'YYYY-1'`.
-- For "Q1 2023", query between '2023-01-01' and '2023-03-31'.
-- `price_at_purchase` in `order_items` is the historical price; `unit_price` in `products` is the current price.
-- `manager_id` in `employees` references `employees.employee_id`.
"""
    return schema_ddl + "\n" + date_hints


def execute_sql_query(sql_query):
    """
    Executes a SQL query against the database.
    This is the core function of the Retriever Agent.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(sql_query)
        rows = cursor.fetchall()
        # Convert rows to list of dicts for JSON serialization
        results = [dict(row) for row in rows]
        conn.commit() # Important for INSERT/UPDATE/DELETE, though we expect mostly SELECTs
        return results, None
    except sqlite3.Error as e:
        return None, f"SQLite Error: {e}"
    except Exception as e:
        return None, f"Execution Error: {e}"
    finally:
        conn.close()

# --- Agent Definitions ---

# 1. Schema Agent (Simplified: provides the full schema)
# In this implementation, the Schema Agent's role is fulfilled by get_schema_description()

# 2. SQL Generator Agent
sql_generator_prompt_template = """
You are an expert SQLite SQL query writer. Your task is to generate a valid SQLite SQL query
based on the provided database schema and a natural language question.

Database Schema:
{schema}

Guidelines:
1.  Only use tables and columns defined in the schema.
2.  If the question involves dates, use SQLite date functions like `strftime`, `date`, `datetime`.
    Pay close attention to the date formats mentioned in the schema notes.
3.  For temporal references like "last year", "next month", "Q1 2023", "yesterday":
    - Assume the current date is {current_date}.
    - "last year": `strftime('%Y', date_column) = '{last_year_yyyy}'`
    - "this year": `strftime('%Y', date_column) = '{current_year_yyyy}'`
    - "Q1 YYYY": `date_column BETWEEN 'YYYY-01-01' AND 'YYYY-03-31'` (adjust for other quarters)
    - "last 30 days": `date_column >= date('now', '-30 days')`
    - "yesterday": `date(date_column) = date('now', '-1 day')`
4.  If a JOIN is required, ensure the JOIN condition is correct based on the schema's foreign keys.
5.  For aggregations (SUM, AVG, COUNT), make sure to GROUP BY an appropriate column if needed.
6.  If the question is ambiguous or lacks information for a precise query, try to make a reasonable assumption or ask for clarification (though for this system, generate the best possible query).
7.  Return ONLY the SQL query. Do not add any explanations, introductory text, or markdown formatting like ```sql ... ```.

Examples:
Question: "How many customers do we have?"
SQL: SELECT COUNT(customer_id) FROM customers;

Question: "What are the names of employees in the Sales department hired last year?"
SQL: SELECT first_name, last_name FROM employees WHERE department = 'Sales' AND strftime('%Y', hire_date) = '{last_year_yyyy}';

Question: "Total sales amount for product 'SuperWidget' in Q2 2023?"
SQL: SELECT SUM(oi.quantity * oi.price_at_purchase) FROM order_items oi JOIN products p ON oi.product_id = p.product_id JOIN orders o ON oi.order_id = o.order_id WHERE p.product_name = 'SuperWidget' AND o.order_date BETWEEN '2023-04-01 00:00:00' AND '2023-06-30 23:59:59';

Question: "List all products in the 'Electronics' category."
SQL: SELECT product_name, unit_price FROM products WHERE category = 'Electronics';

Question: "Who are the top 3 highest paid employees?"
SQL: SELECT first_name, last_name, salary FROM employees ORDER BY salary DESC LIMIT 3;

Question: {question}
SQL:
"""

def generate_sql_query(question: str, schema: str) -> str:
    """Generates SQL query using an LLM."""
    current_time = datetime.now()
    prompt = PromptTemplate(
        template=sql_generator_prompt_template,
        input_variables=["schema", "question", "current_date", "current_year_yyyy", "last_year_yyyy"]
    )
    
    sql_chain = prompt | llm | StrOutputParser()
    
    # Clean the output in case the LLM still adds ```sql ... ```
    def clean_sql(raw_sql):
        if raw_sql.strip().startswith("```sql"):
            raw_sql = raw_sql.strip()[6:]
        if raw_sql.strip().endswith("```"):
            raw_sql = raw_sql.strip()[:-3]
        return raw_sql.strip()

    try:
        generated_sql = sql_chain.invoke({
            "schema": schema,
            "question": question,
            "current_date": current_time.strftime("%Y-%m-%d"),
            "current_year_yyyy": current_time.strftime("%Y"),
            "last_year_yyyy": str(current_time.year - 1)
        })
        return clean_sql(generated_sql), None
    except Exception as e:
        return None, f"SQL Generation Error: {e}"

# 3. Retriever Agent (fulfilled by execute_sql_query)

# 4. Synthesizer Agent
synthesizer_prompt_template = """
You are an AI assistant that synthesizes human-readable answers from SQL query results.
Based on the original question, the generated SQL query, and the query results, provide a concise and natural language answer.

Original Question: {question}
Generated SQL Query: {sql_query}
Query Results:
{results}

Important considerations:
- If the results are empty, state that no matching records were found or the query returned no data.
- If there's an error in the results (e.g., an error message instead of data), mention the error.
- If the results are a single number (e.g., from COUNT, SUM, AVG), state it clearly. Example: "There are X items." or "The total Y is Z."
- If the results are a list of items, summarize them or list a few if appropriate. Avoid just dumping a large table.
- Be polite and helpful.

Natural Language Answer:
"""

def synthesize_answer(question: str, sql_query: str, results, execution_error: str = None) -> str:
    """Generates a natural language answer from SQL results using an LLM."""
    prompt = PromptTemplate(
        template=synthesizer_prompt_template,
        input_variables=["question", "sql_query", "results"]
    )
    synthesis_chain = prompt | llm | StrOutputParser()

    if execution_error:
        results_str = f"An error occurred during SQL execution: {execution_error}"
    elif results is None or (isinstance(results, list) and not results): # Check for None or empty list
        results_str = "No matching records found."
    else:
        # Limit the number of rows displayed in the prompt to avoid exceeding token limits
        max_rows_for_prompt = 20
        if isinstance(results, list) and len(results) > max_rows_for_prompt:
            results_str = json.dumps(results[:max_rows_for_prompt], indent=2) + \
                          f"\n... (and {len(results) - max_rows_for_prompt} more rows)"
        else:
            results_str = json.dumps(results, indent=2)


    try:
        answer = synthesis_chain.invoke({
            "question": question,
            "sql_query": sql_query,
            "results": results_str
        })
        return answer, None
    except Exception as e:
        return None, f"Answer Synthesis Error: {e}"


# --- API Endpoint ---
@app.route('/')
def home():
    """Serves the simple HTML page for querying."""
    return render_template('index.html')

@app.route('/ask', methods=['POST'])
def ask_question():
    data = request.get_json()
    if not data or 'question' not in data:
        return jsonify({"error": "No question provided"}), 400
    
    question = data['question']
    
    intermediate_steps = {}
    final_response = {
        "natural_language_answer": None,
        "intermediate_steps": intermediate_steps,
        "error_message": None
    }

    try:
        # 1. Schema Agent: Get schema
        schema_desc = get_schema_description()
        intermediate_steps["relevant_schema"] = schema_desc
        if "Error:" in schema_desc:
            final_response["error_message"] = schema_desc
            return jsonify(final_response), 500

        # 2. SQL Generator Agent: Generate SQL
        generated_sql, sql_gen_error = generate_sql_query(question, schema_desc)
        intermediate_steps["generated_sql_query"] = generated_sql
        if sql_gen_error:
            final_response["error_message"] = sql_gen_error
            # Try to synthesize an answer about the failure
            nl_answer, _ = synthesize_answer(question, "Failed to generate SQL.", 
                                             f"SQL Generation Error: {sql_gen_error}")
            final_response["natural_language_answer"] = nl_answer or "Could not generate SQL due to an error."
            return jsonify(final_response), 500
        if not generated_sql: # Should be caught by sql_gen_error, but as a safeguard
            final_response["error_message"] = "SQL generation failed to produce a query."
            final_response["natural_language_answer"] = "I apologize, I couldn't construct a database query for your question."
            return jsonify(final_response), 500

        # 3. Retriever Agent: Execute SQL
        query_results, execution_error = execute_sql_query(generated_sql)
        intermediate_steps["result_rows"] = query_results if query_results is not None else [] # Ensure it's a list for JSON
        
        if execution_error:
            intermediate_steps["execution_error"] = execution_error
            # Fallback for synthesis if execution fails
            nl_answer, synth_error = synthesize_answer(question, generated_sql, None, execution_error)
            final_response["natural_language_answer"] = nl_answer or "There was an error executing the query."
            if synth_error:
                 final_response["natural_language_answer"] += f" (Synthesis also failed: {synth_error})"
            final_response["error_message"] = execution_error # Prioritize execution error message
            return jsonify(final_response), 500
        
        # Handle "no matching records" explicitly if not an error
        if query_results is None or (isinstance(query_results, list) and not query_results):
             intermediate_steps["execution_message"] = "No matching records found."


        # 4. Synthesizer Agent: Generate Natural Language Answer
        natural_answer, synth_error = synthesize_answer(question, generated_sql, query_results)
        final_response["natural_language_answer"] = natural_answer
        if synth_error:
            # If synthesis fails, provide raw results if available, or a fallback message
            final_response["natural_language_answer"] = (
                f"Successfully retrieved data, but could not synthesize a natural answer (Error: {synth_error}). "
                f"Query: {generated_sql}. Results: {json.dumps(query_results, indent=2) if query_results else 'No data.'}"
            )
            intermediate_steps["synthesis_error"] = synth_error
            # Still return 200 as we got data, but indicate synthesis issue
            return jsonify(final_response), 200 


        return jsonify(final_response), 200

    except Exception as e:
        app.logger.error(f"An unexpected error occurred: {e}", exc_info=True)
        final_response["error_message"] = f"An unexpected system error occurred: {str(e)}"
        final_response["natural_language_answer"] = "I encountered an unexpected issue while processing your request."
        return jsonify(final_response), 500

if __name__ == '__main__':
    # Ensure the data directory and db file exist.
    # The sqlite_mock_data.py script should be run first to create office_rag.db
    if not os.path.exists(DB_FILENAME):
        print(f"ERROR: Database file '{DB_FILENAME}' not found.")
        print("Please run the `sqlite_mock_data.py` script first to generate the database.")
    else:
        app.run(debug=True, port=5001) # Using port 5001 to avoid common conflicts