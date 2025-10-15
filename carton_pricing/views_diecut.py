# carton_pricing/views_diecut.py
from django.http import JsonResponse
from django.conf import settings
from pathlib import Path
from .services.diecut import DiecutCalculator

def diecut_calc_api(request):
    if request.method != "POST":
        return JsonResponse({"error":"method not allowed"}, status=405)
    data = {
        "layers": request.POST.get("layers"),
        "flute": request.POST.get("flute"),
        "length_cm": request.POST.get("length_cm"),
        "width_cm": request.POST.get("width_cm"),
        "height_cm": request.POST.get("height_cm"),
        "door_code": request.POST.get("door_code"),
        "pieces": request.POST.get("pieces"),
        "qty": request.POST.get("qty"),
        "machine": request.POST.get("machine") or "default",
    }
    calc = DiecutCalculator(Path(settings.BASE_DIR) / "carton_pricing" / "config" / "diecut_rules.json")
    out = calc.calculate(data)
    return JsonResponse(out)
