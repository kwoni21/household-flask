"""
app.py  ─  원♡순 가계부 Flask 웹 앱
로컬: python app.py
배포: Railway (Procfile 참고)
"""

import os
import hashlib
import psycopg2
import psycopg2.extras
from datetime import datetime, date
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'household-secret-2024')

DATABASE_URL = os.environ.get('DATABASE_URL', '')

# ── DB 연결 ──────────────────────────────────────────────────
def get_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode('utf-8')).hexdigest()

def init_db():
    conn = get_conn(); cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            userid TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS categories (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS transactions (
            id SERIAL PRIMARY KEY,
            date DATE NOT NULL,
            cat_code TEXT REFERENCES categories(code),
            description TEXT,
            income NUMERIC(15,2) DEFAULT 0,
            expense NUMERIC(15,2) DEFAULT 0,
            credit SMALLINT DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)
    conn.commit(); cur.close(); conn.close()

# ── 로그인 필수 데코레이터 ───────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'userid' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ── 인증 ────────────────────────────────────────────────────
@app.route('/', methods=['GET', 'POST'])
def login():
    if 'userid' in session:
        return redirect(url_for('dashboard'))
    error = None
    if request.method == 'POST':
        userid   = request.form.get('userid', '').strip()
        password = request.form.get('password', '').strip()
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT 1 FROM users WHERE userid=%s AND password=%s", (userid, hash_pw(password)))
        ok = cur.fetchone()
        cur.close(); conn.close()
        if ok:
            session['userid'] = userid
            return redirect(url_for('dashboard'))
        error = "아이디 또는 비밀번호가 올바르지 않습니다."
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ── 대시보드 ────────────────────────────────────────────────
@app.route('/dashboard')
@login_required
def dashboard():
    now   = datetime.now()
    year  = int(request.args.get('year',  now.year))
    month = int(request.args.get('month', now.month))

    conn = get_conn(); cur = conn.cursor()

    # 월별 거래
    cur.execute("""
        SELECT t.id, t.date, COALESCE(c.name, t.cat_code) as category,
               t.income::float, t.expense::float, t.credit, t.description
        FROM transactions t
        LEFT JOIN categories c ON t.cat_code = c.code
        WHERE EXTRACT(YEAR FROM t.date)=%s AND EXTRACT(MONTH FROM t.date)=%s
        ORDER BY t.date DESC, t.id DESC
    """, (year, month))
    rows = cur.fetchall()

    # 요약
    total_income  = sum(r['income']  for r in rows)
    total_expense = sum(r['expense'] for r in rows if r['credit'] == 0)
    card_expense  = sum(r['expense'] for r in rows if r['credit'] == 1)
    balance       = total_income - total_expense

    # 전체 누적 잔액
    cur.execute("SELECT COALESCE(SUM(income),0)::float as ti FROM transactions")
    all_income = cur.fetchone()['ti']
    cur.execute("SELECT COALESCE(SUM(expense),0)::float as te FROM transactions WHERE credit=0")
    all_expense = cur.fetchone()['te']
    total_balance = all_income - all_expense

    # 카테고리별 지출 (현금)
    cur.execute("""
        SELECT COALESCE(c.name, t.cat_code) as category, SUM(t.expense)::float as total
        FROM transactions t
        LEFT JOIN categories c ON t.cat_code = c.code
        WHERE EXTRACT(YEAR FROM t.date)=%s AND EXTRACT(MONTH FROM t.date)=%s AND t.credit=0 AND t.expense>0
        GROUP BY category ORDER BY total DESC
    """, (year, month))
    cat_data = cur.fetchall()

    # 일별 수입/지출
    cur.execute("""
        SELECT date::text, SUM(income)::float as income, SUM(CASE WHEN credit=0 THEN expense ELSE 0 END)::float as expense
        FROM transactions
        WHERE EXTRACT(YEAR FROM date)=%s AND EXTRACT(MONTH FROM date)=%s
        GROUP BY date ORDER BY date
    """, (year, month))
    daily_data = cur.fetchall()

    # 연도 목록
    cur.execute("SELECT DISTINCT EXTRACT(YEAR FROM date)::int as y FROM transactions ORDER BY y DESC")
    years = [r['y'] for r in cur.fetchall()] or [now.year]

    cur.close(); conn.close()

    return render_template('dashboard.html',
        userid=session['userid'], year=year, month=month, years=years,
        rows=rows[:10], total_income=total_income, total_expense=total_expense,
        card_expense=card_expense, balance=balance, total_balance=total_balance,
        cat_data=list(cat_data), daily_data=list(daily_data)
    )

# ── 거래 내역 ────────────────────────────────────────────────
@app.route('/transactions')
@login_required
def transactions():
    now   = datetime.now()
    year  = int(request.args.get('year',  now.year))
    month = int(request.args.get('month', now.month))
    search = request.args.get('search', '')
    type_f = request.args.get('type_f', '전체')
    pay_f  = request.args.get('pay_f',  '전체')

    conn = get_conn(); cur = conn.cursor()

    q = """
        SELECT t.id, t.date, COALESCE(c.name, t.cat_code) as category,
               t.income::float, t.expense::float, t.credit, t.description
        FROM transactions t
        LEFT JOIN categories c ON t.cat_code = c.code
        WHERE EXTRACT(YEAR FROM t.date)=%s AND EXTRACT(MONTH FROM t.date)=%s
    """
    params = [year, month]
    if search:
        q += " AND (t.description ILIKE %s OR c.name ILIKE %s)"
        params += [f'%{search}%', f'%{search}%']
    if type_f == '수입만':  q += " AND t.income > 0"
    if type_f == '지출만':  q += " AND t.expense > 0"
    if pay_f  == '현금':    q += " AND t.credit = 0"
    if pay_f  == '신용카드': q += " AND t.credit = 1"
    q += " ORDER BY t.date DESC, t.id DESC"

    cur.execute(q, params)
    rows = cur.fetchall()

    cur.execute("SELECT DISTINCT EXTRACT(YEAR FROM date)::int as y FROM transactions ORDER BY y DESC")
    years = [r['y'] for r in cur.fetchall()] or [now.year]
    cur.close(); conn.close()

    return render_template('transactions.html',
        userid=session['userid'], rows=rows, year=year, month=month, years=years,
        search=search, type_f=type_f, pay_f=pay_f
    )

# ── 거래 추가 ────────────────────────────────────────────────
@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_transaction():
    conn = get_conn(); cur = conn.cursor()
    cur.execute("SELECT code, name FROM categories ORDER BY code")
    cats = cur.fetchall()

    if request.method == 'POST':
        tx_date     = request.form.get('date')
        cat_code    = request.form.get('cat_code')
        description = request.form.get('description', '').strip()
        income      = float(request.form.get('income', '0').replace(',', '') or 0)
        expense     = float(request.form.get('expense', '0').replace(',', '') or 0)
        credit      = 1 if request.form.get('credit') else 0

        if income == 0 and expense == 0:
            return render_template('add.html', cats=cats, userid=session['userid'], error="수입 또는 지출 금액을 입력하세요.")
        if not description:
            return render_template('add.html', cats=cats, userid=session['userid'], error="내용을 입력하세요.")

        cur.execute(
            "INSERT INTO transactions (date,cat_code,description,income,expense,credit) VALUES (%s,%s,%s,%s,%s,%s)",
            (tx_date, cat_code, description, income, expense, credit)
        )
        conn.commit(); cur.close(); conn.close()
        return redirect(url_for('dashboard'))

    cur.close(); conn.close()
    return render_template('add.html', cats=cats, userid=session['userid'], error=None)

# ── 거래 삭제 ────────────────────────────────────────────────
@app.route('/delete/<int:tx_id>', methods=['POST'])
@login_required
def delete_transaction(tx_id):
    conn = get_conn(); cur = conn.cursor()
    cur.execute("DELETE FROM transactions WHERE id=%s", (tx_id,))
    conn.commit(); cur.close(); conn.close()
    return redirect(request.referrer or url_for('transactions'))

# ── 카테고리 관리 ────────────────────────────────────────────
@app.route('/categories', methods=['GET', 'POST'])
@login_required
def categories():
    conn = get_conn(); cur = conn.cursor()
    if request.method == 'POST':
        code = request.form.get('code', '').strip()
        name = request.form.get('name', '').strip()
        if code and name:
            cur.execute("INSERT INTO categories (code,name) VALUES (%s,%s) ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name", (code, name))
            conn.commit()
    cur.execute("SELECT code, name FROM categories ORDER BY code")
    cats = cur.fetchall()
    cur.close(); conn.close()
    return render_template('categories.html', cats=cats, userid=session['userid'])

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
