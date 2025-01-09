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
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password != confirm_password:
            return 'Passwords do not match.'
        if len(password) < 8:
            return 'Password must be at least 8 characters long.'

        hashed_password = generate_password_hash(password)
        cursor = mysql.connection.cursor()
        try:
            cursor.execute("INSERT INTO users (username, password, production_id) VALUES (%s, %s, %s)", (username, hashed_password, 1))
            mysql.connection.commit()
            session['username'] = username  # Добавляем пользователя в сессию
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

@app.route('/optimize_books', methods=['GET', 'POST'])
@login_required


def optimize_books():
    cursor = mysql.connection.cursor()

    try:
        # Получаем бюджет и общее время из формы
        budget = float(request.form.get('budget', 0))
        total_days = int(request.form.get('total_days', 0))
        total_time_available = total_days * 8 * 60  # Преобразуем дни в минуты (например, 8-часовой рабочий день)

        # Fetch necessary data from the database
        cursor.execute("SELECT book_id, selling_price FROM books")
        books = cursor.fetchall()

        # Преобразуем кортежи в словари
        books = [
            {
                'book_id': book[0],
                'selling_price': book[1]
            }
            for book in books
        ]

        cursor.execute("SELECT hardware_id, capacity FROM hardwares")
        hardwares = cursor.fetchall()

        cursor.execute(
            "SELECT book_id, hardware_id, production_time_in_hours, order_in_queue "
            "FROM book_hardwares ORDER BY order_in_queue"
        )
        book_hardwares = cursor.fetchall()

        # Prepare data structures
        book_prices = {book['book_id']: book['selling_price'] for book in books}
        hardware_capacity = {hw[0]: hw[1] for hw in hardwares}
        hardware_usage = defaultdict(list)  # To track hardware usage

        # Organize book-hardware mappings
        book_to_hardwares = defaultdict(list)
        for bh in book_hardwares:
            book_to_hardwares[bh[0]].append({
                'hardware_id': bh[1],
                'production_time': bh[2],
                'order': bh[3]
            })

        # Priority queue to simulate parallel machine operation
        hardware_queue = [(0, hw_id) for hw_id in hardware_capacity.keys()]  # (end_time, hardware_id)
        heapq.heapify(hardware_queue)

        total_profit = 0
        total_production_time = 0  # Общее время производства
        production_log = []

        for book_id, hardwares in book_to_hardwares.items():
            hardwares = sorted(hardwares, key=lambda x: x['order'])
            book_start_time = 0

            for hw in hardwares:
                hw_id = hw['hardware_id']
                production_time = hw['production_time']

                # Find the next available time slot for the required hardware
                while hardware_queue:
                    end_time, current_hw_id = heapq.heappop(hardware_queue)
                    if current_hw_id == hw_id:
                        break

                # Calculate start and end time for this hardware operation
                start_time = max(book_start_time, end_time)
                end_time = start_time + production_time

                # Log the usage
                hardware_usage[hw_id].append({
                    'book_id': book_id,
                    'start_time': start_time,
                    'end_time': end_time
                })

                # Push the hardware back into the queue with its updated end time
                heapq.heappush(hardware_queue, (end_time, hw_id))

                # Update book_start_time for the next operation in sequence
                book_start_time = end_time

            # Calculate profit for this book
            total_profit += book_prices.get(book_id, 0)  # Use .get() to avoid KeyError
            production_log.append({
                'book_id': book_id,
                'profit': book_prices.get(book_id, 0)
            })

            # Обновляем общее время производства
            total_production_time += sum(hw['production_time'] for hw in hardwares)

        # Проверка на укладывание в бюджет и время
        if total_profit > budget:
            print("Превышен бюджет!")
            return render_template('optimize_books.html', books=books, min_budget=0, min_time=0, error="Превышен бюджет!")

        if total_production_time > total_time_available:
            print("Превышено доступное время!")
            return render_template('optimize_books.html', books=books, min_budget=0, min_time=0, error="Превышено доступное время!")

        # Prepare output summary
        hardware_summary = {
            hw_id: [
                {
                    'book_id': log['book_id'],
                    'start_time': log['start_time'],
                    'end_time': log['end_time']
                } for log in logs
            ] for hw_id, logs in hardware_usage.items()
        }

        summary = {
            'total_profit': total_profit,
            'hardware_usage': hardware_summary,
            'production_log': production_log
        }

        # Print the summary instead of returning
        print("Total Profit:", summary['total_profit'])
        print("\nHardware Usage:")
        for hw_id, logs in hardware_summary.items():
            print(f"Hardware {hw_id}:")
            for log in logs:
                print(f"  Book ID: {log['book_id']}, Start Time: {log['start_time']}, End Time: {log['end_time']}")
        print("\nProduction Log:")
        for log in production_log:
            print(f"Book ID: {log['book_id']}, Profit: {log['profit']}")

        return render_template('optimize_books.html', books=books, min_budget=0, min_time=0)

    except Exception as e:
        print(f"Error occurred: {e}")
        return render_template('optimize_books.html', books=[], min_budget=0, min_time=0)  # Возвращаем пустой список книг в случае ошибки
    finally:
        cursor.close()  # Ensure the cursor is closed


@app.route('/books', methods=['GET'])
@login_required
def books():
    cursor = mysql.connection.cursor()

    # Fetch all books from the database
    cursor.execute("SELECT b.book_id, b.name, b.selling_price, SUM(bh.production_time_in_hours), SUM(m.cost_per_piece * bm.material_quantity) AS total_material_cost FROM books b LEFT JOIN book_hardwares bh ON b.book_id = bh.book_id LEFT JOIN book_materials bm ON b.book_id = bm.book_id LEFT JOIN materials m ON bm.material_id = m.material_id GROUP BY b.book_id, b.name, b.selling_price;")
    books_list = cursor.fetchall()
    # You can now pass these data to your template or further processing
    books = []
    for book in books_list:
        books.append({
            'id': book[0] if book[0] is not None else 0,  # Default value is 0 if None
            'name': book[1] if book[1] is not None else 'Unknown',  # Default value is 'Unknown' if None
            'selling_price': book[2] if book[2] is not None else 0.0,  # Default value is 0.0 if None
            'production_time': book[3] if book[3] is not None else 0.0,  # Default value is 0.0 if None
            'total_material_cost': book[4] if book[4] is not None else 0.0  # Default value is 0.0 if None
        })

    return render_template('books.html', books=books)

@app.route('/edit_book/<book_id>', methods=['GET', 'POST'])
@login_required
def edit_book(book_id):
    cursor = mysql.connection.cursor()

    # if POST, update
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        selling_price = request.form['selling_price']


        cursor.execute("""
            UPDATE books
            SET  name = %s, description = %s, selling_price = %s
            WHERE book_id = %s;
        """, (name, description,selling_price, book_id))

        mysql.connection.commit()
        cursor.close()
        return redirect(url_for('books'))

    # if GET show existing data
    cursor.execute("""SELECT
                      b.book_id, b.name, b.description, b.selling_price
                      FROM books b
                      where b.book_id = %s""", (book_id,))
    books_list1 = cursor.fetchall()
    print(books_list1, book_id)
         # You can now pass these data to your template or further processing
    books1 = []
    for book in books_list1:

        books1.append({
            'id': book[0],
            'name': book[1],
            'description': book[2],
            'selling_price': book[3]
        })
   # cursor.close()
    print(books1, book_id)
    return render_template('edit_book.html', book=books1[0])

@app.route('/delete_book/<book_id>', methods=['GET'])
@login_required
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

        mysql.connection.commit()
        cursor.close()

        return redirect(url_for('books'))

    # Fetch available materials from the database
    cursor.execute("SELECT material_id, name, type FROM materials")
    materials = cursor.fetchall()
    cursor.close()

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
#     grouped_materials = {
#     "Paper": [{"id": 1, "name": "A4 Paper"}, {"id": 2, "name": "A3 Paper"}],
#     "Ink": [{"id": 3, "name": "Black Ink"}, {"id": 4, "name": "Blue Ink"}]
#     }

    return render_template('create_book.html', materials=grouped_materials)



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
        
    cursor.close()
    return render_template('materials.html', materials=materials)

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
    return render_template('employees.html', employees=employees)

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
        
    cursor.close()
    return render_template('machines.html', machines=machines)

@app.route('/create_material', methods=['GET', 'POST'])
@login_required
def create_material():
    if request.method == 'POST':
        name = request.form['name']
        quantity = request.form['quantity']
        cost_per_piece = request.form['cost_per_piece']
        material_type = request.form['type']

        cursor = mysql.connection.cursor()
        cursor.execute("""
            INSERT INTO materials (name, quantity, cost_per_piece, type)
            VALUES (%s, %s, %s, %s)
        """, (name, quantity, cost_per_piece, material_type))
        
        mysql.connection.commit()
        cursor.close()
        return redirect(url_for('materials'))

    return render_template('create_material.html')

@app.route('/edit_material/<int:material_id>', methods=['GET', 'POST'])
@login_required
def edit_material(material_id):
    cursor = mysql.connection.cursor()

    if request.method == 'POST':
        name = request.form['name']
        quantity = request.form['quantity']
        cost_per_piece = request.form['cost_per_piece']
        material_type = request.form['type']

        cursor.execute("""
            UPDATE materials
            SET name = %s, quantity = %s, cost_per_piece = %s, type = %s
            WHERE material_id = %s
        """, (name, quantity, cost_per_piece, material_type, material_id))

        mysql.connection.commit()
        cursor.close()
        return redirect(url_for('materials'))

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
        return render_template('edit_material.html', material=material_data)
    
    return redirect(url_for('materials'))

@app.route('/delete_material/<int:material_id>')
@login_required
def delete_material(material_id):
    cursor = mysql.connection.cursor()
    
    # Проверяем, используется ли материал в книгах
    cursor.execute("""
        SELECT COUNT(*) FROM book_materials 
        WHERE material_id = %s
    """, (material_id,))
    
    if cursor.fetchone()[0] > 0:
        cursor.close()
        return "Cannot delete material as it is used in books", 400
    
    cursor.execute("DELETE FROM materials WHERE material_id = %s", (material_id,))
    mysql.connection.commit()
    cursor.close()
    
    return redirect(url_for('materials'))

@app.route('/create_machine', methods=['GET', 'POST'])
@login_required
def create_machine():
    if request.method == 'POST':
        name = request.form['name']
        machine_type = request.form['type']
        capacity = request.form['capacity']

        cursor = mysql.connection.cursor()
        cursor.execute("""
            INSERT INTO hardwares (name, type, capacity)
            VALUES (%s, %s, %s)
        """, (name, machine_type, capacity))
        
        mysql.connection.commit()
        cursor.close()
        return redirect(url_for('machines'))

    return render_template('create_machine.html')

@app.route('/edit_machine/<int:machine_id>', methods=['GET', 'POST'])
@login_required
def edit_machine(machine_id):
    cursor = mysql.connection.cursor()

    if request.method == 'POST':
        name = request.form['name']
        machine_type = request.form['type']
        capacity = request.form['capacity']

        cursor.execute("""
            UPDATE hardwares
            SET name = %s, type = %s, capacity = %s
            WHERE hardware_id = %s
        """, (name, machine_type, capacity, machine_id))

        mysql.connection.commit()
        cursor.close()
        return redirect(url_for('machines'))

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
        return render_template('edit_machine.html', machine=machine_data)
    
    return redirect(url_for('machines'))

@app.route('/delete_machine/<int:machine_id>', methods=['GET'])
@login_required
def delete_machine(machine_id):
    cursor = mysql.connection.cursor()
    cursor.execute("DELETE FROM hardwares WHERE hardware_id = %s", (machine_id,))
    mysql.connection.commit()
    cursor.close()
    
    return redirect(url_for('machines'))

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
    
