from scipy.optimize import linprog

def optimize_production(books, machines, total_days, budget):
    total_minutes = total_days * 8 * 60  # Время в минутах (8 часов в день)
    print(f"Total available minutes: {total_minutes}")
    print(f"Budget: {budget}")

    result = {
        'quantities': [],
        'gross_income': 0.0,
        'net_income': 0.0,
        'total_books': 0,
        'machine_stats': {machine['id']: {'time_worked': 0, 'produced_books': {book['name']: 0 for book in books if book['machine'] == machine['id']}} for machine in machines}
    }

    # Вычисляет прибыль для каждой книги
    c = [-(book['selling_price'] - book['material_cost']) for book in books]

    A = []
    b = []

    # Ограничения для минимального и максимального количества книг
    for i, book in enumerate(books):
        A.append([1 if j == i else 0 for j in range(len(books))])
        b.append(book['max_books'])
        A.append([-1 if j == i else 0 for j in range(len(books))])
        b.append(-book['min_books'])

    # Ограничения на время для каждой машины
    machine_times = [0] * len(machines)
    for i, book in enumerate(books):
        machine_times[book['machine']] += book['time_per_book'] * 60  # Переводим часы в минуты

    for machine_id in range(len(machines)):
        A.append([machine_times[machine_id] if book['machine'] == machine_id else 0 for book in books])
        b.append(total_minutes)

    # Ограничение на бюджет
    A.append([book['material_cost'] for book in books])
    b.append(budget)

    bounds = [(book['min_books'], book['max_books']) for book in books]
    res = linprog(c, A_ub=A, b_ub=b, bounds=bounds, method='highs')

    if res.success:
        print(f"Optimization result: {res.x}")
        for i, book in enumerate(books):
            production_count = int(res.x[i])
            result['quantities'].append(production_count)
            result['total_books'] += production_count
            result['gross_income'] += production_count * book['selling_price']
            result['net_income'] += production_count * (book['selling_price'] - book['material_cost'])

            # Обновление статистики для машин
            machine_id = book['machine']
            time_spent = production_count * book['time_per_book'] * 60  # Переводим часы в минуты
            result['machine_stats'][machine_id]['time_worked'] += time_spent
            result['machine_stats'][machine_id]['produced_books'][book['name']] += production_count
    else:
        # не знаю куда он у нас принтить будет и как мы это увидим
        print("Optimization failed:", res.message)

    return result
