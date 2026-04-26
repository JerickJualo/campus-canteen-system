from django.shortcuts import render

# Create your views here.
def inventory_home(request):
    return render(request, 'inventory.html')