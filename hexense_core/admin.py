from django.contrib import admin
from .models import Company, Department, Role, UserProfile, Conversation, Message, GptPackageGroup, GptPackage, GptService, GptModel, GptPackageFile
from django.contrib.postgres.fields import JSONField
from django.db import models
from django.forms import widgets
from django_json_widget.widgets import JSONEditorWidget

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'address')
    search_fields = ('name', 'description')
    readonly_fields = ('logo',)
    fields = ('name', 'description', 'address', 'logo', 'openai_api_key', 'gemini_api_key', 
             'claude_api_key', 'deepseek_api_key', 'azure_api_key', 'azure_endpoint')

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'parent')
    list_filter = ('company',)
    search_fields = ('name', 'description')
    fields = ('company', 'name', 'description', 'parent')

@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('name', 'department')
    list_filter = ('department__company',)
    search_fields = ('name', 'description')
    fields = ('department', 'name', 'description')

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'company', 'department', 'role', 'phone_number', 'is_current')
    list_filter = ('company', 'department', 'role')
    search_fields = ('user__username', 'phone_number')
    readonly_fields = ('avatar',)
    fields = ('user', 'company', 'department', 'role', 'phone_number', 'avatar', 
             'gpt_preferences', 'work_experience_notes', 'is_current')

class MessageInline(admin.TabularInline):
    formfield_overrides = {
        models.JSONField: {"widget": JSONEditorWidget}
    }
    model = Message
    extra = 0
    readonly_fields = ('timestamp',)
    fields = ('sender', 'content', 'gpt_package', 'actions', 'timestamp')
    ordering = ('timestamp',)

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('user_profile__user', 'created_at', 'updated_at')
    list_filter = ('user_profile__user', 'created_at')
    search_fields = ('user_profile__user__username', 'topic')
    readonly_fields = ('created_at', 'updated_at')
    fields = ('user_profile', 'topic', 'created_at', 'updated_at')
    inlines = [MessageInline]

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    formfield_overrides = {
        models.JSONField: {"widget": JSONEditorWidget}
    }
    list_display = ('conversation', 'sender', 'gpt_package', 'timestamp')
    list_filter = ('sender', 'timestamp', 'gpt_package')
    search_fields = ('content', 'conversation__title')
    readonly_fields = ('timestamp',)
    fields = ('conversation', 'sender', 'content', 'gpt_package', 'actions', 'timestamp')

@admin.register(GptPackageGroup)
class GptPackageGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'key')
    search_fields = ('name', 'key', 'description')
    fields = ('key', 'name', 'description')

class GptPackageFileInline(admin.TabularInline):
    model = GptPackageFile
    extra = 0
    fields = ('file', 'description', 'uploaded_at', 'uploaded_by')
    readonly_fields = ('uploaded_at',)

@admin.register(GptPackage)
class GptPackageAdmin(admin.ModelAdmin):
    list_display = ('name', 'key', 'model', 'group', 'is_default')
    list_filter = ('group', 'is_default')
    search_fields = ('name', 'key', 'description')
    filter_horizontal = ('allowed_roles', 'services')
    fields = ('group', 'key', 'name', 'model', 'description', 'system_prompt', 'services', 
             'allowed_roles', 'is_default')
    inlines = [GptPackageFileInline]

@admin.register(GptService)
class GptServiceAdmin(admin.ModelAdmin):
    formfield_overrides = {
        models.JSONField: {"widget": JSONEditorWidget}
    }
    list_display = ('name', 'key', 'group', 'function_name', 'is_active')
    list_filter = ('group', 'is_active')
    search_fields = ('name', 'key', 'description', 'function_name')
    fields = ('group', 'key', 'name', 'description', 'input_schema', 'output_schema', 
             'function_name', 'default_params', 'is_active')


@admin.register(GptModel)
class GptModelAdmin(admin.ModelAdmin):
    list_display = ('name', 'provider', 'is_active')
    search_fields = ('name', 'key')
    list_filter = ('provider', 'is_active')
