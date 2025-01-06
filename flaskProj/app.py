import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
import optimize
import random
from decimal import Decimal
import math
from functools import wraps
from datetime import timedelta
from flask_session import Session

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
    min_budget = sum(book['min_books'] * book['material_cost'] for book in books)
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
    print("Current session:", session)
    cursor = mysql.connection.cursor()

        # Fetch all books from the database

    cursor.execute("""
    SELECT
        b.book_id as id,
        b.name as book_name,
        b.selling_price,
        cast(sum(m.cost_per_piece*bm.material_quantity) as decimal(10,2)) as total_material_cost,
        ppb.book_amount_min,
        sum(bh.production_time_in_hours) as total_prod_time_in_hours
    FROM books b
    LEFT JOIN book_materials bm ON b.book_id = bm.book_id
    LEFT JOIN materials m ON bm.material_id =m.material_id
    LEFT JOIN production_plan_books ppb ON b.book_id = ppb.book_id
    LEFT JOIN production_plan pp ON ppb.production_plan_id = pp.production_plan_id
    LEFT JOIN book_hardwares bh ON b.book_id =bh.book_id
    LEFT JOIN hardwares h ON bh.hardware_id = h.hardware_id
    WHERE pp.production_plan_id = 1
    GROUP BY b.book_id,b.name,b.selling_price,ppb.book_amount_min,bh.production_time_in_hours
    order by b.name""")


    books_list = cursor.fetchall()
    # You can now pass these data to your template or further processing
    books = []
#     Name
#     Total income(count)
#     Min books quantity
#     Max books quantity (not in database)

    for book in books_list:
        books.append({
        'book_id': book[0] if book[0] is not None else 'N/A',
        'name': book[1] if book[1] is not None else 'Unnamed',
        'selling_price': book[2] if book[2] is not None else Decimal('0.0'),
        'material_cost': book[3] if book[3] is not None else Decimal('0.0'),
        'min_books': book[4] if book[4] is not None else 0,
        'max_books': 100,  # Hardcoded value
        'time_per_book': book[5] if book[5] is not None else Decimal('0.0'),
        'machine' : random.randint(0, 3)
    })
    cursor.close()
    print(books)
#     machines = [
#             {'name': 'Machine 1', 'id': 0},
#             {'name': 'Machine 2', 'id': 1},
#             {'name': 'Machine 3', 'id': 2},
#             {'name': 'Machine 4', 'id': 3},
#     ]
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
    # Count minimal budget here (can be without separate function)
    min_budget = sum(book['material_cost'] * book['min_books'] for book in books)
    min_time = math.ceil(sum(book['time_per_book'] * book['min_books'] for book in books)/8)
    
    if request.method == 'POST':
        budget = float(request.form['budget'])
        total_days = int(request.form['total_days'])

        result = optimize.optimize_production(books, machines, total_days, budget)# Logic of optimization

        return render_template('result.html', result=result, books=books)

    return render_template('optimize_books.html', books=books, min_budget=min_budget, min_time=min_time)


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
    
