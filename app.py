from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response
from flask_bcrypt import Bcrypt
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime, timedelta
import os

app = Flask(__name__)
app.secret_key = "supersecret"
bcrypt = Bcrypt(app)

# ---------------- MongoDB Setup ---------------- #
client = MongoClient("mongodb://localhost:27017/")
db = client["expenseTracker"]

# ---------------- Upload Folder ---------------- #
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ---------------- ROUTES ---------------- #

@app.route("/")
def home():
    return redirect(url_for("login_page"))

@app.route("/login_page")
def login_page():
    return render_template("login.html")

@app.route("/signup_page")
def signup_page():
    return render_template("signup.html")

@app.route("/signup", methods=["POST"])
def signup():
    username = request.form["username"]
    email = request.form["email"]

    # Check for existing email or username
    if db.users.find_one({"email": email}):
        return "Email already registered! <a href='/signup_page'>Try again</a>"
    if db.users.find_one({"username": username}):
        return "Username already taken! <a href='/signup_page'>Try again</a>"

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

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))

# ---------------- Add Expense ---------------- #
@app.route("/add_expense", methods=["POST"])
def add_expense():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    file = request.files.get("receipt")
    filename = None
    if file and file.filename != "":
        filename = f"{datetime.now().timestamp()}_{file.filename}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    data = {
        "userId": ObjectId(session["user_id"]),
        "amount": float(request.form["amount"]),
        "category": request.form["category"],
        "description": request.form["description"],
        "date": datetime.strptime(request.form["date"], "%Y-%m-%d"),
        "recurring": request.form.get("recurring") == "on",
        "frequency": request.form.get("frequency", ""),
        "receipt": filename
    }
    db.expenses.insert_one(data)
    return redirect(url_for("dashboard"))

# ---------------- Delete Expense ---------------- #
@app.route("/delete/<id>", methods=["DELETE"])
def delete_expense(id):
    if "user_id" not in session:
        return jsonify({"success": False, "message": "Not logged in"}), 401

    result = db.expenses.delete_one({
        "_id": ObjectId(id),
        "userId": ObjectId(session["user_id"])
    })
    if result.deleted_count:
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "Expense not found"})

# ---------------- Dashboard ---------------- #
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    user_id = session["user_id"]
    search = request.args.get("search", "")
    category = request.args.get("category", "")
    from_date = request.args.get("from", "")
    to_date = request.args.get("to", "")

    query = {"userId": ObjectId(user_id)}
    if search:
        query["description"] = {"$regex": search, "$options": "i"}
    if category:
        query["category"] = category
    if from_date or to_date:
        query["date"] = {}
        if from_date:
            query["date"]["$gte"] = datetime.strptime(from_date, "%Y-%m-%d")
        if to_date:
            query["date"]["$lte"] = datetime.strptime(to_date, "%Y-%m-%d")

    expenses = list(db.expenses.find(query))
    for exp in expenses:
        exp["_id"] = str(exp["_id"])

    total_expense = sum(exp["amount"] for exp in expenses)
    num_expenses = len(expenses)

    # Category totals
    category_totals = {}
    for exp in expenses:
        category_totals[exp["category"]] = category_totals.get(exp["category"], 0) + exp["amount"]
    highest_category = max(category_totals, key=category_totals.get) if category_totals else "N/A"
    highest_total = category_totals.get(highest_category, 0)

    user = db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
     session.clear()
     return redirect(url_for("login_page"))

    budget = user.get("budget", 0)
    currency = user.get("currency", "₹")


    notifications = []
    if budget > 0:
        if total_expense > budget:
            notifications.append({"message": "You have exceeded your budget!"})
        elif total_expense > 0.9 * budget:
            notifications.append({"message": "You are nearing your budget limit!"})

    # Recurring expenses alert
    upcoming = [exp for exp in expenses if exp.get("recurring")]
    for exp in upcoming:
        next_date = exp["date"] + timedelta(days=7 if exp["frequency"]=="weekly" else 30)
        days_left = (next_date.date() - datetime.now().date()).days
        if 0 <= days_left <= 3:
            notifications.append({"message": f"Upcoming recurring expense: {exp['description']} in {days_left} days"})

    return render_template(
        "dashboard.html",
        expenses=expenses,
        username=session["username"],
        total_expense=total_expense,
        num_expenses=num_expenses,
        highest_category=highest_category,
        highest_total=highest_total,
        budget=budget,
        currency=currency,
        notifications=notifications,
        search=search,
        category=category,
        from_date=from_date,
        to_date=to_date
    )

# ---------------- Chart Data ---------------- #
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

# ---------------- Set Budget ---------------- #
@app.route('/set_budget', methods=['POST'])
def set_budget():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    budget = float(request.form['budget'])
    user_id = session['user_id']
    db.users.update_one({'_id': ObjectId(user_id)}, {'$set': {'budget': budget}})
    return redirect(url_for('dashboard'))

# ---------------- Export CSV ---------------- #
@app.route('/export_csv')
def export_csv():
    if "user_id" not in session:
        return redirect(url_for("login_page"))

    expenses = db.expenses.find({"userId": ObjectId(session["user_id"])})

    def generate():
        yield "Category,Amount,Description,Date\n"
        for exp in expenses:
            yield f"{exp['category']},{exp['amount']},{exp['description']},{exp['date'].strftime('%Y-%m-%d')}\n"

    return Response(generate(), mimetype='text/csv',
                    headers={"Content-Disposition": "attachment;filename=expenses.csv"})

# ---------------- Run App ---------------- #
if __name__ == "__main__":
    app.run(debug=True)
