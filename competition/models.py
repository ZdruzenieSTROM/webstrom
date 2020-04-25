import datetime
import pdf2image
from django.contrib.sites.models import Site
from django.db import models
from django.shortcuts import get_object_or_404
from django.utils.timezone import now
from django.utils.functional import cached_property

class Competition(models.Model):
    class Meta:
        verbose_name = 'seminár'
        verbose_name_plural = 'semináre'

    name = models.CharField(
        max_length=50,
        verbose_name='názov'
    )

    start_year = models.PositiveSmallIntegerField(
        verbose_name='rok prvého ročníka súťaže'
    )
    site = models.ForeignKey(
        Site, blank=True, null=True, on_delete=models.SET_NULL)

    def __str__(self):
        return self.name

    @classmethod
    def get_by_site(cls, site):
        return get_object_or_404(cls, site=site)

    @classmethod
    def get_by_current_site(cls):
        return cls.get_by_site(Site.objects.get_current())


class LateTag(models.Model):
    class Meta:
        verbose_name = 'omeškanie'
        verbose_name_plural = 'omeškanie'

    name = models.CharField(
        max_length=50, verbose_name='označenie štítku pre riešiteľa')
    upper_bound = models.DurationField(
        verbose_name='maximálna dĺžka omeškania')
    comment = models.TextField(verbose_name='komentár pre opravovateľa')

    def __str__(self):
        return self.name


class Semester(models.Model):
    class Meta:
        verbose_name = 'semester'
        verbose_name_plural = 'semestre'

    competition = models.ForeignKey(
        Competition,
        on_delete=models.CASCADE
    )

    year = models.PositiveSmallIntegerField(
        verbose_name='ročník'
    )

    start = models.DateTimeField(
        verbose_name='dátum začiatku semestra'
    )

    end = models.DateTimeField(
        verbose_name='dátum konca semestra'
    )
    late_tags = models.ManyToManyField(
        LateTag,
        verbose_name=''
    )
    season = models.CharField(
        max_length=10
    )

    @cached_property
    def is_active(self):
        return self.series_set.filter(complete=False).count() > 0

    def __str__(self):
        return f'{self.competition.name}, {self.year}. ročník - {self.season} semester'


class Series(models.Model):
    class Meta:
        verbose_name = 'séria'
        verbose_name_plural = 'série'

    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    order = models.PositiveSmallIntegerField(verbose_name='poradie série')
    deadline = models.DateTimeField(verbose_name='termín série')
    complete = models.BooleanField(verbose_name='séria uzavretá')
    # sum_method =  # NO FOKEN IDEA

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
        else:
            return remaining_time


class Problem(models.Model):
    class Meta:
        verbose_name = 'úloha'
        verbose_name_plural = 'úlohy'

    text = models.TextField(verbose_name='znenie úlohy')
    series = models.ForeignKey(
        Series,
        on_delete=models.CASCADE,
        verbose_name='úloha zaradená do série'
    )
    order = models.PositiveSmallIntegerField(verbose_name='poradie v sérii')

    def __str__(self):
        return f'{self.series.semester.competition.name}-{self.series.semester.year}-{self.series.semester.season[0]}S-S{self.series.order} - {self.order}. úloha'


class Grade(models.Model):
    class Meta:
        verbose_name = 'ročník'
        verbose_name_plural = 'ročníky'

    name = models.CharField(
        max_length=32,
        verbose_name='názov ročníku'
    )
    tag = models.CharField(
        max_length=2,
        unique=True,
        verbose_name='skratka'
    )
    years_in_school = models.PositiveSmallIntegerField(
        verbose_name='počet rokov v škole'
    )

    def __str__(self):
        return self.name


class UserSemesterRegistration(models.Model):
    class Meta:
        verbose_name = 'séria'
        verbose_name_plural = 'série'

    user = models.ForeignKey('user.User', on_delete=models.CASCADE)
    school = models.ForeignKey(
        'user.School', on_delete=models.SET_NULL, null=True)
    class_level = models.ForeignKey(Grade, on_delete=models.CASCADE)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)


class Solution(models.Model):
    class Meta:
        verbose_name = 'riešenie'
        verbose_name_plural = 'riešenia'

    problem = models.ForeignKey(Problem, on_delete=models.CASCADE)
    user_semester_registration = models.ForeignKey(
        UserSemesterRegistration,
        on_delete=models.CASCADE
    )
    # solution_path =  # File field - isteho typu

    # corrected_solution_path =  # File field - isteho typu

    score = models.PositiveSmallIntegerField(verbose_name='body')

    uploaded_at = models.DateTimeField(
        auto_now=True, verbose_name='nahrané dňa')

    # V prípade, že riešenie prišlo po termíne nastaví sa na príslušný tag
    late_tag = models.ForeignKey(
        LateTag,
        on_delete=models.SET_NULL,
        verbose_name='',
        null=True,
        blank=True)

    is_online = models.BooleanField(
        verbose_name='internetové riešenie'
    )


class Booklet(models.Model):
    class Meta:
        verbose_name = 'časopis'
        verbose_name_plural = 'časopisy'
    
    semester = models.ForeignKey(Semester,null=True,on_delete=models.SET_NULL)
    pdf_file = models.FileField(

    )
    order = models.PositiveSmallIntegerField()
    @property
    def thumbnail_path(self):
        pass
    def __str__(self):
        f'{self.semester.competition}-{self.semester.year}-{self.order}'
"""
@receiver(post_save, sender=Leaflet)
def generate_leaflet_thumbnail(sender, instance, created, **kwargs):
    source_path = instance.get_leaflet_path()
    dest_path = instance.get_thumbnail_path()
    pdf2image.

"""