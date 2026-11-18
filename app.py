import os
import re
import pdfplumber
import requests
from datetime import datetime

from flask import Flask, render_template, redirect, url_for, request, flash
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt

from models import db, User, Resume, Job, Application, Bookmark


# =========================
# API KEYS (Move to .env later for security)
# =========================
ADZUNA_APP_ID = "c8848ab8"
ADZUNA_APP_KEY = "c358146aa93ed6ddc47b7432a5fe5585"


# =========================
# APP CONFIG
# =========================
app = Flask(__name__)
app.config["SECRET_KEY"] = "jobnexa_secret_key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///jobnexa.db"
app.config["UPLOAD_FOLDER"] = "uploads"

db.init_app(app)
bcrypt = Bcrypt(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


# =========================
# LOGIN MANAGER
# =========================
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# =========================
# FETCH LIVE JOBS (ADZUNA)
# =========================
def fetch_live_jobs(query="python developer", location="india"):
    url = "https://api.adzuna.com/v1/api/jobs/in/search/1"

    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,
        "results_per_page": 10,
        "what": query,
        "where": location,
        "sort_by": "date"
    }

    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            return data.get("results", [])
        else:
            return []
    except:
        return []


# =========================
# HOME
# =========================
@app.route("/")
def home():
    return render_template("index.html")


# =========================
# REGISTER
# =========================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":

        if User.query.filter_by(email=request.form["email"]).first():
            flash("Email already exists.")
            return redirect(url_for("register"))

        hashed_pw = bcrypt.generate_password_hash(
            request.form["password"]
        ).decode("utf-8")

        user = User(
            name=request.form["name"],
            email=request.form["email"],
            password=hashed_pw
        )

        db.session.add(user)
        db.session.commit()

        return redirect(url_for("login"))

    return render_template("register.html")


# =========================
# LOGIN
# =========================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":

        user = User.query.filter_by(email=request.form["email"]).first()

        if user and bcrypt.check_password_hash(user.password, request.form["password"]):
            login_user(user)
            return redirect(url_for("dashboard"))

        flash("Invalid credentials.")

    return render_template("login.html")


# =========================
# LOGOUT
# =========================
@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("home"))


# =========================
# DASHBOARD
# =========================
@app.route("/dashboard")
@login_required
def dashboard():

    keyword = request.args.get("keyword", "python developer")

    jobs = fetch_live_jobs(keyword)

    resumes = Resume.query.filter_by(user_id=current_user.id).all()
    applications = Application.query.filter_by(user_id=current_user.id).all()

    stats = {
        "total": len(applications),
        "interviews": len([a for a in applications if a.status == "Interview"]),
        "offers": len([a for a in applications if a.status == "Offer"]),
    }

    return render_template(
        "dashboard.html",
        name=current_user.name,
        resumes=resumes,
        jobs=jobs,
        stats=stats
    )


# =========================
# RESUME UPLOAD
# =========================
@app.route("/upload_resume", methods=["POST"])
@login_required
def upload_resume():

    file = request.files["resume"]

    if not file or not file.filename.endswith(".pdf"):
        flash("Only PDF allowed.")
        return redirect(url_for("dashboard"))

    path = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
    file.save(path)

    text = ""
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""

    resume = Resume(
        user_id=current_user.id,
        file_name=file.filename,
        extracted_text=text
    )

    db.session.add(resume)
    db.session.commit()

    flash("Resume uploaded.")
    return redirect(url_for("dashboard"))


# =========================
# APPLY (TRACK MANUALLY)
# =========================
@app.route("/apply_job/<int:job_id>")
@login_required
def apply_job(job_id):

    if not Application.query.filter_by(user_id=current_user.id,
                                       job_id=job_id).first():

        app_record = Application(
            user_id=current_user.id,
            job_id=job_id,
            status="Applied"
        )

        db.session.add(app_record)
        db.session.commit()

    return redirect(url_for("applications"))


# =========================
# VIEW APPLICATIONS
# =========================
@app.route("/applications")
@login_required
def applications():
    apps = Application.query.filter_by(user_id=current_user.id).all()
    return render_template("applications.html", apps=apps)


# =========================
# UPDATE STATUS
# =========================
@app.route("/update_status/<int:app_id>", methods=["POST"])
@login_required
def update_status(app_id):

    app_record = Application.query.get_or_404(app_id)

    app_record.status = request.form["status"]
    app_record.notes = request.form["notes"]
    app_record.interview_date = request.form["interview_date"]

    db.session.commit()

    return redirect(url_for("applications"))


# =========================
# BOOKMARK
# =========================
@app.route("/bookmark/<int:job_id>")
@login_required
def bookmark(job_id):

    existing = Bookmark.query.filter_by(
        user_id=current_user.id,
        job_id=job_id
    ).first()

    if not existing:
        new_bookmark = Bookmark(
            user_id=current_user.id,
            job_id=job_id
        )
        db.session.add(new_bookmark)
        db.session.commit()

    return redirect(url_for("dashboard"))


@app.route("/bookmarks")
@login_required
def bookmarks():
    saved = Bookmark.query.filter_by(user_id=current_user.id).all()
    return render_template("bookmarks.html", saved=saved)


# =========================
# RUN APP
# =========================
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
