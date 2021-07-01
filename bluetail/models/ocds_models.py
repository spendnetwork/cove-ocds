from django.conf import settings
from django.contrib.postgres.fields import JSONField
from django.db import models
from django_pgviews import view as pgviews

OCDSReleaseJSONBase = models.Model
if settings.USE_PSQL_EXTRA:
    from psqlextra.models import PostgresModel
    OCDSReleaseJSONBase = PostgresModel

from silvereye.models import FileSubmission
from .bluetail_models import Flag


class OCDSPackageDataJSON(models.Model):
    """
    Model to store OCDS JSON package data.
    """
    package_data = JSONField(null=True)
    supplied_data = models.ForeignKey(FileSubmission, on_delete=models.CASCADE, null=True)

    class Meta:
        app_label = 'bluetail'
        db_table = 'bluetail_ocds_package_data_json'


class OCDSPackageData(pgviews.View):
    """
    Model to store OCDS JSON package data.
    """
    package_data = JSONField()
    supplied_data = models.ForeignKey(FileSubmission, on_delete=models.DO_NOTHING)
    uri = models.TextField()
    published_date = models.DateTimeField()
    publisher = JSONField()
    publisher_uid = models.TextField()
    publisher_uri = models.TextField()
    publisher_name = models.TextField()
    publisher_scheme = models.TextField()
    extensions = JSONField()

    sql = """
        SELECT
            package.id,
            package.supplied_data_id,
            package.package_data as package_data,
            package.package_data ->> 'uri' as uri,
            package.package_data ->> 'license' as license,
            package.package_data ->> 'version' as version,
            package.package_data ->> 'publishedDate' as published_date,
            package.package_data ->> 'publicationPolicy' as publication_policy,            
            package.package_data -> 'packages' as packages,
            package.package_data -> 'publisher' as publisher,
            package.package_data -> 'publisher' ->> 'uid' as publisher_uid,
            package.package_data -> 'publisher' ->> 'uri' as publisher_uri,
            package.package_data -> 'publisher' ->> 'name' as publisher_name,
            package.package_data -> 'publisher' ->> 'scheme' as publisher_scheme,
            package.package_data -> 'extensions' as extensions
        FROM bluetail_ocds_package_data_json package
        """

    class Meta:
        app_label = 'bluetail'
        db_table = 'bluetail_ocds_package_data_view'
        managed = False


class OCDSRecordJSON(models.Model):
    """
    Model to store OCDS JSON records.
    """
    ocid = models.TextField(primary_key=True)
    record_json = JSONField()
    package_data = models.ForeignKey(OCDSPackageDataJSON, on_delete=models.CASCADE, null=True)

    class Meta:
        app_label = 'bluetail'
        db_table = 'bluetail_ocds_record_json'


class OCDSReleaseJSON(OCDSReleaseJSONBase):
    """
    Model to store OCDS JSON releases.
    """
    ocid = models.TextField()
    release_id = models.TextField()
    release_json = JSONField()
    package_data = models.ForeignKey(OCDSPackageDataJSON, on_delete=models.CASCADE, null=True)

    class Meta:
        app_label = 'bluetail'
        db_table = 'bluetail_ocds_release_json'
        unique_together = (("ocid", "release_id"),)


class OCDSReleaseView(pgviews.View):
    """
    Postgres view combining releases stored in OCDSReleaseJSON
        with the extracted "compiled_release" from the OCDSRecordJSON
    in to a single queryable model.
    Use the release_tag to filter; "tender", "award", "compiled".
    eg. OCDSReleaseView.objects.filter(release_tag__contains="tender").count()
    """
    ocid = models.TextField(primary_key=True)
    release_id = models.TextField()
    release_tag = JSONField()
    release_json = JSONField()
    package_data = models.ForeignKey(OCDSPackageData, on_delete=models.DO_NOTHING, null=True)

    sql = """
        SELECT
            ocds.ocid,
            ocds.record_json -> 'compiledRelease' ->> 'id' as release_id,
            ocds.record_json -> 'compiledRelease' -> 'tag' as release_tag,
            ocds.record_json -> 'compiledRelease' as release_json,
            ocds.package_data_id
        FROM bluetail_ocds_record_json ocds
        UNION ALL 
        SELECT 
            ocid, 
            release_id, 
            release_json -> 'tag' as release_tag, 
            release_json, 
            package_data_id
        FROM bluetail_ocds_release_json
        """

    class Meta:
        app_label = 'bluetail'
        db_table = 'bluetail_ocds_release_json_view'
        managed = False


class OCDSTender(pgviews.View):
    """
    django-pg-views for extracting Tender details from an OCDSReleaseView object
    Tender as from an OCDS version 1.1 release
    https://standard.open-contracting.org/latest/en/schema/reference/#tender
    """
    # projection = ['bluetail.OCDSReleaseView.*', ]
    # dependencies = ['bluetail.OtherView',]
    ocid = models.TextField(primary_key=True)
    release_id = models.TextField()
    release_json = JSONField()
    package_data_id = models.TextField()
    title = models.TextField()
    description = models.TextField()
    value = models.FloatField()
    currency = models.TextField()
    release_date = models.DateTimeField()
    tender_startdate = models.DateTimeField()
    tender_enddate = models.DateTimeField()
    buyer = models.TextField()
    buyer_id = models.TextField()

    sql = """
        SELECT
            ocds.ocid,
            ocds.release_id,
            ocds.release_json,
            ocds.package_data_id,
            ocds.release_json -> 'tag' as release_tag,
            ocds.release_json ->> 'language' AS language,
            ocds.release_json -> 'tender' ->> 'title' AS title,
            ocds.release_json -> 'tender' ->> 'description' AS description,
            ocds.release_json -> 'tender' -> 'value' ->> 'amount' AS value,
            ocds.release_json -> 'tender' -> 'value' ->> 'currency' AS currency,
            cast(NULLIF(ocds.release_json ->> 'date', '') AS TIMESTAMPTZ) AS release_date,
            cast(NULLIF(ocds.release_json -> 'tender' -> 'tenderPeriod' ->> 'startDate', '') AS TIMESTAMPTZ) AS tender_startdate,
            cast(NULLIF(ocds.release_json -> 'tender' -> 'tenderPeriod' ->> 'endDate', '') AS TIMESTAMPTZ) AS tender_enddate,
            ocds.release_json -> 'buyer' ->> 'name' AS buyer,
            ocds.release_json -> 'buyer' ->> 'id' AS buyer_id
        FROM bluetail_ocds_release_json_view ocds
        """

    @property
    def flags(self):
        return Flag.objects.filter(flagattachment__ocid=self.ocid)

    @property
    def total_warnings(self):
        return self.flags.filter(flag_type="warning").count()

    @property
    def total_errors(self):
        return self.flags.filter(flag_type="error").count()

    class Meta:
        app_label = 'bluetail'
        db_table = 'bluetail_ocds_tender_view'
        managed = False


class OCDSTenderer(pgviews.View):
    """
    View for extracting Party details from an OCDSReleaseView object
    Parties as from an OCDS version 1.1 release in
    https://standard.open-contracting.org/latest/en/schema/reference/#parties
    """
    # dependencies = ['bluetail.OtherView',]
    # projection = ['bluetail.OCDSReleaseView.ocid', ]
    ocid = models.TextField(primary_key=True)
    release_json = JSONField()
    party_json = JSONField()
    party_id = models.TextField()
    party_role = models.TextField()
    party_identifier_scheme = models.TextField()
    party_identifier_id = models.TextField()
    party_legalname = models.TextField()
    party_name = models.TextField()
    party_countryname = models.TextField()
    contact_name = models.TextField()

    sql = """
        SELECT
            ocds.ocid,
            ocds.release_id,
            ocds.release_json,
            party                               as party_json,
            role                                AS party_role,
            party ->> 'id'                     as party_id,
            party -> 'identifier' ->> 'scheme'      as party_identifier_scheme,
            party -> 'identifier' ->> 'id'          as party_identifier_id,
            party -> 'identifier' ->> 'legalName'   as party_legalname,
            party -> 'address' ->> 'countryName'    as party_countryname,

            party ->> 'name'                           party_name,
            party -> 'contactPoint' ->> 'name'      as contact_name
        FROM
            bluetail_ocds_release_json_view ocds,
            LATERAL jsonb_array_elements(ocds.release_json -> 'parties') party,
            LATERAL jsonb_array_elements_text(party -> 'roles') role
        WHERE role = 'tenderer'
        """

    class Meta:
        app_label = 'bluetail'
        db_table = 'bluetail_ocds_tenderers_view'
        managed = False
