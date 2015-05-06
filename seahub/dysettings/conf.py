from django.conf import settings as dj_settings

from .models import Setting

class SettingsProxy():
    def __getattr__(self, name):
        try:
            return Setting.objects.get_value_by_key(name)
        except Setting.DoesNotExist:
            return getattr(dj_settings, name)

    def __setattr__(self, name, value):
        Setting.objects.save_or_update(name, value)

    def __setitem__(self, name, value):
        return self.__setattr__(name, value)


settings = SettingsProxy()
