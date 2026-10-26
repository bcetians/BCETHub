from django.http import request
import os
import datetime
from django.conf import settings
from django.shortcuts import render, redirect, HttpResponse,  get_object_or_404
from django.contrib import messages
from django.contrib.auth import (
    authenticate, login as auth_login, logout as auth_logout,
    get_user_model, update_session_auth_hash
)
from django.utils import timezone
from django.http import JsonResponse
from django.db.models import Q
from .models import (
    Branch, AcademicYear, Pooling, Faculty, InductionProgram, RoutineSlot, 
    MessTiming, DailyMessMenu, Feedback, Section, Notes, Course, Subject, 
    PYQ, Assignment, Notice, Community, CommunityGroupType, 
    CommunityPost, CommunityPostImage, StudentPortfolio
)
from .routine_utils import (
    read_routine_csv, get_routine_file_version, get_filtered_routine_csv,
    evaluate_slot_status
)
from urllib.parse import urlparse
from django.contrib.auth.decorators import login_required
import re
import random
from django.core.mail import send_mail
from .email_content import (
    send_signup_otp_email,
    send_verification_success_email,
    send_welcome_email,
    send_login_alert_email,
    send_password_reset_otp_email,
    send_password_reset_success_email,
    send_email_change_otp,
    send_email_changed_success
)
from django.db.models import Case, When, F, IntegerField
from datetime import date, datetime, time, timedelta
from decouple import config

User = get_user_model()

# restricted username
RESTRICTED_USERNAMES = {
    "admin",
    "administrator",
    "root",
    "superuser",
    "staff",
    "support",
    "moderator",
    "system",
    "login",
    "logout",
    "register",
    "signup",
    "api",
    "bcethub",
    "rishabhsahil",
    "rishabh",
    "sahil",
    "rishabhkumar",
    "kumarrishabh",
    "sahilkumar",
    "kumarsahil",
    "kumar",
    "edit",
    "student",
    "feedback",
    "attendance",
    "about"
}

# Student email pattern
STUDENT_EMAIL_REGEX = config('STUDENT_EMAIL_REGEX') 


# Club email pattern
CLUB_EMAIL_REGEX = config('CLUB_EMAIL_REGEX')

# Greeting Function
def get_greeting(request):
    now = timezone.localtime()
    current_hour = now.hour
    username = "BCETians"

    if request.user.username:
        username = f'@{request.user.username}'

    if 4 <= current_hour < 12:
        greeting = "Good Morning"
    elif 12 <= current_hour < 17:
        greeting = "Good Afternoon"
    else:
        greeting = "Good Evening"

    return HttpResponse(f"<strong>{greeting}, <span>{username}</span></strong>")

DAYS_MAP = {
    0: ('MON', 'Monday'),
    1: ('TUE', 'Tuesday'),
    2: ('WED', 'Wednesday'),
    3: ('THU', 'Thursday'),
    4: ('FRI', 'Friday'),
    5: ('SAT', 'Saturday'),
    6: ('SUN', 'Sunday'),
}

DAY_LOOKUP = {
    'monday': 'MON', 'mon': 'MON',
    'tuesday': 'TUE', 'tue': 'TUE',
    'wednesday': 'WED', 'wed': 'WED',
    'thursday': 'THU', 'thu': 'THU',
    'friday': 'FRI', 'fri': 'FRI',
    'saturday': 'SAT', 'sat': 'SAT',
    'sunday': 'SUN', 'sun': 'SUN',
}

DAYS_LIST = [
    ('MON', 'Monday'),
    ('TUE', 'Tuesday'),
    ('WED', 'Wednesday'),
    ('THU', 'Thursday'),
    ('FRI', 'Friday'),
    ('SAT', 'Saturday'),
    ('SUN', 'Sunday'),
]

# current time in IST timezone
def get_ist_now():
    return timezone.localtime()

def service_worker(request):
    sw_path = os.path.join(settings.BASE_DIR, 'static', 'js', 'serviceworker.js')
    if os.path.exists(sw_path):
        with open(sw_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return HttpResponse(content, content_type='application/javascript')
    return HttpResponse('', content_type='application/javascript')

def group_evaluated_csv_slots(slots, target_day, target_time, current_day):
    evaluated = []
    for s in slots:
        status = evaluate_slot_status(s, target_day, target_time, current_day)
        fac_code = (s.get('faculty_code') or '').strip()
        if not fac_code or fac_code.upper() in ['LIB', 'FACULTY', '--']:
            fac_code_clean = '--'
            fac_ref = None
        else:
            fac_code_clean = fac_code
            fac_ref = Faculty.objects.filter(short_code__iexact=fac_code_clean).first()

        st_obj = None
        et_obj = None
        if s.get('start_time'):
            try:
                parts = s['start_time'].split(':')
                st_obj = datetime.time(int(parts[0]), int(parts[1]))
            except Exception:
                pass
        if s.get('end_time'):
            try:
                parts = s['end_time'].split(':')
                et_obj = datetime.time(int(parts[0]), int(parts[1]))
            except Exception:
                pass

        evaluated.append({
            'start_slot_number': s['slot_number'],
            'end_slot_number': s['slot_number'],
            'slot_number_display': f"Slot {s['slot_number']}",
            'start_time': st_obj or s['start_time'],
            'end_time': et_obj or s['end_time'],
            'subject_code': s['subject_code'],
            'subject_name': s['subject_name'],
            'faculty_code': fac_code_clean,
            'faculty_ref': fac_ref,
            'lh_room': s['lh_room'],
            'section_name': s['section'],
            'status': status,
        })
    return evaluated

def group_evaluated_slots(slots_qs, target_day, target_time, current_day):
    return group_evaluated_csv_slots(slots_qs, target_day, target_time, current_day)

# Sync API endpoint for instant offline sync and notice check
def sync_check(request):
    routine_data = read_routine_csv()
    r_ver = get_routine_file_version()
    
    notices_qs = Notice.objects.filter(is_active=True)
    n_list = []
    latest_n_time = 0
    for n in notices_qs:
        n_list.append({
            'id': n.id,
            'notice': n.notice,
            'icon': n.icon or '',
            'n_url': n.n_url or '',
            'n_url_name': n.n_url_name or '',
            'n_url_icon': n.n_url_icon or ''
        })
        if hasattr(n, 'updated_at') and n.updated_at:
            ts = int(n.updated_at.timestamp())
            if ts > latest_n_time:
                latest_n_time = ts
                
    n_ver = f"{latest_n_time}_{len(n_list)}"
    
    unique_sections = sorted(list(set(row['section'] for row in routine_data if row.get('section'))))
    unique_years = sorted(list(set(str(row['year']) for row in routine_data if row.get('year'))))

    return JsonResponse({
        'status': 'success',
        'routine_version': str(r_ver),
        'notice_version': str(n_ver),
        'routine_data': routine_data,
        'notices': n_list,
        'sections': unique_sections,
        'years': unique_years,
    })

# Home View
def home(request):
    now = get_ist_now()
    today_date = now.date()
    today_time = now.time()
    today_day_code, today_day_name = DAYS_MAP[now.weekday()]

    # Fetch Mess Menu
    today_mess = DailyMessMenu.objects.filter(day_of_week=today_day_code).first()

    # Calculate Displayed Meal
    current_mins = today_time.hour * 60 + today_time.minute

    if current_mins < 10 * 60:
        meal_type_code = 'Breakfast'
        meal_title = "Today's Breakfast Menu"
        meal_food = today_mess.breakfast if today_mess else None
        meal_icon = 'coffee'
        time_1_2 = '07:45 AM - 08:45 AM'
        time_3_4 = '08:45 AM - 09:45 AM'
        is_serving = (7 * 60 + 45) <= current_mins <= (9 * 60 + 45)
    elif current_mins < 14 * 60 + 30:
        meal_type_code = 'Lunch'
        meal_title = "Today's Lunch Menu"
        meal_food = today_mess.lunch if today_mess else None
        meal_icon = 'soup'
        time_1_2 = '12:00 PM - 01:00 PM'
        time_3_4 = '01:00 PM - 02:00 PM'
        is_serving = (12 * 60) <= current_mins <= (14 * 60)
    elif current_mins < 18 * 60 + 30:
        meal_type_code = 'Evening Hi-Tea'
        meal_title = "Today's Evening Hi-Tea"
        meal_food = today_mess.hi_tea if today_mess else None
        meal_icon = 'cup-soda'
        time_1_2 = '05:00 PM - 05:30 PM'
        time_3_4 = '05:30 PM - 06:00 PM'
        is_serving = (17 * 60) <= current_mins <= (18 * 60)
    else:
        meal_type_code = 'Dinner'
        meal_title = "Today's Dinner Menu"
        meal_food = today_mess.dinner if today_mess else None
        meal_icon = 'utensils'
        time_1_2 = '08:00 PM - 09:00 PM'
        time_3_4 = '09:00 PM - 10:00 PM'
        is_serving = (20 * 60) <= current_mins <= (22 * 60)

    displayed_meal = {
        'type': meal_type_code,
        'title': meal_title,
        'food': meal_food,
        'icon': meal_icon,
        'time_1_2': time_1_2,
        'time_3_4': time_3_4,
        'is_serving': is_serving
    }

    # Fetch Active Meal
    active_meal = None
    all_timings = MessTiming.objects.all()
    for mt in all_timings:
        if mt.start_time <= today_time <= mt.end_time:
            active_meal = mt
            break

    # Fetch Today Induction
    today_induction = InductionProgram.objects.filter(date=today_date).first()

    # Fetch Today Routine from CSV
    all_sections = Section.objects.all()
    all_years = AcademicYear.objects.all()
    selected_sec = request.GET.get('sec', 'CSE - A')
    selected_year = request.GET.get('year', '1')
        
    csv_slots = get_filtered_routine_csv(year_filter=selected_year, sec_filter=selected_sec, day_filter=today_day_code)
    evaluated_routine = group_evaluated_csv_slots(csv_slots, today_day_code, today_time, today_day_code)
    live_slot = next((item for item in evaluated_routine if item['status'] == 'LIVE'), None)

    # Calculate Layout Priorities
    p_meal = 2
    p_induction = 3
    p_routine = 4

    is_induction_live = (today_induction and today_induction.status(today_date, today_time) == 'LIVE')
    is_routine_live = (live_slot is not None)
    is_meal_live = displayed_meal['is_serving']

    if is_induction_live:
        p_induction = 1
        p_routine = 2
        p_meal = 3
    elif is_routine_live:
        p_routine = 1
        p_meal = 2
        p_induction = 3
    elif is_meal_live:
        p_meal = 1
        p_induction = 2
        p_routine = 3
    else:
        if today_day_code in ['SUN', 'MON']:
            p_meal = 1
            p_induction = 2
            p_routine = 3
        elif current_mins < 10 * 60:
            p_meal = 1
            p_induction = 2
            p_routine = 3
        elif 10 * 60 <= current_mins < 12 * 60:
            p_induction = 1
            p_routine = 2
            p_meal = 3
        elif 12 * 60 <= current_mins < 14 * 60:
            p_meal = 1
            p_routine = 2
            p_induction = 3
        elif 14 * 60 <= current_mins < 17 * 60:
            p_routine = 1
            p_meal = 2
            p_induction = 3
        else:
            p_meal = 1
            p_routine = 2
            p_induction = 3

    if not evaluated_routine:
        p_routine = 99
    if not today_induction:
        p_induction = 99

    notice = Notice.objects.all()

    # fetch active events
    active_club_events = CommunityPost.objects.filter(
        status='PUBLISHED'
    ).filter(
        Q(event_status='CANCELLED') |
        Q(event_status='UPCOMING') |
        Q(event_date__gte=now) |
        Q(post_type='EVENT')
    ).select_related('community').order_by('event_date', '-created_at')[:4]

    # recent club posts
    recent_club_posts = CommunityPost.objects.filter(
        status='PUBLISHED'
    ).select_related('community').order_by('-created_at')[:6]

    context = {
        'now': now,
        'today_date_str': now.strftime('%A, %d %B %Y'),
        'today_time_str': now.strftime('%I:%M %p'),
        'today_day_code': today_day_code,
        'today_day_name': today_day_name,
        'today_mess': today_mess,
        'displayed_meal': displayed_meal,
        'active_meal': active_meal,
        'today_induction': today_induction,
        'live_slot': live_slot,
        'evaluated_routine': evaluated_routine,
        'selected_sec': selected_sec,
        'selected_year': selected_year,
        'all_sections': all_sections,
        'all_years': all_years,
        'p_meal': p_meal,
        'p_induction': p_induction,
        'p_routine': p_routine,
        'notice': notice,
        'active_club_events': active_club_events,
        'recent_club_posts': recent_club_posts,
    }
    return render(request, 'blog/home.html', context)

# Fetch search results
def get_search_data(query):
    query = (query or '').strip()
    query_lower = query.lower()
    terms = [t for t in query.split() if t]

    mess_results = None
    routine_results = None
    induction_results = None
    faculty_results = None
    branch_results = None
    notes_results = None
    assignments_results = None
    pyqs_results = None
    community_results = None
    portfolio_results = None
    post_results = None

    if query:
        day_code = DAY_LOOKUP.get(query_lower)
        if day_code:
            mess_results = DailyMessMenu.objects.filter(day_of_week=day_code)
            routine_results = RoutineSlot.objects.filter(day=day_code)

        if any(w in query_lower for w in ['1st', 'first', '1']):
            r_1st = RoutineSlot.objects.filter(section_name__name__icontains='1st')
            routine_results = (routine_results | r_1st).distinct() if routine_results else r_1st
        elif any(w in query_lower for w in ['2nd', 'second', '2']):
            r_2nd = RoutineSlot.objects.filter(section_name__name__icontains='2nd')
            routine_results = (routine_results | r_2nd).distinct() if routine_results else r_2nd

        fac_q = Q(name__icontains=query) | Q(short_code__icontains=query) | Q(designation__icontains=query)
        for w in terms:
            fac_q |= Q(name__icontains=w) | Q(short_code__icontains=w)
        faculty_results = Faculty.objects.filter(fac_q).select_related('branch').distinct()[:15]

        routine_q = (
            Q(subject_code__icontains=query) |
            Q(subject_name__icontains=query) |
            Q(faculty_code__icontains=query) |
            Q(lh_room__icontains=query) |
            Q(section_name__name__icontains=query)
        )
        for w in terms:
            routine_q |= Q(subject_code__icontains=w) | Q(subject_name__icontains=w) | Q(faculty_code__icontains=w)
        routine_matches = RoutineSlot.objects.filter(routine_q)
        routine_results = (routine_results | routine_matches).distinct() if routine_results else routine_matches

        ind_q = (
            Q(topic_programme__icontains=query) |
            Q(venue__icontains=query) |
            Q(assigned_persons_text__icontains=query) |
            Q(external_guest__icontains=query)
        )
        for w in terms:
            ind_q |= Q(topic_programme__icontains=w) | Q(assigned_persons_text__icontains=w)
        induction_results = InductionProgram.objects.filter(ind_q).distinct()[:10]

        mess_q = (
            Q(breakfast__icontains=query) |
            Q(lunch__icontains=query) |
            Q(hi_tea__icontains=query) |
            Q(dinner__icontains=query)
        )
        for w in terms:
            mess_q |= (
                Q(breakfast__icontains=w) |
                Q(lunch__icontains=w) |
                Q(hi_tea__icontains=w) |
                Q(dinner__icontains=w)
            )
        mess_matches = DailyMessMenu.objects.filter(mess_q)
        mess_results = (mess_results | mess_matches).distinct() if mess_results else mess_matches

        branch_results = Branch.objects.filter(
            Q(name__icontains=query) | Q(code__icontains=query)
        )[:10]

        notes_q = (
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(subject__name__icontains=query) |
            Q(subject__code__icontains=query) |
            Q(module__name__icontains=query) |
            Q(cr_name__icontains=query) |
            Q(cr__name__icontains=query)
        )
        for w in terms:
            notes_q |= (
                Q(title__icontains=w) |
                Q(description__icontains=w) |
                Q(subject__name__icontains=w) |
                Q(subject__code__icontains=w)
            )
        notes_results = Notes.objects.filter(notes_q).select_related('course', 'branch', 'year', 'section', 'subject').distinct()[:15]

        assign_q = (
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(subject__name__icontains=query) |
            Q(subject__code__icontains=query) |
            Q(author__icontains=query)
        )
        for w in terms:
            assign_q |= (
                Q(title__icontains=w) |
                Q(description__icontains=w) |
                Q(subject__name__icontains=w) |
                Q(subject__code__icontains=w)
            )
        assignments_results = Assignment.objects.filter(assign_q).select_related('course', 'branch', 'year', 'subject').distinct()[:15]

        pyqs_q = (
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(subject__name__icontains=query) |
            Q(subject__code__icontains=query) |
            Q(cr_name__icontains=query)
        )
        for w in terms:
            pyqs_q |= (
                Q(title__icontains=w) |
                Q(description__icontains=w) |
                Q(subject__name__icontains=w) |
                Q(subject__code__icontains=w)
            )
        pyqs_results = PYQ.objects.filter(pyqs_q).select_related('course', 'branch', 'year', 'subject').distinct()[:15]

        comm_q = (
            Q(group_name__icontains=query) |
            Q(group_dec__icontains=query) |
            Q(group_type__name__icontains=query) |
            Q(user__username__icontains=query)
        )
        for w in terms:
            comm_q |= (
                Q(group_name__icontains=w) |
                Q(group_dec__icontains=w) |
                Q(group_type__name__icontains=w) |
                Q(user__username__icontains=w)
            )
        community_results = Community.objects.filter(Q(is_active=True) & comm_q).select_related('group_type', 'user').distinct()[:15]

        # Student portfolios search
        port_q = (
            Q(full_name__icontains=query) |
            Q(user__username__icontains=query) |
            Q(department__icontains=query) |
            Q(headline__icontains=query) |
            Q(bio__icontains=query) |
            Q(skills__icontains=query) |
            Q(batch_year__icontains=query)
        )
        for w in terms:
            port_q |= (
                Q(full_name__icontains=w) |
                Q(user__username__icontains=w) |
                Q(department__icontains=w) |
                Q(skills__icontains=w)
            )
        portfolio_results = StudentPortfolio.objects.filter(Q(is_public=True, is_block=False) & port_q).select_related('user').distinct()[:15]

        post_q = (
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(venue__icontains=query) |
            Q(post_type__icontains=query) |
            Q(community__group_name__icontains=query) |
            Q(community__user__username__icontains=query)
        )
        for w in terms:
            post_q |= (
                Q(title__icontains=w) |
                Q(description__icontains=w) |
                Q(community__group_name__icontains=w)
            )
        post_results = CommunityPost.objects.filter(Q(status='PUBLISHED') & post_q).select_related('community', 'community__user').distinct()[:20]

    return {
        'mess_results': mess_results,
        'routine_results': routine_results,
        'induction_results': induction_results,
        'faculty_results': faculty_results,
        'branch_results': branch_results,
        'notes_results': notes_results,
        'assignments_results': assignments_results,
        'pyqs_results': pyqs_results,
        'community_results': community_results,
        'portfolio_results': portfolio_results,
        'post_results': post_results,
    }

# Live search view
def live_search(request):
    query = (request.GET.get('q') or request.GET.get('query') or '').strip()
    data = get_search_data(query)
    data['query'] = query
    return render(request, 'blog/includes/live_search_results.html', data)

# Search page view
def search(request):
    query = (request.GET.get('q') or request.GET.get('query') or '').strip()
    data = get_search_data(query)
    data['query'] = query
    data['now'] = get_ist_now()
    return render(request, 'blog/search.html', data)

# Routine View
def routine(request):
    now = get_ist_now()
    today_time = now.time()
    today_day_code = DAYS_MAP[now.weekday()][0]

    all_sections = Section.objects.all()
    all_years = AcademicYear.objects.all()
    
    sec_filter = request.GET.get('sec', 'CSE - A')
    day_filter = request.GET.get('day', today_day_code)
    year_filter = request.GET.get('year', '1')

    slots = get_filtered_routine_csv(year_filter=year_filter, sec_filter=sec_filter, day_filter=day_filter)
    evaluated_slots = group_evaluated_csv_slots(slots, day_filter, today_time, today_day_code)

    context = {
        'sec_filter': sec_filter,
        'day_filter': day_filter,
        'year_filter': year_filter,
        'all_sections': all_sections,
        'all_years': all_years,
        'days_list': DAYS_LIST,
        'evaluated_slots': evaluated_slots,
        'today_day_code': today_day_code,
        'now': now,
    }
    return render(request, 'blog/routine.html', context)

# Induction Program View
def induction(request):
    now = get_ist_now()
    today_date = now.date()
    today_time = now.time()

    filter_tab = request.GET.get('tab', 'all')

    all_sessions = InductionProgram.objects.all().order_by('day_number', 'start_time')

    evaluated_list = []
    for sess in all_sessions:
        st = sess.status(today_date, today_time)

        if filter_tab == 'today' and sess.date != today_date:
            continue
        elif filter_tab == 'live' and st != 'LIVE':
            continue
        elif filter_tab == 'upcoming' and st != 'UPCOMING':
            continue
        elif filter_tab == 'past' and st != 'PAST':
            continue

        evaluated_list.append({
            'session': sess,
            'status': st
        })

    context = {
        'filter_tab': filter_tab,
        'evaluated_list': evaluated_list,
        'today_date': today_date,
        'now': now,
    }
    return render(request, 'blog/induction.html', context)

# Mess Menu View
def mess_menu(request):
    now = get_ist_now()
    today_time = now.time()
    today_day_code = DAYS_MAP[now.weekday()][0]

    all_menus = DailyMessMenu.objects.all()
    mess_timings_1_2 = MessTiming.objects.filter(academic_years__year='1').distinct()
    mess_timings_3_4 = MessTiming.objects.filter(academic_years__year='3').distinct()

    active_meal = None
    for mt in MessTiming.objects.all():
        if mt.start_time <= today_time <= mt.end_time:
            active_meal = mt
            break

    context = {
        'all_menus': all_menus,
        'today_day_code': today_day_code,
        'mess_timings_1_2': mess_timings_1_2,
        'mess_timings_3_4': mess_timings_3_4,
        'active_meal': active_meal,
        'now': now,
    }
    return render(request, 'blog/mess_menu.html', context)


def about(request):
    faculties = Faculty.objects.filter(is_active=True).select_related('branch')
    branches = Branch.objects.all()
    return render(request, 'blog/about.html', {'faculties': faculties, 'branches': branches})

# show 403 page
def custom_403(request, exception=None):
    return render(request, 'errors/403.html', status=403)

def custom_404(request, exception=None):
    return render(request, 'errors/404.html', status=404)

def custom_500(request):
    return render(request, 'errors/500.html', status=500)


# Testing Function's Broooooo Wait

# Main Page View
def pooling_page(request):
    # Get the latest pool object or create one if it doesn't exist
    obj, created = Pooling.objects.get_or_create(id=1)
    
    # Check if user already voted today using cookies
    already_voted = 'today_attendance' in request.COOKIES
    
    context = {
        'pool_count': f"{((obj.pool)/50)*100}%",
        'already_voted': already_voted
    }
    return render(request, 'blog/pooling.html', context)

# HTMX Live Update View (Handles Click)
def mark_attendance(request):
    obj, created = Pooling.objects.get_or_create(id=1)
    
    # Increment count only if cookie is not present
    if 'today_attendance' not in request.COOKIES:
        obj.pool += 1
        obj.save()
    
    # Prepare HTML chunk to return to HTMX
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = f'<span id="live-count">{((obj.pool)/50)*100}%</span>'
    
    response = HttpResponse(html)
    
    # Save current date-time in cookie named 'today_attendance' (expires in 1 day)
    response.set_cookie('today_attendance', current_time, max_age=86400)
    return response

# HTMX Live Counter View (For polling/auto-refreshing globally)
def live_counter(request):
    obj, created = Pooling.objects.get_or_create(id=1)
    return HttpResponse(f'<span id="live-count">{((obj.pool)/50)*100}%</span>')

# Submit User Feedback / Bug Report
def submit_feedback(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        category = request.POST.get('category', 'BUG')
        contact = request.POST.get('contact', '').strip()
        message_text = request.POST.get('message', '').strip()

        if name and message_text:
            Feedback.objects.create(
                name=name,
                category=category,
                contact=contact,
                message=message_text
            )
            messages.success(request, 'Thank you! Your feedback has been sent to the developer.')
        else:
            messages.error(request, 'Please provide both your name and feedback message.')

    return redirect(request.META.get('HTTP_REFERER', 'home'))

# Qr-Code
def qr_code(request):
    return render(request, 'blog/qr.html')

# Study View
def study(request):
    return render(request, 'blog/study.html')

# Notes View
def notes(request):
    course_id = request.GET.get('course', '').strip()
    branch_id = request.GET.get('branch', '').strip()
    year_id = request.GET.get('year', '').strip()
    section_id = request.GET.get('section', '').strip()
    subject_id = request.GET.get('subject', '').strip()
    search_query = request.GET.get('q', '').strip()

    notes_qs = Notes.objects.select_related('course', 'branch', 'year', 'section', 'subject', 'module', 'cr').prefetch_related('images').all()

    if course_id:
        notes_qs = notes_qs.filter(course_id=course_id)
    if branch_id:
        notes_qs = notes_qs.filter(branch_id=branch_id)
    if year_id:
        notes_qs = notes_qs.filter(year_id=year_id)
    if section_id:
        notes_qs = notes_qs.filter(section_id=section_id)
    if subject_id:
        notes_qs = notes_qs.filter(subject_id=subject_id)
    if search_query:
        notes_qs = notes_qs.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(subject__name__icontains=search_query) |
            Q(subject__code__icontains=search_query) |
            Q(module__name__icontains=search_query) |
            Q(cr_name__icontains=search_query) |
            Q(cr__name__icontains=search_query)
        )

    all_courses = Course.objects.all()
    all_branches = Branch.objects.all()
    all_years = AcademicYear.objects.all()
    all_sections = Section.objects.all()
    all_subjects = Subject.objects.all()

    context = {
        'notes': notes_qs,
        'all_courses': all_courses,
        'all_branches': all_branches,
        'all_years': all_years,
        'all_sections': all_sections,
        'all_subjects': all_subjects,
        'selected_course': course_id,
        'selected_branch': branch_id,
        'selected_year': year_id,
        'selected_section': section_id,
        'selected_subject': subject_id,
        'search_query': search_query,
    }
    return render(request, 'blog/notes.html', context)


# Previous Year Questions View
def pyqs(request):
    course_id = request.GET.get('course', '').strip()
    branch_id = request.GET.get('branch', '').strip()
    year_id = request.GET.get('year', '').strip()
    semester = request.GET.get('semester', '').strip()
    subject_id = request.GET.get('subject', '').strip()
    exam_year = request.GET.get('exam_year', '').strip()
    search_query = request.GET.get('q', '').strip()

    pyqs_qs = PYQ.objects.select_related('course', 'branch', 'year', 'subject').prefetch_related('images').all()

    if course_id:
        pyqs_qs = pyqs_qs.filter(course_id=course_id)
    if branch_id:
        pyqs_qs = pyqs_qs.filter(branch_id=branch_id)
    if year_id:
        pyqs_qs = pyqs_qs.filter(year_id=year_id)
    if semester:
        pyqs_qs = pyqs_qs.filter(semester=semester)
    if subject_id:
        pyqs_qs = pyqs_qs.filter(subject_id=subject_id)
    if exam_year:
        pyqs_qs = pyqs_qs.filter(exam_year=exam_year)
    if search_query:
        pyqs_qs = pyqs_qs.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(subject__name__icontains=search_query) |
            Q(subject__code__icontains=search_query) |
            Q(cr_name__icontains=search_query)
        )

    all_courses = Course.objects.all()
    all_branches = Branch.objects.all()
    all_years = AcademicYear.objects.all()
    all_subjects = Subject.objects.all()
    semesters_list = PYQ.SEMESTER_CHOICES

    context = {
        'pyqs': pyqs_qs,
        'all_courses': all_courses,
        'all_branches': all_branches,
        'all_years': all_years,
        'all_subjects': all_subjects,
        'semesters_list': semesters_list,
        'selected_course': course_id,
        'selected_branch': branch_id,
        'selected_year': year_id,
        'selected_semester': semester,
        'selected_subject': subject_id,
        'selected_exam_year': exam_year,
        'search_query': search_query,
    }
    return render(request, 'blog/pyqs.html', context)


def assignments(request):
    course_id = request.GET.get('course', '').strip()
    branch_id = request.GET.get('branch', '').strip()
    year_id = request.GET.get('year', '').strip()
    semester = request.GET.get('semester', '').strip()
    subject_id = request.GET.get('subject', '').strip()
    search_query = request.GET.get('q', '').strip()

    assignments = Assignment.objects.select_related('course', 'branch', 'year', 'subject')

    if course_id:
        assignments = assignments.filter(course_id=course_id)
    if branch_id:
        assignments = assignments.filter(branch_id=branch_id)
    if year_id:
        assignments = assignments.filter(year_id=year_id)
    if semester:
        assignments = assignments.filter(semester=semester)
    if subject_id:
        assignments = assignments.filter(subject_id=subject_id)
    if search_query:
        assignments = assignments.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(subject__name__icontains=search_query) |
            Q(subject__code__icontains=search_query) |
            Q(author__icontains=search_query)
        )

    all_courses = Course.objects.all()
    all_branches = Branch.objects.all()
    all_years = AcademicYear.objects.all()
    all_subjects = Subject.objects.all()
    semesters_list = PYQ.SEMESTER_CHOICES

    context = {
        'assignments': assignments,
        'all_courses': all_courses,
        'all_branches': all_branches,
        'all_years': all_years,
        'all_subjects': all_subjects,
        'semesters_list': semesters_list,
        'selected_course': course_id,
        'selected_branch': branch_id,
        'selected_year': year_id,
        'selected_semester': semester,
        'selected_subject': subject_id,
        'search_query': search_query,
    }
    return render(request, 'blog/assignments.html', context)

# Community list
def community(request):
    communities_qs = Community.objects.filter(is_active=True).select_related('group_type', 'user')
    
    communities = sorted(
        communities_qs,
        key=lambda c: (c.group_type.name if c.group_type and c.group_type.name else "", c.id),
        reverse=True  # Descending (Z se A) order 
    )

    # 1. Blue Tick (is_bluetick=True)  -> Old account first, then New (+id)
    # 2. Without Blue Tick (False)     -> New account first, then Old (-id)
    portfolios = (
        StudentPortfolio.objects.filter(is_public=True, is_block=False)
        .select_related('user')
        .annotate(
            sort_order=Case(
                When(is_bluetick=True, then=F('id')),
                default=0 - F('id'),
                output_field=IntegerField(),
            )
        )
        .order_by('-is_bluetick', 'sort_order')
    )

    group_types = CommunityGroupType.objects.all().order_by('id')

    context = {
        "community": communities,
        "portfolios": portfolios,
        "group_types": group_types,
    }
    return render(request, 'blog/community.html', context)

# Community profile
def community_page(request, username):
    community = Community.objects.filter(user__username__iexact=username, is_active=True).select_related('group_type', 'user').first()
    if not community:
        return render(request, 'errors/404.html', status=404)

    is_owner = request.user.is_authenticated and (request.user == community.user or request.user.is_superuser)
    
    # Club posts
    if is_owner:
        posts = community.posts.all().prefetch_related('images').order_by('-created_at')
    else:
        posts = community.posts.filter(status='PUBLISHED').prefetch_related('images').order_by('-created_at')
        
    context = {
        "community": community,
        "is_owner": is_owner,
        "posts": posts,
    }
    return render(request, 'blog/includes/community_page.html', context)

# Post detail
def community_post_detail(request, username, slug):
    community = Community.objects.filter(user__username__iexact=username, is_active=True).select_related('group_type', 'user').first()
    if not community:
        return render(request, 'errors/404.html', status=404)

    is_owner = request.user.is_authenticated and (request.user == community.user or request.user.is_superuser)

    # Fetch post item
    post_qs = community.posts.prefetch_related('images')
    if not is_owner:
        post_qs = post_qs.filter(status='PUBLISHED')

    post = post_qs.filter(slug=slug).first()
    if not post and slug.isdigit():
        post = post_qs.filter(id=int(slug)).first()

    if not post:
        return render(request, 'errors/404.html', status=404)

    context = {
        "community": community,
        "post": post,
        "is_owner": is_owner,
    }
    return render(request, 'blog/community_post_detail.html', context)

# user login page
def community_login(request):
    # check user login
    if request.user.is_authenticated:
        if hasattr(request.user, 'community_profile') and request.user.community_profile:
            return redirect('community_page', username=request.user.username)
        return redirect('home')

    next_url = request.GET.get('next') or request.POST.get('next') or ''

    # Extract username from next URL
    parts = urlparse(next_url).path.strip('/').split('/')
    username_url = parts[1] if len(parts) > 1 and parts[0] == 'community' else False
    print(username_url)

    # check form post
    if request.method == 'POST':
        uname = request.POST.get('username', '').strip().lower()
        pwd = request.POST.get('password', '').strip()

        # check user pass
        user = authenticate(request, username=uname, password=pwd)

        if user is not None:
            auth_login(request, user)
            messages.success(request, f"Welcome back, @{user.username}!")

            if next_url:
                return redirect(next_url)

            if hasattr(user, 'community_profile') and user.community_profile:
                return redirect('community_page', username=user.username)

            return redirect('home')
        else:
            messages.error(request, "Invalid username or password.")

    return render(request, 'blog/community_login.html', {
        'next': next_url,
        'username_url': username_url
    })

# user logout view
def community_logout(request):
    auth_logout(request)
    messages.info(request, "Logged out successfully.")
    return redirect('community')

# add post view
@login_required(login_url='community_login')
def community_post_create(request, username):
    # check login user
    if not request.user.is_authenticated:
        messages.warning(request, "Please login first to create posts.")
        return redirect(f"/login?next=/community/{username}/post/")

    community = Community.objects.filter(user__username__iexact=username, is_active=True).select_related('group_type', 'user').first()
    if not community:
        return render(request, 'errors/404.html', status=404)

    # check owner access
    if request.user != community.user and not request.user.is_superuser:
        return render(request, 'errors/403.html', status=403)

    # save form data
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        post_type = request.POST.get('post_type', 'BLOG')
        status = request.POST.get('status', 'PUBLISHED')
        venue = request.POST.get('venue', '').strip()
        event_status = request.POST.get('event_status', '')
        link_title = request.POST.get('link_title', '').strip()
        link_url = request.POST.get('link_url', '').strip()
        cover_image = request.FILES.get('cover_image')
        event_date = request.POST.get('event_date') or None

        # validate title text
        if not title or not description:
            messages.error(request, "Title and description are required.")
            return render(request, 'blog/community_post_create.html', {
                'community': community,
                'post_types': CommunityPost.POST_TYPES,
                'status_choices': CommunityPost.STATUS_CHOICES,
            })

        # create new post
        post = CommunityPost.objects.create(
            community=community,
            title=title,
            description=description,
            post_type=post_type,
            status=status,
            venue=venue,
            event_status=event_status,
            link_title=link_title,
            link_url=link_url,
            cover_image=cover_image,
            event_date=event_date,
            published_at=timezone.now() if status == 'PUBLISHED' else None
        )

        # save gallery images
        gallery_images = request.FILES.getlist('gallery_images')
        for idx, img in enumerate(gallery_images):
            CommunityPostImage.objects.create(post=post, image=img, order=idx)

        messages.success(request, "Post created successfully!")
        return redirect('community_page', username=community.username)

    return render(request, 'blog/community_post_create.html', {
        'community': community,
        'post_types': CommunityPost.POST_TYPES,
        'status_choices': CommunityPost.STATUS_CHOICES,
    })

# edit post view
@login_required(login_url='community_login')
def community_post_edit(request, username, post_id):
    # check login user
    if not request.user.is_authenticated:
        messages.warning(request, "Please login first to edit posts.")
        return redirect('community_login')

    community = Community.objects.filter(user__username__iexact=username, is_active=True).first()
    if not community:
        return render(request, 'errors/404.html', status=404)

    # check owner access
    if request.user != community.user and not request.user.is_superuser:
        return render(request, 'errors/403.html', status=403)

    post = CommunityPost.objects.filter(community=community, id=post_id).first()
    if not post:
        return render(request, 'errors/404.html', status=404)

    # update post data
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        post_type = request.POST.get('post_type', 'BLOG')
        status = request.POST.get('status', 'PUBLISHED')
        venue = request.POST.get('venue', '').strip()
        event_status = request.POST.get('event_status', '')
        link_title = request.POST.get('link_title', '').strip()
        link_url = request.POST.get('link_url', '').strip()
        cover_image = request.FILES.get('cover_image')
        event_date = request.POST.get('event_date') or None

        # validate title text
        if not title or not description:
            messages.error(request, "Title and description are required.")
            return render(request, 'blog/community_post_create.html', {
                'community': community,
                'post': post,
                'is_edit': True,
                'post_types': CommunityPost.POST_TYPES,
                'status_choices': CommunityPost.STATUS_CHOICES,
            })

        post.title = title
        post.description = description
        post.post_type = post_type
        post.status = status
        post.venue = venue
        post.event_status = event_status
        post.link_title = link_title
        post.link_url = link_url
        post.event_date = event_date

        if cover_image:
            post.cover_image = cover_image

        if status == 'PUBLISHED' and not post.published_at:
            post.published_at = timezone.now()

        post.save()

        # save gallery images
        gallery_images = request.FILES.getlist('gallery_images')
        for idx, img in enumerate(gallery_images):
            CommunityPostImage.objects.create(post=post, image=img, order=idx)

        messages.success(request, "Post updated successfully!")
        return redirect('community_post_detail', username=community.username, slug=post.slug)

    return render(request, 'blog/community_post_create.html', {
        'community': community,
        'post': post,
        'is_edit': True,
        'post_types': CommunityPost.POST_TYPES,
        'status_choices': CommunityPost.STATUS_CHOICES,
    })

# delete post item
@login_required(login_url='community_login')
def community_post_delete(request, username, post_id):
    # check login user
    if not request.user.is_authenticated:
        return redirect('community_login')

    community = Community.objects.filter(user__username__iexact=username).first()
    if not community or (request.user != community.user and not request.user.is_superuser):
        return render(request, 'errors/403.html', status=403)

    post = CommunityPost.objects.filter(community=community, id=post_id).first()
    if post:
        post.delete()
        messages.success(request, "Post deleted successfully.")
    return redirect('community_page', username=username)

# Check username
@login_required(login_url='community_login')
def check_username(request):
    username = (request.GET.get("user_name") or request.GET.get("username") or "").strip().lower()
    current_username = (request.GET.get("current_username") or "").strip().lower()

    if not username:
        return HttpResponse(
            '<span style="color: #ef4444; font-size: 13px;">Username required</span>'
        )
    
    if len(username) < 4:
        return HttpResponse(
            '<span style="color: #ef4444; font-size: 13px;">Must be at least 4 characters</span>'
        )

    if not re.fullmatch(r"[a-z0-9_.]{1,20}", username):
        return HttpResponse(
            '<span style="color: #ef4444; font-size: 13px;">Only lowercase letters, numbers, _ and . allowed</span>'
        )

    if (
        username.startswith((".", "_"))
        or username.endswith((".", "_"))
        or ".." in username
    ):
        return HttpResponse(
            '<span style="color: #ef4444; font-size: 13px;">Invalid username format</span>'
        )

    if username in RESTRICTED_USERNAMES:
        return HttpResponse(
            '<span style="color: #ef4444; font-size: 13px;">This username is reserved</span>'
        )

    # Current username
    if username == current_username:
        return HttpResponse(
            '<span style="color: #94a3b8; font-size: 13px;">This is your current username</span>'
        )

    # Check existence
    if User.objects.filter(username__iexact=username).exists():
        return HttpResponse(
            '<span style="color: #ef4444; font-size: 13px;">Username already exists</span>'
        )

    return HttpResponse(
        '<span style="color: #22c55e; font-size: 13px;">Username available</span>'
    )

# community edit
@login_required(login_url='community_login')
def community_edit(request, username):
    community = Community.objects.filter(
        user__username__iexact=username
    ).first()

    # Check profile ownership
    if not community or (
        request.user != community.user
        and not request.user.is_superuser
    ):
        return render(
            request,
            'errors/403.html',
            status=403
        )

    if request.method == 'POST':
        user_name = request.POST.get(
            'user_name', ''
        ).strip()

        group_name = request.POST.get(
            'group_name', ''
        ).strip()

        group_dec = request.POST.get(
            'group_dec', ''
        ).strip()

        # Validate club name
        if not group_name:
            messages.error(
                request,
                'Club name is required.'
            )

        # Validate username
        elif not re.fullmatch(r'[a-z0-9_.]{4,20}', user_name):
            messages.error(
                request,
                'Username must be 4-20 characters long and contain only lowercase letters, numbers, _ and .'
            )

        elif (
            user_name.startswith(('.', '_'))
            or user_name.endswith(('.', '_'))
            or '..' in user_name
        ):
            messages.error(
                request,
                'Username cannot start or end with . or _, or contain consecutive dots.'
            )

        elif user_name in RESTRICTED_USERNAMES:
            messages.error(
                request,
                'This username is reserved. Please choose another.'
            )

        elif User.objects.filter(
            username__iexact=user_name
        ).exclude(
            pk=community.user_id
        ).exists():
            messages.error(
                request,
                'Username already exists. Please choose another.'
            )

        else:
            # Update username
            community.user.username = user_name
            community.user.save(update_fields=['username'])

            # Update club email
            club_email = request.POST.get('email', '').strip().lower()
            if club_email and club_email != (community.user.email or '').strip().lower():
                if not re.fullmatch(CLUB_EMAIL_REGEX, club_email):
                    messages.error(request, "Club email must be a valid @gmail.com address.")
                    return redirect('community_edit_slash', username=community.user.username)
                if User.objects.filter(email__iexact=club_email).exclude(pk=community.user_id).exists():
                    messages.error(request, "This email is already in use by another account.")
                    return redirect('community_edit_slash', username=community.user.username)
                community.user.email = club_email
                community.user.save(update_fields=['email'])

            # Details
            community.group_name = group_name
            community.group_dec = group_dec

            # Group category
            group_type_id = request.POST.get('group_type')
            if group_type_id:
                gt = CommunityGroupType.objects.filter(pk=group_type_id).first()
                if gt:
                    community.group_type = gt

            # Social links
            for field in [
                'instagram',
                'facebook',
                'linkedin',
                'discord',
                'other',
                'other_title',
                'join',
            ]:
                setattr(
                    community,
                    field,
                    request.POST.get(field, '').strip()
                )

            # Logo handling
            if request.POST.get('clear_group_logo'):
                if community.group_logo:
                    community.group_logo.delete(save=False)
                    community.group_logo = None
            elif request.FILES.get('group_logo'):
                if community.group_logo:
                    community.group_logo.delete(save=False)
                community.group_logo = request.FILES['group_logo']

            # Banner handling
            if request.POST.get('clear_banner'):
                if community.banner:
                    community.banner.delete(save=False)
                    community.banner = None
            elif request.FILES.get('banner'):
                if community.banner:
                    community.banner.delete(save=False)
                community.banner = request.FILES['banner']

            community.save()

            messages.success(
                request,
                'Profile updated successfully!'
            )

            return redirect(
                'community_page',
                username=community.user.username
            )

    context = {
        'community': community,
        'group_types': CommunityGroupType.objects.all().order_by('name'),
    }

    return render(
        request,
        'blog/community_edit.html',
        context
    )


# Email validation
def check_student_email(request):
    email = request.GET.get('email', '').strip().lower()

    if not email:
        return HttpResponse(
            '<span style="color: #94a3b8; font-size: 13px;">Enter your GDG BCET email.</span>'
        )

    match = re.fullmatch(STUDENT_EMAIL_REGEX, email)
    if not match:
        return HttpResponse(
            '<span style="color: #ef4444; font-size: 13px;">'
            'Invalid format! Must follow bcet gmail format'
            '</span>'
        )

    extracted_username = match.group(1)

    if User.objects.filter(email__iexact=email).exists():
        return HttpResponse(
            '<span style="color: #ef4444; font-size: 13px;">'
            'Email already registered. Please sign in.'
            '</span>'
        )

    if User.objects.filter(username__iexact=extracted_username).exists():
        return HttpResponse(
            f'<span style="color: #ef4444; font-size: 13px;">'
            f'Username <b>@{extracted_username}</b> is already registered.'
            f'</span>'
        )

    return HttpResponse(
        f'<span style="color: #22c55e; font-size: 13px;">'
        f'Valid email! Default username: <b>@{extracted_username}</b>'
        f'</span>'
    )


# Create portfolio
def create_portfolio_account(request):
    if request.user.is_authenticated:
        return redirect('student_portfolio_profile', username=request.user.username)

    step = request.session.get('otp_step', 'form')

    if request.method == 'POST':
        action = request.POST.get('action')

        # Send OTP
        if action == 'send_otp':
            email = request.POST.get('email', '').strip().lower()
            password1 = request.POST.get('password1', '').strip()
            password2 = request.POST.get('password2', '').strip()

            match = re.fullmatch(STUDENT_EMAIL_REGEX, email)
            if not match:
                messages.error(request, "Invalid email. Must match 'gdg bcet' pattern.")
                return render(request, 'blog/student_create_portfolio.html', {'step': 'form', 'email': email})

            username = match.group(1)
            batch_year = match.group(2)

            if User.objects.filter(email__iexact=email).exists():
                messages.error(request, "This email is already registered.")
                return render(request, 'blog/student_create_portfolio.html', {'step': 'form', 'email': email})

            if User.objects.filter(username__iexact=username).exists():
                messages.error(request, f"Username @{username} is already taken.")
                return render(request, 'blog/student_create_portfolio.html', {'step': 'form', 'email': email})

            if len(password1) < 6:
                messages.error(request, "Password must be at least 6 characters.")
                return render(request, 'blog/student_create_portfolio.html', {'step': 'form', 'email': email})

            if password1 != password2:
                messages.error(request, "Passwords do not match.")
                return render(request, 'blog/student_create_portfolio.html', {'step': 'form', 'email': email})

            otp = str(random.randint(100000, 999999))
            request.session['portfolio_signup_data'] = {
                'email': email,
                'username': username,
                'batch_year': batch_year,
                'password': password1,
                'otp': otp,
            }
            request.session['otp_step'] = 'verify'

            success, err = send_signup_otp_email(email, username, otp)
            if success:
                messages.success(request, f"Verification OTP sent to {email}.")
            else:
                messages.error(request, f"Failed to send email: {err}")
                request.session['otp_step'] = 'form'
                return render(request, 'blog/student_create_portfolio.html', {'step': 'form', 'email': email})

            return render(request, 'blog/student_create_portfolio.html', {
                'step': 'verify',
                'email': email,
                'username': username
            })

        # Verify OTP
        elif action == 'verify_otp':
            entered_otp = request.POST.get('otp', '').strip()
            signup_data = request.session.get('portfolio_signup_data')

            if not signup_data:
                messages.error(request, "Session expired. Please try again.")
                request.session['otp_step'] = 'form'
                return redirect('create_portfolio_account')

            if entered_otp != signup_data.get('otp'):
                messages.error(request, "Invalid OTP code.")
                return render(request, 'blog/student_create_portfolio.html', {
                    'step': 'verify',
                    'email': signup_data.get('email'),
                    'username': signup_data.get('username')
                })

            if User.objects.filter(email__iexact=signup_data['email']).exists():
                messages.error(request, "This email is already registered.")
                request.session.pop('portfolio_signup_data', None)
                request.session['otp_step'] = 'form'
                return redirect('student_login')

            user = User.objects.create_user(
                username=signup_data['username'],
                email=signup_data['email'],
                password=signup_data['password']
            )
            StudentPortfolio.objects.create(
                user=user
                # batch_year=signup_data['batch_year']
            )

            send_verification_success_email(user.email, user)
            send_welcome_email(user.email, user)

            request.session.pop('portfolio_signup_data', None)
            request.session.pop('otp_step', None)

            auth_login(request, user)
            messages.success(request, f"Welcome @{user.username}! Your portfolio account is ready.")
            return redirect('student_portfolio_profile', username=user.username)

        # Reset email
        elif action == 'reset':
            request.session.pop('portfolio_signup_data', None)
            request.session['otp_step'] = 'form'
            return redirect('create_portfolio_account')

    signup_data = request.session.get('portfolio_signup_data', {})
    return render(request, 'blog/student_create_portfolio.html', {
        'step': step,
        'email': signup_data.get('email', ''),
        'username': signup_data.get('username', '')
    })


# Student login
def student_login(request):
    if request.user.is_authenticated:
        return redirect('student_portfolio_profile', username=request.user.username)

    next_url = request.GET.get('next') or request.POST.get('next') or ''

    if request.method == 'POST':
        identifier = request.POST.get('identifier', '').strip().lower()
        password = request.POST.get('password', '').strip()

        user_obj = User.objects.filter(Q(email__iexact=identifier) | Q(username__iexact=identifier)).first()
        uname = user_obj.username if user_obj else identifier

        user = authenticate(request, username=uname, password=password)
        if user is not None:
            auth_login(request, user)
            if user.email:
                send_login_alert_email(user.email, user)

            messages.success(request, f"Welcome back, @{user.username}!")
            if next_url:
                return redirect(next_url)
            return redirect('student_portfolio_profile', username=user.username)
        else:
            messages.error(request, "Invalid username, email, or password.")

    return render(request, 'blog/student_login.html', {'next': next_url})


# Student logout
def student_logout(request):
    auth_logout(request)
    messages.info(request, "Logged out successfully.")
    return redirect('student_login')

# Reset password
def student_forgot_password(request):
    if request.user.is_authenticated:
        return redirect('student_portfolio_profile', username=request.user.username)

    step = request.session.get('reset_step', 'form')

    if request.method == 'POST':
        action = request.POST.get('action')

        # Send reset OTP
        if action == 'send_otp':
            email = request.POST.get('email', '').strip().lower()
            user = User.objects.filter(email__iexact=email).first()

            if not user:
                messages.error(request, "No account found with this email.")
                return render(request, 'blog/student_forgot_password.html', {'step': 'form', 'email': email})

            otp = str(random.randint(100000, 999999))
            request.session['reset_password_data'] = {
                'email': email,
                'username': user.username,
                'otp': otp,
            }
            request.session['reset_step'] = 'verify'

            success, err = send_password_reset_otp_email(email, user, otp)
            if success:
                messages.success(request, f"Password reset OTP sent to {email}.")
            else:
                messages.error(request, f"Failed to send email: {err}")
                request.session['reset_step'] = 'form'
                return render(request, 'blog/student_forgot_password.html', {'step': 'form', 'email': email})

            return render(request, 'blog/student_forgot_password.html', {
                'step': 'verify',
                'email': email,
                'username': user.username
            })

        # Verify and update
        elif action == 'verify_reset':
            entered_otp = request.POST.get('otp', '').strip()
            new_password = request.POST.get('password1', '').strip()
            confirm_password = request.POST.get('password2', '').strip()

            reset_data = request.session.get('reset_password_data')
            if not reset_data:
                messages.error(request, "Session expired. Please try again.")
                request.session['reset_step'] = 'form'
                return redirect('student_forgot_password')

            if entered_otp != reset_data.get('otp'):
                messages.error(request, "Invalid OTP code.")
                return render(request, 'blog/student_forgot_password.html', {
                    'step': 'verify',
                    'email': reset_data.get('email'),
                    'username': reset_data.get('username')
                })

            if len(new_password) < 6:
                messages.error(request, "Password must be at least 6 characters.")
                return render(request, 'blog/student_forgot_password.html', {
                    'step': 'verify',
                    'email': reset_data.get('email'),
                    'username': reset_data.get('username')
                })

            if new_password != confirm_password:
                messages.error(request, "Passwords do not match.")
                return render(request, 'blog/student_forgot_password.html', {
                    'step': 'verify',
                    'email': reset_data.get('email'),
                    'username': reset_data.get('username')
                })

            user = User.objects.filter(email__iexact=reset_data['email']).first()
            if user:
                user.set_password(new_password)
                user.save()
                send_password_reset_success_email(user.email, user.username)

                request.session.pop('reset_password_data', None)
                request.session.pop('reset_step', None)

                messages.success(request, "Password reset successfully! Please sign in.")
                return redirect('student_login')
            else:
                messages.error(request, "User account not found.")
                return redirect('student_login')

        # Reset email
        elif action == 'reset':
            request.session.pop('reset_password_data', None)
            request.session['reset_step'] = 'form'
            return redirect('student_forgot_password')

    reset_data = request.session.get('reset_password_data', {})
    return render(request, 'blog/student_forgot_password.html', {
        'step': step,
        'email': reset_data.get('email', ''),
        'username': reset_data.get('username', '')
    })


# Change password
@login_required(login_url='student_login')
def change_password(request):
    if request.method == 'POST':
        old_password = request.POST.get('old_password', '').strip()
        new_password = request.POST.get('new_password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()

        if not request.user.check_password(old_password):
            messages.error(request, "Current password is incorrect.")
            return render(request, 'blog/change_password.html')

        if len(new_password) < 6:
            messages.error(request, "New password must be at least 6 characters.")
            return render(request, 'blog/change_password.html')

        if new_password != confirm_password:
            messages.error(request, "New passwords do not match.")
            return render(request, 'blog/change_password.html')

        request.user.set_password(new_password)
        request.user.save()
        update_session_auth_hash(request, request.user)
        if Community.objects.filter(user=request.user).exists():
            return redirect('community_page', username=request.user.username)
        return redirect('student_portfolio_profile', username=request.user.username)

    # Render template
    context = {
        'is_club': Community.objects.filter(user=request.user).exists(),
    }
    return render(request, 'blog/change_password.html', context)


# Check student email
@login_required(login_url='student_login')
def student_email_check(request):
    new_email = request.GET.get('email', '').strip().lower()
    current_email = (request.user.email or '').strip().lower()

    if not new_email:
        return JsonResponse({'status': 'empty', 'message': 'Please enter an email address.'})

    if new_email == current_email:
        return JsonResponse({'status': 'current', 'message': 'Current email address.'})

    is_club = Community.objects.filter(user=request.user).exists()
    if is_club:
        if not re.fullmatch(CLUB_EMAIL_REGEX, new_email):
            return JsonResponse({'status': 'invalid', 'message': 'Club email must be a valid @gmail.com address.'})
    else:
        if not re.fullmatch(STUDENT_EMAIL_REGEX, new_email):
            return JsonResponse({'status': 'invalid', 'message': 'Must follow bcet gmail format.'})

    if User.objects.filter(email__iexact=new_email).exclude(pk=request.user.pk).exists():
        return JsonResponse({'status': 'taken', 'message': 'This email is already in use by another account.'})

    return JsonResponse({'status': 'available', 'message': 'Email is available. Click Send OTP to verify.'})


# Send email OTP
@login_required(login_url='student_login')
def student_email_send_otp(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed.'}, status=405)

    new_email = request.POST.get('email', '').strip().lower()
    current_email = (request.user.email or '').strip().lower()

    if not new_email:
        return JsonResponse({'success': False, 'message': 'Email address cannot be empty.'})

    if new_email == current_email:
        return JsonResponse({'success': False, 'message': 'This is already your current email.'})

    is_club = Community.objects.filter(user=request.user).exists()
    if is_club:
        if not re.fullmatch(CLUB_EMAIL_REGEX, new_email):
            return JsonResponse({'success': False, 'message': 'Club email must be a valid @gmail.com address.'})
    else:
        if not re.fullmatch(STUDENT_EMAIL_REGEX, new_email):
            return JsonResponse({'success': False, 'message': 'Must follow bcet gmail format.'})

    if User.objects.filter(email__iexact=new_email).exclude(pk=request.user.pk).exists():
        return JsonResponse({'success': False, 'message': 'This email is already registered to another account.'})

    otp = str(random.randint(100000, 999999))
    request.session['email_change_data'] = {
        'new_email': new_email,
        'otp': otp,
    }
    if request.session.get('email_change_verified_email') != new_email:
        request.session.pop('email_change_verified_email', None)
    request.session.modified = True

    success, err = send_email_change_otp(new_email, request.user.username, otp)
    if not success:
        return JsonResponse({'success': False, 'message': f'Failed to send OTP: {err}'})

    return JsonResponse({'success': True, 'message': f'OTP sent successfully to {new_email}'})


# Verify email OTP
@login_required(login_url='student_login')
def student_email_verify_otp(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed.'}, status=405)

    entered_otp = request.POST.get('otp', '').strip()
    new_email = request.POST.get('email', '').strip().lower()

    change_data = request.session.get('email_change_data')
    if not change_data:
        return JsonResponse({'success': False, 'message': 'Session expired. Please click Send OTP again.'})

    session_email = change_data.get('new_email', '').lower()
    session_otp = change_data.get('otp', '')

    if session_email != new_email:
        return JsonResponse({'success': False, 'message': 'Email does not match requested OTP.'})

    if entered_otp != session_otp:
        return JsonResponse({'success': False, 'message': 'Invalid OTP code. Please enter the correct 6-digit code.'})

    request.session['email_change_verified_email'] = new_email
    request.session.modified = True

    return JsonResponse({'success': True, 'message': 'Email verified successfully!'})

# DOB-Countdown
def birthday_countdown(request, dob, username):
    try:
        dob_date = date.fromisoformat(dob)
    except ValueError:
        return HttpResponse("Invalid date", status=400)

    now = timezone.localtime()
    today = now.date()

    # Today Birthday
    if today.month == dob_date.month and today.day == dob_date.day:
        return render(request, "blog/includes/birthday_countdown.html", {
            "is_birthday": True,
            "username": username,
        })

    # Next birthday calculate
    year = today.year + (
        (today.month, today.day) > (dob_date.month, dob_date.day)
    )

    try:
        birthday = date(year, dob_date.month, dob_date.day)
    except ValueError:  # 29 February
        birthday = date(year, 2, 28)

    target = timezone.make_aware(
        datetime.combine(birthday, time.min),
        timezone.get_current_timezone(),
    )

    remaining = max(0, int((target - now).total_seconds()))

    return render(request, "blog/includes/birthday_countdown.html", {
        "is_birthday": False,
        "username": username,
        "days": remaining // 86400,
        "hours": (remaining % 86400) // 3600,
        "minutes": (remaining % 3600) // 60,
        "seconds": remaining % 60,
    })

# Edit portfolio
@login_required(login_url='student_login')
def student_portfolio_edit(request, username):
    if request.user.username.lower() != username.lower() and not request.user.is_superuser:
        messages.error(request, "You can only edit your own portfolio.")
        return redirect('student_portfolio_profile', username=username)

    portfolio, _ = StudentPortfolio.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        # Update username
        new_username = request.POST.get('username', '').strip().lower()
        if new_username and new_username != request.user.username:
            if len(new_username) < 4 or not re.fullmatch(r"[a-z0-9_.]{4,20}", new_username):
                messages.error(request, "Username must be 4-20 chars with lowercase letters, numbers, _, or .")
                return redirect('student_portfolio_edit', username=request.user.username)

            if new_username.startswith((".", "_")) or new_username.endswith((".", "_")) or ".." in new_username:
                messages.error(request, "Username cannot start/end with dot or underscore or have double dots.")
                return redirect('student_portfolio_edit', username=request.user.username)

            if new_username in RESTRICTED_USERNAMES:
                messages.error(request, "This username is reserved. Choose another.")
                return redirect('student_portfolio_edit', username=request.user.username)

            if User.objects.filter(username__iexact=new_username).exclude(pk=request.user.pk).exists():
                messages.error(request, "Username is already taken. Choose another.")
                return redirect('student_portfolio_edit', username=request.user.username)

            request.user.username = new_username
            request.user.save(update_fields=['username'])

        # Update email
        new_email = request.POST.get('email', '').strip().lower()
        current_email = (request.user.email or '').strip().lower()
        if new_email and new_email != current_email:
            if not re.fullmatch(STUDENT_EMAIL_REGEX, new_email):
                messages.error(request, "Invalid email. Must follow bcet gmail format.")
                return redirect('student_portfolio_edit', username=request.user.username)

            if User.objects.filter(email__iexact=new_email).exclude(pk=request.user.pk).exists():
                messages.error(request, "This email is already in use by another account.")
                return redirect('student_portfolio_edit', username=request.user.username)

            entered_email_otp = request.POST.get('email_otp', '').strip()
            verified_in_session = request.session.get('email_change_verified_email') == new_email
            matches_session_otp = (
                request.session.get('email_change_data', {}).get('new_email') == new_email and
                request.session.get('email_change_data', {}).get('otp') == entered_email_otp
            )

            if verified_in_session or matches_session_otp:
                request.user.email = new_email
                request.user.save(update_fields=['email'])
                request.session.pop('email_change_data', None)
                request.session.pop('email_change_verified_email', None)
                request.session.modified = True
                send_email_changed_success(new_email, request.user.username)
                messages.success(request, f"Email address updated to {new_email}!")
            else:
                messages.error(request, "Please verify your new email address with OTP before saving.")
                return redirect('student_portfolio_edit', username=request.user.username)

        # Visibility setting
        vis = request.POST.get('visibility')
        if vis:
            if vis == 'block':
                portfolio.is_block = True
                portfolio.is_public = False
            elif vis == 'private':
                portfolio.is_block = False
                portfolio.is_public = False
            else:
                portfolio.is_block = False
                portfolio.is_public = True
        else:
            is_public_val = request.POST.get('is_public')
            if is_public_val in ['block', 'blocked']:
                portfolio.is_block = True
                portfolio.is_public = False
            elif is_public_val in ['0', 'false', 'False', 'private']:
                portfolio.is_block = False
                portfolio.is_public = False
            else:
                portfolio.is_block = False
                portfolio.is_public = True

        # Academic details
        adm_year = request.POST.get('admission_year', '').strip()
        portfolio.admission_year = int(adm_year) if adm_year.isdigit() else None

        sem_val = request.POST.get('current_semester', '').strip()
        if sem_val.isdigit() and 1 <= int(sem_val) <= 8:
            portfolio.current_semester = int(sem_val)
        else:
            portfolio.current_semester = None

        is_grad = request.POST.get('is_graduated')
        portfolio.is_graduated = (is_grad in ['1', 'true', 'True', 'on']) or (sem_val == 'graduated')

        dur_val = request.POST.get('degree_duration_years', '').strip()
        portfolio.degree_duration_years = int(dur_val) if (dur_val.isdigit() and int(dur_val) > 0) else 4

        # Graduation Year (Batch)
        user_batch_val = request.POST.get('batch_year', '').strip()
        if user_batch_val:
            portfolio.batch_year = user_batch_val
        elif portfolio.expected_completion_year:
            portfolio.batch_year = str(portfolio.expected_completion_year)

        # Details
        portfolio.full_name = request.POST.get('full_name', '').strip()
        portfolio.headline = request.POST.get('headline', '').strip()
        portfolio.department = request.POST.get('department', '').strip()
        portfolio.bio = request.POST.get('bio', '').strip()
        portfolio.skills = request.POST.get('skills', '').strip()
        portfolio.website = request.POST.get('website', '').strip()
        portfolio.github = request.POST.get('github', '').strip()
        portfolio.linkedin = request.POST.get('linkedin', '').strip()

        # Gender
        portfolio.gender = request.POST.get('gender', '').strip()

        # DOB
        dob = request.POST.get('dob', '').strip()
        portfolio.dob = dob or None


        # Verified socials
        if portfolio.is_bluetick:
            portfolio.instagram = request.POST.get('instagram', '').strip()
            portfolio.facebook = request.POST.get('facebook', '').strip()
            portfolio.twitter = request.POST.get('twitter', '').strip()

        # Avatar handling
        if request.POST.get('clear_profile_pic'):
            if portfolio.profile_pic:
                portfolio.profile_pic.delete(save=False)
                portfolio.profile_pic = None
        elif request.FILES.get('profile_pic'):
            if portfolio.profile_pic:
                portfolio.profile_pic.delete(save=False)
            portfolio.profile_pic = request.FILES['profile_pic']

        # Banner handling
        if request.POST.get('clear_banner'):
            if portfolio.banner:
                portfolio.banner.delete(save=False)
                portfolio.banner = None
        elif request.FILES.get('banner'):
            if portfolio.banner:
                portfolio.banner.delete(save=False)
            portfolio.banner = request.FILES['banner']

        # Resume handling
        if request.POST.get('clear_resume'):
            if portfolio.resume:
                portfolio.resume.delete(save=False)
                portfolio.resume = None
        elif request.FILES.get('resume'):
            if portfolio.resume:
                portfolio.resume.delete(save=False)
            portfolio.resume = request.FILES['resume']

        portfolio.save()
        messages.success(request, "Portfolio updated successfully!")
        return redirect('student_portfolio_profile', username=request.user.username)

    return render(request, 'blog/student_edit_portfolio.html', {
        'portfolio': portfolio,
        'profile_user': request.user,
        'gender_list': portfolio._meta.get_field('gender').choices,
    })


# Student profile
def student_portfolio_profile(request, username):
    user_obj = get_object_or_404(User, username__iexact=username)
    portfolio, _ = StudentPortfolio.objects.get_or_create(user=user_obj)
    is_owner = request.user.is_authenticated and request.user == user_obj

    # Relationship badge
    relationship_badge = None
    if request.user.is_authenticated and not is_owner:
        relationship_badge = portfolio.get_relationship_to(request.user)

    # Blocked profile check
    if portfolio.is_block and not is_owner:
        return render(request, 'blog/student_portfolio_profile.html', {
            'profile_user': user_obj,
            'portfolio': portfolio,
            'is_owner': False,
            'is_private_locked': False,
            'is_blocked_locked': True,
            'relationship_badge': None,
        })

    # Privacy check
    if not portfolio.is_public and not is_owner:
        return render(request, 'blog/student_portfolio_profile.html', {
            'profile_user': user_obj,
            'portfolio': portfolio,
            'is_owner': False,
            'is_private_locked': True,
            'is_blocked_locked': False,
            'relationship_badge': None,
        })

    return render(request, 'blog/student_portfolio_profile.html', {
        'profile_user': user_obj,
        'portfolio': portfolio,
        'is_owner': is_owner,
        'is_private_locked': False,
        'is_blocked_locked': False,
        'relationship_badge': relationship_badge,
    })
