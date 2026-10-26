import logging
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.urls import reverse, NoReverseMatch

logger = logging.getLogger(__name__)


# Fetch base domain from request or settings
def _get_base_url(request=None):
    if request is not None:
        return f"{request.scheme}://{request.get_host()}".rstrip('/')

    site_url = getattr(settings, 'SITE_URL', None)
    if site_url:
        return site_url.rstrip('/')

    trusted_origins = getattr(settings, 'CSRF_TRUSTED_ORIGINS', [])
    if trusted_origins:
        return trusted_origins[0].rstrip('/')

    allowed_hosts = [
        h for h in getattr(settings, 'ALLOWED_HOSTS', [])
        if h not in ('*', 'localhost', '127.0.0.1', '[::1]')
    ]
    if allowed_hosts:
        host = allowed_hosts[0].lstrip('.')
        scheme = 'http' if getattr(settings, 'DEBUG', False) else 'https'
        return f"{scheme}://{host}"

    # Local development fallback
    return "http://127.0.0.1:2017"


# Dynamic URL using Django reverse() + fallback path
def _build_url(fallback_path="", url_name=None, url_kwargs=None, request=None):
    resolved_path = fallback_path
    if url_name:
        try:
            resolved_path = reverse(url_name, kwargs=url_kwargs or {})
        except NoReverseMatch:
            resolved_path = fallback_path

    if not resolved_path.startswith('/'):
        resolved_path = f"/{resolved_path}"

    if request is not None:
        return request.build_absolute_uri(resolved_path)

    return f"{_get_base_url()}{resolved_path}"


# Resolve user name
def _resolve_name_and_username(user_or_username):
    from django.contrib.auth import get_user_model
    User = get_user_model()

    user = None
    raw_username = ""

    if isinstance(user_or_username, User):
        user = user_or_username
        raw_username = user.username
    elif isinstance(user_or_username, str):
        raw_username = user_or_username.strip().lstrip('@')
        try:
            user = User.objects.filter(username__iexact=raw_username).first()
        except Exception:
            user = None
    elif hasattr(user_or_username, 'username'):
        raw_username = getattr(user_or_username, 'username', '')
        user = user_or_username

    display_name = ""
    if user:
        portfolio = getattr(user, 'student_portfolio', None)
        if portfolio and getattr(portfolio, 'full_name', None) and portfolio.full_name.strip():
            display_name = portfolio.full_name.strip()
        elif hasattr(user, 'get_full_name') and user.get_full_name() and user.get_full_name().strip():
            display_name = user.get_full_name().strip()
        elif hasattr(user, 'first_name') and user.first_name and user.first_name.strip():
            display_name = user.first_name.strip()
        else:
            comm = getattr(user, 'community_profile', None)
            if comm and comm.group_name and comm.group_name.strip():
                display_name = comm.group_name.strip()

    if not display_name:
        display_name = f"@{raw_username}" if raw_username else "Student"

    return display_name, raw_username


# Send email helper
def _send_bcet_email(recipient_email, subject, plain_message, html_content):
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'githubsahil4@gmail.com')
    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=from_email,
            to=[recipient_email]
        )
        if html_content:
            msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        return True, None
    except Exception as e:
        logger.error(f"Failed to send email to {recipient_email}: {e}")
        return False, str(e)


# Simple base template
def _get_base_email_html(title, body_paragraphs, otp_code=None, cta_text=None, cta_url=None):
    paragraphs_html = "".join([
        f'<p style="font-size: 15px; line-height: 1.5; color: #333333; margin: 10px 0;">{p}</p>'
        for p in body_paragraphs
    ])

    otp_html = ""
    if otp_code:
        otp_html = f"""
        <div style="margin: 20px 0; padding: 14px 20px; background-color: #f1f5f9; border-left: 4px solid #0284c7; border-radius: 4px;">
            <p style="margin: 0 0 6px; font-size: 13px; color: #64748b; font-weight: 600; text-transform: uppercase;">Verification Code</p>
            <p style="margin: 0; font-size: 28px; font-weight: bold; letter-spacing: 5px; color: #0284c7; font-family: monospace;">{otp_code}</p>
            <p style="margin: 6px 0 0; font-size: 12px; color: #94a3b8;">Valid for 10 minutes. Do not share this code.</p>
        </div>
        """

    cta_html = ""
    if cta_text and cta_url:
        cta_html = f"""
        <p style="margin: 20px 0;">
            <a href="{cta_url}" style="display: inline-block; padding: 10px 20px; background-color: #0284c7; color: #ffffff; text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 14px;">
                {cta_text}
            </a>
        </p>
        """

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{title}</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 24px; color: #333333;">
    <div style="max-width: 560px; margin: 0 auto; background: #ffffff; padding: 28px; border: 1px solid #e2e8f0; border-radius: 8px;">
        <h1 style="font-size: 20px; color: #0284c7; margin: 0 0 16px 0; border-bottom: 2px solid #f1f5f9; padding-bottom: 12px;">BCETHub</h1>
        <h2 style="font-size: 17px; color: #0f172a; margin: 0 0 14px 0;">{title}</h2>
        {paragraphs_html}
        {otp_html}
        {cta_html}
        <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 24px 0 14px 0;">
        <p style="font-size: 12px; color: #94a3b8; margin: 0 0 4px 0;">Bengal College of Engineering & Technology (BCET) - Automated notification.</p>
        <p style="font-size: 12px; color: #94a3b8; margin: 0;">Developer: <a href="https://instagram.com/rishabhsahill" target="_blank" rel="noopener noreferrer" style="color: #0284c7; text-decoration: none; font-weight: 600;">@rishabhsahill</a></p>
    </div>
</body>
</html>"""
    return html


# Signup OTP
def send_signup_otp_email(recipient_email, user_or_username, otp, request=None):
    display_name, username = _resolve_name_and_username(user_or_username)
    subject = "BCETHub - Account Verification OTP"
    plain_message = (
        f"Hello {display_name},\n\n"
        f"Your verification OTP code for creating your BCETHub portfolio is: {otp}\n\n"
        f"This code will expire in 10 minutes.\n\n"
        f"Bengal College of Engineering & Technology (BCET) - Automated notification.\n"
        f"Developer: @rishabhsahill (https://instagram.com/rishabhsahill)"
    )
    html_content = _get_base_email_html(
        title="Verify Your Account",
        body_paragraphs=[
            f"Hello <strong>{display_name}</strong>,",
            "Thank you for signing up on BCETHub. Please use the verification code below to activate your student portfolio account:"
        ],
        otp_code=otp
    )
    return _send_bcet_email(recipient_email, subject, plain_message, html_content)


# Verification success
def send_verification_success_email(recipient_email, user_or_username, request=None):
    display_name, username = _resolve_name_and_username(user_or_username)
    login_url = _build_url(
        fallback_path="/student/login/",
        url_name="student_login",
        request=request
    )
    subject = "BCETHub - Email Verified Successfully"
    plain_message = (
        f"Hello {display_name},\n\n"
        f"Your GDG BCET email has been successfully verified. Your portfolio account is now active.\n"
        f"Sign in here: {login_url}\n\n"
        f"Welcome aboard!\nBCETHub Team\n\n"
        f"Bengal College of Engineering & Technology (BCET) - Automated notification.\n"
        f"Developer: @rishabhsahill (https://instagram.com/rishabhsahill)"
    )
    html_content = _get_base_email_html(
        title="Email Verified Successfully",
        body_paragraphs=[
            f"Hello <strong>{display_name}</strong>,",
            "Your official email address has been successfully verified. Your BCETHub student portfolio account is now fully active."
        ],
        cta_text="Sign In to BCETHub",
        cta_url=login_url
    )
    return _send_bcet_email(recipient_email, subject, plain_message, html_content)


# Welcome email
def send_welcome_email(recipient_email, user_or_username, request=None):
    display_name, username = _resolve_name_and_username(user_or_username)
    profile_url = _build_url(
        fallback_path=f"/profile/{username}/",
        url_name="student_portfolio_profile",
        url_kwargs={"username": username},
        request=request
    )
    subject = f"Welcome to BCETHub, {display_name}!"
    plain_message = (
        f"Hello {display_name},\n\n"
        f"Welcome to the BCETHub student portfolio platform!\n\n"
        f"You can now customize your bio, skills, showcase projects, and connect links.\n\n"
        f"Explore at: {profile_url}\n\n"
        f"Best regards,\nBCETHub Community\n\n"
        f"Bengal College of Engineering & Technology (BCET) - Automated notification.\n"
        f"Developer: @rishabhsahill (https://instagram.com/rishabhsahill)"
    )
    html_content = _get_base_email_html(
        title=f"Welcome, {display_name}!",
        body_paragraphs=[
            f"Hi <strong>{display_name}</strong>,",
            "Welcome to the official BCET student portfolio network. Your profile has been created and is ready to customize.",
            "Add your headline, profile picture, skills, GitHub, and social links to stand out."
        ],
        cta_text="View Your Portfolio",
        cta_url=profile_url
    )
    return _send_bcet_email(recipient_email, subject, plain_message, html_content)


# Login alert
def send_login_alert_email(recipient_email, user_or_username, request=None):
    display_name, username = _resolve_name_and_username(user_or_username)
    security_url = _build_url(
        fallback_path="/change-password/",
        url_name="change_password",
        request=request
    )
    subject = "BCETHub - New Sign-In Alert"
    plain_message = (
        f"Hello {display_name},\n\n"
        f"A new sign-in was detected for your BCETHub account.\n"
        f"If this was you, you can ignore this email. If not, please change your password immediately: {security_url}\n\n"
        f"BCETHub Security\n\n"
        f"Bengal College of Engineering & Technology (BCET) - Automated notification.\n"
        f"Developer: @rishabhsahill (https://instagram.com/rishabhsahill)"
    )
    html_content = _get_base_email_html(
        title="New Sign-In Detected",
        body_paragraphs=[
            f"Hello <strong>{display_name}</strong>,",
            "A successful sign-in to your BCETHub portfolio account was just recorded.",
            "If this was you, no action is required. If you did not perform this login, please update your password immediately."
        ],
        cta_text="Account Security",
        cta_url=security_url
    )
    return _send_bcet_email(recipient_email, subject, plain_message, html_content)


# Password reset OTP
def send_password_reset_otp_email(recipient_email, user_or_username, otp, request=None):
    display_name, username = _resolve_name_and_username(user_or_username)
    subject = "BCETHub - Password Reset Code"
    plain_message = (
        f"Hello {display_name},\n\n"
        f"We received a request to reset your BCETHub password.\n"
        f"Your password reset OTP is: {otp}\n\n"
        f"This code will expire in 10 minutes. If you did not request this, please ignore this email.\n\n"
        f"BCETHub Security\n\n"
        f"Bengal College of Engineering & Technology (BCET) - Automated notification.\n"
        f"Developer: @rishabhsahill (https://instagram.com/rishabhsahill)"
    )
    html_content = _get_base_email_html(
        title="Reset Your Password",
        body_paragraphs=[
            f"Hello <strong>{display_name}</strong>,",
            "We received a request to reset the password for your BCETHub account. Use the code below to complete the reset:"
        ],
        otp_code=otp
    )
    return _send_bcet_email(recipient_email, subject, plain_message, html_content)


# Password reset success
def send_password_reset_success_email(recipient_email, user_or_username, request=None):
    display_name, username = _resolve_name_and_username(user_or_username)
    login_url = _build_url(
        fallback_path="/student/login/",
        url_name="student_login",
        request=request
    )
    subject = "BCETHub - Password Changed Successfully"
    plain_message = (
        f"Hello {display_name},\n\n"
        f"Your BCETHub account password has been updated successfully.\n\n"
        f"You can now sign in with your new password: {login_url}\n\n"
        f"BCETHub Security\n\n"
        f"Bengal College of Engineering & Technology (BCET) - Automated notification.\n"
        f"Developer: @rishabhsahill (https://instagram.com/rishabhsahill)"
    )
    html_content = _get_base_email_html(
        title="Password Updated Successfully",
        body_paragraphs=[
            f"Hello <strong>{display_name}</strong>,",
            "The password for your BCETHub account was updated successfully.",
            "If you did not initiate this change, please contact campus support immediately."
        ],
        cta_text="Sign In Now",
        cta_url=login_url
    )
    return _send_bcet_email(recipient_email, subject, plain_message, html_content)


# Email change OTP
def send_email_change_otp(recipient_email, user_or_username, otp, request=None):
    display_name, username = _resolve_name_and_username(user_or_username)
    subject = "BCETHub - Verify Your New Email Address"
    plain_message = (
        f"Hello {display_name},\n\n"
        f"Your verification code to update your BCETHub account email is: {otp}\n\n"
        f"This code will expire in 10 minutes. If you did not request this change, please ignore this email.\n\n"
        f"BCETHub Security\n\n"
        f"Bengal College of Engineering & Technology (BCET) - Automated notification.\n"
        f"Developer: @rishabhsahill (https://instagram.com/rishabhsahill)"
    )
    html_content = _get_base_email_html(
        title="Verify New Email Address",
        body_paragraphs=[
            f"Hello <strong>{display_name}</strong>,",
            "We received a request to update the email address for your BCETHub student portfolio account.",
            "Please enter the verification code below to confirm this email change:"
        ],
        otp_code=otp
    )
    return _send_bcet_email(recipient_email, subject, plain_message, html_content)


# Email change success
def send_email_changed_success(recipient_email, user_or_username, request=None):
    display_name, username = _resolve_name_and_username(user_or_username)
    subject = "BCETHub - Email Address Updated Successfully"
    plain_message = (
        f"Hello {display_name},\n\n"
        f"Your BCETHub account email address has been updated successfully to {recipient_email}.\n\n"
        f"BCETHub Security\n\n"
        f"Bengal College of Engineering & Technology (BCET) - Automated notification.\n"
        f"Developer: @rishabhsahill (https://instagram.com/rishabhsahill)"
    )
    html_content = _get_base_email_html(
        title="Email Updated Successfully",
        body_paragraphs=[
            f"Hello <strong>{display_name}</strong>,",
            f"Your BCETHub account email address has been successfully updated to <strong>{recipient_email}</strong>.",
            "If you did not make this change, please change your password and contact support immediately."
        ]
    )
    return _send_bcet_email(recipient_email, subject, plain_message, html_content)