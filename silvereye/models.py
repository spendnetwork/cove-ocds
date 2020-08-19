from django.db import models


class Publisher(models.Model):
    publisher_id = models.CharField(max_length=1024, primary_key=True)
    publisher_name = models.CharField(max_length=1024)
    contact_name = models.CharField(max_length=1024, null=True, blank=True, default="")
    contact_email = models.CharField(max_length=1024, null=True, blank=True, default="")
    contact_telephone = models.CharField(max_length=1024, null=True, blank=True, default="")

    class Meta:
        app_label = 'silvereye'
        db_table = 'silvereye_publisher_metadata'


class PublisherMetrics(models.Model):
    publisher_id = models.CharField(max_length=1024, primary_key=True)
    publisher_name = models.CharField(max_length=1024)
    count_lastmonth = models.IntegerField(null=True)
    count_last3months = models.IntegerField(null=True)
    count_last12months = models.IntegerField(null=True)
    average_lastmonth = models.IntegerField(null=True)
    average_last3months = models.IntegerField(null=True)
    average_last12months = models.IntegerField(null=True)

    class Meta:
        app_label = 'silvereye'
        db_table = 'silvereye_publisher_metrics'
