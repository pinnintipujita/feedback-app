from flask import Flask, render_template, request, redirect, session, url_for, g
import psycopg2
import psycopg2.extras
import os

app = Flask(__name__)
app.secret_key = "admintest"  # Required for sessions

# ----------------- DB Helpers -----------------
DATABASE_URL = os.getenv("DATABASE_URL")  # Add this in Vercel environment variables

def get_db():
    if "db" not in g:
        g.db = psycopg2.connect(DATABASE_URL, sslmode="require")
    return g.db

@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    cur = db.cursor()
    # feedback table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            message TEXT NOT NULL,
            category TEXT,
            selected_name TEXT
        )
    """)
    # users table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            fullname TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            blocked BOOLEAN DEFAULT FALSE
        )
    """)
    db.commit()
    cur.close()

# ----------------- Routes -----------------
@app.route("/")
def home():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        db = get_db()
        cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT * FROM users WHERE username=%s AND password=%s", (username, password))
        user = cur.fetchone()
        cur.close()

        if user:
            if user["blocked"]:
                error = "🚫 Your account has been blocked. Contact admin."
            else:
                session["user"] = user["id"]
                return redirect(url_for("collection"))
        else:
            error = "❌ Invalid credentials"

    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/collection")
def collection():
    if "user" not in session:
        return redirect(url_for("login"))

    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM feedback ORDER BY id DESC")
    feedbacks = cur.fetchall()
    cur.close()

    return render_template("index.html", feedbacks=feedbacks)

@app.route("/feedback", methods=["GET", "POST"])
def feedback():
    if "user" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        name = request.form["name"]
        message = request.form["message"]
        category = request.form.get("category")
        selected_name = request.form.get("selected_name")

        db = get_db()
        cur = db.cursor()
        cur.execute(
            "INSERT INTO feedback (name, message, category, selected_name) VALUES (%s, %s, %s, %s)",
            (name, message, category, selected_name),
        )
        db.commit()
        cur.close()

        return redirect(url_for("collection"))

    return render_template("feedback.html")

@app.route("/admin")
def admin():
    if "user" not in session:
        return redirect(url_for("login"))

    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM users ORDER BY id ASC")
    users = cur.fetchall()
    cur.close()

    return render_template("admin.html", users=users)

@app.route("/block_user/<int:user_id>")
def block_user(user_id):
    db = get_db()
    cur = db.cursor()
    cur.execute("UPDATE users SET blocked = NOT blocked WHERE id=%s", (user_id,))
    db.commit()
    cur.close()
    return redirect(url_for("admin"))

@app.route("/delete_user/<int:user_id>")
def delete_user(user_id):
    db = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM users WHERE id=%s", (user_id,))
    db.commit()
    cur.close()
    return redirect(url_for("admin"))

@app.route("/edit_user/<int:user_id>", methods=["GET", "POST"])
def edit_user(user_id):
    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)

    if request.method == "POST":
        fullname = request.form["fullname"]
        username = request.form["username"]
        email = request.form["email"]

        cur.execute(
            "UPDATE users SET fullname=%s, username=%s, email=%s WHERE id=%s",
            (fullname, username, email, user_id),
        )
        db.commit()
        cur.close()
        return redirect(url_for("admin"))

    cur.execute("SELECT * FROM users WHERE id=%s", (user_id,))
    user = cur.fetchone()
    cur.close()

    return render_template("edit_user.html", user=user)

# ----------------- Run Init -----------------
with app.app_context():
    init_db()

# Required for Vercel
if __name__ == "__main__":
    app.run(debug=True)
