from django.shortcuts import render

# Create your views here.

def cashier_home(request):
    return render(request, 'cashier.html')