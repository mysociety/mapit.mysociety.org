import account.forms

from subscriptions.forms import SubscriptionMixin


class SignupForm(SubscriptionMixin, account.forms.SignupForm):
    """ Override account.forms.SignupForm to remove username field """

    def __init__(self, *args, **kwargs):
        super(SignupForm, self).__init__(*args, **kwargs)
        del self.fields["username"]
