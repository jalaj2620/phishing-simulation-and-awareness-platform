# app.py
import os
import sqlite3
import uuid
import datetime
import csv
import io
import smtplib
import re
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask import Flask, request, jsonify, send_from_directory, g
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
print("SMTP_HOST:", os.environ.get("SMTP_HOST"))
print("SMTP_USER:", os.environ.get("SMTP_USER"))


app = Flask(__name__)
CORS(app)

# ---------- Configuration ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, './'))
DB_PATH = os.path.join(BASE_DIR, 'database.db')

# SMTP defaults - override with env vars in production
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "smtp00022@gmail.com"
SMTP_PASS = "wpri lcpz kavr aclg"
MAIL_FROM_DOMAIN = os.environ.get('MAIL_FROM_DOMAIN', 'example.local')
TEST_DOMAINS = [d.strip().lower() for d in os.environ.get('TEST_DOMAINS', 'example.com,localhost').split(',') if d.strip()]

# ---------- Database helpers ----------
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH, check_same_thread=False)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    cur = db.cursor()
    try:
        sql_path = os.path.join(BASE_DIR, 'schema.sql')
        with open(sql_path, 'r') as f:
            cur.executescript(f.read())
        db.commit()
    except Exception as e:
        print("Failed to initialize DB:", e)

# ---------- Utility ----------
def send_email_smtp(to_email, subject, html_body, text_body=None):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = SMTP_USER
    msg['To'] = to_email
    if not text_body:
        text_body = html_body
    msg.attach(MIMEText(text_body, 'plain'))
    msg.attach(MIMEText(html_body, 'html'))
    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10)
        server.ehlo()
        # start TLS only if we have auth creds or port suggests it
        if SMTP_USER and SMTP_PASS:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(msg['From'], [to_email], msg.as_string())
        server.quit()
        return True, "sent"
    except Exception as e:
        # return readable error to caller (frontend logs/summaries)
        return False, str(e)

# password helpers (migrate plaintext to hashed on first successful login)
def verify_and_migrate_password(db, cur, user_row, provided_password):
    stored = user_row['password']
    user_id = user_row['id']

    # if stored looks like a werkzeug hash, use check_password_hash
    if stored and stored.startswith('pbkdf2:'):
        ok = check_password_hash(stored, provided_password)
        return ok
    # otherwise treat stored as plaintext for backward compatibility
    if provided_password == stored:
        # migrate to hashed password
        hashed = generate_password_hash(provided_password)
        try:
            cur.execute("UPDATE users SET password=? WHERE id=?", (hashed, user_id))
            db.commit()
        except Exception as e:
            print("Password migration failed:", e)
        return True
    return False

# ---------- Routes ----------
@app.route('/')
def root():
    return send_from_directory(FRONTEND_DIR, 'login.html')

@app.route('/<path:p>')
def frontend(p):
    target = os.path.join(FRONTEND_DIR, p)
    if os.path.exists(target):
        return send_from_directory(FRONTEND_DIR, p)
    return "File not found", 404

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id, username, email, password FROM users WHERE username=?", (username,))
    user = cur.fetchone()
    if not user:
        return jsonify({'status': 'error'}), 401

    if not verify_and_migrate_password(db, cur, user, password):
        return jsonify({'status': 'error'}), 401

    # return user metadata (do not include password)
    user_out = {'id': user['id'], 'username': user['username'], 'email': user['email']}
    return jsonify({'status': 'success', 'user': user_out})

# ---------- Campaign APIs ----------
@app.route('/api/campaigns', methods=['GET'])
def get_campaigns():
    db = get_db()
    query = """
        SELECT 
            c.*,
            COUNT(t.id) AS targets_count,
            COALESCE(SUM(t.clicked), 0) AS clicks_count
        FROM campaigns c
        LEFT JOIN targets t ON c.id = t.campaign_id
        GROUP BY c.id
        ORDER BY c.created_at DESC
    """
    cur = db.execute(query)
    return jsonify([dict(row) for row in cur.fetchall()])

@app.route('/api/campaigns', methods=['POST'])
def create_campaign():
    data = request.get_json() or {}
    name = data.get('name')
    template = data.get('template', '')
    status = data.get('status', 'draft')

    if not name:
        return jsonify({'error': 'Campaign name required'}), 400

    db = get_db()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO campaigns (name, template, status, created_at) VALUES (?, ?, ?, datetime('now'))",
        (name, template, status)
    )
    db.commit()
    new_id = cur.lastrowid

    cur.execute("SELECT * FROM campaigns WHERE id = ?", (new_id,))
    new_campaign = cur.fetchone()

    return jsonify(dict(new_campaign)), 201


@app.route('/api/campaigns/<int:campaign_id>/import', methods=['POST'])
def import_to_campaign(campaign_id):
    data = request.get_json() or {}
    emails = data.get('emails', [])
    if not emails:
        return jsonify({'error': 'No emails provided'}), 400

    db = get_db()
    cur = db.cursor()
    imported = 0
    sent_ok = 0
    sent_fail = 0
    skipped = 0

    # Fetch campaign info
    cur.execute("SELECT name, template FROM campaigns WHERE id=?", (campaign_id,))
    campaign = cur.fetchone()
    if not campaign:
        return jsonify({'error': 'Campaign not found'}), 404
    subject = campaign['name']
    html_body = """
<html>
<body>
<h3>Security Awareness Notification</h3>

<p>Hello,</p>

<p>You have been selected to participate in an internal security awareness training exercise.</p>

<p>Please review the message below and follow the link provided:</p>

<p>
<a href="http://127.0.0.1:5000/track/{token}">
Open Training Message
</a>
</p>

<p>This exercise helps employees recognize phishing attempts and improve cybersecurity awareness.</p>

<p>Regards,<br>
IT Security Team</p>
</body>
</html>
"""

    for email in emails:
        email = (email or '').strip()
        if not EMAIL_REGEX.match(email):
            skipped += 1
            continue
        token = str(uuid.uuid4())
        # ensure token uniqueness (very small loop)
        attempts = 0
        while attempts < 3:
            try:
                cur.execute(
                    "INSERT INTO targets (campaign_id, name, email, department, token) VALUES (?, ?, ?, ?, ?)",
                    (campaign_id, email.split('@')[0], email, 'N/A', token)
                )
                imported += 1
                break
            except sqlite3.IntegrityError:
                # token conflict, regen
                token = str(uuid.uuid4())
                attempts += 1
        else:
            # could not insert due to repeated token collisions
            skipped += 1
            continue

        # Send the email
        personalized_html = html_body.replace("{token}", token)
        success, msg = send_email_smtp(
            to_email=email,
            subject=f"Security Awareness Training - {subject}",
            html_body=personalized_html,
            text_body=f"Visit http://127.0.0.1:5000/track/{token}"
        )
        if success:
            sent_ok += 1
        else:
            sent_fail += 1
            print(f"Email send failed for {email}: {msg}")

    db.commit()
    return jsonify({
        'message': f'Imported {imported} targets. Emails sent: {sent_ok} success, {sent_fail} failed. Skipped {skipped} invalid/duplicate.'
    })


@app.route('/api/campaigns/<int:campaign_id>/export', methods=['GET'])
def export_campaign(campaign_id):
    db = get_db()
    cur = db.execute("SELECT name, email, department, clicked FROM targets WHERE campaign_id=?", (campaign_id,))
    rows = cur.fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['name', 'email', 'department', 'clicked'])
    for row in rows:
        writer.writerow([row['name'], row['email'], row['department'], row['clicked']])
    output.seek(0)
    return (
        output.getvalue(),
        200,
        {'Content-Type': 'text/csv', 'Content-Disposition': f'attachment; filename=campaign_{campaign_id}.csv'}
    )

@app.route('/api/campaigns/<int:campaign_id>/stats', methods=['GET'])
def campaign_stats(campaign_id):
    db = get_db()

    cur = db.execute("""
        SELECT 
            COUNT(*) AS total_targets,
            COALESCE(SUM(clicked), 0) AS clicks
        FROM targets
        WHERE campaign_id=?
    """, (campaign_id,))

    stats = cur.fetchone()

    total = stats['total_targets'] or 0
    clicks = stats['clicks'] or 0

    ctr = 0
    if total > 0:
        ctr = round((clicks / total) * 100, 2)

    return jsonify({
        "total_targets": total,
        "clicks": clicks,
        "ctr": ctr
    })

@app.route('/api/campaigns/<int:campaign_id>', methods=['DELETE'])
def delete_campaign(campaign_id):
    db = get_db()
    cur = db.cursor()

    # Delete targets linked to this campaign (to maintain integrity)
    cur.execute("DELETE FROM targets WHERE campaign_id = ?", (campaign_id,))
    cur.execute("DELETE FROM campaigns WHERE id = ?", (campaign_id,))
    db.commit()

    # rowcount refers to last execute (campaigns delete)
    if cur.rowcount == 0:
        return jsonify({'error': 'Campaign not found'}), 404

    return jsonify({'message': f'Campaign {campaign_id} deleted successfully'}), 200

@app.route('/track/<token>')
def track_click(token):
    db = get_db()
    cur = db.cursor()

    # Mark this token as clicked
    cur.execute("UPDATE targets SET clicked=1 WHERE token=?", (token,))
    # record in clicks table optionally
    try:
        cur.execute("SELECT id, campaign_id FROM targets WHERE token=?", (token,))
        t = cur.fetchone()
        if t:
            cur.execute("INSERT INTO clicks (target_id, campaign_id, ts) VALUES (?, ?, datetime('now'))", (t['id'], t['campaign_id']))
    except Exception:
        pass
    db.commit()



    return """
    <html>
    <body style='font-family:sans-serif;text-align:center;margin-top:80px;'>
      <h2>✅ Simulation Click Recorded</h2>
      <p>This click was tracked as part of your organization's phishing awareness program.</p>
    </body>
    </html>
    """

@app.route('/user-awareness')
def user_awareness():
    return send_from_directory(FRONTEND_DIR, 'user_awareness.html')

if __name__ == '__main__':
    if not os.path.exists(DB_PATH):
        open(DB_PATH, 'a').close()
    with app.app_context():
        init_db()
    app.run(host='127.0.0.1', port=5000, debug=True)


