import logging

from django.shortcuts import render
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.cache import never_cache

from .services.errors import ResultNotReady, VideoProcessingError
from .services.processing import load_result, process_upload

logger = logging.getLogger(__name__)


def home(request):
    # Preserve legacy uploads to / without redirecting or losing request.FILES.
    if request.method == 'POST':
        return workspace(request)
    return render(request, 'home.html')


@never_cache
def workspace(request):
    context = dict.fromkeys([
        'output_video', 'input_video', 'compare_video', 'score',
        'before_mean', 'before_std', 'after_mean', 'after_std',
        'processing_report', 'chart_data', 'analysis_url', 'pending_job',
    ])
    context['error_message'] = None
    if request.method == 'POST' and request.FILES.get('video'):
        try:
            context.update(process_upload(request.FILES['video'], job_id=request.POST.get('job_id') or None))
        except VideoProcessingError as exc:
            context['error_message'] = str(exc)
        except Exception:
            logger.exception('Unexpected video processing failure')
            context['error_message'] = 'Xử lý video thất bại. Video gốc vẫn được giữ nếu đã tải lên. Hãy thử lại hoặc kiểm tra nhật ký máy chủ.'
    elif request.method == 'GET' and request.GET.get('job'):
        job_id = request.GET['job']
        status_request = request.GET.get('result_status') == '1'
        try:
            context.update(load_result(job_id))
            if status_request:
                return JsonResponse({'state': 'complete', 'result_url': reverse('workspace') + '?job=' + job_id})
        except ResultNotReady:
            if status_request:
                return JsonResponse({'state': 'pending'}, status=202)
            context['pending_job'] = job_id
        except VideoProcessingError as exc:
            if status_request:
                return JsonResponse({'state': 'error', 'message': str(exc)}, status=400)
            context['error_message'] = str(exc)
    return render(request, 'workspace.html', context)
