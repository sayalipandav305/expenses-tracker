from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_bcrypt import Bcrypt
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "supersecret"

bcrypt = Bcrypt(app)

# MongoDB setup
client = MongoClient("mongodb://localhost:27017")
db = client["expenseTracker"]

# ---------------- ROUTES ---------------- #

# Home redirects to login
@app.route("/")
def home():
    return redirect(url_for("login_page"))

# Login page
@app.route("/login_page")
def login_page():
    return render_template("login.html")

# Signup page
@app.route("/signup_page")
def signup_page():
    return render_template("signup.html")

# Signup POST
@app.route("/signup", methods=["POST"])
def signup():
    username = request.form["username"]
    email = request.form["email"]
    password = bcrypt.generate_password_hash(request.form["password"]).decode("utf-8")
    currency = request.form.get("currency", "₹")
    
    db.users.insert_one({
        "username": username,
        "email": email,
        "password": password,
        "budget": 0,
        "currency": currency
    })
    return redirect(url_for("login_page"))

# Login POST
@app.route("/login", methods=["POST"])
def login():
    email = request.form["email"]
    password = request.form["password"]
    user = db.users.find_one({"email": email})

    if user and bcrypt.check_password_hash(user["password"], password):
        session["user_id"] = str(user["_id"])
        session["username"] = user["username"]
        return redirect(url_for("dashboard"))
    return "Invalid credentials! <a href='/login_page'>Try again</a>"

# Logout
@app.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("username", None)
    return redirect(url_for("login_page"))

# Add Expense
@app.route("/add_expense", methods=["POST"])
def add_expense():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    data = {
        "userId": ObjectId(session["user_id"]),
        "amount": float(request.form["amount"]),
        "category": request.form["category"],
        "description": request.form["description"],
        "date": datetime.strptime(request.form["date"], "%Y-%m-%d"),
        "recurring": request.form.get("recurring") == "on",
        "frequency": request.form.get("frequency", ""),
    }
    db.expenses.insert_one(data)
    return redirect(url_for("dashboard"))

# Delete Expense
@app.route("/delete/<id>")
def delete_expense(id):
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    db.expenses.delete_one({"_id": ObjectId(id)})
    return redirect(url_for("dashboard"))

# Dashboard
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    user_id = session["user_id"]
    expenses = list(db.expenses.find({"userId": ObjectId(user_id)}))
    
    # Format expenses
    for exp in expenses:
        exp["_id"] = str(exp["_id"])

    # Summary
    total_expense = sum(exp["amount"] for exp in expenses)
    num_expenses = len(expenses)

    # Category totals
    category_totals = {}
    for exp in expenses:
        category_totals[exp["category"]] = category_totals.get(exp["category"], 0) + exp["amount"]
    if category_totals:
        highest_category = max(category_totals, key=category_totals.get)
        highest_total = category_totals[highest_category]
    else:
        highest_category = "N/A"
        highest_total = 0

    # Budget
    user = db.users.find_one({"_id": ObjectId(user_id)})
    budget = user.get("budget", 0)
    progress_percent = (total_expense / budget * 100) if budget > 0 else 0
    currency = user.get("currency", "₹")

    # Notifications
    notifications = []
    if budget > 0 and total_expense > budget:
        notifications.append({"message": "You have exceeded your budget!"})

    # Example: upcoming recurring expense alert
    upcoming = [exp for exp in expenses if exp.get("recurring")]
    for exp in upcoming:
        next_date = exp["date"] + timedelta(days=7 if exp["frequency"]=="weekly" else 30)
        if next_date.date() <= datetime.now().date() + timedelta(days=3):
            notifications.append({"message": f"Upcoming recurring expense: {exp['description']} on {next_date.strftime('%Y-%m-%d')}"})

    return render_template(
        "dashboard.html",
        expenses=expenses,
        username=session["username"],
        total_expense=total_expense,
        num_expenses=num_expenses,
        highest_category=highest_category,
        highest_total=highest_total,
        budget=budget,
        progress_percent=progress_percent,
        currency=currency,
        notifications=notifications
    )
# Totals for Chart.js
@app.route("/totals")
def totals():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    pipeline = [
        {"$match": {"userId": ObjectId(session["user_id"])}},
        {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}}
    ]
    result = list(db.expenses.aggregate(pipeline))
    return jsonify(result)

# Set Budget
@app.route('/set_budget', methods=['POST'])
def set_budget():
    budget = float(request.form['budget'])
    user_id = session['user_id']

    # Save budget in DB (example with MongoDB)
    db.users.update_one({'_id': ObjectId(user_id)}, {'$set': {'budget': budget}})

    flash=('Budget updated!', 'success')
    return redirect(url_for('dashboard'))


if __name__ == "__main__":
    app.run(debug=True)

