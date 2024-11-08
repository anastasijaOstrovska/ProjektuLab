import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
import optimize  # Импортирует файл с оптимизацией, надеюсь найдёт его в брэнче

app = Flask(__name__)
load_dotenv('pswd.env')  # Загружает пароль из энв файла (помнняйте пароль потом в этом файле как база будет!)

# Настройка подключения к базе данных
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD')
app.config['MYSQL_DB'] = 'projlab'
app.secret_key = 'supersecretkey'

mysql = MySQL(app)

@app.route('/')
def home():
    return render_template('home.html')

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
            cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s)", (username, hashed_password))
            mysql.connection.commit()
            return redirect(url_for('login'))
        except:
            return 'User already exists.'
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
            session['username'] = username
            return redirect(url_for('optimize_books'))
        return 'Invalid username or password.'
    return render_template('login.html')

def calculate_min_budget(books):
    """
    Рассчитать минимальный бюджет как сумму минимального количества книг * стоимость производства каждой книги.
    """
    min_budget = sum(book['min_books'] * book['material_cost'] for book in books)
    return min_budget

def calculate_days_needed(books, is_max):
    total_time = 0  # Время в часах
    for book in books:
        quantity = book['max_books'] if is_max else book['min_books']
        total_time += quantity * book['time_per_book']
    return total_time / 8  # Переводим в дни (8 часов в день если рабочий день считаем)

@app.route('/optimize_books', methods=['GET', 'POST'])
def optimize_books():
    if 'username' not in session:
        return redirect(url_for('login'))

    # Пример параметров для книг и машин (пока база не подключена, потом поменять!!!!!)
    books = [
        {'name': 'Book 1', 'selling_price': 20.0, 'material_cost': 5.0, 'min_books': 10, 'max_books': 100, 'machine': 0, 'time_per_book': 1},
        {'name': 'Book 2', 'selling_price': 25.0, 'material_cost': 7.0, 'min_books': 15, 'max_books': 150, 'machine': 1, 'time_per_book': 0.7},
        {'name': 'Book 3', 'selling_price': 22.0, 'material_cost': 6.0, 'min_books': 20, 'max_books': 200, 'machine': 2, 'time_per_book': 1.2},
        {'name': 'Book 4', 'selling_price': 18.0, 'material_cost': 4.5, 'min_books': 25, 'max_books': 250, 'machine': 3, 'time_per_book': 0.9},
        {'name': 'Book 5', 'selling_price': 30.0, 'material_cost': 10.0, 'min_books': 5, 'max_books': 50, 'machine': 0, 'time_per_book': 1.5},
        {'name': 'Book 6', 'selling_price': 28.0, 'material_cost': 8.0, 'min_books': 30, 'max_books': 300, 'machine': 1, 'time_per_book': 0.8},
        {'name': 'Book 7', 'selling_price': 35.0, 'material_cost': 12.0, 'min_books': 12, 'max_books': 120, 'machine': 2, 'time_per_book': 1.1},
        {'name': 'Book 8', 'selling_price': 40.0, 'material_cost': 15.0, 'min_books': 10, 'max_books': 100, 'machine': 3, 'time_per_book': 1.3},
        {'name': 'Book 9', 'selling_price': 22.0, 'material_cost': 6.5, 'min_books': 15, 'max_books': 150, 'machine': 0, 'time_per_book': 0.9},
        {'name': 'Book 10', 'selling_price': 45.0, 'material_cost': 20.0, 'min_books': 8, 'max_books': 80, 'machine': 1, 'time_per_book': 2.0},
    ]

    machines = [
        {'name': 'Machine 1', 'id': 0},
        {'name': 'Machine 2', 'id': 1},
        {'name': 'Machine 3', 'id': 2},
        {'name': 'Machine 4', 'id': 3},
    ]

    # Рассчитываем минимальный бюджет тут, хотя можно и без отдельной функции
    min_budget = calculate_min_budget(books)
    max_budget = sum(book['material_cost'] * book['max_books'] for book in books)
    
    if request.method == 'POST':
        budget = float(request.form['budget'])
        total_days = int(request.form['total_days'])

        result = optimize.optimize_production(books, machines, total_days, budget)# Логика оптимизации здесь, из того файла второго

        return render_template('result.html', result=result, books=books)

    return render_template('optimize_books.html', books=books, min_budget=min_budget, max_budget=max_budget)




if __name__ == '__main__':
    app.run(debug=True)
