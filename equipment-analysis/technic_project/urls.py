from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.views.decorators.csrf import csrf_exempt
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    # The preview is embedded in a cross-site iframe. Some browsers block the
    # CSRF cookie there even with SameSite=None, so keep authentication usable
    # while all state-changing application forms remain CSRF-protected.
    path(
        'login/',
        csrf_exempt(auth_views.LoginView.as_view(template_name='registration/login.html')),
        name='login',
    ),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('', include('analysis.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
