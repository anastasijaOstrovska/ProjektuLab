import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
import optimize
import random
from decimal import Decimal
import math

app = Flask(__name__)
load_dotenv('pswd.env')

# Database connection
app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST') 
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB')
app.config['MYSQL_PORT'] = int(os.getenv('MYSQL_PORT'))
app.secret_key = os.getenv('APP_SECRET_KEY')

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
#	    cursor.execute("INSERT INTO users (username, password, production_id) VALUES (%s, %s, %i)", (username, hashed_password, 1))
            cursor.execute("INSERT INTO users (username, password, production_id) VALUES (%s, %s, %s)", (username, hashed_password, 1))
            mysql.connection.commit()
            return redirect(url_for('login'))
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
            session['username'] = username
            return redirect(url_for('optimize_books'))
        return 'Invalid username or password.'
    return render_template('login.html')

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
def optimize_books():
    if 'username' not in session:
        return redirect(url_for('login'))
    cursor = mysql.connection.cursor()

        # Fetch all books from the database

    cursor.execute("""
    SELECT
        b.book_id as id,
        b.name as book_name,
        b.selling_price,
        cast(sum(m.cost_per_piece*bm.material_quantity) as decimal(10,2)) as total_material_cost,
        ppb.book_amount_min,
        ppb.book_amount_max,
        sum(bh.production_time_in_hours) as total_prod_time_in_hours
    FROM books b
    LEFT JOIN book_materials bm ON b.book_id = bm.book_id
    LEFT JOIN materials m ON bm.material_id =m.material_id
    LEFT JOIN production_plan_books ppb ON b.book_id = ppb.book_id
    LEFT JOIN production_plan pp ON ppb.production_plan_id = pp.production_plan_id
    LEFT JOIN book_hardwares bh ON b.book_id =bh.book_id
    LEFT JOIN hardwares h ON bh.hardware_id = h.hardware_id
    WHERE pp.production_plan_id = 1
    GROUP BY b.book_id,b.name,b.selling_price,ppb.book_amount_min,ppb.book_amount_max,bh.production_time_in_hours
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
        'max_books': book[5] if book[5] is not None else Decimal('1000.0'),
        'time_per_book': book[6] if book[6] is not None else Decimal('0.0'),
        'machine' : random.randint(0, 3)
    })
    print(books)
    machines = [
            {'name': 'Machine 1', 'id': 0},
            {'name': 'Machine 2', 'id': 1},
            {'name': 'Machine 3', 'id': 2},
            {'name': 'Machine 4', 'id': 3},
    ]
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
# Name
# Selling price
# Total Time of printing
#
# Material total cost
# Material needed + quantity
def books():
    if 'username' not in session:
        return redirect(url_for('login'))
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

@app.route('/edit_opt_param/<book_id>/<production_plan_id>', methods=['GET', 'POST'])
def edit_opt_param(book_id,production_plan_id):
    cursor = mysql.connection.cursor()

    # if POST, update
    if request.method == 'POST':
        min_books = request.form['min_books']
        max_books = request.form['max_books']


        cursor.execute("""
            UPDATE production_plan_books
            SET  book_amount_min = %s, book_amount_max = %s
            WHERE book_id = %s and production_plan_id = %s;
        """, (min_books,max_books, book_id, production_plan_id))

        mysql.connection.commit()
        cursor.close()
        return redirect(url_for('optimize_books'))

    # if GET show existing data
    cursor.execute("""SELECT
                      b.book_id, b.name, ppb.book_amount_min, ppb.book_amount_max, ppb.production_plan_id
                      FROM production_plan_books ppb
                      LEFT JOIN books b ON b.book_id = ppb.book_id
                      where ppb.book_id = %s and ppb.production_plan_id = %s""", (book_id,production_plan_id,))
    books_list1 = cursor.fetchall()
    print(books_list1, book_id)
         # You can now pass these data to your template or further processing
    books1 = []
    for book in books_list1:

        books1.append({
            'id': book[0],
            'name': book[1],
            'min_books': book[2],
            'max_books': book[3],
            'production_plan_id': book[4]
        })
   # cursor.close()
    print(books1, book_id)
    return render_template('edit_opt_param.html', book=books1[0])

@app.route('/delete_book/<book_id>', methods=['GET'])
def delete_book(book_id):
    cursor = mysql.connection.cursor()

    # Delete the book from the database
    cursor.execute("DELETE FROM books WHERE book_id = %s", (book_id,))
    mysql.connection.commit()
    cursor.close()

    # Redirect to the book list page after deletion
    return redirect(url_for('books'))
if __name__ == '__main__':
    app.run(debug=True)
    app.run(port=7295)  # Change the port here (e.g., 8080)
