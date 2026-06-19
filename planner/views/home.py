"""Home page, profile, and my lines views."""
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView

from ..models import Like, ProductionLine, Bookmark


class HomeView(ListView):
    """Home page: list of recently published production lines."""
    model = ProductionLine
    template_name = 'planner/home.html'
    context_object_name = 'lines'
    paginate_by = 10

    def get_queryset(self):
        return ProductionLine.objects.filter(
            is_published=True
        ).select_related('author').prefetch_related('outputs__item', 'likes').order_by('-created_at')


def profile_view(request):
    user_id = request.GET.get('user')
    if user_id:
        profile_user = get_object_or_404(User, id=user_id)
    else:
        profile_user = request.user

    published_count = profile_user.lines.filter(is_published=True).count()
    likes_received = Like.objects.filter(line__author=profile_user).count()
    bookmark_count = profile_user.bookmarks.count() if profile_user == request.user else 0
    published_lines = profile_user.lines.filter(
        is_published=True
    ).prefetch_related('outputs__item', 'likes')

    context = {
        'profile_user': profile_user,
        'published_count': published_count,
        'likes_received': likes_received,
        'published_lines': published_lines,
        'bookmark_count': bookmark_count,
    }
    return render(request, 'planner/profile.html', context)


@login_required
def my_lines_view(request):
    """User's own lines and bookmarks."""
    own_lines = request.user.lines.all().prefetch_related('outputs__item', 'likes')
    bookmarked_lines = ProductionLine.objects.filter(
        bookmarked_by__user=request.user
    ).select_related('author').prefetch_related('outputs__item', 'likes')

    context = {
        'own_lines': own_lines,
        'bookmarked_lines': bookmarked_lines,
    }
    return render(request, 'planner/my_lines.html', context)

@login_required
def toggle_publish(request, line_id):
    line = get_object_or_404(ProductionLine, id=line_id, author=request.user)
    line.is_published = not line.is_published
    line.save()
    return redirect('my_lines')

@login_required
def delete_line(request, line_id):
    line = get_object_or_404(ProductionLine, id=line_id, author=request.user)
    line.delete()
    return redirect('my_lines')

@login_required
def delete_bookmark(request, line_id):
    Bookmark.objects.filter(user=request.user, line_id=line_id).delete()
    return redirect('my_lines')
