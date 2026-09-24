from rest_framework.routers import DefaultRouter

from sanaap_backend_challenge_api.documents.views import FileViewSet

router = DefaultRouter()
router.register("files", FileViewSet, basename="file")

urlpatterns = router.urls
