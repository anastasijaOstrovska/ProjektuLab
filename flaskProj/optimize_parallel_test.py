from decimal import Decimal

def optimize_production_with_dependencies(books, machines, total_days, budget):
    # Total available time for all machines in minutes
    total_minutes = total_days * 8 * 60

    # Initialize machine availability
    machine_availability = {machine['id']: 0 for machine in machines}

    # Result structure
    result = {
        'quantities': {book['name']: 0 for book in books},
        'gross_income': Decimal(0.0),
        'net_income': Decimal(0.0),
        'total_books': 0,
        'machine_stats': {machine['id']: {'time_worked': 0, 'task_order': []} for machine in machines},
    }

    # Remaining budget
    remaining_budget = Decimal(budget)

    # Sort books by profitability
    books = sorted(books, key=lambda x: (x['selling_price'] - x['material_cost']), reverse=True)

    # Process books
    for book in books:
        quantity = 0

        while (
            remaining_budget >= book['material_cost'] and
            result['quantities'][book['name']] < book['max_books']
        ):
            # Check each step in the production sequence
            sequence = book['sequence']
            book_produced = True

            for step in sequence:
                machine_id = step['machine']
                time_per_book = step['time'] * 60

                # Machine availability and finish time
                start_time = machine_availability[machine_id]
                finish_time = start_time + time_per_book

                if finish_time > total_minutes:
                    book_produced = False
                    break

                # Update machine availability
                machine_availability[machine_id] = finish_time
                result['machine_stats'][machine_id]['time_worked'] += time_per_book
                result['machine_stats'][machine_id]['task_order'].append(
                    f"Processed {book['name']} part on Machine {machine_id} (Time: {start_time}-{finish_time} mins)"
                )

            if book_produced:
                quantity += 1
                remaining_budget -= book['material_cost']
                result['quantities'][book['name']] += 1
                result['total_books'] += 1
                result['gross_income'] += Decimal(book['selling_price'])
                result['net_income'] += Decimal(book['selling_price'] - book['material_cost'])

                if quantity < book['min_books']:
                    break

    return result