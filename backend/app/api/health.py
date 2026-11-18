from fastapi import APIRouter

from app.core import registry

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/")
def health_check():
    return {
        "backend": "running",
        "model_loaded": registry.yolo_detector is not None,
        "model_path": str(registry.yolo_detector.model_path) if registry.yolo_detector else None,
        "status": "healthy",
    }
