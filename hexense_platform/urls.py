from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from hexense_core.views import LoginView, LogoutView, WhoAmIView
from django.views.generic import TemplateView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/core/', include('hexense_core.urls')),  # 💡 Hexense Core API burada
    path('', TemplateView.as_view(template_name='chat.html')),
    path('login/', TemplateView.as_view(template_name='login.html')),
    # 🔐 Global login/logout işlemleri:
    path('api/auth/login/', LoginView.as_view(), name='login'),
    path('api/auth/logout/', LogoutView.as_view(), name='logout'),
    path('api/auth/whoami/', WhoAmIView.as_view(), name='whoami')
]

# Development ortamında medya ve statik dosyaların sunulması
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)