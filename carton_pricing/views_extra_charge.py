from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from .models import ExtraCharge
from .forms import ExtraChargeForm

class ExtraChargeList(ListView):
    model = ExtraCharge
    template_name = "carton_pricing/extra_charge_list.html"
    context_object_name = "items"

class ExtraChargeCreate(CreateView):
    model = ExtraCharge
    form_class = ExtraChargeForm
    template_name = "carton_pricing/extra_charge_form.html"
    success_url = reverse_lazy("carton_pricing:extracharge_list")

    def form_valid(self, form):
        messages.success(self.request, "بند اضافی با موفقیت ایجاد شد.")
        return super().form_valid(form)

class ExtraChargeUpdate(UpdateView):
    model = ExtraCharge
    form_class = ExtraChargeForm
    template_name = "carton_pricing/extra_charge_form.html"
    success_url = reverse_lazy("carton_pricing:extracharge_list")

    def form_valid(self, form):
        messages.success(self.request, "بند اضافی با موفقیت ویرایش شد.")
        return super().form_valid(form)

class ExtraChargeDelete(DeleteView):
    model = ExtraCharge
    template_name = "carton_pricing/extra_charge_confirm_delete.html"
    success_url = reverse_lazy("carton_pricing:extracharge_list")

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "بند اضافی حذف شد.")
        return super().delete(request, *args, **kwargs)
