from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

# ======================================================
# USER TABLE (Unified Model for Admin, Company, Student)
# ======================================================

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

    # Role: admin / company / student
    role = db.Column(db.String(20), nullable=False)

    # Account control
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    student_profile = db.relationship("StudentProfile", backref="user", uselist=False)
    company_profile = db.relationship("CompanyProfile", backref="user", uselist=False)


# ======================================================
# STUDENT PROFILE
# ======================================================

class StudentProfile(db.Model):
    __tablename__ = "student_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    branch = db.Column(db.String(100))
    year = db.Column(db.Integer)
    cgpa = db.Column(db.Float)
    phone = db.Column(db.String(15))
    resume = db.Column(db.String(200))  # file path

    is_blacklisted = db.Column(db.Boolean, default=False)

    applications = db.relationship("Application", backref="student", lazy=True)
    placement_records = db.relationship("PlacementRecord", backref="student", lazy=True)


# ======================================================
# COMPANY PROFILE
# ======================================================

class CompanyProfile(db.Model):
    __tablename__ = "company_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    company_name = db.Column(db.String(150), nullable=False)
    hr_contact = db.Column(db.String(100))
    website = db.Column(db.String(200))
    description = db.Column(db.Text)

    # Approval by admin
    approval_status = db.Column(db.String(20), default="Pending")
    # Pending / Approved / Rejected

    is_blacklisted = db.Column(db.Boolean, default=False)

    drives = db.relationship("PlacementDrive", backref="company", lazy=True)
    placement_records = db.relationship("PlacementRecord", backref="company", lazy=True)


# ======================================================
# PLACEMENT DRIVE
# ======================================================

class PlacementDrive(db.Model):
    __tablename__ = "placement_drives"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("company_profiles.id"), nullable=False)

    job_title = db.Column(db.String(150), nullable=False)
    job_description = db.Column(db.Text, nullable=False)

    eligibility_branch = db.Column(db.String(100))
    eligibility_cgpa = db.Column(db.Float)
    eligibility_year = db.Column(db.Integer)

    application_deadline = db.Column(db.Date, nullable=False)

    status = db.Column(db.String(20), default="Pending")
    # Pending / Approved / Rejected / Closed

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    applications = db.relationship("Application", backref="drive", lazy=True)
    placement_records = db.relationship("PlacementRecord", backref="drive", lazy=True)


# ======================================================
# APPLICATION TABLE
# ======================================================

class Application(db.Model):
    __tablename__ = "applications"

    id = db.Column(db.Integer, primary_key=True)

    student_id = db.Column(db.Integer, db.ForeignKey("student_profiles.id"), nullable=False)
    drive_id = db.Column(db.Integer, db.ForeignKey("placement_drives.id"), nullable=False)

    application_date = db.Column(db.DateTime, default=datetime.utcnow)

    status = db.Column(db.String(20), default="Applied")
    # Applied / Shortlisted / Selected / Rejected

    # Prevent duplicate application
    __table_args__ = (
        db.UniqueConstraint("student_id", "drive_id", name="unique_application"),
    )


# ======================================================
# PLACEMENT RECORD (Final Selected Students)
# ======================================================

class PlacementRecord(db.Model):
    __tablename__ = "placement_records"

    id = db.Column(db.Integer, primary_key=True)

    student_id = db.Column(db.Integer, db.ForeignKey("student_profiles.id"), nullable=False)
    drive_id = db.Column(db.Integer, db.ForeignKey("placement_drives.id"), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey("company_profiles.id"), nullable=False)

    package = db.Column(db.String(50))
    placed_at = db.Column(db.DateTime, default=datetime.utcnow)