from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.utils.html import format_html

from competition.models import (Event, Problem, Semester, SemesterPublication,
                                Series, Solution, UnspecifiedPublication)


@admin.register(Series)
class SeriesAdmin(admin.ModelAdmin):
    list_display = (
        '__str__',
        'competition',
        'semester',
        'order',
        'deadline',
        'active',
        'complete',
    )

    list_filter = (
        'semester__competition',
        'complete',
    )

    @staticmethod
    def active(obj):
        return not obj.is_past_deadline
    active.boolean = True

    @staticmethod
    def competition(obj):
        return obj.semester.competition
    active.admin_order_field = 'semester__competition'


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = (
        '__str__',
        'competition',
        'year',
        'school_year',
        'start',
        'end',
    )

    list_filter = (
        'competition',
        'school_year'
    )


@admin.register(Semester)
class SemesterAdmin(admin.ModelAdmin):
    list_display = (
        '__str__',
        'competition',
        'year',
        'school_year',
        'season_code',
        'start',
        'end',
    )

    list_filter = (
        'competition',
        'school_year',
        'season_code',
    )


@admin.register(Problem)
class ProblemAdmin(admin.ModelAdmin):
    list_display = (
        '__str__',
        'order',
        'series',
        'get_text',
    )

    @staticmethod
    def get_text(obj):
        return obj.text[:70] + '...'


@admin.register(Solution)
class SolutionAdmin(admin.ModelAdmin):
    list_display = (
        'solution_name',
        'problem',
        'semester_registration',
        'uploaded_at',
        'late_tag',
        'is_online',
        'score',
    )

    list_editable = ('score', )

    list_filter = (
        'semester_registration__event__competition',
        'late_tag',
        'is_online',
        'score',
    )

    date_hierarchy = 'uploaded_at'

    @staticmethod
    def solution_name(obj):
        return obj.semester_registration.profile.user.get_full_name()\
            + ' | ' + str(obj.problem.order)

# TODO: duplikátny kód v SemesterPublicationAdmin a UnspecifiedPublicationAdmin


@admin.register(SemesterPublication)
class SemesterPublicationAdmin(admin.ModelAdmin):
    change_form_template = 'competition/admin/semesterpublication_change.html'

    list_display = (
        'name',
        'thumbnail_list_preview',
        'competition',
        'semester',
        'order',
        'school_year',
    )

    ordering = (
        'semester',
        '-order',
    )

    list_filter = (
        'semester__school_year',
        # 'semester__competition',
    )

    def get_changeform_initial_data(self, request):
        # TODO: doplniť výber súťaže
        return {
            'semester': Semester.objects.first(),
            'order': Semester.objects.first().semesterpublication_set.count() + 1,
        }

    @staticmethod
    def school_year(obj):
        return obj.semester.school_year
    school_year.admin_order_field = 'semester__school_year'

    @staticmethod
    def competition(obj):
        return obj.semester.competition
    competition.admin_order_field = 'semester__competition'

    @staticmethod
    def thumbnail_list_preview(obj):
        return format_html(
            '<a href="{}"><img src="{}" height="100" /></a>',
            obj.file.url,
            obj.thumbnail.url
        )

    def response_change(self, request, obj):
        if 'generate-name' in request.POST:
            obj.generate_name(forced=True)

            if obj.name:
                self.message_user(request, 'Meno bolo vygenerované')
            else:
                self.message_user(
                    request, 'Meno sa nepodarilo vygenerovať', level=messages.ERROR)

            return HttpResponseRedirect('.')

        if 'generate-thumbnail' in request.POST:
            obj.generate_thumbnail(forced=True)

            if obj.thumbnail:
                self.message_user(request, 'Náhľad bol vygenerovaný')
            else:
                self.message_user(
                    request, 'Náhľad sa nepodarilo vygenerovať', level=messages.ERROR)

            return HttpResponseRedirect('.')

        return super().response_change(request, obj)


@admin.register(UnspecifiedPublication)
class UnspecifiedPublicationAdmin(admin.ModelAdmin):
    change_form_template = 'competition/admin/unspecifiedpublication_change.html'

    def response_change(self, request, obj):
        if 'generate-name' in request.POST:
            obj.generate_name(forced=True)

            if obj.name:
                self.message_user(request, 'Meno bolo vygenerované')
            else:
                self.message_user(
                    request, 'Meno sa nepodarilo vygenerovať', level=messages.ERROR)

            return HttpResponseRedirect('.')

        return super().response_change(request, obj)
