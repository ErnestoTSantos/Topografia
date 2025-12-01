from django.db import models


class Plant(models.Model):
    name = models.CharField(max_length=200)
    dxf_file = models.FileField(upload_to="plants/")
    cep = models.CharField(max_length=255, null=True, blank=True)
    number = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
