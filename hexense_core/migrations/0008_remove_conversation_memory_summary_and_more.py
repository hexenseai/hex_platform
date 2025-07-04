# Generated by Django 5.1 on 2025-05-23 09:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hexense_core', '0007_userprofile_company_admin'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='conversation',
            name='memory_summary',
        ),
        migrations.RemoveField(
            model_name='conversation',
            name='title',
        ),
        migrations.AddField(
            model_name='conversation',
            name='topic',
            field=models.TextField(blank=True, help_text='Konuşmanın özet başlığı veya konusu', null=True),
        ),
        migrations.AddField(
            model_name='conversation',
            name='topic_embedding',
            field=models.JSONField(blank=True, help_text='Konuşma başlığının embedding vektörü', null=True),
        ),
    ]
