"""Admin panel configuration."""
from django.contrib import admin

from .models import (
    Bookmark, Building, BuildingPort, BuildingCost, Connection, Item, Like,
    LineOutput, PlacedBuilding, PortInstance, ProductionLine,
    Recipe, RecipeRequirement, GeneratorFuel,
)


class BuildingPortInline(admin.TabularInline):
    model = BuildingPort
    extra = 1


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_liquid', 'is_raw', 'tier', 'extraction_rate')
    list_filter = ('is_liquid', 'is_raw')
    search_fields = ('name',)


class BuildingCostInline(admin.TabularInline):
    model = BuildingCost
    extra = 1
    autocomplete_fields = ['item']


class GeneratorFuelInline(admin.TabularInline):
    model = GeneratorFuel
    extra = 1
    autocomplete_fields = ['item']


@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'base_power', 'connection_slots', 'supports_overclock')
    list_filter = ('category',)
    search_fields = ('name',)
    inlines = (BuildingPortInline, BuildingCostInline, GeneratorFuelInline)


class RecipeRequirementInline(admin.TabularInline):
    model = RecipeRequirement
    extra = 1


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = ('name', 'building', 'base_duration', 'is_alternative')
    list_filter = ('is_alternative', 'building')
    search_fields = ('name',)
    inlines = (RecipeRequirementInline,)


@admin.register(ProductionLine)
class ProductionLineAdmin(admin.ModelAdmin):
    list_display = ('name', 'author', 'is_published', 'mma_power_slots', 'created_at')
    list_filter = ('is_published',)
    search_fields = ('name', 'author__username')


@admin.register(PlacedBuilding)
class PlacedBuildingAdmin(admin.ModelAdmin):
    list_display = ('id', 'line', 'building_type', 'x', 'y', 'overclock', 'somersloop_active')


@admin.register(PortInstance)
class PortInstanceAdmin(admin.ModelAdmin):
    list_display = ('id', 'placed_building', 'building_port', 'item')


@admin.register(Connection)
class ConnectionAdmin(admin.ModelAdmin):
    list_display = ('id', 'line', 'from_port', 'to_port', 'connection_type', 'belt_level', 'pipe_level')
    list_filter = ('connection_type',)


@admin.register(LineOutput)
class LineOutputAdmin(admin.ModelAdmin):
    list_display = ('line', 'item', 'rate')


@admin.register(Like)
class LikeAdmin(admin.ModelAdmin):
    list_display = ('user', 'line', 'created_at')


@admin.register(Bookmark)
class BookmarkAdmin(admin.ModelAdmin):
    list_display = ('user', 'line', 'created_at')