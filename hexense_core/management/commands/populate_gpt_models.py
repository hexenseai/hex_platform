from django.core.management.base import BaseCommand
from hexense_core.models import GptModel, Company
import openai
import anthropic
import google.generativeai as genai
import os
import json


def load_known_models():
    base_dir = os.path.dirname(os.path.dirname(__file__))  # hexense_core/
    file_path = os.path.join(base_dir, 'resources', 'known_models.json')
    if not os.path.exists(file_path):
        return {}
    with open(file_path, 'r') as f:
        return json.load(f)


class Command(BaseCommand):
    help = "LLM sağlayıcılarındaki modelleri GptModel tablosuna kaydeder (OpenAI, Anthropic, Gemini)."

    def add_arguments(self, parser):
        parser.add_argument('company_name', type=str)

    def handle(self, *args, **options):
        company_name = options['company_name']
        try:
            company = Company.objects.get(name__iexact=company_name)
        except Company.DoesNotExist:
            self.stderr.write(self.style.ERROR(f"Firma bulunamadı: {company_name}"))
            return

        self.known_models = load_known_models()
        self.import_openai(company)
        self.import_anthropic(company)
        self.import_gemini(company)

    def import_openai(self, company):
        if not company.openai_api_key:
            self.stdout.write("OpenAI anahtarı bulunamadı.")
            return

        openai.api_key = company.openai_api_key
        try:
            models = openai.models.list().data
            for model in models:
                self.upsert_model('openai', model.id)
        except Exception as e:
            self.stderr.write(f"OpenAI hatası: {str(e)}")

    def import_anthropic(self, company):
        if not company.claude_api_key:
            self.stdout.write("Anthropic anahtarı bulunamadı.")
            return

        try:
            client = anthropic.Anthropic(api_key=company.claude_api_key)
            models = client.models.list().data
            for model in models:
                self.upsert_model('anthropic', model.id)
        except Exception as e:
            self.stderr.write(f"Anthropic hatası: {str(e)}")

    def import_gemini(self, company):
        if not company.gemini_api_key:
            self.stdout.write("Gemini anahtarı bulunamadı.")
            return

        try:
            genai.configure(api_key=company.gemini_api_key)
            models = genai.list_models()
            for model in models:
                if model.supported_generation_methods:
                    model_id = model.name.replace("models/", "")
                    self.upsert_model('gemini', model_id)
        except Exception as e:
            self.stderr.write(f"Gemini hatası: {str(e)}")

    def upsert_model(self, provider, model_key):
        meta = self.known_models.get(model_key, {})
        obj, created = GptModel.objects.update_or_create(
            key=model_key,
            defaults={
                'provider': provider,
                'name': model_key,
                'description': f"{provider.capitalize()}: {model_key}",
                'is_active': True,
                'context_window': meta.get("context_window"),
                'supports_function_call': meta.get("supports_function_call", False),
                'supports_multimodal': meta.get("supports_multimodal", False),
                'supports_tool_use': meta.get("supports_tool_use", False),
                'capabilities': meta.get("capabilities", []),
                'input_types': meta.get("input_types", []),
                'output_types': meta.get("output_types", ["text"]),
                'optimized_for': meta.get("optimized_for", []),
                'pricing_per_1k': meta.get("pricing_per_1k", {}),
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"Model eklendi: {model_key}"))
        else:
            self.stdout.write(self.style.WARNING(f"Güncellendi: {model_key}"))
