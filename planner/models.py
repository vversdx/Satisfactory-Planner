"""Data models for the Satisfactory production line planner."""
from django.contrib.auth.models import User
from django.db import models


class Item(models.Model):
    """Any game resource: ore, ingot, part, liquid, gas."""
    name = models.CharField(max_length=100, unique=True, verbose_name='Название')
    icon = models.ImageField(upload_to='items/', verbose_name='Иконка')
    is_liquid = models.BooleanField(default=False, verbose_name='Жидкость или газ')
    is_raw = models.BooleanField(default=False, verbose_name='Сырьё (добывается)')
    tier = models.IntegerField(default=0, verbose_name='Уровень')
    extraction_rate = models.FloatField(
        null=True, blank=True,
        verbose_name='Базовая скорость добычи (ед/мин, для бедного месторождения)'
    )
    energy_value = models.FloatField(default=0.0, verbose_name='Энергоёмкость (МДж)')

    class Meta:
        verbose_name = 'Предмет'
        verbose_name_plural = 'Предметы'
        ordering = ['tier', 'name']

    def __str__(self):
        return self.name


class Building(models.Model):
    """Any placeable structure type."""
    CATEGORY_CHOICES = [
        ('extraction', 'Добыча'),
        ('production', 'Производство'),
        ('energy', 'Энергетика'),
        ('logistics', 'Логистика'),
        ('storage', 'Хранение'),
        ('special', 'Особые'),
    ]

    name = models.CharField(max_length=100, unique=True, verbose_name='Название')
    icon = models.ImageField(upload_to='buildings/icons/', verbose_name='Иконка для списка')
    category = models.CharField(
        max_length=20, choices=CATEGORY_CHOICES, verbose_name='Категория'
    )
    base_power = models.FloatField(default=0, verbose_name='Базовая мощность (МВт)')
    connection_slots = models.IntegerField(default=0, verbose_name='Слотов энергоподключения')
    supports_overclock = models.BooleanField(default=False, verbose_name='Поддержка разгона')

    class Meta:
        verbose_name = 'Здание'
        verbose_name_plural = 'Здания'
        ordering = ['category', 'name']

    def __str__(self):
        return self.name


class BuildingPort(models.Model):
    """
    Describes one port on a building type.
    Ports of the same direction and accepted_form are interchangeable.
    """
    DIRECTION_CHOICES = [
        ('input', 'Вход'),
        ('output', 'Выход'),
    ]
    FORM_CHOICES = [
        ('solid', 'Твёрдое'),
        ('liquid', 'Жидкость/Газ'),
    ]

    building = models.ForeignKey(
        Building, on_delete=models.CASCADE, related_name='ports',
        verbose_name='Здание'
    )
    direction = models.CharField(
        max_length=10, choices=DIRECTION_CHOICES, verbose_name='Направление'
    )
    accepted_form = models.CharField(
        max_length=10, choices=FORM_CHOICES, verbose_name='Форма ресурса'
    )
    label = models.CharField(max_length=50, blank=True, verbose_name='Метка')

    class Meta:
        verbose_name = 'Порт здания'
        verbose_name_plural = 'Порты зданий'
        ordering = ['direction', 'label']

    def __str__(self):
        dir_label = 'Вх' if self.direction == 'input' else 'Вых'
        return f'{self.building.name} [{dir_label}] {self.label or self.accepted_form}'


class BuildingCost(models.Model):
    """Resource cost to construct a building."""
    building = models.ForeignKey(
        Building, on_delete=models.CASCADE, related_name='costs',
        verbose_name='Здание'
    )
    item = models.ForeignKey(
        Item, on_delete=models.CASCADE, verbose_name='Предмет'
    )
    amount = models.FloatField(verbose_name='Количество')

    class Meta:
        verbose_name = 'Стоимость здания'
        verbose_name_plural = 'Стоимость зданий'
        unique_together = ('building', 'item')

    def __str__(self):
        return f'{self.item.name} ×{self.amount}'


class Recipe(models.Model):
    """Production recipe with multiple inputs and outputs."""
    name = models.CharField(max_length=200, verbose_name='Название')
    building = models.ForeignKey(
        Building, on_delete=models.CASCADE, related_name='recipes',
        verbose_name='Здание'
    )
    base_duration = models.FloatField(verbose_name='Длительность цикла (сек)')
    is_alternative = models.BooleanField(default=False, verbose_name='Альтернативный')
    max_power = models.FloatField(default=0.0, verbose_name='Макс. энергопотребление (МВт)')

    class Meta:
        verbose_name = 'Рецепт'
        verbose_name_plural = 'Рецепты'
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def inputs(self):
        return self.requirements.filter(direction='input')

    @property
    def outputs(self):
        return self.requirements.filter(direction='output')


class RecipeRequirement(models.Model):
    """
    What item and how much is consumed or produced by a recipe.
    No index — ports of matching form are interchangeable.
    """
    DIRECTION_CHOICES = [
        ('input', 'Вход'),
        ('output', 'Выход'),
    ]

    recipe = models.ForeignKey(
        Recipe, on_delete=models.CASCADE, related_name='requirements',
        verbose_name='Рецепт'
    )
    direction = models.CharField(
        max_length=10, choices=DIRECTION_CHOICES, verbose_name='Направление'
    )
    item = models.ForeignKey(
        Item, on_delete=models.CASCADE, verbose_name='Предмет'
    )
    amount = models.FloatField(verbose_name='Количество за цикл')
    is_waste = models.BooleanField(
        default=False,
        verbose_name='Побочный продукт (требует обязательного вывода)'
    )

    class Meta:
        verbose_name = 'Требование рецепта'
        verbose_name_plural = 'Требования рецептов'
        ordering = ['direction', 'item__name']

    def __str__(self):
        arrow = '←' if self.direction == 'input' else '→'
        waste = ' [отход]' if self.is_waste else ''
        return f'{arrow} {self.item.name} ×{self.amount}{waste}'

    @property
    def per_minute(self):
        """Units per minute at 100% clock speed."""
        return (self.amount / self.recipe.base_duration) * 60


class ProductionLine(models.Model):
    """Saved production line preset."""
    name = models.CharField(max_length=200, verbose_name='Название')
    author = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='lines',
        verbose_name='Автор'
    )
    mma_power_slots = models.BooleanField(
        default=False,
        verbose_name='Улучшение MMA: доп. энергослоты'
    )
    is_published = models.BooleanField(default=False, verbose_name='Опубликовано')
    total_power = models.FloatField(default=0, verbose_name='Потребление (МВт)')
    total_buildings = models.IntegerField(default=0, verbose_name='Всего зданий')
    layout_json = models.JSONField(default=dict, verbose_name='Схема линии')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    class Meta:
        verbose_name = 'Производственная линия'
        verbose_name_plural = 'Производственные линии'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} ({self.author})'


class PlacedBuilding(models.Model):
    """Single placed building instance within a line."""
    line = models.ForeignKey(
        ProductionLine, on_delete=models.CASCADE, related_name='placed_buildings',
        verbose_name='Линия'
    )
    building_type = models.ForeignKey(
        Building, on_delete=models.CASCADE, verbose_name='Тип здания'
    )
    x = models.IntegerField(verbose_name='X')
    y = models.IntegerField(verbose_name='Y')
    recipe = models.ForeignKey(
        Recipe, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Рецепт'
    )
    overclock = models.FloatField(default=1.0, verbose_name='Разгон (1.0 = 100%)')
    somersloop_active = models.BooleanField(
        default=False,
        verbose_name='Петлевик активен (удвоение выхода, ×4 энергии)'
    )

    # For external input generators
    is_external_input = models.BooleanField(
        default=False, verbose_name='Внешний ввод'
    )
    external_item = models.ForeignKey(
        Item, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='external_sources', verbose_name='Предмет внешнего ввода'
    )
    external_rate = models.FloatField(
        null=True, blank=True, verbose_name='Объём внешнего ввода (ед/мин)'
    )

    # For extractors / miners
    resource_purity = models.FloatField(
        null=True, blank=True, verbose_name='Богатство месторождения (0.5/1.0/2.0)'
    )

    # For splitters
    splitter_config = models.JSONField(
        null=True, blank=True,
        verbose_name='Настройка разветвителя: {"left": item_id|"any"|"overflow", ...}'
    )

    class Meta:
        verbose_name = 'Размещённое здание'
        verbose_name_plural = 'Размещённые здания'

    def __str__(self):
        return f'{self.building_type.name} @ ({self.x}, {self.y})'


class PortInstance(models.Model):
    """
    Concrete port on a placed building.
    Created automatically when a building is placed or recipe is assigned.
    The item field is set based on recipe requirements during calculation.
    """
    placed_building = models.ForeignKey(
        PlacedBuilding, on_delete=models.CASCADE, related_name='port_instances',
        verbose_name='Размещённое здание'
    )
    building_port = models.ForeignKey(
        BuildingPort, on_delete=models.CASCADE, verbose_name='Порт здания'
    )
    item = models.ForeignKey(
        Item, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Фактический ресурс'
    )

    class Meta:
        verbose_name = 'Экземпляр порта'
        verbose_name_plural = 'Экземпляры портов'
        unique_together = ('placed_building', 'building_port')

    def __str__(self):
        item_name = self.item.name if self.item else '—'
        return f'{self.placed_building} [{self.building_port.direction}] {item_name}'

    @property
    def direction(self):
        return self.building_port.direction

    @property
    def accepted_form(self):
        return self.building_port.accepted_form


class Connection(models.Model):
    """Belt, pipe, or power connection between two port instances."""
    CONNECTION_TYPES = [
        ('belt', 'Конвейер'),
        ('pipe', 'Труба'),
        #('power', 'Энергокабель'),
        ('well', 'Скважинное соединение')
    ]

    line = models.ForeignKey(
        ProductionLine, on_delete=models.CASCADE, related_name='connections',
        verbose_name='Линия'
    )
    from_port = models.ForeignKey(
        PortInstance, on_delete=models.CASCADE, related_name='output_connections',
        verbose_name='От порта'
    )
    to_port = models.ForeignKey(
        PortInstance, on_delete=models.CASCADE, related_name='input_connections',
        verbose_name='К порту'
    )
    connection_type = models.CharField(
        max_length=10, choices=CONNECTION_TYPES, default='belt',
        verbose_name='Тип соединения'
    )
    belt_level = models.IntegerField(
        null=True, blank=True, verbose_name='Уровень конвейера (Mk.1–Mk.5)'
    )
    pipe_level = models.IntegerField(
        null=True, blank=True, verbose_name='Уровень трубы (Mk.1–Mk.2)'
    )

    class Meta:
        verbose_name = 'Соединение'
        verbose_name_plural = 'Соединения'
        constraints = [
            models.CheckConstraint(
                check=~models.Q(from_port=models.F('to_port')),
                name='no_self_connection'
            )
        ]

    def __str__(self):
        return f'{self.from_port} → {self.to_port}'


class LineOutput(models.Model):
    """Final output of a line (what ends up in Receivers)."""
    line = models.ForeignKey(
        ProductionLine, on_delete=models.CASCADE, related_name='outputs',
        verbose_name='Линия'
    )
    item = models.ForeignKey(
        Item, on_delete=models.CASCADE, verbose_name='Предмет'
    )
    rate = models.FloatField(verbose_name='Объём (ед/мин)')

    class Meta:
        verbose_name = 'Итоговый ресурс'
        verbose_name_plural = 'Итоговые ресурсы'
        unique_together = ('line', 'item')

    def __str__(self):
        return f'{self.item.name}: {self.rate}/мин'


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True, verbose_name='Аватар')
    bio = models.TextField(max_length=500, blank=True, verbose_name='О себе')

    class Meta:
        verbose_name = 'Профиль'
        verbose_name_plural = 'Профили'

    def __str__(self):
        return self.user.username


class Like(models.Model):
    """User like on a published line."""
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, verbose_name='Пользователь'
    )
    line = models.ForeignKey(
        ProductionLine, on_delete=models.CASCADE, related_name='likes',
        verbose_name='Линия'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Лайк'
        verbose_name_plural = 'Лайки'
        unique_together = ('user', 'line')


class Bookmark(models.Model):
    """User bookmarked someone else's line."""
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='bookmarks',
        verbose_name='Пользователь'
    )
    line = models.ForeignKey(
        ProductionLine, on_delete=models.CASCADE, related_name='bookmarked_by',
        verbose_name='Линия'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Закладка'
        verbose_name_plural = 'Закладки'
        unique_together = ('user', 'line')


class GeneratorFuel(models.Model):
    """Allowed fuel type for a power generator building."""
    building = models.ForeignKey(
        Building, on_delete=models.CASCADE, related_name='fuel_types',
        verbose_name='Генератор'
    )
    item = models.ForeignKey(
        Item, on_delete=models.CASCADE, related_name='used_in_generators',
        verbose_name='Топливо'
    )

    class Meta:
        verbose_name = 'Топливо генератора'
        verbose_name_plural = 'Топливо генераторов'
        unique_together = ('building', 'item')

    def __str__(self):
        return f'{self.building.name} ← {self.item.name}'