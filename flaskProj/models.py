class Machine:
    def __init__(self, hardware_id, name, type, capacity):
        self.hardware_id = hardware_id
        self.name = name
        self.type = type
        self.capacity = capacity
        self.available_at = 0  # When the machine will be free (in minutes)

    def __repr__(self):
        return f"{self.name} (ID: {self.hardware_id}, Capacity: {self.capacity}, Available at: {self.available_at})"

    def __lt__(self, other):
        return self.available_at < other.available_at

class Book:
    def __init__(self, book_id, name, selling_price, hardware_sequence):
        self.book_id = book_id
        self.name = name
        self.selling_price = selling_price
        self.hardware_sequence = hardware_sequence  # List (hardware_id, production_time)
        self.production_time = 0  # Now in minutes
        self.production_count = 0
        self.production_cost = 0  # Cost of book production
        self.profit_per_minute = 0  # Profit per minute of production

    def calculate_profit_per_minute(self):
        if self.production_time > 0:
            self.profit_per_minute = (self.selling_price - self.production_cost) / self.production_time

    def __repr__(self):
        return (f"Book {self.name} (ID: {self.book_id}, Price: {self.selling_price}, Production Cost: {self.production_cost}, "
                f"Production Time: {self.production_time} minutes, Profit/Minute: {self.profit_per_minute:.2f}), Min Amount: {self.min_amount}, Max Amount: {self.max_amount}")
    
class ProductionPlan:
    def __init__(self, production_plan_id, production_plan_name, operator_id, operator_name, time_limit_in_days,budget,profit,status):
        self.production_plan_id = production_plan_id
        self.production_plan_name = production_plan_name
        self.operator_id = operator_id
        self.operator_name = operator_name
        self.time_limit_in_days = time_limit_in_days
        self.books = []
        self.budget = budget
        self.profit = profit
        self.status = status
        self.min_amount = []
        self.max_amount = []

    def calculate_budget(self, books):
        min_budget = sum(book.production_cost * self.min_amount[self.books.index(book)] for book in self.books)
        max_budget = sum(book.production_cost * self.max_amount[self.books.index(book)] for book in self.books)
        return min_budget, max_budget

    def __repr__(self):
        return (f"Production Plan {self.production_plan_id} (Operator ID: {self.operator_id}, "
                f"Time Limit: {self.time_limit_in_days} days, Books: {len(self.books)}), Status: {self.status}")
    def get_plan_status(self):
        return self.status