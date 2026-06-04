import account.forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from subscriptions.forms import SubscriptionMixin


class SignupForm(SubscriptionMixin, account.forms.SignupForm):
    """ Override account.forms.SignupForm to remove username field """

    def __init__(self, *args, **kwargs):
        super(SignupForm, self).__init__(*args, **kwargs)
        del self.fields["username"]

    def clean(self):
        super().clean()
        dummy_user = get_user_model()
        dummy_user.email = self.cleaned_data.get("email")
        validate_password(self.cleaned_data["password"], dummy_user)
