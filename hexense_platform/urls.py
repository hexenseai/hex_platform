from django.urls import path, include, re_path
from django.views.generic import TemplateView
from django.conf import settings # Statik dosya sunumu için
from django.conf.urls.static import static # Statik dosya sunumu için
from django.contrib import admin
from hexense_core.views import LoginView, LogoutView, WhoAmIView, RegisterView # Bunları burada import edin

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/core/', include('hexense_core.urls')), # API endpointleriniz

    # Auth API endpointlerini buraya taşıyabilir veya ayrı bir app'in urls.py'sine alabilirsiniz
    path('api/auth/login/', LoginView.as_view(), name='api_login'),
    path('api/auth/logout/', LogoutView.as_view(), name='api_logout'),
    path('api/auth/whoami/', WhoAmIView.as_view(), name='api_whoami'),
    path('api/auth/register/', RegisterView.as_view(), name='api_register'),
    # React uygulamasının ana HTML dosyasını sunacak catch-all route
    # Bu, API, admin, static ve media URL'leri dışındaki tüm istekleri yakalar.
    re_path(r'^(?!api/|admin/|static/|media/).*$', TemplateView.as_view(template_name="index.html")),
]

# Geliştirme ortamında statik ve medya dosyalarını sunmak için:
if settings.DEBUG:
    # urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT) # Bu satır collectstatic sonrası için
    # Geliştirme sırasında STATICFILES_DIRS'deki dosyaları sunmak için:
    # Django normalde app'lerin static klasörlerini ve STATICFILES_DIRS'i otomatik olarak DEBUG modunda sunar.
    # Eğer React build dosyalarınız (index.html dahil) STATICFILES_DIRS içindeyse
    # ve Django'nun template loader'ı bunu bulamıyorsa, index.html'in templates dizinine konması gerekebilir.
    # En temiz çözüm, React build çıktısındaki index.html'in Django'nun TEMPLATES ayarlarında
    # belirtilen bir DIRS içinde olmasını sağlamaktır.

    # Ya da, index.html'i React build klasöründen Django'nun ana template klasörüne kopyalayan bir script yazılabilir.
    # Veya `TemplateView.as_view(template_name="dist/index.html")` gibi bir yol belirtilebilir,
    # eğer template loader'ınız `REACT_APP_DIR`'i de arıyorsa.

    # Medya dosyaları için:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
