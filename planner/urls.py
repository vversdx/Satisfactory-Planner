"""URL configuration for the planner app."""
from django.urls import path
from django.contrib.auth import views as auth_views

from .views.profile_edit import edit_profile
from .views.auth import register_view
from .views.home import HomeView, my_lines_view, profile_view, toggle_publish, delete_line, delete_bookmark
from .views.builder import (
    build_view, load_line, save_line, toggle_bookmark, toggle_like, get_line,
)
from .views.api import (
    calculate_preview, get_all_buildings, get_all_items,
    get_all_recipes, get_extractor_options, get_recipes_for_item,
)


urlpatterns = [
    # Pages
    path('', HomeView.as_view(), name='home'),

    path('profile/', profile_view, name='profile'),
    path('profile/edit/', edit_profile, name='edit_profile'),

    path('my-lines/', my_lines_view, name='my_lines'),
    path('toggle-publish/<int:line_id>/', toggle_publish, name='toggle_publish'),
    path('api/line/<int:line_id>/', get_line, name='get_line'),
    path('delete-line/<int:line_id>/', delete_line, name='delete_line'),
    path('delete-bookmark/<int:line_id>/', delete_bookmark, name='delete_bookmark'),
    path('build/', build_view, name='build'),
    path('line/<int:line_id>/', load_line, name='line_detail'),

    # Actions
    path('api/save-line/', save_line, name='save_line'),
    path('api/calculate/', calculate_preview, name='calculate_preview'),
    path('api/like/<int:line_id>/', toggle_like, name='toggle_like'),
    path('api/bookmark/<int:line_id>/', toggle_bookmark, name='toggle_bookmark'),

    # Data
    path('api/items/', get_all_items, name='api_items'),
    path('api/recipes/', get_all_recipes, name='api_recipes'),
    path('api/buildings/', get_all_buildings, name='api_buildings'),
    path('api/recipes/<int:item_id>/', get_recipes_for_item, name='api_recipes_for_item'),
    path('api/extractor-options/<int:item_id>/', get_extractor_options, name='api_extractor_options'),

    path('accounts/login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('accounts/register/', register_view, name='register'),
]
