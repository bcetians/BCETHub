from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.conf import settings
import os
import shutil

class Course(models.Model):
    name = models.CharField(max_length=100, help_text="e.g. B.Tech, M.Tech, MBA")
    code = models.CharField(max_length=20, unique=True, help_text="e.g. BTECH, MTECH, MBA")

    class Meta:
        verbose_name_plural = "Courses"

    def __str__(self):
        return f"{self.name} ({self.code})"

# Academic Branch 
class Branch(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='branches')
    name = models.CharField(max_length=100, help_text="e.g. Computer Science & Engineering")
    code = models.CharField(max_length=20, unique=True, help_text="e.g. CSE, CSE-AIML, ECE, EE, IT, ME, CE")

    class Meta:
        verbose_name_plural = "Branches"

    def __str__(self):
        return f"{self.name} ({self.code})"

# Academic Year Management
class AcademicYear(models.Model):
    YEAR_CHOICES = [
        ('1', '1st Year'),
        ('2', '2nd Year'),
        ('3', '3rd Year'),
        ('4', '4th Year'),
    ]
    year = models.CharField(max_length=2, choices=YEAR_CHOICES, unique=True)

    def __str__(self):
        return f"{self.get_year_display()}"

class Section(models.Model):
    name = models.CharField(max_length=100, help_text="e.g. A, B, C")
    def __str__(self):
        return self.name

# Faculty Directory for the College
class Faculty(models.Model):
    DESIGNATION_CHOICES = [
        ('HOD', 'Head of Department'),
        ('PROF', 'Professor'),
        ('ASSOC_PROF', 'Associate Professor'),
        ('ASST_PROF', 'Assistant Professor'),
        ('STAFF', 'Supporting Staff'),
    ]

    name = models.CharField(max_length=100)
    short_code = models.CharField(max_length=30, blank=True, null=True, help_text="e.g. AR(PH), BA(M), RKA(PH)")
    designation = models.CharField(max_length=20, choices=DESIGNATION_CHOICES, default='ASST_PROF')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='faculties')
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Faculties"
        ordering = ['name']

    def __str__(self):
        code_str = f" [{self.short_code}]" if self.short_code else ""
        return f"{self.name}{code_str} - {self.get_designation_display()} ({self.branch.code})"


# Induction Program for 1st Year Students
class InductionProgram(models.Model):
    day_number = models.IntegerField(help_text="e.g. 1, 2, 3... 21")
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    topic_programme = models.CharField(max_length=255, help_text="e.g. AI & Next Generation, Universal Human Values")
    assigned_faculty = models.ManyToManyField(Faculty, blank=True, related_name='induction_sessions')
    assigned_persons_text = models.CharField(max_length=255, blank=True, null=True, help_text="Text representation of speakers")
    external_guest = models.CharField(max_length=200, blank=True, null=True, help_text="Any external speaker name")
    venue = models.CharField(max_length=150, default="CSE Seminar Hall")
    branches_applicable = models.ManyToManyField(Branch, blank=True, help_text="Applicable for specific or all branches")
    material_file = models.FileField(upload_to='induction_materials/', blank=True, null=True, help_text="Upload session PDF or PPT presentation")

    class Meta:
        ordering = ['day_number', 'start_time']
        verbose_name = "Induction Program Session"
        verbose_name_plural = "Induction Program Schedule"

    def __str__(self):
        return f"Day {self.day_number} ({self.date.strftime('%d/%m/%Y')}) | {self.topic_programme}"

    def status(self, target_date=None, target_time=None):
        if target_date is None:
            now = timezone.localtime()
            target_date = now.date()
            target_time = now.time()

        if self.date < target_date:
            return 'PAST'
        elif self.date > target_date:
            return 'UPCOMING'
        else: 
            if target_time < self.start_time:
                return 'UPCOMING'
            elif self.start_time <= target_time <= self.end_time:
                return 'LIVE'
            else:
                return 'PAST'

# Class Routine Timetable
class RoutineSlot(models.Model):
    DAY_CHOICES = [
        ('MON', 'Monday'),
        ('TUE', 'Tuesday'),
        ('WED', 'Wednesday'),
        ('THU', 'Thursday'),
        ('FRI', 'Friday'),
        ('SAT', 'Saturday'),
        ('SUN', 'Sunday'),
    ]

    year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='routine_slots')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='routine_slots')
    section_name = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='routine_slots')
    lh_room = models.CharField(max_length=50, help_text="e.g. LH-234, LH-232, LH-231, LH-233, LH-235, LH-236")
    day = models.CharField(max_length=3, choices=DAY_CHOICES)
    slot_number = models.IntegerField(help_text="Slot 1-9")
    start_time = models.TimeField()
    end_time = models.TimeField()
    subject_code = models.CharField(max_length=100, help_text="e.g. BS-PH 101, ES-EE 101, Induction Program")
    subject_name = models.CharField(max_length=150, blank=True, null=True, help_text="Full subject name if any")
    faculty_code = models.CharField(max_length=100, blank=True, null=True, help_text="e.g. AR(PH), BA(M), NF(EE)")
    faculty_ref = models.ForeignKey(Faculty, on_delete=models.SET_NULL, null=True, blank=True, related_name='routine_slots')

    class Meta:
        ordering = ['section_name', 'day', 'slot_number']
        verbose_name = "Class Routine Slot"
        verbose_name_plural = "Class Routine Timetable"

    def __str__(self):
        return f"{self.section_name} ({self.lh_room}) | {self.get_day_display()} Slot {self.slot_number}: {self.subject_code}"

    def status(self, target_day=None, target_time=None, current_day=None):
        now = timezone.localtime()
        days_map = {0: 'MON', 1: 'TUE', 2: 'WED', 3: 'THU', 4: 'FRI', 5: 'SAT', 6: 'SUN'}

        if current_day is None:
            current_day = days_map[now.weekday()]
        if target_time is None:
            target_time = now.time()
        if target_day is None:
            target_day = current_day

        if self.day != target_day:
            return 'OTHER_DAY'

        # Only evaluate live status for current actual day
        if target_day != current_day:
            return 'SCHEDULED'

        if target_time < self.start_time:
            return 'UPCOMING'
        elif self.start_time <= target_time <= self.end_time:
            return 'LIVE'
        else:
            return 'PAST'

# Mess Menu for the Hostel
class MessTiming(models.Model):
    MEAL_CHOICES = [
        ('BREAKFAST', 'Breakfast'),
        ('LUNCH', 'Lunch'),
        ('HI_TEA', 'Evening Hi-Tea'),
        ('DINNER', 'Dinner'),
    ]
    
    meal_type = models.CharField(max_length=20, choices=MEAL_CHOICES)
    academic_years = models.ManyToManyField(AcademicYear, help_text="Select 1st & 2nd Year OR 3rd & 4th Year")
    start_time = models.TimeField()
    end_time = models.TimeField()

    def __str__(self):
        years = ", ".join([y.get_year_display() for y in self.academic_years.all()])
        return f"{self.get_meal_type_display()} ({years}): {self.start_time.strftime('%I:%M %p')} - {self.end_time.strftime('%I:%M %p')}"

    def status(self, target_time=None):
        if target_time is None:
            target_time = timezone.localtime().time()
            
        if target_time < self.start_time:
            return 'UPCOMING'
        elif self.start_time <= target_time <= self.end_time:
            return 'LIVE'
        else:
            return 'PAST'

# Daily Mess Menu for the Hostel
class DailyMessMenu(models.Model):
    DAY_CHOICES = [
        ('MON', 'Monday'),
        ('TUE', 'Tuesday'),
        ('WED', 'Wednesday'),
        ('THU', 'Thursday'),
        ('FRI', 'Friday'),
        ('SAT', 'Saturday'),
        ('SUN', 'Sunday'),
    ]

    day_of_week = models.CharField(max_length=3, choices=DAY_CHOICES, unique=True)
    breakfast = models.TextField(help_text="Items served during Breakfast")
    lunch = models.TextField(help_text="Items served during Lunch")
    hi_tea = models.TextField(help_text="Items served during Evening Tea/Snacks")
    dinner = models.TextField(help_text="Items served during Dinner")

    class Meta:
        verbose_name = "Daily Mess Menu"
        verbose_name_plural = "Hostel Mess Menus"

    def __str__(self):
        return f"Mess Menu - {self.get_day_of_week_display()}"

class Pooling(models.Model):
    pool = models.IntegerField(default=0)

    def __str__(self):
        return f"{((self.pool)/50)*100}%"


# User Feedback
class Feedback(models.Model):
    CATEGORY_CHOICES = [
        ('BUG', 'Bug Report'),
        ('IDEA', 'Suggestion / Idea'),
        ('OTHER', 'General Feedback'),
    ]

    name = models.CharField(max_length=100, help_text="User Name")
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='BUG')
    contact = models.CharField(max_length=200, help_text="User Contact", blank=True)
    message = models.TextField(help_text="User Message")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "User Feedback"
        verbose_name_plural = "User Feedbacks"

    def __str__(self):
        return f"[{self.get_category_display()}] {self.name} ({self.created_at.strftime('%d/%m/%Y')})"

class CRProfile(models.Model):
    name = models.CharField(max_length=100, help_text="CR Name")
    year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='cr_profiles')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='cr_profiles')
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='cr_profiles')
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Class Representative Profiles"
        ordering = ['branch', 'section', 'name']

    def __str__(self):
        return f"{self.name} - {self.branch.code} Section {self.section}"

class Module(models.Model):
    name = models.CharField(max_length=100, help_text="Name of the module")
    code = models.CharField(max_length=20, unique=True, help_text="e.g. DSA01, CN01")

    class Meta:
        verbose_name_plural = "Modules"

    def __str__(self):
        return f"{self.name} ({self.code})"

class Subject(models.Model):
    name = models.CharField(max_length=200, help_text="Name of the subject")
    code = models.CharField(max_length=20, unique=True, help_text="e.g. DSA, CN, DBMS")

    class Meta:
        verbose_name_plural = "Subjects"

    def __str__(self):
        return f"{self.name} ({self.code})"

class Notes(models.Model):
    title = models.CharField(max_length=200, help_text="Title of the notes")
    description = models.TextField(help_text="Brief description of the notes")
    file = models.FileField(upload_to='notes_files/', blank=True, null=True, help_text="Upload the notes file (PDF, DOCX, etc.)")
    year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='notes')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='notes')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='notes')
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='notes')
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='notes', blank=True, null=True)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='notes', blank=True, null=True)
    cr = models.ForeignKey(CRProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='notes', help_text="CR who provided this note")
    cr_name = models.CharField(max_length=100, blank=True, null=True, help_text="CR / Author Name e.g. Rishabh Kumar")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']
        verbose_name_plural = "Notes"

    def __str__(self):
        return f"{self.title} - {self.branch.code} Section {self.section}"

    def get_cr_name(self):
        if self.cr:
            return self.cr.name
        elif self.cr_name:
            return self.cr_name
        return "CR / Contributor"

import io
from PIL import Image
from django.core.files.base import ContentFile

class NoteImage(models.Model):
    note = models.ForeignKey(Notes, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='notes_images/')
    caption = models.CharField(max_length=150, blank=True, null=True, help_text="Optional caption for page e.g. Page 1")
    order = models.PositiveIntegerField(default=0, help_text="Order/Page Number")

    class Meta:
        ordering = ['order', 'id']
        verbose_name = "Note Image"
        verbose_name_plural = "Note Images"

    def __str__(self):
        return f"Image {self.order} for {self.note.title}"

    def save(self, *args, **kwargs):
        if self.image and hasattr(self.image, 'file'):
            try:
                img = Image.open(self.image)
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
                
                orig_w, orig_h = img.size
                if orig_w > 2000 or orig_h > 2000:
                    img.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
                
                output = io.BytesIO()
                img.save(output, format='JPEG', quality=88, optimize=True)
                output.seek(0)
                
                filename = self.image.name.rsplit('.', 1)[0] + '.jpg'
                self.image.save(filename, ContentFile(output.read()), save=False)
            except Exception:
                pass
        super().save(*args, **kwargs)


class PYQ(models.Model):
    SEMESTER_CHOICES = [
        ('1', '1st Semester'),
        ('2', '2nd Semester'),
        ('3', '3rd Semester'),
        ('4', '4th Semester'),
        ('5', '5th Semester'),
        ('6', '6th Semester'),
        ('7', '7th Semester'),
        ('8', '8th Semester'),
    ]

    title = models.CharField(max_length=200, help_text="Title of the PYQ (e.g. End Sem Exam 2024)")
    description = models.TextField(blank=True, null=True, help_text="Details / instructions for this paper")
    file = models.FileField(upload_to='pyq_files/', blank=True, null=True, help_text="Upload PYQ PDF or DOCX file")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='pyqs')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='pyqs')
    year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='pyqs')
    semester = models.CharField(max_length=2, choices=SEMESTER_CHOICES, default='1')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='pyqs', blank=True, null=True)
    exam_year = models.IntegerField(default=2024, help_text="e.g. 2023, 2024, 2025")
    cr_name = models.CharField(max_length=100, blank=True, null=True, help_text="Uploaded by CR / Contributor")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-exam_year', '-uploaded_at']
        verbose_name = "Previous Year Question"
        verbose_name_plural = "Previous Year Questions (PYQs)"

    def __str__(self):
        return f"{self.title} - {self.get_semester_display()} ({self.exam_year})"

    def get_cr_name(self):
        return self.cr_name if self.cr_name else "CR / Contributor"


class PYQImage(models.Model):
    pyq = models.ForeignKey(PYQ, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='pyq_images/')
    caption = models.CharField(max_length=150, blank=True, null=True, help_text="e.g. Question Paper Page 1")
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = "PYQ Image"
        verbose_name_plural = "PYQ Images"

    def __str__(self):
        return f"Page {self.order} for {self.pyq.title}"

    def save(self, *args, **kwargs):
        if self.image and hasattr(self.image, 'file'):
            try:
                img = Image.open(self.image)
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
                
                orig_w, orig_h = img.size
                if orig_w > 2000 or orig_h > 2000:
                    img.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
                
                output = io.BytesIO()
                img.save(output, format='JPEG', quality=88, optimize=True)
                output.seek(0)
                
                filename = self.image.name.rsplit('.', 1)[0] + '.jpg'
                self.image.save(filename, ContentFile(output.read()), save=False)
            except Exception:
                pass
        super().save(*args, **kwargs)


class Assignment(models.Model):
    SEMESTER_CHOICES = [
        ('1', '1st Semester'),
        ('2', '2nd Semester'),
        ('3', '3rd Semester'),
        ('4', '4th Semester'),
        ('5', '5th Semester'),
        ('6', '6th Semester'),
        ('7', '7th Semester'),
        ('8', '8th Semester'),
    ]

    title = models.CharField(max_length=200, help_text="Title of the Assignment (e.g. End Sem Exam 2024)")
    description = models.TextField(blank=True, null=True, help_text="Details / instructions for this paper")
    file = models.FileField(upload_to='pyq_files/', blank=True, null=True, help_text="Upload Assignment PDF or DOCX file")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='assignments')
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='assignments')
    year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='assignments')
    semester = models.CharField(max_length=2, choices=SEMESTER_CHOICES, default='1')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='assignments', blank=True, null=True)
    author = models.CharField(max_length=100, blank=True, null=True, help_text="Uploaded by / Contributor")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = "Assignment"
        verbose_name_plural = "Assignments"

    def get_author_name(self):
        return self.author if self.author else "Author / Contributor"

class Notice(models.Model):
    is_active = models.BooleanField(default=False)
    icon = models.CharField(max_length=2000, help_text="Add lucide icon name.", blank=True, null=True)
    notice = models.CharField(max_length=5000, blank=True, null=True)
    n_url = models.CharField(max_length=5000, blank=True, null=True)
    n_url_name = models.CharField(max_length=20, blank=True, null=True)
    n_url_icon = models.CharField(max_length=2000, blank=True, null=True, help_text="Add lucide icon name.")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Notice: {self.notice[:40]}" if self.notice else f"Notice #{self.id}"


class RoutineFile(models.Model):
    title = models.CharField(max_length=150, default="Class Routine Timetable (CSV/Excel)")
    file = models.FileField(upload_to='routine/', help_text="Upload CSV file for Class Routine")
    is_active = models.BooleanField(default=True, help_text="Set as active routine CSV file")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Class Routine CSV File"
        verbose_name_plural = "Class Routine CSV Files"

    def __str__(self):
        return f"{self.title} (Updated: {self.updated_at.strftime('%d %b %Y, %I:%M %p')})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.file and os.path.exists(self.file.path):
            dest_media = os.path.join(settings.MEDIA_ROOT, 'routine', 'routine.csv')
            os.makedirs(os.path.dirname(dest_media), exist_ok=True)
            if os.path.abspath(self.file.path) != os.path.abspath(dest_media):
                shutil.copy(self.file.path, dest_media)
            
            dest_static = os.path.join(settings.BASE_DIR, 'static', 'data', 'routine.csv')
            os.makedirs(os.path.dirname(dest_static), exist_ok=True)
            shutil.copy(self.file.path, dest_static)

# group type model
class CommunityGroupType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)

    class Meta:
        verbose_name = "Community Group Type"
        verbose_name_plural = "Community Group Types"

    # save group slug
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    # show group name
    def __str__(self):
        return self.name

# club community model
class Community(models.Model):
    group_type = models.ForeignKey(
        CommunityGroupType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='communities'
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='community_profile',
        null=True,
        blank=True,
    )

    group_name = models.CharField(max_length=2000)
    group_dec = models.CharField(max_length=5000)

    group_logo = models.FileField(
        upload_to='group-logo/',
        blank=True,
        null=True
    )
    
    banner = models.ImageField(
        upload_to='group-banner/',
        blank=True,
        null=True
    )

    instagram = models.CharField(max_length=2000, blank=True, null=True)
    facebook = models.CharField(max_length=2000, blank=True, null=True)
    linkedin = models.CharField(max_length=2000, blank=True, null=True)
    discord = models.CharField(max_length=2000, blank=True, null=True)
    other = models.CharField(max_length=2000, blank=True, null=True)
    other_title = models.CharField(max_length=2000, blank=True, null=True)
    join = models.CharField(max_length=2000, blank=True, null=True)

    is_bluetick = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)

    # return username string
    @property
    def username(self):
        return self.user.username if self.user else ""

    # return group title
    @property
    def get_group_type_display(self):
        return self.group_type.name if self.group_type else "Other"

    # save user community
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    # show club name
    def __str__(self):
        if self.user_id:
            return f"@{self.user.username} - {self.group_name}"
        return self.group_name

# community post model
class CommunityPost(models.Model):

    POST_TYPES = [
        ('EVENT', 'Event'),
        ('ACTIVITY', 'Activity'),
        ('ACHIEVEMENT', 'Achievement'),
        ('BLOG', 'Blog'),
        ('ANNOUNCEMENT', 'Announcement'),
    ]

    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('PUBLISHED', 'Published'),
    ]

    EVENT_STATUS_CHOICES = [
        ('UPCOMING', 'Upcoming'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
    ]

    community = models.ForeignKey(
        Community,
        on_delete=models.CASCADE,
        related_name='posts'
    )

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220)
    post_type = models.CharField(
        max_length=20,
        choices=POST_TYPES,
        default='BLOG'
    )

    description = models.TextField()
    cover_image = models.ImageField(
        upload_to='community_posts/covers/',
        blank=True,
        null=True
    )

    event_date = models.DateTimeField(
        blank=True,
        null=True
    )
    venue = models.CharField(
        max_length=255,
        blank=True
    )
    event_status = models.CharField(
        max_length=20,
        choices=EVENT_STATUS_CHOICES,
        blank=True
    )

    link_title = models.CharField(
        max_length=100,
        blank=True
    )
    link_url = models.URLField(
        max_length=2000,
        blank=True,
        null=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='DRAFT'
    )

    published_at = models.DateTimeField(
        blank=True,
        null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['community', 'slug'],
                name='unique_community_post_slug'
            )
        ]

    # dynamic event status
    @property
    def computed_event_status(self):
        if self.event_status == 'CANCELLED':
            return 'CANCELLED'
        if self.event_date:
            now = timezone.localtime()
            if self.event_date > now:
                return 'UPCOMING'
            else:
                return 'COMPLETED'
        return self.event_status or ''

    # dynamic status label
    @property
    def computed_status_label(self):
        st = self.computed_event_status
        if st == 'CANCELLED':
            return 'Cancelled'
        elif st == 'UPCOMING':
            return 'Upcoming'
        elif st == 'COMPLETED':
            return 'Completed'
        return ''

    # clean text snippet
    @property
    def clean_snippet(self):
        import re
        txt = self.description or ''
        txt = re.sub(r'#+\s*', '', txt)
        txt = re.sub(r'[*_`~>\[\]]', '', txt)
        words = txt.split()
        if len(words) > 22:
            return ' '.join(words[:22]) + '...'
        return ' '.join(words)

    # save post slug
    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title) or "post"
            slug = base_slug
            counter = 1
            while CommunityPost.objects.filter(community=self.community, slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    # return post title
    def __str__(self):
        return f"{self.community.username}: {self.title}"

# community multiple imge post model
class CommunityPostImage(models.Model):
    post = models.ForeignKey(
        CommunityPost,
        on_delete=models.CASCADE,
        related_name='images'
    )
    image = models.ImageField(
        upload_to='community_posts/gallery/'
    )
    caption = models.CharField(
        max_length=200,
        blank=True
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

# holidays models
class Holiday(models.Model):
    title = models.CharField(max_length=200)
    dec = models.CharField(max_length=200, blank=True, null=True)
    holiday_start = models.DateField(null=True, blank=True)
    holiday_end = models.DateField(null=True, blank=True)
    is_class = models.BooleanField(default=False)
    is_mess = models.BooleanField(default=False)

    # auto set date
    def save(self, *args, **kwargs):
        if self.holiday_start and not self.holiday_end:
            self.holiday_end = self.holiday_start
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} - {self.holiday_start or 'No Date'}"

GENDER_LIST = ["Male", "Female", "Other", "Prefer not to say"]

# portfolio model
class StudentPortfolio(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='student_portfolio'
    )
    full_name = models.CharField(max_length=150, blank=True, null=True, help_text="Full name of student")
    gender = models.CharField(
        max_length=20,
        choices=[(g, g) for g in GENDER_LIST],
        blank=True,
    )
    dob = models.DateField(blank=True, null=True)
    headline = models.CharField(max_length=220, blank=True, null=True, help_text="Tagline e.g. Full Stack Developer | GDG Member")
    batch_year = models.CharField(max_length=10, blank=True, null=True)
    department = models.CharField(max_length=120, blank=True, null=True, help_text="Department / Branch e.g. Computer Science & Engineering")
    bio = models.TextField(blank=True, null=True)
    skills = models.TextField(blank=True, null=True, help_text="Comma-separated skills e.g. Python, Django, React, Git")

    profile_pic = models.ImageField(
        upload_to='portfolios/profiles/',
        blank=True,
        null=True
    )
    banner = models.ImageField(
        upload_to='portfolios/banners/',
        blank=True,
        null=True
    )

    # Resume file
    resume = models.FileField(
        upload_to='portfolios/resumes/',
        blank=True,
        null=True
    )

    website = models.URLField(max_length=2000, blank=True, null=True)
    github = models.URLField(max_length=2000, blank=True, null=True)
    linkedin = models.URLField(max_length=2000, blank=True, null=True)

    # Academic details
    admission_year = models.PositiveIntegerField(blank=True, null=True)
    current_semester = models.PositiveSmallIntegerField(blank=True, null=True)
    is_graduated = models.BooleanField(default=False)
    degree_duration_years = models.PositiveSmallIntegerField(default=4)

    # Verification status
    is_bluetick = models.BooleanField(default=False)
    is_public = models.BooleanField(default=True)
    is_block = models.BooleanField(default=False)

    # Social links
    instagram = models.CharField(max_length=2000, blank=True, null=True)
    facebook = models.CharField(max_length=2000, blank=True, null=True)
    twitter = models.CharField(max_length=2000, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def display_name(self):
        if self.full_name and self.full_name.strip():
            return self.full_name.strip()
        full = self.user.get_full_name().strip() if self.user else ""
        if full:
            return full
        return self.user.username if self.user else "Student"

    @property
    def skills_list(self):
        if not self.skills:
            return []
        return [s.strip() for s in self.skills.split(',') if s.strip()]

    @property
    def is_academic_setup(self):
        # Academic setup status
        return bool(self.admission_year or self.current_semester or self.is_graduated)

    @property
    def is_profile_setup(self):
        # Profile setup status
        if self.is_academic_setup:
            return True
        if self.full_name and self.full_name.strip():
            return True
        if self.department and self.department.strip():
            return True
        if self.headline and self.headline.strip():
            return True
        if self.bio and self.bio.strip():
            return True
        return False

    @property
    def calculated_academic_year(self):
        # Academic year calculation
        import datetime
        if not self.is_academic_setup:
            return "New"
        if self.is_graduated:
            return "Passout"
        if self.current_semester:
            if self.current_semester in [1, 2]:
                return "1st Year"
            elif self.current_semester in [3, 4]:
                return "2nd Year"
            elif self.current_semester in [5, 6]:
                return "3rd Year"
            elif self.current_semester in [7, 8]:
                return "4th Year"
            elif self.current_semester > 8:
                return "Passout"
        if self.admission_year:
            now_year = datetime.date.today().year
            now_month = datetime.date.today().month
            curr_academic = now_year if now_month >= 7 else (now_year - 1)
            diff = curr_academic - self.admission_year + 1
            if diff <= 1:
                return "1st Year"
            elif diff == 2:
                return "2nd Year"
            elif diff == 3:
                return "3rd Year"
            elif diff == 4:
                return "4th Year"
            else:
                return "Passout"
        return "New"

    @property
    def expected_completion_year(self):
        # Expected graduation year
        if self.admission_year:
            dur = self.degree_duration_years or 4
            return self.admission_year + dur
        if self.is_academic_setup and self.batch_year:
            try:
                by = int(self.batch_year)
                return by if by > 100 else (2000 + by)
            except (ValueError, TypeError):
                pass
        return None

    @property
    def academic_year_rank(self):
        # Academic rank calculation
        yr = self.calculated_academic_year
        if yr == "Passout":
            return 5
        elif yr == "4th Year":
            return 4
        elif yr == "3rd Year":
            return 3
        elif yr == "2nd Year":
            return 2
        elif yr == "1st Year":
            return 1
        return 0

    def get_relationship_to(self, viewer_user):
        # Relationship comparison
        if not viewer_user or not viewer_user.is_authenticated:
            return None
        if viewer_user == self.user:
            return None
        viewer_portfolio = getattr(viewer_user, 'student_portfolio', None)
        if not viewer_portfolio:
            return None

        # Requires academic setup
        if not self.is_academic_setup or not viewer_portfolio.is_academic_setup:
            return None

        # Compare admission years
        if self.admission_year and viewer_portfolio.admission_year:
            if self.admission_year < viewer_portfolio.admission_year:
                return {'type': 'senior', 'label': 'Senior'}
            elif self.admission_year > viewer_portfolio.admission_year:
                return {'type': 'junior', 'label': 'Junior'}
            else:
                return {'type': 'batchmate', 'label': 'Batchmate'}

        # Compare academic rank
        s_rank = self.academic_year_rank
        v_rank = viewer_portfolio.academic_year_rank
        if s_rank > 0 and v_rank > 0:
            if s_rank > v_rank:
                return {'type': 'senior', 'label': 'Senior'}
            elif s_rank < v_rank:
                return {'type': 'junior', 'label': 'Junior'}
            else:
                return {'type': 'batchmate', 'label': 'Batchmate'}

        return None

    @property
    def instagram_url(self):
        if not self.instagram:
            return ''
        val = self.instagram.strip()
        if val.startswith('http://') or val.startswith('https://'):
            return val
        val = val.lstrip('@')
        return f"https://instagram.com/{val}"

    @property
    def twitter_url(self):
        if not self.twitter:
            return ''
        val = self.twitter.strip()
        if val.startswith('http://') or val.startswith('https://'):
            return val
        val = val.lstrip('@')
        return f"https://x.com/{val}"

    @property
    def facebook_url(self):
        if not self.facebook:
            return ''
        val = self.facebook.strip()
        if val.startswith('http://') or val.startswith('https://'):
            return val
        return f"https://facebook.com/{val}"

    def __str__(self):
        return f"@{self.user.username} - {self.display_name} ({self.calculated_academic_year or self.batch_year})"
