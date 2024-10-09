import re

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.files.storage import FileSystemStorage
from django.shortcuts import redirect
from django.views.generic import DetailView
from django.utils.encoding import force_str
from formtools.wizard.views import SessionWizardView
import stripe

from .models import BulkLookup, cache
from .forms import CSVForm, PostcodeFieldForm, OutputOptionsForm, PersonalDetailsForm

from mapit.shortcuts import output_json
from mapit_mysociety_org.mixins import NeverCacheMixin
from subscriptions.views import StripeObjectMixin


class WizardError(Exception):
    """If something odd happens (e.g. missing data though we're part way
    through the process), raise this and the wizard will reset."""


class WizardView(NeverCacheMixin, StripeObjectMixin, SessionWizardView):
    object = None

    form_list = [
        ('csv', CSVForm),
        ('postcode_field', PostcodeFieldForm),
        ('output_options', OutputOptionsForm),
        ('personal_details', PersonalDetailsForm)]
    TEMPLATES = {
        'csv': 'bulk_lookup/index.html',
        'postcode_field': 'bulk_lookup/postcode_field.html',
        'output_options': 'bulk_lookup/output_options.html',
        'personal_details': 'bulk_lookup/personal_details.html',
    }
    file_storage = FileSystemStorage()

    def post(self, *args, **kwargs):
        # If a CSV file has been submitted, reset the postcode field form
        # to prevent potential field errors.
        if self.request.POST.get('wizard_view-current_step') == 'csv':
            self.storage.set_step_data('postcode_field', None)
        try:
            return super(WizardView, self).post(*args, **kwargs)
        except WizardError:
            self.storage.current_step = self.steps.first
            return self.render(self.get_form())

    def get_template_names(self):
        return [self.TEMPLATES[self.steps.current]]

    @cache
    def get_cleaned_csv_data(self):
        dat = self.get_cleaned_data_for_step('csv')
        if not dat:
            raise WizardError
        return BulkLookup(**dat)

    def get_form_kwargs(self, step):
        kwargs = super(WizardView, self).get_form_kwargs(step)
        if step == 'postcode_field':
            kwargs['bulk_lookup'] = self.get_cleaned_csv_data
        elif step == 'personal_details':
            kwargs['amount'] = settings.BULK_LOOKUP_PRICE
            kwargs['free'] = False
            if self.request.user.is_authenticated:
                if not self.object:
                    self.object = self.get_object()
                if self.object and self.object.price.id == settings.PRICING[-1]['id']:
                    kwargs['free'] = True
        return kwargs

    def get_form_initial(self, step):
        initial = super(WizardView, self).get_form_initial(step)
        if step == 'postcode_field':
            bulk_lookup = self.get_cleaned_csv_data
            for choice in bulk_lookup.field_names:
                if re.match(r'post(\s)*code', force_str(choice), flags=re.IGNORECASE):
                    initial['postcode_field'] = choice
                    break
        elif step == 'personal_details':
            if self.request.user.is_authenticated:
                initial['email'] = self.request.user.email
        return initial

    def get_context_data(self, form, **kwargs):
        context = super(WizardView, self).get_context_data(form=form, **kwargs)
        if self.steps.current == 'csv':
            context['amount'] = settings.BULK_LOOKUP_PRICE
            return context

        bulk_lookup = self.get_cleaned_csv_data

        if self.steps.current == 'postcode_field':
            context['bulk_lookup'] = {
                'field_names': bulk_lookup.field_names,
                'example_rows': bulk_lookup.example_rows(),
            }
            return context

        # output_options or personal_details
        pc_data = self.get_cleaned_data_for_step('postcode_field')
        if not pc_data:
            raise WizardError
        context['num_good_rows'] = pc_data['num_rows'] - pc_data['bad_rows']
        if self.steps.current == 'personal_details':
            context['price'] = settings.BULK_LOOKUP_PRICE
            if self.object and self.object.price.id == settings.PRICING[-1]['id']:
                context['price'] = 0
        return context

    def done(self, form_list, form_dict, **kwargs):
        data = {}
        for form_obj in form_list:
            data.update(form_obj.cleaned_data)

        output_options = data.pop('output_options')
        data.pop('num_rows')
        bulk_lookup = BulkLookup.objects.create(**data)
        bulk_lookup.output_options.add(*output_options)
        return redirect('finished', pk=bulk_lookup.id, token=bulk_lookup.charge_id)


# The flow is from https://docs.stripe.com/payments/accept-a-payment-synchronously
def AjaxConfirmView(request):
    intent = None
    try:
        if 'payment_method_id' in request.POST:
            intent = stripe.PaymentIntent.create(
                payment_method=request.POST['payment_method_id'],
                amount=settings.BULK_LOOKUP_PRICE * 100,
                currency='gbp',
                description='[MapIt] %s' % (request.POST['personal_details-description'] or 'Bulk lookup',),
                receipt_email=request.POST['personal_details-email'],
                confirmation_method='manual',
                confirm=True,
                payment_method_types=['card'],
            )
        elif 'payment_intent_id' in request.POST:
            intent = stripe.PaymentIntent.confirm(request.POST['payment_intent_id'])
    except stripe.error.CardError as e:
        return output_json({'error': e.user_message}, 200)

    data, code = generate_payment_response(intent)
    return output_json(data, code)


def generate_payment_response(intent):
    if intent.status in ('requires_action', 'requires_source_action') and intent.next_action.type == 'use_stripe_sdk':
        return {
            'requires_action': True,
            'payment_intent_client_secret': intent.client_secret,
        }, 200
    elif intent.status == 'succeeded':
        return {'success': True, 'charge_id': intent.id}, 200
    else:
        return {'error': 'Invalid PaymentIntent status'}, 500


class FinishedView(NeverCacheMixin, DetailView):
    model = BulkLookup
    template_name = 'bulk_lookup/finished.html'

    def get_object(self, *args, **kwargs):
        obj = super(FinishedView, self).get_object(*args, **kwargs)
        if self.kwargs['token'] != obj.charge_id:
            raise PermissionDenied
        return obj
