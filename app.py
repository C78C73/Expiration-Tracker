from flask import Flask, request, render_template, redirect, url_for, flash

import os
from dotenv import load_dotenv
from datetime import datetime
import smtplib
from email.message import EmailMessage
import psycopg2
import threading
import time



load_dotenv()
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev")

# Database connection
def get_db():
    db_url = os.environ.get("DATABASE_URL")
    return psycopg2.connect(db_url)

# Initialize table
def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS food (
                    id SERIAL PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    exp DATE NOT NULL,
                    notified BOOLEAN DEFAULT FALSE
                )
            """)
            conn.commit()
init_db()

# Helper: log actions (optional, can be expanded to a table)
def log_action(action, name, exp=None):
    print(f"LOG: {action} {name} {exp} at {datetime.now()}")

def send_email(food_name, exp_date, added=False, deleted=False):
    sender_email = os.environ.get("EMAIL_USER")
    sender_pass = os.environ.get("EMAIL_PASS")
    receiver_email = sender_email

    # Format date for email as M/D/YYYY (or %#m/%#d/%Y on Windows)
    exp_fmt = exp_date
    if exp_date:
        try:
            dt = datetime.strptime(exp_date, "%Y-%m-%d")
            exp_fmt = dt.strftime("%-m/%-d/%Y") if os.name != "nt" else dt.strftime("%#m/%#d/%Y")
        except Exception:
            exp_fmt = exp_date

    if added:
        subject = f"Food Added: {food_name}"
        content = f"<h2>New Food Item Added</h2><p><b>Food:</b> {food_name}<br><b>Expiration Date:</b> {exp_fmt}</p>"
    elif deleted:
        subject = f"Food Deleted: {food_name}"
        content = f"<h2>Food Item Deleted</h2><p><b>Food:</b> {food_name}<br><b>Expiration Date:</b> {exp_fmt}</p>"
    else:
        subject = f"Food Expiration Alert: {food_name}"
        content = f"<h2>Expiration Alert</h2><p><b>Food:</b> {food_name}<br><b>Expires:</b> {exp_fmt}</p>"

    msg = EmailMessage()
    msg.set_content(f"Food: {food_name}\nExpiration: {exp_fmt if exp_fmt else ''}")
    msg.add_alternative(content, subtype="html")
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = receiver_email

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender_email, sender_pass)
            smtp.send_message(msg)
        print(f"Email sent for {food_name}")
    except Exception as e:
        print("Failed to send email:", e)


def check_expirations():
    today = datetime.now().date()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT name, exp, notified FROM food")
            for name, exp, notified in cur.fetchall():
                if exp and 0 <= (exp - today).days <= 3 and not notified:
                    send_email(name, exp.strftime("%Y-%m-%d"))
                    cur.execute("UPDATE food SET notified=TRUE WHERE name=%s", (name,))
            conn.commit()


def background_checker():
    while True:
        check_expirations()
        time.sleep(3600)

# Web routes


@app.route("/delete/<name>", methods=["POST"])
def delete_food(name):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT exp FROM food WHERE name=%s", (name,))
            row = cur.fetchone()
            exp = row[0].strftime("%Y-%m-%d") if row else None
            cur.execute("DELETE FROM food WHERE name=%s", (name,))
            conn.commit()
    log_action("delete", name, exp)
    send_email(name, exp, deleted=True)
    flash(f"Deleted {name}", "info")
    return redirect(url_for("index"))


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        name = request.form["name"].strip()
        exp = request.form["exp"]
        # Check for duplicate
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM food WHERE LOWER(name)=%s", (name.lower(),))
                if cur.fetchone():
                    flash(f"Food '{name}' already exists!", "warning")
                else:
                    cur.execute("INSERT INTO food (name, exp) VALUES (%s, %s)", (name, exp))
                    conn.commit()
                    log_action("add", name, exp)
                    send_email(name, exp, added=True)
                    flash(f"Added {name}", "success")
        return redirect(url_for("index"))
    # Format dates for display
    display_list = []
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT name, exp FROM food ORDER BY exp ASC")
            for name, exp in cur.fetchall():
                try:
                    exp_fmt = exp.strftime("%-m/%-d/%Y") if os.name != "nt" else exp.strftime("%#m/%#d/%Y")
                except Exception:
                    exp_fmt = str(exp)
                display_list.append({"name": name, "exp": exp_fmt})
    return render_template("index.html", food_list=display_list)


# Start background thread
threading.Thread(target=background_checker, daemon=True).start()

if __name__ == "__main__":
    app.run()
