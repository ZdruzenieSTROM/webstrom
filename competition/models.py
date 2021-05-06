import datetime
import os
from io import BytesIO

import pdf2image

from django.contrib.sites.models import Site
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.validators import validate_slug
from django.db import models
from django.db.models import Q
from django.db.models.constraints import UniqueConstraint
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.shortcuts import get_object_or_404
from django.utils.functional import cached_property
from django.utils.timezone import now


from base.managers import UnspecifiedValueManager
from base.models import RestrictedFileField
from base.utils import mime_type
from base.validators import school_year_validator
from personal.models import Profile, School
from competition import utils
from user.models import User


class Competition(models.Model):
    """
    Model súťaže, ktorý pokrýva súťaž ako koncept. Napríklad Matboj, Seminár STROM, Kôš
    """
    class Meta:
        verbose_name = 'súťaž'
        verbose_name_plural = 'súťaže'

    COMPETITION_TYPE_CHOICES = [
        (0, 'Seminár'),
        (1, 'Jednodňová súťaž'),
        (2, 'Iné'),
    ]

    name = models.CharField(verbose_name='názov', max_length=50)
    start_year = models.PositiveSmallIntegerField(
        verbose_name='rok prvého ročníka súťaže', blank=True)
    description = models.TextField(verbose_name='Popis súťaže', blank=True)
    rules = models.TextField(
        verbose_name='Pravidlá súťaže', blank=True, null=True)

    sites = models.ManyToManyField(Site)

    competition_type = models.PositiveSmallIntegerField(
        verbose_name='typ súťaže', choices=COMPETITION_TYPE_CHOICES)

    min_years_until_graduation = models.PositiveSmallIntegerField(
        verbose_name='Minimálny počet rokov do maturity', null=True,
        help_text='Horná hranica na účasť v súťaži. '
        'Zadáva sa v počte rokov do maturity. '
        'Ak najstraší, kto môže riešiť súťaž je deviatak, zadá sa 4.')

    permission_group = models.ManyToManyField('auth.Group',
                                              blank=True,
                                              verbose_name='Skupiny práv')

    def can_user_participate(self, user):
        if self.min_years_until_graduation:
            return user.profile.year_of_graduation-utils.get_school_year_start_by_date() \
                >= self.min_years_until_graduation
        return True

    def __str__(self):
        return self.name

    @cached_property
    def semester_set(self):
        return Semester.objects.filter(competition=self.pk)

    @classmethod
    def get_seminar_by_site(cls, site):
        return get_object_or_404(cls, sites=site, competition_type=0)

    @classmethod
    def get_seminar_by_current_site(cls):
        return cls.get_seminar_by_site(Site.objects.get_current())

    def can_user_modify(self, user):
        return len(set(self.permission_group.all()).intersection(set(user.groups.all()))) > 0


class LateTag(models.Model):
    """
    Slúži na označenie riešenia po termíne.
    Každý LateTag vyjadruje druh omeškania (napríklad do 24 hodín)
    """
    class Meta:
        verbose_name = 'omeškanie'
        verbose_name_plural = 'omeškanie'

    name = models.CharField(
        verbose_name='označenie štítku pre riešiteľa', max_length=50)
    slug = models.CharField(
        verbose_name='označenie priečinku pri stiahnutí', max_length=50, validators=[validate_slug])
    upper_bound = models.DurationField(
        verbose_name='maximálna dĺžka omeškania')
    comment = models.TextField(verbose_name='komentár pre opravovateľa')

    def __str__(self):
        return self.name


class Event(models.Model):
    """
    Slúži na označenie instancie súťaže (Napríklad: Matboj 2020,
    Letný semester 40. ročníka STROMu, Jarný výlet 2021)
    """
    # pylint: disable=no-member
    class Meta:
        verbose_name = 'ročník súťaže'
        verbose_name_plural = 'ročníky súťaží'
        ordering = ['-school_year', ]

    competition = models.ForeignKey(
        Competition, null=True, on_delete=models.CASCADE)

    year = models.PositiveSmallIntegerField(verbose_name='ročník', blank=True)
    school_year = models.CharField(
        verbose_name='školský rok', max_length=10, blank=True,
        validators=[school_year_validator])

    start = models.DateTimeField(verbose_name='dátum začiatku súťaže')
    end = models.DateTimeField(verbose_name='dátum konca súťaže')

    def is_user_registered(self, user):
        return EventRegistration.objects.filter(event=self.pk, user=user).exists()

    @property
    def registered_profiles(self):
        return Profile.objects.filter(eventregistration_set__event=self.pk)

    def __str__(self):
        if self.semester:
            return str(self.semester)

        return f'{self.competition.name}, {self.year}. ročník'

    def can_user_modify(self, user):
        return self.competition.can_user_modify(user)


class Semester(Event):
    """
    Špeciálny prípad eventu pridávajúci niekoľko ďalších polí
    pre funkcionalitu semestrov korešpondenčných seminárov.
    S dodatočnými informáciami ako season(letný, zimný) a povolené kategórie omeškaní riešení
    """
    class Meta:
        verbose_name = 'semester'
        verbose_name_plural = 'semestre'
        ordering = ['-year', '-season_code', ]

    SEASON_CHOICES = [
        (0, 'Zimný'),
        (1, 'Letný'),
    ]

    season_code = models.PositiveSmallIntegerField(choices=SEASON_CHOICES)
    late_tags = models.ManyToManyField(
        LateTag, verbose_name='Stavy omeškania', blank=True)
    frozen_results = models.TextField(
        null=True,
        blank=True,
        default=None)

    def get_first_series(self):
        return self.series_set.get(order=1)

    def get_second_series(self):
        return self.series_set.get(order=2)

    def freeze_results(self, results):
        self.frozen_results = results

    @cached_property
    def season(self):
        return self.get_season_code_display()

    @cached_property
    def season_short(self):
        return self.get_season_code_display()[:3].lower()

    @cached_property
    def is_active(self):
        return self.series_set.filter(complete=False).exists()

    @property
    def is_at_least_one_series_open(self):
        return self.series_set.filter(can_submit=True).exists()

    def __str__(self):
        return f'{self.competition.name}, {self.year}. ročník - {self.season} semester'


class Series(models.Model):
    """
    Popisuje jednu sériu semestra
    """
    class Meta:
        verbose_name = 'séria'
        verbose_name_plural = 'série'
        ordering = ['semester', '-order', ]

    semester = models.ForeignKey(
        Semester, verbose_name='semester', on_delete=models.CASCADE)
    order = models.PositiveSmallIntegerField(verbose_name='poradie série')

    deadline = models.DateTimeField(verbose_name='termín série')
    complete = models.BooleanField(
        verbose_name='séria uzavretá', help_text='Séria má finálne poradie a už sa nebude meniť')

    # Implementuje bonfikáciu
    sum_method = models.CharField(
        verbose_name='Súčtová metóda', max_length=50, blank=True,
        choices=utils.SERIES_SUM_METHODS)
    frozen_results = models.TextField(
        null=True,
        blank=True,
        default=None)

    def __str__(self):
        return f'{self.semester} - {self.order}. séria'

    @property
    def is_past_deadline(self):
        return now() > self.deadline

    @property
    def time_to_deadline(self):
        remaining_time = self.deadline - now()

        if remaining_time.total_seconds() < 0:
            return datetime.timedelta(0)

        return remaining_time

    @property
    def can_submit(self):
        """
        Vráti True, ak užívateľ ešte môže odovzdať úlohu.
        Pozerá sa na maximálne možné omeškanie v LateFlagoch.
        """
        max_late_tag_value = self.semester.late_tags.aggregate(
            models.Max('upper_bound'))['upper_bound__max']
        if not max_late_tag_value:
            max_late_tag_value = datetime.timedelta(0)
        return now() < self.deadline + max_late_tag_value

    def get_actual_late_flag(self):
        """
        Vráti late flag, ktorý má byť v tomto okamihu priradený riešeniu,
        teda jeho aktuálne omeškanie
        """
        if not self.is_past_deadline:
            return None
        if not self.can_submit:
            return None
        return self.semester.late_tags.filter(upper_bound__gte=now()-self.deadline)\
            .order_by('upper_bound')\
            .first()

    def freeze_results(self, results):
        self.frozen_results = results

    @property
    def num_problems(self):
        return self.problems.count()

    def can_user_modify(self, user):
        return self.semester.can_user_modify(user)


class Problem(models.Model):
    """
    Popisuje jednu úlohu v sérií
    """
    class Meta:
        verbose_name = 'úloha'
        verbose_name_plural = 'úlohy'

        ordering = ['series', 'order', ]

    text = models.TextField(verbose_name='znenie úlohy')
    order = models.PositiveSmallIntegerField(verbose_name='poradie v sérii')
    series = models.ForeignKey(
        Series, verbose_name='úloha zaradená do série',
        related_name='problems',
        on_delete=models.CASCADE,)

    def __str__(self):
        return f'{self.series.semester.competition.name}-{self.series.semester.year}' \
            f'-{self.series.semester.season[0]}S-S{self.series.order} - {self.order}. úloha'

    def get_stats(self):
        stats = {}
        stats['histogram'] = []
        total_solutions = 0
        total_points = 0
        for score in range(10):
            count = self.solution_set.filter(score=score).count()
            total_solutions += count
            total_points += count*score
            stats['histogram'].append({'score': score, 'count': count})
        stats['num_solutions'] = total_solutions

        stats['mean'] = total_points / \
            total_solutions if total_solutions else '?'
        return stats

    def can_user_modify(self, user):
        return self.series.can_user_modify(user)

    def get_comments(self, user):
        def filter_by_permissions(obj):
            if user.is_staff:
                return True
            if obj.published:
                return True
            if obj.posted_by == user:
                return True
            return False

        return filter(filter_by_permissions, Comment.objects.filter(problem=self))

    def add_comment(self, text, user_id, published=0):
        Comment.create_comment(
            _text=text,
            _problem_id=self.pk,
            _posted_by=user_id,
            _published=published
        )


class Comment(models.Model):
    class Meta:
        verbose_name = 'komentár'
        verbose_name_plural = 'komentáre'

        ordering = ['posted_at']

    problem = models.ForeignKey(
        Problem, verbose_name='komentár k úlohe',
        on_delete=models.CASCADE,)
    text = models.TextField()
    posted_at = models.DateTimeField(
        verbose_name='dátum pridania', auto_now_add=True)
    posted_by = models.ForeignKey(
        User, verbose_name='autor komentára',
        on_delete=models.CASCADE)
    published = models.BooleanField(
        verbose_name='komentár publikovaný')

    def publish(self):
        self.published = True

    def hide(self):
        self.published = False

    def change_text(self, new_text):
        self.text = new_text

    @staticmethod
    def create_comment(_text, _problem_id, _posted_by, _published):
        comment = Comment.objects.create(
            problem=Problem.objects.get(pk=_problem_id),
            text=_text,
            published=_published,
            posted_by=_posted_by
        )
        comment.save()

    def can_user_modify(self, user):
        return self.problem.can_user_modify(user)


class Grade(models.Model):
    """
    Popisuje ročník súťažiaceho. Napríklad Z9, S1 ...
    """
    class Meta:
        verbose_name = 'ročník účastníka'
        verbose_name_plural = 'ročníky účastníka'
        ordering = ['years_until_graduation', ]

    name = models.CharField(verbose_name='názov ročníku', max_length=32)
    tag = models.CharField(verbose_name='skratka', max_length=2, unique=True)
    years_until_graduation = models.SmallIntegerField(
        verbose_name='počet rokov do maturity')
    is_active = models.BooleanField(
        verbose_name='aktuálne používaný ročník')

    objects = UnspecifiedValueManager(unspecified_value_pk=13)

    def get_year_of_graduation_by_date(self, date=None):
        return utils.get_school_year_end_by_date(date) + self.years_until_graduation

    @staticmethod
    def get_grade_by_year_of_graduation(year_of_graduation, date=None):
        years_until_graduation = year_of_graduation - \
            utils.get_school_year_end_by_date(date)

        try:
            grade = Grade.objects.get(
                years_until_graduation=years_until_graduation)
        except Grade.DoesNotExist:
            grade = Grade.objects.get_unspecified_value()

        return grade

    def __str__(self):
        return self.name


class EventRegistration(models.Model):
    """
    Registruje účastníka na instanciu súťaže(napríklad Matboj 2020,
    letný semester 40. ročník STROMu).
    V registrácií sú uložené údaje účastníka aktuálne v čase konania súťaže.
    """
    class Meta:
        verbose_name = 'registrácia užívateľa na akciu'
        verbose_name_plural = 'registrácie užívateľov na akcie'
        constraints = [
            UniqueConstraint(fields=['profile', 'event'],
                             name='single_registration_in_event'),
        ]

    profile = models.ForeignKey(
        Profile, verbose_name='profil', on_delete=models.CASCADE)
    school = models.ForeignKey(
        School, verbose_name='škola', on_delete=models.SET_NULL, null=True)
    grade = models.ForeignKey(
        Grade, verbose_name='ročník', on_delete=models.CASCADE)
    event = models.ForeignKey(
        Event, verbose_name='semester', on_delete=models.CASCADE)

    @staticmethod
    def get_registration_by_profile_and_event(profile, event):
        try:
            registration = EventRegistration.objects.get(
                profile=profile, event=event)
        except EventRegistration.DoesNotExist:
            registration = None

        return registration

    def __str__(self):
        return f'{ self.profile.user.get_full_name() } @ { self.event }'

    def can_user_modify(self, user):
        return self.event.can_user_modify(user)


class Vote(models.IntegerChoices):
    '''
    Enum hlasov
    '''
    NEGATIVE = -1, 'negatívny'
    NONE = 0, 'žiaden'
    POSITIVE = 1, 'pozitívny'


class Solution(models.Model):
    """
    Popisuje riešenie úlohy od užívateľa. Obsahuje nahraté aj opravné riešenie, body
    """
    class Meta:
        verbose_name = 'riešenie'
        verbose_name_plural = 'riešenia'

    problem = models.ForeignKey(Problem, on_delete=models.CASCADE)
    semester_registration = models.ForeignKey(
        EventRegistration, on_delete=models.CASCADE)

    solution = models.FileField(
        verbose_name='účastnícke riešenie', blank=True, upload_to='solutions/')
    corrected_solution = models.FileField(
        verbose_name='opravené riešenie', blank=True, upload_to='solutions/corrected/')

    score = models.PositiveSmallIntegerField(
        verbose_name='body', null=True, blank=True)

    vote = models.IntegerField(choices=Vote.choices,
                               default=Vote.NONE)

    uploaded_at = models.DateTimeField(
        verbose_name='dátum pridania', auto_now_add=True)

    # V prípade, že riešenie prišlo po termíne nastaví sa na príslušný tag
    late_tag = models.ForeignKey(
        LateTag, verbose_name='Stavy omeškania',
        on_delete=models.SET_NULL, null=True)

    is_online = models.BooleanField(
        verbose_name='internetové riešenie', default=False)

    def __str__(self):
        return f'Riešiteľ: { self.semester_registration } - úloha { self.problem }'

    def get_solution_file_name(self):
        return f'{self.semester_registration.profile.user.get_full_name_camel_case()}'\
               f'-{self.problem.id}-{self.semester_registration.id}.pdf'

    def get_corrected_solution_file_name(self):
        return f'corrected/{self.semester_registration.profile.user.get_full_name_camel_case()}'\
               f'-{self.problem.id}-{self.semester_registration.id}_corrected.pdf'

    def can_user_modify(self, user):
        return self.problem.can_user_modify(user)

    def set_vote(self, vote):
        self.vote = vote
        self.save()


class SemesterPublication(models.Model):
    """
    Časopis
    """
    class Meta:
        verbose_name = 'časopis'
        verbose_name_plural = 'časopisy'

    name = models.CharField(max_length=30, blank=True)
    semester = models.ForeignKey(
        Semester, null=True, on_delete=models.SET_NULL)
    order = models.PositiveSmallIntegerField()
    file = RestrictedFileField(
        upload_to='publications/semester_publication/%Y',
        content_types=['application/pdf'],
        verbose_name='súbor')
    thumbnail = models.ImageField(
        upload_to='publications/thumbnails/%Y',
        blank=True,
        verbose_name='náhľad')

    def validate_unique(self, exclude=None):
        if SemesterPublication.objects.filter(semester=self.semester) \
                .filter(~Q(pk=self.pk), order=self.order) \
                .exists():
            raise ValidationError({
                'order': 'Časopis s týmto číslom už v danom semestri existuje',
            })

    def generate_thumbnail(self, forced=False):
        if mime_type(self.file) != 'application/pdf':
            return

        if self.thumbnail and not forced:
            return

        with self.file.open(mode='rb') as file:
            pil_image = pdf2image.convert_from_bytes(
                file.read(), first_page=1, last_page=1)[0]

        png_image_bytes = BytesIO()
        pil_image.save(png_image_bytes, format='png')
        png_image_bytes.seek(0)

        thumbnail_filename = os.path.splitext(
            os.path.basename(self.file.name))[0] + '.png'

        if self.thumbnail:
            self.thumbnail.delete()

        self.thumbnail.save(
            thumbnail_filename, ContentFile(png_image_bytes.read()))

    def __str__(self):
        return self.name

    def generate_name(self, forced=False):
        if self.name and not forced:
            return

        self.name = f'{self.semester.competition}-{self.semester.year}-{self.order}'
        self.save()

    def can_user_modify(self, user):
        return self.semester.can_user_modify(user)


class UnspecifiedPublication(models.Model):
    """
    Reprezentuje výsledky, brožúrku alebo akýkoľvek materiál
    zverejnený k nejakému Eventu okrem časopisov. Časopisy majú
    vlastnú triedu SemesterPublication.
    """
    class Meta:
        verbose_name = 'iná publikácia'
        verbose_name_plural = 'iné publikácie'

    name = models.CharField(max_length=30, blank=True)
    event = models.ForeignKey(Event, null=True, on_delete=models.SET_NULL)

    file = RestrictedFileField(
        upload_to='publications/%Y',
        content_types=['application/pdf', 'application/zip'],
        verbose_name='súbor')

    def generate_name(self, forced=False):
        if self.name and not forced:
            return

        self.name = f'{self.event.competition}-{self.event.year}'
        self.save()

    def __str__(self):
        return self.name

    def can_user_modify(self, user):
        return self.event.can_user_modify(user)


@ receiver(post_save, sender=SemesterPublication)
def make_thumbnail_on_creation(sender, instance, created, **kwargs):
    # pylint: disable=unused-argument
    if created:
        instance.generate_thumbnail()


@ receiver(post_save, sender=SemesterPublication)
@ receiver(post_save, sender=UnspecifiedPublication)
def make_name_on_creation(sender, instance, created, **kwargs):
    # pylint: disable=unused-argument
    if created:
        instance.generate_name()


class RegistrationLink(models.Model):
    class Meta:
        verbose_name = 'link na registráciu'
        verbose_name_plural = 'linky na registráciu'

    event = models.ForeignKey(
        Event, related_name='registration_links', on_delete=models.CASCADE)
    url = models.URLField(verbose_name='url registrácie')
    start = models.DateTimeField(verbose_name='Začiatok registrácie')
    end = models.DateTimeField(verbose_name='Koniec registrácie')
    additional_info = models.TextField(verbose_name='Doplňujúce informácie')

    def can_user_modify(self, user):
        return self.event.can_user_modify(user)
