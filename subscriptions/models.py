from django.conf import settings
from django.db import models

class Subscription(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    stripe_id = models.CharField(max_length=100)

    def __unicode__(self):
        return u"%s (%s)" % (self.user, self.stripe_id)
