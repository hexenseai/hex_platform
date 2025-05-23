from django.db import migrations

def forwards_func(apps, schema_editor):
    Conversation = apps.get_model('hexense_core', 'Conversation')
    UserProfile = apps.get_model('hexense_core', 'UserProfile')
    for conv in Conversation.objects.all():
        # Kullanıcının aktif profilini bul
        profile = UserProfile.objects.filter(user=conv.user, is_current=True).first()
        if not profile:
            # Eğer aktif profil yoksa, ilk profili ata
            profile = UserProfile.objects.filter(user=conv.user).first()
        if profile:
            conv.user_profile = profile
            conv.save()

def reverse_func(apps, schema_editor):
    # Geri alma işlemi için bir şey yapmaya gerek yok
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('hexense_core', '0004_conversation_user_profile_userprofile_is_current_and_more'),
    ]

    operations = [
        migrations.RunPython(forwards_func, reverse_func),
    ]
