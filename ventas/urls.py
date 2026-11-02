from django.urls import path
from django.views.generic import RedirectView

from . import views

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="producto_list", permanent=False), name="home"),
    path("productos/", views.producto_list, name="producto_list"),
    path("productos/nuevo/", views.producto_create, name="producto_create"),
    path("productos/<int:pk>/", views.producto_detail, name="producto_detail"),
    path("productos/<int:pk>/editar/", views.producto_update, name="producto_update"),
    path("productos/<int:pk>/eliminar/", views.producto_delete, name="producto_delete"),
    path("ventas/", views.venta_list, name="venta_list"),
    path("ventas/nueva/", views.venta_create, name="venta_create"),
    path("ventas/<int:pk>/", views.venta_detail, name="venta_detail"),
    path("ventas/<int:pk>/editar/", views.venta_update, name="venta_update"),
    path("ventas/<int:pk>/eliminar/", views.venta_delete, name="venta_delete"),
]