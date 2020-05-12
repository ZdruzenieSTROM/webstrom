from django import forms
from django.contrib.auth.password_validation import validate_password

from competition.models import Grade
from user.models import County, District, Profile, User


class UserCreationForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('email',)

    new_password1 = forms.CharField(label='Heslo', widget=forms.PasswordInput)
    new_password2 = forms.CharField(
        label='Potvrdenie hesla', widget=forms.PasswordInput)

    def clean_new_password1(self):
        new_password1 = self.cleaned_data['new_password1']
        validate_password(new_password1)
        return new_password1

    def clean_new_password2(self):
        new_password1 = self.cleaned_data.get('new_password1')
        new_password2 = self.cleaned_data.get('new_password2')
        if new_password1 and new_password2 and new_password1 != new_password2:
            raise forms.ValidationError('Heslá sa nezhodujú')
        return new_password2

    def save(self, commit=True):
        user = super(UserCreationForm, self).save(commit=False)
        user.set_password(self.cleaned_data['new_password1'])

        if commit:
            user.save()

        return user


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['first_name', 'last_name', 'nickname',
                  'school_not', 'county', 'district', 'school',
                  'school_name', 'school_not_found', 'school_info',
                  'grade', 'phone', 'parent_phone', 'gdpr', ]

    grade = forms.ModelChoiceField(
        queryset=Grade.objects.filter(is_active=True),
        label='Ročník',
        help_text='V prípade, že je leto, zadaj ročník, '
        'ktorý končíš (školský rok začína septembrom).')

    school_not = forms.BooleanField(
        required=False,
        label='Už nie som študent základnej ani strednej školy.')

    school_name = forms.CharField(
        required=False,
        label='Škola*')

    school_not_found = forms.BooleanField(
        required=False,
        label='Moja škola sa v zozname nenachádza.')

    school_info = forms.CharField(
        required=False,
        widget=forms.Textarea,
        label='povedz nám, kam chodíš na školu, aby sme ti ju mohli dodatočne pridať')

    county = forms.ModelChoiceField(
        required=False,
        queryset=County.objects,
        label='Kraj školy')

    district = forms.ModelChoiceField(
        required=False,
        queryset=District.objects,
        label='Okres školy')

    def __init__(self, *args, **kwargs):
        super(ProfileForm, self).__init__(*args, **kwargs)

        self.fields['county'].queryset = County.objects.all_except_unspecified()
        self.fields['school'].widget = forms.HiddenInput()

    def clean_gdpr(self):
        gdpr = self.cleaned_data['gdpr']

        if not gdpr:
            raise forms.ValidationError(
                'Súhlas so spracovaním osobných údajov je nutnou podmienkou registrácie')

        return gdpr

    def save(self, commit=True):
        profile = super(ProfileForm, self).save(commit=False)

        profile.year_of_graduation = \
            self.cleaned_data['grade'].get_year_of_graduation_by_date()

        if commit:
            profile.save()

        return profile


class ProfileCreationForm(ProfileForm):
    class Meta:
        model = Profile
        fields = ['first_name', 'last_name', 'nickname',
                  'school_not', 'county', 'district', 'school',
                  'school_name', 'school_not_found', 'school_info',
                  'grade', 'phone', 'parent_phone', 'gdpr', ]


class ProfileUpdateForm(ProfileForm):
    class Meta:
        model = Profile
        fields = ['first_name', 'last_name', 'nickname',
                  'school_not', 'county', 'district', 'school',
                  'school_name', 'school_not_found', 'school_info',
                  'grade', 'phone', 'parent_phone', ]
