from flask import Flask, render_template, request, redirect, session, jsonify, send_file
from flask_caching import Cache
from config import Config
from models import db, User, StudentProfile, CompanyProfile, PlacementDrive, Application, PlacementRecord
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
import os

# ----------------------------------------
# APP SETUP
# ----------------------------------------

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)

# Setup caching
cache = Cache(app)

# Create all database tables if they don't exist
with app.app_context():
    db.create_all()

# ----------------------------------------
# CREATE DEFAULT ADMIN (runs once at startup)
# ----------------------------------------

def create_admin():
    """
    Creates a default admin user if no admin exists in the database.
    This ensures there is always one admin to manage the system.
    """
    existing_admin = User.query.filter_by(role="admin").first()

    if not existing_admin:
        admin_user = User(
            name="Admin",
            email="admin@gmail.com",
            password=generate_password_hash("admin123"),
            role="admin",
            is_active=True
        )
        db.session.add(admin_user)
        db.session.commit()

with app.app_context():
    create_admin()

# ----------------------------------------
# DECORATOR: Restrict Access to Admin Only
# ----------------------------------------

def admin_required(f):
    """
    A decorator that protects routes from non-admin users.
    If the user is not logged in or is not an admin, they are redirected to login.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session or session.get("user_role") != "admin":
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function

# ----------------------------------------
# DECORATOR: Restrict Access to Students Only
# ----------------------------------------

def student_required(f):
    """Protects routes so only logged-in students can access them."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session or session.get("user_role") != "student":
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function

# ----------------------------------------
# DECORATOR: Restrict Access to Companies Only
# ----------------------------------------

def company_required(f):
    """Protects routes so only logged-in companies can access them."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session or session.get("user_role") != "company":
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function

# ============================================================
# GENERAL ROUTES (Login, Signup, Dashboard, Logout)
# ============================================================

# ----------------------------------------
# HOME - Redirects to Login Page
# ----------------------------------------

@app.route("/")
def home():
    return redirect("/login")

# ----------------------------------------
# LOGIN - Handles user authentication
# ----------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        email    = request.form["email"]
        password = request.form["password"]

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            if not user.is_active:
                error = "Your account has been deactivated. Contact admin."
            else:
                session["user_id"]   = user.id
                session["user_name"] = user.name
                session["user_role"] = user.role
                return redirect("/dashboard")
        else:
            error = "Invalid email or password"

    return render_template("login.html", error=error, show_navbar=False)

# ----------------------------------------
# SIGNUP
# ----------------------------------------

@app.route("/signup", methods=["GET", "POST"])
def signup():
    error = None
    success = None

    if request.method == "POST":
        name     = request.form["name"]
        email    = request.form["email"]
        password = request.form["password"]
        role     = request.form["role"]

        if role == "admin":
            error = "Admin registration not allowed."
            return render_template("signup.html", error=error, show_navbar=False)

        existing_user = User.query.filter_by(email=email).first()

        if existing_user:
            error = "Email already exists!"
        else:
            new_user = User(
                name=name,
                email=email,
                password=generate_password_hash(password),
                role=role
            )
            db.session.add(new_user)
            db.session.commit()
            success = "Account created successfully! Please login."

    return render_template("signup.html", error=error, success=success, show_navbar=False)

# ----------------------------------------
# DASHBOARD - Redirects user based on their role
# ----------------------------------------

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    role = session.get("user_role")

    if role == "admin":
        return redirect("/admin/dashboard")
    elif role == "company":
        return redirect("/company/dashboard")
    elif role == "student":
        return redirect("/student/dashboard")
    else:
        return redirect("/login")

# ============================================================
# ADMIN ROUTES (All protected with @admin_required)
# ============================================================

# ----------------------------------------
# ADMIN DASHBOARD - Shows system overview stats
# ----------------------------------------

@app.route("/admin/dashboard")
@admin_required
@cache.cached(timeout=60, key_prefix="admin_dashboard")
def admin_dashboard():
    total_students    = StudentProfile.query.count()
    total_companies   = CompanyProfile.query.count()
    total_drives      = PlacementDrive.query.count()
    total_applications = Application.query.count()

    return render_template(
        "admin_dashboard.html",
        total_students=total_students,
        total_companies=total_companies,
        total_drives=total_drives,
        total_applications=total_applications
    )

# ============================================================
# COMPANY MANAGEMENT
# ============================================================

# ----------------------------------------
# VIEW ALL COMPANIES (with search)
# ----------------------------------------

@app.route("/admin/companies")
@admin_required
def view_companies():
    search = request.args.get("search", "").strip()

    if search:
        companies = CompanyProfile.query.filter(
            CompanyProfile.company_name.ilike(f"%{search}%")
        ).all()
    else:
        companies = CompanyProfile.query.all()

    return render_template("admin_companies.html", companies=companies, search=search)

# ----------------------------------------
# APPROVE COMPANY
# ----------------------------------------

@app.route("/admin/company/<int:id>/approve")
@admin_required
def approve_company(id):
    company = CompanyProfile.query.get_or_404(id)
    company.approval_status = "Approved"
    db.session.commit()
    cache.delete("admin_dashboard")
    return redirect("/admin/companies")

# ----------------------------------------
# REJECT COMPANY
# ----------------------------------------

@app.route("/admin/company/<int:id>/reject")
@admin_required
def reject_company(id):
    company = CompanyProfile.query.get_or_404(id)
    company.approval_status = "Rejected"
    db.session.commit()
    cache.delete("admin_dashboard")
    return redirect("/admin/companies")

# ----------------------------------------
# BLACKLIST COMPANY
# ----------------------------------------

@app.route("/admin/company/<int:id>/blacklist")
@admin_required
def blacklist_company(id):
    company = CompanyProfile.query.get_or_404(id)
    company.is_blacklisted = True
    db.session.commit()
    return redirect("/admin/companies")

# ----------------------------------------
# ACTIVATE COMPANY
# ----------------------------------------

@app.route("/admin/company/<int:id>/activate")
@admin_required
def activate_company(id):
    company = CompanyProfile.query.get_or_404(id)
    company.is_blacklisted = False
    db.session.commit()
    return redirect("/admin/companies")

# ============================================================
# PLACEMENT DRIVE MANAGEMENT
# ============================================================

# ----------------------------------------
# VIEW ALL PLACEMENT DRIVES
# ----------------------------------------

@app.route("/admin/drives")
@admin_required
def view_drives():
    drives = PlacementDrive.query.all()
    return render_template("admin_drives.html", drives=drives)

# ----------------------------------------
# APPROVE DRIVE
# ----------------------------------------

@app.route("/admin/drive/<int:id>/approve")
@admin_required
def approve_drive(id):
    drive = PlacementDrive.query.get_or_404(id)
    drive.status = "Approved"
    db.session.commit()
    cache.delete("admin_dashboard")
    return redirect("/admin/drives")

# ----------------------------------------
# REJECT DRIVE
# ----------------------------------------

@app.route("/admin/drive/<int:id>/reject")
@admin_required
def reject_drive(id):
    drive = PlacementDrive.query.get_or_404(id)
    drive.status = "Rejected"
    db.session.commit()
    return redirect("/admin/drives")

# ----------------------------------------
# ADMIN EDIT DRIVE
# ----------------------------------------

@app.route("/admin/drive/<int:id>/edit", methods=["GET", "POST"])
@admin_required
def admin_drive_edit(id):
    drive = PlacementDrive.query.get_or_404(id)

    error   = None
    success = None

    if request.method == "POST":
        job_title    = request.form.get("job_title", "").strip()
        job_desc     = request.form.get("job_description", "").strip()
        elig_branch  = request.form.get("eligibility_branch", "").strip()
        elig_cgpa    = request.form.get("eligibility_cgpa", "").strip()
        elig_year    = request.form.get("eligibility_year", "").strip()
        deadline_str = request.form.get("application_deadline", "").strip()
        status       = request.form.get("status", "").strip()

        if not job_title or not job_desc or not deadline_str:
            error = "Job title, description, and deadline are required."
        else:
            drive.job_title            = job_title
            drive.job_description      = job_desc
            drive.eligibility_branch   = elig_branch
            drive.eligibility_cgpa     = float(elig_cgpa) if elig_cgpa else None
            drive.eligibility_year     = int(elig_year) if elig_year else None
            drive.application_deadline = datetime.strptime(deadline_str, "%Y-%m-%d").date()
            drive.status               = status

            db.session.commit()
            cache.delete("admin_dashboard")
            success = "Drive updated successfully!"

    return render_template(
        "admin_drive_edit.html",
        drive=drive,
        error=error,
        success=success
    )

# ----------------------------------------
# CLOSE DRIVE - Admin can close a drive
# ----------------------------------------

@app.route("/admin/drive/<int:id>/close")
@admin_required
def close_drive(id):
    drive = PlacementDrive.query.get_or_404(id)
    drive.status = "Closed"
    db.session.commit()
    cache.delete("admin_dashboard")
    return redirect("/admin/drives")

# ----------------------------------------
# ADMIN DELETE DRIVE
# ----------------------------------------

@app.route("/admin/drive/<int:id>/delete")
@admin_required
def admin_drive_delete(id):
    drive = PlacementDrive.query.get_or_404(id)

    # Delete related records first
    Application.query.filter_by(drive_id=id).delete()
    PlacementRecord.query.filter_by(drive_id=id).delete()

    db.session.delete(drive)
    db.session.commit()
    cache.delete("admin_dashboard")

    return redirect("/admin/drives")
    

# ============================================================
# STUDENT MANAGEMENT
# ============================================================

# ----------------------------------------
# VIEW ALL STUDENTS (with search)
# ----------------------------------------

@app.route("/admin/students")
@admin_required
def view_students():
    search = request.args.get("search", "").strip()

    if search:
        # Search by name or email through the User table
        users = User.query.filter(
            User.role == "student",
            (User.name.ilike(f"%{search}%")) | (User.email.ilike(f"%{search}%"))
        ).all()
        student_ids = [u.id for u in users]
        students = StudentProfile.query.filter(
            StudentProfile.user_id.in_(student_ids)
        ).all()
    else:
        students = StudentProfile.query.all()

    return render_template("admin_students.html", students=students, search=search)

# ----------------------------------------
# BLACKLIST STUDENT
# ----------------------------------------

@app.route("/admin/student/<int:id>/blacklist")
@admin_required
def blacklist_student(id):
    student = StudentProfile.query.get_or_404(id)
    student.is_blacklisted = True
    db.session.commit()
    return redirect("/admin/students")

# ----------------------------------------
# ACTIVATE STUDENT
# ----------------------------------------

@app.route("/admin/student/<int:id>/activate")
@admin_required
def activate_student(id):
    student = StudentProfile.query.get_or_404(id)
    student.is_blacklisted = False
    db.session.commit()
    return redirect("/admin/students")

# ============================================================
# APPLICATION MANAGEMENT
# ============================================================

# ----------------------------------------
# VIEW ALL APPLICATIONS
# ----------------------------------------

@app.route("/admin/applications")
@admin_required
def view_applications():
    applications = Application.query.all()
    return render_template("admin_applications.html", applications=applications)

# ============================================================
# ADMIN REPORTS
# ============================================================

# ----------------------------------------
# ADMIN REPORTS PAGE
# ----------------------------------------

@app.route("/admin/reports")
@admin_required
def admin_reports():
    from datetime import date, timedelta

    today = date.today()
    first_of_month = today.replace(day=1)

    # Monthly stats
    drives_this_month = PlacementDrive.query.filter(
        PlacementDrive.created_at >= datetime.combine(first_of_month, datetime.min.time())
    ).all()

    total_drives_month = len(drives_this_month)
    drive_ids = [d.id for d in drives_this_month]

    apps_this_month = Application.query.filter(
        Application.drive_id.in_(drive_ids)
    ).all() if drive_ids else []

    total_applied_month  = len(apps_this_month)
    total_selected_month = len([a for a in apps_this_month if a.status == "Selected"])

    # Overall stats
    total_students    = StudentProfile.query.count()
    total_companies   = CompanyProfile.query.count()
    total_drives      = PlacementDrive.query.count()
    total_applications = Application.query.count()
    total_selected    = Application.query.filter_by(status="Selected").count()

    return render_template(
        "admin_reports.html",
        total_drives_month=total_drives_month,
        total_applied_month=total_applied_month,
        total_selected_month=total_selected_month,
        total_students=total_students,
        total_companies=total_companies,
        total_drives=total_drives,
        total_applications=total_applications,
        total_selected=total_selected,
        drives_this_month=drives_this_month,
        current_month=first_of_month.strftime("%B %Y")
    )

# ============================================================
# STUDENT ROUTES (All protected with @student_required)
# ============================================================

# ----------------------------------------
# STUDENT DASHBOARD
# ----------------------------------------

@app.route("/student/dashboard")
@student_required
def student_dashboard():
    profile = StudentProfile.query.filter_by(user_id=session["user_id"]).first()

    total_drives = PlacementDrive.query.filter_by(status="Approved").count()

    if profile:
        my_applications  = len(profile.applications)
        profile_status   = "Complete"
        selected_count   = len([a for a in profile.applications if a.status == "Selected"])
    else:
        my_applications = 0
        profile_status  = "Incomplete"
        selected_count  = 0

    return render_template(
        "student_dashboard.html",
        total_drives=total_drives,
        my_applications=my_applications,
        profile_status=profile_status,
        selected_count=selected_count
    )

# ----------------------------------------
# STUDENT PROFILE
# ----------------------------------------

@app.route("/student/profile", methods=["GET", "POST"])
@student_required
def student_profile():
    success = None
    error   = None
    profile = StudentProfile.query.filter_by(user_id=session["user_id"]).first()

    if request.method == "POST":
        branch = request.form.get("branch", "").strip()
        year   = request.form.get("year", "").strip()
        cgpa   = request.form.get("cgpa", "").strip()
        phone  = request.form.get("phone", "").strip()
        resume = request.form.get("resume", "").strip()

        if not branch or not year or not cgpa:
            error = "Branch, Year, and CGPA are required."
        else:
            if not profile:
                profile = StudentProfile(user_id=session["user_id"])
                db.session.add(profile)

            profile.branch = branch
            profile.year   = int(year)
            profile.cgpa   = float(cgpa)
            profile.phone  = phone
            profile.resume = resume

            db.session.commit()
            success = "Profile saved successfully!"

    return render_template("student_profile.html", profile=profile, success=success, error=error)

# ----------------------------------------
# BROWSE DRIVES
# ----------------------------------------

@app.route("/student/drives")
@student_required
def student_drives():
    profile = StudentProfile.query.filter_by(user_id=session["user_id"]).first()

    search = request.args.get("search", "").strip()
    branch_filter = request.args.get("branch", "").strip()

    query = PlacementDrive.query.filter_by(status="Approved")

    if search:
        query = query.filter(
            PlacementDrive.job_title.ilike(f"%{search}%")
        )

    if branch_filter:
        query = query.filter(
            PlacementDrive.eligibility_branch.ilike(f"%{branch_filter}%")
        )

    drives = query.all()

    applied_ids = []
    if profile:
        applied_ids = [app.drive_id for app in profile.applications]

    return render_template(
        "student_drives.html",
        drives=drives,
        applied_ids=applied_ids,
        profile=profile,
        search=search,
        branch_filter=branch_filter
    )

# ----------------------------------------
# APPLY TO A DRIVE
# ----------------------------------------

@app.route("/student/drive/<int:id>/apply")
@student_required
def apply_drive(id):
    profile = StudentProfile.query.filter_by(user_id=session["user_id"]).first()

    if not profile:
        return redirect("/student/profile")

    if profile.is_blacklisted:
        session["apply_error"] = "You are blacklisted and cannot apply."
        return redirect("/student/drives")

    drive = PlacementDrive.query.get_or_404(id)

    # Check CGPA only if company set it greater than 0
    if drive.eligibility_cgpa and drive.eligibility_cgpa > 0:
        if profile.cgpa and profile.cgpa < drive.eligibility_cgpa:
            session["apply_error"] = f"You need minimum CGPA of {drive.eligibility_cgpa} to apply for {drive.job_title}."
            return redirect("/student/drives")

    # Check Year only if company set it greater than 0
    if drive.eligibility_year and drive.eligibility_year > 0:
        if profile.year and profile.year != drive.eligibility_year:
            session["apply_error"] = f"This drive is only for Year {drive.eligibility_year} students."
            return redirect("/student/drives")

    # Check Branch only if company set it
    if drive.eligibility_branch and drive.eligibility_branch.strip() != "":
        if profile.branch and drive.eligibility_branch.lower() not in profile.branch.lower():
            session["apply_error"] = f"This drive is only for {drive.eligibility_branch} branch students."
            return redirect("/student/drives")

    # Prevent applying to same drive twice
    existing = Application.query.filter_by(
        student_id=profile.id, drive_id=id
    ).first()

    if existing:
        session["apply_error"] = "You have already applied to this drive."
        return redirect("/student/applications")

    # All good - create application
    new_application = Application(
        student_id=profile.id,
        drive_id=id,
        status="Applied"
    )
    db.session.add(new_application)
    db.session.commit()

    session["apply_success"] = f"Successfully applied for {drive.job_title}!"
    return redirect("/student/applications")

# ----------------------------------------
# MY APPLICATIONS
# ----------------------------------------

@app.route("/student/applications")
@student_required
def student_applications():
    profile = StudentProfile.query.filter_by(user_id=session["user_id"]).first()
    applications = profile.applications if profile else []
    return render_template("student_applications.html", applications=applications)

# ----------------------------------------
# APPLICATION DETAILS - Student views
# company details after shortlist/selection
# ----------------------------------------

@app.route("/student/application/<int:id>/details")
@student_required
def student_application_details(id):
    profile     = StudentProfile.query.filter_by(
        user_id=session["user_id"]
    ).first()

    application = Application.query.get_or_404(id)

    # Security check - make sure this application
    # belongs to the logged in student
    if not profile or application.student_id != profile.id:
        return redirect("/student/applications")

    # Only allow if shortlisted or selected
    if application.status not in ["Shortlisted", "Selected"]:
        return redirect("/student/applications")

    drive   = application.drive
    company = drive.company

    return render_template(
        "student_application_details.html",
        application=application,
        drive=drive,
        company=company
    )

# ----------------------------------------
# EXPORT APPLICATIONS AS CSV (Async Job)
# ----------------------------------------

@app.route("/student/export")
@student_required
def export_applications():
    from tasks import export_student_csv

    profile  = StudentProfile.query.filter_by(user_id=session["user_id"]).first()
    user     = User.query.get(session["user_id"])

    if not profile:
        return redirect("/student/profile")

    # Trigger async celery task
    export_student_csv.delay(profile.id, user.email, user.name)

    return render_template("export_triggered.html")

# ============================================================
# COMPANY ROUTES (All protected with @company_required)
# ============================================================

# ----------------------------------------
# COMPANY DASHBOARD
# ----------------------------------------

@app.route("/company/dashboard")
@company_required
def company_dashboard():
    profile = CompanyProfile.query.filter_by(user_id=session["user_id"]).first()

    total_drives       = 0
    total_applications = 0
    approval_status    = "Profile Not Created"

    if profile:
        approval_status    = profile.approval_status
        total_drives       = len(profile.drives)

        for drive in profile.drives:
            total_applications += len(drive.applications)

    return render_template(
        "company_dashboard.html",
        total_drives=total_drives,
        total_applications=total_applications,
        approval_status=approval_status,
        profile=profile
    )

# ----------------------------------------
# COMPANY PROFILE
# ----------------------------------------

@app.route("/company/profile", methods=["GET", "POST"])
@company_required
def company_profile():
    success = None
    error   = None
    profile = CompanyProfile.query.filter_by(user_id=session["user_id"]).first()

    if request.method == "POST":
        company_name = request.form.get("company_name", "").strip()
        hr_contact   = request.form.get("hr_contact", "").strip()
        website      = request.form.get("website", "").strip()
        description  = request.form.get("description", "").strip()

        if not company_name:
            error = "Company name is required."
        else:
            if not profile:
                profile = CompanyProfile(user_id=session["user_id"])
                db.session.add(profile)

            profile.company_name = company_name
            profile.hr_contact   = hr_contact
            profile.website      = website
            profile.description  = description

            db.session.commit()
            cache.delete("admin_dashboard")
            success = "Profile saved successfully!"

    return render_template("company_profile.html", profile=profile, success=success, error=error)

# ----------------------------------------
# POST NEW DRIVE
# ----------------------------------------

@app.route("/company/drive/new", methods=["GET", "POST"])
@company_required
def company_drive_new():
    profile = CompanyProfile.query.filter_by(user_id=session["user_id"]).first()

    if not profile:
        return redirect("/company/profile")

    if profile.is_blacklisted or profile.approval_status != "Approved":
        return render_template("company_drive_form.html", profile=profile, blocked=True)

    error = None

    if request.method == "POST":
        job_title    = request.form.get("job_title", "").strip()
        job_desc     = request.form.get("job_description", "").strip()
        elig_branch  = request.form.get("eligibility_branch", "").strip()
        elig_cgpa    = request.form.get("eligibility_cgpa", "").strip()
        elig_year    = request.form.get("eligibility_year", "").strip()
        deadline_str = request.form.get("application_deadline", "").strip()

        if not job_title or not job_desc or not deadline_str:
            error = "Job title, description, and deadline are required."
        else:
            new_drive = PlacementDrive(
                company_id           = profile.id,
                job_title            = job_title,
                job_description      = job_desc,
                eligibility_branch   = elig_branch,
                eligibility_cgpa     = float(elig_cgpa) if elig_cgpa else None,
                eligibility_year     = int(elig_year) if elig_year else None,
                application_deadline = datetime.strptime(deadline_str, "%Y-%m-%d").date(),
                status               = "Pending"
            )
            db.session.add(new_drive)
            db.session.commit()
            cache.delete("admin_dashboard")
            return redirect("/company/drives")

    return render_template("company_drive_form.html", profile=profile, blocked=False, error=error)

# ----------------------------------------
# MY DRIVES
# ----------------------------------------

@app.route("/company/drives")
@company_required
def company_drives():
    profile = CompanyProfile.query.filter_by(user_id=session["user_id"]).first()
    drives  = profile.drives if profile else []
    return render_template("company_drives.html", drives=drives, profile=profile)

# ----------------------------------------
# VIEW APPLICANTS for a specific drive
# ----------------------------------------

@app.route("/company/drive/<int:id>/applicants")
@company_required
def company_applicants(id):
    profile = CompanyProfile.query.filter_by(user_id=session["user_id"]).first()
    drive   = PlacementDrive.query.get_or_404(id)

    if not profile or drive.company_id != profile.id:
        return redirect("/company/drives")

    applications = drive.applications
    return render_template("company_applicants.html", drive=drive, applications=applications)

# ----------------------------------------
# UPDATE APPLICATION STATUS
# ----------------------------------------

@app.route("/company/application/<int:id>/<status>")
@company_required
def update_application_status(id, status):
    profile     = CompanyProfile.query.filter_by(user_id=session["user_id"]).first()
    application = Application.query.get_or_404(id)

    if not profile or application.drive.company_id != profile.id:
        return redirect("/company/drives")

    # Added Applied so undo works
    if status in ["Applied", "Shortlisted", "Selected", "Rejected"]:
        application.status = status

        if status == "Selected":
            # Create placement record when selected
            existing_record = PlacementRecord.query.filter_by(
                student_id=application.student_id,
                drive_id=application.drive_id
            ).first()

            if not existing_record:
                record = PlacementRecord(
                    student_id=application.student_id,
                    drive_id=application.drive_id,
                    company_id=profile.id
                )
                db.session.add(record)

        else:
            # If status changed away from Selected
            # remove placement record if it exists
            existing_record = PlacementRecord.query.filter_by(
                student_id=application.student_id,
                drive_id=application.drive_id
            ).first()

            if existing_record:
                db.session.delete(existing_record)

        db.session.commit()

    return redirect(f"/company/drive/{application.drive_id}/applicants")

# ----------------------------------------
# EDIT DRIVE - Company can edit their drive
# ----------------------------------------

@app.route("/company/drive/<int:id>/edit", methods=["GET", "POST"])
@company_required
def company_drive_edit(id):
    profile = CompanyProfile.query.filter_by(user_id=session["user_id"]).first()
    drive = PlacementDrive.query.get_or_404(id)

    # Security check - make sure this drive belongs to this company
    if not profile or drive.company_id != profile.id:
        return redirect("/company/drives")

    # Blacklisted or not approved companies cannot edit
    if profile.is_blacklisted or profile.approval_status != "Approved":
        return redirect("/company/drives")

    error = None
    success = None

    if request.method == "POST":
        job_title    = request.form.get("job_title", "").strip()
        job_desc     = request.form.get("job_description", "").strip()
        elig_branch  = request.form.get("eligibility_branch", "").strip()
        elig_cgpa    = request.form.get("eligibility_cgpa", "").strip()
        elig_year    = request.form.get("eligibility_year", "").strip()
        deadline_str = request.form.get("application_deadline", "").strip()

        if not job_title or not job_desc or not deadline_str:
            error = "Job title, description, and deadline are required."
        else:
            drive.job_title            = job_title
            drive.job_description      = job_desc
            drive.eligibility_branch   = elig_branch
            drive.eligibility_cgpa     = float(elig_cgpa) if elig_cgpa else None
            drive.eligibility_year     = int(elig_year) if elig_year else None
            drive.application_deadline = datetime.strptime(deadline_str, "%Y-%m-%d").date()
            drive.status               = "Pending"  # Reset to pending after edit

            db.session.commit()
            cache.delete("admin_dashboard")
            success = "Drive updated successfully! Waiting for admin approval again."

    return render_template(
        "company_drive_edit.html",
        drive=drive,
        profile=profile,
        error=error,
        success=success
    )


# ----------------------------------------
# DELETE DRIVE - Company can delete their drive
# ----------------------------------------

@app.route("/company/drive/<int:id>/delete")
@company_required
def company_drive_delete(id):
    profile = CompanyProfile.query.filter_by(user_id=session["user_id"]).first()
    drive   = PlacementDrive.query.get_or_404(id)

    # Security check
    if not profile or drive.company_id != profile.id:
        return redirect("/company/drives")

    # Delete all applications for this drive first
    Application.query.filter_by(drive_id=id).delete()
    PlacementRecord.query.filter_by(drive_id=id).delete()

    db.session.delete(drive)
    db.session.commit()
    cache.delete("admin_dashboard")

    return redirect("/company/drives")

# ============================================================
# AUTH - LOGOUT
# ============================================================

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ============================================================
# RUN THE APP
# ============================================================

if __name__ == "__main__":
    app.run(debug=True)