from django.urls import path

from .views import log_detail, log_list


urlpatterns = [
    path("", log_list, name="log_list"),
    path("<uuid:log_entry_pk>/", log_detail, name="log_detail"),
]
