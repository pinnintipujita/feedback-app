import os
import psycopg2
import psycopg2.extras
from flask import Flask, render_template, request, redirect, session, url_for, g

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "admintest")

# ----------------- Database Config -----------------
DATABASE_URL = os.getenv(
    "SUPABASE_DB_URL",
    "postgresql://postgres:Pujita123Pujita@db.njtgheclmepthxfxfroh.supabase.co:5432/postgres"
)

def get_db():
    """Connect to PostgreSQL (Supabase)"""
    if "db" not in g:
        try:
            g.db = psycopg2.connect(DATABASE_URL, sslmode="require")
        except Exception as e:
            print("❌ Database connection error:", e)
            raise
    return g.db

@app.teardown_appcontext
def close_db(error):
    """Close DB connection"""
    db = g.pop("db", None)
    if db is not None:
        db.close()

# ----------------- Routes -----------------
@app.route("/")
def home():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        db = get_db()
        cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(
            "SELECT * FROM users WHERE username=%s AND password=%s",
            (username, password),
        )
        user = cur.fetchone()
        cur.close()

        if user:
            if user["is_blocked"]:
                error = "🚫 Your account has been blocked. Contact admin."
            else:
                session["user"] = user["id"]
                return redirect(url_for("collection"))
        else:
            error = "❌ Invalid credentials"

    return render_template("admin_login.html", error=error)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        db = get_db()
        cur = db.cursor()
        cur.execute(
            "INSERT INTO users (username, password, is_blocked) VALUES (%s, %s, %s)",
            (username, password, False),
        )
        db.commit()
        cur.close()

        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/collection")
def collection():
    if "user" not in session:
        return redirect(url_for("login"))

    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM feedback ORDER BY id DESC")
    feedbacks = cur.fetchall()
    cur.close()

    return render_template("collection.html", feedbacks=feedbacks)

@app.route("/feedback", methods=["GET", "POST"])
def feedback():
    if request.method == "POST":
        name = request.form.get("name")
        message = request.form.get("message")

        db = get_db()
        cur = db.cursor()
        cur.execute(
            "INSERT INTO feedback (name, message) VALUES (%s, %s)", (name, message)
        )
        db.commit()
        cur.close()

        return render_template("success.html")

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

    return render_template("admin_dashboard.html", users=users)

@app.route("/admin/userview")
def admin_userview():
    if "user" not in session:
        return redirect(url_for("login"))

    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM users ORDER BY id ASC")
    users = cur.fetchall()
    cur.close()

    return render_template("admin_userview.html", users=users)

@app.route("/edit_user/<int:user_id>", methods=["GET", "POST"])
def edit_user(user_id):
    if "user" not in session:
        return redirect(url_for("login"))

    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)

    if request.method == "POST":
        is_blocked = request.form.get("is_blocked") == "on"
        cur.execute(
            "UPDATE users SET is_blocked=%s WHERE id=%s", (is_blocked, user_id)
        )
        db.commit()
        cur.close()
        return redirect(url_for("admin_userview"))

    cur.execute("SELECT * FROM users WHERE id=%s", (user_id,))
    user = cur.fetchone()
    cur.close()
    return render_template("edit_user.html", user=user)

@app.route("/edit_feedback/<int:feedback_id>", methods=["GET", "POST"])
def edit_feedback(feedback_id):
    if "user" not in session:
        return redirect(url_for("login"))

    db = get_db()
    cur = db.cursor(cursor_factory=psycopg2.extras.DictCursor)

    if request.method == "POST":
        message = request.form.get("message")
        cur.execute(
            "UPDATE feedback SET message=%s WHERE id=%s", (message, feedback_id)
        )
        db.commit()
        cur.close()
        return redirect(url_for("collection"))

    cur.execute("SELECT * FROM feedback WHERE id=%s", (feedback_id,))
    feedback = cur.fetchone()
    cur.close()
    return render_template("edit_feedback.html", feedback=feedback)

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))

# ----------------- Run -----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
