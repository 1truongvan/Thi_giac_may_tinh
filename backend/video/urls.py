from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('workspace/', views.workspace, name='workspace'),
]
