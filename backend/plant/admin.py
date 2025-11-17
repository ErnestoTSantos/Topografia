from django.contrib import admin
from .models import Plant

admin.site.register(Plant)


class PlantAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "dxf_file")
    list_per_page = 25
