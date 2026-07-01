from celery import Celery
from celery.schedules import crontab
import csv
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime, date, timedelta

# Create celery app
celery = Celery("tasks", broker="redis://localhost:6379/0", backend="redis://localhost:6379/0")

celery.conf.beat_schedule = {
    # Run daily at 8 AM
    "daily-deadline-reminders": {
        "task": "tasks.send_deadline_reminders",
        "schedule": crontab(hour=8, minute=0),
    },
    # Run on 1st of every month at 9 AM
    "monthly-activity-report": {
        "task": "tasks.send_monthly_report",
        "schedule": crontab(hour=9, minute=0, day_of_month=1),
    },
}

celery.conf.timezone = "UTC"


def send_email(to_email, subject, body, attachment_path=None):
    """Helper to send email via Gmail SMTP"""
    from_email = "your_email@gmail.com"
    password = "your_app_password"

    msg = MIMEMultipart()
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html"))

    if attachment_path and os.path.exists(attachment_path):
        with open(attachment_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename={os.path.basename(attachment_path)}",
            )
            msg.attach(part)

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(from_email, password)
        server.sendmail(from_email, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False


@celery.task
def send_deadline_reminders():
    """
    Runs daily - sends email to students about drives closing in next 3 days
    """
    from app import app
    from models import StudentProfile, PlacementDrive, Application, User

    with app.app_context():
        today = date.today()
        upcoming = today + timedelta(days=3)

        # Get drives closing within 3 days
        drives = PlacementDrive.query.filter(
            PlacementDrive.status == "Approved",
            PlacementDrive.application_deadline >= today,
            PlacementDrive.application_deadline <= upcoming,
        ).all()

        if not drives:
            return "No upcoming deadlines"

        students = StudentProfile.query.filter_by(is_blacklisted=False).all()

        for student in students:
            applied_ids = [app.drive_id for app in student.applications]
            user = User.query.get(student.user_id)

            if not user:
                continue

            reminder_drives = [d for d in drives if d.id not in applied_ids]

            if not reminder_drives:
                continue

            drive_list = ""
            for d in reminder_drives:
                drive_list += f"""
                <li>
                    <strong>{d.job_title}</strong> at {d.company.company_name}
                    - Deadline: {d.application_deadline}
                </li>
                """

            body = f"""
            <h3>Hi {user.name},</h3>
            <p>The following placement drives are closing soon. Don't miss out!</p>
            <ul>{drive_list}</ul>
            <p>Login to the Placement Portal to apply now.</p>
            """

            send_email(user.email, "Placement Drive Deadline Reminder", body)

    return "Reminders sent"


@celery.task
def send_monthly_report():
    """
    Runs on 1st of every month - sends HTML report to admin
    """
    from app import app
    from models import PlacementDrive, Application, StudentProfile, User

    with app.app_context():
        today = date.today()
        first_of_month = today.replace(day=1)
        last_month_end = first_of_month - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)

        # Drives created last month
        drives = PlacementDrive.query.filter(
            PlacementDrive.created_at >= datetime.combine(last_month_start, datetime.min.time()),
            PlacementDrive.created_at <= datetime.combine(last_month_end, datetime.max.time()),
        ).all()

        total_drives = len(drives)
        drive_ids = [d.id for d in drives]

        # Applications for those drives
        applications = Application.query.filter(
            Application.drive_id.in_(drive_ids)
        ).all() if drive_ids else []

        total_applied = len(applications)
        total_selected = len([a for a in applications if a.status == "Selected"])

        report_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h2>Monthly Placement Activity Report</h2>
            <h4>Period: {last_month_start.strftime('%B %Y')}</h4>
            <hr>
            <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse;">
                <tr style="background:#333;color:#fff;">
                    <th>Metric</th>
                    <th>Count</th>
                </tr>
                <tr>
                    <td>Drives Conducted</td>
                    <td>{total_drives}</td>
                </tr>
                <tr>
                    <td>Students Applied</td>
                    <td>{total_applied}</td>
                </tr>
                <tr>
                    <td>Students Selected</td>
                    <td>{total_selected}</td>
                </tr>
            </table>
            <br>
            <h4>Drive Details:</h4>
            <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse;">
                <tr style="background:#333;color:#fff;">
                    <th>Job Title</th>
                    <th>Company</th>
                    <th>Applicants</th>
                    <th>Status</th>
                </tr>
                {"".join([
                    f"<tr><td>{d.job_title}</td><td>{d.company.company_name}</td>"
                    f"<td>{len(d.applications)}</td><td>{d.status}</td></tr>"
                    for d in drives
                ])}
            </table>
            <br>
            <p style="color:gray;font-size:12px;">
                Generated on {today.strftime('%d %B %Y')} by Placement Portal System
            </p>
        </body>
        </html>
        """

        admin_user = User.query.filter_by(role="admin").first()
        if admin_user:
            send_email(
                admin_user.email,
                f"Monthly Placement Report - {last_month_start.strftime('%B %Y')}",
                report_html,
            )

    return "Monthly report sent"


@celery.task(bind=True)
def export_student_csv(self, student_profile_id, user_email, user_name):
    """
    User-triggered async task - exports student applications to CSV
    and sends it via email
    """
    from app import app
    from models import StudentProfile, Application, PlacementDrive, CompanyProfile

    with app.app_context():
        profile = StudentProfile.query.get(student_profile_id)

        if not profile:
            return "Student not found"

        # Create export folder if not exists
        export_dir = os.path.join("static", "exports")
        os.makedirs(export_dir, exist_ok=True)

        filename = f"applications_{student_profile_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
        filepath = os.path.join(export_dir, filename)

        with open(filepath, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(
                ["Application ID", "Student ID", "Company Name", "Drive Title",
                 "Application Status", "Application Date"]
            )

            for app_record in profile.applications:
                drive = PlacementDrive.query.get(app_record.drive_id)
                company = CompanyProfile.query.get(drive.company_id) if drive else None
                writer.writerow([
                    app_record.id,
                    profile.id,
                    company.company_name if company else "N/A",
                    drive.job_title if drive else "N/A",
                    app_record.status,
                    app_record.application_date.strftime("%Y-%m-%d %H:%M"),
                ])

        # Email the CSV
        body = f"""
        <h3>Hi {user_name},</h3>
        <p>Your placement application history has been exported successfully.</p>
        <p>Please find the CSV file attached to this email.</p>
        <p>Thank you for using the Placement Portal.</p>
        """

        send_email(user_email, "Your Application Export is Ready", body, filepath)

    return f"CSV exported and sent to {user_email}"