from fastapi import APIRouter
from fastapi.responses import RedirectResponse


router = APIRouter(prefix="/legal", tags=["legal"])


# External legal URLs
PRIVACY_URL = "https://www.hyperlabsai.com/privacypolicy"
APPLE_EULA_URL = "https://www.apple.com/legal/internet-services/itunes/dev/stdeula/"


@router.get("/privacy")
async def privacy_policy():
    return RedirectResponse(url=PRIVACY_URL, status_code=307)


@router.get("/terms")
async def terms_of_use():
    return RedirectResponse(url=APPLE_EULA_URL, status_code=307)


