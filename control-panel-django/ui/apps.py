from django.apps import AppConfig


class UiConfig(AppConfig):
    default_auto_field = "django.db.models.AutoField"
    name = "ui"
    verbose_name = "Browser UI shell"