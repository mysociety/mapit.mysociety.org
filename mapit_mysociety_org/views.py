import account.forms
import account.views

from . import forms


class LoginView(account.views.LoginView):
    """ Override account.views.LoginView to use the email-only version """

    form_class = account.forms.LoginEmailForm


class SignupView(account.views.SignupView):
    """ Override account.views.SignupView to use our email-only SignupForm """

    form_class = forms.SignupForm

    def generate_username(self, form):
        # Return the email address as the username (Django's user model needs
        # something to store there).
        return form.cleaned_data['email']
