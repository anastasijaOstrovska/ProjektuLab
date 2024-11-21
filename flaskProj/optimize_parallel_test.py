from decimal import Decimal

def optimize_production_with_dependencies(books, machines, total_days, budget):
    # Calculate total available time for all machines in minutes
    total_minutes = total_days * 8 * 60  

    # Initialize machine availability (time when each machine is next available)
    machine_availability = {machine['id']: 0 for machine in machines}

    # Initialize the result structure to store optimization results
    result = {
        'quantities': {book['name']: 0 for book in books},  # Number of each book produced
        'gross_income': Decimal(0.0),  # Total revenue from selling books
        'net_income': Decimal(0.0),  # Profit after deducting material costs
        'total_books': 0,  # Total books produced
        'machine_stats': {machine['id']: {'time_worked': 0, 'task_order': []} for machine in machines}  # Machine statistics
    }

    # Track the completion time of each step in the production sequence for each book
    book_stage_completion = {book['name']: {step['machine']: 0 for step in book['sequence']} for book in books}

    # Track the remaining budget
    remaining_budget = budget

    # Sort books by profit per book (descending order). Greedy approach prioritizes most profitable books.
    books = sorted(books, key=lambda x: (x['selling_price'] - x['material_cost']), reverse=True)

    # Iterate over each book to determine production
    for book in books:
        # Calculate the maximum number of books that can be produced given the budget and max limit
        max_producible = min(
            remaining_budget // book['material_cost'],  # Budget constraint
            book['max_books']  # Maximum allowed production
        )
        # If the maximum producible quantity is below the minimum required, skip this book
        if max_producible < book['min_books']:
            continue

        # Set the quantity to produce as the maximum producible
        quantity = max_producible

        # Process each step in the production sequence for this book
        for step in book['sequence']:
            machine_id = step['machine']  # Machine used for this step
            time_per_book = step['time'] * 60  # Convert time per book to minutes
            total_time = quantity * time_per_book  # Total time required for this step

            # Determine when the machine can start work
            # It can start only when:
            # 1. The machine becomes available
            # 2. The previous step for this book is complete
            start_time = max(machine_availability[machine_id], max(book_stage_completion[book['name']].values()))
            finish_time = start_time + total_time  # Calculate the finish time for this step

            # Update machine availability and completion time for this book's step
            machine_availability[machine_id] = finish_time
            book_stage_completion[book['name']][machine_id] = finish_time

            # Update machine statistics
            result['machine_stats'][machine_id]['time_worked'] += total_time  # Total time machine was busy
            result['machine_stats'][machine_id]['task_order'].append(
                f"Processed {quantity} of {book['name']} (Time: {start_time}-{finish_time} mins)"
            )

        # Update overall production results
        result['quantities'][book['name']] += quantity  # Add to the count of this book
        result['total_books'] += quantity  # Add to the total book count
        result['gross_income'] += Decimal(quantity) * book['selling_price']  # Add to gross income
        result['net_income'] += Decimal(quantity) * (book['selling_price'] - book['material_cost'])  # Add to net income
        remaining_budget -= quantity * book['material_cost']  # Deduct material cost from the budget

    return result


# Input data: books and their production sequences
books = [
    {
        'name': 'Book A',
        'material_cost': 10,  # Material cost per book
        'selling_price': 20,  # Selling price per book
        'min_books': 50,  # Minimum books that must be produced
        'max_books': 200,  # Maximum books that can be produced
        'sequence': [  # Production sequence: each step specifies the machine and time required
            {'machine': 0, 'time': 1},  # Machine 0: 1 hour per book
            {'machine': 1, 'time': 1.5},  # Machine 1: 1.5 hours per book
            {'machine': 2, 'time': 0.5}  # Machine 2: 0.5 hours per book
        ]
    },
    {
        'name': 'Book B',
        'material_cost': 15,  # Material cost per book
        'selling_price': 30,  # Selling price per book
        'min_books': 30,  # Minimum books that must be produced
        'max_books': 150,  # Maximum books that can be produced
        'sequence': [
            {'machine': 1, 'time': 2},  # Machine 1: 2 hours per book
            {'machine': 2, 'time': 1}  # Machine 2: 1 hour per book
        ]
    }
]

# Input data: machine specifications
machines = [
    {'id': 0, 'hourly_rate': 10},  # Machine 0 hourly rate
    {'id': 1, 'hourly_rate': 15},  # Machine 1 hourly rate
    {'id': 2, 'hourly_rate': 20}   # Machine 2 hourly rate
]

# Total working days and budget
total_days = 20
budget = 5000

# Run optimization
result = optimize_production_with_dependencies(books, machines, total_days, budget)

# Output results
print("Optimization Results:")
print(f"Total books produced: {result['total_books']}")
print(f"Gross income: {result['gross_income']}")
print(f"Net income: {result['net_income']}")
for machine_id, stats in result['machine_stats'].items():
    print(f"Machine {machine_id}:")
    print(f"  Time worked: {stats['time_worked']} minutes")
    print(f"  Task order:")
    for task in stats['task_order']:
        print(f"    {task}")
