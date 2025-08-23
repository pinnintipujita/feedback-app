import os
import psycopg2
import psycopg2.extras
from flask import Flask, render_template, request, redirect, session, url_for, g

app = Flask(__name__)
# It's crucial to set the secret key from an environment variable for production
app.secret_key = os.environ.get('SECRET_KEY', 'admintest')

# Admin credentials
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'admin123'

# Use environment variable for the database URL for Vercel deployment
DATABASE_URL = os.environ.get('SUPABASE_DATABASE_URL')
if not DATABASE_URL:
    raise RuntimeError("SUPABASE_DATABASE_URL environment variable is not set.")

# ----------------- DB Helpers -----------------
def get_db():
    """
    Establishes a database connection.
    Uses a dictionary cursor for easy access to row data by column name.
    """
    if 'db' not in g:
        g.db = psycopg2.connect(DATABASE_URL)
        # Use DictCursor to mimic sqlite3.Row functionality
        g.db.cursor_factory = psycopg2.extras.DictCursor
    return g.db

@app.teardown_appcontext
def close_db(error=None):
    """Closes the database connection at the end of the request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    """
    Initializes the database schema if tables do not exist.
    Note the PostgreSQL syntax differences (e.g., SERIAL for AUTOINCREMENT, TEXT for NOT NULL).
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            # Create feedback table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS feedback (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    message TEXT NOT NULL,
                    category TEXT,
                    selected_name TEXT
                )
            """)
            # Create users table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    fullname TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    blocked INTEGER DEFAULT 0
                )
            """)
        conn.commit()

def ensure_blocked_column():
    """
    Checks if the 'blocked' column exists and adds it if not.
    This is for initial setup on a new database.
    """
    db = get_db()
    try:
        with db.cursor() as cur:
            cur.execute("SELECT blocked FROM users LIMIT 1")
    except psycopg2.errors.UndefinedColumn:
        print("Adding 'blocked' column to users table...")
        with db.cursor() as cur:
            cur.execute("ALTER TABLE users ADD COLUMN blocked INTEGER DEFAULT 0")
        db.commit()


# ----------------- Routes -----------------
@app.route('/', methods=['GET', 'POST'])
def login_register():
    db = get_db()
    error = None
    success = None

    if request.method == 'POST':
        action = request.form.get('action')
        cur = db.cursor()

        if action == "login":
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '').strip()

            if not username or not password:
                error = "⚠️ Please enter username and password."
            else:
                # Admin login
                if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
                    session['admin'] = True
                    return redirect(url_for('admin_dashboard'))

                # Regular user login
                cur.execute(
                    "SELECT * FROM users WHERE username=%s AND password=%s",
                    (username, password)
                )
                user = cur.fetchone()

                if user:
                    if user["blocked"] == 1:
                        error = "🚫 Your account has been blocked. Contact admin."
                    else:
                        session['user'] = user['id']
                        session["username"] = user["username"]
                        return redirect(url_for('collection'))
                else:
                    error = "❌ Invalid credentials"

        elif action == "register":
            fullname = request.form.get('fullname', '').strip()
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip()
            password = request.form.get('password', '').strip()

            if not fullname or not username or not email or not password:
                error = "⚠️ All fields are required."
            else:
                cur.execute(
                    "SELECT * FROM users WHERE username=%s OR email=%s",
                    (username, email)
                )
                existing = cur.fetchone()
                if existing:
                    error = "⚠️ Username or email already exists."
                else:
                    cur.execute(
                        "INSERT INTO users (fullname, username, email, password) VALUES (%s, %s, %s, %s)",
                        (fullname, username, email, password)
                    )
                    db.commit()
                    success = "✅ Successfully registered! You can now login."

    return render_template('register.html', error=error, success=success)

# ----------------- User collection page -----------------
@app.route('/collection')
def collection():
    if session.get('admin'):
        return redirect(url_for('admin_dashboard'))
    if not session.get('user'):
        return redirect(url_for('login_register'))
    return render_template('collection.html')

# ----------------- Feedback routes -----------------
@app.route('/go-feedback', methods=['POST'])
def go_feedback():
    category = request.form.get('category')
    if not category:
        return render_template('collection.html', error="⚠️ Please choose an option.")
    return redirect(url_for('feedback', category=category))

@app.route('/feedback')
def feedback():
    category = request.args.get('category', '')
    name = request.args.get('name', '')
    return render_template('index.html', category=category, name=name)

@app.route('/submit', methods=['POST'])
def submit_feedback():
    name = request.form['name']
    message = request.form['message']
    category = request.form.get('category', '')
    selected_name = request.form.get('selected_name', '')

    if not name or not message:
        return "⚠️ Name and message are required!", 400

    db = get_db()
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO feedback (name, message, category, selected_name) VALUES (%s, %s, %s, %s)",
            (name, message, category, selected_name)
        )
    db.commit()

    return render_template('success.html', name=name, category=category, selected_name=selected_name)

# ----------------- Admin routes -----------------
@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('admin_login.html', error='❌ Invalid credentials')

    return render_template('admin_login.html')

@app.route('/admin-dashboard')
def admin_dashboard():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    db = get_db()
    selected_name = request.args.get('selected_name', None)

    with db.cursor() as cur:
        cur.execute("SELECT DISTINCT selected_name FROM feedback")
        unique_selected_names = [row[0] for row in cur.fetchall()]

        if selected_name:
            cur.execute(
                "SELECT * FROM feedback WHERE selected_name = %s",
                (selected_name,)
            )
            feedbacks = cur.fetchall()

            cur.execute(
                "SELECT COUNT(*) FROM feedback WHERE selected_name = %s",
                (selected_name,)
            )
            count = cur.fetchone()[0]
        else:
            cur.execute("SELECT * FROM feedback")
            feedbacks = cur.fetchall()
            count = None

    return render_template(
        'admin_dashboard.html',
        feedbacks=feedbacks,
        unique_selected_names=unique_selected_names,
        selected_name=selected_name,
        count=count
    )

# ----------------- Edit / Delete Feedback -----------------
@app.route('/edit-feedback/<int:feedback_id>', methods=['GET', 'POST'])
def edit_feedback(feedback_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    db = get_db()
    if request.method == 'POST':
        new_name = request.form['name']
        new_message = request.form['feedback']
        with db.cursor() as cur:
            cur.execute("UPDATE feedback SET name = %s, message = %s WHERE id = %s", (new_name, new_message, feedback_id))
        db.commit()
        return redirect(url_for('admin_dashboard'))

    with db.cursor() as cur:
        cur.execute("SELECT * FROM feedback WHERE id = %s", (feedback_id,))
        row = cur.fetchone()

    if row:
        return render_template('edit_feedback.html', feedback=row)
    else:
        return "Feedback not found", 404

@app.route('/delete-feedback/<int:feedback_id>', methods=['POST'])
def delete_feedback(feedback_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    db = get_db()
    with db.cursor() as cur:
        cur.execute("DELETE FROM feedback WHERE id = %s", (feedback_id,))
    db.commit()
    return redirect(url_for('admin_dashboard'))

@app.route("/admin/userview")
def admin_userview():
    db = get_db()
    with db.cursor() as cur:
        # Get users from users table
        cur.execute("SELECT id, fullname, username, email, blocked FROM users")
        users = cur.fetchall()

        # Get feedbacks from feedback table
        cur.execute("SELECT id, name, message, category, selected_name FROM feedback")
        feedbacks = cur.fetchall()

        # Count
        cur.execute("SELECT COUNT(*) FROM users")
        user_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM feedback")
        feedback_count = cur.fetchone()[0]

    return render_template(
        "admin_userview.html",
        users=users,
        feedbacks=feedbacks,
        user_count=user_count,
        feedback_count=feedback_count
    )


# ----------------- Logout -----------------
@app.route('/logout')
def logout():
    session.pop('user', None)
    session.pop('admin', None)
    return redirect(url_for('login_register'))

# ----------------- User Management for Admin -----------------
@app.route("/block_user/<int:user_id>")
def block_user(user_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    db = get_db()
    with db.cursor() as cur:
        cur.execute("UPDATE users SET blocked = CASE WHEN blocked = 0 THEN 1 ELSE 0 END WHERE id = %s", (user_id,))
    db.commit()
    return redirect(url_for("admin_userview"))


@app.route("/edit_user/<int:user_id>", methods=["GET", "POST"])
def edit_user(user_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    db = get_db()
    with db.cursor() as cur:
        if request.method == "POST":
            fullname = request.form.get("fullname", "").strip()
            username = request.form.get("username", "").strip()
            email = request.form.get("email", "").strip()
            password = request.form.get("password", "").strip()

            if not fullname or not username or not email:
                return "⚠️ All fields are required", 400

            if password:
                cur.execute(
                    "UPDATE users SET fullname = %s, username = %s, email = %s, password = %s WHERE id = %s",
                    (fullname, username, email, password, user_id)
                )
            else:
                cur.execute(
                    "UPDATE users SET fullname = %s, username = %s, email = %s WHERE id = %s",
                    (fullname, username, email, user_id)
                )
            db.commit()
            return redirect(url_for("admin_userview"))

        # Fetch user to prefill form
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()

    if not user:
        return "❌ User not found", 404

    return render_template("register.html", edit_mode=True, user=user)

# ----------------- Delete User -----------------
@app.route("/delete_user/<int:user_id>", methods=["GET", "POST"])
def delete_user(user_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    db = get_db()
    with db.cursor() as cur:
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    db.commit()
    return redirect(url_for("admin_userview"))


# ----------------- Run App -----------------
if __name__ == '__main__':
    # Initialize the database and ensure the 'blocked' column exists.
    # The Vercel deployment will handle this automatically during the build step.
    init_db()
    with app.app_context():
        ensure_blocked_column()
    app.run()
