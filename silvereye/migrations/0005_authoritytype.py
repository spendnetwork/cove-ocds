# Generated by Django 2.2.14 on 2020-09-04 13:10

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('silvereye', '0004_fieldcoverage'),
    ]

    operations = [
        migrations.CreateModel(
            name='AuthorityType',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('authority_name', models.CharField(max_length=1024)),
                ('authority_type', models.CharField(max_length=1024)),
                ('source', models.CharField(max_length=1024)),
            ],
        ),
    ]