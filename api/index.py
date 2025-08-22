from flask import Flask, render_template, request, redirect, session, url_for, g
import sqlite3

app = Flask(__name__)
app.secret_key = 'admintest'  # Required for sessions

# Admin credentials
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'admin123'

# Database configuration
DATABASE = 'database.db'

# ----------------- DB Helpers -----------------
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE, timeout=5)
        g.db.row_factory = sqlite3.Row  # enables dict-like row access
    return g.db

@app.teardown_appcontext
def close_db(error=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    with sqlite3.connect(DATABASE) as conn:
        c = conn.cursor()
        # Create feedback table
        c.execute('''
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                message TEXT NOT NULL,
                category TEXT,
                selected_name TEXT
            )
        ''')
        # Create users table
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                fullname TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                blocked INTEGER DEFAULT 0
            )
        ''')
        conn.commit()

def ensure_blocked_column():
    db = get_db()
    columns = [col[1] for col in db.execute("PRAGMA table_info(users)").fetchall()]
    if 'blocked' not in columns:
        db.execute("ALTER TABLE users ADD COLUMN blocked INTEGER DEFAULT 0")
        db.commit()


# ----------------- Routes -----------------
@app.route('/', methods=['GET', 'POST'])
def login_register():
    db = get_db()
    error = None
    success = None

    if request.method == 'POST':
        action = request.form.get('action')

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
                user = db.execute(
                    "SELECT * FROM users WHERE username=? AND password=?",
                    (username, password)
                ).fetchone()

                if user:
                    if user["blocked"] == 1:  # ✅ fixed: correct column name
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
                existing = db.execute(
                    "SELECT * FROM users WHERE username=? OR email=?",
                    (username, email)
                ).fetchone()
                if existing:
                    error = "⚠️ Username or email already exists."
                else:
                    db.execute(
                        "INSERT INTO users (fullname, username, email, password) VALUES (?, ?, ?, ?)",
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
    db.execute(
        "INSERT INTO feedback (name, message, category, selected_name) VALUES (?, ?, ?, ?)",
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
    unique_selected_names = [row[0] for row in db.execute("SELECT DISTINCT selected_name FROM feedback").fetchall()]

    if selected_name:
        feedbacks = db.execute(
            "SELECT * FROM feedback WHERE selected_name = ?",
            (selected_name,)
        ).fetchall()
        count = db.execute(
            "SELECT COUNT(*) FROM feedback WHERE selected_name = ?",
            (selected_name,)
        ).fetchone()[0]
    else:
        feedbacks = db.execute("SELECT * FROM feedback").fetchall()
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
        db.execute("UPDATE feedback SET name = ?, message = ? WHERE id = ?", (new_name, new_message, feedback_id))
        db.commit()
        return redirect(url_for('admin_dashboard'))

    row = db.execute("SELECT * FROM feedback WHERE id = ?", (feedback_id,)).fetchone()
    if row:
        feedback = dict(row)
        return render_template('edit_feedback.html', feedback=feedback)
    else:
        return "Feedback not found", 404

@app.route('/delete-feedback/<int:feedback_id>', methods=['POST'])
def delete_feedback(feedback_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    db = get_db()
    db.execute("DELETE FROM feedback WHERE id = ?", (feedback_id,))
    db.commit()
    return redirect(url_for('admin_dashboard'))

@app.route("/admin/userview")
def admin_userview():
    conn = get_db()
    cursor = conn.cursor()
    
    # Get users from users table
    cursor.execute("SELECT id, fullname, username, email, blocked FROM users")
    users = [dict(row) for row in cursor.fetchall()]

    # Get feedbacks from feedback table
    cursor.execute("SELECT id, name, message, category, selected_name FROM feedback")
    feedbacks = cursor.fetchall()

    # Count
    cursor.execute("SELECT COUNT(*) FROM users")
    user_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM feedback")
    feedback_count = cursor.fetchone()[0]

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
    db.execute("UPDATE users SET blocked = CASE WHEN blocked = 0 THEN 1 ELSE 0 END WHERE id = ?", (user_id,))
    db.commit()
    return redirect(url_for("admin_userview"))


@app.route("/edit_user/<int:user_id>", methods=["GET", "POST"])
def edit_user(user_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    db = get_db()
    if request.method == "POST":
        fullname = request.form.get("fullname", "").strip()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()  # allow updating password too

        if not fullname or not username or not email:
            return "⚠️ All fields are required", 400

        if password:  # update password only if filled
            db.execute(
                "UPDATE users SET fullname = ?, username = ?, email = ?, password = ? WHERE id = ?",
                (fullname, username, email, password, user_id)
            )
        else:
            db.execute(
                "UPDATE users SET fullname = ?, username = ?, email = ? WHERE id = ?",
                (fullname, username, email, user_id)
            )
        db.commit()
        return redirect(url_for("admin_userview"))

    # Fetch user to prefill form
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        return "❌ User not found", 404

    # Reuse register.html but pass user data for prefill
    return render_template("register.html", edit_mode=True, user=user)

# ----------------- Delete User -----------------
@app.route("/delete_user/<int:user_id>", methods=["GET", "POST"])
def delete_user(user_id):
    if not session.get('admin'):
        return redirect(url_for('admin_login'))

    db = get_db()
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()
    return redirect(url_for("admin_userview"))


# ----------------- Run App -----------------
if __name__ == '__main__':
    init_db()
    with app.app_context():
        ensure_blocked_column()  # Add blocked column if missing
    app.run(debug=True)

# ----------------- Vercel Handler -----------------
# For Vercel deployment (no app.run)
def handler(event, context):
    init_db()
    with app.app_context():
        ensure_blocked_column()
    return app(event, context)

