from flask import Flask, request, render_template, redirect, url_for, flash
import os
from dotenv import load_dotenv
from datetime import datetime
import smtplib
from email.message import EmailMessage
import json
import threading
import time


load_dotenv()
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev")


food_file = "food_data.json"
log_file = "food_log.json"

def log_action(action, name, exp=None):
    log_entry = {
        "action": action,
        "name": name,
        "exp": exp,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    try:
        with open(log_file, "r") as f:
            logs = json.load(f)
    except:
        logs = []
    logs.append(log_entry)
    with open(log_file, "w") as f:
        json.dump(logs, f, indent=2)

try:
    with open(food_file, "r") as f:
        food_list = json.load(f)
except:
    food_list = []

# Save food list to JSON
def save_food():
    with open(food_file, "w") as f:
        json.dump(food_list, f)

# Send email reminder
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

# Check expirations
def check_expirations():
    today = datetime.now()
    for food in food_list:
        exp_date = datetime.strptime(food["exp"], "%Y-%m-%d")
        if 0 <= (exp_date - today).days <= 3 and not food.get("notified"):
            send_email(food["name"], food["exp"])
            food["notified"] = True
    save_food()

# Background thread
def background_checker():
    while True:
        check_expirations()
        time.sleep(3600)  # check every hour

# Web routes

# Delete food route
@app.route("/delete/<name>", methods=["POST"])
def delete_food(name):
    global food_list
    deleted_item = None
    for f in food_list:
        if f["name"].lower() == name.lower():
            deleted_item = f
            break
    food_list = [f for f in food_list if f["name"].lower() != name.lower()]
    save_food()
    log_action("delete", name, deleted_item["exp"] if deleted_item else None)
    send_email(name, deleted_item["exp"] if deleted_item else None, deleted=True)
    flash(f"Deleted {name}", "info")
    return redirect(url_for("index"))

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        name = request.form["name"].strip()
        exp = request.form["exp"]
        # Check for duplicate
        if any(f["name"].lower() == name.lower() for f in food_list):
            flash(f"Food '{name}' already exists!", "warning")
        else:
            food_list.append({"name": name, "exp": exp})
            save_food()
            log_action("add", name, exp)
            send_email(name, exp, added=True)
            flash(f"Added {name}", "success")
        return redirect(url_for("index"))
    # Format dates for display
    display_list = []
    for food in food_list:
        try:
            dt = datetime.strptime(food["exp"], "%Y-%m-%d")
            exp_fmt = dt.strftime("%-m/%-d/%Y") if os.name != "nt" else dt.strftime("%#m/%#d/%Y")
        except Exception:
            exp_fmt = food["exp"]
        display_list.append({"name": food["name"], "exp": exp_fmt})
    return render_template("index.html", food_list=display_list)

# Start background thread
threading.Thread(target=background_checker, daemon=True).start()

if __name__ == "__main__":
    app.run()
