from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.views.generic import ListView
from .models import Paper
from .forms import PaperForm

class PaperListView(ListView):
    model = Paper
    template_name = "papers/paper_list.html"
    context_object_name = "papers"
    paginate_by = 25
    ordering = ("name_paper",)

def paper_create_view(request):
    form = PaperForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "کاغذ با موفقیت ایجاد شد.")
        return redirect(reverse("carton_pricing:paper_list"))
    return render(request, "papers/paper_form.html", {"form": form, "mode": "create"})

def paper_update_view(request, pk: int):
    obj = get_object_or_404(Paper, pk=pk)
    form = PaperForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "کاغذ به‌روزرسانی شد.")
        return redirect(reverse("carton_pricing:paper_list"))
    return render(request, "papers/paper_form.html", {"form": form, "mode": "update"})
