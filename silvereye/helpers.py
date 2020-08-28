import json
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
import logging
import os
import re
from urllib.parse import urlparse, parse_qsl, urlencode

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import get_storage_class
import requests
from django.db import connections
from django.db.models import Sum
from django.db.models.functions import Coalesce

import silvereye
from bluetail.helpers import UpsertDataHelpers
from silvereye.models import FileSubmission

logger = logging.getLogger(__name__)

SILVEREYE_DIR = silvereye.__path__[0]


class S3_helpers():
    def retrieve_data_from_S3(self, id):
        logger.info("Attempting to download file for SuppliedData from S3: %s", id)

        upsert_helper = UpsertDataHelpers()
        s3_storage = get_storage_class(settings.S3_FILE_STORAGE)()

        directories, filenames = s3_storage.listdir(name=id)

        for filename in filenames:
            original_file_path = os.path.join(id, filename)
            logger.info(f"Downloading {original_file_path}")
            filename_root = os.path.splitext(filename)[0]

            # Create FileSubmission entry
            supplied_data, created = FileSubmission.objects.update_or_create(
                id=id,
                defaults={
                    "current_app": "silvereye",
                    "original_file": original_file_path,
                }
            )

            # Extract created date from filename if possible
            try:
                filename_datetime = datetime.strptime(filename_root, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
                supplied_data.created = filename_datetime
            except ValueError:
                logger.debug("Couldn't extract datetime from filename")

            supplied_data.save()
            sync_with_s3(supplied_data)

            # package_json_raw = s3_storage._open(original_file_path)
            # package_json_dict = json.load(package_json_raw)
            # package_json = json.dumps(package_json_dict)
            #
            # upsert_helper.upsert_ocds_data(package_json, supplied_data=supplied_data)


def sync_with_s3(supplied_data):
    logger.info("Syncing supplied_data original_file with S3")
    s3_storage = get_storage_class(settings.S3_FILE_STORAGE)()
    original_filename = supplied_data.original_file.name.split(os.path.sep)[1]
    original_file_path = supplied_data.original_file.path
    # Sync to S3
    if os.path.exists(original_file_path):
        if not s3_storage.exists(supplied_data.original_file.name):
            logger.info("Storing to S3: %s", supplied_data.original_file.name)
            local_file = supplied_data.original_file.read()
            # Temporarily change the storage for the original_file FileField to save to S3
            supplied_data.original_file.storage = s3_storage
            supplied_data.original_file.save(original_filename, ContentFile(local_file))
            # Put storage back to DEFAULT_FILE_STORAGE for
            supplied_data.original_file.storage = get_storage_class(settings.DEFAULT_FILE_STORAGE)()
    # Sync from S3 if not local
    if not os.path.exists(original_file_path):
        if s3_storage.exists(supplied_data.original_file.name):
            logger.info("Retrieving from S3: %s", supplied_data.original_file.name)
            # Switch to S# storage and read file
            supplied_data.original_file.storage = s3_storage
            s3_file = supplied_data.original_file.read()

            supplied_data.original_file.storage = get_storage_class(settings.DEFAULT_FILE_STORAGE)()
            supplied_data.original_file.save(original_filename, ContentFile(s3_file))


class GoogleSheetHelpers():
    def get_sheet(self, url=""):
        # response = requests.get('https://docs.google.com/spreadsheet/ccc?key=0ArM5yzzCw9IZdEdLWlpHT1FCcUpYQ2RjWmZYWmNwbXc&output=csv')
        # XLSX download
        # response = requests.get('https://doc-0s-9k-docs.googleusercontent.com/docs/securesc/n0brkuvlm1o8v4u5up5nq9pasjli738t/e8277pb9tjvu5qsf4c9plmqjshmaadtj/1595943150000/07589777472805171581/07589777472805171581/1FWayBu0AogNhpCNdBUY8JYHHIHYIsTV2?e=download&h=03732756254954671626&authuser=0&nonce=k5isku8rmg6qc&user=07589777472805171581&hash=6qunlod35ocgdevm17se8e9s8k6s7pl2')
        # drive shared link
        # https://drive.google.com/file/d/1FWayBu0AogNhpCNdBUY8JYHHIHYIsTV2/view?usp=sharing
        response = requests.get('https://docs.google.com/spreadsheets/d/1Wkad_nigbS6xti8X0bzagfi8Hy5R2JvggtOMPQSvOpg/export?format=csv&gid=0')
        c = response.content
        return c

    def fix_url(self, url):
        if "docs.google.com/spreadsheets/" in url:
            # file_id = re.search(r"gid=([0-9]+)", parsed.fragment).group(1)

            if "xlsx" in url:
                url = "https://drive.google.com/uc?export=download&id=1FWayBu0AogNhpCNdBUY8JYHHIHYIsTV2"
                return url
            if "export" not in url:
                parsed = urlparse(url)
                if parsed.path.endswith("edit"):
                    gid = re.search(r"gid=([0-9]+)", parsed.fragment).group(1)
                    # guid = parsed.fragment.split("gid=")
                    parsed = parsed._replace(path=parsed.path.replace("edit", "export"))
                    # parsed.path = parsed.path.replace("edit", "export")
                    query = dict(parse_qsl(parsed.query))
                    query["format"] = "csv"
                    query["gid"] = gid
                    query2 = urlencode(query)
                    parsed = parsed._replace(query=query2)
                    parsed = parsed._replace(fragment="")
                    url_new = parsed.geturl()
                    return url_new
        return url


# CF data prep
def prepare_base_json_from_release_df(fixed_df, base_json_path=None):
    max_release_date = datetime.strptime(max(fixed_df["date"]), '%Y-%m-%dT%H:%M:%SZ')
    base_json = {
        "version": "1.1",
        "publisher": {
            "name": fixed_df.iloc[0]["buyer/name"],
            "scheme": fixed_df.iloc[0]["buyer/identifier/scheme"],
            "uid": fixed_df.iloc[0]["buyer/identifier/id"],
        },
        "publishedDate": max_release_date.strftime('%Y-%m-%dT%H:%M:%SZ'),
        # "license": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/2/",
        # "publicationPolicy": "https://www.gov.uk/government/publications/open-contracting",
        "uri": "https://ocds-silvereye.herokuapp.com/"
    }
    if base_json_path:
        with open(base_json_path, "w") as writer:
            json.dump(base_json, writer, indent=2)
    return base_json


def get_published_release_metrics(release_queryset):
    count_tenders = release_queryset.filter(release_tag__contains="tender").count()
    count_awards = release_queryset.filter(release_tag__contains="award").count()
    count_spend = release_queryset.filter(release_tag__contains="spend").count()

    context = {
            "tenders_count": count_tenders,
            "awards_count": count_awards,
            "spend_count": count_spend,
    }
    return context


def update_publisher_monthly_counts():
    sql_path = os.path.join(SILVEREYE_DIR, "metrics", "monthly_counts.sql")

    with connections['default'].cursor() as cursor:
        sql = open(sql_path).read()
        logger.info(f"Executing metric sql from file {sql_path}")
        cursor.execute(sql)


class MetricHelpers():

    def period_descriptions(self):
        return  {
            'current': 'This month',
            '1_month': 'Last month',
            '3_month': 'Last 3 months',
            '6_month': 'Last 6 months',
            '12_month': 'Last 12 months',
            'all': 'All time'
        }

    def comparison_descriptions(self):
        return {
            'preceding': 'preceding',
            '1_year': 'last year',
            '2_year': 'two years ago'
        }

    def percentage_change_value(self, current, previous):
        raw_percent = (100 * (current - previous) / previous) if previous else 0
        return round(raw_percent, 1)

    def period_counts(self, queryset, period_start, period_end):
        if not (period_start is None and period_end is None):
            queryset = queryset.filter(date__gte=period_start, date__lt=period_end)
        return queryset\
        .aggregate(tenders=Coalesce(Sum('count_tenders'), 0), awards=Coalesce(Sum('count_awards'), 0), spend=Coalesce(Sum('count_spend'), 0))

    def period_data(self, queryset, period_start, period_end):
        period_counts = self.period_counts(queryset, period_start, period_end)
        return {
            "counts": {
                "tenders": period_counts.get("tenders"),
                "awards": period_counts.get("awards"),
                "spend": period_counts.get("spend"),
            }
        }

    def comparison_data(self, queryset, comparison_start, comparison_end, period_counts):
        comparison_counts = self.period_counts(queryset, comparison_start, comparison_end)

        return { "change": {
                    "tenders": period_counts.get("tenders") - comparison_counts.get("tenders"),
                    "awards": period_counts.get("awards") - comparison_counts.get("awards"),
                    "spend": period_counts.get("spend") - comparison_counts.get("spend")
                    },
                 "percentages": {
                    "tenders": self.percentage_change_value(period_counts.get("tenders"), comparison_counts.get("tenders")),
                    "awards": self.percentage_change_value(period_counts.get("awards"), comparison_counts.get("awards")),
                    "spend": self.percentage_change_value(period_counts.get("spend"), comparison_counts.get("spend")),
                    },
                 "counts": {
                    "tenders": comparison_counts.get("tenders"),
                    "awards": comparison_counts.get("awards"),
                    "spend": comparison_counts.get("spend"),
                    },
                }

    def metric_data(self, queryset, reference_date, period_option, comparison_option):
        data = {}

        period_start, period_end = self.period_bounds(reference_date=reference_date,
                                                      period_option=period_option)
        period_data = self.period_data(queryset, period_start, period_end)

        if period_option != 'all':
            period_data['comparison'] = {}
            comparison_start, comparison_end = self.comparison_bounds(period_start, period_end, period_option, comparison_option)
            period_data['comparison'] = self.comparison_data(queryset, comparison_start, comparison_end, period_data['counts'])
        return period_data

    def period_bounds(self, reference_date, period_option):
        if period_option == 'all':
            period_start = None
            period_end = None
        elif period_option == 'current':
            period_end = reference_date
            period_start = reference_date.replace(day=1)
        else:
            period_span = self.parse_period_option(period_option)
            period_end = reference_date.replace(day=1)
            period_start = period_end - relativedelta(months=period_span)
        return (period_start, period_end)

    def comparison_bounds(self, period_start, period_end, period_option, comparison_option):
        if period_option == 'current':
            period_span = 1
            period_end = period_start.replace(day=1) + relativedelta(months=period_span)
        else:
            period_span = self.parse_period_option(period_option)
        if comparison_option == 'preceding':
            comparison_start = period_start - relativedelta(months=period_span)
            comparison_end = period_start
        else:
            comparison_span = self.parse_comparison_option(comparison_option)
            comparison_start = period_start - relativedelta(years=comparison_span)
            comparison_end = period_end - relativedelta(years=comparison_span)
        return (comparison_start, comparison_end)

    def parse_comparison_option(self, comparison_option):
        # 1_year
        # 2_year
        return int(comparison_option.split('_')[0])

    def parse_period_option(self, period_option):
        # 1_month
        # 3_month
        # 6_month
        # 12_month
        return int(period_option.split('_')[0])
