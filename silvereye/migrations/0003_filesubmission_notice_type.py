# Generated by Django 2.2.14 on 2020-09-04 00:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('silvereye', '0002_auto_20200824_1355'),
    ]

    operations = [
        migrations.AddField(
            model_name='filesubmission',
            name='notice_type',
            field=models.CharField(max_length=128, null=True),
        ),
    ]
