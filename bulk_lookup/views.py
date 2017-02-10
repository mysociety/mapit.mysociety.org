import re

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.files.storage import FileSystemStorage
from django.shortcuts import redirect
from django.views.generic import DetailView
from formtools.wizard.views import SessionWizardView

from .models import BulkLookup
from .forms import CSVForm, PostcodeFieldForm, OutputOptionsForm, PersonalDetailsForm

from subscriptions.views import StripeObjectMixin


class WizardView(StripeObjectMixin, SessionWizardView):
    object = None
    amount = 20

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
        # Make sure charge_id can't come in from outside
        if 'charge_id' in self.request.POST:
            self.request.POST = self.request.POST.copy()
            del self.request.POST['charge_id']
        return super(WizardView, self).post(*args, **kwargs)

    def get_template_names(self):
        return [self.TEMPLATES[self.steps.current]]

    def get_form_kwargs(self, step):
        kwargs = super(WizardView, self).get_form_kwargs(step)
        if step == 'postcode_field':
            dat = self.get_cleaned_data_for_step('csv')
            kwargs['bulk_lookup'] = BulkLookup(**dat)
        elif step == 'personal_details':
            kwargs['amount'] = self.amount
            kwargs['free'] = False
            if self.request.user.is_authenticated():
                if not self.object:
                    self.object = self.get_object()
                if self.object and self.object.plan.id == settings.PRICING[-1]['plan']:
                    kwargs['free'] = True
        return kwargs

    def get_form_initial(self, step):
        initial = super(WizardView, self).get_form_initial(step)
        if step == 'postcode_field':
            dat = self.get_cleaned_data_for_step('csv')
            bulk_lookup = BulkLookup(**dat)
            for choice in bulk_lookup.field_names():
                if re.match(r'post(\s)*code', choice, flags=re.IGNORECASE):
                    initial['postcode_field'] = choice
                    break
        elif step == 'personal_details':
            if self.request.user.is_authenticated():
                initial['email'] = self.request.user.email
        return initial

    def get_form_step_data(self, form):
        # If Stripe charge was successful, make sure it's stored so it isn't
        # tried again
        if 'charge_id' in form.cleaned_data:
            form.data['personal_details-charge_id'] = form.cleaned_data['charge_id']
        return form.data

    def get_context_data(self, form, **kwargs):
        context = super(WizardView, self).get_context_data(form=form, **kwargs)
        if self.steps.current == 'csv':
            return context

        csv_data = self.get_cleaned_data_for_step('csv')
        bulk_lookup = BulkLookup(**csv_data)

        if self.steps.current == 'postcode_field':
            context['bulk_lookup'] = {
                'field_names': bulk_lookup.field_names(),
                'example_rows': bulk_lookup.example_rows(),
            }
            return context

        # output_options or personal_details
        pc_data = self.get_cleaned_data_for_step('postcode_field')
        context['num_good_rows'] = bulk_lookup.num_rows() - pc_data['bad_rows']
        if self.steps.current == 'personal_details':
            context['price'] = self.amount
            context['STRIPE_PUBLIC_KEY'] = settings.STRIPE_PUBLIC_KEY
            if self.object and self.object.plan.id == settings.PRICING[-1]['plan']:
                context['price'] = 0
        return context

    def done(self, form_list, form_dict, **kwargs):
        data = self.get_all_cleaned_data()
        output_options = data.pop('output_options')
        bulk_lookup = BulkLookup.objects.create(**data)
        bulk_lookup.output_options.add(*output_options)
        return redirect('finished', pk=bulk_lookup.id, token=bulk_lookup.charge_id)


class FinishedView(DetailView):
    model = BulkLookup
    template_name = 'bulk_lookup/finished.html'

    def get_object(self, *args, **kwargs):
        obj = super(FinishedView, self).get_object(*args, **kwargs)
        if self.kwargs['token'] != obj.charge_id:
            raise PermissionDenied
        return obj
