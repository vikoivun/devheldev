import json, requests
from collections import OrderedDict
from taggit.models import TaggedItemBase, Tag
from modelcluster.contrib.taggit import ClusterTaggableManager

from django.db import models
from django.core.cache import cache
from django.conf import settings
from django.utils.text import slugify

from wagtail.wagtailcore.models import Page, Orderable
from wagtail.wagtailcore.fields import RichTextField
from wagtail.wagtailadmin.edit_handlers import FieldPanel, InlinePanel
from wagtail.wagtailimages.models import Image
from wagtail.wagtailimages.edit_handlers import ImageChooserPanel
from wagtail.wagtailsnippets.models import register_snippet
from wagtail.wagtailsearch import index

from modelcluster.fields import ParentalKey


class ProjectPageTag(TaggedItemBase):
    content_object = ParentalKey('ProjectPage', related_name='tagged_items')


@register_snippet
class ProjectTag(Tag):
    class Meta:
        proxy = True


class ProjectPage(Orderable, Page):
    STATUSES = (
        ('discovery', 'Discovery'),
        ('alpha', 'Alpha'),
        ('beta', 'Beta'),
        ('live', 'LIVE'),
        ('retirement', 'Retirement')
    )
    tags = ClusterTaggableManager(through=ProjectPageTag, blank=True)
    short_description = models.TextField()
    full_description = RichTextField(blank=True)
    image = models.ForeignKey(
        'wagtailimages.Image',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )
    status = models.CharField(max_length=20, choices=STATUSES, default='discovery')
    piwik_id = models.IntegerField(blank=True, null=True)
    uptimerobot_name = models.CharField(blank=True, null=True, max_length=100)

    def save(self, *args, **kwargs):
        if not self.title:
            if self.project:
                self.title = self.project.name
        return super().save(*args, **kwargs)

    search_fields = Page.search_fields + (
        index.SearchField('short_description'),
        index.SearchField('full_description'),
    )

    content_panels = Page.content_panels + [
        FieldPanel('status'),
        FieldPanel('tags'),
        FieldPanel('short_description'),
        FieldPanel('full_description'),
        ImageChooserPanel('image'),
        FieldPanel('piwik_id'),
        FieldPanel('uptimerobot_name'),
        InlinePanel('dynamic_kpis', label="Dynamic key performance indicators"),
        InlinePanel('kpis', label="Key performance indicators"),
        InlinePanel('roles', label="Roles"),
        InlinePanel('links', label="Links"),
    ]

    def piwik_data(self):
        data = cache.get('piwik_' + slugify(self.title))
        if not data and self.piwik_id:
            response = requests.get(
                'https://analytics.hel.ninja/piwik/?idSite=' +
                str(self.piwik_id) +
                '&module=API&period=day&date=last30&method=VisitsSummary.get&format=json&token_auth=' +
                settings.PIWIK_API_TOKEN)
            if response.status_code == 200:
                # piwik_id was valid
                data = response.text
                # data = json.loads(response.text, object_pairs_hook=OrderedDict)
                cache.add('piwik_' + slugify(self.title), data, 3600)
        return data

    def kpi_data(self):
        data = cache.get('kpis_' + slugify(self.title))
        if not data and self.dynamic_kpis.count():
            data = {}
            for kpi in self.dynamic_kpis.all():
                response = requests.get(kpi.object_count_url)
                if response.status_code == 200:
                    json_data = response.json()
                    for key in kpi.object_count_field_name.split('.'):
                        json_data = json_data[key]
                    data[kpi.object_name] = json_data
            # coffeescript wants the data in json
            data = json.dumps(data)
            cache.add('kpis_' + slugify(self.title), data, 3600)
        return data

    def uptime_data(self):
        complete_data = cache.get('uptime')
        if not complete_data and self.uptimerobot_name:
            response = requests.get(
                'https://api.uptimerobot.com/getMonitors?apiKey=' +
                settings.UPTIMEROBOT_API_TOKEN +
                '&format=json&noJsonCallback=1')
            if response.status_code == 200:
                # returns all monitors, we still have to check for matching name
                complete_data = response.json()
                cache.add('uptime', complete_data, 3600)
        try:
            data = [single_data for single_data in
                    complete_data['monitors']['monitor'] if
                    single_data['friendlyname'] == self.uptimerobot_name][0]
            # coffeescript wants the data in json
            data = json.dumps(data)
        # if name doesn't match, return None
        except (IndexError, TypeError, KeyError):
            data = None
        return data


class ProjectRoleType(Orderable, models.Model):
    name = models.CharField(max_length=50)

    def __lt__(self, other):
        if self.sort_order is None:
            return True
        if other.sort_order is None:
            return False
        return int(self.sort_order).__lt__(int(other.sort_order))

    def __str__(self):
        return self.name


class ProjectRole(models.Model):
    TYPES = (
        ('service_manager', 'Service manager'),
        ('tech', 'Tech lead'),
    )
    project = ParentalKey('projects.ProjectPage', related_name='roles')
    type = models.ForeignKey(ProjectRoleType, related_name='roles')
    person = ParentalKey('aboutus.PersonPage', related_name='roles')

    def __str__(self):
        return "%s as %s for %s" % (self.person, self.type, self.project.title)

    class Meta:
        ordering = ('type',)


class ProjectKPI(models.Model):
    project = ParentalKey('projects.ProjectPage', related_name='kpis')
    name = models.CharField(max_length=20)
    description = models.CharField(max_length=200, null=True, blank=True)
    value = models.CharField(max_length=200)


class ProjectObjectCount(models.Model):
    """
    This model allows dynamic KPI data, fetching number of objects at any API endpoint
    """
    project = ParentalKey('projects.ProjectPage', related_name='dynamic_kpis')
    object_name = models.CharField(max_length=40)
    description = models.CharField(max_length=200, null=True, blank=True)
    object_count_url = models.URLField()
    object_count_field_name = models.CharField(default='meta.count', max_length=40)

    def _str__(self):
        return self.object_name

class ProjectLink(models.Model):
    TYPES = (
        ('main', 'Main'),
        ('github', 'GitHub'),
    )

    project = ParentalKey('projects.ProjectPage', related_name='links')
    type = models.CharField(max_length=20, choices=TYPES)
    public = models.BooleanField(default=True)
    description = models.CharField(max_length=200, null=True, blank=True)
    url = models.URLField()

    def __str__(self):
        return "{0} / {1}".format(str(self.project), self.type)


class ProjectIndexPage(Page):
    subpage_types = ['projects.ProjectPage']

    def projects(self):
        return ProjectPage.objects.live()

    def top_projects(self):
        return self.projects()[:5]
