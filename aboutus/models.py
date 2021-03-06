import requests
from django.db import models
from django.conf import settings

from wagtail.wagtailcore.models import Page, Orderable
from wagtail.wagtailsearch import index
from wagtail.wagtailadmin.edit_handlers import FieldPanel


class PersonPage(Orderable, Page):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True,
                                related_name='person', on_delete=models.SET_NULL)
    name = models.CharField(max_length=200, null=False)
    contact = models.URLField(null=False)
    github_user = models.CharField(max_length=200, blank=True, null=True)
    job_title = models.CharField(max_length=20)
    description = models.TextField(blank=True, null=True)
    listed = models.BooleanField()
    avatar_url = models.URLField(blank=True, null=True)

    search_fields = Page.search_fields + (
        index.SearchField('name'),
        index.SearchField('job_title'),
        index.SearchField('github_user'),
        index.SearchField('description'),
    )

    content_panels = Page.content_panels + [
        FieldPanel('name'),
        FieldPanel('contact'),
        FieldPanel('github_user'),
        FieldPanel('user'),
        FieldPanel('job_title'),
        FieldPanel('description'),
        FieldPanel('listed')
    ]

    def get_github_link(self):
        if not self.github_user:
            return None
        return 'https://github.com/%s' % self.github_user

    def save(self, *args, **kwargs):
        # update the avatar url
        if self.github_user:
            self.avatar_url\
                = requests.get('https://api.github.com/users/' + self.github_user).json()['avatar_url']
        super().save(*args, **kwargs)
        print(self.avatar_url)


class AboutUsIndexPage(Page):

    def people(self):
        return PersonPage.objects.live().filter(listed=True)
