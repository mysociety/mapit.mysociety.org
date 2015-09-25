import account.forms


class SignupForm(account.forms.SignupForm):
    """ Override account.forms.SignupForm to remove username field """

    def __init__(self, *args, **kwargs):
        super(SignupForm, self).__init__(*args, **kwargs)
        del self.fields["username"]
