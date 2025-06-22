# sqlite_mock_data.py
import sqlite3
from faker import Faker
import random
from datetime import datetime, timedelta # Still useful for Faker
import os
from dotenv import load_dotenv

load_dotenv() # For OPENAI_API_KEY if used later, not for DB credentials here

DB_FILENAME = "office_rag.db"

fake = Faker()

# --- Configuration (remains largely the same) ---
NUM_EMPLOYEES = 50
NUM_CUSTOMERS = 200
NUM_PRODUCTS = 100
NUM_ORDERS = 500

DEPARTMENTS = ["Sales", "Marketing", "Engineering", "HR", "Support", "Finance"]
JOB_TITLES_PER_DEPT = {
    "Sales": ["Sales Manager", "Sales Representative", "Account Executive"],
    "Marketing": ["Marketing Manager", "Marketing Specialist", "Content Creator"],
    "Engineering": ["Software Engineer", "Senior Engineer", "Tech Lead", "Engineering Manager"],
    "HR": ["HR Manager", "HR Specialist", "Recruiter"],
    "Support": ["Support Agent", "Support Lead", "Customer Success Manager"],
    "Finance": ["Accountant", "Financial Analyst", "Controller"]
}
PRODUCT_CATEGORIES = ["Electronics", "Books", "Clothing", "Home & Kitchen", "Sports & Outdoors", "Toys & Games"]
ORDER_STATUSES = ['Pending', 'Processing', 'Shipped', 'Delivered', 'Cancelled']

def create_tables(conn):
    cur = conn.cursor()
    # Enable Foreign Keys for this connection
    cur.execute("PRAGMA foreign_keys = ON;")

    # Drop tables in reverse order of creation due to foreign keys
    cur.execute("DROP TABLE IF EXISTS order_items;")
    cur.execute("DROP TABLE IF EXISTS orders;")
    cur.execute("DROP TABLE IF EXISTS products;")
    cur.execute("DROP TABLE IF EXISTS customers;")
    cur.execute("DROP TABLE IF EXISTS employees;")

    cur.execute("""
    CREATE TABLE employees (
        employee_id INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        phone_number TEXT,
        hire_date TEXT NOT NULL, -- Store as ISO8601 string: YYYY-MM-DD
        job_title TEXT,
        department TEXT,
        salary REAL,
        manager_id INTEGER REFERENCES employees(employee_id) ON DELETE SET NULL
    );
    """)

    cur.execute("""
    CREATE TABLE customers (
        customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
        first_name TEXT NOT NULL,
        last_name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        phone_number TEXT,
        address TEXT,
        city TEXT,
        state TEXT,
        zip_code TEXT,
        registration_date TEXT NOT NULL -- Store as ISO8601 string: YYYY-MM-DD
    );
    """)

    cur.execute("""
    CREATE TABLE products (
        product_id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_name TEXT NOT NULL,
        category TEXT,
        unit_price REAL NOT NULL,
        stock_quantity INTEGER DEFAULT 0
    );
    """)

    cur.execute("""
    CREATE TABLE orders (
        order_id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
        employee_id INTEGER REFERENCES employees(employee_id) ON DELETE SET NULL, 
        order_date TEXT NOT NULL, -- Store as ISO8601 string: YYYY-MM-DD HH:MM:SS
        status TEXT NOT NULL
    );
    """)

    cur.execute("""
    CREATE TABLE order_items (
        order_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
        product_id INTEGER NOT NULL REFERENCES products(product_id) ON DELETE RESTRICT,
        quantity INTEGER NOT NULL,
        price_at_purchase REAL NOT NULL
    );
    """)
    print("Tables created successfully for SQLite.")
    conn.commit()
    cur.close()

def insert_employees(conn, num_employees):
    cur = conn.cursor()
    employee_ids = []
    
    employee_data_to_insert = []
    for _ in range(num_employees):
        dept = random.choice(DEPARTMENTS)
        job_title = random.choice(JOB_TITLES_PER_DEPT[dept])
        salary_base = 50000
        if "Manager" in job_title: salary_base += 30000
        if "Senior" in job_title or "Lead" in job_title: salary_base += 20000
        if dept == "Engineering": salary_base += 10000
        if dept == "Sales": salary_base += 5000

        employee_data_to_insert.append((
            fake.first_name(), fake.last_name(), fake.unique.email(), fake.phone_number(),
            fake.date_between(start_date='-5y', end_date='today').isoformat(),
            job_title, dept, round(random.uniform(salary_base*0.8, salary_base*1.2), 2)
        ))

    for data in employee_data_to_insert:
        cur.execute(
            """
            INSERT INTO employees (first_name, last_name, email, phone_number, hire_date, job_title, department, salary)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            data
        )
        employee_ids.append(cur.lastrowid)

    for emp_id_idx, emp_id in enumerate(employee_ids): # Use enumerate to avoid issues with modifying list while iterating (though not strictly necessary here)
        # Avoid self-management and simplify manager assignment
        potential_managers = [m_id for i, m_id in enumerate(employee_ids) if i != emp_id_idx]
        if not potential_managers: continue

        cur.execute("SELECT department FROM employees WHERE employee_id = ?", (emp_id,))
        emp_dept_row = cur.fetchone()
        if not emp_dept_row: continue 
        emp_dept = emp_dept_row[0]
        
        cur.execute("""
            SELECT employee_id FROM employees 
            WHERE department = ? AND employee_id != ? AND job_title LIKE ?
        """, (emp_dept, emp_id, '%Manager%'))
        dept_managers = [row[0] for row in cur.fetchall()]

        manager_id = None
        if dept_managers:
            manager_id = random.choice(dept_managers)
        else:
            cur.execute("SELECT employee_id FROM employees WHERE employee_id != ? AND job_title LIKE ?", (emp_id, '%Manager%'))
            all_managers = [row[0] for row in cur.fetchall()]
            if all_managers:
                manager_id = random.choice(all_managers)
            else:
                if potential_managers: # Only assign if there are others
                    manager_id = random.choice(potential_managers)
        
        if manager_id:
            cur.execute(
                "UPDATE employees SET manager_id = ? WHERE employee_id = ?",
                (manager_id, emp_id)
            )

    print(f"{num_employees} employees inserted.")
    conn.commit()
    cur.close()
    return employee_ids

def insert_customers(conn, num_customers):
    cur = conn.cursor()
    customer_ids = []
    for _ in range(num_customers):
        cur.execute(
            """
            INSERT INTO customers (first_name, last_name, email, phone_number, address, city, state, zip_code, registration_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                fake.first_name(), fake.last_name(), fake.unique.email(), fake.phone_number(),
                fake.street_address(), fake.city(), fake.state_abbr(), fake.zipcode(),
                fake.date_between(start_date='-3y', end_date='today').isoformat()
            )
        )
        customer_ids.append(cur.lastrowid)
    print(f"{num_customers} customers inserted.")
    conn.commit()
    cur.close()
    return customer_ids

def insert_products(conn, num_products):
    cur = conn.cursor()
    product_ids = []
    for _ in range(num_products):
        cur.execute(
            """
            INSERT INTO products (product_name, category, unit_price, stock_quantity)
            VALUES (?, ?, ?, ?);
            """,
            (
                fake.catch_phrase(), # MODIFIED LINE
                random.choice(PRODUCT_CATEGORIES),
                round(random.uniform(5.0, 500.0), 2),
                random.randint(0, 1000)
            )
        )
        product_ids.append(cur.lastrowid)
    print(f"{num_products} products inserted.")
    conn.commit()
    cur.close()
    return product_ids

def insert_orders_and_items(conn, num_orders, customer_ids, product_ids, employee_ids):
    cur = conn.cursor()
    order_ids = []
    
    cur.execute("SELECT employee_id FROM employees WHERE department IN ('Sales', 'Support')")
    sales_employees = [row[0] for row in cur.fetchall()]
    if not sales_employees and employee_ids: # Added check for employee_ids
        sales_employees = employee_ids 

    for _ in range(num_orders):
        if not customer_ids or not product_ids: # Ensure we have customers and products
            print("Skipping order creation due to lack of customers or products.")
            continue

        customer_id = random.choice(customer_ids)
        employee_id = random.choice(sales_employees) if sales_employees else None
        
        order_date_dt = fake.date_time_between(start_date='-2y', end_date='now', tzinfo=None)
        order_date_str = order_date_dt.isoformat(sep=' ', timespec='seconds')

        status = random.choice(ORDER_STATUSES)

        cur.execute(
            """
            INSERT INTO orders (customer_id, employee_id, order_date, status)
            VALUES (?, ?, ?, ?);
            """,
            (customer_id, employee_id, order_date_str, status)
        )
        order_id = cur.lastrowid
        order_ids.append(order_id)

        num_items_in_order = random.randint(1, 5)
        
        # Ensure we have enough unique products to sample from
        sample_size = min(num_items_in_order, len(product_ids))
        if sample_size == 0: continue # Skip if no products to add

        available_products_for_order = random.sample(product_ids, sample_size)

        for product_id in available_products_for_order:
            cur.execute("SELECT unit_price FROM products WHERE product_id = ?", (product_id,))
            price_row = cur.fetchone()
            if price_row:
                price_at_purchase = price_row[0]
                quantity = random.randint(1, 10)
                cur.execute(
                    """
                    INSERT INTO order_items (order_id, product_id, quantity, price_at_purchase)
                    VALUES (?, ?, ?, ?);
                    """,
                    (order_id, product_id, quantity, price_at_purchase)
                )
    print(f"{num_orders} orders and their items potentially inserted (check logs for skips).")
    conn.commit()
    cur.close()
    return order_ids

if __name__ == "__main__":
    if os.path.exists(DB_FILENAME):
        os.remove(DB_FILENAME)
        print(f"Removed old database file: {DB_FILENAME}")

    conn = None
    try:
        # Faker's unique email generation needs to be "fresh" for each run if the DB is recreated.
        # Instantiating Faker here ensures its internal state for `unique` is reset.
        fake = Faker() # Re-initialize Faker here for fresh unique values if script is run multiple times

        conn = sqlite3.connect(DB_FILENAME)
        print(f"Connected to SQLite database: {DB_FILENAME}")

        create_tables(conn)
        
        employee_ids = insert_employees(conn, NUM_EMPLOYEES)
        customer_ids = insert_customers(conn, NUM_CUSTOMERS)
        product_ids = insert_products(conn, NUM_PRODUCTS)
        
        if customer_ids and product_ids and employee_ids:
            insert_orders_and_items(conn, NUM_ORDERS, customer_ids, product_ids, employee_ids)
        else:
            print("Skipping orders due to lack of customers, products, or employees to link from initial generation.")

        print("\nMock data generation complete for SQLite!")

    except sqlite3.Error as e:
        print(f"SQLite database error: {e}")
        if conn:
            conn.rollback()
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()
            print("SQLite connection closed.")