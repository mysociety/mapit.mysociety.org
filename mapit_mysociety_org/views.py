from django.shortcuts import redirect
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.http import Http404
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView
from django.views.decorators.debug import sensitive_post_parameters
import stripe

import account.forms
import account.views
from subscriptions.views import SubscriptionUpdateMixin

from . import forms


stripe.api_key = settings.STRIPE_SECRET_KEY
stripe.api_version = settings.STRIPE_API_VERSION


class LoginView(account.views.LoginView):
    """ Override account.views.LoginView to use the email-only version """

    form_class = account.forms.LoginEmailForm


class LogoutView(TemplateView):
    template_name = "account/logout.html"

    def get(self, *args, **kwargs):
        if self.request.user.is_authenticated:
            logout(self.request)
        return super(LogoutView, self).get(*args, **kwargs)


class SignupView(SubscriptionUpdateMixin, account.views.SignupView):
    """ Override account.views.SignupView to use our email-only SignupForm """

    form_class = forms.SignupForm
    identifier_field = 'email'

    def __init__(self, *args, **kwargs):
        self.messages.pop('email_confirmation_sent', None)
        super(SignupView, self).__init__(*args, **kwargs)

    @method_decorator(sensitive_post_parameters('password', 'password_confirm'))
    def dispatch(self, *args, **kwargs):
        return super(SignupView, self).dispatch(*args, **kwargs)

    def get_initial(self):
        initial = super(SignupView, self).get_initial()
        initial['price'] = self.request.GET.get('price')
        return initial

    def form_valid(self, form):
        return self.update_subscription(form)

    def generate_username(self, form):
        # Generate a random username (we used to use the email address
        # directly, but Django has a 30 character limit for the username).
        truncated_email = form.cleaned_data['email'][:25]
        return self.generate_unique_username(truncated_email, 0)

    def generate_unique_username(self, email, index):
        username = email
        if index > 0:
            username = "{0}_{1}".format(username, str(index))
        try:
            User.objects.get(username=username)
            # If we get here, the username already exists, so we have to try
            # a different one.
            index += 1
            return self.generate_unique_username(email, index)
        except User.DoesNotExist:
            # Yay, it's unique
            return username


class ConfirmEmailView(account.views.ConfirmEmailView):
    """
    Override account.views.ConfirmEmailView so that it automatically
    confirms the user's account on GET, logs them in immediately and redirects
    them on.
    """

    # Don't allow the inherited post method, just to be clear
    http_method_names = ['get']

    def get(self, *args, **kwargs):
        """
        Does mostly what account.views.ConfirmEmailView.post does, with some
        simplification because we always want to redirect to a specific URL,
        and the addition of logging the user in directly.
        """
        self.object = confirmation = self.get_object()
        confirmation.confirm()
        self.after_confirmation(confirmation)

        # Update any associated stripe email
        user = confirmation.email_address.user
        if hasattr(user, 'subscription'):
            try:
                obj = stripe.Subscription.retrieve(user.subscription.stripe_id, expand=['customer'])
                if obj.customer.email != confirmation.email_address.email:
                    stripe.Customer.modify(obj.customer.id, email=confirmation.email_address.email)
            except stripe.error.InvalidRequestError:
                pass

        self.login_user(user=confirmation.email_address.user)
        if self.messages.get("email_confirmed"):
            messages.add_message(
                self.request,
                self.messages["email_confirmed"]["level"],
                self.messages["email_confirmed"]["text"].format(**{
                    "email": confirmation.email_address.email
                })
            )
        return redirect('api_keys_keys')

    def login_user(self, user):
        """
        Automatically log a user in without knowing their password
        (otherwise you could just use authenticate() followed by login()).
        """
        if user is not None and not user.is_superuser:
            # This what authenticate() does that login() needs
            user.backend = 'account.auth_backends.EmailAuthenticationBackend'
            login(self.request, user)

    def get_queryset(self):
        """
        Alter the queryset returned by
        account.views.ConfirmEmailView.get_queryset so that it only looks in
        unconfirmed EmailConfirmations, to avoid double-confirming.
        """
        qs = super(ConfirmEmailView, self).get_queryset()
        return qs.filter(email_address__verified=False)

    def get_object(self, queryset=None):
        """
        Add an extra check on the object returned by
        account.views.ConfirmEmailView.get_object in order to check that the
        confirmation key hasn't expired.
        """
        obj = super(ConfirmEmailView, self).get_object(queryset)
        if obj.key_expired():
            raise Http404()
        return obj
