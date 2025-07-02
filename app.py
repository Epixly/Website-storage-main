from flask import Flask, render_template, request, redirect, session, send_from_directory
import os
import sqlite3
from werkzeug.utils import secure_filename
from datetime import datetime


app = Flask(__name__)
app.config['SESSION_PERMANENT'] = False
app.secret_key = 'YOUR_SECRET_KEY'
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --------- DB Setup ---------
def init_db():
    with sqlite3.connect('data.db') as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE,
                        password TEXT)''')

        c.execute('''CREATE TABLE IF NOT EXISTS persons (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT,
                        son_of TEXT,
                        age INTEGER,
                        area TEXT,
                        address TEXT,
                        reports_count INTEGER DEFAULT 0)''')

        c.execute('''CREATE TABLE IF NOT EXISTS reports (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        person_id INTEGER,
                        summary TEXT,
                        date TEXT,
                        pdf_path TEXT,
                        FOREIGN KEY(person_id) REFERENCES persons(id))''')

        # Create default login
        c.execute("INSERT OR IGNORE INTO users (username, password) VALUES (?, ?)", ('admin', 'admin'))

# --------- Auth Routes ---------
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = ''
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        with sqlite3.connect('data.db') as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
            if c.fetchone():
                session['user'] = username
                return redirect('/')
            else:
                error = 'Invalid credentials'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/login')

# --------- Protect Everything ---------
@app.before_request
def require_login():
    if request.endpoint not in ('login', 'static', 'uploaded_file') and 'user' not in session:
        return redirect('/login')

# --------- Menu/Home ---------
@app.route('/')
def menu():
    return render_template('home.html')

# --------- Input Data ---------
@app.route('/input', methods=['GET', 'POST'])
def input_data():
    if request.method == 'POST':
        name = request.form['name']
        son_of = request.form['son_of']
        age = request.form['age']
        area = request.form['area']
        address = request.form['address']
        summary = request.form['summary']
        date = request.form['date']
        pdf = request.files['pdf']

        with sqlite3.connect('data.db') as conn:
            c = conn.cursor()
            # Check if person exists
            c.execute("SELECT id FROM persons WHERE name=? AND son_of=? AND age=?", (name, son_of, age))
            person = c.fetchone()

            if person:
                person_id = person[0]
            else:
                c.execute("INSERT INTO persons (name, son_of, age, area, address) VALUES (?, ?, ?, ?, ?)", 
                          (name, son_of, age, area, address))
                person_id = c.lastrowid

            pdf_path = ''
            if pdf:
                filename = secure_filename(pdf.filename)
                path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                pdf.save(path)
                pdf_path = path

            c.execute("INSERT INTO reports (person_id, summary, date, pdf_path) VALUES (?, ?, ?, ?)", 
                      (person_id, summary, date, pdf_path))
            c.execute("UPDATE persons SET reports_count = reports_count + 1 WHERE id = ?", (person_id,))
        return redirect('/')
    return render_template('input.html')

# --------- View All ---------
@app.route('/viewall')
def viewall():
    conn = sqlite3.connect('data.db')
    c = conn.cursor()
    c.execute("""
        SELECT persons.id, name, son_of, COUNT(reports.id)
        FROM persons
        LEFT JOIN reports ON persons.id = reports.person_id
        GROUP BY persons.id
    """)
    persons = c.fetchall()
    conn.close()
    return render_template('viewall.html', persons=persons)


@app.route('/delete_person/<int:person_id>')
def delete_person(person_id):
    with sqlite3.connect('data.db') as conn:
        c = conn.cursor()
        # First delete all reports of this person
        c.execute("DELETE FROM reports WHERE person_id=?", (person_id,))
        # Then delete the person
        c.execute("DELETE FROM persons WHERE id=?", (person_id,))
    return redirect('/viewall')



# --------- View Reports ---------
@app.route('/reports/<int:person_id>')
def reports(person_id):
    with sqlite3.connect('data.db') as conn:
        conn.row_factory = sqlite3.Row  # Enables dict-style access
        c = conn.cursor()
        c.execute("SELECT * FROM persons WHERE id=?", (person_id,))
        person = c.fetchone()
        c.execute("SELECT * FROM reports WHERE person_id=?", (person_id,))
        reports = c.fetchall()
    return render_template('reports.html', person=person, reports=reports)


# --------- Add Another Report ---------
@app.route('/add_report/<int:person_id>', methods=['GET', 'POST'])
def add_report(person_id):
    if request.method == 'POST':
        report_area = request.form['report_area']
        summary = request.form['summary']
        date = request.form['date']
        pdf = request.files['pdf']

        pdf_path = ''
        if pdf:
            filename = secure_filename(pdf.filename)
            path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            pdf.save(path)
            pdf_path = path

        with sqlite3.connect('data.db') as conn:
            c = conn.cursor()
            c.execute("INSERT INTO reports (person_id, summary, date, pdf_path, report_area) VALUES (?, ?, ?, ?, ?)", 
                (person_id, summary, date, pdf_path, report_area))
            c.execute("UPDATE persons SET reports_count = reports_count + 1 WHERE id = ?", (person_id,))
        return redirect(f'/reports/{person_id}')
    else:
        with sqlite3.connect('data.db') as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM persons WHERE id=?", (person_id,))
            person = c.fetchone()
        return render_template('add_report.html', person=person)


# --------- Delete Report ---------
@app.route('/delete/<int:report_id>')
def delete_report(report_id):
    with sqlite3.connect('data.db') as conn:
        c = conn.cursor()
        c.execute("SELECT person_id FROM reports WHERE id=?", (report_id,))
        person = c.fetchone()
        if person:
            person_id = person[0]
            c.execute("DELETE FROM reports WHERE id=?", (report_id,))
            c.execute("UPDATE persons SET reports_count = reports_count - 1 WHERE id=?", (person_id,))
    return redirect(f'/reports/{person_id}')

# --------- Search ---------
@app.route('/search', methods=['GET', 'POST'])
def search():
    results = []
    searched = False
    if request.method == 'POST':
        query = request.form['query']
        with sqlite3.connect('data.db') as conn:
            c = conn.cursor()
            c.execute("SELECT id, name, son_of, age, reports_count FROM persons WHERE name LIKE ?", ('%' + query + '%',))
            results = c.fetchall()
        searched = True
    return render_template('search.html', results=results, searched=searched)

# --------- Serve PDF ---------
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --------- Start ---------
if __name__ == '__main__':
    init_db()
    app.run(debug=True)
