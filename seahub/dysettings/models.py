from django.core.cache import cache
from django.db import models


class SettingManager(models.Manager):
    def get_value_by_key(self, key):
        # try cache first, if not found, then db
        cache_key = 'dysettings__%s' % key
        value = cache.get(cache_key)
        if value is None:
            value = self.get(key=key).value
            cache.set(cache_key, value)

        return value

    def save_or_update(self, key, value):
        # save to db and update cache
        try:
            s = self.get(key=key)
            s.value = value
        except Setting.DoesNotExist:
            s = self.model(key=key, value=value)
        s.save(using=self._db)

        cache_key = 'dysettings__%s' % key
        cache.set(cache_key, value)
        return s

class Setting(models.Model):
    key = models.CharField(max_length=512, primary_key=True)
    value = models.CharField(max_length=2048)

    objects = SettingManager()
