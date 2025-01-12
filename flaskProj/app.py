import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
import optimize
import random
from decimal import Decimal
import math
import heapq
from functools import wraps
from datetime import timedelta
from flask_session import Session
from optimize_parallel_test import optimize_production_with_dependencies
from collections import defaultdict
from models import Machine, Book, ProductionPlan
from math import ceil


app = Flask(__name__)
load_dotenv('/var/www/ProjektuLab/flaskProj/pswd.env')

# Настройки сессии
app.config['SESSION_TYPE'] = 'filesystem'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=10)
app.config['SESSION_FILE_DIR'] = os.path.join(app.root_path, 'flask_session')  # Папка для хранения сессий
app.secret_key = os.getenv('APP_SECRET_KEY')

# Инициализация Flask-Session
Session(app)

# Database connection
app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST') 
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB')
app.config['MYSQL_PORT'] = int(os.getenv('MYSQL_PORT'))
app.secret_key = os.getenv('APP_SECRET_KEY')

mysql = MySQL(app)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_role_id(role):
    if role == "operator":
        return 2
    elif role == "admin":
        return 1
    elif role == "manager":
        return 3
    else:
        return None
    
def get_role():
    username = session.get('username')
    if username:
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT role_id FROM users WHERE username = %s", (username,))
        role_id = cursor.fetchone()
        cursor.close()

        if role_id:
            role = get_user_role(role_id[0])  # Получаем роль по role_id
        else:
            role = 'unknown'  # На случай, если роль не найдена
    return(role)

def role_required(allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Получаем role_id из сессии
            role = session.get('role')
            role_id = get_role_id(role)  
            if role_id not in allowed_roles:
                return redirect(url_for('home'))  
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.route('/')
def home():
    if 'username' in session:
        return redirect(url_for('main'))
    return render_template('home.html')

@app.route('/main')
@login_required
def main():
    return render_template('main.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        name = request.form['name']
        surname = request.form['surname']
        personal_code = request.form['personal_code']
        phone_number = request.form['phone_number']
        email = request.form['email']
        role = 2
        product_id = 1
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password != confirm_password:
            return 'Passwords do not match.'
        if len(password) < 8:
            return 'Password must be at least 8 characters long.'

        hashed_password = generate_password_hash(password)
        cursor = mysql.connection.cursor()
        try:
            cursor.execute("INSERT INTO users (username, password, role_id, production_id) VALUES (%s, %s, %s, %s)", (username, hashed_password, role, product_id))
            user_id = cursor.lastrowid
            cursor.execute("INSERT INTO employees (name, surname, personal_code, phone_number, email, user_id) VALUES (%s, %s, %s, %s, %s, %s)", (name, surname, personal_code, phone_number, email, user_id))
            mysql.connection.commit()
            session['username'] = username  # Добавляем пользователя в сессию
            session['role'] = get_role()
            session.permanent = True
            return redirect(url_for('main'))  # Перенаправляем на main
        except Exception as e:
            return f"Error occurred: {str(e)}"
        finally:
            cursor.close()
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        cursor = mysql.connection.cursor()
        cursor.execute("SELECT password FROM users WHERE username = %s", (username,))
        result = cursor.fetchone()

        if result and check_password_hash(result[0], password):
            session.clear()
            session['username'] = username
            session['role'] = get_role()
            session.permanent = True
            return redirect(url_for('main'))  # Изменено с optimize_books на main
        return 'Invalid username or password.'
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

def calculate_min_budget(books):
    """
    Count minimal budget as sum of minimal quantity of books * cost of production of every book
    """
    min_budget = sum(
        (book['material_cost'] if book['material_cost'] is not None else Decimal(0)) * 
        (book['min_books'] if book['min_books'] is not None else 0) 
        for book in books
    )
    return min_budget

def calculate_days_needed(books, is_max):
    total_time = 0  # Time in hours
    for book in books:
        quantity = book['max_books'] if is_max else book['min_books']
        total_time += quantity * book['time_per_book']
    return total_time / 8  # Transpose into days (8 working hours)

@app.route('/books', methods=['GET'])
@login_required
def books():
    cursor = mysql.connection.cursor()

    # Fetch all books from the database
    cursor.execute("""SELECT b.book_id, b.name, b.selling_price, total_production_time,
                    bm.total_material_cost
                      FROM books b
                      LEFT JOIN (SELECT bh.book_id,
                            SUM(bh.production_time_in_minutes) AS total_production_time
                            FROM book_hardwares bh
                            GROUP BY bh.book_id) bh ON b.book_id = bh.book_id
                      LEFT JOIN (SELECT bm.book_id, SUM(m.cost_per_piece * bm.material_quantity) AS total_material_cost
                            FROM book_materials bm
                            LEFT JOIN materials m ON bm.material_id = m.material_id
                            GROUP BY bm.book_id) bm ON b.book_id = bm.book_id; """)
    books_list = cursor.fetchall()
    # You can now pass these data to your template or further processing
    books = []
    role = session.get('role')
    role_id = get_role_id(role)
    for book in books_list:
        books.append({
            'id': book[0] if book[0] is not None else 0,  # Default value is 0 if None
            'name': book[1] if book[1] is not None else 'Unknown',  # Default value is 'Unknown' if None
            'selling_price': book[2] if book[2] is not None else 0.0,  # Default value is 0.0 if None
            'production_time': book[3] if book[3] is not None else 0.0,  # Default value is 0.0 if None
            'total_material_cost': book[4] if book[4] is not None else 0.0  # Default value is 0.0 if None
            
        })

    return render_template('books.html', books=books, role_id=role_id)


@app.route('/edit_book/<int:book_id>', methods=['GET'])
@role_required(allowed_roles=[1, 3])
@login_required
def edit_book(book_id):
    cursor = mysql.connection.cursor()
    cursor.execute("""SELECT
                      b.book_id, b.name, b.description, b.selling_price
                      FROM books b
                      where b.book_id = %s""", (book_id,))

    if cursor.rowcount == 0:
        return redirect(url_for('books'))

    books_list1 = cursor.fetchall()
    book = {
            'id': books_list1[0][0],
            'name': books_list1[0][1],
            'description': books_list1[0][2],
            'selling_price': books_list1[0][3],
            'materials': [],
            'machines': []
        }
    # Book materials
    cursor.execute("""SELECT
                      bm.book_material_id, bm.material_id, m.name, m.type, bm.material_quantity
                      FROM book_materials bm
                      JOIN materials m ON bm.material_id = m.material_id
                      where bm.book_id = %s""", (book_id,))
    material_list = cursor.fetchall()

    for material in material_list:
        book['materials'].append({
            'book_material_id': material[0],
            'id': material[1],
            'name': material[2],
            'type': material[3],
            'quantity': material[4]
        })

    cursor.execute("""SELECT
                      bh.book_hardware_id, bh.hardware_id, m.name, m.type,
                      bh.production_time_in_minutes, bh.order_in_queue
                      FROM book_hardwares bh
                      JOIN hardwares m ON bh.hardware_id = m.hardware_id
                      WHERE bh.book_id = %s
                      ORDER BY bh.order_in_queue""", (book_id,))
    machine_list = cursor.fetchall()

    for machine in machine_list:
        book['machines'].append({
            'book_hardware_id': machine[0],
            'id': machine[1],
            'name': machine[2],
            'type': machine[3],
            'production_time': machine[4],
            'order': machine[5],
        })

#     print(book)

    # Fetch available materials from the database
    cursor.execute("SELECT material_id, name, type FROM materials")
    materials = cursor.fetchall()

    # Group materials by type
    materials_options = {}
    for material in materials:
        material_type = material[2]
        if material_type not in materials_options:
            materials_options[material_type] = []
        materials_options[material_type].append({
            'id': material[0],
            'name': material[1]
        })


    # Fetch available machines from the database
    cursor.execute("SELECT hardware_id, name, type FROM hardwares")
    machines = cursor.fetchall()
    cursor.close()

    # Group machines by type
    machines_options = {}
    for machine in machines:
        machine_type = machine[2]
        if machine_type not in machines_options:
            machines_options[machine_type] = []
        machines_options[machine_type].append({
            'id': machine[0],
            'name': machine[1]
        })

#     materials_options = {
#     "Paper": [{"id": 1, "name": "A4 Paper"}, {"id": 2, "name": "A3 Paper"}],
#     "Ink": [{"id": 3, "name": "Black Ink"}, {"id": 4, "name": "Blue Ink"}]
#     }


    # materials_options = get_materials_options()  # Получение материалов из базы
    # machines_options = get_machines_options()  # Получение машин из базы
    cursor.close()
    return render_template('edit_book.html', book=book, materials_options=materials_options, machines_options=machines_options)



@app.route('/edit_book/<int:book_id>', methods=['POST'])
@login_required
@role_required(allowed_roles=[1, 3])
def save_book(book_id):
#     return redirect(url_for('books'))
    cursor = mysql.connection.cursor()

    book_name = request.form['name']
    book_description = request.form['description']
    book_selling_price = request.form['selling_price']
    print(book_name,book_selling_price)
    cursor.execute("""
        UPDATE books
        SET  name = %s, description = %s, selling_price = %s
        WHERE book_id = %s;
    """, (book_name, book_description,book_selling_price, book_id))


    # Получить данные из формы
    material_row_statuses = request.form.getlist('material_row_status[]')
    book_material_ids = request.form.getlist('book_material_id[]')
    material_ids = request.form.getlist('material_id[]')
    quantities = request.form.getlist('quantity[]')

    machine_row_statuses = request.form.getlist('machine_row_status[]')
    book_machine_ids = request.form.getlist('book_machine_id[]')
    machine_ids = request.form.getlist('machine_id[]')
    production_times = request.form.getlist('production_time[]')

    # Material tables
    for material_row_status,book_material_id, material_id,quantity in zip(material_row_statuses, book_material_ids, material_ids,quantities):
        if material_row_status == 'new':
            # Добавить новую строку
            cursor.execute("""
                INSERT INTO book_materials (book_id, material_id, material_quantity)
                VALUES (%s, %s, %s)
            """, (book_id, material_id, quantity))
        elif material_row_status == 'edited':
            # Обновить существующую строку
            cursor.execute("""
                        UPDATE book_materials
                        SET material_id = %s, material_quantity = %s
                        WHERE book_material_id = %s
                    """, (material_id, quantity, book_material_id))
        elif material_row_status == 'deleted':
            # Удалить строку
            cursor.execute("DELETE FROM book_materials WHERE book_material_id = %s", (book_material_id,))


    # Machine tables
    order=0
    for machine_row_status, book_machine_id, machine_id, production_time in zip(machine_row_statuses, book_machine_ids, machine_ids, production_times):
        order+=1
        if machine_row_status == 'new':
            # Добавить новую строку
            cursor.execute("""
                INSERT INTO book_hardwares (book_id, hardware_id, production_time_in_minutes, order_in_queue)
                VALUES (%s, %s, %s, %s)
            """, (book_id, machine_id, production_time, order))
        elif machine_row_status == 'edited':
            # Обновить существующую строку
            cursor.execute("""
                        UPDATE book_hardwares
                        SET hardware_id = %s, production_time_in_minutes = %s, order_in_queue = %s
                        WHERE book_hardware_id = %s
                    """, (machine_id, production_time, order, book_machine_id))
        elif machine_row_status == 'deleted':
            order-=1
            # Удалить строку
            cursor.execute("DELETE FROM book_hardwares WHERE book_hardware_id = %s", (book_machine_id,))



    mysql.connection.commit()
    return redirect(url_for('books'))

@app.route('/delete_plan/<int:plan_id>')
@login_required
@role_required(allowed_roles=[1, 3])
def delete_plan(plan_id):
    cursor = mysql.connection.cursor()

    cursor.execute("DELETE FROM production_plan WHERE production_plan_id = %s", (plan_id,))
    cursor.execute("DELETE FROM production_plan_books WHERE production_plan_id = %s", (plan_id,))


    mysql.connection.commit()

    cursor.close()

    # Redirect to the book list page after deletion
    return redirect(url_for('display_plans'))

@app.route('/delete_book/<book_id>', methods=['GET'])
@login_required
@role_required(allowed_roles=[1, 3])
def delete_book(book_id):
    cursor = mysql.connection.cursor()

    # Delete the book from the database
    cursor.execute("DELETE FROM books WHERE book_id = %s", (book_id,))
    mysql.connection.commit()

    cursor.close()

    # Redirect to the book list page after deletion
    return redirect(url_for('books'))


@app.route('/create_book', methods=['GET', 'POST'])
@login_required
def create_book():
    cursor = mysql.connection.cursor()

    if request.method == 'POST':
        # Get book details from the form
        name = request.form['name']
        description = request.form['description']
        selling_price = request.form['selling_price']

        # Insert the book into the database
        cursor.execute("""
            INSERT INTO books (name, description, selling_price) VALUES (%s, %s, %s)
        """, (name, description, selling_price))
        book_id = cursor.lastrowid

        # print(name, description, selling_price)
        # Insert materials associated with the book
        material_ids = request.form.getlist('material_id[]')
        material_quantities = request.form.getlist('quantity[]')

        for material_id, quantity in zip(material_ids, material_quantities):
            # print(material_id, quantity)
            cursor.execute("""
                INSERT INTO book_materials (book_id, material_id, material_quantity)
                VALUES (%s, %s, %s)
            """, (book_id, material_id, quantity))

        # Insert machines associated with the book
        machine_ids = request.form.getlist('machine_id[]')
        machine_pr_times = request.form.getlist('production_time[]')

        order=0
        for machine_id, machine_pr_time in zip(machine_ids, machine_pr_times):
            order+=1
            cursor.execute("""
                INSERT INTO book_hardwares (book_id, hardware_id, production_time_in_minutes, order_in_queue)
                VALUES (%s, %s, %s, %s)
            """, (book_id, machine_id, machine_pr_time, order))

        mysql.connection.commit()
        cursor.close()

        return redirect(url_for('books'))

    # Fetch available materials from the database
    cursor.execute("SELECT material_id, name, type FROM materials")
    materials = cursor.fetchall()

    # Group materials by type
    grouped_materials = {}
    for material in materials:
        material_type = material[2]
        if material_type not in grouped_materials:
            grouped_materials[material_type] = []
        grouped_materials[material_type].append({
            'id': material[0],
            'name': material[1]
        })

    # Fetch available machines from the database
    cursor.execute("SELECT hardware_id, name, type FROM hardwares")
    machines = cursor.fetchall()
    cursor.close()

    # Group machines by type
    grouped_machines = {}
    for machine in machines:
        machine_type = machine[2]
        if machine_type not in grouped_machines:
            grouped_machines[machine_type] = []
        grouped_machines[machine_type].append({
            'id': machine[0],
            'name': machine[1]
        })
#     grouped_materials = {
#     "Paper": [{"id": 1, "name": "A4 Paper"}, {"id": 2, "name": "A3 Paper"}],
#     "Ink": [{"id": 3, "name": "Black Ink"}, {"id": 4, "name": "Blue Ink"}]
#     }

    return render_template('create_book.html', materials=grouped_materials, machines=grouped_machines)



@app.before_request
def session_handler():
    session.permanent = True  # Делаем сессию постоянной
    app.permanent_session_lifetime = timedelta(minutes=10)  # Устанавливаем время жизни

@app.route('/materials')
@login_required
def materials():
    cursor = mysql.connection.cursor()
    
    # Получаем список всех материалов с правильными полями из базы
    cursor.execute("""
        SELECT 
            material_id,
            name,
            quantity,
            cost_per_piece,
            type
        FROM materials
        ORDER BY name
    """)
    
    materials_list = cursor.fetchall()
    materials = []
    
    for material in materials_list:
        materials.append({
            'id': material[0],
            'name': material[1],
            'quantity': material[2],
            'cost': material[3],
            'type': material[4]
        })
    role = session.get('role')
    role_id = get_role_id(role)   
    print(role_id) 
    cursor.close()
    return render_template('materials.html', materials=materials,role_id = role_id)

@app.route('/employees')
@login_required
def employees():
    cursor = mysql.connection.cursor()
    
    cursor.execute("""
        SELECT 
            employee_id,
            name,
            surname,
            personal_code,
            phone_number,
            email,
            user_id
        FROM employees
        ORDER BY surname, name
    """)
    
    employees_list = cursor.fetchall()
    employees = []
    
    for employee in employees_list:
        employees.append({
            'id': employee[0],
            'name': employee[1],
            'surname': employee[2],
            'personal_code': employee[3],
            'phone': employee[4],
            'email': employee[5],
            'user_id': employee[6]
        })
        
    cursor.close()
    role_id = get_role_id(session['role'])
    return render_template('employees.html', employees=employees,role_id=role_id)

@app.route('/delete_employee/<int:employee_id>')
@role_required(allowed_roles=[1])
@login_required
def delete_employee(employee_id):
    cursor = mysql.connection.cursor()

    # Fetch the user_id of the employee

    cursor.execute("SELECT user_id FROM employees WHERE employee_id = %s", (employee_id,))
    result = cursor.fetchone()  # Fetch the record

    if result:
        user_id = result[0]  # Extract user_id from the result

        # Delete the employee record
        cursor.execute("DELETE FROM employees WHERE employee_id = %s", (employee_id,))

        # Delete the user record
        cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
        print(f"Deleted user with ID: {user_id}")
    else:
        print("No user found for the given employee_id")
    mysql.connection.commit()

    cursor.close()

    # Redirect to the book list page after deletion
    return redirect(url_for('employees'))

@app.route('/edit_employee/<int:employee_id>', methods=['GET', 'POST'])
@role_required(allowed_roles=[1])
@login_required
def edit_employee(employee_id):
    if request.method == 'GET':
        print("get used")
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT employee_id, name, surname, personal_code, phone_number, email FROM employees WHERE employee_id = %s", (employee_id,))

        if cursor.rowcount == 0:
                        return redirect(url_for('books'))

        employees = cursor.fetchall()

        employee = {
                'id': employees[0][0],
                'name': employees[0][1],
                'surname': employees[0][2],
                'personal_code': employees[0][3],
                'phone': employees[0][4],
                'email': employees[0][5]
            }
        cursor.close()

        if employee:
            return render_template('edit_employee.html', employee=employee)
        else:
            return "Employee not found", 404

    if request.method == 'POST':
        cursor = mysql.connection.cursor()
        name = request.form['name']
        surname = request.form['surname']
        personal_code = request.form['personal_code']
        phone = request.form['phone']
        email = request.form['email']

        cursor.execute("""
                    UPDATE employees
                    SET name = %s, surname = %s, personal_code = %s, phone_number = %s, email = %s
                    WHERE employee_id = %s
                """, (name, surname, personal_code, phone, email,employee_id ))

        mysql.connection.commit()

        cursor.close()
        return redirect(url_for('employees'))
    return redirect(url_for('employees'))

@app.route('/machines')
@login_required
def machines():
    cursor = mysql.connection.cursor()
    
    cursor.execute("""
        SELECT 
            hardware_id,
            name,
            type,
            capacity
        FROM hardwares
        ORDER BY name
    """)
    
    machines_list = cursor.fetchall()
    machines = []
    
    for machine in machines_list:
        machines.append({
            'id': machine[0],
            'name': machine[1],
            'type': machine[2],
            'capacity': machine[3]
        })
    role_id = get_role_id(session['role'])    
    cursor.close()
    return render_template('machines.html', machines=machines, role_id = role_id)

@app.route('/create_material', methods=['GET', 'POST'])
@login_required
def create_material():
    cursor = mysql.connection.cursor()
    if request.method == 'POST':
        type = request.form.get('type')
        new_type = request.form.get('new_type')
        name = request.form.get('name')
        quantity = request.form.get('quantity')
        cost_per_piece = request.form['cost_per_piece']

#         print(type, new_type)
        # If new type selected
        if type == 'new':
            type = new_type

        cursor.execute("""
            INSERT INTO materials (name, quantity, cost_per_piece, type)
            VALUES (%s, %s, %s, %s)
        """, (name, quantity, cost_per_piece, type))


        mysql.connection.commit()
        cursor.close()
        return redirect(url_for('materials'))

    # Get existing types
    cursor.execute("""
            SELECT DISTINCT type
            FROM materials
            ORDER BY type
        """)

    materials_list = cursor.fetchall()
    existing_types = []

    for material in materials_list:
        existing_types.append(material[0])

    cursor.close()
    return render_template('create_material.html', existing_types=existing_types)







@app.route('/edit_material/<int:material_id>', methods=['GET', 'POST'])
@login_required
@role_required(allowed_roles=[1, 3])
def edit_material(material_id):
    cursor = mysql.connection.cursor()

    if request.method == 'POST':
        name = request.form['name']
        material_type = request.form['type']
        new_type = request.form['new_type']
        quantity = request.form['quantity']
        cost_per_piece = request.form['cost_per_piece']

        # If new type selected
        if material_type == 'new':
            material_type = new_type

        cursor.execute("""
            UPDATE materials
            SET name = %s, quantity = %s, cost_per_piece = %s, type = %s
            WHERE material_id = %s
        """, (name, quantity, cost_per_piece, material_type, material_id))

        mysql.connection.commit()
        cursor.close()
        return redirect(url_for('materials'))
 # Get existing types
    cursor.execute("""
            SELECT DISTINCT type
            FROM materials
            ORDER BY type
        """)

    materials_list = cursor.fetchall()
    existing_types = []

    for material in materials_list:
        existing_types.append(material[0])

    # Получаем данные материала для редактирования
    cursor.execute("""
        SELECT material_id, name, quantity, cost_per_piece, type
        FROM materials
        WHERE material_id = %s
    """, (material_id,))
    
    material = cursor.fetchone()
    cursor.close()

    if material:
        material_data = {
            'id': material[0],
            'name': material[1],
            'quantity': material[2],
            'cost': material[3],
            'type': material[4]
        }
        return render_template('edit_material.html', material=material_data, existing_types=existing_types)
    
    return redirect(url_for('materials'))

@app.route('/delete_material/<int:material_id>')
@role_required(allowed_roles=[1, 3])
@login_required
def delete_material(material_id):
    cursor = mysql.connection.cursor()

    # Check if the material is used in books
    cursor.execute("""
        SELECT b.name FROM book_materials bm
        JOIN books b ON bm.book_id = b.book_id
        WHERE bm.material_id = %s
    """, (material_id,))

    used_in_books = cursor.fetchall()

    if used_in_books:
        cursor.close()
        # Generate a list of book titles where the material is used
        books_list = [book[0] for book in used_in_books]
        books_message = ', '.join(books_list).replace("'", "\\'")  # Escape single quotes for JavaScript
        return f"Cannot delete material as it is used in the following books: {books_message}."

    # Delete the material if not used
    cursor.execute("DELETE FROM materials WHERE material_id = %s", (material_id,))
    mysql.connection.commit()
    cursor.close()

    return f"Material was successfully deleted"


@app.route('/create_machine', methods=['GET', 'POST'])
@login_required
def create_machine():
    cursor = mysql.connection.cursor()
    if request.method == 'POST':
        type = request.form.get('type')
        new_type = request.form.get('new_type')
        name = request.form.get('name')
        capacity = request.form.get('capacity')
        print(type, new_type)
        # If new type selected
        if type == 'new':
            type = new_type

        cursor.execute("""
            INSERT INTO hardwares (name, type, capacity)
            VALUES (%s, %s, %s)
        """, (name, type, capacity))

        mysql.connection.commit()
        cursor.close()
        return redirect(url_for('machines'))

    # Get existing types
    cursor.execute("""
            SELECT DISTINCT type
            FROM hardwares
            ORDER BY type
        """)

    machines_list = cursor.fetchall()
    existing_types = []

    for machine in machines_list:
        existing_types.append(machine[0])

    cursor.close()
    return render_template('create_machine.html', existing_types=existing_types)





@app.route('/edit_machine/<int:machine_id>', methods=['GET', 'POST'])
@role_required(allowed_roles=[1, 3])
@login_required
def edit_machine(machine_id):
    cursor = mysql.connection.cursor()

    if request.method == 'POST':
        name = request.form['name']
        machine_type = request.form['type']
        new_type = request.form['new_type']
        capacity = request.form['capacity']

        # If new type selected
        if machine_type == 'new':
            machine_type = new_type

        cursor.execute("""
            UPDATE hardwares
            SET name = %s, type = %s, capacity = %s
            WHERE hardware_id = %s
        """, (name, machine_type, capacity, machine_id))

        mysql.connection.commit()
        cursor.close()

        return redirect(url_for('machines'))
    # Get existing types
    cursor.execute("""
            SELECT DISTINCT type
            FROM hardwares
            ORDER BY type
        """)

    machines_list = cursor.fetchall()
    existing_types = []

    for machine in machines_list:
        existing_types.append(machine[0])

    cursor.execute("""
        SELECT hardware_id, name, type, capacity
        FROM hardwares
        WHERE hardware_id = %s
    """, (machine_id,))
    
    machine = cursor.fetchone()
    cursor.close()

    if machine:
        machine_data = {
            'id': machine[0],
            'name': machine[1],
            'type': machine[2],
            'capacity': machine[3]
        }
        return render_template('edit_machine.html', machine=machine_data, existing_types=existing_types)
    
    return redirect(url_for('machines'))

@app.route('/delete_machine/<int:machine_id>', methods=['GET'])
@role_required(allowed_roles=[1, 3])
@login_required
def delete_machine(machine_id):
    cursor = mysql.connection.cursor()

# Check if the machine is used in books
    cursor.execute("""
    SELECT b.name FROM book_hardwares bm
    JOIN books b ON bm.book_id = b.book_id
    WHERE bm.hardware_id = %s
    """, (machine_id,))

    used_in_books = cursor.fetchall()

    if used_in_books:
        cursor.close()
        # Generate a list of book titles where the machine is used
        books_list = [book[0] for book in used_in_books]
        books_message = ', '.join(books_list).replace("'", "\\'")  # Escape single quotes for JavaScript
        return f"Cannot delete machine as it is used in the following books: {books_message}."

    cursor.execute("DELETE FROM hardwares WHERE hardware_id = %s", (machine_id,))
    mysql.connection.commit()
    cursor.close()
    
    return f"Machine was successfully deleted"


# plans CRUD operations

@app.route('/create_plan', methods=['GET', 'POST'])
@role_required(allowed_roles=[1, 3])
@login_required
def create_plan():
    cursor = mysql.connection.cursor()

    if request.method == 'POST':
        # Get plan details from the form
        name = request.form['name']
        operator = request.form['operator']

        # Insert the plan into the database
        cursor.execute("""
            INSERT INTO production_plan (plan_name, operator_id) VALUES (%s, %s)
        """, (name, operator))
        plan_id = cursor.lastrowid

#         print(name, operator)
        # Insert books associated with the plan
        book_ids = request.form.getlist('book_id[]')
        min_amounts = request.form.getlist('min_amount[]')
        max_amounts = request.form.getlist('max_amount[]')

        for book_id, min_amount, max_amount in zip(book_ids, min_amounts, max_amounts):
            # print(material_id, quantity)
            cursor.execute("""
                INSERT INTO production_plan_books (book_id, book_amount_min, book_amount_max, production_plan_id)
                VALUES (%s, %s, %s, %s)
            """, (book_id, min_amount, max_amount, plan_id))

        mysql.connection.commit()
        cursor.close()

        return redirect(url_for('display_plans'))

    # Fetch available books from the database
    cursor.execute("SELECT book_id, name FROM books")
    books = cursor.fetchall()

    # Group books by type
    grouped_books = []
    for book in books:
        grouped_books.append({
        'id': book[0],
        'name': book[1]
        })

    # Fetch available operators from the database
    cursor.execute("""
           SELECT e.employee_id, e.name, e.surname FROM employees e
           JOIN users u on u.user_id = e.user_id
           WHERE role_id = 2
       """)
    operators = cursor.fetchall()

    # Group books by type
    grouped_operators = []
    for operator in operators:
        grouped_operators.append({
        'id': operator[0],
        'name': operator[1] + " " + operator[2]
        })
    cursor.close()
    return render_template('create_plan.html', operators=grouped_operators, books=grouped_books)



@app.route('/edit_plan/<int:plan_id>', methods=['GET'])
@role_required(allowed_roles=[1, 3])
@login_required
def edit_plan(plan_id):

    cursor = mysql.connection.cursor()
    cursor.execute("""SELECT
                      p.plan_name, p.operator_id
                      FROM production_plan p
                      where p.production_plan_id = %s""", (plan_id,))

    if cursor.rowcount == 0:
        return redirect(url_for('display_plans'))

    plan_list = cursor.fetchone()
    plan = {
            'name': plan_list[0],
            'operator_id': plan_list[1],
            'books': [],
        }
    # Books list
    cursor.execute("""SELECT
                      b.book_id, b.name, ppl.book_amount_min, ppl.book_amount_max, ppl.production_plan_book_id
                      FROM production_plan_books ppl
                      JOIN books b ON b.book_id = ppl.book_id
                      where ppl.production_plan_id = %s """, (plan_id,))
    books_list = cursor.fetchall()

    for book in books_list:
        plan['books'].append({
            'id': book[0],
            'name': book[1],
            'min_amount': book[2],
            'max_amount': book[3],
            'plan_book_id': book[4]
        })


# Fetch available books from the database
    cursor.execute("SELECT book_id, name FROM books")
    books = cursor.fetchall()

    # Group books by type
    book_options = []
    for book in books:
        book_options.append({
        'id': book[0],
        'name': book[1]
        })

    # Fetch available operators from the database
    cursor.execute("""
           SELECT e.employee_id, e.name, e.surname FROM employees e
           JOIN users u on u.user_id = e.user_id
           WHERE role_id = 2
       """)
    operators = cursor.fetchall()

    # Group books by type
    operator_options = []
    for operator in operators:
        operator_options.append({
        'id': operator[0],
        'name': operator[1] + " " + operator[2]
        })
    cursor.close()


#     materials_options = {
#     "Paper": [{"id": 1, "name": "A4 Paper"}, {"id": 2, "name": "A3 Paper"}],
#     "Ink": [{"id": 3, "name": "Black Ink"}, {"id": 4, "name": "Blue Ink"}]
#     }

    cursor.close()
    return render_template('edit_plan.html', plan=plan, operator_options=operator_options, book_options=book_options)



@app.route('/edit_plan/<int:plan_id>', methods=['POST'])
@role_required(allowed_roles=[1, 3])
@login_required
def save_plan(plan_id):
#     return redirect(url_for('books'))
    cursor = mysql.connection.cursor()

    # Get plan details from the form
    name = request.form['name']
    operator = request.form['operator']

    cursor.execute("""
        UPDATE production_plan
        SET  plan_name = %s, operator_id = %s
        WHERE production_plan_id = %s;
    """, (name, operator, plan_id))


    # Получить данные из формы
    # Insert books associated with the plan
    book_row_statuses = request.form.getlist('book_row_status[]')
    plan_book_ids = request.form.getlist('plan_book_id[]')
    book_ids = request.form.getlist('book_id[]')
    min_amounts = request.form.getlist('min_amount[]')
    max_amounts = request.form.getlist('max_amount[]')

    print(book_row_statuses, book_ids, min_amounts, max_amounts)
    # Material tables
    for book_row_status, plan_book_id, book_id, min_amount, max_amount in zip(book_row_statuses, plan_book_ids, book_ids, min_amounts, max_amounts):
        print(book_row_status, book_id, min_amount, max_amount)
        if book_row_status == 'new':
            # Добавить новую строку
            cursor.execute("""
                INSERT INTO production_plan_books (book_id, book_amount_min, book_amount_max, production_plan_id)
                VALUES (%s, %s, %s, %s)
            """, (book_id, min_amount, max_amount, plan_id))
        elif book_row_status == 'edited':
            # Обновить существующую строку
            print("edit")
            cursor.execute("""
                        UPDATE production_plan_books
                        SET book_id = %s, book_amount_min = %s, book_amount_max = %s
                        WHERE production_plan_book_id = %s
                    """, (book_id, min_amount, max_amount, plan_book_id))
        elif book_row_status == 'deleted':
            # Удалить строку
            cursor.execute("DELETE FROM production_plan_books WHERE production_plan_book_id = %s", (plan_id,))

    mysql.connection.commit()
    return redirect(url_for('display_plans'))

@app.route('/finish_plan/<int:plan_id>/<int:budget>/<int:profit>/<int:days>')
@role_required(allowed_roles=[1, 3])
@login_required
def finish_plan(plan_id, budget, profit, days):
    cursor = mysql.connection.cursor()
    cursor.execute("""
            UPDATE production_plan
            SET budget = %s, completed = 2, profit = %s , time_limit_in_days = %s
            WHERE production_plan_id = %s;
        """, (budget, profit, days, plan_id))

    mysql.connection.commit()

    cursor.close()
    return redirect(url_for('display_plans'))

@app.route('/save_optimization/<int:plan_id>/<int:budget>/<int:profit>/<int:days>')
@role_required(allowed_roles=[1, 3])
@login_required
def save_optimization(plan_id, budget, profit, days):
    cursor = mysql.connection.cursor()
    cursor.execute("""
            UPDATE production_plan
            SET budget = %s, completed = 1, profit = %s , time_limit_in_days = %s
            WHERE production_plan_id = %s;
        """, (budget, profit, days, plan_id))

    mysql.connection.commit()

    cursor.close()
    return redirect(url_for('display_plans'))

#########################################################################################################
#########################################################################################################
#########################################################################################################
###########################################OPTIMIZATION PART#############################################
#########################################################################################################
#########################################################################################################
#########################################################################################################

def fetch_books_and_machines():
    cursor = mysql.connection.cursor()

    # Get data about books
    cursor.execute(""" 
        SELECT book_id, name, selling_price FROM books;
    """)
    books_data = cursor.fetchall()

    # Get data about machines
    cursor.execute(""" 
        SELECT hardware_id, name, type, capacity FROM hardwares;
    """)
    machines_data = cursor.fetchall()

    # Get production plans
    cursor.execute(""" 
        SELECT p.production_plan_id, p.plan_name, p.operator_id, CONCAT(e.name,' ',e.surname), p.time_limit_in_days, p.budget, p.profit, p.completed FROM production_plan p
        JOIN employees e ON e.employee_id = p.operator_id;
    """)
    production_plan_data = cursor.fetchall()

    # Get books in production plans
    cursor.execute(""" 
        SELECT production_plan_book_id, book_id, book_amount_min, book_amount_max, production_plan_id
        FROM production_plan_books;
    """)
    production_plan_books_data = cursor.fetchall()

    # Get materials for each book
    cursor.execute(""" 
        SELECT book_id, material_id, material_quantity 
        FROM book_materials;
    """)
    book_materials_data = cursor.fetchall()

    # Get production time for each book and each machine
    cursor.execute(""" 
        SELECT book_id, hardware_id, production_time_in_minutes 
        FROM book_hardwares;
    """)
    book_hardwares_data = cursor.fetchall()

    books = {}
    for book_id, name, selling_price in books_data:
        books[book_id] = Book(book_id, name, selling_price, [], 0, 0)

    machines = {}
    for hardware_id, name, type, capacity in machines_data:
        machines[hardware_id] = Machine(hardware_id, name, type, capacity)

    production_plans = {}
    for production_plan_id, production_plan_name, operator_id, operator_name, time_limit_in_days, budget, profit, completed in production_plan_data:
        production_plans[production_plan_id] = ProductionPlan(production_plan_id, production_plan_name, operator_id, operator_name, time_limit_in_days, budget, profit, completed)

    # Bind books to plans considering their order in the production_plan_books table
    for production_plan_book_id, book_id, book_amount_min, book_amount_max, production_plan_id in production_plan_books_data:
        if book_id in books and production_plan_id in production_plans:
            book = books[book_id]
            book.min_amount = book_amount_min
            book.max_amount = book_amount_max
            # Add books to plan in the order they appear
            production_plans[production_plan_id].books.append(book)

    # Bind equipment to books
    for book in books.values():
        book.hardware_sequence = [
            (hardware_id, production_time) for book_id, hardware_id, production_time in book_hardwares_data if book_id == book.book_id
        ]
        book.production_time = sum(time for _, time in book.hardware_sequence)

    # Fill in information about materials for books
    for book_id, material_id, material_quantity in book_materials_data:
        if book_id in books:
            cursor.execute(""" 
                SELECT cost_per_piece FROM materials WHERE material_id = %s;
            """, [material_id])
            material_cost = cursor.fetchone()[0]
            total_material_cost = material_quantity * material_cost
            books[book_id].production_cost += total_material_cost

    # Calculate profit per minute for each book
    for book in books.values():
        book.calculate_profit_per_minute()

    cursor.close()
    return books, machines, production_plans


def calculate_budget_and_profit(production_plan_id, production_plans, books, machines, use_min_amount=False):
    plan = production_plans.get(production_plan_id)
    if not plan:
        return None, None, None, [], 0, 0

    min_budget = 0
    max_budget = 0
    total_production_cost = 0
    total_sales = 0
    schedule_details = []  # For storing information about time intervals for each book and stage

    # For tracking when machines will be free
    machine_availability = {machine.hardware_id: 0 for machine in machines.values()}

    # For calculating minimum and maximum production time
    min_time = 0  # Minimum production time for the entire plan
    max_time = 0  # Maximum production time for the entire plan

    # Calculate minimum budget
    # Calculate maximum budget
   
    for book in plan.books:
        min_budget += book.production_cost * book.min_amount
        max_budget += book.production_cost * book.max_amount
   
    sorted_books= sorted(plan.books, key=lambda b: b.profit_per_minute, reverse=True)
    for book in sorted_books:
        # Use min_amount or max_amount depending on the flag
        book_amount = book.min_amount if use_min_amount else book.max_amount

        total_production_cost += book.production_cost * book_amount
        total_sales += book.selling_price * book_amount

        # Start time for each book will depend on the last completed stage
        book_start_time = 0  # Start from zero minutes

        # For each book, consider its stages on different machines
        for hardware_id, production_time in book.hardware_sequence:
            available_at = max(book_start_time, machine_availability[hardware_id])  # Machine can start only when it's free
            start_time = available_at
            finish_time = start_time + production_time * book_amount

            # Add information about time interval for this stage
            schedule_details.append({
                'book_name': book.name,
                'hardware_name': machines[hardware_id].name,
                'start_time': start_time,
                'finish_time': finish_time,
                'production_time': production_time * book_amount
            })

            # Update when machine will be free
            machine_availability[hardware_id] = finish_time

            # Update start time for next stage of this book
            book_start_time = finish_time

            # Calculate minimum and maximum time for current stage
            min_time = max(min_time, finish_time)
            max_time = max(max_time, finish_time)

    # Convert time to days
    total_days_min = min_time / (24 * 60)  # Minimum time in days
    total_days_max = max_time / (24 * 60)  # Maximum time in days

    # Calculate profit
    profit = total_sales - total_production_cost

    return min_budget, max_budget, profit, total_days_max, total_days_min, schedule_details

@app.route('/plans')
@login_required
def display_plans():
    books, machines, production_plans = fetch_books_and_machines()
    role_id = get_role_id(session['role'])
    print(production_plans)
    viewed_production_plans = {}
    in_progress_production_plans = {}
    completed_production_plans = {}
    for plan in production_plans:  # Assuming `production_plans` is a list of dictionaries
        if production_plans.get(plan).status == 0:
            viewed_production_plans[plan] = production_plans[plan]
        elif production_plans.get(plan).status == 1:
            in_progress_production_plans[plan] = production_plans[plan]
        elif production_plans.get(plan).status == 2:
            completed_production_plans[plan] = production_plans[plan]
    
    return render_template(
        'plans.html', 
        viewed_production_plans=viewed_production_plans,
        in_progress_production_plans=in_progress_production_plans,
        completed_production_plans=completed_production_plans,
        role_id=role_id
    )


@app.route('/plan/<int:production_plan_id>/', methods=['GET', 'POST'])
@login_required
def display_production_plan(production_plan_id, saved_budget=None, saved_days=None):
    books, machines, production_plans = fetch_books_and_machines()
    plan = production_plans.get(production_plan_id)
    saved_budget = request.args.get('saved_budget', type=float)
    saved_days = request.args.get('saved_days', type=int)
    if not plan:
        return f"<h1>Production plan {production_plan_id} not found.</h1>"

    production_plan_name = plan.production_plan_name

    # Получаем минимальный и максимальный бюджет
    min_budget, max_budget = plan.calculate_budget(books)
    optimized_budget = min_budget
#     optimized_budget = optimize_budget(min_budget, max_budget, production_plans, production_plan_id)
    # Проверяем, был ли отправлен POST-запрос для оптимизации бюджета
    if request.method == 'POST':
        optimized_budget = optimize_budget(min_budget, max_budget, production_plans, production_plan_id)  # Оптимизируем бюджет
        print(optimized_budget)
    
    # Prepare books information for the table
    books_details = []
    for book in production_plans[production_plan_id].books:
        production_time = book.production_time  # время производства одной единицы книги в часах
        profit_per_unit = book.selling_price - book.production_cost
        profit_per_hour = profit_per_unit / production_time if production_time > 0 else 0

        books_details.append({
            "name": book.name,
            "min_amount": book.min_amount,
            "max_amount": book.max_amount,
            "production_cost": book.production_cost,
            "selling_price": book.selling_price,
            "production_time": round(production_time, 2),  # округление до 2 знаков
            "profit_per_hour": round(profit_per_hour, 2)  # округление до 2 знаков
        })

    # Get budget and profit details

    min_budget, max_budget, profit, total_days_max, total_days_min, schedule_details_max = calculate_budget_and_profit(
        production_plan_id, production_plans, books, machines)
    min_budget1, max_budget1, profit1, total_days_max1, total_days_min, schedule_details_max1 = calculate_budget_and_profit(
        production_plan_id, production_plans, books, machines, True)

    if min_budget is None:
        return f"<h1>Production plan with ID {production_plan_id} not found.</h1>"

    # Calculate minimum and maximum profit
    min_profit = sum((book.selling_price - book.production_cost) * book.min_amount
                     for book in production_plans[production_plan_id].books)
    max_profit = sum((book.selling_price - book.production_cost) * book.max_amount
                     for book in production_plans[production_plan_id].books)
    
    if saved_budget is None:
        saved_budget = min_budget
    if saved_days is None:
        saved_days = ceil(total_days_min)
    # Pass data to the template
    return render_template(
        'plan.html',
        production_plan_id=production_plan_id,
        production_plan_name=production_plan_name,
        books_details=books_details,  # Add book details for table
        min_budget=min_budget,
        max_budget=max_budget,
        profit=profit,
        min_profit=min_profit,
        max_profit=max_profit,
        total_days_min=ceil(total_days_min),
        total_days_max=ceil(total_days_max),
        optimized_budget=optimized_budget,  # Передаем текущий бюджет
        saved_budget = saved_budget,
        saved_days = saved_days
    )

@app.route('/calculate_with_budget', methods=['POST'])
@login_required
def calculate_with_budget():
    # Get data from the form
    budget = Decimal(request.form['budget'])  # Convert to Decimal
    production_plan_id = int(request.form['production_plan_id'])

    books, machines, production_plans = fetch_books_and_machines()
    plan = production_plans.get(production_plan_id)
    if not plan:
        return f"<h1>Production plan with ID {production_plan_id} not found.</h1>"
    production_plan_name = plan.production_plan_name
    # First, fill in the budget for each book considering the minimum amount
    selected_books = []
    total_cost = Decimal(0)  # Use Decimal for precise calculations
    remaining_budget = budget

    # Sort books by profit_per_minute priority (descending)
    sorted_books = sorted(plan.books, key=lambda b: b.profit_per_minute, reverse=True)

    # 1. First, add the minimum amount of each book if the budget allows
    for book in sorted_books:
        min_cost = Decimal(book.production_cost) * book.min_amount  # Cost of minimum amount of book

        if remaining_budget >= min_cost:  # Check if we can run minimum amount
            selected_books.append((book, book.min_amount))
            remaining_budget -= min_cost  # Reduce remaining budget
        else:
            # If there is no budget for the minimum amount of the book, skip this book
            continue

    # 2. After that, if there is room in the budget, add additional books by profitability
    for book in sorted_books:
        if any(selected_book[0] == book for selected_book in selected_books):  # If book has already been added
            already_added_amount = next(amount for selected_book, amount in selected_books if selected_book == book)
            max_possible_amount = book.max_amount - already_added_amount

            if max_possible_amount > 0:  # Only proceed if there is room to add more
                # Check if there is enough budget for the maximum amount
                max_cost = Decimal(book.production_cost) * max_possible_amount  # Cost of maximum amount of book

                if remaining_budget >= max_cost:  # If there is enough budget for the maximum amount
                    selected_books = [(selected_book, amount + max_possible_amount) if selected_book == book else (selected_book, amount) for selected_book, amount in selected_books]
                    remaining_budget -= max_cost  # Reduce remaining budget
                else:
                    # If there is not enough budget, add as much as we can
                    possible_amount = remaining_budget // Decimal(book.production_cost)
                    if possible_amount > 0:
                        selected_books = [(selected_book, amount + possible_amount) if selected_book == book else (selected_book, amount) for selected_book, amount in selected_books]
                        remaining_budget -= possible_amount * Decimal(book.production_cost)

    # Calculate time and profit for the selected books
    machine_availability = {machine.hardware_id: 0 for machine in machines.values()}
    schedule_details = []
    profit = Decimal(0)  # Use Decimal for precise calculations
    for book, amount in selected_books:
        book_start_time = 0
        for hardware_id, production_time in book.hardware_sequence:
            available_at = max(book_start_time, machine_availability[hardware_id])
            start_time = available_at
            finish_time = start_time + production_time * amount
            schedule_details.append({
                'book_name': book.name,
                'hardware_name': machines[hardware_id].name,
                'start_time': start_time,
                'finish_time': finish_time,
                'production_time': production_time * amount
            })
            machine_availability[hardware_id] = finish_time
            book_start_time = finish_time
        profit += (book.selling_price - book.production_cost) * amount

    # Pass data to the result
    return render_template(
        'result.html',
        production_plan_id=production_plan_id,
        production_plan_name=production_plan_name,
        budget=budget,
        profit=profit,
        selected_books=selected_books,
        schedule_details=schedule_details,
        total_days=ceil(finish_time/24/60)
    )

@app.route('/calculate_by_days', methods=['POST'])
@login_required
def calculate_by_days():
    production_plan_id = int(request.form['production_plan_id'])

    # Получаем данные о планах, книгах и машинах
    books, machines, production_plans = fetch_books_and_machines()

    plan = production_plans.get(production_plan_id)

    if not plan:
        return f"<h1>Production plan with ID {production_plan_id} not found.</h1>"

    # Получаем минимальный бюджет
    min_budget, max_budget = plan.calculate_budget(books)

    # Получаем лимит по дням из формы
    time_limit_days = int(request.form['time_limit'])  
    budget = min_budget
    # Начинаем с минимального бюджета
    budget, profit, selected_books, schedule_details, total_days_max = calculate_budget_with_time_limit(
            production_plan_id, production_plans, books, machines, budget)
    while not (time_limit_days * 0.99 <= total_days_max <= time_limit_days * 1.01):

        # Проверяем, превышает ли бюджет максимальное значение
        if budget * Decimal(1.0025) > max_budget:

            budget = max_budget  # Используем максимальный бюджет
            break  # Выходим из цикла
        else:
            budget = round(budget * Decimal(1.0025))
        # Вызываем новую функцию для расчета бюджета с учетом времени
        budget1, profit, selected_books, schedule_details, total_days_max = calculate_budget_with_time_limit(
            production_plan_id, production_plans, books, machines, budget)


    # Возврат результата
    return render_template(
        'result.html',
        production_plan_id=production_plan_id,
        budget=budget,
        profit=profit,
        selected_books=selected_books,
        schedule_details=schedule_details,
        total_days = ceil(total_days_max)
        )

def calculate_budget_with_time_limit(production_plan_id, production_plans, books, machines, budget):
    
    books, machines, production_plans = fetch_books_and_machines()
    plan = production_plans.get(production_plan_id)
    if not plan:
        return f"<h1>Production plan with ID {production_plan_id} not found.</h1>"

    # First, fill in the budget for each book considering the minimum amount
    selected_books = []
    total_cost = Decimal(0)  # Use Decimal for precise calculations
    remaining_budget = budget

    # Sort books by profit_per_minute priority (descending)
    sorted_books = sorted(plan.books, key=lambda b: b.profit_per_minute, reverse=True)

    # 1. First, add the minimum amount of each book if the budget allows
    for book in sorted_books:
        min_cost = Decimal(book.production_cost) * book.min_amount  # Cost of minimum amount of book

        if remaining_budget >= min_cost:  # Check if we can run minimum amount
            selected_books.append((book, book.min_amount))
            remaining_budget -= min_cost  # Reduce remaining budget
        else:
            # If there is no budget for the minimum amount of the book, skip this book
            continue

    # 2. After that, if there is room in the budget, add additional books by profitability
    for book in sorted_books:
        if any(selected_book[0] == book for selected_book in selected_books):  # If book has already been added
            already_added_amount = next(amount for selected_book, amount in selected_books if selected_book == book)
            max_possible_amount = book.max_amount - already_added_amount

            if max_possible_amount > 0:  # Only proceed if there is room to add more
                # Check if there is enough budget for the maximum amount
                max_cost = Decimal(book.production_cost) * max_possible_amount  # Cost of maximum amount of book

                if remaining_budget >= max_cost:  # If there is enough budget for the maximum amount
                    selected_books = [(selected_book, amount + max_possible_amount) if selected_book == book else (selected_book, amount) for selected_book, amount in selected_books]
                    remaining_budget -= max_cost  # Reduce remaining budget
                else:
                    # If there is not enough budget, add as much as we can
                    possible_amount = remaining_budget // Decimal(book.production_cost)
                    if possible_amount > 0:
                        selected_books = [(selected_book, amount + possible_amount) if selected_book == book else (selected_book, amount) for selected_book, amount in selected_books]
                        remaining_budget -= possible_amount * Decimal(book.production_cost)

    # Calculate time and profit for the selected books
    machine_availability = {machine.hardware_id: 0 for machine in machines.values()}
    schedule_details = []
    profit = Decimal(0)  # Use Decimal for precise calculations
    for book, amount in selected_books:
        book_start_time = 0
        for hardware_id, production_time in book.hardware_sequence:
            available_at = max(book_start_time, machine_availability[hardware_id])
            start_time = available_at
            finish_time = start_time + production_time * amount
            schedule_details.append({
                'book_name': book.name,
                'hardware_name': machines[hardware_id].name,
                'start_time': start_time,
                'finish_time': finish_time,
                'production_time': production_time * amount
            })
            machine_availability[hardware_id] = finish_time
            book_start_time = finish_time
        profit += (book.selling_price - book.production_cost) * amount
    total_days_max = finish_time/60/24
    # Pass data to the result
    return(
        budget,
        profit,
        selected_books,
        schedule_details,
        total_days_max
    )

@app.route('/completed_result/<int:production_plan_id>/<int:budget>', methods=['POST','GET'])
@login_required
def completed_result(production_plan_id, budget):
    
    books, machines, production_plans = fetch_books_and_machines()
    budget1,profit,selected_books,schedule_details,total_days_max = calculate_budget_with_time_limit(production_plan_id, production_plans, books, machines, budget)
    return render_template(
        'result.html',
        production_plan_id=production_plan_id,
        budget=budget1,
        profit=profit,
        selected_books=selected_books,
        schedule_details=schedule_details,
        total_days = ceil(total_days_max),
        completed = 2
        )
def optimize_budget(budget, max_budget, production_plans, production_plan_id):

    # Получаем данные о планах, книгах и машинах
    books, machines, production_plans = fetch_books_and_machines()

    plan = production_plans.get(production_plan_id)
    if not plan:
        return f"<h1>Production plan with ID {production_plan_id} not found.</h1>"

    best_budget=budget;
    koef = 0
    bestkoef = 0
    while budget < max_budget:
        print(budget, '$')
        budget1, profit, selected_books, schedule_details, total_days_max = calculate_budget_with_time_limit(
            production_plan_id, production_plans, books, machines, budget)
        print("Koef", profit/budget)
        if profit/budget > koef:
            koef = profit/budget
            bestkoef = koef
            best_budget = budget
        if budget * Decimal(1.01) <= max_budget:
            budget = budget * Decimal(1.01)
        else:
            budget = max_budget
    #print("BestKoef",bestkoef)
    #print("BestBudget",best_budget)
    return round(best_budget)

def get_user_role(user_id):
    if user_id == 1:
        return 'admin'
    elif user_id == 2:
        return 'operator'
    elif user_id == 3:
        return 'manager'
    else:
        return 'unknown'  # На случай, если id не соответствует ни одной роли

if __name__ == '__main__':
    # Очищаем сессии при запуске
    session_dir = app.config['SESSION_FILE_DIR']
    if os.path.exists(session_dir):
        for f in os.listdir(session_dir):
            file_path = os.path.join(session_dir, f)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f'Error deleting session file: {e}')
    
    # Создаем директорию для сессий, если её нет
    os.makedirs(session_dir, exist_ok=True)
    
    app.run(port=8080, debug=True)
    
