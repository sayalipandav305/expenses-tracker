from pymongo import MongoClient
from datetime import datetime

# Connect to MongoDB
client = MongoClient("mongodb://localhost:27017/")
db = client.expense_db

# Sample expense
expense = {
    "amount": 100,
    "category": "Food",
    "description": "Pizza",
    "date": datetime.now(),
    "username": "sayali"
}

# Insert into MongoDB
db.expenses.insert_one(expense)
print("Expense added!")

# Optional: Show all expenses
for exp in db.expenses.find():
    print(exp)
