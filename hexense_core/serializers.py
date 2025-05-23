from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Company, Department, Role, UserProfile, Message, Conversation, GptPackageGroup, GptPackage, GptService, GptModel

class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = [
            'id',
            'name',
            'description',
            'address',
            'logo',
            'openai_api_key',
            'gemini_api_key',
            'claude_api_key',
            'deepseek_api_key',
            'azure_api_key',
            'azure_endpoint'
        ]

class DepartmentSerializer(serializers.ModelSerializer):
    company = CompanySerializer(read_only=True)
    company_id = serializers.PrimaryKeyRelatedField(
        queryset=Company.objects.all(), source='company', write_only=True
    )

    class Meta:
        model = Department
        fields = [
            'id',
            'name',
            'description',
            'parent',
            'company',
            'company_id'
        ]

class RoleSerializer(serializers.ModelSerializer):
    department = DepartmentSerializer(read_only=True)
    department_id = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(), source='department', write_only=True, required=False
    )

    class Meta:
        model = Role
        fields = [
            'id',
            'name',
            'description',
            'department',
            'department_id'
        ]

class GptPackageMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = GptPackage
        fields = ['id', 'name', 'description', 'is_default', 'group']

class UserProfileSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)
    company = CompanySerializer(read_only=True)
    company_id = serializers.PrimaryKeyRelatedField(
        queryset=Company.objects.all(), source='company', write_only=True, required=False
    )
    department = DepartmentSerializer(read_only=True)
    department_id = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(), source='department', write_only=True, required=False
    )
    role = RoleSerializer(read_only=True)
    role_id = serializers.PrimaryKeyRelatedField(
        queryset=Role.objects.all(), source='role', write_only=True, required=False
    )
    is_current = serializers.BooleanField(read_only=True)
    gpt_packages = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = [
            'id',
            'user',
            'company',
            'company_id',
            'department',
            'department_id',
            'role',
            'role_id',
            'phone_number',
            'avatar',
            'gpt_preferences',
            'work_experience_notes',
            'is_current',
            'gpt_packages'
        ]

    def get_gpt_packages(self, obj):
        if obj.role:
            packages = GptPackage.objects.filter(allowed_roles=obj.role).select_related('group').distinct()
            return GptPackageMiniSerializer(packages, many=True).data
        return []

class MessageSerializer(serializers.ModelSerializer):
    conversation = serializers.PrimaryKeyRelatedField(queryset=Conversation.objects.all())
    gpt_package = serializers.PrimaryKeyRelatedField(queryset=GptPackage.objects.all(), required=False, allow_null=True)
    
    class Meta:
        model = Message
        fields = ['id', 'conversation', 'sender', 'content', 'gpt_package', 'actions', 'timestamp']
        read_only_fields = ['sender', 'timestamp']
        
    def create(self, validated_data):
        # sender alanı view tarafından sağlanacak
        return Message.objects.create(**validated_data)

class ConversationSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True, read_only=True)
    topic = serializers.CharField(read_only=True)
    topic_embedding = serializers.JSONField(read_only=True)
    
    class Meta:
        model = Conversation
        fields = ['id', 'created_at', 'updated_at', 'messages', 'topic', 'topic_embedding']
        read_only_fields = ['created_at', 'updated_at']

class GptModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = GptModel
        fields = ['id', 'key', 'provider', 'name', 'description', 'is_active']

class GptPackageGroupMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = GptPackageGroup
        fields = ['id', 'key', 'name', 'description']


class GptServiceSerializer(serializers.ModelSerializer):
    group = GptPackageGroupMiniSerializer(read_only=True)
    group_id = serializers.PrimaryKeyRelatedField(
        queryset=GptPackageGroup.objects.all(), source='group', write_only=True
    )

    class Meta:
        model = GptService
        fields = [
            'id', 'key', 'name', 'description',
            'input_schema', 'output_schema',
            'function_name', 'default_params',
            'group', 'group_id'
        ]


class GptPackageSerializer(serializers.ModelSerializer):
    group = GptPackageGroupMiniSerializer(read_only=True)
    group_id = serializers.PrimaryKeyRelatedField(
        queryset=GptPackageGroup.objects.all(), source='group', write_only=True
    )
    allowed_roles = RoleSerializer(many=True, read_only=True)
    services = GptServiceSerializer(many=True, read_only=True)
    model = GptModelSerializer(read_only=True)
    model_id = serializers.PrimaryKeyRelatedField(
        queryset=GptModel.objects.all(),
        source='model',
        write_only=True
    )

    class Meta:
        model = GptPackage
        fields = [
            'id', 'key', 'name', 'description',
            'system_prompt', 'group', 'group_id',
            'allowed_roles', 'services', 'is_default',
            'model', 'model_id'
        ]

class WhoAmISerializer(serializers.ModelSerializer):
    profiles = UserProfileSerializer(many=True, read_only=True)
    current_profile = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'profiles', 'current_profile']

    def get_current_profile(self, obj):
        current = obj.profiles.filter(is_current=True).first()
        return UserProfileSerializer(current).data if current else None
